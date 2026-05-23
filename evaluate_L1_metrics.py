#!/usr/bin/env python3
"""
Evaluate tool call metrics from benchmark results.

All metrics are per-task (denominator = total_tasks):
1. T_valid  - Tool Name Valid Rate:    predicted tool name �?available tool set
2. T_acc    - Tool Selection Accuracy: predicted tool == ground-truth tool
3. S_acc    - Schema Compliance Rate:  arguments conform to tool's API schema
4. P_acc    - Parameter Accuracy:      arguments match ground-truth parameters
5. R_success- Execution Success Rate:  tool call executes without runtime error
"""

import json
import argparse
import importlib
from typing import Dict, Any

try:
    import jsonschema
    from jsonschema import ValidationError
except ImportError:
    jsonschema = None
    ValidationError = Exception

# Will be set dynamically based on input path
AVAILABLE_TOOLS_SCHEMA = {}


def detect_and_load_schema(input_path: str) -> Dict[str, Any]:
    """Auto-detect dataset from input path and load corresponding schema."""
    path_lower = input_path.lower()
    if "foursquare" in path_lower:
        module_name = "available_tools_schema_foursquare"
    elif "yelp" in path_lower:
        module_name = "available_tools_schema_yelp"
    else:
        module_name = "available_tools_schema_amazon"
    
    try:
        mod = importlib.import_module(module_name)
        schema = mod.AVAILABLE_TOOLS_SCHEMA
        dataset = module_name.replace("available_tools_schema_", "")
        print(f"  [Auto-detected dataset: {dataset}, loaded {module_name}.py]")
        return schema
    except ImportError:
        # Fallback to the current available_tools_schema.py
        from available_tools_schema import AVAILABLE_TOOLS_SCHEMA as fallback
        print(f"  [Warning: {module_name}.py not found, using available_tools_schema.py]")
        return fallback

def normalize_tool_name(tool_name: str) -> tuple:
    """Extract (server, tool) from 'server:tool' format."""
    if ":" in tool_name:
        return tool_name.split(":", 1)
    return None, tool_name

def compute_f1_score(str1: str, str2: str) -> float:
    """
    Compute F1 score between two keyword strings.
    str1 is treated as GT keywords, str2 as actual.
    F1 = 2 * P * R / (P + R), where P = |overlap|/|ACT|, R = |overlap|/|GT|.
    """
    import re
    
    stopwords = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be'
    }
    
    def tokenize(s: str) -> set:
        tokens = re.findall(r'\b\w+\b', s.lower())
        return set(t for t in tokens if t not in stopwords and len(t) > 1)
    
    gt_tokens = tokenize(str1)
    act_tokens = tokenize(str2)
    
    if not gt_tokens and not act_tokens:
        return 1.0
    if not gt_tokens or not act_tokens:
        return 0.0
    
    overlap = gt_tokens & act_tokens
    if not overlap:
        return 0.0
    
    precision = len(overlap) / len(act_tokens)
    recall = len(overlap) / len(gt_tokens)
    return 2 * precision * recall / (precision + recall)

def remove_symbols(text, symbols=None):
    if symbols is None:
        # 默认符号列表
        symbols = ' !"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~'
    # 移除指定符号
    return ''.join(char for char in text if char not in symbols)
    
def normalize_text(text: Any) -> str:
    """Normalize text fields"""
    if text is None:
        return ""
    if isinstance(text, list):
        return " ".join(str(x) for x in text if x)
    if isinstance(text, dict):
        return " ".join(str(v) for v in text.values() if v)
    # Normalize numbers: treat 15.0 and 15 as equal
    if isinstance(text, (int, float)):
        if isinstance(text, float) and text == int(text):
            return str(int(text))
        return str(text)
    if isinstance(text, str):
        # remove all whitespace
        return remove_symbols(text)
    return str(text).strip()

