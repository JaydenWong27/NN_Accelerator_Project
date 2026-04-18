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

def systolic_expected(activations_8x8, weights_flat_64):
    """
    activations_8x8: list of 8 lists, each with 8 INT8 values (one per cycle per row)
    weights_flat_64: list of 64 INT8 values, weight for PE[i][j] at index i*8+j
    REturns: list of 64 INT32 expected acc_out values
    """
    result = []
    for i in range(8):
        row_sum = sum(int(a) for a in activations_8x8[i])
        for j in range(8):
            raw = int(weights_flat_64[i*8+j]) * row_sum
            # Two's complement INT32 wrap (matches RTL behavior)
            raw &= 0xFFFFFFFF
            if raw & 0x80000000:
                raw -= 0x100000000
            result.append(raw)
    return result

async def run_array(dut, activations_8x8, weights_flat_64, drive_cycles=8, drain_cycles=14):
    await reset_dut(dut)
    for k in range(64):
        dut.weight[k].value = weights_flat_64[k]
    dut.en.value = 1
    for cycle in range(drive_cycles + drain_cycles):
        for row in range(8):
            if cycle < drive_cycles:
                dut.activation_in[row].value = activations_8x8[row][cycle]
            else:
                dut.activation_in[row].value = 0
        await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

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

@cocotb.test()
async def test_all_zer_activations(dut):
    """Basic 8x8 matrix mulltiply but with zero activations weights"""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    weights = [127] * 64
    activations = [[0] * 8 for _ in range(8)]

    await run_array(dut, activations,weights)

    for i in range(8):
        for j in range(8):
            result = dut.acc_out[i*8+j].value.signed_integer
            assert result == 0, \
                f"PE[{i}][{j}]: expected 0 got {result}"
            

@cocotb.test()
async def test_all_zero_weights(dut):
    """"Weight is all zero, activations are non zero"""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    weights = [0] * 64
    activations = [[1] * 8 for _ in range(8)]

    await run_array(dut, activations,weights)

    for i in range(8):
        for j in range(8):
            result = dut.acc_out[i*8+j].value.signed_integer
            assert result == 0, \
                f"PE[{i}][{j}]: expected 0 got {result}"
            
@cocotb.test()
async def test_single_active_cycle(dut):
    """only cyle 0 has non zero activation per row """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    weights = [1] * 64
    # only the first cycle is non zero across all rows
    activations = [
        [1, 2, 3, 4, 5, 6, 7, 8],  # row 0: active
        [0, 0, 0, 0, 0, 0, 0, 0],  # row 1: silent
        [0, 0, 0, 0, 0, 0, 0, 0],  # row 2: silent
        [0, 0, 0, 0, 0, 0, 0, 0],  # row 3: silent
        [0, 0, 0, 0, 0, 0, 0, 0],  # row 4: silent
        [0, 0, 0, 0, 0, 0, 0, 0],  # row 5: silent
        [0, 0, 0, 0, 0, 0, 0, 0],  # row 6: silent
        [0, 0, 0, 0, 0, 0, 0, 0],  # row 7: silent
    ]

    await run_array(dut, activations, weights)

    expected = systolic_expected(activations, weights)

    for i in range(8):
        for j in range(8):
            result = dut.acc_out[i*8+j].value.signed_integer
            assert result == expected[i*8+j], \
                f"PE[{i}][{j}]: expected {expected[i*8+j]} got {result}"
            

@cocotb.test()
async def test_single_active_row(dut):
    """only row 0 has non zero activations other rows (1-7 get 0 every cycle) """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    weights = [1] * 64
    # only the first cycle is non zero across all rows
    activations = [[5,0,0,0,0,0,0,0] for _ in range(8)]

    await run_array(dut, activations, weights)

    expected = systolic_expected(activations, weights)

    for i in range(8):
        for j in range(8):
            result = dut.acc_out[i*8+j].value.signed_integer
            assert result == expected[i*8+j], \
                f"PE[{i}][{j}]: expected {expected[i*8+j]} got {result}"
            


@cocotb.test()
async def test_alternating_sign_sum_to_zero(dut):
    """per row any nonzero weight row sums = 0, all 64 output must be zero"""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    weights = [1] * 64

    activations = [[1,-1,1,-1,1,-1,1,-1] for _ in range(8)]

    await run_array(dut, activations, weights)

    expected = systolic_expected(activations, weights)

    for i in range(8):
        for j in range(8):
            result = dut.acc_out[i*8+j].value.signed_integer
            assert result == expected[i*8+j], \
                f"PE[{i}][{j}]: expected {expected[i*8+j]} got {result}"
            
