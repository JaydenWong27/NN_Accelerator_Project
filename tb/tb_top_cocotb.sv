`timescale 1ns/1ps
// cocotb wrapper for full-system tests: nn_accelerator_top with its SDRAM
// pins looped into the behavioural model from tb_sdram.sv. cocotb drives
// clock, reset, and the Wishbone port.
module tb_top_cocotb (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        wb_cyc,
    input  logic        wb_stb,
    input  logic        wb_we,
    input  logic [31:0] wb_addr,
    input  logic [31:0] wb_dat_m2s,
    input  logic [3:0]  wb_sel,
    output logic [31:0] wb_dat_s2m,
    output logic        wb_ack,
    output logic        wb_err
);

logic        sdram_cke, sdram_cs_n, sdram_ras_n, sdram_cas_n, sdram_we_n;
logic [1:0]  sdram_ba;
logic [12:0] sdram_a;
wire  [15:0] sdram_dq;

nn_accelerator_top u_top (
    .clk(clk), .rst_n(rst_n),
    .wb_cyc(wb_cyc), .wb_stb(wb_stb), .wb_we(wb_we),
    .wb_addr(wb_addr), .wb_dat_m2s(wb_dat_m2s), .wb_sel(wb_sel),
    .wb_dat_s2m(wb_dat_s2m), .wb_ack(wb_ack), .wb_err(wb_err),
    .sdram_cke(sdram_cke), .sdram_cs_n(sdram_cs_n),
    .sdram_ras_n(sdram_ras_n), .sdram_cas_n(sdram_cas_n),
    .sdram_we_n(sdram_we_n), .sdram_ba(sdram_ba),
    .sdram_a(sdram_a), .sdram_dq(sdram_dq)
);

sdram_model #(.INIT_ZERO(1)) u_model (
    .clk(clk), .cke(sdram_cke), .cs_n(sdram_cs_n),
    .ras_n(sdram_ras_n), .cas_n(sdram_cas_n), .we_n(sdram_we_n),
    .ba(sdram_ba), .a(sdram_a), .dq(sdram_dq)
);

endmodule
