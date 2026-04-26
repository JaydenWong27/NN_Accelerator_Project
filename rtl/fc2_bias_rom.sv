module fc2_bias_rom (
    input logic [3:0] addr,
    output logic signed [7:0] data
);

logic signed [7:0] rom [0:9];

initial begin
    $readmemh("weights/fc2_bias.hex", rom);
end

assign data = rom[addr];

endmodule
