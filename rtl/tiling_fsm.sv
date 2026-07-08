module tiling_fsm (
    input logic clk,
    input logic rst_n,
    input logic tiling_start,
    input logic tiling_layer_sel,
    input logic fill_done,
    input logic signed [31:0] pe_acc_out [0:63],
    input logic signed [7:0] input_buf [0:783],
    input logic signed [7:0] bias_in [0:7],
    output logic tiling_done,
    output logic pe_en,
    output logic pe_rst_acc,
    output logic fill_active,
    output logic sdram_req_valid,
    output logic [23:0] sdram_req_addr,
    output logic [7:0] sdram_req_len,
    output logic signed [7:0] activation_in [0:7],
    output logic signed [31:0] acc_out [0:127]
);

// weights_all.hex layout (see weights/export_weights.py), all input-major:
//   FC1 weights [784][128]  W[in][n] at in*128 + n
//   FC2 weights [128][10]   W[in][n] at L2_W_BASE + in*10 + n
//   FC1 biases  [128] INT8
//   FC2 biases  [10]  INT8
localparam int unsigned L2_W_BASE = 100352;
localparam int unsigned L1_B_BASE = 101632;
localparam int unsigned L2_B_BASE = 101760;

// layer-1 INT32 -> INT8 requantisation constants (weights/scale_factors.json)
localparam logic [11:0] REQUANT_MULT  = 12'd2810;
localparam int unsigned REQUANT_SHIFT = 24;
localparam logic [45:0] RQ_ROUND      = 46'd1 << (REQUANT_SHIFT - 1);

logic [6:0] tile_col;    // tile index along the input dim: L1 0..97, L2 0..15
logic [7:0] neuron_row;  // first neuron of the active group: L1 0..120, L2 0/8
logic [3:0] cycle_cnt;   // compute wavefront counter, 0..14
logic [2:0] burst_idx;   // 8 strided bursts of 8 bytes fill one 64-weight tile
logic [2:0] req_cnt;     // requantise: one neuron per cycle
logic fill_done_q;       // burst_done is held for several cycles; edge-detect

// layer-1 activations after ReLU + requantise, consumed by layer 2
logic signed [7:0] hidden [0:127];

typedef enum logic [3:0] {
    IDLE,
    FETCH_TILE,   // 8 strided bursts load W[in_base+b][n_base..n_base+7]
    COMPUTE,      // 1-cycle activation pulse rides the 15-cycle wavefront
    ACCUMULATE,   // fold each PE column into acc_out[n_base+j]
    ADVANCE_TILE, // next tile, or all tiles done -> fetch this group's bias
    FETCH_BIAS,   // one 8-byte burst of INT8 biases into cache slots 0..7
    ADD_BIAS,
    REQUANT,      // layer 1 only: ReLU + requantise into hidden[]
    DONE
} state_t;

state_t state;

logic fill_burst_done;
assign fill_burst_done = fill_done && !fill_done_q;

// ReLU + requantise of the neuron currently indexed by req_cnt.
// Post-ReLU values are non-negative, so the golden model's symmetric
// rounding reduces to adding +2^(shift-1).
logic signed [31:0] rq_v;
logic [30:0] rq_relu;
logic [45:0] rq_scaled;
logic [21:0] rq_shifted;
logic signed [7:0] rq_q;

