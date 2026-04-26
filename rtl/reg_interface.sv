module reg_interface (
    input logic clk,
    input logic rst_n,

    //Wishbone
    input logic wb_cyc,
    input logic wb_stb,
    input logic wb_we,
    input logic [11:0] wb_addr,
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
            if (offset >= 12'h008 && offset <= 12'h314) begin
                if (wb_sel[0]) begin
                    input_buf[((offset - 12'h008) >> 2 << 2) + 0] <= wb_dat_m2s[7:0];
                end
                if (wb_sel[1]) begin
                    input_buf[((offset - 12'h008) >> 2 << 2) + 1] <= wb_dat_m2s[15:8];
                end
                if (wb_sel[2]) begin
                    input_buf[((offset - 12'h008) >> 2 << 2) + 2] <= wb_dat_m2s[23:16];
                end
                if (wb_sel[3]) begin
                    input_buf[((offset - 12'h008) >> 2 << 2) + 3] <= wb_dat_m2s[31:24];
                end
            end
         end
    end
end

always_comb begin
    wb_dat_s2m = 32'h0;

    case (offset)
        12'h004: wb_dat_s2m = {28'h0, boot_done, error, busy, done};
        default: begin
            if (offset >= 12'h318 && offset <= 12'h33C) begin
                if (((offset - 12'h318) >> 2) < 10) begin
                    wb_dat_s2m = output_buf[(offset - 12'h318) >> 2];
                end
            end
        end
    endcase
 end



endmodule