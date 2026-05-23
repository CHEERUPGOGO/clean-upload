#!/usr/bin/env python3
"""
Level-2 Benchmark Evaluation Script â€?Parallel Tool Calling

Metrics (aligned with paper):
  Schema Understanding:
    S_acc    Schema Compliance Rate:     schema_valid_calls / total_calls
    R_success Execution Success Rate:    successful_calls / total_calls

  Tool Usage Quality:
    T_f1     Tool Selection F1 Score:   2 * P * R / (P + R)
    P_acc    Parameter Accuracy:         matched_calls / expected_calls

  Planning Effectiveness:
    R_para   Parallel Ratio:            |R1 âˆ?expected| / max(|expected|, |R1_unique|)
    S_eff    Efficiency Score:           |expected_tools| / max(|expected_tools|, total_calls)

  Task Completion:
    R_hit    Hit Ratio:                 any target ID in output items

Usage:
  python evaluate_L2_metrics.py -i <results_file_or_dir>
  python evaluate_L2_metrics.py -i <results_file_or_dir> --detail
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any

# Import schema definitions
sys.path.insert(0, str(Path(__file__).parent))
from available_tools_schema import AVAILABLE_TOOLS_SCHEMA
from evaluate_L1_metrics import check_param_match


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

# Build flat lookup: tool_short_name -> schema
_FLAT_SCHEMA: Dict[str, dict] = {}
for _server, _tools in AVAILABLE_TOOLS_SCHEMA.items():
    for _tool_name, _schema in _tools.items():
        _FLAT_SCHEMA[_tool_name] = _schema

_TYPE_MAP = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _check_schema_compliance(tool_short: str, params: dict) -> bool:
    """Check if params comply with tool schema. Returns True if valid."""
    schema = _FLAT_SCHEMA.get(tool_short)
    if schema is None:
        return False  # unknown tool -> also covers T_valid

    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    # Check required params present
    for req in required:
        if req not in params or params[req] is None:
            return False

    # Check each provided param has correct type
    for key, value in params.items():
        if key not in properties:
            continue  # extra params are ok (server may accept them)
        expected_type_str = properties[key].get("type")
        if expected_type_str and value is not None:
            expected_types = _TYPE_MAP.get(expected_type_str)
            if expected_types and not isinstance(value, expected_types):
                # Allow int where number is expected
                if expected_type_str == "number" and isinstance(value, (int, float)):
                    continue
                return False

    return True


# ---------------------------------------------------------------------------
# Per-task metrics
# ---------------------------------------------------------------------------

def evaluate_task(task: dict, f1_threshold: float = 0.5) -> Dict[str, Any]:
    """Compute all L2 metrics for a single task."""
    results = task.get("execution_results", [])
    expected_tools = set(task.get("selected_tools", []))
    total_rounds = task.get("total_rounds", 0)
    planned_calls = task.get("planned_tool_calls", [])
    expected_calls = task.get("expected_tool_calls", planned_calls)
    # Extract target item ID from multiple possible formats:
    #   target_item_id (str/list), target_item.asin, target_item.id, etc.
    target_ids = set()
    _raw_tid = task.get("target_item_id")
    _raw_ti = task.get("target_item")
    if isinstance(_raw_tid, list):
        target_ids = {str(v) for v in _raw_tid if v}
    elif _raw_tid:
        target_ids = {str(_raw_tid)}
    elif isinstance(_raw_ti, dict):
        for _k in ("asin", "id", "item_id", "venue_id", "business_id"):
            if _raw_ti.get(_k):
                target_ids.add(str(_raw_ti[_k]))

    if not results:
        return {
            "task_id": task.get("task_id"),
            "total_calls": 0,
            "total_rounds": 0,
            "unique_tools": 0,
            "expected_tools": len(expected_tools),
            "covered_tools": 0,
            "max_parallel": 0,
            "r1_count": 0,
            "schema_compliance": 0.0,
            "success_rate": 0.0,
            "tool_f1": 0.0,
            "param_accuracy": 0.0,
            "r1_parallel_ratio": 0.0,
            "efficiency": 0.0,
            "hit_rate": 0.0,
        }

    # Parse calls
    calls_by_round: Dict[int, List[str]] = {}
    unique_call_keys = set()
    dup_count = 0
    success_count = 0
    schema_ok_count = 0
    actual_tools = set()
    all_output_items = []  # collect item IDs from results

    for r in results:
        tool_full = r.get("tool", "")
        tool_short = tool_full.split(":")[-1] if ":" in tool_full else tool_full
        params = r.get("parameters", {})
        round_num = r.get("round_num", 0)

        actual_tools.add(tool_short)

        # Duplicate detection
        call_key = (tool_short, json.dumps(params, sort_keys=True, default=str))
        if call_key in unique_call_keys:
            dup_count += 1
        unique_call_keys.add(call_key)

        # Per-round tracking
        calls_by_round.setdefault(round_num, []).append(tool_short)

        # Success: requires success=True, no error, and non-empty result
        raw_result = r.get("result", r.get("output"))
        result_is_empty = (
            raw_result is None or
            raw_result == "" or
            raw_result == [] or
            raw_result == {} or
            (isinstance(raw_result, str) and raw_result.strip() in ("", "null", "[]", "{}"))
        )
        if r.get("success", False) and not r.get("error") and not result_is_empty:
            success_count += 1

        # Schema compliance
        if _check_schema_compliance(tool_short, params):
            schema_ok_count += 1

        # Collect output item IDs for hit rate
        # Note: "result" is often a stringified JSON, need to parse it
        raw_output = r.get("output", r.get("result", {}))
        if isinstance(raw_output, str):
            try:
                raw_output = json.loads(raw_output)
            except (json.JSONDecodeError, TypeError):
                raw_output = {}

        if isinstance(raw_output, dict):
            # Format: {"items": [...]} or {"item_id": "...", "item": {...}}
            if "item_id" in raw_output and "item" in raw_output:
                # get_item_details format
                iid = raw_output.get("item_id")
                if iid:
                    all_output_items.append(str(iid))
            for key in ("items", "item_ids", "recommendations", "results", "asins",
                        "venue_ids", "business_ids"):
                val = raw_output.get(key, [])
                if isinstance(val, list):
                    for v in val:
                        if isinstance(v, dict):
                            _id = v.get("asin", v.get("item_id", v.get("venue_id",
                                   v.get("business_id", v.get("id", "")))))
                            if _id:
                                all_output_items.append(str(_id))
                        elif v:
                            all_output_items.append(str(v))
        elif isinstance(raw_output, list):
            for item in raw_output:
                if isinstance(item, dict):
                    _id = item.get("asin", item.get("item_id", item.get("venue_id",
                           item.get("business_id", item.get("id", "")))))
                    if _id:
                        all_output_items.append(str(_id))
                elif item:
                    all_output_items.append(str(item))

    total_calls = len(results)

    # Round-1 specific analysis
    r1_tools = calls_by_round.get(1, [])
    r1_count = len(r1_tools)

    # === Schema Understanding ===

    # S_acc: Schema Compliance Rate (call-level)
    schema_rate = schema_ok_count / total_calls if total_calls > 0 else 0.0

    # R_success: Execution Success Rate (call-level)
    success_rate = success_count / total_calls if total_calls > 0 else 0.0

    # === Tool Usage Quality ===

    # T_f1: Tool Selection F1 Score
    if expected_tools:
        recall = len(actual_tools & expected_tools) / len(expected_tools)
    else:
        recall = 1.0 if total_calls > 0 else 0.0
    precision = len(actual_tools & expected_tools) / len(actual_tools) if actual_tools else 0.0
    if precision + recall > 0:
        tool_f1 = 2 * precision * recall / (precision + recall)
    else:
        tool_f1 = 0.0

    # P_acc: Parameter Accuracy (per-call, matched / expected_calls)
    param_match_count = 0
    if expected_calls:
        # Build lookup: tool_short -> list of expected param dicts
        expected_by_tool: Dict[str, List[dict]] = {}
        for ec in expected_calls:
            tool_full = ec.get("tool", "")
            tool_short = tool_full.split(":")[-1] if ":" in tool_full else tool_full
            expected_by_tool.setdefault(tool_short, []).append(ec.get("parameters", {}))

        # Build lookup: tool_short -> list of (global_idx, result_dict)
        actual_by_tool: Dict[str, List[tuple]] = {}
        for global_idx, r in enumerate(results):
            tf = r.get("tool", "")
            ts = tf.split(":")[-1] if ":" in tf else tf
            actual_by_tool.setdefault(ts, []).append((global_idx, r))

        # For each expected call, find best matching actual call
        matched_actual = set()
        for tool_short, exp_params_list in expected_by_tool.items():
            for exp_params in exp_params_list:
                for global_idx, ar in actual_by_tool.get(tool_short, []):
                    if global_idx in matched_actual:
                        continue
                    if check_param_match(ar.get("parameters", {}), exp_params,
                                        tool_name=tool_short, f1_threshold=f1_threshold):
                        param_match_count += 1
                        matched_actual.add(global_idx)
                        break

    param_accuracy = param_match_count / len(expected_calls) if expected_calls else 0.0

    # === Planning Effectiveness ===

    # R_para: Parallel Ratio = |R1 âˆ?expected| / max(|expected|, |R1_unique|), ideal = 1.0
    # Penalizes both missing expected tools and invoking extra tools in R1
    r1_unique = set(r1_tools)
    r1_intersection = len(r1_unique & expected_tools)
    r1_par_denom = max(len(expected_tools), len(r1_unique))
    r1_parallel_ratio = r1_intersection / r1_par_denom if r1_par_denom > 0 else 0.0

    # S_eff: Efficiency Score = |expected| / max(|expected|, total_calls), ideal = 1.0
    # When total_calls <= |expected|: = |expected|/|expected| = 1.0 (optimal, no excess calls)
    # When total_calls > |expected|: = |expected|/total_calls < 1.0 (penalizes redundant calls)
    expected_n = len(expected_tools)
    efficiency = expected_n / max(expected_n, total_calls) if total_calls > 0 else 0.0

    # === Task Completion ===

    # Hit Rate: any target appears in output items
    # NOTE: has_target indicates whether this task has a ground-truth target.
    # Aggregation should only average hit_rate over tasks where has_target=True.
    has_target = bool(target_ids)
    hit_rate = 0.0
    if target_ids and all_output_items:
        output_set = set(all_output_items)
        if target_ids & output_set:
            hit_rate = 1.0

    return {
        "task_id": task.get("task_id"),
        "total_calls": total_calls,
        "total_rounds": total_rounds,
        "unique_tools": len(actual_tools),
        "expected_tools": len(expected_tools),
        "covered_tools": len(actual_tools & expected_tools),
        "max_parallel": max(len(v) for v in calls_by_round.values()) if calls_by_round else 0,
        "r1_count": r1_count,
        "dup_count": dup_count,
        "schema_compliance": schema_rate,
        "success_rate": success_rate,
        "tool_f1": tool_f1,
        "param_accuracy": param_accuracy,
        "r1_parallel_ratio": r1_parallel_ratio,
        "efficiency": efficiency,
        "has_target": has_target,
        "hit_rate": hit_rate,
    }


# ---------------------------------------------------------------------------
# File-level evaluation
# ---------------------------------------------------------------------------

def evaluate_file(filepath: str) -> Dict[str, Any]:
    """Evaluate all tasks in a single results JSON file."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Results are keyed by model name
    all_tasks = []
    for model_name, tasks in data.items():
        if isinstance(tasks, list):
            all_tasks.extend(tasks)

    if not all_tasks:
        return {"file": filepath, "tasks": 0, "metrics": {}}

    task_metrics = [evaluate_task(t) for t in all_tasks]

    # Aggregate
    n = len(task_metrics)

    # Hit metrics: only average over tasks that have a ground-truth target
    tasks_with_target = [m for m in task_metrics if m.get("has_target")]
    n_target = len(tasks_with_target)

    agg = {
        "schema_compliance": sum(m["schema_compliance"] for m in task_metrics) / n,
        "success_rate": sum(m["success_rate"] for m in task_metrics) / n,
        "tool_f1": sum(m["tool_f1"] for m in task_metrics) / n,
        "param_accuracy": sum(m["param_accuracy"] for m in task_metrics) / n,
        "r1_parallel_ratio": sum(m["r1_parallel_ratio"] for m in task_metrics) / n,
        "efficiency": sum(m["efficiency"] for m in task_metrics) / n,
        "hit_rate": sum(m["hit_rate"] for m in tasks_with_target) / n_target if n_target > 0 else 0.0,
    }

    return {
        "file": os.path.basename(filepath),
        "tasks": n,
        "tasks_with_target": n_target,
        "per_task": task_metrics,
        "aggregate": agg,
    }


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------

