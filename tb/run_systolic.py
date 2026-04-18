import os
from cocotb_tools.runner import get_runner

SOURCES = [
    os.path.abspath("../rtl/pe.sv"),
    os.path.abspath("../rtl/systolic_array.sv"),
]

runner = get_runner("icarus")
runner.build(
    sources=SOURCES,
    hdl_toplevel="systolic_array",
    always=True,
    build_args=["-g2012"],
    timescale=("1ns", "1ps"),
)
runner.test(
    hdl_toplevel="systolic_array",
    test_module="systolic_array_pe",
)
