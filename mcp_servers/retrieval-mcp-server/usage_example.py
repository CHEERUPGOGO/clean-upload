#!/usr/bin/env python3
"""
Usage examples for the new retrieval MCP server
Demonstrates how to call each of the three tools
"""

import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from new_retrieval_server import NewRetrievalMCPServer


async def example_1_semantic_search():
    """Example 1: Using semantic search for natural language queries"""
    
    print("\n" + "="*70)
    print("EXAMPLE 1: Semantic Search - Natural Language Query")
    print("="*70)
    
    server = NewRetrievalMCPServer(data_dir=Path(__file__).parent / "data")
    
    # Scenario: User wants affordable wireless earbuds for sports
    query = "affordable wireless earbuds for running and sports with long battery"
    
    print(f"\nüí¨ User Query: '{query}'")
    print("\nüîç Searching...")
    
    result = await server._search_items_by_semantic(
        query=query,
        top_k=5
    )
    
    print(f"\n‚ú?Found {result['total_results']} relevant items:")
    print("-" * 70)
    
    for i, item in enumerate(result.get('items', []), 1):
        print(f"\n{i}. {item['title']}")
        print(f"   Brand: {item['brand']} | Price: ${item.get('price', 'N/A')}")
        print(f"   Similarity Score: {item['similarity_score']:.3f}")
        print(f"   Description: {item.get('description', '')[:100]}...")


