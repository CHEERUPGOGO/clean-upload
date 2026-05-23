#!/usr/bin/env python3

# JSON Schema definitions for all tools across all servers
AVAILABLE_TOOLS_SCHEMA = {
    "poi-retrieval-mcp-foursquare-server": {
        "get_poi_details": {
            "type": "object",
            "properties": {
                "venue_id": {"type": "string"}
            },
            "required": ["venue_id"]
        },
        "search_pois": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "location": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                "distance": {"type": "number"},
                "item_ids": {"type": "array", "items": {"type": "string"}},
                "top_k": {"type": "integer"}
            },
            "required": []
        },
        "filter_pois": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "min_checkins": {"type": "integer"},
                "location": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                "distance": {"type": "number"},
                "item_ids": {"type": "array", "items": {"type": "string"}}
            },
            "required": []
        }
    },
    "rec-mcp-foursquare-server": {
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
                "destination": {"type": "string"}
            },
            "required": ["origin", "destination"]
        }
    }
}
