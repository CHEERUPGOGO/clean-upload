"""
LLM-as-Judge Evaluator for L4 Hybrid Workflow Tasks (MCP-Bench)

Evaluates agent performance on 4 LLM-judged dimensions:
  - Planning Coherence       (PC):  hybrid workflow structure correctness
  - Multi-round Efficiency   (ME):  execution economy, no redundant calls
  - Parameter Appropriateness (PA): tool parameters semantically match task constraints
  - Information Grounding    (IG):  final answer grounded in tool outputs

These complement the 4 rule-based metrics from evaluate_L4_metrics.py:
  S_acc, R_suc, T_f1, R_hit
"""

import asyncio
import logging
from typing import List, Dict, Any, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM provider protocol
# ---------------------------------------------------------------------------

class LLMProvider(Protocol):
    async def get_completion(self, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        ...

    def clean_and_parse_json(self, raw_text: str) -> Any:
        ...


# ---------------------------------------------------------------------------
# Judge prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are an expert evaluator for AI agents that execute hybrid tool workflows "
    "(combining parallel and serial tool calls). "
    "Score strictly based on evidence in the execution trace. "
    "Be critical: default to 4-5 unless strong evidence supports higher."
)

_JUDGE_PROMPT_TEMPLATE = """\
You are evaluating an AI agent that completed a task requiring a **hybrid workflow**: \
some tools should run in parallel (independent of each other), and some tools must run \
serially (depending on outputs from earlier tools).

---

## Task Description
{task}

## Expected Workflow Structure
{workflow_structure}

## Execution Trace
{execution_trace}

## Agent's Final Answer
{final_answer}

---

## Scoring Dimensions

Score each dimension on a scale of **1â€?0**.

### 1. Planning Coherence (PC)
Does the agent correctly decompose the task into a hybrid plan?
- Did it identify which tools can run in parallel (no inter-dependencies)?
- Did it correctly sequence serial steps that depend on prior outputs?
- Did it properly handle fan-in (merging results from parallel stage before serial stage)?
- Is the overall execution order logically consistent with the task requirements?

| Score | Criterion |
|-------|-----------|
| 9â€?0  | Perfect hybrid plan: all parallel opportunities exploited, all dependencies respected |
| 7â€?   | Mostly correct plan; one minor ordering issue or missed parallelism |
| 4â€?   | Partially correct; some tools run serially that could be parallel, or dependencies violated |
| 1â€?   | No coherent plan; tools called randomly or all sequentially despite parallel opportunities |

### 2. Multi-round Efficiency (ME)
Did the agent complete the task efficiently without unnecessary tool calls?
- Were parallelizable tools called in the same round (not spread across multiple rounds)?
- Were there redundant/duplicate calls?
- Were there wasted exploratory calls that contributed nothing?
- Did it avoid unnecessary retries or irrelevant tool usage?

| Score | Criterion |
|-------|-----------|
| 9â€?0  | Optimal or near-optimal execution: minimal rounds, no waste, parallel when possible |
| 7â€?   | Mostly efficient; one extra round or one redundant call |
| 4â€?   | Noticeable inefficiency; several wasted calls or missed parallelism opportunities |
| 1â€?   | Highly inefficient; many redundant calls, excessive rounds, or irrelevant tools used |

### 3. Parameter Appropriateness (PA)
Are the parameters passed to each tool call semantically correct for the task?
- Do filter thresholds match what the task description specifies or implies?
- Are search keywords relevant to the user's stated interests?
- Are item IDs passed to downstream tools correctly derived from upstream results?
- Are parameters reasonable even if not exactly matching a single "correct" answer?

| Score | Criterion |
|-------|-----------|
| 9â€?0  | All parameters are well-justified by the task description and upstream outputs |
| 7â€?   | Most parameters correct; one minor mismatch (e.g., slightly off threshold) |
| 4â€?   | Some parameters are incorrect, hardcoded, or don't match task constraints |
| 1â€?   | Most parameters are wrong, arbitrary, or ignore task requirements entirely |

### 4. Information Grounding (IG)
Does the agent's final answer faithfully reflect what the tools actually returned?
- Are recommended items actually present in tool outputs?
- Are ratings, titles, review counts, etc. traceable to tool results?
- Does the agent avoid hallucinating information not returned by any tool?
- Is the final synthesis logically supported by the collected evidence?

| Score | Criterion |
|-------|-----------|
| 9â€?0  | 90-100% of factual claims are directly grounded in tool outputs |
| 7â€?   | 70-80% grounded; minor unsupported details |
| 4â€?   | 40-60% grounded; noticeable hallucination or fabricated data |
| 1â€?   | Less than 30% grounded; agent largely ignores tool results |

---

## Instructions
1. First reason briefly for each dimension (1-2 sentences each).
2. Then output scores in JSON.

Return **only** the following JSON (no extra text):
{{
  "planning_coherence_reasoning": "<brief reasoning about workflow structure>",
  "multi_round_efficiency_reasoning": "<brief reasoning about execution economy>",
  "parameter_appropriateness_reasoning": "<brief reasoning about parameter choices>",
  "information_grounding_reasoning": "<brief reasoning about answer faithfulness>",
  "planning_coherence": <int 1-10>,
  "multi_round_efficiency": <int 1-10>,
  "parameter_appropriateness": <int 1-10>,
  "information_grounding": <int 1-10>
}}
"""


