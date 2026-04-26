import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def reset_dut(dut):
    dut.rst_n.value = 0
    dut.sdram_init_done.value = 0
    dut.wr_ready.value = 0
    dut.rom_data.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


@cocotb.test()
async def test_reset_state(dut):
    """After reset: boot_done=0, wr_valid=0, byte_counter=0."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    assert int(dut.boot_done.value) == 0, "boot_done should be 0 after reset"
    assert int(dut.wr_valid.value) == 0, "wr_valid should be 0 after reset"
    assert int(dut.rom_addr.value) == 0, "byte_counter (rom_addr) should be 0 after reset"


@cocotb.test()
async def test_stays_in_boot_wait(dut):
    """Stays in BOOT_WAIT while sdram_init_done is 0."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    for _ in range(10):
        await RisingEdge(dut.clk)
        assert int(dut.wr_valid.value) == 0, "wr_valid should stay 0 in BOOT_WAIT"
        assert int(dut.boot_done.value) == 0, "boot_done should stay 0 in BOOT_WAIT"


@cocotb.test()
async def test_transitions_to_boot_copy(dut):
    """When sdram_init_done goes high, FSM enters BOOT_COPY (wr_valid asserted)."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.sdram_init_done.value = 1
    dut.wr_ready.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, units="ns")

    assert int(dut.wr_valid.value) == 1, "wr_valid should be 1 in BOOT_COPY when wr_ready=0"
    assert int(dut.boot_done.value) == 0, "boot_done should still be 0"


@cocotb.test()
async def test_wr_valid_drops_when_ready(dut):
    """wr_valid becomes 0 when wr_ready is high (handshake complete)."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.sdram_init_done.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, units="ns")
    assert int(dut.wr_valid.value) == 1

    dut.wr_ready.value = 1
    await Timer(1, units="ns")
    assert int(dut.wr_valid.value) == 0, "wr_valid should drop when wr_ready is high"


@cocotb.test()
async def test_byte_counter_increments(dut):
    """byte_counter increments by one each cycle wr_ready is high."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.sdram_init_done.value = 1
    await RisingEdge(dut.clk)  # enter BOOT_COPY

    assert int(dut.rom_addr.value) == 0

    dut.wr_ready.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, units="ns")
    assert int(dut.rom_addr.value) == 1, f"counter should be 1, got {int(dut.rom_addr.value)}"

    await RisingEdge(dut.clk)
    await Timer(1, units="ns")
    assert int(dut.rom_addr.value) == 2, f"counter should be 2, got {int(dut.rom_addr.value)}"


@cocotb.test()
async def test_address_ports_track_counter(dut):
    """rom_addr and wr_byte_addr both track byte_counter."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.sdram_init_done.value = 1
    await RisingEdge(dut.clk)
    dut.wr_ready.value = 1

    for _ in range(5):
        await RisingEdge(dut.clk)
    await Timer(1, units="ns")

    assert int(dut.rom_addr.value) == 5
    assert int(dut.wr_byte_addr.value) == 5
    assert int(dut.rom_addr.value) == int(dut.wr_byte_addr.value), \
        "rom_addr and wr_byte_addr should match"


@cocotb.test()
async def test_wr_data_passthrough(dut):
    """wr_data passes rom_data through combinationally."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.rom_data.value = 0xAB
    await Timer(1, units="ns")
    assert int(dut.wr_data.value) == 0xAB, f"wr_data should be 0xAB, got {hex(int(dut.wr_data.value))}"

    dut.rom_data.value = 0x55
    await Timer(1, units="ns")
    assert int(dut.wr_data.value) == 0x55, f"wr_data should be 0x55, got {hex(int(dut.wr_data.value))}"


@cocotb.test()
async def test_full_boot_sequence(dut):
    """Run the full 101,770-byte copy and verify boot_done fires."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.sdram_init_done.value = 1
    dut.wr_ready.value = 1

    for _ in range(101_775):
        await RisingEdge(dut.clk)

    assert int(dut.boot_done.value) == 1, "boot_done should be 1 after full sequence"
    assert int(dut.wr_valid.value) == 0, "wr_valid should be 0 in BOOT_DONE"


@cocotb.test()
async def test_stays_in_boot_done(dut):
    """boot_done stays high once reached."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.sdram_init_done.value = 1
    dut.wr_ready.value = 1
    for _ in range(101_775):
        await RisingEdge(dut.clk)

    assert int(dut.boot_done.value) == 1

    for _ in range(10):
        await RisingEdge(dut.clk)
        assert int(dut.boot_done.value) == 1, "boot_done should stay 1 in BOOT_DONE"


@cocotb.test()
async def test_reset_mid_copy(dut):
    """Reset during BOOT_COPY returns FSM to BOOT_WAIT with counter cleared."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.sdram_init_done.value = 1
    dut.wr_ready.value = 1
    for _ in range(20):
        await RisingEdge(dut.clk)

    assert int(dut.rom_addr.value) > 0, "counter should have advanced"

    dut.rst_n.value = 0
    dut.sdram_init_done.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await Timer(1, units="ns")

    assert int(dut.rom_addr.value) == 0, "counter should reset to 0"
    assert int(dut.wr_valid.value) == 0, "wr_valid should be 0 after reset"
    assert int(dut.boot_done.value) == 0, "boot_done should be 0 after reset"
