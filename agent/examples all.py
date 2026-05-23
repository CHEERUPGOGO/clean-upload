#!/usr/bin/env python3

# AMAZON
EXAMPLES = """
EXAMPLE TASK: "Find products where reviews mention that the case is heavy, seems durable, covers the Kindle completely, but note the tabs that secure the Kindle Fire inside the case."
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "nlptool-mcp-server:query_opinion",
            "parameters": {{                 "keywords": [
                  "The case is heavy. The case seems durable, and covers the Kindle completely. The only thing I don't care for are the tabs that secure the Kindle Fire inside the case."
                ] }}
        }}

EXAMPLE TASK: "What are the most reviewed component subwoofers?"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "rating-mcp-server:get_most_reviewed",
            "parameters": {{ "category": "Component Subwoofers" }}
        }}

EXAMPLE TASK: "Based on my purchase history as user A1XEWKJCBGDAXJ, can you rank these items for me: B00HAWW590, B00BX7TJ2O, B00URHAXQC, B007ORX8ME, and B00JDVRCI0?"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "rec-mcp-server:rank_items",
            "parameters": {{ "user_id": "A1XEWKJCBGDAXJ",
                "item_ids": [
                  "B00HAWW590",
                  "B00BX7TJ2O",
                  "B00URHAXQC",
                  "B007ORX8ME",
                  "B00JDVRCI0"
                ] }}
        }}

EXAMPLE TASK: "Rii wireless keyboard with touchpad"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "retrieval-mcp-server:filter_items_by_attributes",
            "parameters": {{ "brand": "Rii",
                "category": "Electronics",
                "min_price": "None",
                "max_price": "None" }}
        }}
"""

# YELP
EXAMPLES = """
EXAMPLE TASK: "What is the latitude and longitude for 455 Regency Park, Ste B in O'Fallon?"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "googlemap-mcp-server:google_geo",
            "parameters": {{ "address": "455 Regency Park, Ste B",
                "city": "O'fallon" }}
        }}

EXAMPLE TASK: "Which businesses have at least a 67% positive review rate?"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "nlptool-mcp-yelp-server:query_sentiment",
            "parameters": {{ "min_positive_rate": 67 }}
        }}

EXAMPLE TASK: "Compare the ratings of businesses 16pzkRO8Yxdh7w1eJqnyqw and 2vsHDnVOwO54rKCt1An3pA."
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "rating-mcp-yelp-server:compare_ratings",
            "parameters": {{ "item_ids": [
                  "16pzkRO8Yxdh7w1eJqnyqw",
                  "2vsHDnVOwO54rKCt1An3pA"
                ] }}
        }}

EXAMPLE TASK: "Based on my visiting history as user PR62P0c1i6hSLB57GCItpQ, can you rank these businesses for me: _f3JQU6IXpGmTLaSqGy79g, pEsWGGWiT9ElbJxmXHXMpA, z-G-WVOJoY8QVNfATkMxGw, 0q27L4aOGuXyQ1Eo-IOY0Q, and yjcIKn2T2QY_DjXWACsAFw?"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "rec-mcp-yelp-server:rank_items",
            "parameters": {{ "user_id": "PR62P0c1i6hSLB57GCItpQ",
                "item_ids": [
                  "_f3JQU6IXpGmTLaSqGy79g",
                  "pEsWGGWiT9ElbJxmXHXMpA",
                  "z-G-WVOJoY8QVNfATkMxGw",
                  "0q27L4aOGuXyQ1Eo-IOY0Q",
                  "yjcIKn2T2QY_DjXWACsAFw"
                ] }}
        }}

EXAMPLE TASK: "Find American traditional restaurants near 38.5325582, -90.3090247 that are open on Saturday at 21:00."
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "retrieval-mcp-yelp-server:filter_businesses",
            "parameters": {{ "categories": "Nightlife, Sports Bars, Bars, American (Traditional), Restaurants",
                "location": [
                  38.5325582,
                  -90.3090247
                ] }}
        }}
"""

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
