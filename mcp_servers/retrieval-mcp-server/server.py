#!/usr/bin/env python3
"""
Retrieval MCP Server for Recommendation Systems.
Provides three specialized retrieval tools using FastMCP.
"""
import json
import re
import sqlite3
from pathlib import Path
from typing import Optional, List
import numpy as np
from fastmcp import FastMCP

# Data paths
DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "products.db"

# Create FastMCP server
mcp = FastMCP("retrieval-mcp")

# Global state for embeddings
embedding_model = None
item_embeddings = None
asin_to_idx = {}
idx_to_asin = {}
bpr_item_embeddings = None
bpr_asin_to_idx = {}
bpr_idx_to_asin = {}


def ensure_database():
    """Ensure database exists."""
    DATA_DIR.mkdir(exist_ok=True, parents=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                asin TEXT PRIMARY KEY, title TEXT, brand TEXT, category TEXT,
                price REAL, rating REAL, description TEXT, features TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON products(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_brand ON products(brand)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_price ON products(price)")
        conn.commit()


def load_embedding_model():
    """Lazy load embedding model."""
    global embedding_model
    if embedding_model is None:
        from sentence_transformers import SentenceTransformer
        embedding_model = SentenceTransformer('../../../all-MiniLM-L6-v2')
        print("Loaded sentence transformer model", flush=True)


def load_item_embeddings():
    """Load or create item embeddings."""
    global item_embeddings, asin_to_idx, idx_to_asin
    if item_embeddings is not None:
        return
    
    embeddings_path = DATA_DIR / "item_embeddings.npy"
    asin_map_path = DATA_DIR / "asin_map.json"
    
    if embeddings_path.exists() and asin_map_path.exists():
        item_embeddings = np.load(embeddings_path)
        with open(asin_map_path, 'r') as f:
            data = json.load(f)
            asin_to_idx = data['asin_to_idx']
            idx_to_asin = {int(v): k for k, v in asin_to_idx.items()}
        print(f"Loaded embeddings for {len(asin_to_idx)} items", flush=True)


def load_bpr_embeddings():
    """Load BPR embeddings for collaborative filtering."""
    global bpr_item_embeddings, bpr_asin_to_idx, bpr_idx_to_asin
    if bpr_item_embeddings is not None:
        return
    
    embeddings_path = DATA_DIR / "bpr_item_embeddings.npy"
    asin_map_path = DATA_DIR / "bpr_asin_map.json"
    
    if embeddings_path.exists() and asin_map_path.exists():
        print('Loading pretrained BPR model...', flush=True)
        bpr_item_embeddings = np.load(embeddings_path)
        with open(asin_map_path, 'r') as f:
            data = json.load(f)
            bpr_asin_to_idx = data.get('asin_to_idx', {})
            bpr_idx_to_asin = {int(v): k for k, v in bpr_asin_to_idx.items()}


# Initialize database
ensure_database()


@mcp.tool()
def filter_items_by_attributes(
    category: Optional[str] = None,
    brand: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    asins: Optional[List[str]] = None
) -> str:
    """Hard filter by exact category, brand, or price range.
    
    Args:
        category: Filter by product category
        brand: Filter by brand name
        min_price: Minimum price
        max_price: Maximum price
        asins: Optional list of ASINs to restrict the filter to. When provided, ONLY these ASINs
               are evaluated and returned (as a whitelist). Use this to apply attribute filters to
               a specific candidate set from previous tool results. If omitted, all items are considered.
    
    Returns:
        JSON string with filtered items
    """
    query = "SELECT * FROM products WHERE 1=1"
    params = []
    
    if category and category != "None":
        query += " AND category LIKE ?"
        params.append(f"%{category}%")
    
    if brand and brand != "None":
        query += " AND brand LIKE ?"
        params.append(f"%{brand}%")
    
    if min_price is not None and min_price != "None":
        try:
            query += " AND price >= ?"
            params.append(float(min_price))
        except (ValueError, TypeError):
            pass
    
    if max_price is not None and max_price != "None":
        try:
            query += " AND price <= ?"
            params.append(float(max_price))
        except (ValueError, TypeError):
            pass

    if asins:
        placeholders = ','.join(['?'] * len(asins))
        query += f" AND asin IN ({placeholders})"
        params.extend(asins)
    
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            items = [dict(row) for row in conn.execute(query, params).fetchall()]
        
        return json.dumps({
            "filters": {"category": category, "brand": brand, "min_price": min_price, "max_price": max_price},
            "asins_filter_applied": bool(asins),
            "total_results": len(items),
            "items": items
        }, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def search_keyword(query: str, top_k: int = 100, asins: Optional[List[str]] = None) -> str:
    """Soft filter: match query words against product title or description.
    
    Args:
        query: User query to match against product title or description
        top_k: Number of top results to return (default: 100)
        asins: Optional list of ASINs to restrict the search to. When provided, ONLY these ASINs
               are scored and returned (as a whitelist). Use this to rank/filter a specific
               candidate set by keyword relevance. If omitted, all items are considered.
    
    Returns:
        JSON string with matched items and hit rates
    """
    query_words = [w.strip().lower() for w in query.split() if w.strip()]
    
    if not query_words:
        return json.dumps({"error": "No valid words in query", "query": query})
    
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            if asins:
                placeholders = ','.join(['?'] * len(asins))
                all_items = [dict(row) for row in conn.execute(
                    f"SELECT * FROM products WHERE asin IN ({placeholders})", asins
                ).fetchall()]
            else:
                all_items = [dict(row) for row in conn.execute("SELECT * FROM products").fetchall()]
        
        scored_items = []
        for item in all_items:
            description = (item.get('description') or '').lower()
            title = (item.get('title') or '').lower()
            # Match against both title and description so candidate items with short/empty
            # descriptions can still match via title.
            search_text = f"{title} {description}"
            matching_words = sum(1 for word in query_words if word in search_text)
            
            if matching_words > 0:
                item['hit_rate'] = matching_words / len(query_words)
                item['matching_words'] = matching_words
                scored_items.append(item)
        
        scored_items.sort(key=lambda x: x['hit_rate'], reverse=True)
        
        return json.dumps({
            "query": query,
            "asins_filter_applied": bool(asins),
            "total_results": len(scored_items[:top_k]),
            "items": scored_items[:top_k]
        }, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e), "query": query})


@mcp.tool()
def item2item_search(query_text: str, top_k: int = 100) -> str:
    """Collaborative filter: find items frequently bought together based on item title.
    
    Args:
        query_text: Query text containing item title to find frequently bought together items
        top_k: Number of similar items to return (default: 100)
    
    Returns:
        JSON string with similar items based on collaborative filtering
    """
    try:
        item_title = query_text.strip().lower()
        
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            
            # Try exact match first, then fuzzy
            cursor = conn.execute("SELECT * FROM products WHERE LOWER(title) = ? LIMIT 1", [item_title])
            ref_row = cursor.fetchone()
            
            if not ref_row:
                cursor = conn.execute("SELECT * FROM products WHERE LOWER(title) LIKE ? LIMIT 1", [f"%{item_title}%"])
                ref_row = cursor.fetchone()
            
            if not ref_row:
                return json.dumps({"error": f"Item not found for query: {query_text}", "query_text": query_text})
            
            ref_item = dict(ref_row)
            asin = ref_item.get("asin")
        
        # Load BPR embeddings
        load_bpr_embeddings()
        
        if bpr_item_embeddings is None or len(bpr_item_embeddings) == 0:
            return json.dumps({"error": "BPR embeddings not available", "query_text": query_text})
        
        if asin not in bpr_asin_to_idx:
            return json.dumps({"error": f"Item ASIN {asin} not in BPR model", "query_text": query_text})
        
        # Calculate similarities
        ref_idx = bpr_asin_to_idx[asin]
        ref_embedding = bpr_item_embeddings[ref_idx]
        similarities = bpr_item_embeddings @ ref_embedding
        similarities[ref_idx] = -1e9  # Exclude self
        
        top_indices = np.argsort(similarities)[::-1][:top_k]
        asins = [bpr_idx_to_asin[int(idx)] for idx in top_indices]
        top_scores = similarities[top_indices]
        
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            placeholders = ','.join(['?' for _ in asins])
            items = [dict(row) for row in conn.execute(f"SELECT * FROM products WHERE asin IN ({placeholders})", asins).fetchall()]
        
        asin_to_score = {a: float(s) for a, s in zip(asins, top_scores)}
        for item in items:
            item['similarity_score'] = asin_to_score.get(item['asin'], 0.0)
        items.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        return json.dumps({
            "query_text": query_text,
            "reference_item": {"asin": ref_item.get('asin'), "title": ref_item.get('title')},
            "total_results": len(items),
            "items": items
        }, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e), "query_text": query_text})


