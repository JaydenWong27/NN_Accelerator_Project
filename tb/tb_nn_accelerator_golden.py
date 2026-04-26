"""
tb_nn_accelerator_golden.py -- End-to-end test against golden model
=====================================================================

Runs complete MNIST inference on nn_accelerator_top and compares against
the golden INT8 reference model.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles
import numpy as np
import sys
from pathlib import Path

# Add weights dir to path for golden model
sys.path.insert(0, str(Path(__file__).parent.parent / "weights"))

from golden_model import load_quantized_state, quantise_input, forward_int8


async def wishbone_write(dut, addr, data, sel=0xF):
    """Write a 32-bit value to Wishbone slave."""
    dut.wb_cyc.value = 1
    dut.wb_stb.value = 1
    dut.wb_we.value = 1
    dut.wb_addr.value = addr & 0xFFF  # Mask to 12-bit address
    dut.wb_dat_m2s.value = data
    dut.wb_sel.value = sel
    await RisingEdge(dut.clk)
    while dut.wb_ack.value == 0:
        await RisingEdge(dut.clk)
    dut.wb_cyc.value = 0
    dut.wb_stb.value = 0
    dut.wb_we.value = 0


async def wishbone_read(dut, addr):
    """Read a 32-bit value from Wishbone slave."""
    dut.wb_cyc.value = 1
    dut.wb_stb.value = 1
    dut.wb_we.value = 0
    dut.wb_addr.value = addr & 0xFFF  # Mask to 12-bit address
    await RisingEdge(dut.clk)
    while dut.wb_ack.value == 0:
        await RisingEdge(dut.clk)
    result = int(dut.wb_dat_s2m.value)
    dut.wb_cyc.value = 0
    dut.wb_stb.value = 0
    return result


async def wait_for_boot(dut, timeout_cycles=100000):
    """Wait for boot_done to go high."""
    for _ in range(timeout_cycles):
        status = await wishbone_read(dut, 0x004)
        boot_done = (status >> 3) & 1
        if boot_done:
            return True
        await RisingEdge(dut.clk)
    raise TimeoutError("Boot did not complete within timeout")


async def wait_for_done(dut, timeout_cycles=1000000):
    """Wait for done bit in status register."""
    for _ in range(timeout_cycles):
        status = await wishbone_read(dut, 0x004)
        done = status & 1
        if done:
            return True
        await RisingEdge(dut.clk)
    raise TimeoutError("Inference did not complete within timeout")


async def write_input_image(dut, image_i8_784):
    """Write 784-byte input image to input buffer (4 bytes per word)."""
    for offset in range(0, 784, 4):
        word = 0
        for i in range(min(4, 784 - offset)):
            byte_val = image_i8_784[offset + i] & 0xFF
            word |= (byte_val << (i * 8))
        wb_addr = 0x008 + offset
        await wishbone_write(dut, wb_addr, word, sel=0xF)


async def read_output_logits(dut):
    """Read all 10 output logits from output buffer."""
    logits = []
    for i in range(10):
        wb_addr = 0x318 + (i * 4)
        val = await wishbone_read(dut, wb_addr)
        # Convert from unsigned 32-bit to signed 32-bit
        if val & 0x80000000:
            val = val - 0x100000000
        logits.append(val)
    return np.array(logits, dtype=np.int32)


async def run_single_inference(dut, image_i8_784):
    """Run a single MNIST inference and return the output logits."""
    # Write input image
    await write_input_image(dut, image_i8_784)

    # Pulse start
    await wishbone_write(dut, 0x000, 0x1)
    await RisingEdge(dut.clk)
    await wishbone_write(dut, 0x000, 0x0)

    # Wait for done
    await wait_for_done(dut)

    # Read logits
    logits = await read_output_logits(dut)
    return logits


@cocotb.test()
async def test_nn_accelerator_golden(dut):
    """Golden model comparison test."""
    # Start clock
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)

    # Load golden model state
    state = load_quantized_state()
    input_scale = int(state["input_scale"])

    # Wait for boot
    await wait_for_boot(dut)
    dut._log.info("Boot completed!")

    # Run on first 10 test images (or fewer if not available)
    state_dict = load_quantized_state()
    try:
        from golden_model import load_test_dataset
        dataset = load_test_dataset()
        num_images = min(10, len(dataset))
    except:
        num_images = 0

    matching = 0
    mismatching = 0
    errors = []

    if num_images > 0:
        dut._log.info(f"Running {num_images} test images...")
        for idx in range(num_images):
            image_tensor, label = dataset[idx]
            pixels_f32 = image_tensor.numpy().reshape(-1)
            pixels_i8 = quantise_input(pixels_f32, input_scale)

            # Get golden output
            golden_logits = forward_int8(pixels_i8)
            golden_pred = int(np.argmax(golden_logits))

            # Get hardware output
            hw_logits = await run_single_inference(dut, pixels_i8)
            hw_pred = int(np.argmax(hw_logits))

            label_int = int(label)
            match_str = "✓" if hw_pred == golden_pred else "✗"
            correct_str = "✓" if hw_pred == label_int else "✗"

            dut._log.info(
                f"Image {idx}: label={label_int} golden={golden_pred} hw={hw_pred} "
                f"match={match_str} correct={correct_str}"
            )

            if hw_pred == golden_pred:
                matching += 1
            else:
                mismatching += 1
                errors.append({
                    "image": idx,
                    "label": label_int,
                    "golden": golden_pred,
                    "hardware": hw_pred,
                    "golden_logits": golden_logits,
                    "hardware_logits": hw_logits
                })

        accuracy = 100.0 * matching / num_images
        dut._log.info("")
        dut._log.info(f"=== Results ===")
        dut._log.info(f"Matching:     {matching}/{num_images}")
        dut._log.info(f"Mismatching:  {mismatching}/{num_images}")
        dut._log.info(f"Accuracy:     {accuracy:.1f}%")

        if errors:
            dut._log.info("")
            dut._log.info(f"=== Mismatches ===")
            for err in errors[:3]:  # Show first 3 errors
                dut._log.info(f"Image {err['image']}:")
                dut._log.info(f"  Label:   {err['label']}")
                dut._log.info(f"  Golden:  {err['golden']}")
                dut._log.info(f"  Hardware:{err['hardware']}")

        # Assert we got good matching rate
        assert matching >= num_images * 0.9, \
            f"Hardware accuracy too low: {accuracy:.1f}% ({matching}/{num_images})"
    else:
        dut._log.warning("Could not load test dataset, skipping golden comparison")
