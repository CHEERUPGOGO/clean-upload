# L3 & L2 Query Synthesis Pipeline - Complete Flow Analysis

## Overview

This codebase implements a sophisticated **multi-level task synthesis pipeline** that generates benchmark tasks for testing Multi-Protocol Composition (MCP) tool orchestration. The pipeline creates:
- **L3 Tasks**: Complex multi-tool tasks with **strict sequential dependencies** (serial chains 2-6 tools)
- **L2 Tasks**: Complex multi-tool tasks with **parallel independent tool calls** (2-5 tools)
- **Fuzzy Descriptions**: Natural language versions with intentional ambiguity injected
- **Quality Filtered Tasks**: LLM-evaluated and validated task sets

---

## High-Level Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    L2/L3 SYNTHESIS PIPELINE                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
                    ▼                   ▼
            ┌─────────────┐       ┌──────────┐
            │ L3 Pipeline │       │ L2 Pipeline│
            └─────────────┘       └──────────┘
                    │                   │
         ┌──────────┴──────────┐        │
         │                     │        │
         ▼                     ▼        ▼
    [Step 1]           [Step 2]    [Step 2]
    Generate          Generate      Generate
    Tasks             Fuzzy         Fuzzy
    (Serial)          Desc.         Desc.
         │              │             │
         └──────────────┴─────────────┘
                   │
                   ▼
            [Step 3]
            LLM Judge
            Quality
            Filter
                   │
                   ▼
         [Final] Tasks Ready
         for Benchmarking
```

---

## DETAILED FLOW: L2 Query Synthesis

### **Step 1: L2 Task Generation** (`run_task_synthesis_L2_for_yelp_crossServer.py`)

**Entry Point**: `generate_level2_tasks()`

**Input**:
- `business_id_to_meta`: Dict mapping business IDs to metadata (name, categories, etc.)
- `targets`: List of (user_id, business_id) tuples representing user's last interaction
- `max_tasks`: Number of tasks to generate (default: 5)
- `mode`: "cross" (multi-server) or "intra" (single-server)

**Key Functions**:

| Function | Purpose |
|----------|---------|
| `pick_tools_from_multiple_servers()` | Randomly select 2-5 tools from ≥2 different servers |
| `load_level2_prompt()` | Load L2 system + user prompt templates |
| `call_llm_for_query()` | Call eval_server LLM API with formatting constraints |
| `_normalize_planned_tool_calls()` | Parse & validate tool_calls from LLM, reject invalid refs |
| `validate_parallel_structure()` | Heuristic check: reject serial language patterns |
| `_safe_parse_json_object()` | Robust JSON extraction from LLM output |

**Seed Data Provided to LLM**:
```json
{
  "user_id": "user_xyz",
  "selected_tools": [
    {
      "name": "search_businesses",
      "server": "retrieval-mcp-yelp-server",
      "signature": "search_businesses(query, location, top_k)",
      ...
    }
  ],
  "target_product": {
    "business_id": "abc123xyz",
    "name": "Example Coffee Shop",
    "categories": ["Cafes", "Coffee"]
  },
  "candidate_items": [
    {"business_id": "abc123xyz", "name": "Example Coffee Shop"},
    {"business_id": "def456uvw", "name": "Another Cafe"},
    ...
  ]
}
```

**LLM Prompt Constraints**:
1. **Task must be PARALLEL**: All tool calls have independent inputs from seed_data
2. **No sequential language**: Rejects patterns like "step 1, step 2", "then", "after that"
3. **Candidate IDs inline**: Must list actual candidate IDs in task_description (≥2 required)
4. **Forbidden param references**: Rejects tool_calls referencing "step", "output", "previous", "prior"
5. **Tool call inclusion**: `tool_calls` JSON field with concrete executable parameters for ALL selected tools

**Validation Gate**:
```python
if not validate_parallel_structure(task_desc, dep_analysis, tool_names):
    skip(attempt)  # Serial language detected