always_comb begin
    rq_v       = acc_out[neuron_row + req_cnt];
    rq_relu    = rq_v[31] ? 31'd0 : rq_v[30:0];
    rq_scaled  = {15'b0, rq_relu} * REQUANT_MULT + RQ_ROUND;
    rq_shifted = rq_scaled[45:REQUANT_SHIFT];
    rq_q       = (rq_shifted > 22'd127) ? 8'sd127 : {1'b0, rq_shifted[6:0]};
end

always_ff @(posedge clk) begin
    if (!rst_n) begin
        state       <= IDLE;
        tile_col    <= 0;
        neuron_row  <= 0;
        cycle_cnt   <= 0;
        burst_idx   <= 0;
        req_cnt     <= 0;
        fill_done_q <= 0;
        for (int i = 0; i < 128; i++) begin
            acc_out[i] <= 32'sd0;
            hidden[i]  <= 8'sd0;
        end
    end else begin
        fill_done_q <= fill_done;
        case (state)
        IDLE: begin
            tile_col   <= 0;
            neuron_row <= 0;
            cycle_cnt  <= 0;
            burst_idx  <= 0;
            req_cnt    <= 0;
            if (tiling_start) begin
                // fresh accumulators for this layer; results of the previous
                // run stay readable until the next start. hidden[] is kept:
                // layer 2 consumes what layer 1 wrote.
                for (int i = 0; i < 128; i++) begin
                    acc_out[i] <= 32'sd0;
                end
                state <= FETCH_TILE;
            end
        end
        FETCH_TILE: begin
            if (fill_burst_done) begin
                if (burst_idx == 3'd7) begin
                    burst_idx <= 0;
                    state     <= COMPUTE;
                end else
                    burst_idx <= burst_idx + 1;
            end
        end
        COMPUTE: begin
            cycle_cnt <= cycle_cnt + 1;
            if (cycle_cnt == 4'd14) begin
                cycle_cnt <= 0;
                state     <= ACCUMULATE;
            end
        end
        ACCUMULATE: begin
            // neuron j of this group gets the column-j sum: the tile's
            // contribution sum_i a[in_base+i] * W[in_base+i][n_base+j]
            for (int j = 0; j < 8; j++) begin
                acc_out[neuron_row + j] <= acc_out[neuron_row + j]
                    + pe_acc_out[0*8 + j] + pe_acc_out[1*8 + j]
                    + pe_acc_out[2*8 + j] + pe_acc_out[3*8 + j]
                    + pe_acc_out[4*8 + j] + pe_acc_out[5*8 + j]
                    + pe_acc_out[6*8 + j] + pe_acc_out[7*8 + j];
            end
            state <= ADVANCE_TILE;
        end
        ADVANCE_TILE: begin
            if (tile_col == (tiling_layer_sel ? 7'd15 : 7'd97)) begin
                tile_col <= 0;
                state    <= FETCH_BIAS;
            end else begin
                tile_col <= tile_col + 1;
                state    <= FETCH_TILE;
            end
        end
        FETCH_BIAS: begin
            if (fill_burst_done) state <= ADD_BIAS;
        end
        ADD_BIAS: begin
            for (int j = 0; j < 8; j++) begin
                acc_out[neuron_row + j] <= acc_out[neuron_row + j] + bias_in[j];
            end
            if (tiling_layer_sel) begin
                // layer 2: acc_out[0..9] are now the INT32 logits
                if (neuron_row >= 8'd8) state <= DONE;
                else begin
                    neuron_row <= neuron_row + 8;
                    state      <= FETCH_TILE;
                end
            end else begin
                req_cnt <= 0;
                state   <= REQUANT;
            end
        end
        REQUANT: begin
            hidden[neuron_row + req_cnt] <= rq_q;
            req_cnt <= req_cnt + 1;
            if (req_cnt == 3'd7) begin
                req_cnt <= 0;
                if (neuron_row >= 8'd120) state <= DONE;
                else begin
                    neuron_row <= neuron_row + 8;
                    state      <= FETCH_TILE;
                end
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
    pe_en       = (state == COMPUTE);
    // the array only needs live registers while computing and while its
    // accumulators are being read; holding it in synchronous reset the rest
    // of the time also flushes the skew pipeline between tiles
    pe_rst_acc  = !(state == COMPUTE || state == ACCUMULATE);
    fill_active = (state == FETCH_TILE) || (state == FETCH_BIAS);

    sdram_req_valid = fill_active;
    sdram_req_len   = 8'd8;
    if (state == FETCH_BIAS)
        sdram_req_addr = (tiling_layer_sel ? L2_B_BASE : L1_B_BASE) + neuron_row;
    else if (tiling_layer_sel)
        sdram_req_addr = L2_W_BASE + (tile_col * 8 + burst_idx) * 10 + neuron_row;
    else
        sdram_req_addr = (tile_col * 8 + burst_idx) * 128 + neuron_row;

    // one-cycle activation pulse on the first compute cycle; the input skew
    // registers stagger it so PE[i][j] sees a[in_base+i] at cycle i+j
    for (int i = 0; i < 8; i++) begin
        if (state == COMPUTE && cycle_cnt == 0) begin
            if (tiling_layer_sel)
                activation_in[i] = hidden[tile_col * 8 + i];
            else
                activation_in[i] = input_buf[tile_col * 8 + i];
        end else
            activation_in[i] = 8'sd0;
    end
end

endmodule
