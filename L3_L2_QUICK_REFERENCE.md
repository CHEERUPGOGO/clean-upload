# L2 & L3 Query Synthesis - Quick Reference Guide

## 🎯 Key Difference: L2 vs L3

```
┌─────────────────────────────────────────────────────────────────────┐
│                         EXECUTION MODEL                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  L2: PARALLEL EXECUTION                L3: SEQUENTIAL EXECUTION    │
│  ───────────────────────              ──────────────────────────  │
│                                                                     │
│  Tool_A ──────┐                        Tool_A                      │
│               ├─→ [Merge Results]           │                      │
│  Tool_B ──────┤                            (output) → Tool_B       │
│               │                                  │                  │
│  Tool_C ──────┘                                 (output) → Tool_C  │
│                                                      │              │
│  ✓ All run simultaneously                          (output) → Tool_D│
│  ✓ Independent inputs                              │                │
│  ✓ Merge/aggregate results                        Final Result      │
│                                                                     │
│  ✗ Tool chains                        ✓ Each tool needs prior      │
│  ✗ Sequential dependencies            ✗ Cannot run in parallel     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Task Characteristics Comparison

| Feature | L2 | L3 |
|---------|-----|-----|
| **Tool Count** | 2-5 | 2-5 (in chain) |
| **Execution** | Parallel | Sequential |
| **Chain Length** | N/A | 2-6 steps |
| **Candidate Items** | 3-6 | 10-30 |
| **Tool Calls Field** | Yes (`tool_calls`) | No |
| **Ambiguity OK** | Yes | Yes |
| **Sequential Language** | ✗ REJECTED | ✓ REQUIRED |
| **Dependency Markers** | ✗ Forbidden | ✓ Required (≥1) |

---

## 🔄 Pipeline Execution Order

### L2 Pipeline (4 Stages)

```
STAGE 1: Task Generation (run_task_synthesis_L2_for_yelp_crossServer.py)
├─ Pick 2-5 tools from ≥2 servers
├─ Create parallel task using LLM
├─ Validate: no serial language, ≥2 inline IDs, tool_calls present
└─ Output: mcpbench_tasks_level2_cross_runner_format.json

        ↓

STAGE 2: Fuzzy Query Generation (fuzzy_query_level2.py)
├─ Convert task_description → natural language
├─ Inject ambiguity (low/moderate/high)
├─ Validate: no target leak, ✗NO sequential language (L2-specific)
└─ Output: mcpbench_tasks_level2_*_with_fuzzy.json

        ↓

STAGE 3: Quality Filter (llm_judge_level2.py)
├─ Judge LLM evaluates parallelism
├─ Score: clarity, tool appropriateness
├─ Mark: accepted / rejected
└─ Output: mcpbench_tasks_level2_*_with_fuzzy_quality_filtered.json

        ↓

STAGE 4: Post-process (postprocess_add_target_to_filtered.py)
├─ Extract user_id from task_description
├─ Lookup user's ground-truth target from sequences
├─ Extract candidate IDs from text
└─ Output: mcpbench_tasks_level2_*_with_target.json
```

### L3 Pipeline (4 Stages)

```
STAGE 1: Task Generation (run_task_synthesis_L3_for_yelp.py)
├─ Pick 2-5 tools from ≥2 servers
├─ Create SEQUENTIAL task using LLM
├─ Validate: serial structure, ≥1 marker, ≥3 inline IDs, chain 2-6
├─ Checkpoint to: level3_checkpoint.jsonl (JSONL, resumable)
└─ Output: mcpbench_tasks_level3_cross_runner_format.json

        ↓

STAGE 2: Fuzzy Query Generation (fuzzy_query_level3.py)
├─ Convert task_description → natural language
├─ Inject ambiguity (low/moderate/high)
├─ Validate: no target leak, ✓PRESERVE sequential language (L3-specific)
└─ Output: mcpbench_tasks_level3_*_with_fuzzy.json

        ↓

STAGE 3: Quality Filter (llm_judge_level3.py)
├─ Judge LLM evaluates seriality & dependencies
├─ Score: chain correctness, 2-6 steps
├─ Mark: accepted / rejected
└─ Output: mcpbench_tasks_level3_*_with_fuzzy_quality_filtered.json

        ↓

