// Test wrapper: instantiates nn_accelerator_top with a minimal SDRAM bus model
// so cocotb only needs to drive the Wishbone interface.
//
// Since rom_data is tied to 0 in nn_accelerator_top, every byte the boot FSM
// writes is 0. So we don't need a storage-faithful SDRAM model — we just need
// the dq bus to settle to 0 when the controller isn't driving it. A bank of
// pulldowns gives us exactly that: controller's strong drives win during
// writes, and reads see 0 (matching the all-zero contents).

module tb_nn_top_wrapper (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        wb_cyc,
    input  logic        wb_stb,
    input  logic        wb_we,
    input  logic [11:0] wb_addr,
    input  logic [31:0] wb_dat_m2s,
    input  logic [3:0]  wb_sel,
    output logic [31:0] wb_dat_s2m,
    output logic        wb_ack,
    output logic        wb_err
);

logic        sdram_cke, sdram_cs_n;
logic        sdram_ras_n, sdram_cas_n, sdram_we_n;
logic [1:0]  sdram_ba;
logic [12:0] sdram_a;
wire  [7:0]  sdram_dq;

// Pulldown on every dq line: resolves Z to 0 when controller releases the bus
pulldown pd_dq [7:0] (sdram_dq);

nn_accelerator_top u_dut (
    .clk(clk), .rst_n(rst_n),
    .wb_cyc(wb_cyc), .wb_stb(wb_stb), .wb_we(wb_we),
    .wb_addr(wb_addr), .wb_dat_m2s(wb_dat_m2s), .wb_sel(wb_sel),
    .wb_dat_s2m(wb_dat_s2m), .wb_ack(wb_ack), .wb_err(wb_err),
    .sdram_cke(sdram_cke), .sdram_cs_n(sdram_cs_n),
    .sdram_ras_n(sdram_ras_n), .sdram_cas_n(sdram_cas_n),
    .sdram_we_n(sdram_we_n), .sdram_ba(sdram_ba),
    .sdram_a(sdram_a), .sdram_dq(sdram_dq)
);

endmodule
