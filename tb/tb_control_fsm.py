import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

async def reset_dut(dut):
    dut.rst_n.value       = 0
    dut.start.value       = 0
    dut.soft_reset.value  = 0
    dut.tiling_done.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1

async def pulse(dut, signal):
    """Assert a signal for exactly 1 cycle."""
    signal.value = 1
    await RisingEdge(dut.clk)
    signal.value = 0

async def run_full_inference(dut):
    """Helper: drive FSM through a complete inference and return to DONE."""
    await pulse(dut, dut.start)
    await RisingEdge(dut.clk)  # LOAD_INPUT -> LAYER1_COMPUTE

    # wait in LAYER1_COMPUTE until we pulse tiling_done
    await RisingEdge(dut.clk)
    await pulse(dut, dut.tiling_done)
    await RisingEdge(dut.clk)  # LAYER1_RELU -> LAYER2_COMPUTE

    # wait in LAYER2_COMPUTE until we pulse tiling_done
    await RisingEdge(dut.clk)
    await pulse(dut, dut.tiling_done)
    await RisingEdge(dut.clk)  # -> DONE


@cocotb.test()
async def test_reset_state(dut):
    """After reset busy=0, done=0, cycle_count=0."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    assert dut.busy.value       == 0, "busy should be 0 after reset"
    assert dut.done.value       == 0, "done should be 0 after reset"
    assert int(dut.cycle_count.value) == 0, "cycle_count should be 0 after reset"


@cocotb.test()
async def test_idle_to_load_input(dut):
    """start pulse moves FSM out of IDLE, busy goes high."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    assert dut.busy.value == 0
    assert dut.done.value == 0

    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0

    await RisingEdge(dut.clk)
    assert dut.busy.value == 1, "busy should be 1 after leaving IDLE"


@cocotb.test()
async def test_stays_idle_without_start(dut):
    """FSM stays in IDLE when start is never asserted."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    for _ in range(10):
        await RisingEdge(dut.clk)
        assert dut.busy.value == 0, "FSM should stay in IDLE"
        assert dut.done.value == 0


@cocotb.test()
async def test_tiling_start_in_layer1(dut):
    """tiling_start is high during LAYER1_COMPUTE."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    await pulse(dut, dut.start)
    await RisingEdge(dut.clk)  # LOAD_INPUT
    await RisingEdge(dut.clk)  # now settled in LAYER1_COMPUTE

    assert dut.tiling_start.value     == 1, "tiling_start should be high in LAYER1_COMPUTE"
    assert dut.tiling_layer_sel.value == 0, "tiling_layer_sel should be 0 for Layer 1"


@cocotb.test()
async def test_waits_in_layer1_compute(dut):
    """FSM stays in LAYER1_COMPUTE until tiling_done fires."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    await pulse(dut, dut.start)
    await RisingEdge(dut.clk)  # LAYER1_COMPUTE

    # wait 5 cycles without tiling_done - should stay busy, relu_en=0
    for _ in range(5):
        await RisingEdge(dut.clk)
        assert dut.busy.value    == 1
        assert dut.relu_en.value == 0


@cocotb.test()
async def test_relu_en_in_layer1_relu(dut):
    """relu_en is high only during LAYER1_RELU."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    await pulse(dut, dut.start)
    await RisingEdge(dut.clk)       # LAYER1_COMPUTE
    await pulse(dut, dut.tiling_done)
    await RisingEdge(dut.clk)       # LAYER1_RELU

    assert dut.relu_en.value == 1,       "relu_en should be 1 in LAYER1_RELU"
    assert dut.tiling_start.value == 0,  "tiling_start should be 0 in LAYER1_RELU"


