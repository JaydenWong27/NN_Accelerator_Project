import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def reset_dut(dut):
    dut.rst_n.value = 0
    dut.tiling_start.value = 0
    dut.tiling_layer_sel.value = 0
    dut.fill_done.value = 0
    for i in range(64):
        dut.pe_acc_out[i].value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def pulse(dut, signal):
    signal.value = 1
    await RisingEdge(dut.clk)
    signal.value = 0


async def step_one_tile(dut):
    """Walk through one full tile: PREFETCH/FETCH wait, COMPUTE 15 cycles, ACCUMULATE, SWAP."""
    await pulse(dut, dut.fill_done)
    # COMPUTE: 15 cycles (cycle_cnt 0..14)
    for _ in range(15):
        await RisingEdge(dut.clk)
    # ACCUMULATE 1 cycle
    await RisingEdge(dut.clk)
    # SWAP_BUFFERS 1 cycle
    await RisingEdge(dut.clk)


@cocotb.test()
async def test_reset_state(dut):
    """After reset: tiling_done=0, pe_en=0, all acc_out cleared, state=IDLE."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    assert int(dut.tiling_done.value) == 0
    assert int(dut.pe_en.value) == 0
    assert int(dut.pe_rst_acc.value) == 1, "pe_rst_acc should be 1 in IDLE"
    assert int(dut.sdram_req_valid.value) == 0
    for i in range(128):
        assert int(dut.acc_out[i].value) == 0, f"acc_out[{i}] should be 0 after reset"


@cocotb.test()
async def test_idle_without_start(dut):
    """FSM stays in IDLE when tiling_start is never pulsed."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    for _ in range(10):
        await RisingEdge(dut.clk)
        assert int(dut.tiling_done.value) == 0
        assert int(dut.pe_en.value) == 0
        assert int(dut.sdram_req_valid.value) == 0


@cocotb.test()
async def test_start_moves_to_prefetch(dut):
    """tiling_start moves FSM to PREFETCH_TILE_0, sdram_req_valid asserts."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.tiling_start.value = 1
    await RisingEdge(dut.clk)
    dut.tiling_start.value = 0
    await Timer(1, units="ns")

    assert int(dut.sdram_req_valid.value) == 1, "sdram_req_valid should be 1 in PREFETCH_TILE_0"
    assert int(dut.pe_en.value) == 0


@cocotb.test()
async def test_prefetch_waits_for_fill_done(dut):
    """PREFETCH_TILE_0 stays put until fill_done pulses."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    await pulse(dut, dut.tiling_start)
    for _ in range(5):
        await RisingEdge(dut.clk)
        assert int(dut.pe_en.value) == 0, "still waiting for fill_done"


@cocotb.test()
async def test_compute_pe_en(dut):
    """fill_done -> COMPUTE state, pe_en=1 for 15 cycles."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    await pulse(dut, dut.tiling_start)
    await pulse(dut, dut.fill_done)
    await Timer(1, units="ns")

    for cyc in range(15):
        assert int(dut.pe_en.value) == 1, f"pe_en should be 1 in COMPUTE cycle {cyc}"
        await RisingEdge(dut.clk)


@cocotb.test()
async def test_swap_buffers_signal(dut):
    """swap_buffers asserts in SWAP_BUFFERS state."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    await pulse(dut, dut.tiling_start)
    await pulse(dut, dut.fill_done)
    # 15 COMPUTE cycles
    for _ in range(15):
        await RisingEdge(dut.clk)
    # ACCUMULATE
    await RisingEdge(dut.clk)
    await Timer(1, units="ns")

    assert int(dut.swap_buffers.value) == 1, "swap_buffers should pulse in SWAP_BUFFERS state"
    assert int(dut.sdram_req_valid.value) == 1, "sdram_req_valid should pulse in SWAP_BUFFERS"


