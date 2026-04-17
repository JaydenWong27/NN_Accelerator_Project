module systolic_array(
    input logic clk,
    input logic rst_n,
    input logic en,
    input logic signed [7:0] activation_in [0:7],
    input logic signed [7:0] weight[0:63],
    output logic signed [31:0] acc_out [0:63]
);
logic signed [7:0] act [0:7][0:8];
logic signed [7:0] skew [1:7][0:6];
logic signed [31:0] acc_internal[0:63];
genvar i, j;
generate 
    for (i = 0; i < 8; i++) begin : row
            for (j = 0; j < 8; j++) begin : col
                pe pe_inst (
                    .clk(clk),
                    .rst_n(rst_n),
                    .en(en),
                    .activation_in(act[i][j]),
                    .weight(weight[i*8+j]),
                    .acc_in(acc_internal[i*8+j]),
                    .acc_out(acc_internal[i*8+j]),
                    .activation_out(act[i][j+1])
                );
                assign acc_out[i*8+j] = acc_internal[i*8+j];
            end
        end
endgenerate

//row 0: no delay
assign act[0][0] = activation_in[0];

//row 1: 1 cycle delay 
always_ff @(posedge clk) begin 
    skew[1][0] <= activation_in[1];
end
assign act[1][0] = skew[1][0];

//row 2: 2 cycle delay 
always_ff @(posedge clk) begin
    skew[2][0] <= activation_in[2];
    skew[2][1] <= skew[2][0];
end
assign act[2][0] = skew [2][1];

//row 3: 3 cycle delay
always_ff @(posedge clk) begin
    skew[3][0] <= activation_in[3];
    skew[3][1] <= skew[3][0];
    skew[3][2] <= skew[3][1];
end
assign act[3][0] = skew [3][2];

//row 4: 4 cycle delay
always_ff @(posedge clk) begin
    skew[4][0] <= activation_in[4];
    skew[4][1] <= skew[4][0];
    skew[4][2] <= skew[4][1];
    skew[4][3] <= skew[4][2];
end
assign act[4][0] = skew [4][3];

//row 5: 5 cycle delay 
always_ff @(posedge clk) begin
    skew[5][0] <= activation_in[5];
    skew[5][1] <= skew[5][0];
    skew[5][2] <= skew[5][1];
    skew[5][3] <= skew[5][2];
    skew[5][4] <= skew[5][3];
end
assign act[5][0] = skew [5][4];


//row 6: 6 cycle delay
always_ff @(posedge clk) begin
    skew[6][0] <= activation_in[6];
    skew[6][1] <= skew[6][0];
    skew[6][2] <= skew[6][1];
    skew[6][3] <= skew[6][2];
    skew[6][4] <= skew[6][3];
    skew[6][5] <= skew[6][4];
end
assign act[6][0] = skew [6][5];


//row 7: 7 cycle delay
always_ff @(posedge clk) begin
    skew[7][0] <= activation_in[7];
    skew[7][1] <= skew[7][0];
    skew[7][2] <= skew[7][1];
    skew[7][3] <= skew[7][2];
    skew[7][4] <= skew[7][3];
    skew[7][5] <= skew[7][4];
    skew[7][6] <= skew[7][5];
end
assign act[7][0] = skew [7][6];
endmodule