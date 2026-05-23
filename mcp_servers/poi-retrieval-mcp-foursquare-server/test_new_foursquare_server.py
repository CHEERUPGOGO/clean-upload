#!/usr/bin/env python3
"""
Test script for the new retrieval MCP server
Tests the three main tools with sample data
"""

import asyncio
import json
import sqlite3
from pathlib import Path
import sys
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from new_retrieval_foursquare_server import NewRetrievalMCPServer

def normalize_text(value):
    """Normalize text value (handle None, lists, etc.)"""
    if value is None:
        return ""
    if isinstance(value, list):
        if not value:
            return ""
        # Join list items or take first
        return " ".join(str(x) for x in value if x) if len(value) > 1 else str(value[0])
    return str(value)

async def test_get_poi_details(server: NewRetrievalMCPServer):
    """Test get business details tool"""
    print("\n" + "="*60)
    print("TEST 1: Get Business Details")
    print("="*60)
    
    poi_id = "4a78323ef964a52043e51fe3"
    print(f"Query: '{poi_id}', Coffee Shop")
    
    result = await server._get_poi_details(
        query=poi_id
    )
    
    print(f"\nResult: {result}")

async def test_semantic_search(server: NewRetrievalMCPServer):
    """Test semantic search tool"""
    print("\n" + "="*60)
    print("TEST 2 - 1: Semantic Search - name")
    print("="*60)
    
    query = "drug store"
    print(f"Query: '{query}'")
    
    result = await server._search_pois(
        query=query,
        top_k=5
    )
    
    print(f"\nResults: {result['total_results']} items found")
    for i, item in enumerate(result.get('items', []), 1):
        print(f"\n{i}. {item['venue_id']}")
        print(f"   Category: {item['venue_category_name']}| ID: {item['venue_category_id']}")
        print(f"   Location: {item['latitude']}, {item['longitude']}")
        print(f"   Checkins: {item['checkin_counts']}")
        print(f"   Distance: {item['distance']:.4f} km| Hit Rate: {item['hit_rate']:.4f}")

    print("\n" + "="*60)
    print("TEST 2 - 2: Semantic Search - location")
    print("="*60)
    
    location = [40.75228980961091, -73.9875741098406]
    print(f"Location: '{location}'")
    
    result = await server._search_pois(
        location=location,
        distance=5,
        top_k=20
    )
    
    print(f"\nResults: {result['total_results']} items found")
    for i, item in enumerate(result.get('items', []), 1):
        print(f"\n{i}. {item['venue_id']}")
        print(f"   Category: {item['venue_category_name']}| ID: {item['venue_category_id']}")
        print(f"   Location: {item['latitude']}, {item['longitude']}")
        print(f"   Checkins: {item['checkin_counts']}")
        print(f"   Distance: {item['distance']:.4f} km| Hit Rate: {item['hit_rate']:.4f}")

async def test_attribute_search(server: NewRetrievalMCPServer):
    """Test attribute-based search tool"""
    print("\n" + "="*60)
    print("TEST 3: Attribute-Based Search")
    print("="*60)
    
    print("Filters: Category=Hotel, Location around 40.76009835453067, -73.99602174562668, min_checkins>=20")

    result = await server._filter_pois(
        category="Hotel",
        min_checkins=20,
        location=[40.76009835453067, -73.99602174562668]
    )
    
    print(f"\nResults: {result['total_results']} items found")
    for i, item in enumerate(result.get('items', []), 1):
        print(f"\n{i}. {item['venue_id']}")
        print(f"   Category: {item['venue_category_name']}| ID: {item['venue_category_id']}")
        print(f"   Location: {item['latitude']}, {item['longitude']}")
        print(f"   Checkins: {item['checkin_counts']}")

# async def test_similar_items(server: NewRetrievalMCPServer):
#     """Test item-to-item similarity tool"""
#     print("\n" + "="*60)
#     print("TEST 4: Item-to-Item Similarity Test")
#     reference_item ="Vineyards Cafe"   # Vineyards Cafe
#     print(f"Reference Item: {reference_item}")
    
#     result = await server._recall_similar_items(
#         query_text=reference_item,
#         top_k=5,
#         # min_similarity=0.3,
#         # exclude_same_category=False
#     )
    
#     if 'error' in result:
#         print(f"Error: {result['error']}")
#         return
    
#     print(f"\nReference: {result['reference_item']['name']}")
#     print(f"\nSimilar Items: {result['total_results']} found")
    
#     for i, item in enumerate(result.get('similar_items', []), 1):
#         print(f"\n{i}. {item['name']}")
#         print(f"   Address: {item['address']}")
#         print(f"   City: {item['city']} | State: {item['state']} | Postal Code: {item['postal_code']}")
#         print(f"   Latitude: {item['latitude']} | Longitude: {item['longitude']}")
#         print(f"   Stars: {item['stars']} | Review Count: {item['review_count']} | Review Rating: {item['review_rating']}")
#         print(f"   Is Open: {item['is_open']}")
#         # print(f"   Text: {normalize_text(item['text'])}")
#         print(f"   Categories: {item['categories']}")
#         print(f"   Similarity: {item['similarity_score']:.3f}")


async def test_edge_cases(server: NewRetrievalMCPServer):
    """Test edge cases and error handling"""
    print("\n" + "="*60)
    print("TEST 5: Edge Cases and Error Handling")
    print("="*60)
    
    # Test 1: Non-existent business_id
    print("\n5.1 Non-existent business_id:")
    result = await server._recall_similar_items(query_text="INVALID_NAME", top_k=5)
    print(f"Result: {json.dumps(result, indent=2)}")
    
    # Test 2: Empty query
    print("\n5.2 Empty semantic query:")
    result = await server._search_businesses(query="", top_k=3)
    print(f"Found {result['total_results']} results (expected: 3)")
    
    # Test 3: Very strict filters
    print("\n5.3 Very strict attribute filters:")
    result = await server._filter_businesses(
        location=[1000,-1000],  # Unrealistic latitude
        review_rating=5.0
    )
    print(f"Found {result['total_results']} results (expected: 0)")


async def main():
    print("üß™ Testing New Retrieval MCP Yelp Server")
    print("="*60)
    
    test_data_dir = Path(__file__).parent / "data" # use production db
    db_path = test_data_dir / "foursquare.db"

    print("\nüì¶ Initializing server...")
    server = NewRetrievalMCPServer(data_dir=db_path.parent)
    
    try:
        await test_get_poi_details(server)
        await test_semantic_search(server) # soft filter search
        await test_attribute_search(server) # hard filter search
        # await test_similar_items(server)
        # await test_edge_cases(server)
        
        print("\n" + "="*60)
        print("‚ú?All tests completed!")
        print("="*60)
        
    except Exception as e:
        print(f"\n‚ù?Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