def normalize_location_input(location) -> list[float]:
    """
    检测和转换各种格式的location输入为标准格�?[latitude, longitude]
    
    支持的输入格式：
    1. 字符串格�? "27.9959006736, -82.5791342843"
    2. 列表格式: ["27.9959006736, -82.5791342843"]
    3. 标准格式: [27.9959006736, -82.5791342843]
    4. 字典格式: {"latitude": 27.9959006736, "longitude": -82.5791342843}
    5. 字典格式: {"lat": 27.9959006736, "lng": -82.5791342843}
    
    Args:
        location: 各种格式的location输入
    
    Returns:
        标准格式 [latitude, longitude]，其中latitude和longitude都是float
    
    Raises:
        ValueError: 当输入格式无法解析时
    """
    if location is None or location == "None":
        return None
    
    try:
        # 情况1: 字符串格�?"lat, lng"
        if isinstance(location, str):
            parts = location.strip().split(',')
            if len(parts) == 2:
                lat = float(parts[0].strip())
                lng = float(parts[1].strip())
                return [lat, lng]
        
        # 情况2: 列表格式
        elif isinstance(location, list):
            if len(location) == 0:
                return None
            
            # 子情�?.1: ["lat, lng"] 单个字符�?            if len(location) == 1 and isinstance(location[0], str):
                parts = location[0].strip().split(',')
                if len(parts) == 2:
                    lat = float(parts[0].strip())
                    lng = float(parts[1].strip())
                    return [lat, lng]
            
            # 子情�?.2: [lat, lng] 标准格式
            elif len(location) == 2:
                lat = float(location[0])
                lng = float(location[1])
                return [lat, lng]
        
        # 情况3: 字典格式
        elif isinstance(location, dict):
            # 尝试不同的键�?            lat_keys = ['latitude', 'lat']
            lng_keys = ['longitude', 'lng', 'lon']
            
            lat = None
            lng = None
            
            for key in lat_keys:
                if key in location:
                    lat = float(location[key])
                    break
            
            for key in lng_keys:
                if key in location:
                    lng = float(location[key])
                    break
            
            if lat is not None and lng is not None:
                return [lat, lng]
        
        raise ValueError(f"Cannot decode location format: {location}")
    
    except (ValueError, IndexError, TypeError) as e:
        raise ValueError(f"location error: {location}, error: {e}")

