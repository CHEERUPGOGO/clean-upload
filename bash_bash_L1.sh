#!/bin/bash
# =============================================================================
# Level-1 Benchmark Runner
# =============================================================================
# Usage:
#   ./bash_bash_L1.sh <task_path> <model_name> [options]
#
# Auto-detects dataset (amazon/yelp/foursquare) from task path and switches
# MCP servers accordingly. Supports single JSON file or directory.
#
# Examples:
#   ./bash_bash_L1.sh ./synthesized_tasks gpt-4.1
#   ./bash_bash_L1.sh ./synthesis_yelp/some_level1_tasks.json Qwen2.5-7B-Instruct
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    echo "Usage: $0 <task_path> <model_name> [options]"
    echo ""
    echo "Arguments:"
    echo "  task_path   JSON file or directory containing L1 task JSON files"
    echo "  model_name  Model name passed to run_benchmark.py"
    echo ""
    echo "Options:"
    echo "  --dataset <amazon|yelp|foursquare>  Force dataset (default: auto-detect from path)"
    echo "  --eval      Enable LLM judge evaluation (default: disabled)"
    echo "  --slim      Save only tool call traces (smaller output)"
    echo "  --limit N   Only run first N tasks (useful for debugging)"
    echo "  -h, --help  Show this help"
    exit 1
}

# --- Auto-detect dataset from path ---
detect_dataset() {
    local path="$1"
    if echo "$path" | grep -qi "yelp"; then
        echo "yelp"
    elif echo "$path" | grep -qi "foursquare"; then
        echo "foursquare"
    else
        echo "amazon"
    fi
}

# --- Switch dataset (commands.json, examples.py, schema) ---
switch_dataset() {
    local ds="$1"
    local current_commands
    current_commands=$(cat "$SCRIPT_DIR/mcp_servers/commands.json" 2>/dev/null || echo "")

    local target_commands="$SCRIPT_DIR/mcp_servers/commands-${ds}.json"
    if [ ! -f "$target_commands" ]; then
        echo "Warning: $target_commands not found, skipping dataset switch"
        return
    fi

    # Only switch if needed
    local target_content
    target_content=$(cat "$target_commands")
    if [ "$current_commands" = "$target_content" ]; then
        echo "  Dataset already set to: $ds"
        return
    fi

    echo "  Switching to dataset: $ds"
    bash "$SCRIPT_DIR/switch_to_${ds}.sh"
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
fi

if [ $# -lt 2 ]; then
    echo "Error: at least 2 arguments required (task_path model_name)"
    usage
fi

TARGET_PATH="$1"
MODEL_NAME="$2"
shift 2

DATASET=""
SKIP_EVAL="--skip-evaluation"
SLIM_OUTPUT=""
LIMIT_TASKS=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dataset)
            DATASET="$2"
            shift 2
            ;;
        --eval)
            SKIP_EVAL=""
            shift
            ;;
        --slim)
            SLIM_OUTPUT="--slim-output"
            shift
            ;;
        --limit)
            LIMIT_TASKS="--limit-tasks $2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

# Auto-detect dataset if not specified
if [ -z "$DATASET" ]; then
    DATASET=$(detect_dataset "$TARGET_PATH")
fi

# Detect file vs directory
if [ -f "$TARGET_PATH" ]; then
    TASK_ARG="--tasks-file $TARGET_PATH"
    TASK_DISPLAY="$TARGET_PATH (file)"
elif [ -d "$TARGET_PATH" ]; then
    TASK_ARG="--tasks-dir $TARGET_PATH"
    TASK_DISPLAY="$TARGET_PATH (directory)"
else
    echo "Error: '$TARGET_PATH' is not a valid file or directory."
    exit 1
fi

# Build output filename: L1_<dataset>_<model>_<timestamp>.json
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="benchmark_results/L1_${DATASET}_${MODEL_NAME}_${TIMESTAMP}.json"
mkdir -p benchmark_results

echo "========================================"
echo " Level-1 Benchmark"
echo "========================================"
echo "  Model:        $MODEL_NAME"
echo "  Tasks:        $TASK_DISPLAY"
echo "  Dataset:      $DATASET"
echo "  Evaluation:   $([ -z "$SKIP_EVAL" ] && echo 'enabled' || echo 'disabled')"
echo "  Output:       $OUTPUT_FILE"
echo "========================================"

# Switch dataset
switch_dataset "$DATASET"

export BENCHMARK_EXECUTION_MAX_EXECUTION_ROUNDS=1

python run_benchmark.py \
    --models "$MODEL_NAME" \
    $TASK_ARG \
    --single-round \
    --distraction-count 0 \
    --output "$OUTPUT_FILE" \
    $SKIP_EVAL \
    $SLIM_OUTPUT \
    $LIMIT_TASKS

echo ""
echo "========================================"
echo " L1 Benchmark complete: $MODEL_NAME"
echo " Tasks: $TASK_DISPLAY"
echo " Output: $OUTPUT_FILE"
echo "========================================"
