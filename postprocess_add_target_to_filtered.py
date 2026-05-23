#!/usr/bin/env python3
"""
Post-process L2/L3 task files across Amazon, Yelp, Foursquare datasets.

Reads *_cross_runner_format.json (source of truth for task_description),
extracts user_id from task_description, looks up the user's last item in
user_sequences.jsonl, verifies it appears in the candidates listed in
task_description, and writes target_item / user_id / candidate_item_ids
into the corresponding *_with_fuzzy_quality_filtered.json.

Logic mirrors synthesis scripts:
  - target = items[-1] from user_sequences  (last interacted item)
  - candidate_ids always starts with target_id, then random extras
  - So target_id �?candidate_ids is guaranteed

Usage:
  python postprocess_add_target_to_filtered.py --data_root data/
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ── Dataset configs ──────────────────────────────────────────────────────────

DATASET_CONFIGS = {
    "amazon": {
        "sequences_path": "amazon-electronics/processed/user_sequences.jsonl",
        "items_field": "items",          # field in user_sequences for item list
        "id_field": "asin",              # item id field inside each item dict
        "synthesis_dir": "synthesis_amazon",
    },
    "yelp": {
        "sequences_path": "yelp/processed/user_sequences.jsonl",
        "items_field": "items",
        "id_field": "business_id",
        "synthesis_dir": "synthesis_yelp",
    },
    "foursquare": {
        "sequences_path": "foursquare/user_sequences.jsonl",
        "items_field": "list_checkin",
        "id_field": "venue_id",
        "synthesis_dir": "synthesis_foursquare",
    },
}

LEVELS = ["level2", "level3"]


# ── Load user sequences ─────────────────────────────────────────────────────

def load_user_last_items(
    seq_path: Path, items_field: str, id_field: str
) -> Dict[str, str]:
    """user_id -> last interacted item_id."""
    mapping: Dict[str, str] = {}
    with open(seq_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            uid = str(obj.get("user_id", ""))
            items = obj.get(items_field, [])
            if uid and items:
                last = items[-1]
                iid = last.get(id_field)
                if iid:
                    mapping[uid] = str(iid)
    return mapping


# ── Extract user_id from task_description ────────────────────────────────────

# Ordered from most specific to least specific.
USER_PATTERNS = [
    # get_user_history(user_id='XXXX')  —�?L3 common pattern
    r"user_id\s*=\s*['\"]([A-Za-z0-9_-]+)['\"]",
    # user_id: XXXX (colon-separated)
    r"user_id\s*:\s*['\"]?([A-Za-z0-9_-]+)['\"]?",
    # user ID 'XXXX' / user has ID 'XXXX' / user with ID 'XXXX'
    r"user\b[^.]*?\bID\s*['\"]([A-Za-z0-9_-]+)['\"]",
    # For user 'XXXX' or user 'XXXX' (quoted)
    r"[Ff]or user\s+['\"]([A-Za-z0-9_-]+)['\"]",
    r"user\s+['\"]([A-Za-z0-9_-]+)['\"]",
    # For user XXXX (unquoted)
    r"[Ff]or user\s+([A-Za-z0-9_-]+)",
    r"I'm user\s+([A-Za-z0-9_-]+)",
    # user XXXX (generic, last resort)
    r"user\s+([A-Za-z0-9_-]{3,})",
]

# Words that look like user_id but aren't
_FALSE_UIDS = {"has", "the", "with", "and", "who", "that", "will", "can",
               "not", "for", "from", "this", "their", "into", "its", "are",
               "was", "been", "being", "have", "had", "does", "did", "may",
               "might", "must", "shall", "should", "would", "could", "need",
               "recently", "tasked", "history", "currently", "preferences",
               "interaction", "experience", "interface", "is", "at", "to",
               "id", "ID", "about", "wants", "based", "using", "named"}


def extract_user_id(desc: str) -> Optional[str]:
    """Extract user_id from task_description."""
    for pat in USER_PATTERNS:
        m = re.search(pat, desc)
        if m:
            uid = m.group(1)
            if uid.lower() not in _FALSE_UIDS:
                return uid
    return None


# ── Extract candidate IDs from task_description ─────────────────────────────

# Amazon ASINs: B followed by 9 alnum chars
_ASIN_RE = re.compile(r'\bB[0-9A-Z]{9}\b')

# Yelp business_ids: 22-char base64-like (may contain _ and -)
_YELP_ID_RE = re.compile(r'\b[A-Za-z0-9_-]{22}\b')

# Foursquare venue_ids: 24-char hex
_FSQ_ID_RE = re.compile(r'\b[0-9a-f]{24}\b')

# Generic bracket list: [id1, id2, ...]
_BRACKET_RE = re.compile(r'\[([^\[\]]{10,}?)\]')


def extract_candidate_ids(desc: str, dataset: str) -> List[str]:
    """Extract candidate item IDs from task_description."""
    candidates: List[str] = []

    if dataset == "amazon":
        candidates = _ASIN_RE.findall(desc)
    elif dataset == "yelp":
        # First try bracket lists (most reliable)
        for bm in _BRACKET_RE.finditer(desc):
            content = bm.group(1)
            # Check if it looks like IDs (not coordinates / numbers)
            parts = [p.strip().strip("'\"") for p in content.split(",")]
            ids = [p for p in parts if _YELP_ID_RE.match(p)]
            if len(ids) >= 2:
                candidates.extend(ids)
        # Fallback: find all standalone yelp IDs
        if not candidates:
            candidates = _YELP_ID_RE.findall(desc)
    elif dataset == "foursquare":
        # First try bracket lists
        for bm in _BRACKET_RE.finditer(desc):
            content = bm.group(1)
            parts = [p.strip().strip("'\"") for p in content.split(",")]
            ids = [p for p in parts if _FSQ_ID_RE.match(p)]
            if len(ids) >= 2:
                candidates.extend(ids)
        # Fallback: find all standalone foursquare IDs
        if not candidates:
            candidates = _FSQ_ID_RE.findall(desc)

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            deduped.append(c)
    return deduped


# ── Process a single JSON file ───────────────────────────────────────────────

def process_file(
    input_path: Path,
    user_last: Dict[str, str],
    dataset: str,
    output_path: Optional[Path] = None,
    dry_run: bool = False,
) -> dict:
    """Add target_item, user_id, candidate_item_ids to tasks in a JSON file.

    Returns stats dict.
    """
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    stats = {
        "total": 0, "updated": 0,
        "skip_already_has": 0, "skip_no_user": 0,
        "skip_no_candidates": 0, "skip_no_match": 0,
    }
    id_field = DATASET_CONFIGS[dataset]["id_field"]

    for st in data.get("server_tasks", []):
        for task in st.get("tasks", []):
            stats["total"] += 1

            # Skip if already has target
            if task.get("target_item") and task.get("user_id"):
                stats["skip_already_has"] += 1
                continue

            desc = task.get("task_description", "")

            # 1) Extract user_id
            uid = extract_user_id(desc)
            if not uid:
                stats["skip_no_user"] += 1
                continue

            # 2) Extract candidate IDs
            cands = extract_candidate_ids(desc, dataset)
            # Remove user_id itself from candidates (yelp user_ids can match
            # the business_id regex pattern)
            cands = [c for c in cands if c != uid]
            if not cands:
                stats["skip_no_candidates"] += 1
                continue

            # 3) Look up user's last item (= target)
            target_id = user_last.get(uid)
            if not target_id or target_id not in cands:
                stats["skip_no_match"] += 1
                continue

            # 4) Write fields
            task["user_id"] = uid
            task["target_item"] = {id_field: target_id}
            task["candidate_item_ids"] = cands
            stats["updated"] += 1

    if not dry_run:
        out = output_path or input_path
        # If can't write to target, write to *_with_target.json
        try:
            with open(out, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except PermissionError:
            fallback = Path(str(out).replace(".json", "_with_target.json"))
            print(f"    [WARN] Permission denied on {out}, writing to {fallback}")
            with open(fallback, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            out = fallback
        stats["output_path"] = str(out)

    return stats


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Post-process L2/L3 task files to add target_item."
    )
    parser.add_argument(
        "--data_root", type=str, default="data/",
        help="Root directory containing dataset subdirs (amazon-electronics/, yelp/, foursquare/)",
    )
    parser.add_argument(
        "--project_root", type=str, default=".",
        help="Project root containing synthesis_amazon/ synthesis_yelp/ synthesis_foursquare/",
    )
    parser.add_argument(
        "--datasets", nargs="+",
        default=["amazon", "yelp", "foursquare"],
        choices=["amazon", "yelp", "foursquare"],
        help="Datasets to process",
    )
    parser.add_argument(
        "--levels", nargs="+", default=["level2", "level3"],
        help="Levels to process",
    )
    parser.add_argument(
        "--dry_run", action="store_true",
        help="Don't write files, only print stats",
    )
    parser.add_argument(
        "--inplace", action="store_true",
        help="Overwrite *_with_fuzzy_quality_filtered.json in place (default: True)",
    )
    args = parser.parse_args()

    data_root = Path(args.data_root)
    project_root = Path(args.project_root)

    for ds in args.datasets:
        cfg = DATASET_CONFIGS[ds]
        seq_path = data_root / cfg["sequences_path"]

        if not seq_path.exists():
            print(f"\n[SKIP] {ds}: sequences file not found at {seq_path}")
            continue

        print(f"\n{'='*60}")
        print(f"Dataset: {ds}")
        print(f"{'='*60}")

        # Load user -> last_item mapping
        print(f"Loading user sequences from {seq_path}...")
        user_last = load_user_last_items(
            seq_path, cfg["items_field"], cfg["id_field"]
        )
        print(f"  Loaded {len(user_last)} users")

        synth_dir = project_root / cfg["synthesis_dir"]

        for level in args.levels:
            # Target file: *_with_fuzzy_quality_filtered.json
            filtered_file = synth_dir / f"mcpbench_tasks_{level}_cross_runner_format_with_fuzzy_quality_filtered.json"

            if not filtered_file.exists():
                print(f"\n  [{level}] SKIP: {filtered_file.name} not found")
                continue

            print(f"\n  [{level}] Processing {filtered_file.name}")

            stats = process_file(
                input_path=filtered_file,
                user_last=user_last,
                dataset=ds,
                output_path=filtered_file,  # inplace
                dry_run=args.dry_run,
            )

            print(f"    Total tasks:          {stats['total']}")
            print(f"    Updated (target set):  {stats['updated']}")
            print(f"    Skip (already has):    {stats['skip_already_has']}")
            print(f"    Skip (no user_id):     {stats['skip_no_user']}")
            print(f"    Skip (no candidates):  {stats['skip_no_candidates']}")
            print(f"    Skip (no match):       {stats['skip_no_match']}")

            if args.dry_run:
                print(f"    [DRY RUN] No files written")
            else:
                out_path = stats.get("output_path", str(filtered_file))
                print(f"    Saved to {out_path}")

    print(f"\nDone.")


if __name__ == "__main__":
    main()
