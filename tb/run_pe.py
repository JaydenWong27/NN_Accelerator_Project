import os
from cocotb_tools.runner import get_runner

SOURCES = [
    os.path.abspath("../rtl/pe.sv"),
]

runner = get_runner("icarus")
runner.build(
    sources=SOURCES,
    hdl_toplevel="pe",
    always=True,
    build_args=["-g2012"],
    timescale=("1ns", "1ps"),
)
runner.test(
    hdl_toplevel="pe",
    test_module="tb_pe",
)