async def example_2_attribute_filter():
    """Example 2: Using attribute filters for precise requirements"""
    
    print("\n" + "="*70)
    print("EXAMPLE 2: Attribute-Based Filtering - Precise Requirements")
    print("="*70)
    
    server = NewRetrievalMCPServer(data_dir=Path(__file__).parent / "data")
    
    # Scenario: User wants premium Apple products in a specific price range
    print("\nüí¨ User Requirements:")
    print("   - Brand: Apple")
    print("   - Category: Electronics or Computers")
    print("   - Price: $800 - $1500")
    print("   - Rating: >= 4.5")
    print("   - Sort by: Rating (highest first)")
    
    print("\nüîç Filtering...")
    
    result = await server._search_items_by_attributes(
        brand="Apple",
        min_price=800,
        max_price=1500,
        min_rating=4.5,
        sort_by="rating_desc",
        limit=10
    )
    
    print(f"\n‚ú?Found {result['total_results']} matching items:")
    print("-" * 70)
    
    for i, item in enumerate(result.get('items', []), 1):
        print(f"\n{i}. {item['title']}")
        print(f"   Price: ${item.get('price', 'N/A')} | Rating: {item.get('rating', 'N/A')}‚≠?)
        print(f"   Category: {item.get('category', 'N/A')}")


async def example_3_similar_items():
    """Example 3: Finding similar items for recommendations"""
    
    print("\n" + "="*70)
    print("EXAMPLE 3: Item-to-Item Similarity - Product Recommendations")
    print("="*70)
    
    server = NewRetrievalMCPServer(data_dir=Path(__file__).parent / "data")
    
    # First, let's get a reference item
    reference_items = await server._search_items_by_attributes(
        keywords="iPhone",
        limit=1
    )
    
    if not reference_items.get('items'):
        print("\n‚ö†Ô∏è  No reference item found. Please ensure database has data.")
        return
    
    reference = reference_items['items'][0]
    reference_asin = reference['asin']
    
    print(f"\nüì± Reference Product:")
    print(f"   ASIN: {reference_asin}")
    print(f"   Title: {reference['title']}")
    print(f"   Brand: {reference['brand']}")
    print(f"   Category: {reference['category']}")
    
    print("\nüîç Finding similar products...")
    
    result = await server._recall_similar_items(
        query_text=reference_asin,
        top_k=5
    )
    
    if 'error' in result:
        print(f"\n‚ù?Error: {result['error']}")
        return
    
    print(f"\n‚ú?Found {result['total_results']} similar items:")
    print("-" * 70)
    
    for i, item in enumerate(result.get('similar_items', []), 1):
        print(f"\n{i}. {item['title']}")
        print(f"   Brand: {item['brand']} | Category: {item['category']}")
        print(f"   Price: ${item.get('price', 'N/A')}")
        print(f"   Similarity Score: {item['similarity_score']:.3f}")


async def example_4_combined_workflow():
    """Example 4: Combined workflow using multiple tools"""
    
    print("\n" + "="*70)
    print("EXAMPLE 4: Combined Workflow - Multi-Stage Retrieval")
    print("="*70)
    
    server = NewRetrievalMCPServer(data_dir=Path(__file__).parent / "data")
    
    # Stage 1: Semantic search to understand user intent
    print("\nüéØ Stage 1: Semantic Search")
    print("User query: 'premium noise canceling headphones for travel'")
    
    semantic_result = await server._search_items_by_semantic(
        query="premium noise canceling headphones for travel",
        top_k=10
    )
    
    print(f"   Found {semantic_result['total_results']} candidates")
    
    if not semantic_result.get('items'):
        print("   No items found")
        return
    
    # Stage 2: Apply attribute filters to narrow down
    print("\nüéØ Stage 2: Apply Attribute Filters")
    print("   Filter: Category=Audio, Price<$500, Rating>=4.5")
    
    filtered_result = await server._search_items_by_attributes(
        category="Audio",
        max_price=500,
        min_rating=4.5,
        sort_by="rating_desc",
        limit=3
    )
    
    print(f"   Found {filtered_result['total_results']} high-quality options")
    
    if not filtered_result.get('items'):
        print("   No items passed filters")
        return
    
    # Stage 3: Get similar items for the top result
    top_item = filtered_result['items'][0]
    print(f"\nüéØ Stage 3: Find Alternatives Similar to Top Result")
    print(f"   Top result: {top_item['title']}")
    
    similar_result = await server._recall_similar_items(
        query_text=top_item['title'],
        top_k=3
    )
    
    print(f"   Found {similar_result.get('total_results', 0)} similar alternatives")
    
    # Final recommendations
    print("\n" + "="*70)
    print("üìã FINAL RECOMMENDATIONS:")
    print("="*70)
    
    print("\n‚ú?Top Match (from semantic + filters):")
    print(f"   {top_item['title']}")
    print(f"   ${top_item.get('price', 'N/A')} | {top_item.get('rating', 'N/A')}‚≠?)
    
    if similar_result.get('similar_items'):
        print("\nüîÑ Similar Alternatives:")
        for i, item in enumerate(similar_result['similar_items'][:3], 1):
            print(f"   {i}. {item['title']} (similarity: {item['similarity_score']:.2f})")


async def example_5_error_handling():
    """Example 5: Error handling and edge cases"""
    
    print("\n" + "="*70)
    print("EXAMPLE 5: Error Handling & Edge Cases")
    print("="*70)
    
    server = NewRetrievalMCPServer(data_dir=Path(__file__).parent / "data")
    
    # Test 1: Non-existent ASIN
    print("\n1Ô∏è‚É£ Test: Non-existent ASIN")
    result = await server._recall_similar_items(query_text="INVALID_TITLE")
    if 'error' in result:
        print(f"   ‚ú?Handled gracefully: {result['error']}")
    
    # Test 2: Empty query
    print("\n2Ô∏è‚É£ Test: Empty semantic query")
    result = await server._search_items_by_semantic(query="", top_k=5)
    print(f"   ‚ú?Returned {result.get('total_results', 0)} results")
    
    # Test 3: Very strict filters (no results expected)
    print("\n3Ô∏è‚É£ Test: Impossibly strict filters")
    result = await server._search_items_by_attributes(
        min_price=100000,
        max_price=100001,
        min_rating=5.0
    )
    print(f"   ‚ú?Returned {result.get('total_results', 0)} results (expected: 0)")
    
    # Test 4: Very high similarity threshold
    print("\n4Ô∏è‚É£ Test: Very high similarity threshold")
    # First get any item
    items = await server._search_items_by_attributes(limit=1)
    if items.get('items'):
        asin = items['items'][0]['asin']
        result = await server._recall_similar_items(
            query_text=items['items'][0]['title'],
            top_k=10
        )
        print(f"   ‚ú?Returned {result.get('total_results', 0)} results")


async def main():
    """Run all examples"""
    
    print("\n" + "="*70)
    print("üöÄ NEW RETRIEVAL MCP SERVER - USAGE EXAMPLES")
    print("="*70)
    
    # Check if data exists
    data_dir = Path(__file__).parent / "data"
    db_path = data_dir / "products.db"
    
    if not db_path.exists():
        print("\n‚ö†Ô∏è  Database not found!")
        print("\nPlease run one of the following first:")
        print("1. python test_new_server.py  (creates sample data)")
        print("2. python load_amazon_data.py --meta_file /path/to/item_meta.jsonl")
        return
    
    try:
        # Run examples
        await example_1_semantic_search()
        await example_2_attribute_filter()
        await example_3_similar_items()
        await example_4_combined_workflow()
        await example_5_error_handling()
        
        print("\n" + "="*70)
        print("‚ú?ALL EXAMPLES COMPLETED SUCCESSFULLY!")
        print("="*70)
        print("\nüí° Next Steps:")
        print("   1. Integrate these tools into your MCP workflow")
        print("   2. Generate synthetic tasks using task_synthesis")
        print("   3. Run benchmarks and evaluations")
        print("   4. Deploy to production")
        
    except Exception as e:
        print(f"\n‚ù?Error running examples: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
