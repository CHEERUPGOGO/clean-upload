# MCP-RecBench
> Benchmarking Tool-Using LLM Agents with Complex Real-World Recommendation Tasks via MCP Servers

---

### 1. Environment Setup
```bash
# Set up conda environment
conda activate <your_env>
```

### 2. Data Preparation

**Download raw data:**

**Amazon Electronics**
```bash
wget https://mcauleylab.ucsd.edu/public_datasets/data/amazon_v2/metaFiles2/meta_Electronics.json.gz
wget https://mcauleylab.ucsd.edu/public_datasets/data/amazon_v2/categoryFilesSmall/Electronics_5.json.gz
gzip -d *.json.gz
```

**Yelp 2019 Dataset**
Get from: https://business.yelp.com/data/resources/open-dataset/

**Foursquare NYC**
Get from: https://sites.google.com/site/yangdingqi/home/foursquare-dataset

**Preprocess:**

**Amazon Electronics**
```bash
python ./preprocess_scripts/amazon_electronics_preprocess.py \
  --input_dir ./data/amazon-electronics \
  --review_file Electronics_5.json \
  --meta_file meta_Electronics.jsonl \
  --k 10 \
  --min_rating 3.0
```
- user_sequences.jsonl: 58442 users
- item_meta.jsonl: 59925 items

**Yelp 2019 Dataset**
```bash
python ./preprocess_scripts/yelp_preprocess.py \
  --input_dir ./data/yelp 
```

**Foursquare NYC Dataset**
```bash
python ./preprocess_scripts/preprocess_foursquare.py
```

### 3. MCP Server Setup

#### 4.1 Retrieval Tasks

```bash
# Amazon Electronics → data/amazon-electronics/products.db
python mcp_servers/retrieval-mcp-server/load_amazon_data.py \
  --meta_file data/amazon-electronics/processed/item_meta.jsonl

# Yelp → data/yelp/yelp.db
python mcp_servers/retrieval-mcp-yelp-server/load_yelp_data.py \
  --meta_file data/yelp/processed/item_meta.jsonl

# Yelp BPR training
python mcp_servers/retrieval-mcp-yelp-server/bpr_trainer.py \
  --user_sequences_path data/yelp/processed/user_sequences.jsonl
```

#### 4.2 NLP Tasks

Generate sentiment, opinion, and summary data from item reviews using rule-based extraction (no LLM/GPU required, full coverage):

```bash
# Amazon Electronics
python preprocess_scripts/generate_nlp_data.py \
  --meta_dir data/amazon-electronics/processed \
  --data_dir data/amazon-electronics/processed

# Yelp
python preprocess_scripts/generate_nlp_data.py \
  --meta_dir data/yelp/processed \
  --data_dir data/yelp \
  --id_field business_id \
  --name_field name \
  --reviews_field text

```

#### 4.3 Recommendation Tasks

```bash
python mcp_servers/rec-mcp-yelp/train_sasrec.py
```

#### 4.4 Google Map API

Set API key in `mcp_servers/googlemap-mcp/server.py`

### 5. Dataset Synthesis Pipeline

**Universal Pipeline (all levels): `Synthesize → Fuzzy → LLM-As-A-Judge`**

Each level follows the same 3-step flow:
1. **Synthesize** — generate candidate tasks from data
2. **Fuzzy** — rewrite queries into natural, ambiguous user descriptions
3. **Judge** — filter with LLM-as-a-judge (eval_server API, kimi-k2-instruct-0905-local)

#### 5.1 Level Overview

| Level | Description | Synthesis Script |
|-------|-------------|------------------|
| L1 | Single-tool task | `run_task_synthesis_L1.py --scenario <name>` |
| L2 | Multi-tool, single/cross server | `run_task_synthesis_L2_crossServer.py` |
| L3 | Hierarchical tool chains | `run_task_synthesis_L3.py` |

---

#### 5.2 Level-1 (Single-Tool Tasks)

**Available scenarios:**

<details><summary><b>Amazon</b> (13 scenarios)</summary>

`attribute` · `keyword` · `item2item` · `websearch` · `nlp_sentiment` · `nlp_opinion` · `nlp_summary` · `rec_rank` · `rating_filter` · `rating_count` · `top_rated` · `most_reviewed` · `compare_ratings`

</details>

<details><summary><b>Yelp</b> (17 scenarios)</summary>