STAGE 4: Post-process (postprocess_add_target_to_filtered.py)
├─ Extract user_id from task_description
├─ Lookup user's ground-truth target from sequences
├─ Extract candidate IDs from text
└─ Output: mcpbench_tasks_level3_*_with_target.json
```

---

## 🎓 Understanding Validation Checks

### L2 Validations

```python
# ✗ REJECT: Serial language detected
"Then use ratings to filter..." ← "then" is forbidden for L2
"First search, second rank"     ← "first/second" are forbidden
"After that, compare results"   ← "after" is forbidden

# ✓ ACCEPT: Parallel structure
"Search for restaurants AND check sentiment AND filter by rating"
"Combine results from all queries"

# ✗ REJECT: Insufficient inline IDs (need ≥2)
"Find best places" ← 0 IDs
"Compare id1 with other places" ← 1 ID

# ✓ ACCEPT: Sufficient inline IDs
"Compare [id1, id2, id3] by multiple criteria" ← 3 IDs

# ✗ REJECT: Invalid tool_calls (forbidden parameter refs)
{"tool": "rec_rank", "parameters": {"items": "step 1 output"}}
{"tool": "filter_by_rating", "parameters": {"list": "previous results"}}

# ✓ ACCEPT: Concrete parameters
{"tool": "rec_rank", "parameters": {"user_id": "user123", "item_ids": ["id1", "id2"]}}
```

### L3 Validations

```python
# ✓ REQUIRE: ≥1 Serial marker
"First search for items, then check sentiment..." ← ✓ has "first", "then"
"Identify restaurants using sentiment analysis" ← ✗ no serial marker

# ✓ REQUIRE: Chain length 2-6
2 steps ✓ │ 3 steps ✓ │ 4 steps ✓ │ 5 steps ✓ │ 6 steps ✓
1 step ✗ │ 7 steps ✗ │ 8 steps ✗

# ✗ REJECT: ≥3 inline candidate IDs (need at least 3)
"Rank these items [id1, id2]" ← 2 IDs, needs ≥3
"Consider [id1, id2, id3, id4]" ← ✓ 4 IDs

# ✗ REJECT: Forbidden template phrases
"identify which candidate items are most relevant for a user interested in"
"identify the candidate items most relevant for a user interested in"

# ✗ REJECT: No meaningful sequential dependency
"Call search AND call ranking" ← Can run in parallel, not truly sequential
"Use all tools independently" ← No chains
```

---

## 📝 Input Data Structure

### Metadata (business_id_to_meta)
```json
{
  "business_id_1": {
    "name": "Downtown Bistro",
    "categories": ["Restaurants", "French"],
    "rating": 4.5,
    "review_count": 250
  }
}
```

### Targets (user_id, business_id pairs)
```json
[
  ["user_123", "business_id_1"],
  ["user_456", "business_id_2"]
]
```

### Seed Data (generated for each task)
```json
{
  "user_id": "user_123",
  "selected_tools": [
    {
      "name": "search_businesses",
      "server": "retrieval-mcp-yelp-server",
      "signature": "search_businesses(query, location, top_k)",
      "description": "...",
      "parameters": {...},
      "returns": "..."
    }
  ],
  "target_product": {
    "business_id": "id_1",
    "name": "Downtown Bistro",
    "categories": ["Restaurants", "French"]
  },
  "candidate_items": [
    {"business_id": "id_1", "name": "Downtown Bistro"},
    {"business_id": "id_2", "name": "French Cuisine"}
  ]
}
```

---

## 🔧 Tool Selection Logic

### Multi-Server Tool Picking

```python
# Step 1: Select random number of servers (≥2, max all)
available_servers = ["retrieval", "nlptool", "rating", "rec", "geo"]
num_servers = random.randint(2, 5)  # Pick 2-5 servers

# Step 2: Collect tools from selected servers
tools_per_server = {
    "retrieval": ["search_businesses", "get_business_details", ...],
    "nlptool": ["query_sentiment", "query_opinion", ...],
    "rating": ["filter_by_rating", "compare_ratings", ...],
}

# Step 3: Randomly select 2-5 total tools across all servers
# (ensuring mix from multiple servers)
selected_tools = [
    {"name": "search_businesses", "server": "retrieval"},
    {"name": "query_sentiment", "server": "nlptool"},
    {"name": "filter_by_rating", "server": "rating"}
]
```

---

## 🎭 Ambiguity Injection

### Ambiguity Levels & Types

```
LEVEL          APPLICATION              TYPES COUNT
─────────────────────────────────────────────────
Low (40%)      LIGHT application       1 type
               - Mostly rephrase
               - Keep most details
               
