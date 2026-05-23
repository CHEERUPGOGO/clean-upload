#!/usr/bin/env python3

# JSON Schema definitions for Amazon MCP tools (updated to match merged tools)
AVAILABLE_TOOLS_SCHEMA = {
    "retrieval-mcp-server": {
        "filter_items_by_attributes": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "brand": {"type": "string"},
                "min_price": {"type": "number"},
                "max_price": {"type": "number"}
            }
        },
        "item2item_search": {
            "type": "object",
            "properties": {
                "query_text": {"type": "string"},
                "top_k": {"type": "integer"}
            },
            "required": ["query_text"]
        },
        "search_keyword": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer"}
            },
            "required": ["query"]
        },
        "get_item_details": {
            "type": "object",
            "properties": {
                "item_id": {"type": "string"},
                "title": {"type": "string"}
            }
        }
    },
    "nlptool-mcp-server": {
        "query_sentiment": {
            "type": "object",
            "properties": {
                "min_positive_rate": {"type": "number"}
            },
            "required": ["min_positive_rate"]
        },
        "search_reviews": {
            "type": "object",
            "properties": {
                "keywords": {"type": "array", "items": {"type": "string"}},
                "search_in": {"type": "string"}
            },
            "required": ["keywords"]
        }
    },
    "rec-mcp-server": {
        "rank_items": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "item_ids": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["user_id", "item_ids"]
        },
        "get_user_history": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"}
            },
            "required": ["user_id"]
        }
    },
    "rating-mcp-server": {
        "filter_products": {
            "type": "object",
            "properties": {
                "min_rating": {"type": "number"},
                "max_rating": {"type": "number"},
                "min_reviews": {"type": "integer"},
                "max_reviews": {"type": "integer"},
                "category": {"type": "string"},
                "sort_by": {"type": "string"},
                "limit": {"type": "integer"}
            }
        },
        "compare_ratings": {
            "type": "object",
            "properties": {
                "item_ids": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["item_ids"]
        }
    },
    "websearch-mcp-server": {
        "web_search": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "num_results": {"type": "integer"}
            },
            "required": ["query"]
        }
    }
}