def print_per_task(file_result: dict):
    """Print per-task detail table."""
    tasks = file_result.get("per_task", [])
    if not tasks:
        return
    print(f"\n  {'task':>6} {'calls':>5} {'rnds':>4} {'uniq':>4} {'exp':>3} "
          f"{'cov':>3} {'maxP':>4} {'R1':>3} {'dup':>3} "
          f"{'S_acc':>6} {'R_suc':>6} {'T_f1':>6} {'P_acc':>6} "
          f"{'R_par':>6} {'S_eff':>6} {'R_hit':>6}")
    print("  " + "-" * 105)
    for m in tasks:
        print(f"  {m['task_id']:>6} {m['total_calls']:>5} {m['total_rounds']:>4} "
              f"{m['unique_tools']:>4} {m['expected_tools']:>3} {m['covered_tools']:>3} "
              f"{m['max_parallel']:>4} {m['r1_count']:>3} {m['dup_count']:>3} "
              f"{m['schema_compliance']:>6.0%} {m['success_rate']:>6.0%} "
              f"{m['tool_f1']:>6.0%} {m['param_accuracy']:>6.0%} "
              f"{m['r1_parallel_ratio']:>6.0%} {m['efficiency']:>6.0%} "
              f"{m['hit_rate']:>6.0%}")


