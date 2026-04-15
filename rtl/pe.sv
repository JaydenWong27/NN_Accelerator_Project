module pe (
    input logic clk,
    input logic rst_n,
    input logic en,
    input logic signed [7:0] activation_in,
    input logic signed [7:0] weight,
    input logic signed [31:0] acc_in,
    output logic signed [31:0] acc_out,
    output logic signed [7:0] activation_out
);

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            acc_out <= 32'sd0;
            activation_out <= 8'sd0;
        end else if (en) begin
            acc_out <= acc_in + (activation_in * weight);
            activation_out <= activation_in;
        end
    end
endmodule