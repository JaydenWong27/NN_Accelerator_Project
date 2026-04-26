module sdram_model (
    input logic clk,
    input logic cke,
    input logic cs_n,
    input logic ras_n,
    input logic cas_n,
    input logic we_n,
    input logic [1:0] ba,
    input  logic [12:0] a,
    inout logic [15:0] dq
);

logic [15:0] mem [0:3][0:4095][0:255];
logic [12:0] active_row [0:3];

logic [15:0] dq_out;
logic        dq_oe;
logic        burst_running;
logic [1:0]  read_bank;
logic [7:0]  col_cnt;

assign dq = dq_oe ? dq_out : 16'hZZZZ;

always_ff @(posedge clk) begin
    dq_oe <= 0;

    // continue burst — auto-increment column
    if (burst_running) begin
        dq_out <= mem[read_bank][active_row[read_bank]][col_cnt];
        dq_oe  <= 1;
        col_cnt <= col_cnt + 1;
    end

    if (!cs_n) begin
        case ({ras_n, cas_n, we_n})
        3'b011: active_row[ba] <= a;              // ACTIVATE
        3'b101: begin                              // READ - start burst
            read_bank     <= ba;
            col_cnt       <= a[7:0] + 1;
            burst_running <= 1;
            dq_out        <= mem[ba][active_row[ba]][a[7:0]];
            dq_oe         <= 1;
        end
        3'b100: mem[ba][active_row[ba]][a[7:0]] <= dq;  // WRITE
        3'b010: burst_running <= 0;               // PRECHARGE - stop burst
        endcase
    end
end

endmodule

module tb_sdram;

logic clk,rst_n;
logic req_valid;
logic [23:0] req_byte_addr;
logic [7:0] req_burst_len;
logic req_ready;
logic [7:0] data_out;
logic data_valid;
logic burst_done;
logic wr_valid;
logic [23:0] wr_byte_addr;
logic [7:0] wr_data;
logic wr_ready;

logic sdram_cke, sdram_cs_n;
logic sdram_ras_n, sdram_cas_n, sdram_we_n;
logic [1:0] sdram_ba;
logic [12:0] sdram_a;
wire [15:0] sdram_dq;

sdram_controller dut (
    .clk(clk), .rst_n(rst_n),
    .req_valid(req_valid), .req_byte_addr(req_byte_addr),
    .req_burst_len(req_burst_len),.req_ready(req_ready),
    .data_out(data_out), .data_valid(data_valid), .burst_done(burst_done),
    .wr_valid(wr_valid), .wr_byte_addr(wr_byte_addr),
    .wr_data(wr_data), .wr_ready(wr_ready),
    .sdram_cke(sdram_cke), .sdram_cs_n(sdram_cs_n),
    .sdram_ras_n(sdram_ras_n), .sdram_cas_n(sdram_cas_n),
    .sdram_we_n(sdram_we_n), .sdram_ba(sdram_ba),
    .sdram_a(sdram_a), .sdram_dq(sdram_dq)
);

sdram_model ram (
    .clk(clk), .cke(sdram_cke), .cs_n(sdram_cs_n),
    .ras_n(sdram_ras_n), .cas_n(sdram_cas_n), .we_n(sdram_we_n),
    .ba(sdram_ba), .a(sdram_a), .dq(sdram_dq)
);