if len(inlined_ids) < 2:
    skip(attempt)  # Insufficient candidate IDs
if len(planned_tool_calls) != len(tool_names):
    skip(attempt)  # Invalid/incomplete tool_calls
```

**Output Format**:
```json
{
  "task_id": 0,
  "task_description": "Detailed parallel task description with inline candidate IDs...",
  "dependency_analysis": "Describe parallel execution and result merging...",
  "selected_tools": ["search_businesses", "query_sentiment", "filter_by_rating"],
  "planned_tool_calls": [
    {"tool": "search_businesses", "parameters": {"query": "...", "top_k": 10}},
    {"tool": "query_sentiment", "parameters": {"min_positive_rate": 80}},
    ...
  ],
  "user_id": "user_xyz",
  "target_item": {"business_id": "abc123xyz", "name": "...", "categories": [...]},
  "candidate_item_ids": ["abc123xyz", "def456uvw", ...]
}
```

**Saved to**: `synthesis_yelp/mcpbench_tasks_level2_cross_runner_format.json`

---

### **Step 2: L2 Fuzzy Description Generation** (`fuzzy_query_level2.py`)

**Entry Point**: `batch_generate_fuzzy_queries()`

**Input**: Tasks JSON from Step 1 with `task_description` field

**Key Functions**:

| Function | Purpose |
|----------|---------|
| `_sample_ambiguity_config()` | Sample ambiguity level (low 40%, moderate 40%, high 20%) and types |
| `_detect_tools_from_description()` | Extract tool names from task_description |
| `_extract_target_terms()` | Extract forbidden terms (target ID, target name) to avoid leaking answers |
| `generate_fuzzy_query()` | Call LLM to convert structured task into natural query |
| `_contains_target_leak()` | Validate fuzzy description doesn't reveal target |
| `_has_sequential_language()` | **L2-specific**: Reject sequential wording (must stay parallel) |

**Ambiguity Configuration**:
```
Low (40%):        Apply LIGHTLY    - mostly rephrase, keep details (1 type)
Moderate (40%):   Apply MODERATELY - omit 1 detail, add 1 contradiction (2 types)
High (20%):       Apply AGGRESSIVELY - omit 2 details, add contradictions (3 types)

TYPES: ["UNDERSPECIFICATION", "SOFT_CONTRADICTION", "VAGUE_QUANTIFIERS", 
        "PREFERENCE_UNCERTAINTY", "IMPLICIT_CONSTRAINTS"]