`get_business_details` · `search_business` · `filter_businesses` · `recall_similar_items` · `nlp_opinion` · `nlp_sentiment` · `nlp_summary` · `compare_ratings` · `rating_count` · `rating_filter` · `top_rated` · `most_reviewed` · `rank_items` · `get_user_history` · `google_geo` · `google_regeo` · `google_distance`

</details>

<details><summary><b>Foursquare</b> (8 scenarios)</summary>

`get_poi_details` · `search_pois` · `filter_pois` · `rank_items` · `get_user_history` · `google_geo` · `google_regeo` · `google_distance`

</details>

**Full pipeline — Amazon:**

```bash
# Step1: Preprocess NLP data (first time only)
python preprocess_scripts/generate_nlp_data.py \
  --meta_dir data/amazon-electronics/processed \
  --data_dir data/amazon-electronics/processed

# Step2: Synthesize
python synthesis_amazon/run_task_synthesis_L1.py \
  --processed_dir data/amazon-electronics/processed \
  --max_tasks 10 --scenario attribute

# Step3: Fuzzy
python synthesis_amazon/fuzzy_query_level1.py \
  --tasks_file synthesis_amazon/mcpbench_tasks_level1_*_runner_format.json

# Step4: Judge
python synthesis_amazon/llm_judge_level2.py \
  --input_file synthesis_amazon/mcpbench_tasks_level1_*_runner_format_with_fuzzy.json
```

**Full pipeline — Yelp:**

```bash
# Step1: Preprocess NLP data (first time only)
python preprocess_scripts/generate_nlp_data.py \
  --meta_dir data/yelp/processed \
  --data_dir data/yelp 

# Step2: Synthesize
python synthesis_yelp/run_task_synthesis_L1.py \
  --processed_dir data/yelp/ \
  --max_tasks 10 --scenario search_business

# Step3-4: Fuzzy & Judge (same pattern as Amazon, use synthesis_yelp/)
```

**Full pipeline — Foursquare:**

```bash
# Step2: Synthesize (no NLP preprocess needed for Foursquare)
python synthesis_foursquare/run_task_synthesis_L1.py \
  --processed_dir data/foursquare/ \
  --max_tasks 10 --scenario search_pois

# Step3-4: Fuzzy & Judge (same pattern, use synthesis_foursquare/)
```

---

#### 5.3 Level-2 (Multi-Tool, Cross-Server)

**Amazon:**

```bash
# Synthesize
python synthesis_amazon/run_task_synthesis_L2_crossServer.py \
  --processed_dir data/amazon-electronics/processed --max_tasks 100
# Fuzzy → Judge
# Fuzzy query generation now supports ambiguity levels (low 40%, moderate 40%, high 20%)
# and 5 ambiguity types: UNDERSPECIFICATION, SOFT_CONTRADICTION, VAGUE_QUANTIFIERS,
# PREFERENCE_UNCERTAINTY, IMPLICIT_CONSTRAINTS
python synthesis_amazon/fuzzy_query_level2.py --tasks_file <output.json> \
  [--ambiguity_level {low,moderate,high}]  # optional: force specific level
# Judge now checks parallel independence AND ambiguity reasonableness
# Output JSON includes: ambiguity_level, ambiguity_types, quality_scores (S/U/P/A)
python synthesis_amazon/llm_judge_level2.py --input_file <output_with_fuzzy.json> \
  [--min_ambiguity_reasonableness 4]  # default: 4
```

**Key improvements (2026-05-01):**
- ✅ Fuzzy query generation with **5 real-world ambiguity types** + **3 levels** (low/moderate/high)
- ✅ Saves `ambiguity_level`, `ambiguity_types` in output JSON
- ✅ Preserves original explicit `task_description` and tool chain GT
- ✅ Judge now evaluates **ambiguity reasonableness** (4th dimension)
**Yelp:**

```bash
# Synthesize
python synthesis_yelp/run_task_synthesis_L2_for_yelp_crossServer.py \
  --processed_dir data/yelp/processed --max_tasks 1000
# Fuzzy → Judge
python synthesis_yelp/fuzzy_query_level2.py --tasks_file <output.json>
python synthesis_yelp/llm_judge_level2.py --input_file <output_with_fuzzy.json>
```

**Foursquare:**

```bash
# Synthesize
python synthesis_foursquare/run_task_synthesis_L2_for_foursquare_crossServer.py \
  --processed_dir data/foursquare/ --max_tasks 100
# Fuzzy → Judge
python synthesis_foursquare/fuzzy_query_level2.py --tasks_file <output.json>
python synthesis_foursquare/llm_judge_level2.py --input_file <output_with_fuzzy.json>
```

