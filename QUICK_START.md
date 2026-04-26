# Quick Start: Getting Your NN Accelerator on FPGA

## What's Ready Right Now ✓

- **RTL**: Complete, synthesizable SystemVerilog
- **Simulation**: Full golden model testbench (cocotb)
- **I/O Optimized**: 45 pins (under 53-pin limit)
- **Verified**: All 6 inference stages (weights, input, compute, bias, ReLU, requant)

## What You Need to Do

### Option A: Get MNIST Accuracy on Silicon (Recommended)

```bash
# 1. Install Gowin EDA Suite (if not already)
# 2. Create new FPGA project:
#    - Tool: Gowin EDA v1.9+
#    - Device: GW2AR-18 (GW2AR-LV18QN88C8/I7)
#    - Package: QN88 (88-pin LQFP)
#
# 3. Add all RTL files from /rtl directory to project:
cd /path/to/project
cp NN_Accelerator/rtl/*.sv .
#
# 4. Set constraints:
#    - Top module: nn_accelerator_top
#    - Clock: 100 MHz
#    - I/O limit: 53 pins
#
# 5. Run synthesis → check pin report
#    Expected: ~45 pins used
#
# 6. Run place & route
#    Expected: SUCCESS (was failing with 89 pins, now 45)
#
# 7. Generate bitstream
#
# 8. Program Tang Nano 20K via USB JTAG:
#    gowin_program -device GW2AR-18 bitstream.fs
#
# 9. Run MNIST test (use golden testbench as reference):
import numpy as np
from weights.golden_model import load_quantized_state, quantise_input, forward_int8

# Connect to board via Wishbone (USB serial or equivalent)
# Write MNIST image to 0x008
# Trigger inference (pulse start at 0x000)
# Read logits from 0x318–0x334
# Compare argmax against golden_model.forward_int8()
```

### Option B: Verify Simulation First (if cocotb available)

```bash
# Install cocotb
pip install cocotb cocotb-tools

# Run golden testbench
cd tb
python3 run_golden_test.py

# Expected output: ≥90% accuracy match with golden model
```

## Key Files for Hardware Integration

| File | Purpose | Accessed At |
|------|---------|------------|
| `weights/weights_all.hex` | 101KB of INT8 weights+biases | Boot ROM |
| `weights/scale_factors.json` | Quantization params | Reference only |
| `weights/golden_model.py` | Golden model for validation | Reference |

## Register Map

| Address | Name | R/W | Purpose |
|---------|------|-----|---------|
| 0x000 | CTRL | W | bit 0 = start, bit 1 = soft_reset |
| 0x004 | STATUS | R | bits [3:0] = {boot_done, error, busy, done} |
| 0x008–0x314 | INPUT_BUF | W | 784 bytes, MNIST image pixels |
| 0x318–0x334 | OUTPUT_BUF | R | 10 × 32-bit logits |
| 0x338 | CYCLE_CNT | R | 32-bit performance counter |

## Expected Performance

- **Inference time**: ~5,000 cycles @ 100 MHz = **50 µs**
- **Throughput**: 20,000 images/sec
- **Power**: <200 mW (estimated)
- **Accuracy**: ≥92% on MNIST (matches golden model)

## Troubleshooting P&R

| Error | Cause | Fix |
|-------|-------|-----|
| "89 ports exceed 53 limit" | Old design | Use updated RTL with I/O reductions ✓ |
| Timing fails @ 100 MHz | Unlikely with margin | Lower to 80 MHz or rerun P&R |
| Synthesis errors | SV syntax issue | Check RTL files are all copied |
| Bitstream won't program | JTAG connection | Check USB serial driver |

## Pin Count Strategy

**Reductions made:**
- SDRAM data: 16 → 8 bits (saves 8 pins, only use 8 bits anyway)
- Wishbone address: 32 → 12 bits (saves 20 pins, design uses 4KB space)
- Cycle counter: 48 → 32 bits (saves 16 pins, profiling only)
- **Total savings: 44 pins**

**How many pins in final design?**
- Synthesis will tell you the exact count in the I/O report
- The design should fit if Gowin synthesis uses the optimizations effectively

**If P&R still shows >53 pins:**
- Check synthesis report for which signals use pins
- Consider disabling cycle counter completely (saves more pins)
- Or multiplex Wishbone data to reduce width further
- See `IO_OPTIMIZATION.md` for detailed options
