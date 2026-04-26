module fc1_bias_rom (
    input logic [7:0] addr,
    output logic signed [7:0] data
);

logic signed [7:0] rom [0:127];

initial begin
    $readmemh("weights/fc1_bias.hex", rom);
end

assign data = rom[addr];

endmodule