```

**Constraints**:
1. **L2-specific**: Rejects sequential markers (first/then/after/finally/step N)
2. **Never reveal target**: No target ID or exact target name verbatim
3. **Keep candidate IDs**: Must preserve all candidate item IDs in input
4. **No external refs**: No URLs, local files, database references
5. **Preserve tool semantics**: One holistic request, not step-by-step

**Output Field Added**:
```json
{
  "task_description": "...",
  "fuzzy_description": "Can you help me find the best restaurants for different criteria?",
  "ambiguity_level": "moderate",
  "ambiguity_types": ["VAGUE_QUANTIFIERS", "UNDERSPECIFICATION"],
  ...
}
```

**Saved to**: `synthesis_yelp/mcpbench_tasks_level2_cross_runner_format_with_fuzzy.json`

---

### **Step 3: L2 Quality Filtering** (`llm_judge_level2.py`)

**Entry Point**: Judge LLM evaluates task quality

**Key Evaluation Criteria**:
1. **Parallelism Enforcement**: Fuzzy query should trigger parallel tool execution
2. **Tool Selection Appropriateness**: Selected tools match task requirements
3. **Task Clarity**: Fuzzy description is unambiguous enough for execution
4. **Dependency-free**: No implicit sequential dependencies

**Judge Model**: `qwen3.5-397b-a17b` (different from synthesis model to avoid self-judging)

**Output**: Tasks marked as "accepted" or "rejected"

**Saved to**: `synthesis_yelp/mcpbench_tasks_level2_cross_runner_format_with_fuzzy_quality_filtered.json`

---

## DETAILED FLOW: L3 Query Synthesis

### **Step 1: L3 Task Generation** (`run_task_synthesis_L3_for_yelp.py`)

**Entry Point**: `generate_level3_tasks()`

**Key Difference from L2**: 
- **L2 enforces PARALLEL**: No dependencies between tools
- **L3 requires SEQUENTIAL**: Tool B needs output from Tool A (strict chains)

**Input**: Same structure as L2 (metadata, targets)

**Seed Data**: More extensive candidate set for L3
```json
{
  "user_id": "user_xyz",
  "target_product": {...},
  "candidate_items": [  // 10-30 candidates (vs 3-6 for L2)
    {"business_id": "id1", "title": "..."},
    ...
  ]
}
```

**Key Functions**:

| Function | Purpose |
|----------|---------|
| `load_level3_prompt()` | Load L3 system + user prompt templates |
| `validate_serial_structure()` | **L3-specific**: Ensure ≥1 serial marker ("then", "after", "based on", etc.) |
| `has_forbidden_query_phrase()` | Reject templated biasing phrases |
| `_load_checkpoint()` / `_append_checkpoint()` | Save progress incrementally (JSONL) |

**LLM Prompt Constraints (L3-specific)**:

1. **Strict Sequential Chains**: Tool B must need Tool A's output
   - NO parallel branches
   - NO fan-out/fan-in
   - NO independent sub-tasks
   
2. **Chain Length 2-6**: Number of sequential tool calls in main dependency

3. **Dependency Types Allowed**:
   - Deep chains: Tool B ← A output, Tool C ← B output, ...
   - Decision branches: If condition X (from prior output) then workflow Y
   - Verification: Sequential cross-validation
   - Conditional workflows: Based on intermediate results
   - Serial bottlenecks: Later tool input ONLY from earlier tool output

4. **Candidate IDs**: ≥3 must be inline in task_description

5. **Forbidden Phrases**: Rejects templated biasing
   - "identify which candidate items are most relevant for a user interested in"
   - "identify the candidate items most relevant for a user interested in"

**Validation Gate**:
```python
if not validate_serial_structure(task_desc, dep_analysis, tool_names):
    skip(attempt)  # No serial markers found

if not (2 <= chain_length <= 6):
    skip(attempt)  # Invalid chain length

if len(inlined_ids) < 3:
    skip(attempt)  # Insufficient candidate IDs

if has_forbidden_query_phrase(task_desc):
    skip(attempt)  # Templated bias detected
```

**Output Format**:
```json
{
  "task_id": 0,
  "task_description": "Detailed serial task with ≥3 inline candidate IDs...",
  "dependency_analysis": "Describe sequential chain, data flow, decision points...",
  "selected_tools": ["search_businesses", "query_sentiment", "rec_rank"],
  "chain_length": 3,  // Number of sequential steps (2-6)
  "user_id": "user_xyz",
  "target_item": {...},
  "candidate_item_ids": [...]  // 10-30 candidates
}
```

**Checkpoint Feature**: 
- Saves to `synthesis_yelp/level3_checkpoint.jsonl` (one task per line)
- Allows resuming if generation is interrupted
- Already-generated tasks skipped on resume

**Saved to**: `synthesis_yelp/mcpbench_tasks_level3_cross_runner_format.json`

---

### **Step 2: L3 Fuzzy Description Generation** (`fuzzy_query_level3.py`)

**Key Difference from L2**: 
- **L3 PRESERVES sequential language**: "first...then...after that" is CORRECT
- **L2 REJECTS sequential language**

**Entry Point**: `batch_generate_fuzzy_queries()` (same function name, different logic)

**Key Functions**:
```python
def generate_fuzzy_query(task_description, tools, ...):
    """L3: Preserves sequential language (unlike L2)"""
    # Unlike L2, does NOT call _has_sequential_language()
    # Only checks: target leak
