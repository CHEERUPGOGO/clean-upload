#!/usr/bin/env python3
"""
New Retrieval MCP Server for Recommendation Systems
Provides three specialized retrieval tools:
1. filter_items_by_attributes - Hard filter by exact category/brand/price
2. item2item_search - Collaborative filter for complementary products
3. search_keyword   - Soft filter from product title or description
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional
from pathlib import Path
import sqlite3
import numpy as np

# MCP imports
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("new-retrieval-mcp-server")


class NewRetrievalMCPServer:
    """New Retrieval MCP Server with three specialized tools"""
    
    def __init__(self, data_dir: Optional[Path] = None):
        self.server = Server("new-retrieval-mcp-server")
        
        # Data paths
        if data_dir is None:
            data_dir = Path(__file__).parent / "data"
        self.data_dir = Path(data_dir)
        self.db_path = self.data_dir / "products.db"
        
        # Embedding model (lazy loading)
        self.embedding_model = None
        self.item_embeddings = None
        self.asin_to_idx = {}
        self.idx_to_asin = {}
        self.bpr_item_embeddings = None
        self.bpr_asin_to_idx = {}
        self.bpr_idx_to_asin = {}
        
        # Initialize
        self._ensure_database()
        self._setup_tools()
    
    def _ensure_database(self):
        """Ensure database exists"""
        if not self.db_path.exists():
            logger.warning(f"Database not found at {self.db_path}")
        self.data_dir.mkdir(exist_ok=True, parents=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    asin TEXT PRIMARY KEY,
                    title TEXT,
                    brand TEXT,
                    category TEXT,
                    price REAL,
                    rating REAL,
                    description TEXT,
                    features TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON products(category)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_brand ON products(brand)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_price ON products(price)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rating ON products(rating)")
            conn.commit()

    def _tokenize_query_text(self, query_text: str) -> List[str]:
        cleaned = re.sub(r"[^0-9a-zA-Z]+", " ", (query_text or "").lower()).strip()
        if not cleaned:
            return []
        raw_tokens = cleaned.split()
        tokens: List[str] = []
        seen = set()
        for t in raw_tokens:
            if t and t not in seen:
                seen.add(t)
                tokens.append(t)
        return tokens

    def _resolve_query_text_to_item(self, query_text: str) -> Optional[Dict[str, Any]]:
        tokens = self._tokenize_query_text(query_text)
        if not tokens:
            return None

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT asin, title, brand, category, description FROM products LIMIT 5000"
            )
            rows = [dict(r) for r in cursor.fetchall()]

        best_row = None
        best_key = (-1.0, -1, -1)
        for row in rows:
            title = (row.get("title") or "").lower()
            description = (row.get("description") or "").lower()
            combined = f"{title} {description}"
            match_count = 0
            for t in tokens:
                if t in combined:
                    match_count += 1
            if match_count == 0:
                continue
            hit_rate = match_count / len(tokens)
            key = (hit_rate, match_count, len(title))
            if key > best_key:
                best_key = key
                best_row = row
        return best_row
    
    def _load_embedding_model(self):
        """Lazy load embedding model"""
        if self.embedding_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                # Use a lightweight model for fast inference
                self.embedding_model = SentenceTransformer('../../../all-MiniLM-L6-v2')
                logger.info("Loaded sentence transformer model")
            except ImportError:
                logger.error("sentence-transformers not installed. Install with: pip install sentence-transformers")
                raise
    
    def _load_item_embeddings(self):
        """Load or create item embeddings"""
        if self.item_embeddings is not None:
            return
        
        embeddings_path = self.data_dir / "item_embeddings.npy"
        asin_map_path = self.data_dir / "asin_map.json"
        
        # Try to load existing embeddings
        if embeddings_path.exists() and asin_map_path.exists():
            self.item_embeddings = np.load(embeddings_path)
            with open(asin_map_path, 'r') as f:
                data = json.load(f)
                self.asin_to_idx = data['asin_to_idx']
                self.idx_to_asin = {int(v): k for k, v in self.asin_to_idx.items()}
            logger.info(f"Loaded embeddings for {len(self.asin_to_idx)} items")
        else:
            # Create embeddings from database
            self._create_item_embeddings()
    
    def _create_item_embeddings(self):
        """Create embeddings for all items in database"""
        self._load_embedding_model()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT asin, title, brand, category, description FROM products")
            items = [dict(row) for row in cursor.fetchall()]
        
        if not items:
            logger.warning("No items in database to create embeddings")
            self.item_embeddings = np.array([])
            return
        
        texts = []
        asins = []
        for item in items:
            text = f"{item['title'] or ''} {item['brand'] or ''} {item['category'] or ''} {item['description'] or ''}"
            texts.append(text.strip())
            asins.append(item['asin'])
        
        # Create embeddings
        logger.info(f"Creating embeddings for {len(texts)} items...")
        self.item_embeddings = self.embedding_model.encode(texts, show_progress_bar=True)
        
        # Create mappings
        self.asin_to_idx = {asin: idx for idx, asin in enumerate(asins)}
        self.idx_to_asin = {idx: asin for idx, asin in enumerate(asins)}
        
        # Save embeddings
        embeddings_path = self.data_dir / "item_embeddings.npy"
        asin_map_path = self.data_dir / "asin_map.json"
        
        np.save(embeddings_path, self.item_embeddings)
        with open(asin_map_path, 'w') as f:
            json.dump({'asin_to_idx': self.asin_to_idx}, f)
        
        logger.info(f"Saved embeddings to {embeddings_path}")
    
    def _setup_tools(self):
        """Setup MCP tools"""
        
        @self.server.list_tools()
        async def handle_list_tools() -> list[types.Tool]:
            """List available retrieval tools"""
            return [
                types.Tool(
                    name="filter_items_by_attributes",
                    description="Hard filter by exact category, brand, or price range. Returns all items matching the specified criteria.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "category": {
                                "type": "string",
                                "description": "Filter by product category"
                            },
                            "brand": {
                                "type": "string",
                                "description": "Filter by brand name"
                            },
                            "min_price": {
                                "type": "number",
                                "description": "Minimum price"
                            },
                            "max_price": {
                                "type": "number",
                                "description": "Maximum price"
                            },
                            "asins": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional list of ASINs to restrict the filter to (whitelist). When provided, ONLY these ASINs are evaluated."
                            }
                        },
                        "required": []
                    }
                ),
                types.Tool(
                    name="item2item_search",
                    description="Collaborative filter: find items frequently bought together based on item title in query text.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query_text": {
                                "type": "string",
                                "description": "Query text containing item title to find frequently bought together items"
                            }
                        },
                        "required": ["query_text"]
                    }
                ),
                types.Tool(
                    name="search_keyword",
                    description="Soft filter: match query words against product title or description. Returns items with hit rate score.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "User query to match against product title or description"
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "Number of top results to return",
                                "default": 100
                            },
                            "asins": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional list of ASINs to restrict the search to (whitelist). When provided, ONLY these ASINs are scored and returned."
                            }
                        },
                        "required": ["query"]
                    }
                ),
                types.Tool(
                    name="get_item_details",
                    description="Get full item metadata by item_id (ASIN) or title. If item_id is provided, lookup by ASIN directly; otherwise fuzzy-match by title.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "item_id": {
                                "type": "string",
                                "description": "Item identifier (ASIN). Takes priority over title if both provided."
                            },
                            "title": {
                                "type": "string",
                                "description": "Item title for fuzzy lookup when item_id is unknown."
                            }
                        },
                        "required": []
                    }
                )
            ]
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
            """Handle tool calls"""
            logger.info(f"[TOOL CALL] name={name}, arguments={arguments}, type={type(arguments)}")
            try:
                if arguments is None:
                    arguments = {}
                if name == "filter_items_by_attributes":
                    result = await self._search_items_by_attributes(**arguments)
                elif name == "item2item_search":
                    result = await self._recall_similar_items(**arguments)
                elif name == "search_keyword":
                    result = await self._search_items_by_keywords(**arguments)
                elif name == "get_item_details":
                    result = await self._get_item_details(**arguments)
                else:
                    raise ValueError(f"Unknown tool: {name}")
                
                return [types.TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
                
            except Exception as e:
                logger.error(f"Error in tool {name}: {e}", exc_info=True)
                return [types.TextContent(type="text", text=json.dumps({"error": str(e), "tool": name}))]
    
    async def _get_item_details(self, item_id: Optional[str] = None, title: Optional[str] = None) -> Dict[str, Any]:
        """Get full item metadata. Lookup by ASIN first; fall back to fuzzy title match."""
        logger.info(f"[GET_ITEM_DETAILS] item_id={item_id!r}, title={title!r}, db_path={self.db_path}")
        # --- 1. Try ASIN lookup ---
        asin = (item_id or "").strip()
        if asin:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute(
                        "SELECT * FROM products WHERE asin = ? LIMIT 1", [asin]
                    ).fetchone()
                if row:
                    return {"item_id": asin, "item": dict(row)}
                else:
                    return {"error": f"Item with ASIN '{asin}' not found in database. Try a different ASIN or use title search.", "item_id": asin}
            except Exception as e:
                return {"error": str(e), "item_id": asin}

        # --- 2. Fall back to title fuzzy match ---
        title_query = (title or "").strip()
        if not title_query:
            return {"error": "Both item_id and title are empty. Provide at least one."}

        title_lower = title_query.lower()
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                # exact match
                row = conn.execute(
                    "SELECT * FROM products WHERE LOWER(title) = ? LIMIT 1",
                    [title_lower],
                ).fetchone()
                if not row:
                    # fuzzy LIKE match
                    row = conn.execute(
                        "SELECT * FROM products WHERE LOWER(title) LIKE ? LIMIT 1",
                        [f"%{title_lower}%"],
                    ).fetchone()
                if not row:
                    # token-level best match via existing helper
                    best = self._resolve_query_text_to_item(title_query)
                    if best:
                        row = conn.execute(
                            "SELECT * FROM products WHERE asin = ? LIMIT 1",
                            [best["asin"]],
                        ).fetchone()

            if not row:
                return {"error": "Item not found", "title": title_query}

            item = dict(row)
            return {"item_id": item["asin"], "item": item}
        except Exception as e:
            return {"error": str(e), "title": title_query}

    async def _search_items_by_semantic(self, query: str, top_k: int = 100) -> Dict[str, Any]:
        """Match candidate items to user query based on title similarity"""
        
        try:
            self._load_embedding_model()
            self._load_item_embeddings()
            
            if self.item_embeddings is None or len(self.item_embeddings) == 0:
                return {
                    "query": query,
                    "total_results": 0,
                    "items": [],
                    "message": "No items available"
                }
            
            # Encode query
            query_embedding = self.embedding_model.encode([query])[0]
            
            # Compute cosine similarity
            from sklearn.metrics.pairwise import cosine_similarity
            similarities = cosine_similarity(
                query_embedding.reshape(1, -1),
                self.item_embeddings
            )[0]

            # Get all items with similarity > 0
            valid_indices = np.where(similarities > 0)[0]
            valid_similarities = similarities[valid_indices]
            sorted_order = np.argsort(valid_similarities)[::-1][:top_k]
            top_indices = valid_indices[sorted_order]
            top_scores = valid_similarities[sorted_order]
            
            # Fetch item details from database
            asins = [self.idx_to_asin[int(idx)] for idx in top_indices]
            
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                placeholders = ','.join(['?' for _ in asins])
                cursor = conn.execute(
                    f"SELECT * FROM products WHERE asin IN ({placeholders})",
                    asins
                )
                items = [dict(row) for row in cursor.fetchall()]
            
            # Add similarity scores
            asin_to_score = {asin: float(score) for asin, score in zip(asins, top_scores)}
            for item in items:
                item['similarity_score'] = asin_to_score.get(item['asin'], 0.0)
            
            items.sort(key=lambda x: x['similarity_score'], reverse=True)
            
            return {
                "query": query,
                "total_results": len(items),
                "items": items
            }
        
        except Exception as e:
            logger.error(f"Error in semantic search: {e}", exc_info=True)
            return {
                "error": str(e),
                "query": query
            }
    
    async def _search_items_by_attributes(self, category: Optional[str] = None,
                                         brand: Optional[str] = None,
                                         min_price: Optional[float] = None,
                                         max_price: Optional[float] = None,
                                         asins: Optional[List[str]] = None) -> Dict[str, Any]:
        """Filter items by exact category, brand, or price range.

        Args:
            category, brand, min_price, max_price: attribute filters (None = ignored)
            asins: optional whitelist â€?when provided, ONLY these ASINs are considered
        """
        
        query = "SELECT * FROM products WHERE 1=1"
        params = []
        
        # Only add filter if parameter is not None and not the string "None"
        if category is not None and category != "None":
            query += " AND category LIKE ?"
            params.append(f"%{category}%")
        
        if brand is not None and brand != "None":
            query += " AND brand LIKE ?"
            params.append(f"%{brand}%")
        
        if min_price is not None and min_price != "None":
            try:
                min_price_val = float(min_price) if isinstance(min_price, str) else min_price
                query += " AND price >= ?"
                params.append(min_price_val)
            except (ValueError, TypeError):
                pass
        
        if max_price is not None and max_price != "None":
            try:
                max_price_val = float(max_price) if isinstance(max_price, str) else max_price
                query += " AND price <= ?"
                params.append(max_price_val)
            except (ValueError, TypeError):
                pass

        if asins:
            placeholders = ','.join(['?'] * len(asins))
            query += f" AND asin IN ({placeholders})"
            params.extend(asins)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query, params)
                items = [dict(row) for row in cursor.fetchall()]
            
            return {
                "filters": {
                    "category": category,
                    "brand": brand,
                    "min_price": min_price,
                    "max_price": max_price
                },
                "asins_filter_applied": bool(asins),
                "total_results": len(items),
                "items": items
            }
        
        except Exception as e:
            logger.error(f"Error in attribute search: {e}", exc_info=True)
            return {
                "error": str(e),
                "filters": {
                    "category": category,
                    "brand": brand,
                    "min_price": min_price,
                    "max_price": max_price
                }
            }
    
    async def _search_items_by_keywords(self, query: str, top_k: int = 100,
                                        asins: Optional[List[str]] = None) -> Dict[str, Any]:
        """Match user query words against product title or description with hit rate scoring.

        Args:
            query: search query string
            top_k: max results to return
            asins: optional whitelist â€?when provided, ONLY these ASINs are scored
        """
        
        try:
            # Parse query into words
            query_words = [w.strip().lower() for w in query.split() if w.strip()]
            
            if not query_words:
                return {
                    "error": "No valid words in query",
                    "query": query
                }
            
            # Get products (optionally restricted to whitelist)
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                if asins:
                    placeholders = ','.join(['?'] * len(asins))
                    all_items = [dict(row) for row in conn.execute(
                        f"SELECT * FROM products WHERE asin IN ({placeholders})", asins
                    ).fetchall()]
                else:
                    all_items = [dict(row) for row in conn.execute(
                        "SELECT * FROM products"
                    ).fetchall()]
            
            # Calculate hit rate for each item
            scored_items = []
            for item in all_items:
                title = (item.get('title') or '').lower()
                description = (item.get('description') or '').lower()
                search_text = f"{title} {description}"
                
                # Count matching words
                matching_words = sum(1 for word in query_words if word in search_text)
                
                # Only include items with at least one match
                if matching_words > 0:
                    hit_rate = matching_words / len(query_words)
                    item['hit_rate'] = hit_rate
                    item['matching_words'] = matching_words
                    scored_items.append(item)
            
            # Sort by hit rate descending
            scored_items.sort(key=lambda x: x['hit_rate'], reverse=True)
            
            # Return top_k results
            result_items = scored_items[:top_k]
            
            return {
                "query": query,
                "asins_filter_applied": bool(asins),
                "total_results": len(result_items),
                "items": result_items
            }
        
        except Exception as e:
            logger.error(f"Error in keyword search: {e}", exc_info=True)
            return {
                "error": str(e),
                "query": query
            }

    async def _recall_similar_items(self, query_text: str, top_k: int = 100) -> Dict[str, Any]:
        """Find items frequently bought together based on item title in query text"""
        
        try:
            # Resolve query to item title and then to ASIN
            item_title = query_text.strip().lower()
            asin = None
            
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Try exact match first
                cursor = conn.execute(
                    "SELECT * FROM products WHERE LOWER(title) = ? LIMIT 1",
                    [item_title]
                )
                ref_row = cursor.fetchone()
                
                # Try fuzzy match if exact match fails
                if not ref_row:
                    cursor = conn.execute(
                        "SELECT * FROM products WHERE LOWER(title) LIKE ? LIMIT 1",
                        [f"%{item_title}%"]
                    )
                    ref_row = cursor.fetchone()
                
                if not ref_row:
                    return {
                        "error": f"Item not found for query: {query_text}",
                        "query_text": query_text
                    }
                
                ref_item = dict(ref_row)
                asin = ref_item.get("asin")
            
            # Use BPR embeddings for collaborative filtering
            self._load_bpr_item_embeddings()
            
            if self.bpr_item_embeddings is None or len(self.bpr_item_embeddings) == 0:
                return {
                    "error": "BPR embeddings not available",
                    "query_text": query_text
                }
            
            if asin not in self.bpr_asin_to_idx:
                return {
                    "error": f"Item ASIN {asin} not in BPR model",
                    "query_text": query_text,
                    "reference_asin": asin
                }
            
            # Calculate similarities using BPR (collaborative filtering)
            ref_idx = self.bpr_asin_to_idx[asin]
            ref_embedding = self.bpr_item_embeddings[ref_idx]
            similarities = self.bpr_item_embeddings @ ref_embedding
            
            # Exclude reference item itself
            similarities[ref_idx] = -1e9
            
            # Get top_k similar items
            sorted_order = np.argsort(similarities)[::-1][:top_k]
            top_indices = np.array(sorted_order, dtype=int)
            
            # Get items from database
            asins = [self.bpr_idx_to_asin[int(idx)] for idx in top_indices]
            top_scores = similarities[top_indices] if len(top_indices) else np.array([], dtype=float)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                if asins:
                    placeholders = ','.join(['?' for _ in asins])
                    cursor = conn.execute(
                        f"SELECT * FROM products WHERE asin IN ({placeholders})",
                        asins
                    )
                    items = [dict(row) for row in cursor.fetchall()]
                else:
                    items = []
            
            # Add similarity scores
            asin_to_score = {a: float(s) for a, s in zip(asins, top_scores)}
            for item in items:
                item['similarity_score'] = asin_to_score.get(item['asin'], 0.0)
            
            items.sort(key=lambda x: x['similarity_score'], reverse=True)
            
            return {
                "query_text": query_text,
                "reference_item": {
                    "asin": ref_item.get('asin'),
                    "title": ref_item.get('title')
                },
                "total_results": len(items),
                "items": items
            }
        
        except Exception as e:
            logger.error(f"Error in similarity search: {e}", exc_info=True)
            return {
                "error": str(e),
                "query_text": query_text
            }

    def _load_bpr_item_embeddings(self):
        if self.bpr_item_embeddings is not None:
            return
        embeddings_path = self.data_dir / "bpr_item_embeddings.npy"
        asin_map_path = self.data_dir / "bpr_asin_map.json"
        if embeddings_path.exists() and asin_map_path.exists():
            print('load pretrained bpr model...', file=sys.stderr)
            self.bpr_item_embeddings = np.load(embeddings_path)
            with open(asin_map_path, 'r') as f:
                data = json.load(f)
                self.bpr_asin_to_idx = data.get('asin_to_idx', {})
                self.bpr_idx_to_asin = {int(v): k for k, v in self.bpr_asin_to_idx.items()}

async def main():
    """Main server entry point"""
    import sys
    
    # Optional: accept data directory as command line argument
    data_dir = None
    if len(sys.argv) > 1:
        data_dir = Path(sys.argv[1])
    
    server_instance = NewRetrievalMCPServer(data_dir=data_dir)
    logger.info("Starting new retrieval MCP server...")
    
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server_instance.server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="new-retrieval-mcp-server",
                server_version="1.0.0",
                capabilities=server_instance.server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities=None,
                )
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
