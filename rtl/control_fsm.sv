module control_fsm (
    input logic clk,
    input logic rst_n, 
    input logic start,
    input logic soft_reset,
    input logic tiling_done,
    output logic done,
    output logic busy,
    output logic error,
    output logic [47:0] cycle_count,
    output logic tiling_start,
    output logic tiling_layer_sel,
    output logic relu_en
);

typedef enum logic [2:0] {
    IDLE,
    LOAD_INPUT,
    LAYER1_COMPUTE,
    LAYER1_RELU,
    LAYER2_COMPUTE,
    DONE
} state_t;

state_t state;

always_ff @(posedge clk) begin
    if (!rst_n) begin
        state <= IDLE;
        cycle_count <= 48'h0;
    end else begin
        case(state)
            IDLE: begin
                cycle_count <= 48'h0;
                if(start) state <= LOAD_INPUT;
            end
            LOAD_INPUT: begin
                cycle_count <= cycle_count + 1;
                state <= LAYER1_COMPUTE;
            end
            LAYER1_COMPUTE: begin
                cycle_count <= cycle_count + 1;
                if (tiling_done) state <= LAYER1_RELU;
            end
            LAYER1_RELU: begin
                cycle_count <= cycle_count + 1;
                state <= LAYER2_COMPUTE;
            end
            LAYER2_COMPUTE: begin
                cycle_count <= cycle_count + 1;
                if (tiling_done) state <= DONE;
            end
            DONE: begin
                if (soft_reset) state <= IDLE;
            end
        endcase
    end
end

always_comb begin
    done = 0;
    busy = 0;
    tiling_start = 0;
    tiling_layer_sel = 0;
    relu_en = 0;
    error = 0;
    case(state)
    IDLE:begin
        busy = 0;
    end
    LOAD_INPUT: begin
        busy = 1;

    end
    LAYER1_COMPUTE:begin
        tiling_start = 1;
        tiling_layer_sel = 0;
        busy = 1;
    end
    LAYER1_RELU:begin
        relu_en = 1;
        busy = 1;
    end
    LAYER2_COMPUTE:begin
        tiling_layer_sel = 1;
        busy = 1;
    end
    DONE:begin 
        done = 1;
        busy = 0;
    end
    endcase
end
endmodule