```

**Constraints**:
1. **L3-specific**: Sequential flow MUST be inferable
   - Low ambiguity: Rephrase lightly, keep sequential structure
   - Moderate ambiguity: Omit 1 detail, add 1 contradiction, but KEEP sequential chain intact
   - High ambiguity: Omit 2 details, add contradictions, but sequential flow still inferable

2. **Same as L2**: Target leak check, no external refs, keep candidate IDs

**Output**:
```json
{
  "task_description": "...",
  "fuzzy_description": "First, search for highly-rated restaurants in...",  
  "ambiguity_level": "moderate",
  "ambiguity_types": ["SOFT_CONTRADICTION", "VAGUE_QUANTIFIERS"],
  ...
}
```

**Saved to**: `synthesis_yelp/mcpbench_tasks_level3_cross_runner_format_with_fuzzy.json`

---

### **Step 3: L3 Quality Filtering** (`llm_judge_level3.py`)

**Key Evaluation Criteria**:
1. **Seriality Enforcement**: Fuzzy query should trigger sequential tool execution
2. **Dependency Correctness**: Output from tool N+1 clearly feeds tool N+2
3. **Chain Length Validation**: 2-6 distinct sequential calls
4. **No Parallel Alternatives**: Cannot be executed in parallel

**Judge Model**: `qwen3.5-397b-a17b`

**Output**: Tasks marked "accepted" or "rejected"

**Saved to**: `synthesis_yelp/mcpbench_tasks_level3_cross_runner_format_with_fuzzy_quality_filtered.json`

---

## Post-Processing Step (`postprocess_add_target_to_filtered.py`)

**Purpose**: Add ground-truth metadata to quality-filtered tasks for benchmarking

**Process**:
1. Reads `*_quality_filtered.json` (contains task_description, fuzzy_description)
2. Extracts `user_id` from task_description using regex patterns
3. Looks up user's last interacted item from `user_sequences.jsonl`
4. Extracts candidate item IDs from task_description using dataset-specific regex
5. Validates target is in candidate list
6. Adds to output file:
   - `target_item`: {business_id, name, categories}
   - `user_id`
   - `candidate_item_ids`: List of all candidate IDs

**Output**: `synthesis_yelp/mcpbench_tasks_*_with_target.json`

---

## LLM APIs Used

### eval_server API (Internal Qwen/GLM/Deepseek backend)

```
Endpoint: https://api.your-custom-eval-server.com/v1/chat/completions
Auth:     Bearer {eval_server_TOKEN}

