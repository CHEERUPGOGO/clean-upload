"""
LLM-as-Judge Evaluator for L3 Serial Tool Chain Tasks (MCP-Bench)

Evaluates agent performance on 2 LLM-judged dimensions:
  - Grounding          (G):   final answer grounded in tool outputs, not hallucinated
  - Dependency Awareness (D): serial chain dependencies correctly propagated

Plus 4 rule-based dimensions inherited from evaluate_L3_metrics.py:
  S_acc, R_suc, T_f1, P_acc, S_eff, R_hit
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Protocol

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
    "You are an expert evaluator for AI agents that execute serial tool chains. "
    "Score strictly based on evidence in the execution trace. "
    "Be critical: default to 4-5 unless strong evidence supports higher."
)

_JUDGE_PROMPT_TEMPLATE = """\
You are evaluating an AI agent that completed a task by calling tools **one at a time** \
in a sequential chain, where each step may depend on results from the previous step.

---

## Task Description
{task}

## Execution Trace
{execution_trace}

## Agent's Final Answer
{final_answer}

---

## Scoring Dimensions

Score each dimension on a scale of **1â€?0**.

### 1. Grounding (G)
Does the agent's final answer faithfully reflect what the tools actually returned?
Penalize unsupported claims, hallucinated values, or conclusions not traceable to tool outputs.

| Score | Criterion |
|-------|-----------|
| 9â€?0  | 90-100% of factual claims are directly grounded in tool outputs |
| 7â€?   | 70-80% of claims are grounded; minor unsupported details |
| 4â€?   | 40-60% of claims are grounded; noticeable hallucination |
| 1â€?   | Less than 30% grounded; agent largely ignores tool results |

### 2. Dependency Awareness (D)
In the serial chain, does each step correctly use the output of the previous step as its input?
Penalize steps that ignore prior results, use hardcoded/wrong values, or break the information flow.

| Score | Criterion |
|-------|-----------|
| 9â€?0  | 90-100% of inter-step dependencies correctly propagated |
| 7â€?   | 70-80% of dependencies correct; one broken link |
| 4â€?   | 40-60% of dependencies correct; chain partially broken |
| 1â€?   | Less than 30% correct; agent treats steps as independent |

---

## Instructions
1. First reason briefly for each dimension.
2. Then output scores in JSON.

Return **only** the following JSON (no extra text):
{{
  "grounding_reasoning": "<brief reasoning referencing specific tool outputs>",
  "dependency_awareness_reasoning": "<brief reasoning referencing specific inter-step data flow>",
  "grounding": <int 1-10>,
  "dependency_awareness": <int 1-10>
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
    for i, r in enumerate(execution_results, 1):
        tool = r.get("tool", "unknown")
        if ":" in tool:
            tool = tool.split(":")[-1]
        params = r.get("parameters", {})
        success = r.get("success", False)
        # Keep output concise: truncate long strings
        raw_output = r.get("output", r.get("result", None))
        if isinstance(raw_output, str) and len(raw_output) > 400:
            raw_output = raw_output[:400] + " ...[truncated]"
        status = "OK" if success else "FAILED"
        error = r.get("error", "")

        lines.append(f"Step {i}: [{status}] {tool}({params})")
        if raw_output is not None:
            lines.append(f"  â†?output: {raw_output}")
        if error:
            lines.append(f"  â†?error: {error}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM Judge
# ---------------------------------------------------------------------------

class SerialChainJudge:
    """
    LLM-as-judge for serial tool chain tasks.
    Evaluates Grounding and Dependency Awareness.
    """

    def __init__(self, llm_provider: LLMProvider) -> None:
        self.llm = llm_provider

    async def judge(
        self,
        task: str,
        execution_results: List[Dict[str, Any]],
        final_answer: str,
    ) -> Dict[str, Any]:
        """
        Run LLM judge evaluation.

        Returns dict with keys:
            grounding           (int 1-10)
            dependency_awareness (int 1-10)
            grounding_reasoning           (str)
            dependency_awareness_reasoning (str)
            llm_judge_score     (float, mean of the two)
        """
        trace = _format_execution_trace(execution_results)
        prompt = _JUDGE_PROMPT_TEMPLATE.format(
            task=task,
            execution_trace=trace,
            final_answer=final_answer or "(no final answer provided)",
        )

        try:
            response = await self.llm.get_completion(_SYSTEM_PROMPT, prompt, max_tokens=1024)
            parsed = self.llm.clean_and_parse_json(response)
        except Exception as e:
            logger.error(f"[judge] LLM call or parse failed: {e}")
            return {
                "grounding": None,
                "dependency_awareness": None,
                "grounding_reasoning": "",
                "dependency_awareness_reasoning": "",
                "llm_judge_score": None,
            }

        g = parsed.get("grounding")
        d = parsed.get("dependency_awareness")
        mean_score = (g + d) / 2.0 if isinstance(g, (int, float)) and isinstance(d, (int, float)) else None

        return {
            "grounding": g,
            "dependency_awareness": d,
            "grounding_reasoning": parsed.get("grounding_reasoning", ""),
            "dependency_awareness_reasoning": parsed.get("dependency_awareness_reasoning", ""),
            "llm_judge_score": mean_score,
        }
