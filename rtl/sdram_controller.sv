module sdram_controller(
    input  logic        clk,
    input  logic        rst_n,
    input  logic        req_valid,
    input  logic [23:0] req_byte_addr,
    input  logic [7:0]  req_burst_len,
    output logic        req_ready,
    output logic [7:0]  data_out,
    output logic        data_valid,
    output logic        burst_done,
    input  logic        wr_valid,
    input  logic [23:0] wr_byte_addr,
    input  logic [7:0]  wr_data,
    output logic        wr_ready,
    output logic        sdram_cke,
    output logic        sdram_cs_n,
    output logic        sdram_ras_n,
    output logic        sdram_cas_n,
    output logic        sdram_we_n,
    output logic [1:0]  sdram_ba,
    output logic [12:0] sdram_a,
    inout  logic [15:0] sdram_dq
);

logic [14:0] timer;
logic [10:0] refresh_counter;
logic [7:0]  burst_count;
logic [15:0] dq_out;
logic        dq_oe;
logic [23:0] addr_reg;
logic        is_write;

assign sdram_dq = dq_oe ? dq_out : 16'hZZZZ;

typedef enum logic [3:0] {
    INIT_WAIT,
    INIT_PRECHARGE,
    INIT_REFRESH_1,
    INIT_REFRESH_2,
    INIT_MODE,
    IDLE,
    REFRESH,
    ACTIVATE,
    READ,
    READ_WAIT,
    ROW_OPEN,     // burst crossed a row boundary: tRP wait, then re-activate
    PRECHARGE,
    WRITE,
    WRITE_WAIT
} state_t;

state_t state;