Moderate (40%) MODERATE application    2 types
               - Omit 1 non-critical detail
               - Add 1 contradiction/uncertainty
               
High (20%)     AGGRESSIVE application  3 types
               - Omit 2 details
               - Add contradictions
               - Include noise

TYPES: 
  • UNDERSPECIFICATION      - Missing parameters, vague thresholds
  • SOFT_CONTRADICTION     - Conflicting preferences stated together
  • VAGUE_QUANTIFIERS      - "some", "many", "few" instead of numbers
  • PREFERENCE_UNCERTAINTY - "maybe", "possibly", "I think"
  • IMPLICIT_CONSTRAINTS   - Unstated assumptions in request
```

### Ambiguity Constraints (L3 special)

```
For L3, MUST preserve sequential flow even with ambiguity:

Low:      "Search for restaurants, then check reviews..."
          (Keep sequential structure, minimal changes)

Moderate: "Find some restaurants maybe in downtown?, then I guess
           check their reviews and possibly rank them?"
          (Sequential chain still clear: search → check → rank)

High:     "I need restaurants... or maybe cafes? I want good 
           reviews but also maybe I should check trending first?
           Then rankings, or first get details?"
          (Chaotic but sequential dependencies still inferable)
```

---

## 🚀 Execution Commands

### Generate L2 Tasks
```bash
python synthesis_yelp/run_task_synthesis_L2_for_yelp_crossServer.py \
  --processed_dir data/yelp/processed \
  --max_tasks 100 \
  --output_dir synthesis_yelp \
  --mode cross
```

### Generate L3 Tasks
```bash
python synthesis_yelp/run_task_synthesis_L3_for_yelp.py \
  --processed_dir data/yelp/processed \
  --max_tasks 100 \
  --output_dir synthesis_yelp \
  --mode cross
```

### Generate L2 Fuzzy Queries
```bash
python synthesis_yelp/fuzzy_query_level2.py \
  --tasks_file synthesis_yelp/mcpbench_tasks_level2_cross_runner_format.json \
  --ambiguity_level moderate
```

### Generate L3 Fuzzy Queries
```bash
python synthesis_yelp/fuzzy_query_level3.py \
  --tasks_file synthesis_yelp/mcpbench_tasks_level3_cross_runner_format.json \
  --ambiguity_level moderate
```

### Post-process (Add targets)
```bash
python postprocess_add_target_to_filtered.py \
  --data_root data/ \
  --datasets amazon,yelp,foursquare
```

---

## 📊 Output File Naming Convention

```
mcpbench_tasks_level{2|3}_{cross|intra}_runner_format.json
           ↓                ↓
      Generation Type    Server Type

  ↓ + fuzzy generation
mcpbench_tasks_level{2|3}_{cross|intra}_runner_format_with_fuzzy.json

  ↓ + quality filtering
mcpbench_tasks_level{2|3}_{cross|intra}_*_with_fuzzy_quality_filtered.json

  ↓ + post-processing
mcpbench_tasks_level{2|3}_{cross|intra}_*_with_fuzzy_quality_filtered_with_target.json
```

---

## 🎯 Key Concepts

### Task Description vs Fuzzy Description

```
TASK DESCRIPTION (Structured):
"For user_id='user_123', search for restaurants in downtown 
[id1, id2, id3], check sentiment ≥80%, and filter by rating ≥4.0. 
Compare the three tools' results using intersection logic."

↓ (LLM conversion with ambiguity)

FUZZY DESCRIPTION (Natural):
"Can you help me find some really good restaurants downtown 
with positive reviews? I'm looking for highly-rated places 
my preferences match."
```

### Candidate Items vs Target Item

```
TARGET ITEM:
  User's ground-truth item (their last interaction)
  Purpose: Ground truth for evaluation
  Example: business_id = "id_5"

CANDIDATE ITEMS:
  Pool of items the agent must choose from
  Always includes target item
  Purpose: Test agent's ranking/selection ability
  Count: 3-6 for L2, 10-30 for L3
  Example: [id_5, id_1, id_2, id_3, id_4, id_6]
```

### Tool Calls (L2 only)

```json
"tool_calls": [
  {
    "tool": "search_businesses",
    "parameters": {
      "query": "restaurant",
      "location": [-73.9, 40.7],
      "top_k": 10
    }
  },
  {
    "tool": "query_sentiment",
    "parameters": {
      "min_positive_rate": 80
    }
  }
]
```

**Purpose**: Pre-planned tool calls for L2 tasks (parallel execution ready)
**Not in L3**: Because L3 chains cannot pre-plan all tool calls (depend on prior outputs)

### Chain Length (L3 only)

```
chain_length = 3

