SIM = icarus
TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(PWD)/../rtl/pe.sv
TOPLEVEL = pe
MODULE = tb_pe

COCOTB_ROOT ?= $(shell python -c "import cocotb_tools; import os; print(os.path.dirname(cocotb_tools.__file__))")
include $(COCOTB_ROOT)/makefiles/Makefile.sim