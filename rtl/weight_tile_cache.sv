module weight_tile_cache (
    input logic clk,
    input logic rst_n,
    input logic wr_en,
    input logic [5:0] wr_addr,
    input logic signed [7:0] wr_data,
    output logic signed  [7:0] weight_out [0:63]
);

logic signed [7:0] registers [0:63];

always_ff @(posedge clk )begin
    if(!rst_n) begin
        for(int i = 0; i < 64; i+= 1) begin
            registers[i] <= 8'sd0;
        end
    end else begin
        if(wr_en) begin
            registers[wr_addr] <= wr_data;
        end
    end

end

always_comb begin
    for (int i = 0; i < 64; i++)begin
        weight_out[i] = registers[i];
    end
end


endmodule