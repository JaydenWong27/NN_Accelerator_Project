import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
import random

async def reset_dut(dut):
    """Reset the PE to a known state."""
    dut.rst_n.value = 0
    dut.en.value = 0
    dut.activation_in.value = 0
    dut.weight.value = 0
    dut.acc_in.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1

@cocotb.test()
async def test_directed(dut):
    """Test basic MAC operation: (3 * 4) + 0 = 12."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.weight.value = 4
    dut.acc_in.value = 0
    dut.activation_in.value = 3
    dut.en.value = 1

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    result = int(dut.acc_out.value)
    assert result == 12, f"Expected acc_out to be 12, got {result}"
    
    # Feed back the previous result for accumulation
    dut.acc_in.value = result
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    result = int(dut.acc_out.value)
    assert result == 24, f"Expected acc_out to be 24, got {result}"
    
    act_out = int(dut.activation_out.value)
    assert act_out == 3, f"Expected activation_out to be 3, got {act_out}"

@cocotb.test()
async def test_signed_multiply(dut):
    """Test signed multiplication: (-1 * -1) = 1."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.weight.value = -1
    dut.activation_in.value = -1
    dut.acc_in.value = 0
    dut.en.value = 1

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    result = int(dut.acc_out.value)
    if result & 0x80000000:
        result = result - 0x100000000
    assert result == 1, f"Signed multiply broken: (-1 * -1) = 1, got {result}"

@cocotb.test()
async def test_random_operations(dut):
    """Test 100 random MAC operations."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.en.value = 1
    acc_expected = 0

    for i in range(100):
        act = random.randint(-128, 127)
        wgt = random.randint(-128, 127)

        dut.activation_in.value = act
        dut.weight.value = wgt
        dut.acc_in.value = acc_expected
        acc_expected = acc_expected + (act * wgt)

        await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)
        result = int(dut.acc_out.value)
        if result & 0x80000000:
            result = result - 0x100000000
        
        assert result == acc_expected, \
            f"Iteration {i}: act={act} wgt={wgt} expected={acc_expected} got={result}"

@cocotb.test()
async def test_signed_edge_cases(dut):
    """Test edge cases with extreme signed values."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
    dut.en.value = 1

    cases = [
        (-1, -1, 1),
        (-1, 1, -1),
        (1, -1, -1),
        (-128, 1, -128),
        (127, 1, 127),
        (-128, -1, 128),
        (127, 127, 16129),
        (-128, -128, 16384),
    ]

    for act, wgt, expected in cases:
        await reset_dut(dut)
        dut.en.value = 1
        dut.activation_in.value = act
        dut.weight.value = wgt
        dut.acc_in.value = 0

        await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)
        result = int(dut.acc_out.value)
        if result & 0x80000000:
            result = result - 0x100000000
        
        assert result == expected, \
            f"act={act} wgt={wgt}: expected {expected}, got {result}"

@cocotb.test()
async def test_reset_mid_computation(dut):
    """Verify reset clears accumulator during operation."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
    dut.en.value = 1

    dut.activation_in.value = 10
    dut.weight.value = 10
    dut.acc_in.value = 0
    for _ in range(5):
        await RisingEdge(dut.clk)

    dut.rst_n.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    result = int(dut.acc_out.value)
    assert result == 0, f"Reset failed mid-computation, acc={result}"
    
    dut.rst_n.value = 1
    dut.activation_in.value = 3
    dut.weight.value = 4
    dut.acc_in.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    
    result = int(dut.acc_out.value)
    assert result == 12, f"Did not resume correctly after reset, got {result}"

@cocotb.test()
async def test_enable_gate(dut):
    """Verify enable signal gates MAC operations."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.en.value = 1
    dut.activation_in.value = 5
    dut.weight.value = 5
    dut.acc_in.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    
    result = int(dut.acc_out.value)
    assert result == 25, f"Expected 25, got {result}"

    dut.en.value = 0
    dut.activation_in.value = 99
    dut.weight.value = 99
    dut.acc_in.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    
    result = int(dut.acc_out.value)
    assert result == 25, f"Enable gate failed, accumulator changed when disabled"

@cocotb.test()
async def test_accumulator_passthrough(dut):
    """Test that acc_in is correctly passed through for chained MACs."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.en.value = 1
    dut.activation_in.value = 4
    dut.weight.value = 5
    dut.acc_in.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    
    result = int(dut.acc_out.value)
    assert result == 20, f"First operation failed: expected 20, got {result}"

    dut.activation_in.value = 2
    dut.weight.value = 3
    dut.acc_in.value = 20
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    
    result = int(dut.acc_out.value)
    assert result == 26, f"Accumulator passthrough failed: expected 26, got {result}"


@cocotb.test()
async def test_zero_multiplication(dut):
    """Test comprehensive zero multiplication: 0xn, nx0, 0x0 all preserve acc."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    test_cases = [
        # (activation, weight, acc_in, description)
        (0, 4, 100, "0 x 4, acc_in=100"),
        (0, -50, 200, "0 x -50, acc_in=200"),
        (0, 127, -500, "0 x 127, acc_in=-500"),
        (5, 0, 75, "5 x 0, acc_in=75"),
        (-30, 0, 1000, "-30 x 0, acc_in=1000"),
        (127, 0, -1000, "127 x 0, acc_in=-1000"),
        (0, 0, 42, "0 x 0, acc_in=42"),
        (0, 0, -42, "0 x 0, acc_in=-42"),
        (0, 0, 0, "0 x 0, acc_in=0"),
    ]

    for activation, weight, acc_in, desc in test_cases:
        await reset_dut(dut)
        dut.en.value = 1
        dut.activation_in.value = activation
        dut.weight.value = weight
        dut.acc_in.value = acc_in

        await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)
        result = int(dut.acc_out.value)
        
        # Handle signed 32-bit conversion
        if result & 0x80000000:
            result = result - 0x100000000
        
        # When either operand is 0, product is 0, so acc_out = acc_in + 0 = acc_in
        expected = acc_in
        assert result == expected, \
            f"{desc}: expected {expected}, got {result}"

@cocotb.test()
async def accumulator_boundary_conditions(dut):
    """Test adding positive to max positive or negative to min negative"""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    test_cases = [
        # (activation, weight, acc_in, description)
        (0, 1, 2147483647, "max acc_in, zero product -> holds"),
        (0,1,-2147483648, "min acc_in, zero pdocut -> holds"),
        (1,1,2147483647, "max acc_in + 1 -> wraps to INT32_MIN"),
        (1,-1, -2147483648, "min acc_in -1 -> wraps to INT32_MAX"),
        (-128, -128, 2147467263, "max possible product lands exactly at INT32_MAX"),
        (-128,-128, 2147467264, "max possible product overshoots by 1 -> wraps"),
    (-128, 127, -2147467392, "min possible product lands exactly at INT32_MIN"),
    (-128, 127, -2147467393, "min possible product overshoots by 1 -> wraps"),
    ]

    for activation, weight, acc_in, desc in test_cases:
        dut.en.value = 1
        dut.activation_in.value = activation
        dut.weight.value = weight
        dut.acc_in.value = acc_in
        
        await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)
        result = int(dut.acc_out.value)

        if result & 0x80000000:
            result = result - 0x100000000

        expected = (acc_in + activation * weight + 2**31) % 2**32 - 2**31 
        assert result == expected, f"{desc}: expected {expected}, got {result}"

@cocotb.test()
async def test_reset_edge_cases(dut):
    """Test reset behavior in edge case scenarios"""
