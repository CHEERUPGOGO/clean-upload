#!/usr/bin/env python3
"""
Level-3 Benchmark Evaluation Script â€?Serial Tool Chain

Metrics (6 total):
  Schema Understanding:
    S_acc    Schema Compliance Rate:  schema_valid_calls / total_calls
    R_suc    Execution Success Rate:  successful_calls / total_calls

  Tool Usage Quality:
    T_f1     Tool Selection F1:      2 * Prec * Rec / (Prec + Rec)
    P_acc    Parameter Accuracy:     matched_calls / expected_calls

  Planning Efficiency:
    S_eff    Sequential Efficiency:  1 - dup_count / total_calls

  Task Completion (computed only on tasks with ground-truth target):
    R_hit    Hit Ratio:              any target ID in output items

Usage:
  python evaluate_L3_metrics.py -i <results_file_or_dir>
  python evaluate_L3_metrics.py -i <results_file_or_dir> --detail
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any

# Import schema definitions
sys.path.insert(0, str(Path(__file__).parent))
from evaluate_L1_metrics import check_param_match, detect_and_load_schema

# Will be populated dynamically in main() based on input path
AVAILABLE_TOOLS_SCHEMA: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Schema helpers (shared with L2)
# ---------------------------------------------------------------------------

_FLAT_SCHEMA: Dict[str, dict] = {}


def _rebuild_flat_schema():
    """Rebuild _FLAT_SCHEMA from current AVAILABLE_TOOLS_SCHEMA."""
    global _FLAT_SCHEMA
    _FLAT_SCHEMA.clear()
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
        return False

    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    for req in required:
        if req not in params or params[req] is None:
            return False

    for key, value in params.items():
        if key not in properties:
            continue
        expected_type_str = properties[key].get("type")
        if expected_type_str and value is not None:
            expected_types = _TYPE_MAP.get(expected_type_str)
            if expected_types and not isinstance(value, expected_types):
                if expected_type_str == "number" and isinstance(value, (int, float)):
                    continue
                return False

    return True


# ---------------------------------------------------------------------------
# Per-task metrics
# ---------------------------------------------------------------------------

def evaluate_task(task: dict, f1_threshold: float = 0.5) -> Dict[str, Any]:
    """Compute all L3 metrics for a single task."""
    results = task.get("execution_results", [])
    expected_tools = set(task.get("selected_tools", []))
    total_rounds = task.get("total_rounds", 0)
    planned_calls = task.get("planned_tool_calls", [])
    expected_calls = task.get("expected_tool_calls", planned_calls)

    # Extract target item ID from multiple possible formats
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
            "dup_count": 0,
            "tool_f1": 0.0,
            "param_accuracy": 0.0,
            "schema_compliance": 0.0,
            "success_rate": 0.0,
            "seq_efficiency": 0.0,
            "has_target": bool(target_ids),
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

        # Duplicate detection (same tool + same params)
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
        raw_output = r.get("output", r.get("result", {}))
        if isinstance(raw_output, str):
            try:
                raw_output = json.loads(raw_output)
            except (json.JSONDecodeError, TypeError):
                raw_output = {}

        if isinstance(raw_output, dict):
            if "item_id" in raw_output and "item" in raw_output:
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
    covered = actual_tools & expected_tools

    # === Schema Understanding ===

    # S_acc: Schema Compliance Rate
    schema_compliance = schema_ok_count / total_calls

    # R_suc: Execution Success Rate
    success_rate = success_count / total_calls

    # === Tool Usage Quality ===

    # T_f1: Tool Selection F1 = 2 * Prec * Rec / (Prec + Rec)
    recall = len(covered) / len(expected_tools) if expected_tools else 0.0
    precision = len(covered) / len(actual_tools) if actual_tools else 0.0
    if precision + recall > 0:
        tool_f1 = 2 * precision * recall / (precision + recall)
    else:
        tool_f1 = 0.0

    # P_acc: Parameter Accuracy (per-call, matched / expected_calls)
    param_match_count = 0
    if expected_calls:
        expected_by_tool: Dict[str, List[dict]] = {}
        for ec in expected_calls:
            tool_full = ec.get("tool", "")
            tool_short = tool_full.split(":")[-1] if ":" in tool_full else tool_full
            expected_by_tool.setdefault(tool_short, []).append(ec.get("parameters", {}))

        actual_by_tool: Dict[str, List[tuple]] = {}
        for global_idx, r in enumerate(results):
            tf = r.get("tool", "")
            ts = tf.split(":")[-1] if ":" in tf else tf
            actual_by_tool.setdefault(ts, []).append((global_idx, r))

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

    # === Planning Efficiency ===

    # S_eff: Sequential Efficiency = 1 - dup_count / total_calls
    seq_efficiency = 1.0 - dup_count / total_calls

    # === Task Completion ===

    # Hit rate: check if target ID appears in the model's FINAL SOLUTION (not intermediate tool outputs)
    has_target = bool(target_ids)
    hit_rate = 0.0
    if target_ids:
        final_solution = str(task.get("final_solution", ""))
        if final_solution:
            for tid in target_ids:
                if tid in final_solution:
                    hit_rate = 1.0
                    break

    return {
        "task_id": task.get("task_id"),
        "total_calls": total_calls,
        "total_rounds": total_rounds,
        "unique_tools": len(actual_tools),
        "expected_tools": len(expected_tools),
        "covered_tools": len(covered),
        "dup_count": dup_count,
        "schema_compliance": schema_compliance,
        "success_rate": success_rate,
        "tool_f1": tool_f1,
        "param_accuracy": param_accuracy,
        "seq_efficiency": seq_efficiency,
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
    for _, tasks in data.items():
        if isinstance(tasks, list):
            all_tasks.extend(tasks)

    if not all_tasks:
        return {"file": filepath, "tasks": 0, "metrics": {}}

    task_metrics = [evaluate_task(t) for t in all_tasks]

    n = len(task_metrics)

    # Hit metrics: only average over tasks with ground-truth target
    tasks_with_target = [m for m in task_metrics if m.get("has_target")]
    n_target = len(tasks_with_target)

    metric_keys = ["schema_compliance", "success_rate", "tool_f1",
                    "param_accuracy", "seq_efficiency"]
    agg = {k: sum(m[k] for m in task_metrics) / n for k in metric_keys}
    agg["hit_rate"] = sum(m["hit_rate"] for m in tasks_with_target) / n_target if n_target > 0 else 0.0

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

_METRIC_KEYS = ["schema_compliance", "success_rate", "tool_f1",
                "param_accuracy", "seq_efficiency", "hit_rate"]
_SHORT = ["S_acc", "R_suc", "T_f1", "P_acc", "S_eff", "R_hit"]


def print_per_task(file_result: dict):
    """Print per-task detail table."""
    tasks = file_result.get("per_task", [])
    if not tasks:
        return
    print(f"\n  {'task':>6} {'calls':>5} {'rnds':>4} {'uniq':>4} {'exp':>3} "
          f"{'cov':>3} {'dup':>3} {'tgt':>3} "
          + " ".join(f"{s:>6}" for s in _SHORT))
    print("  " + "-" * 100)
    for m in tasks:
        tgt_mark = "Y" if m.get("has_target") else "-"
        print(f"  {m['task_id']:>6} {m['total_calls']:>5} {m['total_rounds']:>4} "
              f"{m['unique_tools']:>4} {m['expected_tools']:>3} {m['covered_tools']:>3} "
              f"{m['dup_count']:>3} {tgt_mark:>3} "
              + " ".join(f"{m[k]:>6.2%}" for k in _METRIC_KEYS))


def print_summary(results: List[dict]):
    """Print summary table across files."""
    metric_header = " ".join(f"{s:>6}" for s in _SHORT)
    header = f"{'File':<50} {'N':>3} {'N_t':>3} {metric_header}"
    sep = "-" * len(header)

    print(f"\n{'=' * len(header)}")
    print("  Level-3 Benchmark Metrics â€?Serial Tool Chain")
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
        vals = " ".join(f"{agg.get(k, 0):>6.2%}" for k in _METRIC_KEYS)
        print(f"{fname:<50} {n:>3} {n_t:>3} {vals}")

    if len(results) > 1 and total_tasks > 0:
        print(sep)
        overall = {}
        # Non-hit metrics: weighted by total tasks
        non_hit_keys = ["schema_compliance", "success_rate", "tool_f1",
                        "param_accuracy", "seq_efficiency"]
        for k in non_hit_keys:
            overall[k] = sum(n * a.get(k, 0) for n, n_t, a in all_aggs) / total_tasks
        # Hit metrics: weighted by tasks_with_target
        for k in ["hit_rate"]:
            if total_target_tasks > 0:
                overall[k] = sum(n_t * a.get(k, 0) for n, n_t, a in all_aggs) / total_target_tasks
            else:
                overall[k] = 0.0
        vals = " ".join(f"{overall[k]:>6.2%}" for k in _METRIC_KEYS)
        print(f"{'OVERALL':<50} {total_tasks:>3} {total_target_tasks:>3} {vals}")

    print(f"{'=' * len(header)}")
    print()
    print("Legend (L3 Serial Metrics):")
    print("  N_t   = Number of tasks with ground-truth target item (R_hit computed only on these)")
    print("  S_acc = Schema Compliance: schema_valid_calls / total_calls")
    print("  R_suc = Execution Success Rate: successful_calls / total_calls")
    print("  T_f1  = Tool Selection F1: 2 * Prec * Rec / (Prec + Rec)")
    print("  P_acc = Parameter Accuracy: matched_calls / expected_calls")
    print("  S_eff = Sequential Efficiency: 1 - dup_count / total_calls")
    print("  R_hit = Hit Ratio: any target ID appears in output items (0 or 1)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Evaluate Level-3 benchmark results")
    parser.add_argument("-i", "--input", required=True, nargs='+',
                        help="Results JSON file(s) or directory of result files (multiple allowed)")
    parser.add_argument("--detail", action="store_true",
                        help="Show per-task detail for each file")
    args = parser.parse_args()

    # Collect all files from all inputs
    files = []
    for inp in args.input:
        input_path = Path(inp)
        if input_path.is_dir():
            found = sorted(input_path.glob("L3_*_results.json")) or sorted(input_path.glob("L3_*.json"))
            files.extend(found)
        elif input_path.is_file():
            files.append(input_path)
        else:
            print(f"Warning: {inp} not found, skipping")

    if not files:
        print(f"No result files found in {args.input}")
        sys.exit(1)

    # Auto-detect dataset and load schema for each file
    global AVAILABLE_TOOLS_SCHEMA
    AVAILABLE_TOOLS_SCHEMA = detect_and_load_schema(str(files[0]))
    _rebuild_flat_schema()

    # For each additional file, try to load its schema and merge
    for f in files[1:]:
        try:
            additional_schema = detect_and_load_schema(str(f))
            for server, tools in additional_schema.items():
                if server not in AVAILABLE_TOOLS_SCHEMA:
                    AVAILABLE_TOOLS_SCHEMA[server] = tools
            _rebuild_flat_schema()
        except Exception:
            pass

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
