import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

CTRL    = 0x000
STATUS  = 0x004
INPUT0  = 0x008
OUT0    = 0x318
WB_BASE = 0x10004000


async def reset_dut(dut):
    dut.rst_n.value = 0
    dut.wb_cyc.value = 0
    dut.wb_stb.value = 0
    dut.wb_we.value = 0
    dut.wb_addr.value = 0
    dut.wb_dat_m2s.value = 0
    dut.wb_sel.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def wb_write(dut, offset, data, sel=0xF):
    dut.wb_addr.value = WB_BASE + offset
    dut.wb_dat_m2s.value = data
    dut.wb_sel.value = sel
    dut.wb_we.value = 1
    dut.wb_cyc.value = 1
    dut.wb_stb.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.wb_cyc.value = 0
    dut.wb_stb.value = 0
    dut.wb_we.value = 0


async def wb_read(dut, offset):
    dut.wb_addr.value = WB_BASE + offset
    dut.wb_we.value = 0
    dut.wb_cyc.value = 1
    dut.wb_stb.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    raw = dut.wb_dat_s2m.value
    dut.wb_cyc.value = 0
    dut.wb_stb.value = 0
    return int(raw) if raw.is_resolvable else 0


@cocotb.test()
async def test_reset(dut):
    """After reset: STATUS reads 0 (nothing busy or done)."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    status = await wb_read(dut, STATUS)
    # bits: {boot_done, error, busy, done}
    done  = status & 0x1
    busy  = (status >> 1) & 0x1
    error = (status >> 2) & 0x1
    assert done  == 0, "done should be 0 after reset"
    assert busy  == 0, "busy should be 0 after reset"
    assert error == 0, "error should be 0 after reset"


@cocotb.test()
async def test_wishbone_read_write(dut):
    """Drive INPUT_BUF and verify Wishbone roundtrip into the buffer."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    await wb_write(dut, INPUT0, 0x44332211, sel=0xF)
    await Timer(1, units="ns")
    assert (int(dut.u_dut.input_buf[0].value) & 0xFF) == 0x11
    assert (int(dut.u_dut.input_buf[1].value) & 0xFF) == 0x22
    assert (int(dut.u_dut.input_buf[2].value) & 0xFF) == 0x33
    assert (int(dut.u_dut.input_buf[3].value) & 0xFF) == 0x44


async def wait_status_bit(dut, bit_idx, timeout_cycles, poll_every=2000):
    """Poll STATUS until bit_idx is set or timeout. Returns (set, cycles_elapsed)."""
    elapsed = 0
    while elapsed < timeout_cycles:
        status = await wb_read(dut, STATUS)
        if (status >> bit_idx) & 0x1:
            return True, elapsed
        for _ in range(poll_every):
            await RisingEdge(dut.clk)
        elapsed += poll_every + 4  # +4 approx for the wb_read transaction
    return False, elapsed


@cocotb.test()
async def test_full_smoke_inference(dut):
    """Full smoke test: boot, load image, START, wait for done, read logits.

    With rom_data=0, every weight written into SDRAM is 0, so all logits read
    back as 0. This verifies the integration plumbing (no deadlocks, FSMs
    transition, Wishbone responds) without checking inference correctness.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    # Phase 1: wait for boot_done (bit 3 of STATUS).
    # SDRAM init ~20k cycles + 101,770-byte boot copy at ~11 cycles/byte ≈ 1.15M cycles.
    dut._log.info("Waiting for boot_done...")
    boot_done, boot_cycles = await wait_status_bit(dut, bit_idx=3,
                                                    timeout_cycles=1_500_000,
                                                    poll_every=5000)
    assert boot_done, f"boot_done never fired within ~{boot_cycles} cycles"
    dut._log.info(f"boot_done fired after ~{boot_cycles} cycles")

    # Phase 2: load 784 input pixels (write 0x01 to every byte for a deterministic image).
    dut._log.info("Loading input image...")
    for word_idx in range(196):  # 784 / 4 = 196 words
        offset = INPUT0 + word_idx * 4
        await wb_write(dut, offset, 0x01010101, sel=0xF)

    # Phase 3: pulse START.
    dut._log.info("Triggering START...")
    await wb_write(dut, CTRL, 0x1)

    # Phase 4: poll STATUS until done=1 (bit 0).
    dut._log.info("Waiting for done...")
    done, inf_cycles = await wait_status_bit(dut, bit_idx=0,
                                              timeout_cycles=200_000,
                                              poll_every=1000)
    assert done, (f"done never fired within ~{inf_cycles} cycles "
                  "(check control_fsm.sv: LAYER2_COMPUTE should set tiling_start=1)")
    dut._log.info(f"done fired after ~{inf_cycles} cycles")

    # Phase 5: read all 10 logits.
    # Note: offsets 0x338/0x33C are CYCLE_COUNT, not output_buf[8]/[9].
    # output_buf[0..9] live at 0x318..0x33C, but reg_interface masks 0x338/0x33C
    # back to cycle_count, so only logits 0..7 are externally readable here.
    dut._log.info("Reading logits...")
    for i in range(8):
        offset = OUT0 + i * 4
        logit = await wb_read(dut, offset)
        # Sign extend from 32 bits
        if logit & 0x80000000:
            logit -= 0x100000000
        dut._log.info(f"logit[{i}] = {logit}")
        assert logit == 0, f"logit[{i}] expected 0 (zero weights), got {logit}"

    dut._log.info("SMOKE TEST PASSED")
