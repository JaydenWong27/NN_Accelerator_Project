module weights_rom (
    input logic [16:0] addr,
    output logic [7:0] data
);

logic [7:0] rom [0:101769];

initial begin
    $readmemh("weights/weights_all.hex", rom);
end

assign data = rom[addr];

endmodule
