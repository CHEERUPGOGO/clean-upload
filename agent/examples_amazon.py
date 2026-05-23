#!/usr/bin/env python3

# AMAZON - examples derived from actual level1 task data
# Tools: 10 total (was 15)
#   retrieval-mcp-server: filter_items_by_attributes, search_keyword, item2item_search, get_item_details
#   nlptool-mcp-server: search_reviews, query_sentiment
#   rating-mcp-server: filter_products, compare_ratings
#   rec-mcp-server: rank_items, get_user_history
#   websearch-mcp-server: web_search
EXAMPLES = """
EXAMPLE TASK: "Find products where reviews mention that the case is heavy, durable, and covers the Kindle completely."
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "nlptool-mcp-server:search_reviews",
            "parameters": {{ "keywords": [
                  "case heavy durable covers Kindle completely"
                ],
                "search_in": "opinion" }}
        }}

EXAMPLE TASK: "Find products with reviews saying: A good read!"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "nlptool-mcp-server:search_reviews",
            "parameters": {{ "keywords": [
                  "A good read"
                ],
                "search_in": "summary" }}
        }}

EXAMPLE TASK: "Which products have at least 83% positive customer reviews?"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "nlptool-mcp-server:query_sentiment",
            "parameters": {{ "min_positive_rate": 83 }}
        }}

EXAMPLE TASK: "Find Fotodiox products under $15"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "retrieval-mcp-server:filter_items_by_attributes",
            "parameters": {{ "brand": "Fotodiox",
                "category": "Electronics",
                "max_price": 15.0 }}
        }}

EXAMPLE TASK: "Find products with camera protection and dust resistance"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "retrieval-mcp-server:search_keyword",
            "parameters": {{ "query": "camera dust scratches jacket case",
                "top_k": 100 }}
        }}

EXAMPLE TASK: "What other items do people often buy with the SwissGear ScanSmart Laptop Backpack?"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "retrieval-mcp-server:item2item_search",
            "parameters": {{ "query_text": "SwissGear ScanSmart Laptop Backpack - Blue" }}
        }}

EXAMPLE TASK: "Show me the details of the product with ASIN B005ODL9LM"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "retrieval-mcp-server:get_item_details",
            "parameters": {{ "item_id": "B005ODL9LM" }}
        }}

EXAMPLE TASK: "Show me products with a rating of 4 stars or higher."
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "rating-mcp-server:filter_products",
            "parameters": {{ "min_rating": 4.0 }}
        }}

EXAMPLE TASK: "Show me popular products with at least 50 customer reviews."
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "rating-mcp-server:filter_products",
            "parameters": {{ "min_reviews": 50 }}
        }}

EXAMPLE TASK: "What are the highest rated subwoofer cables?"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "rating-mcp-server:filter_products",
            "parameters": {{ "category": "Subwoofer Cables",
                "sort_by": "rating" }}
        }}

EXAMPLE TASK: "Show me the most popular computer screws by number of reviews."
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "rating-mcp-server:filter_products",
            "parameters": {{ "category": "Computer Screws",
                "sort_by": "reviews" }}
        }}

EXAMPLE TASK: "Compare the ratings of these products: B004WB8EYM, B00LBZSV7W, B009JPBPWO, and B007GMPZ0A."
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "rating-mcp-server:compare_ratings",
            "parameters": {{ "item_ids": [
                  "B004WB8EYM",
                  "B00LBZSV7W",
                  "B009JPBPWO",
                  "B007GMPZ0A"
                ] }}
        }}

EXAMPLE TASK: "Based on my purchase history as user A1XEWKJCBGDAXJ, rank these items: B00HAWW590, B00BX7TJ2O, B00URHAXQC, B007ORX8ME, B00JDVRCI0."
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

EXAMPLE TASK: "What items has user A1XEWKJCBGDAXJ purchased recently?"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "rec-mcp-server:get_user_history",
            "parameters": {{ "user_id": "A1XEWKJCBGDAXJ" }}
        }}

EXAMPLE TASK: "What are the detailed specifications of the ELP 720p mini IP camera?"
EXAMPLE PLANNED TOOLS:
        {{
            "tool": "websearch-mcp-server:web_search",
            "parameters": {{ "query": "ELP 720p mini IP camera specs resolution connectivity ONVIF support",
                "num_results": 10 }}
        }}
"""