# ---------------------------------------------------------------------------
# Helper: format execution trace
# ---------------------------------------------------------------------------

def _format_execution_trace(execution_results: List[Dict[str, Any]]) -> str:
    """Format tool execution results into a readable trace for the judge."""
    if not execution_results:
        return "(no tool calls recorded)"

    lines = []
    current_round = None
    for i, r in enumerate(execution_results, 1):
        tool = r.get("tool", "unknown")
        if ":" in tool:
            tool = tool.split(":")[-1]
        params = r.get("parameters", {})
        success = r.get("success", False)
        round_num = r.get("round_num", 0)

        # Show round boundaries for hybrid workflow clarity
        if round_num != current_round:
            current_round = round_num
            lines.append(f"\n--- Round {round_num} ---")

        # Keep output concise: truncate long strings
        raw_output = r.get("output", r.get("result", None))
        if isinstance(raw_output, str) and len(raw_output) > 400:
            raw_output = raw_output[:400] + " ...[truncated]"
        status = "OK" if success else "FAILED"
        error = r.get("error", "")

        lines.append(f"  Step {i}: [{status}] {tool}({params})")
        if raw_output is not None:
            lines.append(f"    â†?output: {raw_output}")
        if error:
            lines.append(f"    â†?error: {error}")

    return "\n".join(lines)


