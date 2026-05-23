#!/usr/bin/env python3

# YELP examples aligned with synthesis-query-yelp L2/L3 tool names.
EXAMPLES = """
EXAMPLE TASK: "What is the latitude and longitude for 4265 Reavis Barracks Rd in St. Louis?"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "googlemap-mcp-server:google_geo",
            "parameters": {{ "address": "4265 Reavis Barracks Rd", "city": "St. Louis" }}
        }}

EXAMPLE TASK: "What is the address for the coordinates 38.5325582, -90.3090247?"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "googlemap-mcp-server:google_regeo",
            "parameters": {{ "latlng": "38.5325582,-90.3090247" }}
        }}

EXAMPLE TASK: "How far is it from 38.5325582,-90.3090247 to 27.930772,-82.4571776 by walking?"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "googlemap-mcp-server:google_distance",
            "parameters": {{ "origin": "38.5325582,-90.3090247", "destination": "27.930772,-82.4571776", "mode": "walking" }}
        }}

EXAMPLE TASK: "Find businesses whose opinion aspects mention wait time."
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "nlptool-mcp-yelp-server:query_opinion",
            "parameters": {{ "keywords": ["wait time"] }}
        }}

EXAMPLE TASK: "Find businesses whose review summaries mention food quality."
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "nlptool-mcp-yelp-server:query_summary",
            "parameters": {{ "keywords": ["food quality"] }}
        }}

EXAMPLE TASK: "Which businesses have at least a 68% positive review rate?"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "nlptool-mcp-yelp-server:query_sentiment",
            "parameters": {{ "min_positive_rate": 68 }}
        }}

EXAMPLE TASK: "Show me businesses with a rating of 4.2 or higher."
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "rating-mcp-yelp-server:filter_by_rating",
            "parameters": {{ "min_rating": 4.2 }}
        }}

EXAMPLE TASK: "Show me businesses with at least 50 customer reviews."
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "rating-mcp-yelp-server:filter_by_rating_count",
            "parameters": {{ "min_count": 50 }}
        }}

EXAMPLE TASK: "Which are the top-rated cocktail bars?"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "rating-mcp-yelp-server:get_top_rated",
            "parameters": {{ "category": "Cocktail Bars", "limit": 20 }}
        }}

EXAMPLE TASK: "What are the most popular breweries by review count?"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "rating-mcp-yelp-server:get_most_reviewed",
            "parameters": {{ "category": "Breweries", "limit": 20 }}
        }}

EXAMPLE TASK: "Compare the ratings of businesses 16pzkRO8Yxdh7w1eJqnyqw and 2vsHDnVOwO54rKCt1An3pA."
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "rating-mcp-yelp-server:compare_ratings",
            "parameters": {{ "item_ids": ["16pzkRO8Yxdh7w1eJqnyqw", "2vsHDnVOwO54rKCt1An3pA"] }}
        }}

EXAMPLE TASK: "Find American traditional restaurants near 38.5325582, -90.3090247 that are open on Saturday at 21:00."
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "retrieval-mcp-yelp-server:filter_businesses",
            "parameters": {{ "categories": "American (Traditional), Restaurants", "location": [38.5325582, -90.3090247], "open_timestamp": 1735945200 }}
        }}

EXAMPLE TASK: "Find a sports bar near 38.5325582, -90.3090247."
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "retrieval-mcp-yelp-server:search_businesses",
            "parameters": {{ "query": "sports bar", "location": [38.5325582, -90.3090247], "top_k": 10 }}
        }}

EXAMPLE TASK: "Get details for business Social Bar and Grill."
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "retrieval-mcp-yelp-server:get_business_details",
            "parameters": {{ "business_name": "Social Bar and Grill" }}
        }}

EXAMPLE TASK: "Which businesses do people often visit along with Social Bar and Grill?"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "retrieval-mcp-yelp-server:recall_similar_items",
            "parameters": {{ "query_text": "Social Bar and Grill", "top_k": 10 }}
        }}

EXAMPLE TASK: "Based on my visiting history as user PR62P0c1i6hSLB57GCItpQ, rank these businesses: _f3JQU6IXpGmTLaSqGy79g, pEsWGGWiT9ElbJxmXHXMpA"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "rec-mcp-yelp-server:rank_items",
            "parameters": {{ "user_id": "PR62P0c1i6hSLB57GCItpQ", "item_ids": ["_f3JQU6IXpGmTLaSqGy79g", "pEsWGGWiT9ElbJxmXHXMpA"] }}
        }}

EXAMPLE TASK: "What places has user PR62P0c1i6hSLB57GCItpQ visited recently?"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "rec-mcp-yelp-server:get_user_history",
            "parameters": {{ "user_id": "PR62P0c1i6hSLB57GCItpQ" }}
        }}
"""
