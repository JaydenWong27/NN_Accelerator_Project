"""
golden_model.py -- Integer-only INT8 reference for the FPGA inference path
============================================================================

The forward path itself is fully integer:
    INT8 input -> INT32 accumulate -> ReLU -> INT8 requantise -> INT32 logits

Float is only used for:
    - loading the original PyTorch model for comparison
    - reading torchvision test images before input quantisation
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

FC1_W_BYTES = FC1_IN * FC1_OUT
FC2_W_BYTES = FC1_OUT * FC2_OUT
FC1_B_BYTES = FC1_OUT
FC2_B_BYTES = FC2_OUT
TOTAL_BYTES = FC1_W_BYTES + FC2_W_BYTES + FC1_B_BYTES + FC2_B_BYTES

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
HEX_PATH = SCRIPT_DIR / "weights_all.hex"
JSON_PATH = SCRIPT_DIR / "scale_factors.json"
PTH_PATH = SCRIPT_DIR / "mnist_trained.pth"
TEST_IMAGES_HEX_PATH = SCRIPT_DIR / "test_images.hex"
TEST_LABELS_PATH = SCRIPT_DIR / "test_labels.txt"

_QUANT_STATE: dict[str, object] | None = None


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


def _load_hex_bytes(path: Path) -> np.ndarray:
    with path.open("r", encoding="utf-8") as handle:
        values = [int(line.strip(), 16) for line in handle if line.strip()]

    raw = np.asarray(values, dtype=np.uint8)
    if raw.size != TOTAL_BYTES:
        raise ValueError(f"{path} contains {raw.size} bytes, expected {TOTAL_BYTES}.")
    return raw.view(np.int8)


def load_quantized_state() -> dict[str, object]:
    global _QUANT_STATE
    if _QUANT_STATE is not None:
        return _QUANT_STATE

    raw_i8 = _load_hex_bytes(HEX_PATH)
    with JSON_PATH.open("r", encoding="utf-8") as handle:
        scales = json.load(handle)

    fc1_w = raw_i8[0:FC1_W_BYTES].reshape(FC1_IN, FC1_OUT)
    fc2_w = raw_i8[FC1_W_BYTES:FC1_W_BYTES + FC2_W_BYTES].reshape(FC1_OUT, FC2_OUT)
    fc1_b_start = FC1_W_BYTES + FC2_W_BYTES
    fc1_b_end = fc1_b_start + FC1_B_BYTES
    fc2_b_end = fc1_b_end + FC2_B_BYTES
    fc1_b = raw_i8[fc1_b_start:fc1_b_end]
    fc2_b = raw_i8[fc1_b_end:fc2_b_end]

    _QUANT_STATE = {
        "fc1_w": fc1_w,
        "fc2_w": fc2_w,
        "fc1_b": fc1_b,
        "fc2_b": fc2_b,
        "input_scale": int(round(float(scales["input_scale"]))),
        "layer1_requant_multiplier": int(scales["layer1_requant_multiplier"]),
        "layer1_requant_shift": int(scales["layer1_requant_shift"]),
        "scales": scales,
    }
    return _QUANT_STATE


def quantise_input(pixels_f32: np.ndarray, input_scale: int) -> np.ndarray:
    quantised = np.clip(np.round(pixels_f32 * input_scale), -128, 127).astype(np.int8)
    return quantised


def requantise_int32_to_int8(values: np.ndarray, multiplier: int, shift: int) -> np.ndarray:
    scaled = values.astype(np.int64) * np.int64(multiplier)
    if shift:
        rounding = np.int64(1 << (shift - 1))
        scaled = np.where(scaled >= 0, scaled + rounding, scaled - rounding)
        scaled = scaled >> shift
    return np.clip(scaled, -128, 127).astype(np.int8)


def forward_int8(image_i8_784: np.ndarray) -> np.ndarray:
    state = load_quantized_state()

    image_i8_784 = np.asarray(image_i8_784, dtype=np.int8).reshape(FC1_IN)
    fc1_w = state["fc1_w"]
    fc2_w = state["fc2_w"]
    fc1_b = state["fc1_b"]
    fc2_b = state["fc2_b"]
    multiplier = int(state["layer1_requant_multiplier"])
    shift = int(state["layer1_requant_shift"])

    hidden_i32 = image_i8_784.astype(np.int32) @ fc1_w.astype(np.int32)
    hidden_i32 += fc1_b.astype(np.int32)
    hidden_i32 = np.maximum(hidden_i32, 0)

    hidden_i8 = requantise_int32_to_int8(hidden_i32, multiplier, shift)

    logits_i32 = hidden_i8.astype(np.int32) @ fc2_w.astype(np.int32)
    logits_i32 += fc2_b.astype(np.int32)
    return logits_i32.astype(np.int32)


def predict_int8(image_i8_784: np.ndarray) -> int:
    return int(np.argmax(forward_int8(image_i8_784)))


def load_float_model() -> MNISTNet:
    model = MNISTNet()
    model.load_state_dict(torch.load(PTH_PATH, map_location="cpu"))
    model.eval()
    return model


def load_test_dataset() -> datasets.MNIST:
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.5,), (0.5,)),
    ])

    try:
        return datasets.MNIST(
            root=str(DATA_DIR),
            train=False,
            download=False,
            transform=transform,
        )
    except RuntimeError as exc:
        raise RuntimeError(
            f"MNIST test set not found under {DATA_DIR}. Run train.py once or place the dataset there."
        ) from exc


def export_test_vectors(dataset: datasets.MNIST, num_images: int = 10) -> None:
    state = load_quantized_state()
    input_scale = int(state["input_scale"])

    with TEST_IMAGES_HEX_PATH.open("w", encoding="utf-8") as image_handle, TEST_LABELS_PATH.open(
        "w", encoding="utf-8"
    ) as label_handle:
        for index in range(num_images):
            image_tensor, label = dataset[index]
            pixels_f32 = image_tensor.numpy().reshape(-1)
            pixels_i8 = quantise_input(pixels_f32, input_scale)

            for byte in pixels_i8.view(np.uint8):
                image_handle.write(f"{int(byte):02x}\n")
            label_handle.write(f"{int(label)}\n")


def main() -> None:
    state = load_quantized_state()
    scales = state["scales"]
    float_model = load_float_model()
    test_dataset = load_test_dataset()

    print(f"Loaded INT8 weights from: {HEX_PATH}")
    print(f"  fc1_w shape: {state['fc1_w'].shape}")
    print(f"  fc2_w shape: {state['fc2_w'].shape}")
    print(f"  fc1_b shape: {state['fc1_b'].shape}")
    print(f"  fc2_b shape: {state['fc2_b'].shape}")
    print()
    print("Loaded scale metadata:")
    print(f"  input_scale               : {scales['input_scale']}")
    print(f"  hidden_activation_scale   : {scales['hidden_activation_scale']}")
    print(f"  layer1_requant_multiplier : {scales['layer1_requant_multiplier']}")
    print(f"  layer1_requant_shift      : {scales['layer1_requant_shift']}")
    print(f"  calibration_source        : {scales['activation_calibration_source']}")
    print()

    num_compare = 100
    matching = 0
    mismatching = 0
    int8_correct = 0
    float_correct = 0
    input_scale = int(state["input_scale"])

    print(f"Running comparison on the first {num_compare} MNIST test images...")
    with torch.no_grad():
        for index in range(num_compare):
            image_tensor, label = test_dataset[index]
            pixels_f32 = image_tensor.numpy().reshape(-1)
            pixels_i8 = quantise_input(pixels_f32, input_scale)

            int8_logits = forward_int8(pixels_i8)
            int8_pred = int(np.argmax(int8_logits))

            float_logits = float_model(image_tensor.unsqueeze(0))
            float_pred = int(torch.argmax(float_logits, dim=1).item())

            if int8_pred == float_pred:
                matching += 1
            else:
                mismatching += 1

            if int8_pred == int(label):
                int8_correct += 1
            if float_pred == int(label):
                float_correct += 1

    print(f"Matching classifications   : {matching}")
    print(f"Mismatching classifications: {mismatching}")
    print(f"INT8 accuracy              : {100.0 * int8_correct / num_compare:.2f}% ({int8_correct}/{num_compare})")
    print(f"Float model accuracy       : {100.0 * float_correct / num_compare:.2f}% ({float_correct}/{num_compare})")
    if matching < 95:
        print("WARNING: INT8 model matched the float model on fewer than 95/100 images.")

    export_test_vectors(test_dataset, num_images=10)
    print()
    print(f"Exported test vectors to: {TEST_IMAGES_HEX_PATH}")
    print(f"Exported test labels to : {TEST_LABELS_PATH}")


if __name__ == "__main__":
    main()