@mcp.tool()
def get_item_details(item_id: Optional[str] = None, title: Optional[str] = None) -> str:
    """Get full item metadata by item_id (ASIN) or title.
    
    If item_id is provided, lookup by ASIN directly; otherwise fuzzy-match by title.
    
    Args:
        item_id: Item identifier (ASIN). Takes priority over title if both provided.
        title: Item title for fuzzy lookup when item_id is unknown.
    
    Returns:
        JSON string with item details
    """
    # Try ASIN lookup first
    asin = (item_id or "").strip()
    if asin:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM products WHERE asin = ? LIMIT 1", [asin]
                ).fetchone()
            if row:
                return json.dumps({"item_id": asin, "item": dict(row)}, indent=2, ensure_ascii=False)
            else:
                return json.dumps({"error": f"Item with ASIN '{asin}' not found.", "item_id": asin})
        except Exception as e:
            return json.dumps({"error": str(e), "item_id": asin})

    # Fall back to title fuzzy match
    title_query = (title or "").strip()
    if not title_query:
        return json.dumps({"error": "Both item_id and title are empty. Provide at least one."})

    title_lower = title_query.lower()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            # Exact match
            row = conn.execute(
                "SELECT * FROM products WHERE LOWER(title) = ? LIMIT 1", [title_lower]
            ).fetchone()
            if not row:
                # Fuzzy match
                row = conn.execute(
                    "SELECT * FROM products WHERE LOWER(title) LIKE ? LIMIT 1",
                    [f"%{title_lower}%"]
                ).fetchone()
            if row:
                item = dict(row)
                return json.dumps({"item_id": item.get("asin"), "item": item}, indent=2, ensure_ascii=False)
            else:
                return json.dumps({"error": f"No item found matching title '{title_query}'", "title": title_query})
    except Exception as e:
        return json.dumps({"error": str(e), "title": title_query})


if __name__ == "__main__":
    mcp.run()