def _format_workflow_structure(task: dict) -> str:
    """Format the expected execution_structure into readable text for the judge."""
    exec_struct = task.get("execution_structure", {})
    if not exec_struct:
        # Fallback: use dependency_analysis if available
        dep_analysis = task.get("dependency_analysis", "")
        if dep_analysis:
            return f"Dependency Analysis:\n{dep_analysis}"
        return "(no workflow structure provided)"

    lines = []
    total = exec_struct.get("total_tools", "?")
    lines.append(f"Total tools expected: {total}")

    parallel_stages = exec_struct.get("parallel_stages", [])
    if parallel_stages:
        lines.append("\nParallel stages (tools in same stage can run concurrently):")
        for stage in parallel_stages:
            if isinstance(stage, dict):
                stage_num = stage.get("stage", "?")
                tools = stage.get("tools", [])
                desc = stage.get("description", "")
                lines.append(f"  Stage {stage_num}: {tools}")
                if desc:
                    lines.append(f"    Reason: {desc}")

    serial_deps = exec_struct.get("serial_dependencies", [])
    if serial_deps:
        lines.append("\nSerial dependencies (must wait for upstream output):")
        for dep in serial_deps:
            if isinstance(dep, dict):
                from_tool = dep.get("from", "?")
                to_tool = dep.get("to", "?")
                flow = dep.get("data_flow", "")
                lines.append(f"  {from_tool} â†?{to_tool}")
                if flow:
                    lines.append(f"    Data flow: {flow}")

    exec_order = exec_struct.get("execution_order", "")
    if exec_order:
        lines.append(f"\nExpected execution order: {exec_order}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM Judge
# ---------------------------------------------------------------------------

class HybridWorkflowJudge:
    """
    LLM-as-judge for L4 hybrid workflow tasks.
    Evaluates: Planning Coherence, Multi-round Efficiency,
    Parameter Appropriateness, Information Grounding.
    """

    def __init__(self, llm_provider: LLMProvider) -> None:
        self.llm = llm_provider

    async def judge(
        self,
        task: dict,
        execution_results: List[Dict[str, Any]],
        final_answer: str,
    ) -> Dict[str, Any]:
        """
        Run LLM judge evaluation.

        Args:
            task: Full task dict (contains task_description, execution_structure, etc.)
            execution_results: List of tool call results with round_num
            final_answer: Agent's final text answer

        Returns dict with keys:
            planning_coherence           (int 1-10)
            multi_round_efficiency       (int 1-10)
            parameter_appropriateness    (int 1-10)
            information_grounding        (int 1-10)
            planning_coherence_reasoning           (str)
            multi_round_efficiency_reasoning       (str)
            parameter_appropriateness_reasoning    (str)
            information_grounding_reasoning        (str)
            llm_judge_score              (float, mean of all four)
        """
        task_desc = task.get("fuzzy_description") or task.get("task_description", "")
        if isinstance(task_desc, list):
            task_desc = " ".join(str(x) for x in task_desc if x)

        trace = _format_execution_trace(execution_results)
        workflow = _format_workflow_structure(task)

        prompt = _JUDGE_PROMPT_TEMPLATE.format(
            task=task_desc,
            workflow_structure=workflow,
            execution_trace=trace,
            final_answer=final_answer or "(no final answer provided)",
        )

        try:
            response = await self.llm.get_completion(_SYSTEM_PROMPT, prompt, max_tokens=2048)
            parsed = self.llm.clean_and_parse_json(response)
        except Exception as e:
            logger.error(f"[judge] LLM call or parse failed: {e}")
            return self._empty_result()

        pc = parsed.get("planning_coherence")
        me = parsed.get("multi_round_efficiency")
        pa = parsed.get("parameter_appropriateness")
        ig = parsed.get("information_grounding")

        scores = [s for s in [pc, me, pa, ig] if isinstance(s, (int, float))]
        mean_score = sum(scores) / len(scores) if scores else None

        return {
            "planning_coherence": pc,
            "multi_round_efficiency": me,
            "parameter_appropriateness": pa,
            "information_grounding": ig,
            "planning_coherence_reasoning": parsed.get("planning_coherence_reasoning", ""),
            "multi_round_efficiency_reasoning": parsed.get("multi_round_efficiency_reasoning", ""),
            "parameter_appropriateness_reasoning": parsed.get("parameter_appropriateness_reasoning", ""),
            "information_grounding_reasoning": parsed.get("information_grounding_reasoning", ""),
            "llm_judge_score": mean_score,
        }

    async def judge_batch(
        self,
        tasks: List[dict],
        max_concurrent: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Evaluate multiple tasks concurrently with rate limiting.

        Args:
            tasks: List of task dicts, each containing execution_results and final_answer
            max_concurrent: Maximum concurrent LLM calls

        Returns: List of judge results (same order as input tasks)
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _judge_one(task: dict) -> Dict[str, Any]:
            async with semaphore:
                execution_results = task.get("execution_results", [])
                final_answer = task.get("final_answer", "")
                return await self.judge(task, execution_results, final_answer)

        results = await asyncio.gather(*[_judge_one(t) for t in tasks])
        return list(results)

    @staticmethod
    def _empty_result() -> Dict[str, Any]:
        return {
            "planning_coherence": None,
            "multi_round_efficiency": None,
            "parameter_appropriateness": None,
            "information_grounding": None,
            "planning_coherence_reasoning": "",
            "multi_round_efficiency_reasoning": "",
            "parameter_appropriateness_reasoning": "",
            "information_grounding_reasoning": "",
            "llm_judge_score": None,
        }


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def aggregate_judge_scores(judge_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregate LLM judge scores across tasks.

    Returns per-dimension averages and overall score.
    """
    dims = ["planning_coherence", "multi_round_efficiency",
            "parameter_appropriateness", "information_grounding"]

    per_dim = {d: [] for d in dims}
    for r in judge_results:
        for d in dims:
            v = r.get(d)
            if isinstance(v, (int, float)):
                per_dim[d].append(v)

    agg = {}
    for d in dims:
        scores = per_dim[d]
        agg[d] = sum(scores) / len(scores) if scores else 0.0
        agg[f"{d}_count"] = len(scores)

    all_means = [r.get("llm_judge_score") for r in judge_results
                 if r.get("llm_judge_score") is not None]
    agg["llm_judge_score"] = sum(all_means) / len(all_means) if all_means else 0.0
    agg["total_judged"] = len(all_means)

    return agg


def print_judge_summary(agg: Dict[str, Any]):
    """Print LLM judge aggregated results."""
    print(f"\n{'=' * 70}")
    print("  Level-4 LLM-as-Judge Metrics â€?Hybrid Workflow")
    print(f"{'=' * 70}")

    dims = [
        ("planning_coherence", "PC", "Planning Coherence"),
        ("multi_round_efficiency", "ME", "Multi-round Efficiency"),
        ("parameter_appropriateness", "PA", "Parameter Appropriateness"),
        ("information_grounding", "IG", "Information Grounding"),
    ]

    print(f"\n  {'Dimension':<28} {'Avg':>6} {'N':>4}")
    print("  " + "-" * 42)
    for key, short, name in dims:
        avg = agg.get(key, 0.0)
        n = agg.get(f"{key}_count", 0)
        print(f"  {name:<28} {avg:>6.2f} {n:>4}")

    print("  " + "-" * 42)
    overall = agg.get("llm_judge_score", 0.0)
    total = agg.get("total_judged", 0)
    print(f"  {'Overall (mean of 4 dims)':<28} {overall:>6.2f} {total:>4}")
    print(f"{'=' * 70}")

    print()
    print("Legend (L4 LLM-Judge Dimensions):")
    print("  PC = Planning Coherence: hybrid plan correctness (parallel/serial decomposition)")
    print("  ME = Multi-round Efficiency: minimal rounds, no redundant/wasted calls")
    print("  PA = Parameter Appropriateness: parameters semantically match task constraints")
    print("  IG = Information Grounding: final answer faithful to tool outputs, no hallucination")
