import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

async def reset_dut(dut):
    dut.rst_n.value = 0
    dut.wb_cyc.value = 0
    dut.wb_stb.value = 0
    dut.wb_we.value = 0
    dut.wb_addr.value = 0
    dut.wb_dat_m2s.value = 0
    dut.wb_sel.value = 0
    dut.done.value = 0
    dut.busy.value = 0
    dut.error.value = 0
    dut.boot_done.value = 0
    dut.cycle_count.value = 0
    for i in range(10): 
        dut.output_buf[i].value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1

async def wb_write(dut, offset, data, sel=0xF):
    """Helper: perform one wishbone write transaction."""
    dut.wb_addr.value = 0x10004000 + offset
    dut.wb_dat_m2s.value = data
    dut.wb_sel.value = sel
    dut.wb_we.value = 1
    dut.wb_cyc.value = 1
    dut.wb_stb.value = 1
    await RisingEdge(dut.clk) # cycle 1: request seen
    await RisingEdge(dut.clk) # cycle 2: ack fires
    dut.wb_cyc.value = 0
    dut.wb_stb.value = 0
    dut.wb_we.value = 0

async def wb_read(dut,offset):
    """Helper: perform one wishbone read, return the data. """
    dut.wb_addr.value = 0x10004000 + offset
    dut.wb_we.value = 0
    dut.wb_cyc.value = 1
    dut.wb_stb.value = 1
    await RisingEdge(dut.clk) # cycle 1: request seen 
    await RisingEdge(dut.clk) #cycle 2: ack fires, data valid
    data = int (dut.wb_dat_s2m.value)
    dut.wb_cyc.value = 0
    dut.wb_stb.value = 0
    return data

@cocotb.test()
async def test_ctrl_start_pulse(dut):
    """Write start = 1 to CTRL, verify it pulses to 1 then returns to 0."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.wb_addr.value = 0x10004000 + 0x000
    dut.wb_dat_m2s.value = 0x1
    dut.wb_sel.value = 0xF
    dut.wb_we.value = 1
    dut.wb_cyc.value = 1
    dut.wb_stb.value = 1

    await RisingEdge(dut.clk)  # cycle 1: ack <= 1, start <= 1
    await Timer(1, units="ns")  # let NBA settle past the edge
    assert int(dut.start.value) == 1, f"start should be 1 during pulse, got {int(dut.start.value)}"

    await RisingEdge(dut.clk)  # cycle 2: ack <= 0, start <= 0 (default)
    await Timer(1, units="ns")
    assert int(dut.start.value) == 0, f"start should return to 0, got {int(dut.start.value)}"

    dut.wb_cyc.value = 0
    dut.wb_stb.value = 0
    dut.wb_we.value = 0


@cocotb.test()
async def test_ctrl_soft_reset_pulse(dut):
    """Write 0x2 to CTRL, verify soft_reset is 1 for exactly 1 cycle then returns to 0."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.wb_addr.value = 0x10004000 + 0x000
    dut.wb_dat_m2s.value = 0x2
    dut.wb_sel.value = 0xF
    dut.wb_we.value = 1
    dut.wb_cyc.value = 1
    dut.wb_stb.value = 1

    await RisingEdge(dut.clk)  # cycle 1: soft_reset <= 1
    await Timer(1, units="ns")
    assert int(dut.soft_reset.value) == 1, f"soft_reset should be 1 during pulse, got {int(dut.soft_reset.value)}"

    await RisingEdge(dut.clk)  # cycle 2: soft_reset <= 0
    await Timer(1, units="ns")
    assert int(dut.soft_reset.value) == 0, f"soft_reset should return to 0, got {int(dut.soft_reset.value)}"

    dut.wb_cyc.value = 0
    dut.wb_stb.value = 0
    dut.wb_we.value = 0


@cocotb.test()
async def test_status_read(dut):
    """Drive done=1, busy=0, error=1, boot_done=1 → STATUS should read 0xD."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.done.value = 1
    dut.busy.value = 0
    dut.error.value = 1
    dut.boot_done.value = 1

    data = await wb_read(dut, 0x004)
    assert data == 0xD, f"STATUS expected 0xD (0b1101), got {hex(data)}"


@cocotb.test()
async def test_input_buf_single_pixel_write(dut):
    """Write 0x000000AA to offset 0x008, verify input_buf[0] == 0xAA and pixel 4."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    await wb_write(dut, 0x008, 0x000000AA, sel=0xF)
    assert (int(dut.input_buf[0].value) & 0xFF) == 0xAA, \
        f"input_buf[0] expected 0xAA, got {hex(int(dut.input_buf[0].value) & 0xFF)}"

    await wb_write(dut, 0x00C, 0x000000CC, sel=0xF)
    assert (int(dut.input_buf[4].value) & 0xFF) == 0xCC, \
        f"input_buf[4] expected 0xCC, got {hex(int(dut.input_buf[4].value) & 0xFF)}"


