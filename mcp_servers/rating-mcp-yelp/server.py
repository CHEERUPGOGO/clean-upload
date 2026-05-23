#!/usr/bin/env python3
"""
Rating MCP Server for Yelp - Business rating/review statistics tools.
Tools: get_top_rated, get_most_reviewed, filter_by_rating, filter_by_rating_count, compare_ratings
"""
import json
import sys
from pathlib import Path
from typing import Optional
from fastmcp import FastMCP

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "yelp"
META_FILE = DATA_DIR / "item_meta.jsonl"


def load_item_meta() -> list[dict]:
    items = []
    if not META_FILE.exists():
        return items
    with open(META_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                if item.get('stars') is not None or item.get('review_rating') is not None:
                    items.append(item)
    return items


item_data = load_item_meta()
print(f"Loaded {len(item_data)} items with rating info", file=sys.stderr, flush=True)

mcp = FastMCP("rating-mcp")


def normalize_ids(ids: Optional[list[str]]) -> Optional[set[str]]:
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


def filter_products(
    min_rating: Optional[float] = None,
    max_rating: Optional[float] = None,
    min_reviews: Optional[int] = None,
    max_reviews: Optional[int] = None,
    category: Optional[str] = None,
    business_ids: Optional[list[str]] = None,
    item_ids: Optional[list[str]] = None,
    sort_by: str = "rating",
    limit: int = 20
) -> str:
    """Filter and sort businesses by rating, review count, and/or category.

    This is the unified tool for all rating-based queries:
    - Find businesses with high ratings (set min_rating)
    - Find businesses with many reviews (set min_reviews)
    - Find top-rated in a category (set category + sort_by="rating")
    - Find most-reviewed in a category (set category + sort_by="reviews")

    Args:
        min_rating: Minimum average rating (1.0-5.0).
        max_rating: Maximum average rating (1.0-5.0).
        min_reviews: Minimum number of reviews.
        max_reviews: Maximum number of reviews.
        category: Filter by business category (e.g., 'Bars', 'Italian', 'Coffee').
        business_ids: Optional list of business_ids to restrict the filter to. When provided, ONLY these
                      businesses are evaluated and returned (as a whitelist). Use this to apply filters
                      to a specific candidate set from previous tool results.
        sort_by: Sort by "rating" (default) or "reviews".
        limit: Maximum results (default 20).

    Returns:
        JSON string with matching businesses.
    """
    results = []
    category_lower = category.lower() if category else None
    id_filter = normalize_ids(business_ids if business_ids is not None else item_ids)

    for item in item_data:
        if id_filter is not None and item.get('business_id') not in id_filter:
            continue
        rating = item.get('review_rating')
        count = item.get('review_count', 0)

        if min_rating is not None and (rating is None or rating < min_rating):
            continue
        if max_rating is not None and (rating is None or rating > max_rating):
            continue
        if min_reviews is not None and count < min_reviews:
            continue
        if max_reviews is not None and count > max_reviews:
            continue

        if category_lower:
            item_cats = item.get('categories', [])
            if isinstance(item_cats, list):
                item_cats = ' '.join(item_cats)
            if category_lower not in str(item_cats).lower():
                continue

        results.append({
            'business_id': item.get('business_id'),
            'name': item.get('name'),
            'review_rating': rating,
            'review_count': count,
            'categories': item.get('categories', [])
        })

    if sort_by == "reviews":
        results.sort(key=lambda x: (x['review_count'], x.get('review_rating') or 0), reverse=True)
    else:
        results.sort(key=lambda x: (x.get('review_rating') or 0, x['review_count']), reverse=True)

    truncated = results[:limit]
    return json.dumps({
        'total_results': len(truncated),
        'total_before_limit': len(results),
        'business_ids_filter_applied': id_filter is not None,
        'items': truncated,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def get_top_rated(
    category: Optional[str] = None,
    business_ids: Optional[list[str]] = None,
    item_ids: Optional[list[str]] = None,
    limit: int = 20
) -> str:
    """Get top-rated Yelp businesses, optionally restricted by category and candidate business IDs."""
    return filter_products(
        category=category,
        business_ids=business_ids,
        item_ids=item_ids,
        sort_by="rating",
        limit=limit,
    )


@mcp.tool()
def get_most_reviewed(
    category: Optional[str] = None,
    business_ids: Optional[list[str]] = None,
    item_ids: Optional[list[str]] = None,
    limit: int = 20
) -> str:
    """Get businesses with the largest review counts, optionally restricted by category and candidate IDs."""
    return filter_products(
        category=category,
        business_ids=business_ids,
        item_ids=item_ids,
        sort_by="reviews",
        limit=limit,
    )


@mcp.tool()
def filter_by_rating(
    min_rating: Optional[float] = None,
    max_rating: Optional[float] = None,
    category: Optional[str] = None,
    business_ids: Optional[list[str]] = None,
    item_ids: Optional[list[str]] = None,
    limit: int = 20
) -> str:
    """Filter businesses by rating range, category, and optional candidate IDs."""
    return filter_products(
        min_rating=min_rating,
        max_rating=max_rating,
        category=category,
        business_ids=business_ids,
        item_ids=item_ids,
        sort_by="rating",
        limit=limit,
    )


@mcp.tool()
def filter_by_rating_count(
    min_count: Optional[int] = None,
    max_count: Optional[int] = None,
    min_reviews: Optional[int] = None,
    max_reviews: Optional[int] = None,
    category: Optional[str] = None,
    business_ids: Optional[list[str]] = None,
    item_ids: Optional[list[str]] = None,
    limit: int = 20
) -> str:
    """Filter businesses by review-count thresholds and optional candidate IDs."""
    return filter_products(
        min_reviews=min_reviews if min_reviews is not None else min_count,
        max_reviews=max_reviews if max_reviews is not None else max_count,
        category=category,
        business_ids=business_ids,
        item_ids=item_ids,
        sort_by="reviews",
        limit=limit,
    )


@mcp.tool()
def compare_ratings(item_ids: list[str]) -> str:
    """Compare ratings of multiple businesses side by side.

    Args:
        item_ids: List of business_ids to compare.

    Returns:
        JSON string with rating comparison, sorted by rating descending.
    """
    lookup = {item.get('business_id'): item for item in item_data}
    results = []
    for bid in normalize_ids(item_ids) or []:
        item = lookup.get(bid)
        if item:
            results.append({
                'business_id': bid,
                'name': item.get('name'),
                'review_rating': item.get('review_rating'),
                'review_count': item.get('review_count', 0),
                'categories': item.get('categories', [])
            })
        else:
            results.append({'business_id': bid, 'error': 'Item not found'})

    results.sort(key=lambda x: x.get('review_rating', 0) or 0, reverse=True)
    return json.dumps(results, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