Models Used:
- Task Synthesis L2:     glm-5.1 (temperature: 0, max_tokens: 8192)
- Task Synthesis L3:     deepseek-v3.2 (temperature: 0, max_tokens: 16384)
- Fuzzy Generation L2/L3: minimax-m2.7 (temperature: 0, max_tokens: 4096)
- Quality Judge L2/L3:    qwen3.5-397b-a17b (temperature: 0, max_tokens: 1024)
```

**Retry Logic**: 
- Max 5 retries with exponential backoff
- Sleep: min(10 * attempt, 60) seconds
- On `finish_reason='length'`: Double max_tokens (up to 32768 for L3)

---

## Available MCP Tools (Server Registry)

### Yelp Servers

**retrieval-mcp-yelp-server**:
- `get_business_details(business_name)` - Get business details by name
- `search_businesses(query, location, top_k)` - Soft search with hit rate
- `filter_businesses(categories, location, open_timestamp)` - Hard filter
- `recall_similar_items(query_text)` - Collaborative filtering

**nlptool-mcp-yelp-server**:
- `query_sentiment(min_positive_rate)` - Find items by review sentiment
- `query_opinion(keywords)` - Find items by opinion keywords
- `query_summary(keyword_str)` - Find items by summary keywords

**rec-mcp-yelp-server**:
- `rec_rank(user_id, item_ids)` - Rank items by user history
- `get_user_history(user_id)` - Get user interaction history

**rating-mcp-yelp-server**:
- `filter_by_rating(min_rating, max_rating, limit)` - Filter by rating range
- `filter_by_rating_count(min_count, max_count, limit)` - Filter by review count
- `compare_ratings(business_ids)` - Compare ratings

**geo-mcp-yelp-server**:
- `google_geo(address)` - Get coordinates from address
- `google_distance(origins, destinations)` - Calculate distances

---

## Key Data Structures

### Task Object (L2/L3 Output)

```python
{
    "task_id": int,
    "task_description": str,  # Detailed, structured description
    "fuzzy_description": str,  # Natural language version
    "dependency_analysis": str,  # Explains execution flow
    
    # L2-specific:
    "planned_tool_calls": [{"tool": str, "parameters": dict}],
    
    # L3-specific:
    "chain_length": int,  # 2-6 for sequential chains
    
    # Shared metadata:
    "selected_tools": [str],
    "ambiguity_level": str,  # "low", "moderate", "high"
    "ambiguity_types": [str],
    "user_id": str,
    "target_item": {
        "business_id": str,
        "name": str,
        "categories": [str]
    },
    "candidate_item_ids": [str]  # 3-6 for L2, 10-30 for L3
}
```

### Runner Format (Multi-level tasks grouped)

```json
{
  "generation_info": {
    "status": "completed",
    "source": "task_synthesis"
  },
  "server_tasks": [
    {
      "server_name": "retrieval+nlptool+rating",
      "tasks": [{...}, {...}],
      "servers": ["retrieval-mcp-yelp-server", "nlptool-mcp-yelp-server", ...],
      "combination_name": "Cross-Server: Retrieval+NLP+Rec+Rating",
      "combination_type": "cross_server"
    }
  ]
}
```

---

## Execution Flow Summary

### Complete L2 Pipeline

```
1. Generate L2 Tasks (run_task_synthesis_L2_for_yelp_crossServer.py)
   └─ Input: metadata, user sequences
   └─ Process: LLM generates parallel multi-tool tasks
   └─ Validations: parallel structure, inline candidate IDs
   └─ Output: mcpbench_tasks_level2_cross_runner_format.json

2. Generate L2 Fuzzy Queries (fuzzy_query_level2.py)
   └─ Input: task_description fields
   └─ Process: LLM converts to natural language + ambiguity
   └─ Validations: no target leak, no sequential language (L2-specific)
   └─ Output: mcpbench_tasks_level2_*_with_fuzzy.json

3. Quality Filter L2 (llm_judge_level2.py)
   └─ Input: fuzzy_description fields
   └─ Process: Judge LLM evaluates parallelism + clarity
   └─ Output: mcpbench_tasks_level2_*_with_fuzzy_quality_filtered.json

4. Post-process (postprocess_add_target_to_filtered.py)
   └─ Input: task_description + fuzzy_description
   └─ Extract: user_id, candidate IDs from text
   └─ Lookup: user's ground-truth target from sequences
   └─ Output: mcpbench_tasks_level2_*_with_target.json
```

### Complete L3 Pipeline

```
1. Generate L3 Tasks (run_task_synthesis_L3_for_yelp.py)
   └─ Input: metadata, user sequences
   └─ Process: LLM generates serial multi-tool tasks (2-6 chain length)
   └─ Validations: serial structure, ≥1 serial marker, chain length
   └─ Output: mcpbench_tasks_level3_cross_runner_format.json
   └─ Checkpoint: level3_checkpoint.jsonl (for resumability)

2. Generate L3 Fuzzy Queries (fuzzy_query_level3.py)
   └─ Input: task_description fields
   └─ Process: LLM converts to natural language + ambiguity
   └─ PRESERVE: Sequential language (unlike L2)
   └─ Validations: no target leak, sequence inferable
   └─ Output: mcpbench_tasks_level3_*_with_fuzzy.json