@cocotb.test()
async def test_accumulate_adds_pe_outputs(dut):
    """ACCUMULATE state adds pe_acc_out[i*8] to acc_out[neuron_row+i]."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    # Set pe_acc_out[i*8] = 100 + i for i in 0..7
    for i in range(8):
        dut.pe_acc_out[i * 8].value = 100 + i

    await pulse(dut, dut.tiling_start)
    await pulse(dut, dut.fill_done)
    for _ in range(15):
        await RisingEdge(dut.clk)
    # ACCUMULATE happens on this edge
    await RisingEdge(dut.clk)
    await Timer(1, units="ns")

    for i in range(8):
        expected = 100 + i
        got = int(dut.acc_out[i].value)
        assert got == expected, f"acc_out[{i}] expected {expected}, got {got}"


@cocotb.test()
async def test_layer2_completes_faster(dut):
    """Layer 2 (tiling_layer_sel=1) has 16 tile cols vs 98 for layer 1."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.tiling_layer_sel.value = 1
    await pulse(dut, dut.tiling_start)

    # Walk through 2 row groups * 16 tile cols * ~17 cycles + relu = ~600 cycles
    # Hold fill_done high so prefetches complete instantly
    dut.fill_done.value = 1
    cycles = 0
    while int(dut.tiling_done.value) == 0 and cycles < 2000:
        await RisingEdge(dut.clk)
        cycles += 1

    assert int(dut.tiling_done.value) == 1, f"Layer 2 should complete, took {cycles} cycles"
    assert cycles < 2000, "Layer 2 took too long"


@cocotb.test()
async def test_done_returns_to_idle(dut):
    """After DONE state, FSM returns to IDLE next cycle."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.tiling_layer_sel.value = 1
    await pulse(dut, dut.tiling_start)
    dut.fill_done.value = 1

    # Wait for tiling_done
    cycles = 0
    while int(dut.tiling_done.value) == 0 and cycles < 2000:
        await RisingEdge(dut.clk)
        cycles += 1

    assert int(dut.tiling_done.value) == 1
    # Next cycle: back to IDLE
    await RisingEdge(dut.clk)
    await Timer(1, units="ns")
    assert int(dut.tiling_done.value) == 0, "tiling_done should clear when back in IDLE"
    assert int(dut.pe_rst_acc.value) == 1, "pe_rst_acc=1 in IDLE"


@cocotb.test()
async def test_relu_clips_negatives_layer1(dut):
    """In layer 1, RELU clips negative acc_out values to 0."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    # Negative pe_acc_out feeds (signed -50)
    for i in range(8):
        dut.pe_acc_out[i * 8].value = -50

    dut.tiling_layer_sel.value = 0  # layer 1
    await pulse(dut, dut.tiling_start)
    dut.fill_done.value = 1

    # Run only the FIRST tile row group, which means walk through all 98 tile cols
    # then RELU should clip negatives. Just keep running until tiling_done.
    cycles = 0
    while int(dut.tiling_done.value) == 0 and cycles < 50000:
        await RisingEdge(dut.clk)
        cycles += 1

    # After full inference, all acc_out should be >= 0 in layer 1
    for i in range(120):
        val = int(dut.acc_out[i].value)
        # Treat as signed
        if val & 0x80000000:
            val -= 0x100000000
        assert val >= 0, f"acc_out[{i}] = {val}, should be >= 0 after layer 1 RELU"


@cocotb.test()
async def test_reset_mid_compute(dut):
    """Reset during COMPUTE returns FSM to IDLE."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    await pulse(dut, dut.tiling_start)
    await pulse(dut, dut.fill_done)
    # Now in COMPUTE
    for _ in range(5):
        await RisingEdge(dut.clk)

    dut.rst_n.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await Timer(1, units="ns")

    assert int(dut.tiling_done.value) == 0
    assert int(dut.pe_en.value) == 0
    assert int(dut.pe_rst_acc.value) == 1
    for i in range(128):
        assert int(dut.acc_out[i].value) == 0


@cocotb.test()
async def test_sdram_req_len_constant(dut):
    """sdram_req_len is always 8."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    assert int(dut.sdram_req_len.value) == 8

    await pulse(dut, dut.tiling_start)
    await Timer(1, units="ns")
    assert int(dut.sdram_req_len.value) == 8
