#!/usr/bin/env python3
"""
NLP Tool MCP Server for Yelp - review sentiment and keyword search.
Tools: query_opinion, query_summary, query_sentiment
"""
import json
import sys
from pathlib import Path
from typing import List, Optional
from fastmcp import FastMCP

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "yelp"
SENTIMENT_FILE = DATA_DIR / "item_sentiment.jsonl"
OPINION_FILE = DATA_DIR / "item_opinion.jsonl"
SUMMARY_FILE = DATA_DIR / "item_summary.jsonl"


def load_jsonl(filepath: Path) -> list[dict]:
    items = []
    if not filepath.exists():
        return items
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))
    return items


sentiment_data = load_jsonl(SENTIMENT_FILE)
opinion_data = load_jsonl(OPINION_FILE)
summary_data = load_jsonl(SUMMARY_FILE)

print(f"Loaded {len(sentiment_data)} sentiment items", file=sys.stderr, flush=True)
print(f"Loaded {len(opinion_data)} opinion items", file=sys.stderr, flush=True)
print(f"Loaded {len(summary_data)} summary items", file=sys.stderr, flush=True)

mcp = FastMCP("nlptool-mcp")


def normalize_ids(ids: Optional[List[str]]) -> Optional[set[str]]:
    if ids is None:
        return None
    if isinstance(ids, str):
        ids = [ids]
    normalized = set()
    for value in ids:
        if value is None:
            continue
        bid = str(value).strip().strip('"').strip("'")
        if bid:
            normalized.add(bid)
    return normalized or None


def normalize_keywords(keywords=None, keyword: Optional[str] = None) -> List[str]:
    if keywords is None and keyword is not None:
        keywords = [keyword]
    if isinstance(keywords, str):
        keywords = [keywords]
    return [str(k).strip() for k in (keywords or []) if str(k).strip()]


@mcp.tool()
def query_sentiment(min_positive_rate: float, business_ids: Optional[List[str]] = None) -> str:
    """Filter businesses by review sentiment. Find businesses with a minimum positive review rate.

    Args:
        min_positive_rate: Minimum positive review rate (0-100). E.g., 80 means >80% positive.
        business_ids: Optional list of business_ids to restrict the filter to. When provided, ONLY
                      these businesses are evaluated and returned (as a whitelist). Use this to apply
                      sentiment filters to a specific candidate set. If omitted, all businesses are considered.

    Returns:
        JSON string with matching businesses sorted by positive rate descending.
    """
    results = []
    id_filter = normalize_ids(business_ids)
    for item in sentiment_data:
        bid = item.get('business_id', item.get('asin', ''))
        if id_filter is not None and bid not in id_filter:
            continue
        key_aspects = item.get('key_aspects', [])
        stats = {}
        for aspect in key_aspects:
            if ':' in aspect:
                key, value = aspect.split(':')
                try:
                    stats[key] = int(value)
                except ValueError:
                    continue
        positive = stats.get('positive', 0)
        total = stats.get('total', 0)
        if total <= 0:
            continue
        positive_rate = positive / total * 100
        if positive_rate < min_positive_rate:
            continue
        results.append({
            'business_id': bid,
            'name': item.get('name', item.get('title', '')),
            'positive': positive,
            'negative': stats.get('negative', 0),
            'total': total,
            'positive_rate': round(positive_rate, 2)
        })
    results.sort(key=lambda x: x['positive_rate'], reverse=True)
    return json.dumps({
        'total_results': len(results),
        'business_ids_filter_applied': id_filter is not None,
        'items': results,
    }, ensure_ascii=False, indent=2)


def search_reviews(keywords: List[str], search_in: str = "both", business_ids: Optional[List[str]] = None) -> str:
    """Search businesses by keywords in review opinions, summaries, or both.

    Use this tool when the user wants to find businesses whose reviews mention specific topics or phrases.

    Args:
        keywords: List of keywords to search for (e.g., ['wait time', 'friendly staff']).
        search_in: Where to search - "opinion", "summary", or "both" (default).
        business_ids: Optional list of business_ids to restrict the search to. When provided, ONLY
                      these businesses are searched (as a whitelist). If omitted, all businesses are searched.

    Returns:
        JSON string with matching businesses.
    """
    keywords = normalize_keywords(keywords)
    if not keywords:
        return json.dumps({"error": "keywords parameter is required"})

    keywords_lower = [k.lower() for k in keywords]
    results_map = {}
    id_filter = normalize_ids(business_ids)

    if search_in in ("opinion", "both"):
        for item in opinion_data:
            bid = item.get('business_id', item.get('asin', ''))
            if id_filter is not None and bid not in id_filter:
                continue
            aspects = item.get('key_aspects', [])
            aspects_lower = [a.lower() for a in aspects]
            matched = any(any(kw in asp for asp in aspects_lower) for kw in keywords_lower)
            if matched:
                matched_aspects = [a for a in aspects if any(kw in a.lower() for kw in keywords_lower)]
                if bid not in results_map:
                    results_map[bid] = {
                        'business_id': bid,
                        'name': item.get('name', item.get('title', '')),
                        'matched_opinions': [],
                        'matched_summaries': []
                    }
                results_map[bid]['matched_opinions'] = matched_aspects

    if search_in in ("summary", "both"):
        for item in summary_data:
            bid = item.get('business_id', item.get('asin', ''))
            if id_filter is not None and bid not in id_filter:
                continue
            summaries = item.get('key_aspects', [])
            summary_text = ' '.join(summaries).lower()
            matched_kws = [kw for kw in keywords_lower if kw in summary_text]
            if matched_kws:
                if bid not in results_map:
                    results_map[bid] = {
                        'business_id': bid,
                        'name': item.get('name', item.get('title', '')),
                        'matched_opinions': [],
                        'matched_summaries': []
                    }
                results_map[bid]['matched_summaries'] = matched_kws

    items = list(results_map.values())
    return json.dumps({
        'total_results': len(items),
        'business_ids_filter_applied': id_filter is not None,
        'items': items,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def query_opinion(
    keywords: Optional[List[str]] = None,
    keyword: Optional[str] = None,
    business_ids: Optional[List[str]] = None
) -> str:
    """Search review opinion aspects for the requested keywords."""
    return search_reviews(
        keywords=normalize_keywords(keywords, keyword),
        search_in="opinion",
        business_ids=business_ids,
    )


@mcp.tool()
def query_summary(
    keywords: Optional[List[str]] = None,
    keyword: Optional[str] = None,
    business_ids: Optional[List[str]] = None
) -> str:
    """Search review summary text for the requested keywords."""
    return search_reviews(
        keywords=normalize_keywords(keywords, keyword),
        search_in="summary",
        business_ids=business_ids,
    )


if __name__ == "__main__":
    mcp.run()
