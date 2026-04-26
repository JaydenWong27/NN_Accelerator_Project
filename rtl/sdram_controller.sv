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
    inout  logic [7:0]  sdram_dq
);

logic [14:0] timer;
logic [10:0] refresh_counter;
logic [7:0]  burst_count;
logic [7:0]  dq_out;
logic        dq_oe;
logic [23:0] addr_reg;
logic        is_write;

assign sdram_dq = dq_oe ? dq_out : 8'hZZ;

typedef enum logic [3:0] {
    INIT_WAIT,
    INIT_PRECHARGE,
    INIT_REFRESH_1,
    INIT_REFRESH_2,
    INIT_MODE,
    IDLE,
    ACTIVATE,
    READ,
    READ_WAIT,
    PRECHARGE,
    WRITE,
    WRITE_WAIT
} state_t;

state_t state;

always_ff @(posedge clk) begin
    if (!rst_n) begin
        state           <= INIT_WAIT;
        timer           <= 15'd20000;
        refresh_counter <= 0;
        burst_count     <= 0;
        dq_oe           <= 0;
        is_write        <= 0;
        sdram_cke       <= 1;
        sdram_cs_n      <= 0;
        sdram_ras_n     <= 1;
        sdram_cas_n     <= 1;
        sdram_we_n      <= 1;
        req_ready       <= 0;
        data_valid      <= 0;
        burst_done      <= 0;
        wr_ready        <= 0;
    end else begin
        refresh_counter <= refresh_counter + 1;
        case (state)
            INIT_WAIT: begin
                if (timer == 0) begin
                    state <= INIT_PRECHARGE;
                    timer <= 15'd2;
                end else
                    timer <= timer - 1;
            end

            INIT_PRECHARGE: begin
                sdram_ras_n <= 0;
                sdram_cas_n <= 1;
                sdram_we_n  <= 0;
                sdram_a[10] <= 1;
                if (timer == 0) begin
                    state       <= INIT_REFRESH_1;
                    timer       <= 15'd7;
                    sdram_ras_n <= 1;
                    sdram_we_n  <= 1;
                end else
                    timer <= timer - 1;
            end

            INIT_REFRESH_1: begin
                sdram_ras_n <= 0;
                sdram_cas_n <= 0;
                sdram_we_n  <= 1;
                if (timer == 0) begin
                    state       <= INIT_REFRESH_2;
                    timer       <= 15'd7;
                    sdram_ras_n <= 1;
                    sdram_cas_n <= 1;
                end else
                    timer <= timer - 1;
            end

            INIT_REFRESH_2: begin
                sdram_ras_n <= 0;
                sdram_cas_n <= 0;
                sdram_we_n  <= 1;
                if (timer == 0) begin
                    state       <= INIT_MODE;
                    timer       <= 15'd2;
                    sdram_ras_n <= 1;
                    sdram_cas_n <= 1;
                end else
                    timer <= timer - 1;
            end

            INIT_MODE: begin
                sdram_ras_n <= 0;
                sdram_cas_n <= 0;
                sdram_we_n  <= 0;
                sdram_ba    <= 0;
                sdram_a     <= 13'b0000000100000; // CAS=2, burst=1
                if (timer == 0) begin
                    state       <= IDLE;
                    sdram_ras_n <= 1;
                    sdram_cas_n <= 1;
                    sdram_we_n  <= 1;
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
                    sdram_ras_n     <= 0;
                    sdram_cas_n     <= 0;
                    sdram_we_n      <= 1;
                    timer           <= 15'd7;
                    state           <= INIT_REFRESH_1;
                end else if (wr_valid) begin
                    addr_reg    <= wr_byte_addr;
                    is_write    <= 1;
                    wr_ready    <= 0;
                    req_ready   <= 0;
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
                    sdram_ras_n <= 0;
                    sdram_cas_n <= 1;
                    sdram_we_n  <= 1;
                    sdram_ba    <= req_byte_addr[23:22];
                    sdram_a     <= req_byte_addr[21:9];
                    timer       <= 15'd2;
                    state       <= ACTIVATE;
                end
            end

            ACTIVATE: begin
                sdram_ras_n <= 1;
                if (timer == 0) begin
                    if (is_write) state <= WRITE;
                    else          state <= READ;
                    burst_count <= 0;
                end else
                    timer <= timer - 1;
            end

            READ: begin
                sdram_cas_n <= 0;
                sdram_we_n  <= 1;
                sdram_ba    <= addr_reg[23:22];
                sdram_a     <= {4'b0, addr_reg[8:0]};
                timer       <= 15'd1;
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
                    if (burst_count >= req_burst_len - 1) begin
                        burst_done <= 1;
                        state      <= PRECHARGE;
                        timer      <= 15'd2;
                    end
                end
            end

            WRITE: begin
                sdram_cas_n <= 0;
                sdram_we_n  <= 0;
                sdram_ba    <= addr_reg[23:22];
                sdram_a     <= {4'b0, addr_reg[8:0]};
                dq_oe       <= 1;
                dq_out      <= wr_data;
                timer       <= 15'd2;
                state       <= WRITE_WAIT;
            end

            WRITE_WAIT: begin
                sdram_cas_n <= 1;
                sdram_we_n  <= 1;
                if (timer == 0) begin
                    dq_oe    <= 0;
                    wr_ready <= 1;
                    state    <= PRECHARGE;
                    timer    <= 15'd2;
                end else
                    timer <= timer - 1;
            end

            PRECHARGE: begin
                sdram_ras_n <= 0;
                sdram_we_n  <= 0;
                sdram_a[10] <= 1;
                if (timer == 0) begin
                    state       <= IDLE;
                    sdram_ras_n <= 1;
                    sdram_we_n  <= 1;
                    req_ready   <= 1;
                    wr_ready    <= 0;
                end else
                    timer <= timer - 1;
            end

        endcase
    end
end

endmodule
