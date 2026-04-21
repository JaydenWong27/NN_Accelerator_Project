import os
from cocotb_tools.runner import get_runner

SOURCES = [
    os.path.abspath("../rtl/control_fsm.sv"),
]

runner = get_runner("icarus")
runner.build(
    sources=SOURCES,
    hdl_toplevel="control_fsm",
    always=True,
    build_args=["-g2012"],
    timescale=("1ns", "1ps"),
)
runner.test(
    hdl_toplevel="control_fsm",
    test_module="tb_control_fsm",
)
