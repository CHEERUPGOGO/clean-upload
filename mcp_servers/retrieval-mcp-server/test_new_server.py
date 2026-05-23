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

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from new_retrieval_server import NewRetrievalMCPServer


def create_test_database(db_path: Path):
    """Create a test database with sample products"""
    
    sample_products = [
        {
            "asin": "B001",
            "title": "Apple iPhone 15 Pro Max",
            "brand": "Apple",
            "category": "Electronics",
            "price": 1199.99,
            "rating": 4.8,
            "description": "Latest flagship smartphone with A17 Pro chip, titanium design, and advanced camera system"
        },
        {
            "asin": "B002",
            "title": "Samsung Galaxy S24 Ultra",
            "brand": "Samsung",
            "category": "Electronics",
            "price": 1299.99,
            "rating": 4.7,
            "description": "Premium Android phone with S Pen, AI features, and 200MP camera"
        },
        {
            "asin": "B003",
            "title": "Sony WH-1000XM5 Wireless Headphones",
            "brand": "Sony",
            "category": "Audio",
            "price": 399.99,
            "rating": 4.9,
            "description": "Industry-leading noise canceling wireless headphones with exceptional sound quality"
        },
        {
            "asin": "B004",
            "title": "Apple AirPods Pro (2nd Generation)",
            "brand": "Apple",
            "category": "Audio",
            "price": 249.99,
            "rating": 4.6,
            "description": "Premium wireless earbuds with active noise cancellation and spatial audio"
        },
        {
            "asin": "B005",
            "title": "MacBook Air M3 15-inch",
            "brand": "Apple",
            "category": "Computers",
            "price": 1299.99,
            "rating": 4.9,
            "description": "Lightweight laptop with M3 chip, 15-inch Liquid Retina display, up to 18 hours battery life"
        },
        {
            "asin": "B006",
            "title": "Dell XPS 13 Plus",
            "brand": "Dell",
            "category": "Computers",
            "price": 1199.99,
            "rating": 4.5,
            "description": "Premium ultrabook with Intel Core i7, stunning OLED display, and sleek design"
        },
        {
            "asin": "B007",
            "title": "Bose QuietComfort Ultra Headphones",
            "brand": "Bose",
            "category": "Audio",
            "price": 429.99,
            "rating": 4.7,
            "description": "Premium wireless headphones with world-class noise cancellation and immersive audio"
        },
        {
            "asin": "B008",
            "title": "Google Pixel 8 Pro",
            "brand": "Google",
            "category": "Electronics",
            "price": 999.99,
            "rating": 4.6,
            "description": "AI-powered smartphone with exceptional camera, Google Tensor G3, and pure Android experience"
        },
        {
            "asin": "B009",
            "title": "iPad Pro 12.9-inch M2",
            "brand": "Apple",
            "category": "Tablets",
            "price": 1099.99,
            "rating": 4.8,
            "description": "Professional tablet with M2 chip, stunning Liquid Retina XDR display, and Apple Pencil support"
        },
        {
            "asin": "B010",
            "title": "Anker Soundcore Liberty 4 NC",
            "brand": "Anker",
            "category": "Audio",
            "price": 99.99,
            "rating": 4.4,
            "description": "Affordable wireless earbuds with adaptive noise cancelling and long battery life"
        }
    ]
    
    # Create database
    db_path.parent.mkdir(exist_ok=True, parents=True)
    
    with sqlite3.connect(db_path) as conn:
        # Drop existing table
        conn.execute("DROP TABLE IF EXISTS products")
        
        # Create table
        conn.execute("""
            CREATE TABLE products (
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
        
        # Insert sample data
        for product in sample_products:
            conn.execute("""
                INSERT INTO products (asin, title, brand, category, price, rating, description)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                product["asin"],
                product["title"],
                product["brand"],
                product["category"],
                product["price"],
                product["rating"],
                product["description"]
            ))
        
        conn.commit()
    
    print(f"‚ú?Created test database with {len(sample_products)} products")


