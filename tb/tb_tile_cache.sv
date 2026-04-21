module tb_tile_cache;

logic clk;
logic rst_n;
logic wr_en;
logic [5:0] wr_addr;
logic signed [7:0] wr_data;
logic signed [7:0] weight_out [0:63];

weight_tile_cache cache_inst(
    .clk(clk),
    .rst_n(rst_n),
    .wr_en(wr_en),
    .wr_addr(wr_addr),
    .wr_data(wr_data),
    .weight_out(weight_out)
);

always #5 clk = ~clk;

initial begin
    clk = 0;
    rst_n = 0;
    wr_en = 0;
    wr_addr = 0;
    wr_data = 0;

    @(posedge clk); #1; @(posedge clk); #1;
    rst_n = 1;
    @(posedge clk); #1;
    for(int i = 0; i < 64; i+=1) begin
        if (weight_out[i] !== 8'sd0)
            $display("FAIL reset: slot %0d = %0d", i, weight_out[i]);
    end

    $display("PASS: reset test");

    wr_addr = 5;
    wr_data = 42;
    wr_en = 1;
    @(posedge clk); #1;

    wr_en = 0;
    if (weight_out[5] !== 8'sd42)
        $display("FAIL: expected 42 got %0d", weight_out[5]);
    else
        $display("PASS");

    for(int i = 0; i < 64; i+=1) begin
        wr_addr = i;
        wr_data = i;
        wr_en = 1;
        @(posedge clk); #1;
    end
    wr_en = 0;
    @(posedge clk); #1;

    for(int i = 0; i < 64; i+=1)begin
        if (weight_out[i] !== 8'(i)) 
            $display("FAIL test3: slot %0d", i);
    end
    $display("PASS");

    wr_addr = 10;
    wr_data = 99;
    wr_en = 1;
    @(posedge clk); #1;

    wr_en = 0;
    wr_data = 55;
    wr_addr = 10;

    @(posedge clk); #1;

    if(weight_out[10] !== 8'sd99)
        $display("FAIL test4:expect4ed 99 got %0d", weight_out[10] );
    else
        $display("PASS: test4");
    $finish;

end


endmodule