@cocotb.test()
async def test_tiling_layer_sel_layer2(dut):
    """tiling_layer_sel=1 during LAYER2_COMPUTE."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    await pulse(dut, dut.start)
    await RisingEdge(dut.clk)       # LAYER1_COMPUTE
    await pulse(dut, dut.tiling_done)
    await RisingEdge(dut.clk)       # LAYER1_RELU -> LAYER2_COMPUTE
    await RisingEdge(dut.clk)

    assert dut.tiling_layer_sel.value == 1, "tiling_layer_sel should be 1 in LAYER2_COMPUTE"
    assert dut.busy.value             == 1


@cocotb.test()
async def test_done_state(dut):
    """done=1 and busy=0 when FSM reaches DONE."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    await run_full_inference(dut)

    assert dut.done.value == 1, "done should be 1 in DONE state"
    assert dut.busy.value == 0, "busy should be 0 in DONE state"


@cocotb.test()
async def test_soft_reset_returns_to_idle(dut):
    """soft_reset in DONE state returns FSM to IDLE."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    await run_full_inference(dut)
    assert dut.done.value == 1

    await pulse(dut, dut.soft_reset)
    await RisingEdge(dut.clk)

    assert dut.done.value == 0, "done should clear after soft_reset"
    assert dut.busy.value == 0, "busy should be 0 back in IDLE"


@cocotb.test()
async def test_cycle_count_increments(dut):
    """cycle_count increments every cycle during inference."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    assert int(dut.cycle_count.value) == 0

    await pulse(dut, dut.start)
    await RisingEdge(dut.clk)  # let first increment settle
    prev = int(dut.cycle_count.value)
    for _ in range(5):
        await RisingEdge(dut.clk)
        current = int(dut.cycle_count.value)
        assert current > prev, f"cycle_count should increment, got {current}"
        prev = current


@cocotb.test()
async def test_cycle_count_resets_on_new_inference(dut):
    """cycle_count resets to 0 after soft_reset and new inference starts fresh."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    await run_full_inference(dut)
    count_after = int(dut.cycle_count.value)
    assert count_after > 0, "cycle_count should be nonzero after inference"

    await pulse(dut, dut.soft_reset)
    await RisingEdge(dut.clk)  # DONE -> IDLE transition
    await RisingEdge(dut.clk)  # now in IDLE, cycle_count clears
    assert int(dut.cycle_count.value) == 0, "cycle_count should reset to 0 in IDLE"


@cocotb.test()
async def test_reset_mid_inference(dut):
    """rst_n during inference returns FSM to IDLE with cycle_count=0."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    await pulse(dut, dut.start)
    await RisingEdge(dut.clk)  # mid-inference

    dut.rst_n.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    assert dut.busy.value             == 0, "busy should be 0 after reset"
    assert dut.done.value             == 0, "done should be 0 after reset"
    assert int(dut.cycle_count.value) == 0, "cycle_count should be 0 after reset"

    dut.rst_n.value = 1


@cocotb.test()
async def test_full_inference_sequence(dut):
    """Full state walk: IDLE->LOAD_INPUT->L1_COMPUTE->L1_RELU->L2_COMPUTE->DONE."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    # IDLE
    assert dut.busy.value == 0 and dut.done.value == 0

    # -> LOAD_INPUT
    await pulse(dut, dut.start)
    await RisingEdge(dut.clk)
    assert dut.busy.value == 1 and dut.relu_en.value == 0

    # -> LAYER1_COMPUTE
    await RisingEdge(dut.clk)
    assert dut.tiling_start.value == 1 and dut.tiling_layer_sel.value == 0

    # -> LAYER1_RELU
    await pulse(dut, dut.tiling_done)
    await RisingEdge(dut.clk)
    assert dut.relu_en.value == 1 and dut.tiling_start.value == 0

    # -> LAYER2_COMPUTE
    await RisingEdge(dut.clk)
    assert dut.tiling_layer_sel.value == 1 and dut.relu_en.value == 0

    # -> DONE
    await pulse(dut, dut.tiling_done)
    await RisingEdge(dut.clk)
    assert dut.done.value == 1 and dut.busy.value == 0
