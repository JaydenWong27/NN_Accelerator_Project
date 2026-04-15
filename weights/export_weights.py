"""
export_weights.py -- Quantise trained MNIST weights to INT8 and export hex
===========================================================================

Outputs:
    weights_all.hex
        Flat one-byte-per-line hex dump for $readmemh.
    scale_factors.json
        Weight/bias quantisation scales plus fixed requantisation metadata
        for the layer-1 INT32 -> INT8 activation path.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torchvision import datasets, transforms


FC1_IN = 784
FC1_OUT = 128
FC2_OUT = 10
INPUT_SCALE = 127.0
REQUANT_SHIFT = 24

FC1_W_BYTES = FC1_IN * FC1_OUT
FC2_W_BYTES = FC1_OUT * FC2_OUT
FC1_B_BYTES = FC1_OUT
FC2_B_BYTES = FC2_OUT
TOTAL_BYTES = FC1_W_BYTES + FC2_W_BYTES + FC1_B_BYTES + FC2_B_BYTES


class MNISTNet(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.fc1 = nn.Linear(FC1_IN, FC1_OUT)
        self.relu = nn.ReLU()
        self.fc2 = nn.Linear(FC1_OUT, FC2_OUT)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x.view(x.size(0), -1)
        x = self.relu(self.fc1(x))
        return self.fc2(x)


def quantise_symmetric(values: np.ndarray) -> tuple[np.ndarray, float]:
    max_abs = float(np.max(np.abs(values)))
    if max_abs == 0.0:
        return np.zeros_like(values, dtype=np.int8), 1.0

    scale = 127.0 / max_abs
    quantised = np.clip(np.round(values * scale), -128, 127).astype(np.int8)
    return quantised, scale


def write_hex_section(handle, values: np.ndarray, label: str) -> int:
    flat = values.reshape(-1).view(np.uint8)
    for byte in flat:
        handle.write(f"{int(byte):02x}\n")

    count = int(flat.size)
    print(f"  {label:20s}: {count:7,} bytes")
    return count


def calibrate_hidden_activation_max(model: MNISTNet, data_dir: Path) -> tuple[float, str, int]:
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.5,), (0.5,)),
    ])

    try:
        dataset = datasets.MNIST(
            root=str(data_dir),
            train=False,
            download=False,
            transform=transform,
        )
    except RuntimeError as exc:
        return 0.0, f"dataset unavailable ({exc})", 0

    hidden_max = 0.0
    with torch.no_grad():
        for image, _ in dataset:
            hidden = model.relu(model.fc1(image.view(1, -1)))
            current = float(hidden.abs().max().item())
            if current > hidden_max:
                hidden_max = current

    return hidden_max, "MNIST test set", len(dataset)


def analytic_hidden_upper_bound(fc1_w: np.ndarray, fc1_b: np.ndarray) -> float:
    positive_bias = np.maximum(fc1_b, 0.0)
    return float(np.max(np.sum(np.abs(fc1_w), axis=1) + positive_bias))


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    data_dir = script_dir.parent / "data"
    pth_path = script_dir / "mnist_trained.pth"
    hex_path = script_dir / "weights_all.hex"
    json_path = script_dir / "scale_factors.json"

    print(f"Loading model weights from: {pth_path}")
    model = MNISTNet()
    model.load_state_dict(torch.load(pth_path, map_location="cpu"))
    model.eval()

    fc1_w_f32 = model.fc1.weight.detach().cpu().numpy()
    fc1_b_f32 = model.fc1.bias.detach().cpu().numpy()
    fc2_w_f32 = model.fc2.weight.detach().cpu().numpy()
    fc2_b_f32 = model.fc2.bias.detach().cpu().numpy()

    fc1_w_i8, fc1_w_scale = quantise_symmetric(fc1_w_f32)
    fc1_b_i8, fc1_b_scale = quantise_symmetric(fc1_b_f32)
    fc2_w_i8, fc2_w_scale = quantise_symmetric(fc2_w_f32)
    fc2_b_i8, fc2_b_scale = quantise_symmetric(fc2_b_f32)

    fc1_w_hw = fc1_w_i8.T
    fc2_w_hw = fc2_w_i8.T

    if fc1_w_hw.shape != (FC1_IN, FC1_OUT):
        raise ValueError(f"Unexpected FC1 hardware shape: {fc1_w_hw.shape}")
    if fc2_w_hw.shape != (FC1_OUT, FC2_OUT):
        raise ValueError(f"Unexpected FC2 hardware shape: {fc2_w_hw.shape}")

    hidden_max, calibration_source, calibration_samples = calibrate_hidden_activation_max(model, data_dir)
    if hidden_max == 0.0:
        hidden_max = analytic_hidden_upper_bound(fc1_w_f32, fc1_b_f32)
        calibration_source = "analytic upper bound"

    hidden_activation_scale = 1.0 if hidden_max == 0.0 else 127.0 / hidden_max
    layer1_requant_scale = hidden_activation_scale / (INPUT_SCALE * fc1_w_scale)
    layer1_requant_multiplier = int(round(layer1_requant_scale * (1 << REQUANT_SHIFT)))

    if layer1_requant_multiplier <= 0:
        raise ValueError("Layer-1 requant multiplier rounded to zero.")

    scales = {
        "input_scale": INPUT_SCALE,
        "fc1_weight": fc1_w_scale,
        "fc1_bias": fc1_b_scale,
        "fc2_weight": fc2_w_scale,
        "fc2_bias": fc2_b_scale,
        "hidden_activation_scale": hidden_activation_scale,
        "hidden_activation_max": hidden_max,
        "layer1_requant_scale": layer1_requant_scale,
        "layer1_requant_multiplier": layer1_requant_multiplier,
        "layer1_requant_shift": REQUANT_SHIFT,
        "activation_calibration_source": calibration_source,
        "activation_calibration_samples": calibration_samples,
    }

    print("Quantisation scale factors:")
    print(f"  input_scale            : {INPUT_SCALE:.6f}")
    print(f"  fc1_weight            : {fc1_w_scale:.6f}")
    print(f"  fc1_bias              : {fc1_b_scale:.6f}")
    print(f"  fc2_weight            : {fc2_w_scale:.6f}")
    print(f"  fc2_bias              : {fc2_b_scale:.6f}")
    print(f"  hidden_activation     : {hidden_activation_scale:.6f}")
    print(f"  hidden_activation_max : {hidden_max:.6f}")
    print(f"  layer1_requant_scale  : {layer1_requant_scale:.12f}")
    print(f"  layer1_multiplier     : {layer1_requant_multiplier}")
    print(f"  layer1_shift          : {REQUANT_SHIFT}")
    print(f"  calibration_source    : {calibration_source}")
    if calibration_samples:
        print(f"  calibration_samples   : {calibration_samples}")
    print()

    print(f"Writing hex file: {hex_path}")
    with hex_path.open("w", encoding="utf-8") as handle:
        total = 0
        total += write_hex_section(handle, fc1_w_hw, "FC1 weights [784x128]")
        total += write_hex_section(handle, fc2_w_hw, "FC2 weights [128x10]")
        total += write_hex_section(handle, fc1_b_i8, "FC1 biases  [128]")
        total += write_hex_section(handle, fc2_b_i8, "FC2 biases  [10]")

    print(f"  {'TOTAL':20s}: {total:7,} bytes")
    if total != TOTAL_BYTES:
        raise ValueError(f"Expected {TOTAL_BYTES:,} bytes, wrote {total:,} bytes.")

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(scales, handle, indent=2)
        handle.write("\n")

    print(f"\nScale factors saved to: {json_path}")
    print("\nSDRAM address map:")
    address = 0
    for label, size in (
        ("FC1 weights", FC1_W_BYTES),
        ("FC2 weights", FC2_W_BYTES),
        ("FC1 biases", FC1_B_BYTES),
        ("FC2 biases", FC2_B_BYTES),
    ):
        print(f"  0x{address:06x}  {label:12s}  ({size:,} bytes)")
        address += size
    print(f"  0x{address:06x}  (end)")


if __name__ == "__main__":
    main()