async def test_semantic_search(server: NewRetrievalMCPServer):
    """Test semantic search tool"""
    print("\n" + "="*60)
    print("TEST 1: Semantic Search")
    print("="*60)
    
    query = "affordable wireless earbuds with noise cancellation"
    print(f"Query: '{query}'")
    
    result = await server._search_items_by_semantic(
        query=query,
        top_k=3
    )
    
    print(f"\nResults: {result['total_results']} items found")
    for i, item in enumerate(result.get('items', []), 1):
        print(f"\n{i}. {item['title']}")
        print(f"   Brand: {item['brand']} | Price: ${item['price']}")
        print(f"   Similarity: {item['similarity_score']:.3f}")
        print(f"   {item['description'][:80]}...")


async def test_attribute_search(server: NewRetrievalMCPServer):
    """Test attribute-based search tool"""
    print("\n" + "="*60)
    print("TEST 2: Attribute-Based Search")
    print("="*60)
    
    print("Filters: Category=Audio, Price=$200-$500, Rating>=4.5")
    
    result = await server._search_items_by_attributes(
        category="Audio",
        min_price=200,
        max_price=500,
        min_rating=4.5,
        sort_by="price_asc",
        limit=10
    )
    
    print(f"\nResults: {result['total_results']} items found")
    for i, item in enumerate(result.get('items', []), 1):
        print(f"\n{i}. {item['title']}")
        print(f"   Brand: {item['brand']} | Price: ${item['price']} | Rating: {item['rating']}")


async def test_similar_items(server: NewRetrievalMCPServer):
    """Test item-to-item similarity tool"""
    print("\n" + "="*60)
    print("TEST 3: Item-to-Item Similarity")
    print("="*60)
    
    reference_asin = "B001"  # iPhone 15 Pro Max
    print(f"Reference Item: {reference_asin} (iPhone 15 Pro Max)")
    
    result = await server._recall_similar_items(
        asin=reference_asin,
        top_k=5,
        min_similarity=0.3,
        exclude_same_category=False
    )
    
    if 'error' in result:
        print(f"Error: {result['error']}")
        return
    
    print(f"\nReference: {result['reference_item']['title']}")
    print(f"\nSimilar Items: {result['total_results']} found")
    
    for i, item in enumerate(result.get('similar_items', []), 1):
        print(f"\n{i}. {item['title']}")
        print(f"   Brand: {item['brand']} | Category: {item['category']}")
        print(f"   Similarity: {item['similarity_score']:.3f}")


async def test_edge_cases(server: NewRetrievalMCPServer):
    """Test edge cases and error handling"""
    print("\n" + "="*60)
    print("TEST 4: Edge Cases")
    print("="*60)
    
    # Test 1: Non-existent ASIN
    print("\n4.1 Non-existent ASIN:")
    result = await server._recall_similar_items(query_text="INVALID_TITLE", top_k=5)
    print(f"Result: {json.dumps(result, indent=2)}")
    
    # Test 2: Empty query
    print("\n4.2 Empty semantic query:")
    result = await server._search_items_by_semantic(query="", top_k=3)
    print(f"Found {result['total_results']} results")
    
    # Test 3: Very strict filters
    print("\n4.3 Very strict attribute filters:")
    result = await server._search_items_by_attributes(
        min_price=10000,  # Unrealistic price
        min_rating=5.0
    )
    print(f"Found {result['total_results']} results (expected: 0)")


async def main():
    print("üß™ Testing New Retrieval MCP Server")
    print("="*60)
    
    test_data_dir = Path(__file__).parent / "test_data"
    db_path = test_data_dir / "products.db"
    
    create_test_database(db_path)
    print("\nüì¶ Initializing server...")
    server = NewRetrievalMCPServer(data_dir=test_data_dir)
    
    try:
        await test_semantic_search(server)
        await test_attribute_search(server)
        await test_similar_items(server)
        await test_edge_cases(server)
        
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