Tool_A
   ↓ (output)
Tool_B
   ↓ (output)
Tool_C

Number of sequential steps in the main dependency chain (2-6 range)
```

---

## 💡 Common Issues & Solutions

### Issue: Task generation keeps failing

**Check**:
1. Sufficient metadata loaded? (`Fast loaded {count} products`)
2. Targets available? (`Fast loaded {count} target items`)
3. LLM API connectivity? (Check eval_server endpoint)
4. Tool registry populated? (Check server_tool_registry.py)

### Issue: All L3 tasks rejected for "no serial markers"

**Fix**:
- L3 prompt encourages sequential language
- Ensure `Level3_prompt.txt` mentions "first", "then", "after"
- L3 validator checks for regex patterns: `r"\bthen\b"`, `r"\bafter\b"`

### Issue: Fuzzy tasks contain target ID (target leak)

**Fix**:
- Extract forbidden terms: `_extract_target_terms()`
- Check against fuzzy output: `_contains_target_leak()`
- Use `_FORBIDDEN_PARAM_REF_PATTERNS` for validation

### Issue: Checkpoint not resuming

**Check**:
- File path: `synthesis_yelp/level3_checkpoint.jsonl`
- JSONL format (one JSON object per line)
- No corrupt lines in checkpoint
- Delete checkpoint if needed to restart

---

## 📈 Quality Metrics to Track

```
Generation Stage:
├─ Tasks attempted
├─ Tasks succeeded
├─ Success rate (%)
└─ Reasons for failure (serial/parallel, IDs, parse errors)

Fuzzy Stage:
├─ Tasks processed
├─ Fuzzy generated successfully
├─ Target leak detected (%)
├─ Sequential language rejected (%)
└─ Ambiguity distribution

Quality Judge Stage:
├─ Tasks evaluated
├─ Accepted tasks (%)
├─ Rejected tasks (%)
└─ Common rejection reasons

Post-process Stage:
├─ User IDs extracted
├─ Candidates extracted
├─ Target found in candidates (%)
└─ Final task count
```

---

## 🔐 Forbidden Patterns

### L2: Sequential Language (REJECTED)
```
✗ "step 1", "step 2", "step 3"
✗ "first ... then"
✗ "after that"
✗ "after which"
✗ "once ... then"
✗ "next", "finally"
✗ "subsequently"
```

### Tool Call Parameters (REJECTED for all)
```
✗ "step 1 output"
✗ "output from first tool"
✗ "previous result"
✗ "prior tool's output"
✗ "from step X"
✗ "from tool Y"
```

### L3: Template Biasing Phrases (REJECTED)
```
✗ "identify which candidate items are most relevant for 
   a user interested in"
✗ "identify the candidate items most relevant for 
   a user interested in"
```

---

## ✅ Valid Patterns

### L2: Parallel Language (ACCEPTED)
```
✓ "Search AND check sentiment AND filter by rating"
✓ "Combine results from all tools"
✓ "Merge using intersection/union logic"
✓ "Multiple criteria analysis"
✓ "Cross-tool validation"
```

### L3: Sequential Language (REQUIRED)
```
✓ "First search for ... then check ... finally rank"
✓ "Based on results from step 1, do step 2"
✓ "Use output from search to filter candidates, then rank"
✓ "After getting sentiment scores, use them for ranking"
```

---

## 🎪 Available MCP Servers (Example: Yelp)

```
retrieval-mcp-yelp-server
├─ get_business_details(business_name)
├─ search_businesses(query, location, top_k)
├─ filter_businesses(categories, location, open_timestamp)
└─ recall_similar_items(query_text)

nlptool-mcp-yelp-server
├─ query_sentiment(min_positive_rate)
├─ query_opinion(keywords)
└─ query_summary(keyword_str)

rec-mcp-yelp-server
├─ rec_rank(user_id, item_ids)
└─ get_user_history(user_id)

rating-mcp-yelp-server
├─ filter_by_rating(min_rating, max_rating, limit)
├─ filter_by_rating_count(min_count, max_count, limit)
└─ compare_ratings(business_ids)

geo-mcp-yelp-server
├─ google_geo(address)
└─ google_distance(origins, destinations)
```

---

**Last Updated**: 2026-05-14
**Files Referenced**: See L3_L2_QUERY_SYNTHESIS_ANALYSIS.md for detailed documentation
