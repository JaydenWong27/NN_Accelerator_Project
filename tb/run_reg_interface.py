import os
from cocotb_tools.runner import get_runner

SOURCES = [
    os.path.abspath("../rtl/reg_interface.sv"),
]

runner = get_runner("icarus")
runner.build(
    sources=SOURCES,
    hdl_toplevel="reg_interface",
    always=True,
    build_args=["-g2012"],
    timescale=("1ns", "1ps"),
)
runner.test(
    hdl_toplevel="reg_interface",
    test_module="tb_reg_interface",
)
