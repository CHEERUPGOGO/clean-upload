#!/usr/bin/env python3

# FOURSQUARE
EXAMPLES = """
EXAMPLE TASK: "What is the address for the location with coordinates 40.748539, -73.986669?"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "googlemap-mcp-server:google_regeo",
            "parameters": {{ "latlng": "40.748539, -73.986669" }}
        }}

EXAMPLE TASK: "Find a bar near 40.748539, -73.986669"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "poi-retrieval-mcp-foursquare-server:search_pois",
            "parameters": {{ "query": "Bar",
                "location": [
                  40.748539,
                  -73.986669
                ] }}
        }}

EXAMPLE TASK: "Based on my visit history, rank these places for user 234: ['4be6101dd4f7c9b6de5e2620', '50364286e4b025c29f7d38d0', '4a6ef9a8f964a52020d51fe3', '4b4facbff964a5204b1027e3', '4a9479ecf964a520b72120e3'] from most to least relevant."
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "rec-mcp-foursquare-server:rank_items",
            "parameters": {{ "user_id": "234",
                "item_ids": [
                  "4be6101dd4f7c9b6de5e2620",
                  "50364286e4b025c29f7d38d0",
                  "4a6ef9a8f964a52020d51fe3",
                  "4b4facbff964a5204b1027e3",
                  "4a9479ecf964a520b72120e3"
                ] }}
        }}
"""
