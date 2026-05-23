#!/usr/bin/env python3
"""
Post-process L2 task files to add target_item information.

Extracts user_id and candidate item IDs from task_description,
then looks up user's last interacted item from user_sequences.jsonl.
If the last item is in candidates, it becomes target_item.

Usage:
  python postprocess_add_target_item.py \
    --tasks synthesis_yelp/mcpbench_tasks_level2_cross_runner_format.json \
    --sequences data/yelp/processed/user_sequences.jsonl \
    --dataset yelp
"""

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Set


def load_user_last_items(sequences_path: str, id_field: str = "business_id") -> Dict[str, str]:
    """Load mapping: user_id -> last interacted item_id."""
    user_last: Dict[str, str] = {}
    with open(sequences_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            user_id = obj.get("user_id")
            items = obj.get("items", [])
            if user_id and items:
                last_item = items[-1]
                item_id = last_item.get(id_field) or last_item.get("asin") or last_item.get("item_id")
                if item_id:
                    user_last[user_id] = item_id
    return user_last


def extract_user_id(task_desc: str) -> Optional[str]:
    """Extract user_id from task description."""
    # Pattern: "user XXX" or "user_id XXX" or "For user XXX"
    patterns = [
        r"[Ff]or user[_ ]?(?:id[_ ]?)?['\"]?([A-Za-z0-9_-]+)['\"]?",
        r"user[_ ]?(?:id)?[:\s]+['\"]?([A-Za-z0-9_-]+)['\"]?",
        r"user_id[:\s]+['\"]?([A-Za-z0-9_-]+)['\"]?",
    ]
    for pat in patterns:
        m = re.search(pat, task_desc)
        if m:
            return m.group(1)
    return None


def extract_candidate_ids(task_desc: str, dataset: str = "yelp") -> List[str]:
    """Extract candidate item IDs from task description."""
    candidates = []
    
    # Pattern 1: [id1, id2, id3] or [id1,id2,id3]
    bracket_match = re.search(r'\[([^\]]+)\]', task_desc)
    if bracket_match:
        content = bracket_match.group(1)
        # Split by comma, strip whitespace and quotes
        for item in content.split(','):
            item = item.strip().strip("'\"")
            if item:
                candidates.append(item)
    
    # Pattern 2: ASIN format (B followed by 9 alphanumeric chars) for Amazon
    if dataset == "amazon" and not candidates:
        asin_pattern = re.compile(r'\b(B[0-9A-Z]{9})\b')
        candidates = asin_pattern.findall(task_desc)
    
    # Pattern 3: Yelp business_id format (22-char alphanumeric with _-)
    if dataset == "yelp" and not candidates:
        # Yelp IDs are typically 22 chars with letters, numbers, _, -
        yelp_pattern = re.compile(r'\b([A-Za-z0-9_-]{20,24})\b')
        candidates = yelp_pattern.findall(task_desc)
    
    return list(dict.fromkeys(candidates))  # dedupe while preserving order


def process_tasks_file(
    tasks_path: str,
    sequences_path: str,
    dataset: str,
    output_path: Optional[str] = None
) -> int:
    """Process a tasks JSON file and add target_item info."""
    
    id_field = "business_id" if dataset == "yelp" else "asin"
    
    print(f"Loading user sequences from {sequences_path}...")
    user_last = load_user_last_items(sequences_path, id_field)
    print(f"  Loaded {len(user_last)} users with last items")
    
    print(f"Loading tasks from {tasks_path}...")
    with open(tasks_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    updated_count = 0
    skipped_no_user = 0
    skipped_no_candidates = 0
    skipped_no_match = 0
    
    for server_task in data.get("server_tasks", []):
        for task in server_task.get("tasks", []):
            # Skip if already has target_item
            if task.get("target_item") or task.get("target_item_id"):
                continue
            
            task_desc = task.get("task_description", "")
            
            # Extract user_id
            user_id = extract_user_id(task_desc)
            if not user_id:
                skipped_no_user += 1
                continue
            
            # Extract candidates
            candidates = extract_candidate_ids(task_desc, dataset)
            if not candidates:
                skipped_no_candidates += 1
                continue
            
            # Look up user's last item
            last_item = user_last.get(user_id)
            
            # Determine target
            if last_item and last_item in candidates:
                target_id = last_item
            else:
                # Fallback: first candidate (or skip)
                target_id = candidates[0] if candidates else None
                if last_item:
                    skipped_no_match += 1
            
            if target_id:
                task["user_id"] = user_id
                task["target_item_id"] = target_id
                task["candidate_item_ids"] = candidates
                updated_count += 1
    
    # Save
    if output_path is None:
        output_path = tasks_path.replace(".json", "_with_target.json")
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\nResults:")
    print(f"  Updated tasks: {updated_count}")
    print(f"  Skipped (no user_id found): {skipped_no_user}")
    print(f"  Skipped (no candidates found): {skipped_no_candidates}")
    print(f"  Fallback (last_item not in candidates): {skipped_no_match}")
    print(f"  Output: {output_path}")
    
    return updated_count


def main():
    parser = argparse.ArgumentParser(description="Add target_item to L2 task files")
    parser.add_argument("--tasks", required=True,
                        help="Path to tasks JSON file")
    parser.add_argument("--sequences", required=True,
                        help="Path to user_sequences.jsonl")
    parser.add_argument("--dataset", choices=["amazon", "yelp", "foursquare"],
                        default="yelp", help="Dataset type")
    parser.add_argument("--output", default=None,
                        help="Output path (default: input_with_target.json)")
    parser.add_argument("--inplace", action="store_true",
                        help="Overwrite input file")
    args = parser.parse_args()
    
    output = args.tasks if args.inplace else args.output
    process_tasks_file(args.tasks, args.sequences, args.dataset, output)


if __name__ == "__main__":
    main()
