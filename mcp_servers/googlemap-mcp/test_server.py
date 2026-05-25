#!/usr/bin/env python3
"""Test script for AMAP MCP Server"""

import asyncio
import os
import json

from server import GoogleMapServer

# from fastmcp import Client

# client = Client("http://localhost:8000/mcp")

async def test_google_geo(server):
    """Test google geo functionality"""
    print("\n" + "="*60)
    print("TEST 1: Get Address from Latitude and Longitude")
    print("="*60)

    address = "5505 S Virginia St"
    city = "Reno"
    print(f"Address: '{address}' in city '{city}'")

    result = await server._google_geo(
        address=address,
        city=city
    )
    
    if "error" in result:
        print(f"Error: {result['error']}")
        
    '''
        "name": "Romano's Macaroni Grill", 
        "address": "5505 S Virginia St", 
        "city": "Reno", 
        "state": "NV", 
        "postal_code": "89502", 
        "latitude": 39.4761165, 
        "longitude": -119.7893392, 
    '''

    print(f"Returns: {result}")
        
        # # Print search results
        # for i, item in enumerate(result.get('results', []), 1):
        #     print(f"\n[{i}] {item['title']}")
        #     print(f"    Link: {item['link']}")
        #     print(f"    Snippet: {item['snippet'][:100]}...")
        
        # # Print knowledge graph
        # if result.get('knowledge_graph'):
        #     kg = result['knowledge_graph']
        #     print(f"\nKnowledge Graph: {kg['title']} ({kg['type']})")
        #     if kg.get('description'):
        #         print(f"    {kg['description'][:100]}...")
        
# # �? # if result.get('answer_box'):
        #     ab = result['answer_box']
        #     print(f"\nAnswer Box: {ab['title']}")
        #     print(f"    {ab['answer'][:100]}...")

async def test_google_regeo(server):
    """Test google regeo functionality"""

    print("\n" + "="*60)
    print("TEST 1: Get Address from Latitude and Longitude")
    print("="*60)

    # latlng = "36.162649, -86.775973"
    latlng = "35.9568449367,-86.8024716902"
    print(f"LatLng: '{latlng}'")

    result = await server._google_regeo(
        latlng=latlng
    )
    
    if "error" in result:
        print(f"Error: {result['error']}")
        
    '''
        "name": "Mike's Ice Cream", 
        "address": "129 2nd Ave N", 
        "city": "Nashville", 
        "state": "TN", 
        "postal_code": "37201", 
        "latitude": 36.1626492, 
        "longitude": -86.7759733,
    '''
    print(f"Returns: {result}")

async def test_google_distance(server):
    """Test google distance functionality"""

    print("\n" + "="*60)
    print("TEST 3: Get Distance between two Latitude and Longitude")
    print("="*60)

    origin = "40.578400, -73.936185"
    destination = "40.699991, -73.911959"
    print(f"Origin: '{origin}'")
    print(f"Destination: '{destination}'")

    result = await server._google_distance(
        origin=origin,
        destination=destination
    )
    
    if "error" in result:
        print(f"Error: {result['error']}")
        
    '''
        from Kingsborough Community College,
        to Altamirano Financial Services (Office) in New York
        "distance": "16.3mi, aka 26232.31 m", 
        "duration": "50 mins, aka 3000 seconds", 
    '''
    print(f"Returns: {result}")

if __name__ == "__main__":

    server = GoogleMapServer()
    
    try:
        asyncio.run(test_google_geo(server))
        asyncio.run(test_google_regeo(server))
        asyncio.run(test_google_distance(server))
    except Exception as e:
        print(f"Test failed: {e}")
