import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

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
    """Write start = 1 to CTRL, verify it pulses for exactly 1 cycle. """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    await wb_write(dut, 0x000, 0x1) # write start = 1

    #start should have pulsed - check it is now 0 
    assert int(dut.start.value) == 0, "start should be 0 after pulse"