// Commands are issued for exactly one clock at each state transition; the
// wait states that follow drive NOP so no command is re-latched while a
// timing parameter (tRP/tRC/tRCD/tMRD/tWR) elapses.
always_ff @(posedge clk) begin
    if (!rst_n) begin
        state           <= INIT_WAIT;
        timer           <= 15'd20000;
        refresh_counter <= 0;
        burst_count     <= 0;
        dq_oe           <= 0;
        dq_out          <= 16'h0;
        addr_reg        <= 24'h0;
        is_write        <= 0;
        sdram_cke       <= 1;
        sdram_cs_n      <= 0;
        sdram_ras_n     <= 1;
        sdram_cas_n     <= 1;
        sdram_we_n      <= 1;
        sdram_ba        <= 2'b00;
        sdram_a         <= 13'h0;
        req_ready       <= 0;
        data_valid      <= 0;
        burst_done      <= 0;
        wr_ready        <= 0;
    end else begin
        refresh_counter <= refresh_counter + 1;
        case (state)
            INIT_WAIT: begin
                if (timer == 0) begin
                    sdram_ras_n <= 0;   // PRECHARGE ALL
                    sdram_cas_n <= 1;
                    sdram_we_n  <= 0;
                    sdram_a[10] <= 1;
                    state       <= INIT_PRECHARGE;
                    timer       <= 15'd2;
                end else
                    timer <= timer - 1;
            end

            INIT_PRECHARGE: begin
                sdram_ras_n <= 1;
                sdram_cas_n <= 1;
                sdram_we_n  <= 1;
                if (timer == 0) begin
                    sdram_ras_n <= 0;   // AUTO REFRESH 1
                    sdram_cas_n <= 0;
                    sdram_we_n  <= 1;
                    state       <= INIT_REFRESH_1;
                    timer       <= 15'd7;
                end else
                    timer <= timer - 1;
            end

            INIT_REFRESH_1: begin
                sdram_ras_n <= 1;
                sdram_cas_n <= 1;
                sdram_we_n  <= 1;
                if (timer == 0) begin
                    sdram_ras_n <= 0;   // AUTO REFRESH 2
                    sdram_cas_n <= 0;
                    sdram_we_n  <= 1;
                    state       <= INIT_REFRESH_2;
                    timer       <= 15'd7;
                end else
                    timer <= timer - 1;
            end

            INIT_REFRESH_2: begin
                sdram_ras_n <= 1;
                sdram_cas_n <= 1;
                sdram_we_n  <= 1;
                if (timer == 0) begin
                    sdram_ras_n <= 0;   // MODE REGISTER SET
                    sdram_cas_n <= 0;
                    sdram_we_n  <= 0;
                    sdram_ba    <= 0;
                    sdram_a     <= 13'b0000000100000; // CAS=2, burst=1
                    state       <= INIT_MODE;
                    timer       <= 15'd2;
                end else
                    timer <= timer - 1;
            end

            INIT_MODE: begin
                sdram_ras_n <= 1;
                sdram_cas_n <= 1;
                sdram_we_n  <= 1;
                if (timer == 0) begin
                    state       <= IDLE;
                    req_ready   <= 1;
                end else
                    timer <= timer - 1;
            end

            IDLE: begin
                burst_done <= 0;
                data_valid <= 0;
                wr_ready   <= 0;
                if (refresh_counter >= 11'd1560) begin
                    refresh_counter <= 0;
                    sdram_ras_n     <= 0;   // single AUTO REFRESH
                    sdram_cas_n     <= 0;
                    sdram_we_n      <= 1;
                    req_ready       <= 0;
                    timer           <= 15'd7;
                    state           <= REFRESH;
                end else if (wr_valid) begin
                    addr_reg    <= wr_byte_addr;
                    is_write    <= 1;
                    wr_ready    <= 0;
                    req_ready   <= 0;
                    burst_count <= 0;
                    sdram_ras_n <= 0;
                    sdram_cas_n <= 1;
                    sdram_we_n  <= 1;
                    sdram_ba    <= wr_byte_addr[23:22];
                    sdram_a     <= wr_byte_addr[21:9];
                    timer       <= 15'd2;
                    state       <= ACTIVATE;
                end else if (req_valid) begin
                    addr_reg    <= req_byte_addr;
                    is_write    <= 0;
                    req_ready   <= 0;
                    burst_count <= 0;
                    sdram_ras_n <= 0;
                    sdram_cas_n <= 1;
                    sdram_we_n  <= 1;
                    sdram_ba    <= req_byte_addr[23:22];
                    sdram_a     <= req_byte_addr[21:9];
                    timer       <= 15'd2;
                    state       <= ACTIVATE;
                end
            end

            REFRESH: begin
                sdram_ras_n <= 1;
                sdram_cas_n <= 1;
                sdram_we_n  <= 1;
                if (timer == 0) begin
                    state     <= IDLE;
                    req_ready <= 1;
                end else
                    timer <= timer - 1;
            end

            ACTIVATE: begin
                sdram_ras_n <= 1;
                if (timer == 0) begin
                    if (is_write) state <= WRITE;
                    else          state <= READ;
                end else
                    timer <= timer - 1;
            end

            // mode register burst length is 1, so each byte of the burst
            // gets its own READ command; addr_reg advances one byte per beat
            READ: begin
                sdram_cas_n <= 0;
                sdram_we_n  <= 1;
                sdram_ba    <= addr_reg[23:22];
                sdram_a     <= {4'b0, addr_reg[8:0]};
                data_valid  <= 0;
                timer       <= 15'd2;
                state       <= READ_WAIT;
            end

            READ_WAIT: begin
                sdram_cas_n <= 1;
                if (timer > 0) begin
                    timer <= timer - 1;
                end else begin
                    data_out    <= sdram_dq[7:0];
                    data_valid  <= 1;
                    burst_count <= burst_count + 1;
                    addr_reg    <= addr_reg + 1;
                    if (burst_count >= req_burst_len - 1) begin
                        burst_done  <= 1;
                        sdram_ras_n <= 0;   // PRECHARGE ALL
                        sdram_we_n  <= 0;
                        sdram_a[10] <= 1;
                        state       <= PRECHARGE;
                        timer       <= 15'd2;
                    end else if (addr_reg[8:0] == 9'd511) begin
                        // burst continues in the next row: close this one,
                        // then re-activate at the incremented address
                        sdram_ras_n <= 0;   // PRECHARGE ALL
                        sdram_we_n  <= 0;
                        sdram_a[10] <= 1;
                        state       <= ROW_OPEN;
                        timer       <= 15'd2;
                    end else begin
                        state <= READ;
                    end
                end
            end

            ROW_OPEN: begin
                sdram_ras_n <= 1;
                sdram_we_n  <= 1;
                data_valid  <= 0;
                if (timer == 0) begin
                    sdram_ras_n <= 0;   // ACTIVATE the next row
                    sdram_cas_n <= 1;
                    sdram_we_n  <= 1;
                    sdram_ba    <= addr_reg[23:22];
                    sdram_a     <= addr_reg[21:9];
                    timer       <= 15'd2;
                    state       <= ACTIVATE;
                end else
                    timer <= timer - 1;
            end

            WRITE: begin
                sdram_cas_n <= 0;
                sdram_we_n  <= 0;
                sdram_ba    <= addr_reg[23:22];
                sdram_a     <= {4'b0, addr_reg[8:0]};
                dq_oe       <= 1;
                dq_out      <= {8'h00, wr_data};
                timer       <= 15'd2;
                state       <= WRITE_WAIT;
            end

            WRITE_WAIT: begin
                sdram_cas_n <= 1;
                sdram_we_n  <= 1;
                if (timer == 0) begin
                    dq_oe       <= 0;
                    wr_ready    <= 1;   // 1-cycle pulse; cleared in PRECHARGE
                    sdram_ras_n <= 0;   // PRECHARGE ALL
                    sdram_we_n  <= 0;
                    sdram_a[10] <= 1;
                    state       <= PRECHARGE;
                    timer       <= 15'd2;
                end else
                    timer <= timer - 1;
            end

            PRECHARGE: begin
                sdram_ras_n <= 1;
                sdram_we_n  <= 1;
                wr_ready    <= 0;
                data_valid  <= 0;
                if (timer == 0) begin
                    state       <= IDLE;
                    req_ready   <= 1;
                end else
                    timer <= timer - 1;
            end

        endcase
    end
end

endmodule
