module nn_accelerator_top (
    input  logic        clk,
    input  logic        rst_n,

    // Wishbone slave 
    input  logic        wb_cyc,
    input  logic        wb_stb,
    input  logic        wb_we,
    input  logic [31:0] wb_addr,
    input  logic [31:0] wb_dat_m2s,
    input  logic [3:0]  wb_sel,
    output logic [31:0] wb_dat_s2m,
    output logic        wb_ack,
    output logic        wb_err,

    // SDRAM physical pins
    output logic        sdram_cke,
    output logic        sdram_cs_n,
    output logic        sdram_ras_n,
    output logic        sdram_cas_n,
    output logic        sdram_we_n,
    output logic [1:0]  sdram_ba,
    output logic [12:0] sdram_a,
    inout  logic [15:0] sdram_dq
);

// reg_interface <-> control_fsm
logic  start, soft_reset, done, busy, error;
logic [47:0] cycle_count;

// control_fsm <-> tiling_fsm
logic tiling_start, tiling_layer_sel, tiling_done;

// reg_interface data
logic signed [7:0]  input_buf  [0:783];
logic signed [31:0] output_buf [0:9];
logic signed [31:0] acc_out    [0:127];

// systolic array
logic signed [31:0] pe_acc_out [0:63];
logic signed [7:0]  activation_in [0:7];
logic signed [7:0]  weight_out [0:63];
logic pe_en;

// tiling_fsm -> sdram_controller (read path)
logic sdram_req_valid;
logic [23:0] sdram_req_addr;
logic [7:0] sdram_req_len;
logic sdram_req_ready;
logic [7:0] sdram_data_out;
logic sdram_data_valid;
logic sdram_burst_done;

// weight_boot_fsm -> sdram_controller (write path)
logic wr_valid, wr_ready;
logic [23:0] wr_byte_addr;
logic [7:0] wr_data;

// weight_boot_fsm
logic boot_done;
logic [16:0] rom_addr;

// tile cache write counter
logic [5:0] cache_wr_addr;
always_ff @(posedge clk) begin
    if (!rst_n)
        cache_wr_addr <= 6'h0;
    else if (sdram_data_valid)
        cache_wr_addr <= cache_wr_addr + 1;
end

// burst_done = fill_done for tiling_fsm
logic fill_done;
assign fill_done = sdram_burst_done;

// acc_out[0:9] -> output_buf for Layer 2 logits
genvar k;
generate
    for (k = 0; k < 10; k++) begin : out_map
        assign output_buf[k] = acc_out[k];
    end
endgenerate

// rom_data stub - tie to 0 until weight_boot_rom is added
logic [7:0] rom_data;
assign rom_data = 8'h0;

// Module instantiations
reg_interface u_reg_interface (
    .clk(clk), .rst_n(rst_n),
    .wb_cyc(wb_cyc), .wb_stb(wb_stb), .wb_we(wb_we),
    .wb_addr(wb_addr), .wb_dat_m2s(wb_dat_m2s), .wb_sel(wb_sel),
    .wb_dat_s2m(wb_dat_s2m), .wb_ack(wb_ack), .wb_err(wb_err),
    .start(start), .soft_reset(soft_reset),
    .done(done), .busy(busy), .error(error),
    .boot_done(boot_done), .cycle_count(cycle_count),
    .input_buf(input_buf), .output_buf(output_buf)
);

control_fsm u_control_fsm (
    .clk(clk), .rst_n(rst_n),
    .start(start), .soft_reset(soft_reset),
    .tiling_done(tiling_done),
    .done(done), .busy(busy), .error(error),
    .cycle_count(cycle_count),
    .tiling_start(tiling_start),
    .tiling_layer_sel(tiling_layer_sel),
    .relu_en()
);

tiling_fsm u_tiling_fsm (
    .clk(clk), .rst_n(rst_n),
    .tiling_start(tiling_start),
    .tiling_layer_sel(tiling_layer_sel),
    .fill_done(fill_done),
    .pe_acc_out(pe_acc_out),
    .tiling_done(tiling_done),
    .pe_en(pe_en),
    .pe_rst_acc(),
    .swap_buffers(),
    .sdram_req_valid(sdram_req_valid),
    .sdram_req_addr(sdram_req_addr),
    .sdram_req_len(sdram_req_len),
    .weight_sel(),
    .activation_in(activation_in),
    .acc_out(acc_out)
);

systolic_array u_systolic_array (
    .clk(clk), .rst_n(rst_n), .en(pe_en),
    .activation_in(activation_in),
    .weight(weight_out),
    .acc_out(pe_acc_out)
);

sdram_controller u_sdram_controller (
    .clk(clk), .rst_n(rst_n),
    .req_valid(sdram_req_valid),
    .req_byte_addr(sdram_req_addr),
    .req_burst_len(sdram_req_len),
    .req_ready(sdram_req_ready),
    .data_out(sdram_data_out),
    .data_valid(sdram_data_valid),
    .burst_done(sdram_burst_done),
    .wr_valid(wr_valid),
    .wr_byte_addr(wr_byte_addr),
    .wr_data(wr_data),
    .wr_ready(wr_ready),
    .sdram_cke(sdram_cke), .sdram_cs_n(sdram_cs_n),
    .sdram_ras_n(sdram_ras_n), .sdram_cas_n(sdram_cas_n),
    .sdram_we_n(sdram_we_n), .sdram_ba(sdram_ba),
    .sdram_a(sdram_a), .sdram_dq(sdram_dq)
);

weight_boot_fsm u_weight_boot_fsm (
    .clk(clk), .rst_n(rst_n),
    .sdram_init_done(sdram_req_ready),
    .wr_ready(wr_ready),
    .rom_data(rom_data),
    .rom_addr(rom_addr),
    .wr_byte_addr(wr_byte_addr),
    .wr_data(wr_data),
    .wr_valid(wr_valid),
    .boot_done(boot_done)
);

weight_tile_cache u_weight_tile_cache (
    .clk(clk), .rst_n(rst_n),
    .wr_en(sdram_data_valid),
    .wr_addr(cache_wr_addr),
    .wr_data(sdram_data_out),
    .weight_out(weight_out)
);

endmodule