@cocotb.test()
async def test_diagonal_weights(dut):
    """only 8 diagonal PEs product non zero output verify weigh taddressing (i*8+j)"""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    weights = [100 if i == j else 0 for i in range(8) for j in range(8)]
    activations = [[1] * 8 for _ in range(8)]

    await run_array(dut, activations, weights)

    expected = systolic_expected(activations, weights)

    for i in range(8):
        for j in range(8):
            result = dut.acc_out[i*8+j].value.signed_integer
            assert result == expected[i*8+j], \
                f"PE[{i}][{j}]: expected {expected[i*8+j]} got {result}"
            
@cocotb.test()
async def test_uniform_weight_per_row(dut):
    """only 8 diagonal PEs product non zero output verify weigh taddressing (i*8+j)"""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    weights = []
    for i in range(8):
        for j in range(8):
            weights.append(i+1)

    activations = [[1] * 8 for _ in range(8)]

    await run_array(dut, activations, weights)

    expected = systolic_expected(activations, weights)

    for i in range(8):
        for j in range(8):
            result = dut.acc_out[i*8+j].value.signed_integer
            assert result == expected[i*8+j], \
                f"PE[{i}][{j}]: expected {expected[i*8+j]} got {result}"
            
@cocotb.test()
async def test_max_positive_weights(dut):
    """all weights =127, activations = 1 every ecycle so expected that every pe = 1016"""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    weights = [127] * 64

    activations = [[1] * 8 for _ in range(8)]

    await run_array(dut, activations, weights)

    expected = systolic_expected(activations, weights)

    for i in range(8):
        for j in range(8):
            result = dut.acc_out[i*8+j].value.signed_integer
            assert result == expected[i*8+j], \
                f"PE[{i}][{j}]: expected {expected[i*8+j]} got {result}"
            
@cocotb.test()
async def test_max_negative_weights(dut):
    """all weights = -128, activations = 1 every cycle"""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    weights = [-128] * 64

    activations = [[1] * 8 for _ in range(8)]

    await run_array(dut, activations, weights)

    expected = systolic_expected(activations, weights)

    for i in range(8):
        for j in range(8):
            result = dut.acc_out[i*8+j].value.signed_integer
            assert result == expected[i*8+j], \
                f"PE[{i}][{j}]: expected {expected[i*8+j]} got {result}"
            
@cocotb.test()
async def test_neg_neg_product(dut):
    """all weights = -1, activations = -1 every cycle"""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    weights = [-1] * 64

    activations = [[-1] * 8 for _ in range(8)]

    await run_array(dut, activations, weights)

    expected = systolic_expected(activations, weights)

    for i in range(8):
        for j in range(8):
            result = dut.acc_out[i*8+j].value.signed_integer
            assert result == expected[i*8+j], \
                f"PE[{i}][{j}]: expected {expected[i*8+j]} got {result}"
            

@cocotb.test()
async def test_pos_neg_product(dut):
    """activations = 1, weights = -1 expected every PE = -8"""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    weights = [-1] * 64

    activations = [[1] * 8 for _ in range(8)]

    await run_array(dut, activations, weights)

    expected = systolic_expected(activations, weights)

    for i in range(8):
        for j in range(8):
            result = dut.acc_out[i*8+j].value.signed_integer
            assert result == expected[i*8+j], \
                f"PE[{i}][{j}]: expected {expected[i*8+j]} got {result}"


@cocotb.test()
async def test_neg_pos_product(dut):
    """activations = -1, weights = 1 expected every PE = -8"""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    weights = [1] * 64

    activations = [[-1] * 8 for _ in range(8)]

    await run_array(dut, activations, weights)

    expected = systolic_expected(activations, weights)

    for i in range(8):
        for j in range(8):
            result = dut.acc_out[i*8+j].value.signed_integer
            assert result == expected[i*8+j], \
                f"PE[{i}][{j}]: expected {expected[i*8+j]} got {result}"
            


@cocotb.test()
async def test_max_positive_product(dut):
    """activations = 127, weights = 127m every pe = 129032"""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    weights = [127] * 64

    activations = [[127] * 8 for _ in range(8)]

    await run_array(dut, activations, weights)

    expected = systolic_expected(activations, weights)

    for i in range(8):
        for j in range(8):
            result = dut.acc_out[i*8+j].value.signed_integer
            assert result == expected[i*8+j], \
                f"PE[{i}][{j}]: expected {expected[i*8+j]} got {result}"

@cocotb.test()
async def test_max_negative_activation_max_negative_weight(dut):
    """activations = -128, weights = -128, every pe = 131072"""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    weights = [-128] * 64

    activations = [[-128] * 8 for _ in range(8)]

    await run_array(dut, activations, weights)

    expected = systolic_expected(activations, weights)

    for i in range(8):
        for j in range(8):
            result = dut.acc_out[i*8+j].value.signed_integer
            assert result == expected[i*8+j], \
                f"PE[{i}][{j}]: expected {expected[i*8+j]} got {result}"
            