3. Quality Filter L3 (llm_judge_level3.py)
   └─ Input: fuzzy_description fields
   └─ Process: Judge LLM evaluates seriality + dependency correctness
   └─ Output: mcpbench_tasks_level3_*_with_fuzzy_quality_filtered.json

4. Post-process (postprocess_add_target_to_filtered.py)
   └─ Same as L2 post-processing
   └─ Output: mcpbench_tasks_level3_*_with_target.json
```

---

## Critical Design Decisions

### L2 (Parallel) vs L3 (Serial)

| Aspect | L2 | L3 |
|--------|----|----|
| **Tool Execution** | Parallel | Sequential |
| **Dependencies** | None between tools | Output from tool N feeds tool N+1 |
| **Chain Length** | N/A | 2-6 (fixed) |
| **Candidate Count** | 3-6 | 10-30 |
| **Fuzzy Language** | Must be parallel | Preserves sequential markers |
| **Validation** | Rejects "then", "step 1" | Requires ≥1 "then", "after", etc. |

### Ambiguity Injection Strategy

1. **Prevents Bias**: LLM judges can't memorize task patterns
2. **Realistic**: Real users are ambiguous and contradictory
3. **Tiered**: Low/moderate/high allows curriculum learning
4. **Types**: 5 distinct types cover common human ambiguity

### Checkpointing Strategy (L3)

- **Incremental save**: Each task appended to JSONL immediately
- **Resume support**: On re-run, loads checkpoint and skips existing
- **Progress tracking**: Can monitor generation live
- **Failure resilience**: Network issues don't lose progress

### Forbidden Parameter References

L2 tool_calls must have concrete parameters (no refs to other tools):
```python
# ✗ INVALID (forbidden):
{"tool": "rec_rank", "parameters": {"item_ids": "step 1 output"}}

# ✓ VALID (concrete):
{"tool": "rec_rank", "parameters": {"item_ids": ["id1", "id2"]}}
```

---

## File Structure Summary

```
synthesis_yelp/
├── run_task_synthesis_L2_for_yelp_crossServer.py
│   └─ Entry: python ... --processed_dir data/yelp/processed --max_tasks 100
│   
├── run_task_synthesis_L3_for_yelp.py
│   └─ Entry: python ... --processed_dir data/yelp/processed --max_tasks 100
│   
├── fuzzy_query_level2.py
│   └─ Entry: python ... --tasks_file mcpbench_tasks_level2_cross_runner_format.json
│   
├── fuzzy_query_level3.py
│   └─ Entry: python ... --tasks_file mcpbench_tasks_level3_cross_runner_format.json
│   
├── llm_judge_level2.py
│   └─ Evaluates L2 fuzzy tasks for quality
│   
├── llm_judge_level3.py
│   └─ Evaluates L3 fuzzy tasks for quality
│   
├── server_tool_registry.py
│   └─ SERVER_TOOL_REGISTRY: Static registry of all available tools
│   
├── Level2_prompt.txt
│   └─ System + user prompt templates for L2 generation
│   
├── Level3_prompt.txt
│   └─ System + user prompt templates for L3 generation
│   
├── fuzzy_prompt.txt
│   └─ Template for L2 fuzzy conversion
│   
├── fuzzy_prompt_level3.txt
│   └─ Template for L3 fuzzy conversion
│   
├── task_quality_prompt.txt
│   └─ Prompt for L2 quality judge
│   
└── task_quality_prompt_level3.txt
    └─ Prompt for L3 quality judge

postprocess_add_target_to_filtered.py
└─ Adds ground-truth metadata to all quality-filtered tasks