---

#### 5.4 Level-3 (Hierarchical Tool Chains)

**Amazon:**

```bash
# Synthesize
python synthesis_amazon/run_task_synthesis_L3.py \
  --processed_dir data/amazon-electronics/processed --max_tasks 500
# Fuzzy → Judge (sequential)
python synthesis_amazon/fuzzy_query_level3.py --tasks_file <output.json>
python synthesis_amazon/llm_judge_level3.py --input_file <output_with_fuzzy.json>
```

**Yelp:**

```bash
# Synthesize
python synthesis_yelp/run_task_synthesis_L3_for_yelp.py \
  --processed_dir data/yelp/processed --max_tasks 500
# Fuzzy → Judge (sequential)
python synthesis_yelp/fuzzy_query_level3.py --tasks_file <output.json>
python synthesis_yelp/llm_judge_level3.py --input_file <output_with_fuzzy.json>
```

**Foursquare:**

```bash
# Synthesize
python synthesis_foursquare/run_task_synthesis_L3_for_foursquare.py \
  --processed_dir data/foursquare/ --max_tasks 100
# Fuzzy → Judge (sequential)
python synthesis_foursquare/fuzzy_query_level3.py --tasks_file <output.json>
python synthesis_foursquare/llm_judge_level3.py --input_file <output_with_fuzzy.json>
```

```bash
python synthesis_amazon/run_task_synthesis_L4.py \
    --processed_dir data/amazon-electronics/processed \
    --max_tasks 100 \
    --output_dir ./synthesis_amazon

python synthesis_amazon/fuzzy_query_level4.py --tasks_file <L4_output.json>

python synthesis_amazon/llm_judge_level4.py --input_file <L4_with_fuzzy.json> --min_hybrid 7
```

---
## Leaderboard

| Rank | Model | Overall Score |
|:----:|-------|:-------------:|
| 1 | GPT-5 | - |


> **Note:** Overall Score represents the average performance across all evaluation dimensions including rule-based schema understanding, LLM-judged (o4-mini as judge model) task completion, tool usage, and planning effectiveness. Scores are averaged across single-server and multi-server settings.

---

## Running Benchmarks

### Basic Usage

```bash
source .env
```

Update the startup commands for each MCP server in `mcp_servers/commands.json`.
Run `python utils/collect_mcp_info.py` to verify that all MCP servers can connect successfully.
Make sure MCP servers are running before starting the benchmark.

> **Note:** Update the model path in `./llm/factory.py` to match your actual model location:
> ```python
> configs["qwen2.5-3b-local"] = ModelConfig(
>     name="qwen2.5-3b-local",
>     provider_type="openai_compatible",
>     api_key=local_vllm_api_key,
>     base_url="http://localhost:8002/v1",
>     model_name="<your_model_path>/Qwen2.5-3B-Instruct",
>     max_context_length=32768
> )
> ```
> Adjust parameters such as `round` and `max_tokens` in `config/benchmark_config.yaml` as needed.

### Batch Testing

Scripts auto-detect dataset from path and switch MCP servers. No manual `switch_to_*.sh` needed.

```bash
# Set API keys
export OPENAI_API_KEY="sk-xxx"
export GEMINI_API_KEY="your-key"
export OPENROUTER_API_KEY=""
# List available models
python run_benchmark.py --list-models

# L1 (single tool, single round — auto adds --single-round)
bash bash_bash_L1.sh ./synthesized_tasks_amazon_test/level1 Qwen2.5-3B-Instruct
bash bash_bash_L1.sh ./synthesized_tasks_yelp_test/level1 Qwen2.5-7B-Instruct
bash bash_bash_L1.sh ./synthesized_tasks_foursquare_test/level1 openai-gpt-5

# L2 (parallel multi-tool, default 5 rounds)
bash bash_bash_L2.sh ./synthesis_yelp/mcpbench_tasks_level2_cross_runner_format_with_fuzzy_quality_filtered.json Qwen2.5-3B-Instruct --rounds 5 --distraction 0

bash bash_bash_L2.sh ./synthesis_amazon/mcpbench_tasks_level2_cross_runner_format_with_fuzzy_quality_filtered.json Qwen2.5-3B-Instruct --rounds 1 --distraction 0 --limit 1
bash bash_bash_L2.sh ./synthesis_amazon/mcpbench_tasks_level2_cross_runner_format_with_fuzzy_quality_filtered.json gemini-gemini-2.5-flash --rounds 1 --distraction 0


gemma-4-31b-it-free	/ nemotron-3-nano-30b-free	/ minimax-m2.5-free / openai/gpt-oss-120b:free / meta-llama/llama-3.3-70b-instruct:free
bash bash_bash_L2.sh ./synthesis_amazon/mcpbench_tasks_level2_cross_runner_format_with_fuzzy_quality_filtered.json gemma-4-31b-it-free --rounds 1 --distraction 0


# L3 (serial tool chains, default 10 rounds)
bash bash_bash_L3.sh ./synthesis_amazon/mcpbench_tasks_level3_cross_runner_format_with_fuzzy_quality_filtered.json Qwen2.5-3B-Instruct openai-gpt-5 --rounds 6 --distraction 0 --limit 1

bash bash_bash_L3.sh ./synthesis_amazon/mcpbench_tasks_level3_cross_runner_format_with_fuzzy_quality_filtered.json Qwen2.5-3B-Instruct --rounds 6 --distraction 0

bash bash_bash_L3.sh ./synthesis_amazon/mcpbench_tasks_level3_cross_runner_format_with_fuzzy_quality_filtered.json gpt-oss-120b-free --rounds 6 --distraction 0 

```

