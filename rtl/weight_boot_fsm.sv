module weight_boot_fsm (
    input logic clk,
    input logic rst_n,
    input logic sdram_init_done,
    input logic wr_ready,
    input logic [7:0] rom_data,
    output logic [16:0] rom_addr,
    output logic [23:0] wr_byte_addr,
    output logic [7:0] wr_data,
    output logic wr_valid,
    output logic boot_done
);

typedef enum logic [1:0] {
    BOOT_WAIT,
    BOOT_COPY,
    BOOT_DONE
} state_t;

state_t state;
logic [16:0] byte_counter;

always_ff @(posedge clk) begin
    if (!rst_n) begin
        state <= BOOT_WAIT;
        byte_counter <= 17'h0;
    end else begin
        case (state)
        BOOT_WAIT: begin
            if (sdram_init_done) begin
                state <= BOOT_COPY;
            end
        end
        BOOT_COPY: begin
            if (wr_ready) begin
                if(byte_counter == 101769) begin
                    state <= BOOT_DONE;
                end else begin
                    byte_counter++;
                end
            end
        end
        BOOT_DONE: begin
            
        end
        endcase
    end
end

always_comb begin
    boot_done = (state == BOOT_DONE);
    wr_valid = (state == BOOT_COPY) && !wr_ready;
    rom_addr = byte_counter;
    wr_byte_addr = {7'h0, byte_counter};
    wr_data = rom_data;
end


endmodule