@cocotb.test()
async def test_input_buf_byte_select(dut):
    """Write 0x44332211 to offset 0x008 with wb_sel=0xF, verify pixels 0-3 unpack correctly."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    await wb_write(dut, 0x008, 0x44332211, sel=0xF)
    expected = [0x11, 0x22, 0x33, 0x44]
    for i, exp in enumerate(expected):
        got = int(dut.input_buf[i].value) & 0xFF
        assert got == exp, f"input_buf[{i}] expected {hex(exp)}, got {hex(got)}"


@cocotb.test()
async def test_input_buf_partial_write(dut):
    """Write with wb_sel=0x3 (low 2 bytes), verify only pixels 0-1 update, 2-3 unchanged."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    # Fill all 4 pixels with known values first
    await wb_write(dut, 0x008, 0xDDCCBBAA, sel=0xF)

    # Partial write: only byte lanes 0 and 1
    await wb_write(dut, 0x008, 0xFF11FF22, sel=0x3)

    assert (int(dut.input_buf[0].value) & 0xFF) == 0x22, \
        f"input_buf[0] expected 0x22, got {hex(int(dut.input_buf[0].value) & 0xFF)}"
    assert (int(dut.input_buf[1].value) & 0xFF) == 0xFF, \
        f"input_buf[1] expected 0xFF, got {hex(int(dut.input_buf[1].value) & 0xFF)}"
    assert (int(dut.input_buf[2].value) & 0xFF) == 0xCC, \
        f"input_buf[2] expected 0xCC (unchanged), got {hex(int(dut.input_buf[2].value) & 0xFF)}"
    assert (int(dut.input_buf[3].value) & 0xFF) == 0xDD, \
        f"input_buf[3] expected 0xDD (unchanged), got {hex(int(dut.input_buf[3].value) & 0xFF)}"


@cocotb.test()
async def test_output_buf_read(dut):
    """Set output_buf[0] = 0x12345678, read offset 0x318, verify match."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.output_buf[0].value = 0x12345678
    data = await wb_read(dut, 0x318)
    assert data == 0x12345678, f"output_buf[0] expected 0x12345678, got {hex(data)}"


@cocotb.test()
async def test_all_output_logits(dut):
    """Set logits 0-7 (indices 8-9 are shadowed by CYCLE_COUNT), read each via Wishbone."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    test_values = [
        0x11111111, 0x22222222, 0x33333333, 0x44444444,
        0x55555555, 0x66666666, 0x77777777, 0x01234567,
    ]
    for i, val in enumerate(test_values):
        dut.output_buf[i].value = val

    for i, expected in enumerate(test_values):
        offset = 0x318 + i * 4
        data = await wb_read(dut, offset)
        assert data == expected, \
            f"logit[{i}] @ {hex(offset)}: expected {hex(expected)}, got {hex(data)}"


@cocotb.test()
async def test_cycle_count_read(dut):
    """Set cycle_count = 0xDEADBEEFCAFE, verify lower 32 bits at 0x338 and upper 16 at 0x33C."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.cycle_count.value = 0xDEADBEEFCAFE

    lo = await wb_read(dut, 0x338)
    hi = await wb_read(dut, 0x33C)
    assert lo == 0xBEEFCAFE, f"CYCLES_LO expected 0xBEEFCAFE, got {hex(lo)}"
    assert hi == 0x0000DEAD, f"CYCLES_HI expected 0x0000DEAD, got {hex(hi)}"


@cocotb.test()
async def test_wb_ack_timing(dut):
    """Verify wb_ack is 0 in cycle 1 (before first edge), 1 in cycle 2 (after first edge), 0 in cycle 3."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.wb_addr.value = 0x10004000 + 0x000
    dut.wb_dat_m2s.value = 0x0
    dut.wb_sel.value = 0xF
    dut.wb_we.value = 1
    dut.wb_cyc.value = 1
    dut.wb_stb.value = 1

    await Timer(1, units="ns")
    assert int(dut.wb_ack.value) == 0, "wb_ack should be 0 before first edge"

    await RisingEdge(dut.clk)
    await Timer(1, units="ns")
    assert int(dut.wb_ack.value) == 1, f"wb_ack should be 1 after first edge, got {int(dut.wb_ack.value)}"

    await RisingEdge(dut.clk)
    await Timer(1, units="ns")
    assert int(dut.wb_ack.value) == 0, f"wb_ack should be 0 after second edge, got {int(dut.wb_ack.value)}"

    dut.wb_cyc.value = 0
    dut.wb_stb.value = 0
    dut.wb_we.value = 0