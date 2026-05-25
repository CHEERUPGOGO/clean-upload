#!/bin/bash
# Example script for task synthesis

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Task Synthesis Examples${NC}"
echo -e "${BLUE}========================================${NC}"

# Set data directory
DATA_DIR="../../data/amazon-electronics/processed"

# Example 1: Template-based generation (no API key needed)
echo -e "\n${GREEN}Example 1: Template-based generation${NC}"
echo -e "${YELLOW}No API key required, fast and free${NC}\n"

python run_task_synthesis.py \
    --processed_dir "$DATA_DIR" \
    --max_tasks 20 \
    --scenario all \
    --llm_model template \
    --output_dir ./synthesized_tasks/template_based

# Example 2: Generate only semantic search tasks
echo -e "\n${GREEN}Example 2: Semantic search only${NC}\n"

python run_task_synthesis.py \
    --processed_dir "$DATA_DIR" \
    --max_tasks 30 \
    --scenario semantic \
    --llm_model template \
    --output_dir ./synthesized_tasks/semantic_only

# Example 3: Generate with OpenAI (if API key is set)
if [ -n "$OPENAI_API_KEY" ]; then
    echo -e "\n${GREEN}Example 3: Using LLM-based synthesis${NC}\n"
    
    python run_task_synthesis.py \
        --processed_dir "$DATA_DIR" \
        --max_tasks 10 \
        --scenario all \
        --llm_model Model-A \
        --output_dir ./synthesized_tasks/llm_based
else
    echo -e "\n${YELLOW}Skipping Example 3: OPENAI_API_KEY not set${NC}"
fi

# Example 4: Large batch generation
echo -e "\n${GREEN}Example 4: Large batch (100 tasks per scenario)${NC}\n"

python run_task_synthesis.py \
    --processed_dir "$DATA_DIR" \
    --max_tasks 100 \
    --scenario all \
    --llm_model template \
    --output_dir ./synthesized_tasks/large_batch

echo -e "\n${BLUE}========================================${NC}"
echo -e "${GREEN}All examples completed!${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "\nGenerated tasks are in: ./synthesized_tasks/"
echo -e "View tasks with: cat synthesized_tasks/*/mcp_retrieval_tasks.json | jq"
