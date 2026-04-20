module reg_interface (
    input logic clk,
    input logic rst_n,

    //Wishbone
    input logic wb_cyc,
    input logic wb_stb,
    input logic wb_we,
    input logic [31:0] wb_addr,
    input logic[31:0] wb_dat_m2s,
    input logic [3:0] wb_sel,
    output logic[31:0] wb_dat_s2m,
    output logic wb_ack,
    output logic wb_err,

    //Control
    output logic start,
    output logic soft_reset,

    //status
    input logic done,
    input logic busy,
    input logic error,
    input logic boot_done,
    input logic [47:0] cycle_count,

    //data
    output logic signed [7:0] input_buf [0:783],
    input logic signed [31:0] output_buf [0:9]
);

logic [11:0] offset;
assign offset = wb_addr[11:0];
assign wb_err = 1'b0;

always_ff @(posedge clk) begin
    if (!rst_n) begin
        wb_ack <= 1'b0;
        start <= 1'b0;
        soft_reset <= 1'b0;
        for (int k = 0; k < 784; k++) begin
            input_buf[k] <= 8'sd0;
        end
    end else begin
        wb_ack <= wb_cyc & wb_stb & ~wb_ack;
        start <= 1'b0;
        soft_reset <= 1'b0;
        if (wb_cyc & wb_stb & wb_we & ~wb_ack) begin
            if (offset == 12'h000) begin
                start <= wb_dat_m2s[0];
                soft_reset <= wb_dat_m2s[1];
            end
            if (offset >= 12'h008&& offset <= 12'h314) begin
                automatic int base_pixel;
                base_pixel = (offset - 12'h008) >> 2 << 2; // divide by 4 then multiply by 4 for clearing lower 2 bits
                if (wb_sel[0]) begin
                    input_buf[base_pixel + 0] <= wb_dat_m2s[7:0];
                end 
                if (wb_sel[1]) begin
                    input_buf[base_pixel + 1] <= wb_dat_m2s[15:8];
                end
                if (wb_sel[2]) begin
                    input_buf[base_pixel + 2] <= wb_dat_m2s[23:16];
                end 
                if (wb_sel[3]) begin
                    input_buf[base_pixel + 3] <= wb_dat_m2s[31:24];
                end
            end
         end
    end
end

always_comb begin
    wb_dat_s2m = 32'h0;

    case (offset)
        12'h004: wb_dat_s2m = {28'h0, boot_done, error, busy, done};
        12'h338: wb_dat_s2m = cycle_count[31:0];
        12'h33C: wb_dat_s2m = {16'h0, cycle_count[47:32]};
        default: begin
            if (offset >= 12'h318 && offset <= 12'h33C) begin
                automatic int logit_idx;
                logit_idx = (offset - 12'h318) >> 2;
                if (logit_idx < 10) begin
                    wb_dat_s2m = output_buf[logit_idx];
                end
            end
        end
    endcase
 end



endmodule