def check_param_match(actual: Dict, expected: Dict, tool_name: str = "", f1_threshold: float = 0.5) -> bool:
    """
    Check if actual parameters match expected (ignoring extra params in actual).
    
    For keyword search tools (search_keyword, item2item_search), use F1 score 
    for the query/query_text parameter.
    
    Special rule for attribute filters: If expected value is "None", actual can be:
    - "None" (string)
    - 0 (number)
    - not present in actual dict
    All these cases are considered correct.
    """
    keyword_tools = {"search_keyword", "search_businesses", "search_pois", "filter_businesses", "filter_pois", "search_reviews", "find_businesses", "filter_items_by_attributes"}
    query_params = {"query", "query_text", "categories", "keywords", "brand"}
    
    # Tools where query and categories are interchangeable search intents
    query_categories_interchangeable = {"find_businesses"}
    
    # For search_reviews: accept "both" when expected is "opinion" or "summary"
    search_in_flexible_tools = {"search_reviews"}
    
    # For google_geo: address+city are flexible (city can be merged into address,
    # or city can have state abbreviation appended like "Philadelphia, PA")
    geo_flexible_tools = {"google_geo"}

    # Special handling for google_geo: check address+city as a combined string
    if tool_name in geo_flexible_tools and ("address" in expected or "city" in expected):
        exp_address = expected.get("address", "")
        exp_city = expected.get("city", "")
        exp_full = (exp_address + ", " + exp_city).strip(", ") if exp_city else exp_address
        
        act_address = actual.get("address", "")
        act_city = actual.get("city", "")
        act_full = (act_address + ", " + act_city).strip(", ") if act_city else act_address
        
        # Normalize: lowercase, strip whitespace, remove state abbreviations for comparison
        import re as _re
        def _norm_geo(s):
            s = s.lower().strip()
            s = _re.sub(r',\s*(al|ak|az|ar|ca|co|ct|de|fl|ga|hi|id|il|in|ia|ks|ky|la|me|md|ma|mi|mn|ms|mo|mt|ne|nv|nh|nj|nm|ny|nc|nd|oh|ok|or|pa|ri|sc|sd|tn|tx|ut|vt|va|wa|wv|wi|wy)$', '', s)
            return _re.sub(r'\s+', ' ', s).strip()
        
        if _norm_geo(exp_full) != _norm_geo(act_full):
            return False
        
        # Check remaining params (skip address and city since we already handled them)
        for key, val in expected.items():
            if key in ("address", "city"):
                continue
            if val == "None":
                if key in actual and actual[key] not in ["None", 0, None]:
                    return False
                continue
            if key not in actual or normalize_text(actual[key]) != normalize_text(val):
                return False
        return True

    for key, val in expected.items():
        # If expected value is "None", check if actual is None, 0, or missing
        if val == "None":
            if key in actual:
                actual_val = actual[key]
                # Accept "None" string or 0 (number)
                if actual_val not in ["None", 0, None]:
                    return False
            # If key not in actual, that's also acceptable
            continue
        
        # Special handling: search_in parameter for search_reviews
        # Accept "both" as correct when expected is "opinion" or "summary"
        if key == "search_in" and tool_name in search_in_flexible_tools:
            actual_val = actual.get(key)
            if actual_val == val:
                continue
            if actual_val == "both" and val in ("opinion", "summary"):
                continue
            return False
        
        # For keyword tools, use F1 score for query parameters
        if tool_name in keyword_tools and key in query_params:

            if key == "location":
                # Normalize location input
                expected_location = normalize_location_input(val)
                actual_location = normalize_location_input(actual[key])
                if expected_location != actual_location:
                    return False
                continue

            if tool_name == "search_businesses" and key == "query":
                for query in val.split(','):
                    if query not in expected[key]:
                        # check if each query is in expected queries
                        return False
                continue
            if tool_name == "filter_businesses" and key == "categories":
                for category in val.split(','):
                    if category not in expected[key]:
                        # check if each category is in expected categories
                        return False
                continue

            # For find_businesses: query and categories are interchangeable.
            # If expected has "query" but actual only has "categories" (or vice versa),
            # compare them with Jaccard similarity.
            if tool_name in query_categories_interchangeable and key in ("query", "categories"):
                if key in actual:
                    # Direct match available
                    actual_val = str(actual[key])
                else:
                    # Fallback: try the other field
                    alt_key = "categories" if key == "query" else "query"
                    if alt_key in actual:
                        actual_val = str(actual[alt_key])
                    else:
                        return False
                similarity = compute_f1_score(str(val), actual_val)
                if similarity < f1_threshold:
                    return False
                continue

            if key not in actual:
                return False
            
            expected_query = str(val)
            actual_query = str(actual[key])
            similarity = compute_f1_score(expected_query, actual_query)
            if similarity < f1_threshold:
                return False
        else:
            if key not in actual:
                return False
            actual_val = actual[key]
            # Type mismatch check: string vs numeric should fail
            # e.g., GT "234" (str) vs actual 234 (int) is a type error
            if isinstance(val, str) and isinstance(actual_val, (int, float)):
                return False
            if isinstance(val, (int, float)) and isinstance(actual_val, str):
                # Allow string representation of numbers (e.g., GT=15, actual="15")
                try:
                    if float(actual_val) != float(val):
                        return False
                except (ValueError, TypeError):
                    return False
                continue
            if normalize_text(actual_val) != normalize_text(val):
                return False
    
    return True