def print_summary(results: List[dict]):
    """Print summary table across files."""
    header = (f"{'File':<50} {'N':>3} {'N_t':>3} {'S_acc':>6} {'R_suc':>6} {'T_f1':>6} {'P_acc':>6} "
              f"{'R_par':>6} {'S_eff':>6} {'R_hit':>6}")
    sep = "-" * len(header)

    print(f"\n{'=' * len(header)}")
    print("  Level-2 Benchmark Metrics â€?Parallel Tool Calling")
    print(f"{'=' * len(header)}")
    print(header)
    print(sep)

    all_aggs = []
    total_tasks = 0
    total_target_tasks = 0

    for r in results:
        agg = r.get("aggregate", {})
        n = r["tasks"]
        n_t = r.get("tasks_with_target", 0)
        total_tasks += n
        total_target_tasks += n_t
        all_aggs.append((n, n_t, agg))

        fname = r["file"]
        if len(fname) > 49:
            fname = "..." + fname[-46:]
        print(f"{fname:<50} {n:>3} {n_t:>3} "
              f"{agg.get('schema_compliance', 0):>6.0%} "
              f"{agg.get('success_rate', 0):>6.0%} "
              f"{agg.get('tool_f1', 0):>6.0%} "
              f"{agg.get('param_accuracy', 0):>6.0%} "
              f"{agg.get('r1_parallel_ratio', 0):>6.0%} "
              f"{agg.get('efficiency', 0):>6.0%} "
              f"{agg.get('hit_rate', 0):>6.0%}")

    if len(results) > 1 and total_tasks > 0:
        print(sep)
        overall = {}
        # Non-hit metrics: weighted by total tasks
        for key in ["schema_compliance", "success_rate", "tool_f1", "param_accuracy",
                     "r1_parallel_ratio", "efficiency"]:
            overall[key] = sum(n * a.get(key, 0) for n, n_t, a in all_aggs) / total_tasks
        # Hit metrics: weighted by tasks_with_target
        for key in ["hit_rate"]:
            if total_target_tasks > 0:
                overall[key] = sum(n_t * a.get(key, 0) for n, n_t, a in all_aggs) / total_target_tasks
            else:
                overall[key] = 0.0
        print(f"{'OVERALL':<50} {total_tasks:>3} {total_target_tasks:>3} "
              f"{overall['schema_compliance']:>6.0%} "
              f"{overall['success_rate']:>6.0%} "
              f"{overall['tool_f1']:>6.0%} "
              f"{overall['param_accuracy']:>6.0%} "
              f"{overall['r1_parallel_ratio']:>6.0%} "
              f"{overall['efficiency']:>6.0%} "
              f"{overall['hit_rate']:>6.0%}")

    print(f"{'=' * len(header)}")
    print()
    print("Legend (L2 Parallel Metrics):")
    print("  N_t   = Number of tasks with ground-truth target item (R_hit computed only on these)")
    print("  S_acc = Schema Compliance: schema_valid_calls / total_calls")
    print("  R_suc = Execution Success Rate: successful_calls / total_calls")
    print("  T_f1  = Tool Selection F1: 2 * Prec * Recall / (Prec + Recall)")
    print("  P_acc = Parameter Accuracy: matched_calls / expected_calls")
    print("  R_par = Parallel Ratio: |R1 âˆ?expected| / max(|expected|, |R1|) (ideal=1.0)")
    print("  S_eff = Efficiency Score: |expected| / max(|expected|, total_calls) (ideal=1.0)")
    print("  R_hit = Hit Ratio: any target ID appears in output items (0 or 1)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Evaluate Level-2 benchmark results")
    parser.add_argument("-i", "--input", required=True,
                        help="Results JSON file or directory of result files")
    parser.add_argument("--detail", action="store_true",
                        help="Show per-task detail for each file")
    args = parser.parse_args()

    input_path = Path(args.input)
    files = []

    if input_path.is_dir():
        files = sorted(input_path.glob("*_results.json"))
    elif input_path.is_file():
        files = [input_path]
    else:
        print(f"Error: {args.input} not found")
        sys.exit(1)

    if not files:
        print(f"No result files found in {args.input}")
        sys.exit(1)

    results = []
    for f in files:
        r = evaluate_file(str(f))
        results.append(r)
        if args.detail:
            print(f"\n--- {r['file']} ({r['tasks']} tasks) ---")
            print_per_task(r)

    print_summary(results)


if __name__ == "__main__":
    main()
