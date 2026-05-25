#!/bin/bash
# =============================================================================
# Level-2 Benchmark Runner
# =============================================================================
# Usage:
#   ./bash_bash_L2.sh <task_path> <model_name> [options]
#
# Auto-detects dataset (amazon/yelp/foursquare) from task path and switches
# MCP servers accordingly. Supports single JSON file or directory.
#
# Examples:
#   ./bash_bash_L2.sh ./synthesized_tasks/mcpbench_tasks_level2_cross_runner_format_with_fuzzy.json gpt-5
#   ./bash_bash_L2.sh ./synthesis_yelp Model-A --rounds 5 --distraction 3
#   ./bash_bash_L2.sh ./synthesis_foursquare Model-B --dataset foursquare
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    echo "Usage: $0 <task_path> <model_name> [options]"
    echo ""
    echo "Arguments:"
    echo "  task_path   JSON file or directory containing L2 task JSON files"
    echo "  model_name  Model name passed to run_benchmark.py"
    echo ""
    echo "Options:"
    echo "  --dataset <amazon|yelp|foursquare>  Force dataset (default: auto-detect from path)"
    echo "  --eval      Enable LLM judge evaluation (default: disabled)"
    echo "  --slim      Save only tool call traces (smaller output)"
    echo "  --rounds N  Override max execution rounds (default: 5)"
    echo "  --distraction N  Override distraction server count (default: 3)"
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

# Defaults for L2
MAX_ROUNDS=5
DISTRACTION_COUNT=3
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
        --rounds)
            MAX_ROUNDS="$2"
            shift 2
            ;;
        --distraction)
            DISTRACTION_COUNT="$2"
            shift 2
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

# Build output filename: L2_<dataset>_<model>_<timestamp>.json
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="benchmark_results/L2_${DATASET}_${MODEL_NAME}_${TIMESTAMP}.json"
mkdir -p benchmark_results

echo "========================================"
echo " Level-2 Benchmark"
echo "========================================"
echo "  Model:        $MODEL_NAME"
echo "  Tasks:        $TASK_DISPLAY"
echo "  Dataset:      $DATASET"
echo "  Max rounds:   $MAX_ROUNDS"
echo "  Distraction:  $DISTRACTION_COUNT servers"
echo "  Evaluation:   $([ -z "$SKIP_EVAL" ] && echo 'enabled' || echo 'disabled')"
echo "  Limit tasks:  ${LIMIT_TASKS:-all}"
echo "  Output:       $OUTPUT_FILE"
echo "========================================"

# Switch dataset
switch_dataset "$DATASET"

export BENCHMARK_EXECUTION_MAX_EXECUTION_ROUNDS="$MAX_ROUNDS"

python run_benchmark.py \
    --models "$MODEL_NAME" \
    $TASK_ARG \
    --distraction-count "$DISTRACTION_COUNT" \
    --output "$OUTPUT_FILE" \
    $SKIP_EVAL \
    $SLIM_OUTPUT \
    $LIMIT_TASKS

echo ""
echo "========================================"
echo " L2 Benchmark complete: $MODEL_NAME"
echo " Tasks: $TASK_DISPLAY"
echo " Output: $OUTPUT_FILE"
echo "========================================"
