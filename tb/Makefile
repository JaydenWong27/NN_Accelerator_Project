SIM = icarus
TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(PWD)/../rtl/control_fsm.sv
TOPLEVEL = control_fsm
MODULE = tb_control_fsm

COCOTB_ROOT ?= $(shell python -c "import cocotb_tools; import os; print(os.path.dirname(cocotb_tools.__file__))")
include $(COCOTB_ROOT)/makefiles/Makefile.sim