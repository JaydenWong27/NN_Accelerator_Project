import os
from cocotb_tools.runner import get_runner

RTL_FILES = [
    "pe.sv",
    "systolic_array.sv",
    "control_fsm.sv",
    "tiling_fsm.sv",
    "reg_interface.sv",
    "sdram_controller.sv",
    "weight_boot_fsm.sv",
    "weight_boot_rom.sv",
    "weight_tile_cache.sv",
    "nn_accelerator_top.sv",
]

SOURCES = [os.path.abspath(f"../rtl/{f}") for f in RTL_FILES] + [
    os.path.abspath("tb_sdram.sv"),       # provides sdram_model
    os.path.abspath("tb_top_cocotb.sv"),
]

rom_file = os.path.abspath("../weights/weights_all.hex")

runner = get_runner("icarus")
runner.build(
    sources=SOURCES,
    hdl_toplevel="tb_top_cocotb",
    always=True,
    # macro instead of -P string parameter: icarus crashes on the latter.
    # (no explicit -s here: the runner adds it, and a duplicated -s root
    # also crashes icarus)
    build_args=["-g2012", f'-DWEIGHT_ROM_FILE="{rom_file}"'],
    timescale=("1ns", "1ps"),
)
runner.test(
    hdl_toplevel="tb_top_cocotb",
    test_module="tb_top",
)
