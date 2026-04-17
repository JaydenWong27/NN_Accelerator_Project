import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
import random

async def reset_dut(dut):
    dut.rst_n.value = 0
    dut.en.value = 0
    for row in range(8):
        dut.activation_in[row].value = 0
    for _ in range(8):         # was 2 — needs 8 to flush 7-deep shift register
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1




@cocotb.test()
async def test_directed(dut):
    """basic 8x8 matrix multiply with known inputs."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset_dut(dut)

    for i in range(8):
        for j in range(8):
            dut.weight[i*8+j].value = 1

    activations = [
        [1, 2, 3, 4, 5, 6, 7, 8],# row 0 gets these over 8 cycles
        [1, 2, 3, 4, 5, 6, 7, 8],# row 1 (delayed 1 cycle)
        [1, 2, 3, 4, 5, 6, 7, 8],# etc.
        [1, 2, 3, 4, 5, 6, 7, 8],
        [1, 2, 3, 4, 5, 6, 7, 8],
        [1, 2, 3, 4, 5, 6, 7, 8],
        [1, 2, 3, 4, 5, 6, 7, 8],
        [1, 2, 3, 4, 5, 6, 7, 8],
    ]

    # python golden model: each PE[i][j] = sum(activations[i]) * weight[i][j]
    # with all weights = 1: every PE accumulates sum(1..8) = 36
    expected = [[36]*8 for _ in range(8)]

    dut.en.value = 1

    # feed 8 activations + 7 extra cycles to let skewed rows drain

    for cycle in range(22):   # was 15
        for row in range(8):
            if cycle < 8:
                dut.activation_in[row].value = activations[row][cycle]
            else:
                dut.activation_in[row].value = 0
        await RisingEdge(dut.clk)

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    for i in range (8):
        for j in range(8):
            result = dut.acc_out[i*8+j].value.signed_integer
            assert result == expected[i][j], \
            f"PE[{i}][{j}]: expected {expected[i][j]} got {result}"