> **Distraction** (`--distraction N`): Extra irrelevant MCP servers injected into the tool list. Higher N = more noise, harder tool selection. Default: 3.

### Evaluate Results

```bash
python evaluate_L1_metrics.py -i synthesized_tasks_amazon_test/level1_results_Qwen2.5-3B-Instruct/

python evaluate_L2_metrics.py -i synthesized_tasks_amazon_test/level2_results_Qwen2.5-7B-Instruct/ --detail

```

## Synthesized Task Data Inventory

| Level | Dataset | Path | Tasks |
|-------|---------|------|:-----:|
| L1 | Amazon | `synthesized_tasks_amazon_test/level1/` | 9 files |
| L1 | Yelp | `synthesized_tasks_yelp_test/level1/` | 10 files |
| L1 | Foursquare | `synthesized_tasks_foursquare_test/level1/` | 7 files |
| L2 | Amazon cross | `synthesis_amazon/mcpbench_tasks_level2_cross_runner_format_with_fuzzy_quality_filtered.json` |   
| L2 | Yelp cross | `synthesis_yelp/mcpbench_tasks_level2_cross_runner_format_with_fuzzy_quality_filtered.json` |  |
| L2 | Foursquare | `synthesis_foursquare/mcpbench_tasks_level2_cross_runner_format_with_fuzzy_quality_filtered.json`| |
| L3 | Amazon | — |  |
| L3 | Yelp | `synthesis_yelp/mcpbench_tasks_level3_cross_runner_format_with_fuzzy.json` | |
| L3 | Foursquare | — |  |



## Citation

If you use MCP-Bench in your research, please cite:

```bibtex
```

## Acknowledgments

- Built on the [Model Context Protocol](https://github.com/anthropics/mcp) by Anthropic
- Thanks to all open-sourced MCP server implementations used

---

## OpenRouter Free Models

This project supports the following free models from OpenRouter (set `OPENROUTER_API_KEY`):

| # | 配置名 | OpenRouter Model ID |
|---|---------|------------------|
| 1 | `gemma-4-26b-a4b-it-free` | `google/gemma-4-26b-a4b-it:free` |
| 2 | `gemma-4-31b-it-free` | `google/gemma-4-31b-it:free` |
| 3 | `nemotron-3-super-120b-free` | `nvidia/nemotron-3-super-120b-a12b:free` |
| 4 | `nemotron-3-nano-30b-free` | `nvidia/nemotron-3-nano-30b-a3b:free` |
| 5 | `minimax-m2.5-free` | `minimax/minimax-m2.5:free` |
| 8 | `trinity-large-preview-free` | `arcee-ai/trinity-large-preview:free` |
| 9 | `gpt-oss-20b-free` | `openai/gpt-oss-20b:free` |
| 10 | `gpt-oss-120b-free` | `openai/gpt-oss-120b:free` |
| 11 | `llama-3.3-70b-instruct-free` | `meta-llama/llama-3.3-70b-instruct:free` |
| 11 | `llama-3.3-70b-instruct` | `meta-llama/llama-3.3-70b-instruct` |
claude-3-haiku

Usage example:
```bash
bash bash_bash_L2/L3.sh ./synthesis_amazon/xxx.json gpt-oss-20b-free --rounds 2 --limit 1
```