def evaluate_results(results_file: str, verbose: bool = False, jaccard_threshold: float = 0.5, tools_schema: Dict = None) -> Dict[str, Any]:
    """Evaluate metrics from results file. All metrics are per-task."""
    global AVAILABLE_TOOLS_SCHEMA
    schema_dict = tools_schema if tools_schema is not None else AVAILABLE_TOOLS_SCHEMA
    
    with open(results_file, 'r', encoding='utf-8') as f:
        results = json.load(f)
    
    metrics = {}
    
    for model_name, tasks in results.items():
        total_tasks = len(tasks)
        # All counters are per-task (out of total_tasks)
        valid_tool_tasks = 0       # T_valid: tool name in available set
        correct_tool_tasks = 0     # T_acc:   tool == GT tool
        schema_ok_tasks = 0        # S_acc:   args conform to schema
        param_match_tasks = 0      # P_acc:   args match GT
        exec_success_tasks = 0     # R_success: execution succeeded
        
        for task in tasks:
            expected_calls = task.get("expected_tool_calls", [])
            execution_results = task.get("execution_results", [])
            
            # If model produced no tool call, all metrics = 0 for this task
            if not execution_results:
                continue
            
            # Use the first tool call for evaluation
            actual = execution_results[0]
            tool_full = actual.get("tool", "")
            server, actual_tool = normalize_tool_name(tool_full)
            if not server:
                server = actual.get("server", "")
            actual_params = actual.get("parameters", {})
            success = actual.get("success", False)
            
            # --- T_valid: is the predicted tool in the available tool set? ---
            tool_is_valid = (server in schema_dict and 
                           actual_tool in schema_dict.get(server, {}))
            if tool_is_valid:
                valid_tool_tasks += 1
            
            # --- S_acc: do the arguments conform to the tool's schema? ---
            if tool_is_valid:
                schema = schema_dict[server][actual_tool]
                try:
                    if jsonschema is not None:
                        jsonschema.validate(actual_params, schema)
                    else:
                        valid_keys = set(schema.get("properties", {}).keys())
                        if not all(p in valid_keys for p in actual_params.keys()):
                            raise ValueError("Invalid parameter name")
                    schema_ok_tasks += 1
                except (ValidationError, ValueError, Exception):
                    pass
            
            # --- R_success: did the tool execute successfully? ---
            # Success requires: success=True, no error, and non-empty result
            result = actual.get("result", actual.get("output"))
            result_is_empty = (
                result is None or
                result == "" or
                result == [] or
                result == {} or
                (isinstance(result, str) and result.strip() in ("", "null", "[]", "{}"))
            )
            if success and not result_is_empty:
                exec_success_tasks += 1
            
            # --- T_acc and P_acc: compare with ground truth ---
            if expected_calls:
                exp = expected_calls[0]
                exp_tool = exp.get("tool", "")
                
                if exp_tool == actual_tool:
                    correct_tool_tasks += 1
                    
                    # P_acc: only check if tool selection is correct
                    exp_params = exp.get("parameters", {})
                    if check_param_match(actual_params, exp_params, 
                                        tool_name=actual_tool, 
                                        f1_threshold=jaccard_threshold):
                        param_match_tasks += 1
                    
                    if verbose:
                        print(f"Task {task.get('task_id')}: Tool=OK, Params={'OK' if param_match_tasks else 'FAIL'}")
                elif verbose:
                    print(f"Task {task.get('task_id')}: Tool=WRONG (exp={exp_tool}, act={actual_tool})")
        
        metrics[model_name] = {
            "total_tasks": total_tasks,
            "T_valid": valid_tool_tasks / total_tasks if total_tasks > 0 else 0,
            "T_acc": correct_tool_tasks / total_tasks if total_tasks > 0 else 0,
            "S_acc": schema_ok_tasks / total_tasks if total_tasks > 0 else 0,
            "P_acc": param_match_tasks / total_tasks if total_tasks > 0 else 0,
            "R_success": exec_success_tasks / total_tasks if total_tasks > 0 else 0,
        }
    
    return metrics


def print_metrics(metrics: Dict[str, Any]):
    """Print metrics in formatted table."""
    print("\n" + "=" * 80)
    print("Evaluation Metrics")
    print("=" * 80)
    
    for model_name, m in metrics.items():
        print(f"\nModel: {model_name}")
        print("-" * 40)
        print(f"  Total tasks:  {m['total_tasks']}")
        print()
        print(f"  T_valid   (Tool Name Valid Rate):     {m['T_valid']*100:6.2f}%")
        print(f"  T_acc     (Tool Selection Accuracy):  {m['T_acc']*100:6.2f}%")
        print(f"  S_acc     (Schema Compliance Rate):   {m['S_acc']*100:6.2f}%")
        print(f"  P_acc     (Parameter Accuracy):       {m['P_acc']*100:6.2f}%")
        print(f"  R_success (Execution Success Rate):   {m['R_success']*100:6.2f}%")
    
    print("\n" + "=" * 80)