bash_bash_L2.sh / bash_bash_L3.sh
└─ Runner scripts for executing benchmarks with generated tasks
```

---

## Example L2 Task (Parallel)

```json
{
  "task_id": 0,
  "task_description": "For user 'abc123xyz', find the best recommendations based on multiple criteria. Search for restaurants in downtown area [id1, id2, id3], check sentiment for positive reviews >80% [id4, id5], and filter by rating ≥4.0. Merge all results to create a final ranked list.",
  "fuzzy_description": "Help me discover top-rated restaurants downtown with consistently positive reviews.",
  "dependency_analysis": "All three tools (search, sentiment, rating) are called in PARALLEL with independent inputs from seed data. Results are merged using intersection logic.",
  "selected_tools": ["search_businesses", "query_sentiment", "filter_by_rating"],
  "planned_tool_calls": [
    {"tool": "search_businesses", "parameters": {"query": "restaurant", "location": [-73.9, 40.7], "top_k": 10}},
    {"tool": "query_sentiment", "parameters": {"min_positive_rate": 80}},
    {"tool": "filter_by_rating", "parameters": {"min_rating": 4.0, "limit": 10}}
  ],
  "ambiguity_level": "moderate",
  "ambiguity_types": ["VAGUE_QUANTIFIERS"],
  "user_id": "abc123xyz",
  "target_item": {
    "business_id": "id1",
    "name": "Downtown Bistro",
    "categories": ["Restaurants", "French"]
  },
  "candidate_item_ids": ["id1", "id2", "id3", "id4", "id5"]
}
```

---

## Example L3 Task (Sequential)

```json
{
  "task_id": 0,
  "task_description": "For user 'xyz789', first search for Asian restaurants in downtown [id1-id10]. Then from the top-3 results, check their review sentiments. Finally, rank the candidates [id1, id2, ..., id15] based on user interaction history and return top-5 recommendations.",
  "fuzzy_description": "Find me the best Asian restaurants downtown, but I want ones with really positive reviews and that match my past preferences.",
  "dependency_analysis": "Sequential chain: (1) search_businesses → returns top restaurants (2) query_sentiment uses returned IDs → filters by sentiment (3) rec_rank uses filtered IDs → final ranking. Each step's input depends on prior step's output.",
  "selected_tools": ["search_businesses", "query_sentiment", "rec_rank"],
  "chain_length": 3,
  "ambiguity_level": "low",
  "ambiguity_types": ["UNDERSPECIFICATION"],
  "user_id": "xyz789",
  "target_item": {
    "business_id": "id5",
    "name": "Dim Sum Palace",
    "categories": ["Asian", "Restaurants"]
  },
  "candidate_item_ids": ["id1", "id2", "id3", ..., "id15"]  // 10-30 items
}
```

---

## Summary of Key Components

### Query Synthesis Files

1. **run_task_synthesis_L2_for_yelp_crossServer.py** (594 lines)
   - Generates L2 (parallel) tasks
   - Core: `generate_level2_tasks()` → LLM → validation

2. **run_task_synthesis_L3_for_yelp.py** (524 lines)
   - Generates L3 (serial) tasks with checkpointing
   - Core: `generate_level3_tasks()` → LLM → validation

3. **fuzzy_query_level2.py** (365 lines)
   - Converts L2 task_description → fuzzy_description
   - Rejects sequential language
   - Injects 5 types of ambiguity (3 levels)

4. **fuzzy_query_level3.py** (355 lines)
   - Converts L3 task_description → fuzzy_description
   - **Preserves** sequential language
   - Injects ambiguity with sequence preservation

5. **llm_judge_level2.py** / **llm_judge_level3.py**
   - Quality evaluation using different judge model
   - Filters out low-quality tasks

### Quality Metrics

- **L2 Pass Rate**: Tasks passing parallelism check
- **L3 Pass Rate**: Tasks with valid serial chains
- **Fuzzy Success Rate**: Tasks successfully converted
- **Ambiguity Distribution**: % low/moderate/high across batch

### Extensibility Points

- **New datasets**: Add to DATASET_CONFIGS in postprocess
- **New tool servers**: Register in SERVER_TOOL_REGISTRY
- **custom prompts**: Modify Level2_prompt.txt / Level3_prompt.txt
- **Different LLM models**: Change `llm_call()` model parameter
- **Validation rules**: Extend validate_parallel_structure() / validate_serial_structure()

