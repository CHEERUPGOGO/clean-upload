#!/usr/bin/env python3
"""
NLP Tool MCP Server for querying items based on review sentiment, opinions, and summaries.
Uses FastMCP for simplified server setup.

Tools:
  - search_reviews: Unified keyword search across opinions and/or summaries (replaces query_opinion + query_summary)
  - query_sentiment: Filter items by positive review rate
"""
import json
import sys
from pathlib import Path
from typing import List, Optional
from fastmcp import FastMCP

# Data paths
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "amazon-electronics" / "processed"
SENTIMENT_FILE = DATA_DIR / "item_sentiment.jsonl"
OPINION_FILE = DATA_DIR / "item_opinion.jsonl"
SUMMARY_FILE = DATA_DIR / "item_summary.jsonl"


def load_jsonl(filepath: Path) -> list[dict]:
    """Load JSONL file into list of dicts."""
    items = []
    if not filepath.exists():
        return items
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))
    return items


# Load data at startup
sentiment_data = load_jsonl(SENTIMENT_FILE)
opinion_data = load_jsonl(OPINION_FILE)
summary_data = load_jsonl(SUMMARY_FILE)

print(f"Loaded {len(sentiment_data)} sentiment items", file=sys.stderr, flush=True)
print(f"Loaded {len(opinion_data)} opinion items", file=sys.stderr, flush=True)
print(f"Loaded {len(summary_data)} summary items", file=sys.stderr, flush=True)

# Build lookup by asin for merging
opinion_lookup = {item['asin']: item for item in opinion_data}
summary_lookup = {item['asin']: item for item in summary_data}

# Create FastMCP server
mcp = FastMCP("nlptool-mcp")


@mcp.tool()
def query_sentiment(min_positive_rate: float, asins: Optional[List[str]] = None) -> str:
    """Filter items by review sentiment statistics. Find items with a minimum positive review rate.

    Args:
        min_positive_rate: Minimum positive review rate (0-100). E.g., 80 means items with >80% positive reviews.
        asins: Optional list of ASINs to restrict the filter to. When provided, ONLY these ASINs are
               evaluated and returned (as a whitelist). Use this to check sentiment for specific
               candidate items from previous tool results. If omitted, all items are considered.

    Returns:
        JSON string with items matching the sentiment threshold, sorted by positive rate descending.
    """
    results = []
    asin_filter = set(asins) if asins else None

    for item in sentiment_data:
        # Whitelist filter
        if asin_filter is not None and item.get('asin') not in asin_filter:
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
        negative = stats.get('negative', 0)
        total = stats.get('total', 0)
        if total <= 0:
            continue
        positive_rate = positive / total * 100

        if positive_rate < min_positive_rate:
            continue

        results.append({
            'asin': item['asin'],
            'title': item['title'],
            'positive': positive,
            'negative': negative,
            'total': total,
            'positive_rate': round(positive_rate, 2)
        })

    results.sort(key=lambda x: x['positive_rate'], reverse=True)
    return json.dumps({
        'total_results': len(results),
        'asins_filter_applied': asin_filter is not None,
        'items': results,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def search_reviews(keywords: List[str], search_in: str = "both", asins: Optional[List[str]] = None) -> str:
    """Search items by keywords in review opinions, summaries, or both.

    Use this tool when the user wants to find products whose reviews mention specific topics,
    aspects, or phrases. This covers both opinion-based and summary-based review search.

    Args:
        keywords: List of keywords to search for (e.g., ['battery life', 'durable', 'heavy']).
        search_in: Where to search - "opinion" (review aspects/opinions only),
                   "summary" (review summaries only), or "both" (default, searches both).
        asins: Optional list of ASINs to restrict the search to. When provided, ONLY these ASINs
               are searched (as a whitelist). Use this to check whether specific candidate items
               have reviews mentioning the keywords. If omitted, all items are searched.

    Returns:
        JSON string with items whose reviews match the specified keywords.
    """
    if not keywords:
        return json.dumps({"error": "keywords parameter is required"})

    keywords_lower = [k.lower() for k in keywords]
    results_map = {}
    asin_filter = set(asins) if asins else None

    # Search in opinion data
    if search_in in ("opinion", "both"):
        for item in opinion_data:
            if asin_filter is not None and item.get('asin') not in asin_filter:
                continue
            aspects = item.get('key_aspects', [])
            aspects_lower = [a.lower() for a in aspects]
            matched = any(any(kw in asp for asp in aspects_lower) for kw in keywords_lower)
            if matched:
                matched_aspects = [a for a in aspects if any(kw in a.lower() for kw in keywords_lower)]
                asin = item['asin']
                if asin not in results_map:
                    results_map[asin] = {
                        'asin': asin,
                        'title': item['title'],
                        'matched_opinions': [],
                        'matched_summaries': []
                    }
                results_map[asin]['matched_opinions'] = matched_aspects

    # Search in summary data
    if search_in in ("summary", "both"):
        for item in summary_data:
            if asin_filter is not None and item.get('asin') not in asin_filter:
                continue
            summaries = item.get('key_aspects', [])
            summary_text = ' '.join(summaries).lower()
            matched_keywords = [kw for kw in keywords_lower if kw in summary_text]
            if matched_keywords:
                asin = item['asin']
                if asin not in results_map:
                    results_map[asin] = {
                        'asin': asin,
                        'title': item['title'],
                        'matched_opinions': [],
                        'matched_summaries': []
                    }
                results_map[asin]['matched_summaries'] = matched_keywords
                if not results_map[asin].get('title'):
                    results_map[asin]['title'] = item['title']

    results = list(results_map.values())
    return json.dumps({
        'total_results': len(results),
        'asins_filter_applied': asin_filter is not None,
        'items': results,
    }, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