def evaluate_directory(dir_path: str, verbose: bool = False, jaccard_threshold: float = 0.5, tools_schema: Dict = None) -> Dict[str, Any]:
    """Evaluate all JSON result files in a directory. Returns per-file and aggregated metrics."""
    import glob
    import os

    json_files = sorted(glob.glob(os.path.join(dir_path, "*.json")))
    if not json_files:
        print(f"No JSON files found in {dir_path}")
        return {}

    per_file = {}
    agg = {}

    for fpath in json_files:
        fname = os.path.basename(fpath)
        try:
            file_metrics = evaluate_results(fpath, verbose, jaccard_threshold, tools_schema=tools_schema)
        except Exception as e:
            print(f"  SKIP {fname}: {e}")
            continue

        per_file[fname] = file_metrics

        for model_name, m in file_metrics.items():
            if model_name not in agg:
                agg[model_name] = {
                    "total_tasks": 0,
                    "valid_tool_tasks": 0, "correct_tool_tasks": 0,
                    "schema_ok_tasks": 0, "param_match_tasks": 0,
                    "exec_success_tasks": 0
                }
            a = agg[model_name]
            tt = m["total_tasks"]
            a["total_tasks"] += tt
            a["valid_tool_tasks"] += round(m["T_valid"] * tt)
            a["correct_tool_tasks"] += round(m["T_acc"] * tt)
            a["schema_ok_tasks"] += round(m["S_acc"] * tt)
            a["param_match_tasks"] += round(m["P_acc"] * tt)
            a["exec_success_tasks"] += round(m["R_success"] * tt)

    overall = {}
    for model_name, a in agg.items():
        tt = a["total_tasks"]
        overall[model_name] = {
            "total_tasks": tt,
            "T_valid": a["valid_tool_tasks"] / tt if tt > 0 else 0,
            "T_acc": a["correct_tool_tasks"] / tt if tt > 0 else 0,
            "S_acc": a["schema_ok_tasks"] / tt if tt > 0 else 0,
            "P_acc": a["param_match_tasks"] / tt if tt > 0 else 0,
            "R_success": a["exec_success_tasks"] / tt if tt > 0 else 0,
        }

    return {"per_file": per_file, "overall": overall}


def print_directory_metrics(dir_metrics: Dict[str, Any]):
    """Print per-file summary table and overall metrics."""
    import os
    per_file = dir_metrics.get("per_file", {})
    overall = dir_metrics.get("overall", {})

    if not per_file:
        print("No results to display.")
        return

    first_file_metrics = next(iter(per_file.values()))
    model_name = next(iter(first_file_metrics.keys()))

    print(f"\n{'='*120}")
    print(f"  Per-File Metrics for: {model_name}")
    print(f"{'='*120}")
    print(f"{'File':<52} {'Tasks':>5} {'T_valid':>9} {'T_acc':>8} {'S_acc':>8} {'P_acc':>8} {'R_succ':>8}")
    print("-" * 120)

    for fname, file_metrics in per_file.items():
        m = file_metrics.get(model_name, {})
        short = fname.replace("_runner_format", "").replace(f"_{model_name}_results", "").replace(".json", "")
        if len(short) > 49:
            short = "..." + short[-46:]
        print(f"{short:<52} {m.get('total_tasks',0):>5} "
              f"{m.get('T_valid',0)*100:>8.2f}% "
              f"{m.get('T_acc',0)*100:>7.2f}% "
              f"{m.get('S_acc',0)*100:>7.2f}% "
              f"{m.get('P_acc',0)*100:>7.2f}% "
              f"{m.get('R_success',0)*100:>7.2f}%")

    if model_name in overall:
        m = overall[model_name]
        print("-" * 120)
        print(f"{'OVERALL':<52} {m['total_tasks']:>5} "
              f"{m['T_valid']*100:>8.2f}% "
              f"{m['T_acc']*100:>7.2f}% "
              f"{m['S_acc']*100:>7.2f}% "
              f"{m['P_acc']*100:>7.2f}% "
              f"{m['R_success']*100:>7.2f}%")
    print("=" * 120)


def main():
    parser = argparse.ArgumentParser(description='Evaluate benchmark metrics')
    parser.add_argument('-i', '--input', required=True,
                        help='Input results JSON file or directory containing result JSON files')
    parser.add_argument('-o', '--output', help='Output metrics JSON file')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('-j', '--jaccard-threshold', type=float, default=0.5, 
                        help='F1 score threshold for keyword matching (default: 0.5)')
    
    args = parser.parse_args()
    
    # Auto-detect dataset and load corresponding schema
    tools_schema = detect_and_load_schema(args.input)
    
    import os
    if os.path.isdir(args.input):
        dir_metrics = evaluate_directory(args.input, args.verbose, args.jaccard_threshold, tools_schema=tools_schema)
        print_directory_metrics(dir_metrics)
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(dir_metrics, f, indent=2, ensure_ascii=False)
            print(f"\nMetrics saved to {args.output}")
    else:
        metrics = evaluate_results(args.input, args.verbose, args.jaccard_threshold, tools_schema=tools_schema)
        print_metrics(metrics)
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(metrics, f, indent=2, ensure_ascii=False)
            print(f"\nMetrics saved to {args.output}")


if __name__ == "__main__":
    main()

