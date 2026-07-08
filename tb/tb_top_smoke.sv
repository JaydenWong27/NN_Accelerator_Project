`timescale 1ns/1ps
// Integration smoke test for nn_accelerator_top.
//
// Drives the whole system with the behavioural SDRAM model from tb_sdram.sv:
// boot copy completes, a Wishbone start kicks off inference, both layers run
// their full tile loops (98 + 16 tiles x 16 + 2 neuron groups), and DONE is
// reached. This exercises the control_fsm -> tiling_fsm -> sdram_controller
// handshakes end to end, including SDRAM requests that collide with
// periodic refresh cycles.
//
// The datapath itself is still a stub (tiling_fsm drives zero activations,
// rom_data is tied off), so all logits read back as 0. The point of this
// test is sequencing: no hangs, status bits behave, register map decodes.
//
// Run (-s selects this module as the only root; tb_sdram.sv is on the
// command line just to provide sdram_model):
//   iverilog -g2012 -s tb_top_smoke -o sim_top.vvp tb_top_smoke.sv tb_sdram.sv ../rtl/*.sv
//   vvp sim_top.vvp

module tb_top_smoke;

    logic clk = 0;
    logic rst_n;
    always #5 clk = ~clk;

    // Wishbone
    logic        wb_cyc, wb_stb, wb_we;
    logic [31:0] wb_addr, wb_dat_m2s, wb_dat_s2m;
    logic [3:0]  wb_sel;
    logic        wb_ack, wb_err;

    // SDRAM pins
    logic        sdram_cke, sdram_cs_n, sdram_ras_n, sdram_cas_n, sdram_we_n;
    logic [1:0]  sdram_ba;
    logic [12:0] sdram_a;
    wire  [15:0] sdram_dq;

    nn_accelerator_top u_top (
        .clk(clk), .rst_n(rst_n),
        .wb_cyc(wb_cyc), .wb_stb(wb_stb), .wb_we(wb_we),
        .wb_addr(wb_addr), .wb_dat_m2s(wb_dat_m2s), .wb_sel(wb_sel),
        .wb_dat_s2m(wb_dat_s2m), .wb_ack(wb_ack), .wb_err(wb_err),
        .sdram_cke(sdram_cke), .sdram_cs_n(sdram_cs_n),
        .sdram_ras_n(sdram_ras_n), .sdram_cas_n(sdram_cas_n),
        .sdram_we_n(sdram_we_n), .sdram_ba(sdram_ba),
        .sdram_a(sdram_a), .sdram_dq(sdram_dq)
    );

    // shrink the boot copy so the smoke test stays fast
    defparam u_top.u_weight_boot_fsm.BOOT_BYTES = 64;

    // INIT_ZERO: the shrunk boot copy only writes 64 bytes, but the tiling
    // FSM reads the full weight range; the real boot covers all of it
    sdram_model #(.INIT_ZERO(1)) u_model (
        .clk(clk), .cke(sdram_cke), .cs_n(sdram_cs_n),
        .ras_n(sdram_ras_n), .cas_n(sdram_cas_n), .we_n(sdram_we_n),
        .ba(sdram_ba), .a(sdram_a), .dq(sdram_dq)
    );

    int errors = 0;

    task automatic wb_write32(input [11:0] offset, input [31:0] data);
        int guard;
        guard = 0;
        wb_addr    = {20'h10004, offset};
        wb_dat_m2s = data;
        wb_sel     = 4'hF;
        wb_we      = 1;
        wb_cyc     = 1;
        wb_stb     = 1;
        @(posedge clk); #1;
        while (wb_ack !== 1'b1) begin
            @(posedge clk); #1;
            guard++;
            if (guard > 20) begin
                $display("FAIL: wishbone write to %h never acked", offset);
                errors++;
                break;
            end
        end
        wb_cyc = 0;
        wb_stb = 0;
        wb_we  = 0;
        @(posedge clk); #1;
    endtask

    task automatic wb_read32(input [11:0] offset, output [31:0] data);
        int guard;
        guard = 0;
        wb_addr = {20'h10004, offset};
        wb_we   = 0;
        wb_cyc  = 1;
        wb_stb  = 1;
        @(posedge clk); #1;
        while (wb_ack !== 1'b1) begin
            @(posedge clk); #1;
            guard++;
            if (guard > 20) begin
                $display("FAIL: wishbone read from %h never acked", offset);
                errors++;
                break;
            end
        end
        data   = wb_dat_s2m;
        wb_cyc = 0;
        wb_stb = 0;
        @(posedge clk); #1;
    endtask

    logic [31:0] rd;
    int guard;

    initial begin
        rst_n      = 0;
        wb_cyc     = 0;
        wb_stb     = 0;
        wb_we      = 0;
        wb_addr    = 0;
        wb_dat_m2s = 0;
        wb_sel     = 0;
        repeat (5) begin @(posedge clk); #1; end
        rst_n = 1;

        // --- boot: SDRAM init + weight copy ------------------------------
        guard = 0;
        rd    = 0;
        while (rd[3] !== 1'b1) begin // STATUS bit 3 = boot_done
            wb_read32(12'h004, rd);
            guard++;
            if (guard > 30000) begin
                $display("FAIL: boot_done never asserted (STATUS=%h)", rd);
                errors++;
                break;
            end
        end
        $display("boot done at %0t (STATUS=%h)", $time, rd);

        // --- write one input word, then start inference ------------------
        wb_write32(12'h008, 32'h7F017F01);
        wb_write32(12'h000, 32'h1);       // CTRL.start

        // busy should be visible while the tile loops run
        wb_read32(12'h004, rd);
        if (rd[1] !== 1'b1) begin
            $display("FAIL: STATUS.busy not set right after start (STATUS=%h)", rd);
            errors++;
        end

        // --- wait for done: layer 1 (16x98 tiles) + layer 2 (2x16), each
        // tile is an 8-burst SDRAM fill + 15-cycle compute (~330 cycles) ----
        guard = 0;
        rd    = 0;
        while (rd[0] !== 1'b1) begin // STATUS bit 0 = done
            wb_read32(12'h004, rd);
            guard++;
            if (guard > 400000) begin
                $display("FAIL: inference never reached DONE (STATUS=%h)", rd);
                errors++;
                break;
            end
        end
        $display("inference done at %0t after %0d status polls (STATUS=%h)", $time, guard, rd);
        if (rd[1] !== 1'b0) begin
            $display("FAIL: busy still set in DONE (STATUS=%h)", rd);
            errors++;
        end

        // --- logits readable at 0x318-0x33F (zero: datapath is stubbed) --
        for (int k = 0; k < 10; k++) begin
            wb_read32(12'h318 + 4 * k, rd);
            if (rd !== 32'h0) begin
                $display("FAIL: logit %0d = %h, expected 0 from stubbed datapath", k, rd);
                errors++;
            end
        end

        // --- cycle counter no longer shadows logits 8/9 ------------------
        wb_read32(12'h340, rd);
        if (rd == 32'h0) begin
            $display("FAIL: CYCLES_LO is zero after inference");
            errors++;
        end else
            $display("inference took %0d cycles", rd);

        // --- soft reset returns to IDLE ----------------------------------
        wb_write32(12'h000, 32'h2);       // CTRL.soft_reset
        wb_read32(12'h004, rd);
        if (rd[0] !== 1'b0) begin
            $display("FAIL: done still set after soft_reset (STATUS=%h)", rd);
            errors++;
        end

        errors += u_model.err_count;
        if (errors == 0)
            $display("TB_RESULT: PASS");
        else
            $display("TB_RESULT: FAIL (%0d errors)", errors);
        $finish;
    end

    // global timeout: 20 ms sim time
    initial begin
        #20000000;
        $display("TB_RESULT: FAIL (global timeout: system hung)");
        $finish;
    end

`ifdef SMOKE_DEBUG
    int dbg_lines = 0;
    always @(u_top.u_tiling_fsm.state) begin
        if (dbg_lines < 300) begin
            $display("DBG %0t tiling=%0d tile=%0d grp=%0d burst=%0d layer=%b ctrl=%0d sdram=%0d",
                     $time, u_top.u_tiling_fsm.state, u_top.u_tiling_fsm.tile_col,
                     u_top.u_tiling_fsm.neuron_row, u_top.u_tiling_fsm.burst_idx,
                     u_top.tiling_layer_sel, u_top.u_control_fsm.state,
                     u_top.u_sdram_controller.state);
            dbg_lines++;
        end
    end
`endif

endmodule
