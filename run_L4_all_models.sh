#!/bin/bash
# =============================================================================
# Level-4 Benchmark Runner — All Models (Hybrid Complex Tasks)
# =============================================================================
# Runs L4 benchmarks sequentially for multiple models on a given dataset.
# Model names are anonymized for double-blind review.
#
# Usage:
#   ./run_L4_all_models.sh [--dataset <amazon|yelp|foursquare>] [other options]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Anonymized model list (for double-blind submission) ---
MODELS=(
    "Model-A"
    "Model-B"
    "Model-C"
    "Model-D"
    "Model-E"
)

# Default L4 task paths per dataset
AMAZON_TASKS="$SCRIPT_DIR/synthesis-l4-query/mcpbench_tasks_level4_hybrid_runner_format_with_fuzzy_quality_filtered.json"
YELP_TASKS="$SCRIPT_DIR/synthesis-query-yelp/mcpbench_tasks_level4_hybrid_runner_format_with_fuzzy_quality_filtered.json"
FOURSQUARE_TASKS="$SCRIPT_DIR/synthesis-query-foursquare/mcpbench_tasks_level4_hybrid_runner_format_with_fuzzy_quality_filtered.json"

DATASET="amazon"
MAX_ROUNDS=12
DISTRACTION_COUNT=3
EXTRA_ARGS=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dataset)
            DATASET="$2"
            shift 2
            ;;
        --rounds)
            MAX_ROUNDS="$2"
            shift 2
            ;;
        --distraction)
            DISTRACTION_COUNT="$2"
            shift 2
            ;;
        *)
            EXTRA_ARGS="$EXTRA_ARGS $1"
            shift
            ;;
    esac
done

# Select task file based on dataset
case "$DATASET" in
    amazon)     TASK_FILE="$AMAZON_TASKS" ;;
    yelp)       TASK_FILE="$YELP_TASKS" ;;
    foursquare) TASK_FILE="$FOURSQUARE_TASKS" ;;
    *)          echo "Error: unknown dataset '$DATASET'"; exit 1 ;;
esac

if [ ! -f "$TASK_FILE" ]; then
    echo "Error: task file not found: $TASK_FILE"
    exit 1
fi

echo "========================================"
echo " Level-4 All-Models Benchmark"
echo "========================================"
echo "  Dataset:      $DATASET"
echo "  Task file:    $TASK_FILE"
echo "  Models:       ${MODELS[*]}"
echo "  Max rounds:   $MAX_ROUNDS"
echo "  Distraction:  $DISTRACTION_COUNT servers"
echo "========================================"

for MODEL in "${MODELS[@]}"; do
    echo ""
    echo ">>> Running L4 benchmark for $MODEL ..."
    bash "$SCRIPT_DIR/bash_bash_L3.sh" "$TASK_FILE" "$MODEL" \
        --dataset "$DATASET" \
        --rounds "$MAX_ROUNDS" \
        --distraction "$DISTRACTION_COUNT" \
        $EXTRA_ARGS
done

echo ""
echo "========================================"
echo " All L4 benchmarks complete!"
echo "========================================"
