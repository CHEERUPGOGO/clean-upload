# MCP-RecBench
> Benchmarking Tool-Using LLM Agents with Complex Real-World Recommendation Tasks via MCP Servers

---

### 1. Environment Setup
```bash
# Set up conda environment
conda activate <your_env>
source .env
```

### 2. Dataset Synthesis Pipeline

The universal pipeline generates evaluation tasks across 4 levels. Each level follows a 3-step flow:
1. **Synthesize** — Generate candidate tasks from data.
2. **Fuzzy** — Rewrite queries into natural, ambiguous user descriptions.
3. **Judge** — Filter with LLM-as-a-judge.

#### Level-1 (Single-Tool Tasks)
```bash
# Example for Amazon dataset
python synthesis_amazon/run_task_synthesis_L1.py --processed_dir data/amazon-electronics/processed --max_tasks 10 --scenario attribute
python synthesis_amazon/fuzzy_query_level1.py --tasks_file synthesis_amazon/mcpbench_tasks_level1_*_runner_format.json
python synthesis_amazon/llm_judge_level2.py --input_file synthesis_amazon/mcpbench_tasks_level1_*_runner_format_with_fuzzy.json
```

#### Level-2 (Multi-Tool, Cross-Server)
```bash
python synthesis_amazon/run_task_synthesis_L2_crossServer.py --processed_dir data/amazon-electronics/processed --max_tasks 100
python synthesis_amazon/fuzzy_query_level2.py --tasks_file <output.json>
python synthesis_amazon/llm_judge_level2.py --input_file <output_with_fuzzy.json>
```

#### Level-3 (Hierarchical Tool Chains)
```bash
python synthesis_amazon/run_task_synthesis_L3.py --processed_dir data/amazon-electronics/processed --max_tasks 500
python synthesis_amazon/fuzzy_query_level3.py --tasks_file <output.json>
python synthesis_amazon/llm_judge_level3.py --input_file <output_with_fuzzy.json>
```

#### Level-4 (Hybrid Complex Tasks)
```bash
python synthesis_amazon/run_task_synthesis_L4.py --processed_dir data/amazon-electronics/processed --max_tasks 100 --output_dir ./synthesis_amazon
python synthesis_amazon/fuzzy_query_level4.py --tasks_file <L4_output.json>
python synthesis_amazon/llm_judge_level4.py --input_file <L4_with_fuzzy.json> --min_hybrid 7
```
*(Similar synthesis scripts are available for `synthesis_yelp/` and `synthesis_foursquare/`)*

---

### 3. Running Benchmarks

Set your model API keys in the `.env` file before running the benchmarks. 
The scripts automatically detect the dataset from the path and switch MCP servers dynamically.

```bash
# L1 Benchmarking (Single-round evaluation)
bash bash_bash_L1.sh ./synthesized_tasks_amazon_test/level1 Qwen2.5-3B-Instruct

# L2 Benchmarking (Parallel multi-tool, multiple rounds, with distraction)
bash bash_bash_L2.sh ./synthesis_amazon/mcpbench_tasks_level2_cross_runner_format_with_fuzzy_quality_filtered.json Qwen2.5-3B-Instruct --rounds 5 --distraction 0

# L3 Benchmarking (Serial tool chains)
bash bash_bash_L3.sh ./synthesis_amazon/mcpbench_tasks_level3_cross_runner_format_with_fuzzy_quality_filtered.json Qwen2.5-3B-Instruct --rounds 6 --distraction 0
```

> **Note:** The `--distraction N` flag injects irrelevant MCP servers into the tool list. Higher `N` introduces more noise.

---

### 4. Evaluate Results

Compute the metrics based on the benchmark outputs:
```bash
# Evaluate L1 metrics
python evaluate_L1_metrics.py -i synthesized_tasks_amazon_test/level1_results_Qwen2.5-3B-Instruct/

# Evaluate L2 metrics
python evaluate_L2_metrics.py -i synthesized_tasks_amazon_test/level2_results_Qwen2.5-7B-Instruct/ --detail
```
