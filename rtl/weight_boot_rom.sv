// Boot-time weight ROM. Holds weights_all.hex (FC1/FC2 weights + biases,
// 101,770 bytes) and feeds weight_boot_fsm during the power-up copy to SDRAM.
// Registered read: data is valid one cycle after addr, which the boot FSM
// tolerates because the SDRAM write latches wr_data several cycles after the
// byte counter last changed.
//
// The ROM contents come from the WEIGHT_ROM_FILE macro, e.g.
//   iverilog -DWEIGHT_ROM_FILE='"/path/to/weights_all.hex"' ...
// Without the macro the ROM is zero-filled (sequencing-only simulations).
// A macro is used instead of a string parameter because Icarus crashes on
// -P string parameter overrides.
module weight_boot_rom #(
    parameter int unsigned ROM_BYTES = 101770
) (
    input  logic        clk,
    input  logic [16:0] addr,
    output logic [7:0]  data
);

logic [7:0] rom [0:ROM_BYTES-1];

initial begin
    for (int i = 0; i < ROM_BYTES; i++) rom[i] = 8'h00;
`ifdef WEIGHT_ROM_FILE
    $readmemh(`WEIGHT_ROM_FILE, rom);
`endif
end

always_ff @(posedge clk) begin
    data <= rom[addr];
end

endmodule
