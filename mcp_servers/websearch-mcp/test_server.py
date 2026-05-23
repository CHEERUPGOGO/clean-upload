#!/usr/bin/env python3
"""Test script for Web Search MCP Server"""

import asyncio
import os

# 设置 API Key (测试前需要设�?
# os.environ["SERPER_API_KEY"] = "your_api_key_here"

from server import WebSearchMCPServer


async def test_web_search():
    """Test web search functionality"""
    server = WebSearchMCPServer()
    
    # 测试用例
    test_queries = [
        "iPhone 15 Pro review",
    ]
    
    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print('='*60)
        
        result = await server._web_search(query, num_results=3)
        
        if "error" in result:
            print(f"Error: {result['error']}")
            continue
        
        print(f"Total results: {result['total_results']}")
        
        # 打印搜索结果
        for i, item in enumerate(result.get('results', []), 1):
            print(f"\n[{i}] {item['title']}")
            print(f"    Link: {item['link']}")
            print(f"    Snippet: {item['snippet'][:100]}...")
        
        # 打印知识图谱
        if result.get('knowledge_graph'):
            kg = result['knowledge_graph']
            print(f"\nKnowledge Graph: {kg['title']} ({kg['type']})")
            if kg.get('description'):
                print(f"    {kg['description'][:100]}...")
        
        # 打印答案�?        if result.get('answer_box'):
            ab = result['answer_box']
            print(f"\nAnswer Box: {ab['title']}")
            print(f"    {ab['answer'][:100]}...")


if __name__ == "__main__":
    if not os.environ.get("SERPER_API_KEY"):
        print("Warning: SERPER_API_KEY not set!")
        print("Please set it with: export SERPER_API_KEY='your_key'")
        print("Get your free API key at: https://serper.dev/")
    
    asyncio.run(test_web_search())
