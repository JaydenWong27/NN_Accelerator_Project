"""Full-system MNIST inference test.

Boots the real weights_all.hex through weight_boot_rom -> SDRAM, feeds
pre-quantised MNIST test images over Wishbone, and compares the hardware
logits bit-exactly against a pure-Python reimplementation of
weights/golden_model.py (same integer arithmetic, no numpy/torch needed).
"""

from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

WEIGHTS_DIR = Path(__file__).resolve().parent.parent / "weights"

FC1_IN, FC1_OUT, FC2_OUT = 784, 128, 10
L2_W_BASE = FC1_IN * FC1_OUT                # 100352
L1_B_BASE = L2_W_BASE + FC1_OUT * FC2_OUT   # 101632
L2_B_BASE = L1_B_BASE + FC1_OUT             # 101760
REQUANT_MULT, REQUANT_SHIFT = 2810, 24

NUM_IMAGES = 4  # each inference is ~530k cycles of sim time


def to_signed8(byte):
    return byte - 256 if byte >= 128 else byte


def load_hex_bytes(path):
    return [int(line, 16) for line in path.read_text().split()]


def golden_hidden(pixels, w):
    hidden = []
    for n in range(FC1_OUT):
        acc = sum(pixels[i] * w[i * FC1_OUT + n] for i in range(FC1_IN))
        acc += w[L1_B_BASE + n]
        acc = max(acc, 0)
        q = (acc * REQUANT_MULT + (1 << (REQUANT_SHIFT - 1))) >> REQUANT_SHIFT
        hidden.append(min(q, 127))
    return hidden


def golden_layer2(hidden, w):
    logits = []
    for n in range(FC2_OUT):
        acc = sum(hidden[i] * w[L2_W_BASE + i * FC2_OUT + n] for i in range(FC1_OUT))
        acc += w[L2_B_BASE + n]
        logits.append(acc)
    return logits


def golden_forward(pixels, w):
    """Integer-exact mirror of golden_model.forward_int8 (ReLU before
    requantise means the symmetric rounding is always the +2^23 branch)."""
    return golden_layer2(golden_hidden(pixels, w), w)


async def wb_write(dut, offset, data):
    dut.wb_addr.value = 0x10004000 + offset
    dut.wb_dat_m2s.value = data & 0xFFFFFFFF
    dut.wb_sel.value = 0xF
    dut.wb_we.value = 1
    dut.wb_cyc.value = 1
    dut.wb_stb.value = 1
    await RisingEdge(dut.clk)  # request seen
    await RisingEdge(dut.clk)  # ack fires
    dut.wb_cyc.value = 0
    dut.wb_stb.value = 0
    dut.wb_we.value = 0


async def wb_read(dut, offset):
    dut.wb_addr.value = 0x10004000 + offset
    dut.wb_we.value = 0
    dut.wb_cyc.value = 1
    dut.wb_stb.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    data = int(dut.wb_dat_s2m.value)
    dut.wb_cyc.value = 0
    dut.wb_stb.value = 0
    await RisingEdge(dut.clk)
    return data


@cocotb.test()
async def test_mnist_inference_matches_golden(dut):
    weights = [to_signed8(b) for b in load_hex_bytes(WEIGHTS_DIR / "weights_all.hex")]
    image_bytes = load_hex_bytes(WEIGHTS_DIR / "test_images.hex")
    labels = [int(l) for l in (WEIGHTS_DIR / "test_labels.txt").read_text().split()]

    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.wb_cyc.value = 0
    dut.wb_stb.value = 0
    dut.wb_we.value = 0
    dut.wb_addr.value = 0
    dut.wb_dat_m2s.value = 0
    dut.wb_sel.value = 0
    await Timer(100, "ns")
    dut.rst_n.value = 1

    # boot: 20k-cycle SDRAM init + 101,770-byte ROM->SDRAM copy (~11.4 ms)
    for _ in range(400):
        await Timer(50, "us")
        status = await wb_read(dut, 0x004)
        if status & 0x8:
            break
    else:
        raise AssertionError(f"boot_done never asserted (STATUS={status:#x})")
    dut._log.info("boot complete")

    correct = 0
    for idx in range(NUM_IMAGES):
        pixels = [to_signed8(b) for b in image_bytes[idx * 784:(idx + 1) * 784]]

        # 4 pixels per 32-bit word, byte k of the word = pixel base+k
        for word_idx in range(196):
            word = 0
            for b in range(4):
                word |= (pixels[word_idx * 4 + b] & 0xFF) << (8 * b)
            await wb_write(dut, 0x008 + 4 * word_idx, word)

        await wb_write(dut, 0x000, 0x1)  # CTRL.start

        for _ in range(400):
            await Timer(25, "us")
            status = await wb_read(dut, 0x004)
            if status & 0x1:
                break
        else:
            raise AssertionError(f"image {idx}: inference never reached DONE")

        logits = []
        for k in range(10):
            raw = await wb_read(dut, 0x318 + 4 * k)
            logits.append(raw - (1 << 32) if raw & 0x80000000 else raw)
        cycles = await wb_read(dut, 0x340)

        exp_hidden = golden_hidden(pixels, weights)
        expected = golden_layer2(exp_hidden, weights)
        hw_pred = max(range(10), key=lambda i: logits[i])
        exp_pred = max(range(10), key=lambda i: expected[i])
        dut._log.info(
            f"image {idx}: label={labels[idx]} hw_pred={hw_pred} "
            f"cycles={cycles} logits={logits}"
        )

        # localise mismatches: compare the hidden layer inside the DUT
        hw_hidden = [
            int(dut.u_top.u_tiling_fsm.hidden[i].value.to_signed())
            for i in range(128)
        ]
        hidden_diffs = [
            (i, hw_hidden[i], exp_hidden[i])
            for i in range(128) if hw_hidden[i] != exp_hidden[i]
        ]
        if hidden_diffs:
            dut._log.warning(f"image {idx}: hidden mismatches (i, hw, gold): {hidden_diffs}")

        assert logits == expected, (
            f"image {idx}: hardware logits {logits} != golden {expected}"
        )
        assert hw_pred == exp_pred
        if hw_pred == labels[idx]:
            correct += 1

        await wb_write(dut, 0x000, 0x2)  # CTRL.soft_reset -> IDLE
        await Timer(1, "us")

    dut._log.info(f"{correct}/{NUM_IMAGES} images classified correctly vs labels")
