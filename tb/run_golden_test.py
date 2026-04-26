import os
from cocotb_tools.runner import get_runner

RTL = os.path.abspath("../rtl")
SOURCES = [
    f"{RTL}/pe.sv",
    f"{RTL}/systolic_array.sv",
    f"{RTL}/weight_tile_cache.sv",
    f"{RTL}/sdram_controller.sv",
    f"{RTL}/control_fsm.sv",
    f"{RTL}/tiling_fsm.sv",
    f"{RTL}/weight_boot_fsm.sv",
    f"{RTL}/weights_rom.sv",
    f"{RTL}/reg_interface.sv",
    f"{RTL}/nn_accelerator_top.sv",
    os.path.abspath("tb_nn_top_wrapper.sv"),
]

runner = get_runner("icarus")
runner.build(
    sources=SOURCES,
    hdl_toplevel="tb_nn_top_wrapper",
    always=True,
    build_args=["-g2012"],
    timescale=("1ns", "1ps"),
)
runner.test(
    hdl_toplevel="tb_nn_top_wrapper",
    test_module="tb_nn_accelerator_golden",
)
