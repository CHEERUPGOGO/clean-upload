#!/usr/bin/env python3

# Yelp L2/L3 tasks were synthesized against these task-level tool names.
# Keep the schema aligned with the benchmark tasks instead of the newer merged aliases.
AVAILABLE_TOOLS_SCHEMA = {
    "retrieval-mcp-yelp-server": {
        "get_business_details": {
            "type": "object",
            "properties": {
                "business_name": {"type": "string"},
                "business_id": {"type": "string"}
            },
            "required": []
        },
        "search_businesses": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "location": {"type": "array", "items": {"type": "number"}},
                "business_ids": {"type": "array", "items": {"type": "string"}},
                "top_k": {"type": "integer"}
            },
            "required": []
        },
        "filter_businesses": {
            "type": "object",
            "properties": {
                "categories": {"type": "string"},
                "location": {"type": "array", "items": {"type": "number"}},
                "open_timestamp": {"type": "number"},
                "business_ids": {"type": "array", "items": {"type": "string"}},
                "top_k": {"type": "integer"}
            },
            "required": []
        },
        "recall_similar_items": {
            "type": "object",
            "properties": {
                "query_text": {"type": "string"},
                "top_k": {"type": "integer"}
            },
            "required": ["query_text"]
        }
    },
    "nlptool-mcp-yelp-server": {
        "query_sentiment": {
            "type": "object",
            "properties": {
                "min_positive_rate": {"type": "number"},
                "business_ids": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["min_positive_rate"]
        },
        "query_opinion": {
            "type": "object",
            "properties": {
                "keywords": {"type": "array", "items": {"type": "string"}},
                "business_ids": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["keywords"]
        },
        "query_summary": {
            "type": "object",
            "properties": {
                "keywords": {"type": "array", "items": {"type": "string"}},
                "business_ids": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["keywords"]
        }
    },
    "rec-mcp-yelp-server": {
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
    "rating-mcp-yelp-server": {
        "get_top_rated": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "business_ids": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer"}
            },
            "required": []
        },
        "get_most_reviewed": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "business_ids": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer"}
            },
            "required": []
        },
        "filter_by_rating": {
            "type": "object",
            "properties": {
                "min_rating": {"type": "number"},
                "max_rating": {"type": "number"},
                "category": {"type": "string"},
                "business_ids": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer"}
            },
            "required": []
        },
        "filter_by_rating_count": {
            "type": "object",
            "properties": {
                "min_count": {"type": "integer"},
                "max_count": {"type": "integer"},
                "min_reviews": {"type": "integer"},
                "max_reviews": {"type": "integer"},
                "category": {"type": "string"},
                "business_ids": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer"}
            },
            "required": []
        },
        "compare_ratings": {
            "type": "object",
            "properties": {
                "item_ids": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["item_ids"]
        }
    },
    "googlemap-mcp-server": {
        "google_geo": {
            "type": "object",
            "properties": {
                "address": {"type": "string"},
                "city": {"type": "string"}
            },
            "required": ["address"]
        },
        "google_regeo": {
            "type": "object",
            "properties": {
                "latlng": {"type": "string"}
            },
            "required": ["latlng"]
        },
        "google_distance": {
            "type": "object",
            "properties": {
                "origin": {"type": "string"},
                "destination": {"type": "string"},
                "mode": {"type": "string"}
            },
            "required": ["origin", "destination"]
        }
    }
}