always #5 clk = ~clk;
initial begin
    clk = 0; rst_n =0;
    req_valid = 0; wr_valid = 0;

    //wait for reset, then wait for init sequence to finish
    @(posedge clk); #1;
    rst_n = 1;

    //wait for controller to finish init (~20,000+ cycles)
    wait (req_ready == 1);
    $display("PASS: init complete");

    //tests go here

    
    //write 0xAB to address 0x000000
    wr_valid = 1;
    wr_byte_addr = 24'h000000;
    wr_data = 8'hAB;
    fork
        begin
            wait (wr_ready == 1);
            $display("wr_ready received");
        end
        begin
            #500000;
            $display("TIMEOUT waiting for wr_ready");
            $finish;
        end
    join_any
    disable fork;
    @(posedge clk); #1;
    wr_valid = 0;

    fork
        wait (req_ready == 1);
        begin #500000; $display("TIMEOUT waiting for req_ready after write"); $finish; end
    join_any
    disable fork;
    $display("req_ready back");

    req_valid = 1;
    req_byte_addr = 24'h000000;
    req_burst_len = 8'd1;

    fork
        wait (req_ready == 0);
        begin #500000; $display("TIMEOUT waiting for req_ready to drop"); $finish; end
    join_any
    disable fork;
    req_valid = 0;

    fork
        wait (data_valid == 1);
        begin #500000; $display("TIMEOUT waiting for data_valid"); $finish; end
    join_any
    disable fork;
    @(posedge clk); #1;
    if (data_out !== 8'hAB)
        $display("FAIL test2: expected 0xAB got 0x%0h", data_out);
    else
        $display("PASS: write-read test");

    fork
        wait (burst_done == 1);
        begin #500000; $display("TIMEOUT waiting for burst_done"); $finish; end
    join_any
    disable fork;

    //write 4 bytes to consecutive addresses
    wr_valid = 1;
    wr_byte_addr = 24'h000010; wr_data = 8'h11;
    fork wait(wr_ready == 1); begin #500000; $display("TIMEOUT wr t3a"); $finish; end join_any disable fork;
    fork wait(wr_ready == 0); begin #500000; $display("TIMEOUT wr t3a drop"); $finish; end join_any disable fork;

    wr_byte_addr = 24'h000011; wr_data = 8'h22;
    fork wait(wr_ready==1); begin #500000; $display("TIMEOUT wr t3b"); $finish; end join_any disable fork;
    fork wait(wr_ready == 0); begin #500000; $display("TIMEOUT wr t3b drop"); $finish; end join_any disable fork;

    wr_byte_addr = 24'h000012; wr_data = 8'h33;
    fork wait(wr_ready == 1); begin #500000; $display("TIMEOUT wr t3c"); $finish; end join_any disable fork;
    fork wait(wr_ready == 0); begin #500000; $display("TIMEOUT wr t3c drop"); $finish; end join_any disable fork;

    wr_byte_addr = 24'h000013; wr_data = 8'h44;
    fork wait(wr_ready==1); begin #500000; $display("TIMEOUT wr t3d"); $finish; end join_any disable fork;
    @(posedge clk); #1;
    wr_valid = 0;

    fork wait(req_ready==1); begin #500000; $display("TIMEOUT t3 req_ready"); $finish; end join_any disable fork;

    req_valid = 1;
    req_byte_addr = 24'h000010;
    req_burst_len = 8'd4;
    fork wait(req_ready == 0); begin #500000; $display("TIMEOUT t3 req drop"); $finish; end join_any disable fork;
    req_valid = 0;

    // wait for burst to start, then sample one byte per clock
    fork wait(data_valid==1); begin #500000; $display("TIMEOUT t3 start"); $finish; end join_any disable fork;
    if (data_out !== 8'h11) $display("FAIL test3: byte 0 expected 0x11 got 0x%0h", data_out);

    @(posedge clk); #1;
    if (data_out !== 8'h22) $display("FAIL test3: byte 1 expected 0x22 got 0x%0h", data_out);

    @(posedge clk); #1;
    if (data_out !== 8'h33) $display("FAIL test3: byte 2 expected 0x33 got 0x%0h", data_out);

    @(posedge clk); #1;
    if (data_out !== 8'h44) $display("FAIL test3: byte 3 expected 0x44 got 0x%0h", data_out);
    fork wait(burst_done==1); begin #500000; $display("TIMEOUT t3 burst_done"); $finish; end join_any disable fork;
    $display("PASS: burst read test");

    fork wait(req_ready==1); begin #500000; $display("TIMEOUT t4 req_ready"); $finish; end join_any disable fork;

    req_valid = 1;
    req_byte_addr = 24'h000000; // original address with 0xAB
    req_burst_len = 8'd1;
    fork wait(req_ready==0); begin #500000; $display("TIMEOUT t4 req drop"); $finish; end join_any disable fork;
    req_valid = 0;

    fork wait(data_valid==1); begin #500000; $display("TIMEOUT t4 data"); $finish; end join_any disable fork;
    @(posedge clk); #1;
    if (data_out !== 8'hAB)
        $display("FAIL test4: expected 0xAB got 0x%0h", data_out);
    else
        $display("PASS: address isolation test");
    fork wait(burst_done==1); begin #500000; $display("TIMEOUT t4 burst"); $finish; end join_any disable fork;
    
    $finish;
end

endmodule