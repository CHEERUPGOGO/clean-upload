#!/usr/bin/env python3
"""
Rating MCP Server - Product rating/review statistics tools.
Uses FastMCP for simplified server setup.

Tools:
  - filter_products: Unified filter + sort (replaces filter_by_rating, filter_by_rating_count, get_top_rated, get_most_reviewed)
  - compare_ratings: Compare ratings of multiple products by ASIN
"""
import json
import sys
from pathlib import Path
from typing import Optional
from fastmcp import FastMCP

# Data paths
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "amazon-electronics" / "processed"
META_FILE = DATA_DIR / "item_meta.jsonl"


def load_item_meta() -> list[dict]:
    """Load item metadata with rating information."""
    items = []
    if not META_FILE.exists():
        return items
    with open(META_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                if item.get('average_rating') is not None or item.get('rating_number') is not None:
                    items.append(item)
    return items


# Load data at startup
item_data = load_item_meta()
print(f"Loaded {len(item_data)} items with rating info", file=sys.stderr, flush=True)

# Create FastMCP server
mcp = FastMCP("rating-mcp")


@mcp.tool()
def filter_products(
    min_rating: Optional[float] = None,
    max_rating: Optional[float] = None,
    min_reviews: Optional[int] = None,
    max_reviews: Optional[int] = None,
    category: Optional[str] = None,
    asins: Optional[list[str]] = None,
    sort_by: str = "rating",
    limit: int = 20
) -> str:
    """Filter and sort products by rating, review count, and/or category.

    This is the unified tool for all rating-based queries:
    - Find products with high ratings (set min_rating)
    - Find products with many reviews (set min_reviews)
    - Find top-rated in a category (set category + sort_by="rating")
    - Find most-reviewed in a category (set category + sort_by="reviews")

    Args:
        min_rating: Minimum average rating (1.0-5.0). E.g., 4.0 for 4+ stars.
        max_rating: Maximum average rating (1.0-5.0). Optional upper bound.
        min_reviews: Minimum number of reviews. E.g., 100 for popular products.
        max_reviews: Maximum number of reviews. Optional upper bound.
        category: Filter by product category (e.g., 'Subwoofer Cables', 'Outdoor Speakers').
        asins: Optional list of ASINs to restrict the filter to. When provided, ONLY these ASINs
               are evaluated and returned (as a whitelist). Use this to apply rating/review filters
               to a specific candidate set from previous tool results. If omitted, all items are considered.
        sort_by: Sort results by "rating" (default) or "reviews".
        limit: Maximum number of results (default 20).

    Returns:
        JSON string with matching products sorted as specified.
    """
    results = []
    category_lower = category.lower() if category else None
    asin_filter = set(asins) if asins else None

    for item in item_data:
        if asin_filter is not None and item.get('asin') not in asin_filter:
            continue

        rating = item.get('average_rating')
        count = item.get('rating_number', 0)

        if min_rating is not None and (rating is None or rating < min_rating):
            continue
        if max_rating is not None and (rating is None or rating > max_rating):
            continue
        if min_reviews is not None and count < min_reviews:
            continue
        if max_reviews is not None and count > max_reviews:
            continue

        if category_lower:
            item_category = item.get('main_category', item.get('category', ''))
            if isinstance(item_category, list):
                item_category = ' '.join(item_category)
            if category_lower not in str(item_category).lower():
                continue

        results.append({
            'asin': item.get('asin'),
            'title': item.get('title'),
            'average_rating': rating,
            'rating_number': count,
            'category': item.get('main_category', item.get('category', ''))
        })

    if sort_by == "reviews":
        results.sort(key=lambda x: (x['rating_number'], x.get('average_rating') or 0), reverse=True)
    else:
        results.sort(key=lambda x: (x.get('average_rating') or 0, x['rating_number']), reverse=True)

    truncated = results[:limit]
    return json.dumps({
        'total_results': len(truncated),
        'total_before_limit': len(results),
        'asins_filter_applied': asin_filter is not None,
        'items': truncated,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def compare_ratings(item_ids: list[str]) -> str:
    """Compare ratings of multiple products side by side.

    Args:
        item_ids: List of ASINs to compare (e.g., ['B0007T27HI', 'B001C7RB2A']).

    Returns:
        JSON string with rating comparison for the specified items, sorted by rating descending.
    """
    asin_lookup = {item.get('asin'): item for item in item_data}

    results = []
    for asin in item_ids:
        item = asin_lookup.get(asin)
        if item:
            results.append({
                'asin': asin,
                'title': item.get('title'),
                'average_rating': item.get('average_rating'),
                'rating_number': item.get('rating_number', 0),
                'category': item.get('main_category', item.get('category', ''))
            })
        else:
            results.append({
                'asin': asin,
                'error': 'Item not found'
            })

    results.sort(key=lambda x: x.get('average_rating', 0) or 0, reverse=True)
    return json.dumps(results, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