@cocotb.test()
async def test_accumulation_no_overflow(dut):
    """activations = 50, weights = 50, expected = 20000"""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    weights = [50] * 64

    activations = [[50] * 8 for _ in range(8)]

    await run_array(dut, activations, weights)

    expected = systolic_expected(activations, weights)

    for i in range(8):
        for j in range(8):
            result = dut.acc_out[i*8+j].value.signed_integer
            assert result == expected[i*8+j], \
                f"PE[{i}][{j}]: expected {expected[i*8+j]} got {result}"
            
@cocotb.test()
async def test_per_row_different_activation_levels(dut):
    """Row i gets activation value i+1 every cycle. Weights all 1.
    PE[i][j] = (i+1)*8. Confirms rows accumulate independently."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    weights = [1] * 64
    activations = [[i + 1] * 8 for i in range(8)]

    await run_array(dut, activations, weights)

    expected = systolic_expected(activations, weights)

    for i in range(8):
        for j in range(8):
            result = dut.acc_out[i*8+j].value.signed_integer
            assert result == expected[i*8+j], \
                f"PE[{i}][{j}]: expected {expected[i*8+j]} got {result}"

@cocotb.test()
async def test_completely_independent_row_streams(dut):
    """Each row gets a unique random INT8 activation sequence, weights random.
    Stresses all 64 PEs simultaneously with distinct values."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    weights = [random.randint(-128, 127) for _ in range(64)]
    activations = [
        [random.randint(-128, 127) for _ in range(8)]
        for _ in range(8)
    ]

    await run_array(dut, activations, weights)

    expected = systolic_expected(activations, weights)

    for i in range(8):
        for j in range(8):
            result = dut.acc_out[i*8+j].value.signed_integer
            assert result == expected[i*8+j], \
                f"PE[{i}][{j}]: expected {expected[i*8+j]} got {result}"


@cocotb.test()
async def test_reset_mid_computation(dut):
    """Run 4 cycles of large activations, assert reset, then run a clean
    8+drain cycle. Only the post-reset values should appear in outputs."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    weights = [1] * 64

    # partial first run, these values must be wiped by reset
    await reset_dut(dut)
    for k in range(64):
        dut.weight[k].value = weights[k]
    dut.en.value = 1
    for _ in range(4):
        for row in range(8):
            dut.activation_in[row].value = 99
        await RisingEdge(dut.clk)

    # assert reset mid-computation
    dut.rst_n.value = 0
    dut.en.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1

    # verify all 64 accumulators are zero immediately after reset
    for k in range(64):
        assert dut.acc_out[k].value.signed_integer == 0, \
            f"PE[{k//8}][{k%8}]: reset failed, acc = {dut.acc_out[k].value.signed_integer}"

    # clean second run - only this should appear in final outputs
    second_activations = [[5] * 8 for _ in range(8)]
    dut.en.value = 1
    for cycle in range(8 + 14):
        for row in range(8):
            dut.activation_in[row].value = second_activations[row][cycle] if cycle < 8 else 0
        await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    expected = systolic_expected(second_activations, weights)

    for i in range(8):
        for j in range(8):
            result = dut.acc_out[i*8+j].value.signed_integer
            assert result == expected[i*8+j], \
                f"PE[{i}][{j}]: expected {expected[i*8+j]} got {result}"


@cocotb.test()
async def test_enable_gate(dut):
    """Do a full run with en=1, save outputs, then feed new activations with
    en=0. Accumulators must not change."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    weights = [1] * 64
    activations = [[3] * 8 for _ in range(8)]

    # full run with en=1
    await run_array(dut, activations, weights)

    # save outputs after the run
    saved = [dut.acc_out[k].value.signed_integer for k in range(64)]

    # gate enable, feed completely different activations
    dut.en.value = 0
    for _ in range(8):
        for row in range(8):
            dut.activation_in[row].value = 99
        await RisingEdge(dut.clk)

    # outputs must be identical to before en=0
    for i in range(8):
        for j in range(8):
            result = dut.acc_out[i*8+j].value.signed_integer
            assert result == saved[i*8+j], \
                f"PE[{i}][{j}]: en=0 should freeze acc, expected {saved[i*8+j]} got {result}"


@cocotb.test()
async def test_random_batch(dut):
    """25 random weight/activation configurations verified against
    systolic_expected(). Covers combinations no directed test reaches."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    for iteration in range(25):
        weights = [random.randint(-128, 127) for _ in range(64)]
        activations = [
            [random.randint(-128, 127) for _ in range(8)]
            for _ in range(8)
        ]

        await run_array(dut, activations, weights)

        expected = systolic_expected(activations, weights)

        for i in range(8):
            for j in range(8):
                result = dut.acc_out[i*8+j].value.signed_integer
                assert result == expected[i*8+j], \
                    f"iter {iteration} PE[{i}][{j}]: expected {expected[i*8+j]} got {result}"
