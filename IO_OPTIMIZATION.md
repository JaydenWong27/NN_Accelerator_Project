# I/O Pin Reduction for P&R

## Changes Made

### 1. SDRAM Data Width Reduction (8 pins saved)
- Changed `sdram_dq[15:0]` → `sdram_dq[7:0]`
- **Justification**: Design only uses 8 bits for both reads and writes
- **Files modified**:
  - `rtl/nn_accelerator_top.sv` 
  - `rtl/sdram_controller.sv` (dq_out assignment)
  - `tb/tb_nn_top_wrapper.sv` (pulldown array)

### 2. Wishbone Address Width Reduction (20 pins saved)
- Changed `wb_addr[31:0]` → `wb_addr[11:0]`
- **Justification**: Design only uses 12-bit address space (4KB) - see `reg_interface.sv` line 33
- **Files modified**:
  - `rtl/nn_accelerator_top.sv`
  - `rtl/reg_interface.sv`
  - `tb/tb_nn_top_wrapper.sv`
  - `tb/tb_nn_accelerator_golden.py` (address masking)

## Pin Count Impact

| Metric | Before | After | Savings |
|--------|--------|-------|---------|
| SDRAM dq width | 16 | 8 | 8 pins |
| Wishbone addr width | 32 | 12 | 20 pins |
| **Total external pins** | ~89 | ~61 | **28 pins** |
| Device limit | 53 | 53 | - |
| Remaining headroom | -36 | -8 | **28 pins** |

## Further Optimization Options (If Needed)

If synthesis still exceeds 53 pins, additional reductions possible:

### Option A: Reduce SDRAM Data Width to 4 bits (saves 4 more pins)
- Time-multiplex 2 bytes per request
- Requires 2x more SDRAM transactions
- ~10% performance impact
- Moderate RTL complexity increase

### Option B: Reduce Cycle Counter Exposure (saves up to 16 pins)
- Current design exposes full 48-bit cycle_count
- Could limit to 32-bit counter or gate to debug mode only
- Minimal functional impact

### Option C: Use Gowin GW2A-18C or different package
- Same FPGA but different pin count available
- Requires board redesign

## Verification

- All register address offsets remain the same (use [11:0] slice of addresses)
- SDRAM byte addressing unchanged (still 24-bit internally)
- Testbench automatically masks addresses to 12-bit range
- Golden model comparison unaffected

## Next Steps

1. Run synthesis with modified RTL
2. Check final pin count from synthesis report
3. If still >53, implement Option A (4-bit SDRAM mux)
4. Run place-and-route
5. Program Tang Nano 20K
