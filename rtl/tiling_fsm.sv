module tiling_fsm (
    input logic clk,
    input logic rst_n,
    input logic tiling_start,
    input logic tiling_layer_sel,
    input logic fill_done,
    input logic signed [31:0] pe_acc_out [0:63],
    input logic signed [7:0] input_buf [0:783],
    input logic [23:0] layer1_requant_multiplier,
    input logic [7:0] layer1_requant_shift,
    output logic tiling_done,
    output logic pe_en,
    output logic pe_rst_acc,
    output logic swap_buffers,
    output logic sdram_req_valid,
    output logic [23:0] sdram_req_addr,
    output logic [7:0] sdram_req_len,
    output logic [5:0] weight_sel,
    output logic signed [7:0] activation_in [0:7],
    output logic signed [31:0] acc_out [0:127]
);

logic [6:0] tile_col;
logic [7:0] neuron_row;
logic [3:0] cycle_cnt;

// Load biases from hex files
logic signed [7:0] fc1_bias_data [0:127];
logic signed [7:0] fc2_bias_data [0:9];

initial begin
    $readmemh("weights/fc1_bias.hex", fc1_bias_data);
    $readmemh("weights/fc2_bias.hex", fc2_bias_data);
end

typedef enum logic [2:0] {
    IDLE,
    PREFETCH_TILE_0,
    COMPUTE,
    ACCUMULATE,
    SWAP_BUFFERS,
    FETCH_NEXT_TILE,
    RELU,
    DONE
} state_t;

state_t state;

always_ff @(posedge clk) begin
    if (!rst_n) begin
        state <= IDLE;
        tile_col <= 0;
        neuron_row <= 0;
        cycle_cnt <= 0;
        for (int i = 0; i < 128; i++) begin
            acc_out[i] <= 32'sd0;
        end
    end else begin
        case (state)
        IDLE: begin
            tile_col <= 0;
            neuron_row <= 0;
            cycle_cnt <= 0;
            if (tiling_start) state <= PREFETCH_TILE_0;
        end
        PREFETCH_TILE_0: begin
            if (fill_done) state <= COMPUTE;
        end
        COMPUTE: begin
            cycle_cnt <= cycle_cnt + 1;
            if (cycle_cnt == 14) begin
                cycle_cnt <= 0;
                state <= ACCUMULATE;
            end
        end
        ACCUMULATE: begin
            for (int i = 0; i < 8; i ++) begin
                for (int j = 0; j < 8; j ++) begin
                    acc_out[neuron_row + i] <= acc_out[neuron_row + i] + pe_acc_out[i*8 + j];
                end
            end
            state <= SWAP_BUFFERS;
        end
        SWAP_BUFFERS: begin
            tile_col <= tile_col + 1;
            if (tile_col == (tiling_layer_sel ? 15 : 97)) begin
                tile_col <= 0;
                state <= RELU;
            end else
                state <= FETCH_NEXT_TILE;
         end
        FETCH_NEXT_TILE: begin
            if (fill_done) state <= COMPUTE;
        end
        RELU: begin
            for( int i = 0; i < 8; i++) begin
                logic signed [31:0] biased;
                logic signed [31:0] relu_out;
                logic signed [63:0] requant_scaled;
                logic signed [31:0] requant_out;
                logic signed [31:0] clipped;

                if (tiling_layer_sel == 0) begin
                    biased = acc_out[neuron_row + i] + 32'(fc1_bias_data[neuron_row + i]);
                    relu_out = (biased < 0) ? 32'sd0 : biased;
                    // Multiply by requant_multiplier as 64-bit signed
                    requant_scaled = relu_out * 64'($signed(layer1_requant_multiplier));
                    // Round before shift
                    if (requant_scaled >= 0) begin
                        requant_scaled = requant_scaled + (1 << (layer1_requant_shift - 1));
                    end else begin
                        requant_scaled = requant_scaled - (1 << (layer1_requant_shift - 1));
                    end
                    // Arithmetic right shift
                    requant_out = requant_scaled >>> layer1_requant_shift;
                    // Clip to [-128, 127]
                    if (requant_out < -128) clipped = 32'(8'(-128));
                    else if (requant_out > 127) clipped = 32'(8'(127));
                    else clipped = requant_out;
                    acc_out[neuron_row + i] <= clipped;
                end else begin
                    biased = acc_out[neuron_row + i] + 32'(fc2_bias_data[neuron_row + i]);
                    acc_out[neuron_row + i] <= biased;
                end
            end
            neuron_row <= neuron_row + 8;
            if (neuron_row >= (tiling_layer_sel ? 8'd2 : 8'd120)) begin
                neuron_row <= 0;
                state <= DONE;
            end else begin
                state <= PREFETCH_TILE_0;
            end
        end
        DONE: begin
            state <= IDLE;
        end
        endcase
    end
end

always_comb begin
    tiling_done = (state == DONE);
    pe_en = (state == COMPUTE);
    pe_rst_acc = (state == IDLE);
    swap_buffers = (state== SWAP_BUFFERS);
    sdram_req_len = 8'd8;
    weight_sel = 6'(cycle_cnt);
    sdram_req_valid = (state == PREFETCH_TILE_0) || (state == FETCH_NEXT_TILE);
    sdram_req_addr = 24'(neuron_row * 784 + tile_col * 8);

    for (int i = 0; i < 8; i++) begin
        activation_in[i] = input_buf[tile_col * 8 + i];
    end
end
endmodule