`timescale 1ns/1ps
// Self-checking testbench for sdram_controller.
//
// Includes a minimal behavioural SDR SDRAM model (CAS latency 2, burst
// length 1, per-bank open row). The model flags protocol violations:
//   - any non-NOP command latched on two consecutive clock edges
//   - READ/WRITE issued to a bank with no open row
//
// Checks:
//   1. Init sequence: exactly 2 AUTO REFRESH + 1 MODE REGISTER SET
//   2. wr_ready is a single-cycle pulse (boot FSM advances 1 byte per write)
//   3. Byte writes land at the right addresses (read-after-write)
//   4. 8-byte burst reads return one data_valid per byte, correct data
//   5. Reads still work after a periodic refresh
//
// Run:
//   iverilog -g2012 -o sim_sdram.vvp tb_sdram.sv ../rtl/sdram_controller.sv
//   vvp sim_sdram.vvp

// ---------------------------------------------------------------------------
module sdram_model #(
    // 1: memory powers up as zeros (system tests where not every address is
    //    boot-loaded); 0: unwritten words read X so read-before-write is caught
    parameter bit INIT_ZERO = 0
) (
    input  logic        clk,
    input  logic        cke,
    input  logic        cs_n,
    input  logic        ras_n,
    input  logic        cas_n,
    input  logic        we_n,
    input  logic [1:0]  ba,
    input  logic [12:0] a,
    inout  logic [15:0] dq
);
    // {bank[1:0], row[7:0], col[8:0]} -> 19-bit key (model supports rows 0-255)
    logic [15:0] mem [0:(1<<19)-1];
    logic [12:0] open_row [0:3];
    logic        row_open [0:3];

    // CAS latency 2 read pipe: data driven for one cycle, two edges after READ
    logic [15:0] rd_data [0:1];
    logic        rd_en   [0:1];
    assign dq = rd_en[1] ? rd_data[1] : 16'hzzzz;

    logic [2:0] cmd;
    assign cmd = {ras_n, cas_n, we_n};

    int refresh_count = 0;
    int mrs_count     = 0;
    int err_count     = 0;
    logic prev_cmd_active = 0;

    function automatic [18:0] key(input [1:0] bank, input [12:0] row, input [8:0] col);
        key = {bank, row[7:0], col};
    endfunction

    initial begin
        if (INIT_ZERO)
            for (int i = 0; i < (1<<19); i++) mem[i] = 16'h0;
    end

    always @(posedge clk) begin
        // command must be a 1-cycle pulse: this controller never legitimately
        // issues commands back-to-back, so two active edges in a row means a
        // command was held through a wait state
        prev_cmd_active <= (cke && !cs_n && cmd != 3'b111);
        if (cke && !cs_n && cmd != 3'b111 && prev_cmd_active) begin
            $display("MODEL ERROR @%0t: back-to-back command cmd=%b", $time, cmd);
            err_count++;
        end

        rd_en[1]   <= rd_en[0];
        rd_data[1] <= rd_data[0];
        rd_en[0]   <= 1'b0;

        if (cke && !cs_n) begin
            case (cmd)
                3'b011: begin // ACTIVATE
                    if (a[12:8] != 0) begin
                        $display("MODEL ERROR @%0t: row %0d beyond modelled range", $time, a);
                        err_count++;
                    end
                    open_row[ba] <= a;
                    row_open[ba] <= 1'b1;
                end
                3'b101: begin // READ
                    if (!row_open[ba]) begin
                        $display("MODEL ERROR @%0t: READ with no open row on bank %0d", $time, ba);
                        err_count++;
                    end
                    rd_data[0] <= mem[key(ba, open_row[ba], a[8:0])];
                    rd_en[0]   <= 1'b1;
                end
                3'b100: begin // WRITE (data latched with the command)
                    if (!row_open[ba]) begin
                        $display("MODEL ERROR @%0t: WRITE with no open row on bank %0d", $time, ba);
                        err_count++;
                    end
                    mem[key(ba, open_row[ba], a[8:0])] <= dq;
                end
                3'b010: begin // PRECHARGE
                    if (a[10]) begin
                        row_open[0] <= 0; row_open[1] <= 0;
                        row_open[2] <= 0; row_open[3] <= 0;
                    end else
                        row_open[ba] <= 0;
                end
                3'b001: refresh_count++; // AUTO REFRESH
                3'b000: mrs_count++;     // MODE REGISTER SET
                default: ;               // NOP / burst terminate
            endcase
        end
    end
endmodule

// ---------------------------------------------------------------------------
module tb_sdram;

    logic clk = 0;
    logic rst_n;
    always #5 clk = ~clk;

    // read port
    logic        req_valid;
    logic [23:0] req_byte_addr;
    logic [7:0]  req_burst_len;
    logic        req_ready;
    logic [7:0]  data_out;
    logic        data_valid;
    logic        burst_done;
    // write port
    logic        wr_valid;
    logic [23:0] wr_byte_addr;
    logic [7:0]  wr_data;
    logic        wr_ready;
    // pins
    logic        sdram_cke, sdram_cs_n, sdram_ras_n, sdram_cas_n, sdram_we_n;
    logic [1:0]  sdram_ba;
    logic [12:0] sdram_a;
    wire  [15:0] sdram_dq;

    sdram_controller dut (
        .clk(clk), .rst_n(rst_n),
        .req_valid(req_valid), .req_byte_addr(req_byte_addr),
        .req_burst_len(req_burst_len), .req_ready(req_ready),
        .data_out(data_out), .data_valid(data_valid), .burst_done(burst_done),
        .wr_valid(wr_valid), .wr_byte_addr(wr_byte_addr),
        .wr_data(wr_data), .wr_ready(wr_ready),
        .sdram_cke(sdram_cke), .sdram_cs_n(sdram_cs_n),
        .sdram_ras_n(sdram_ras_n), .sdram_cas_n(sdram_cas_n),
        .sdram_we_n(sdram_we_n), .sdram_ba(sdram_ba),
        .sdram_a(sdram_a), .sdram_dq(sdram_dq)
    );

    sdram_model u_model (
        .clk(clk), .cke(sdram_cke), .cs_n(sdram_cs_n),
        .ras_n(sdram_ras_n), .cas_n(sdram_cas_n), .we_n(sdram_we_n),
        .ba(sdram_ba), .a(sdram_a), .dq(sdram_dq)
    );

    int errors = 0;

    // wr_ready must never be high two cycles in a row (the boot FSM counts
    // one byte per wr_ready cycle)
    int wr_ready_streak = 0;
    always @(posedge clk) begin
        if (wr_ready === 1'b1) begin
            wr_ready_streak++;
            if (wr_ready_streak > 1) begin
                $display("FAIL @%0t: wr_ready held for %0d cycles", $time, wr_ready_streak);
                errors++;
            end
        end else
            wr_ready_streak = 0;
    end

    // capture read bytes exactly the way weight_tile_cache does: sample
    // data_out on every edge where data_valid entered the edge high
    logic [7:0] rx_buf [0:255];
    int rx_count = 0;
    always @(posedge clk) begin
        if (data_valid === 1'b1) begin
            rx_buf[rx_count] = data_out;
            rx_count++;
        end
    end

    function automatic [7:0] pattern(input [23:0] addr);
        pattern = addr[7:0] ^ 8'h5A ^ {4'h0, addr[11:8]};
    endfunction

    // boot-FSM style handshake: hold wr_valid until wr_ready, 1-cycle gap
    task automatic write_byte(input [23:0] addr);
        int guard;
        guard = 0;
        wr_byte_addr = addr;
        wr_data      = pattern(addr);
        wr_valid     = 1;
        @(posedge clk); #1;
        while (wr_ready !== 1'b1) begin
            @(posedge clk); #1;
            guard++;
            if (guard > 200) begin
                $display("FAIL: write to %h timed out", addr);
                errors++;
                break;
            end
        end
        wr_valid = 0;
        @(posedge clk); #1;
    endtask

    task automatic read_burst(input [23:0] addr, input int len);
        int guard;
        guard = 0;
        rx_count      = 0;
        req_byte_addr = addr;
        req_burst_len = 8'(len);
        req_valid     = 1;
        @(posedge clk); #1;
        while (burst_done !== 1'b1) begin
            @(posedge clk); #1;
            guard++;
            if (guard > 500) begin
                $display("FAIL: burst read at %h timed out", addr);
                errors++;
                break;
            end
        end
        req_valid = 0;
        repeat (3) begin @(posedge clk); #1; end

        if (rx_count !== len) begin
            $display("FAIL: burst at %h returned %0d data_valid strobes, expected %0d",
                     addr, rx_count, len);
            errors++;
        end
        for (int k = 0; k < len; k++) begin
            if (rx_buf[k] !== pattern(addr + 24'(k))) begin
                $display("FAIL: byte %0d of burst at %h = %h, expected %h",
                         k, addr, rx_buf[k], pattern(addr + 24'(k)));
                errors++;
            end
        end
    endtask

    initial begin
        int guard;
        rst_n         = 0;
        req_valid     = 0;
        req_byte_addr = 0;
        req_burst_len = 8'd8;
        wr_valid      = 0;
        wr_byte_addr  = 0;
        wr_data       = 0;
        repeat (5) begin @(posedge clk); #1; end
        rst_n = 1;

        // --- 1. initialisation -------------------------------------------
        guard = 0;
        while (req_ready !== 1'b1) begin
            @(posedge clk); #1;
            guard++;
            if (guard > 30000) begin
                $display("FAIL: init never completed");
                errors++;
                break;
            end
        end
        if (u_model.refresh_count !== 2) begin
            $display("FAIL: init issued %0d AUTO REFRESH commands, expected 2",
                     u_model.refresh_count);
            errors++;
        end
        if (u_model.mrs_count !== 1) begin
            $display("FAIL: init issued %0d MODE REGISTER SET commands, expected 1",
                     u_model.mrs_count);
            errors++;
        end
        $display("init complete after %0d cycles (refresh=%0d mrs=%0d)",
                 guard, u_model.refresh_count, u_model.mrs_count);

        // --- 2. byte writes, two banks -------------------------------------
        for (int i = 0; i < 32; i++) write_byte(24'h000100 + 24'(i));
        for (int i = 0; i < 8;  i++) write_byte(24'h400230 + 24'(i));
        // unaligned region straddling the row-0/row-1 boundary (col 508..511
        // of row 0, col 0..3 of row 1)
        for (int i = 0; i < 8;  i++) write_byte(24'h0001FC + 24'(i));
        $display("writes complete");

        // --- 3. burst read-after-write, bank 0 -----------------------------
        read_burst(24'h000100, 8);
        read_burst(24'h000108, 8);
        read_burst(24'h000110, 8);
        read_burst(24'h000118, 8);
        // --- 4. bank decode -------------------------------------------------
        read_burst(24'h400230, 8);
        // --- 4b. burst crossing a row boundary mid-flight -------------------
        read_burst(24'h0001FC, 8);
        $display("burst reads complete");

        // --- 5. survive a periodic refresh ---------------------------------
        repeat (1700) @(posedge clk);
        #1;
        if (u_model.refresh_count < 3) begin
            $display("FAIL: periodic refresh never fired (refresh_count=%0d)",
                     u_model.refresh_count);
            errors++;
        end
        read_burst(24'h000100, 8);
        $display("post-refresh read complete (refresh_count=%0d)", u_model.refresh_count);

        // --- summary --------------------------------------------------------
        errors += u_model.err_count;
        if (errors == 0)
            $display("TB_RESULT: PASS");
        else
            $display("TB_RESULT: FAIL (%0d errors)", errors);
        $finish;
    end

    // global timeout: 1 ms of sim time
    initial begin
        #1000000;
        $display("TB_RESULT: FAIL (global timeout)");
        $finish;
    end

endmodule
