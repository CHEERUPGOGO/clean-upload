#!/usr/bin/env python3
"""
Web Search MCP Server - uses local mock data for benchmark testing.
Falls back to Serper API for queries not in the mock database.
"""
import json
import os
import httpx
from fastmcp import FastMCP

mcp = FastMCP("websearch-mcp")

SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")

# Pre-built mock search results keyed by matching keywords
MOCK_RESULTS = {
    "ELP 720p mini IP camera": {
        "results": [
            {"title": "ELP 1280x720p 1.0 Megapixel Mini IP Camera Specifications", "link": "https://www.amazon.com/dp/B00KA4M4WS", "snippet": "Resolution: 1280x720p (1.0MP), Protocol: ONVIF 2.0, Lens: 3.6mm, Compression: H.264/MJPEG, Min illumination: 0.01 Lux, Power: DC 12V, Size: 40x40mm, Network: RJ45 10/100M Ethernet, IR-cut filter for day/night.", "position": 1},
            {"title": "ELP Mini Hidden Network Camera Review - SecurityBros", "link": "https://securitybros.com/elp-mini-ip-camera-review", "snippet": "The ELP 720p mini IP camera supports ONVIF protocol, features H.264 compression, and works with most NVR systems. Compact 40x40mm form factor ideal for covert installations.", "position": 2}
        ],
        "knowledge_graph": {"title": "ELP 1MP Mini IP Camera", "type": "Product", "description": "720p HD mini IP camera with ONVIF support", "attributes": {"Resolution": "1280x720", "Sensor": "1/4 CMOS", "Protocol": "ONVIF 2.0"}},
    },
    "WLD Electric Universal Power Strip 6 outlets price": {
        "results": [
            {"title": "WLD Electric Universal Power Strip 6 Outlets with 2 USB Ports - Amazon.com", "link": "https://www.amazon.com/dp/B00B8BAC6C", "snippet": "Price: $24.99. Universal Power Strip with 6 outlets and 2 USB ports, supports 100V-220V/250V, 2500W surge protector with circuit breaker.", "position": 1},
            {"title": "WLD Universal Travel Power Strip - Best Prices 2024", "link": "https://www.bestbuy.com/wld-power-strip", "snippet": "Currently available for $22.49 on sale. Features universal worldwide outlets with EU plug, built-in circuit breaker for safety.", "position": 2}
        ],
        "knowledge_graph": {"title": "WLD Electric Universal Power Strip", "type": "Product", "description": "6-outlet universal power strip with USB", "attributes": {"Price": "$24.99", "Wattage": "2500W", "Outlets": "6 + 2 USB"}},
    },
    "FEMORO DisplayPort VGA adapter": {
        "results": [
            {"title": "FEMORO DisplayPort to VGA Adapter 1080P Converter - Amazon.com", "link": "https://www.amazon.com/dp/B01GORJXK0", "snippet": "DisplayPort to VGA adapter supporting up to 1080p@60Hz. Male DP to Female VGA. Compatible with desktops, laptops, projectors, HDTVs. Gold-plated connector, no driver needed.", "position": 1},
            {"title": "FEMORO DP to VGA Adapter Specs and Review", "link": "https://www.techradar.com/femoro-dp-vga", "snippet": "Max resolution: 1920x1080@60Hz. Input: DisplayPort 1.2 male. Output: VGA female (HD-15). Supports mirroring and extended display modes. Plug and play, no external power required.", "position": 2}
        ],
        "knowledge_graph": {"title": "FEMORO DisplayPort to VGA Adapter", "type": "Product", "description": "1080P DP to VGA converter", "attributes": {"Max Resolution": "1920x1080@60Hz", "Input": "DisplayPort 1.2", "Output": "VGA HD-15"}},
    },
    "Anker tempered glass screen protector iPad": {
        "results": [
            {"title": "Anker Tempered Glass Screen Protector for iPad 9.7 / iPad Air 2 - Amazon.com", "link": "https://www.amazon.com/dp/B00SF6VSVG", "snippet": "Price: $9.99. Compatible with iPad 9.7 (2018/2017), iPad Air 2, iPad Pro 9.7, and iPad Air. Features Retina Display clarity, anti-scratch, 9H hardness, easy bubble-free installation.", "position": 1},
            {"title": "Anker iPad Screen Protector Price Comparison", "link": "https://www.google.com/shopping/anker-ipad", "snippet": "Amazon: $9.99, Walmart: $11.49, eBay: $8.99. Fits all 9.7-inch iPad models including Air 2. 0.33mm tempered glass with oleophobic coating.", "position": 2}
        ],
        "knowledge_graph": {"title": "Anker Tempered Glass for iPad 9.7", "type": "Product", "description": "Screen protector for iPad 9.7/Air 2", "attributes": {"Price": "$9.99", "Hardness": "9H", "Thickness": "0.33mm"}},
    },
    "Grace Digital GDI-BTTV100 Wireless TV Speaker price": {
        "results": [
            {"title": "Grace Digital GDI-BTTV100 Wireless TV Speaker - Amazon.com", "link": "https://www.amazon.com/dp/B017W12JI0", "snippet": "Price: $79.99. Wireless TV speaker with Digital Voice Enhancing Equalization. Optimizes TV audio dialog for clearer speech. Bluetooth connectivity, 30-foot range.", "position": 1},
            {"title": "Grace Digital TV Speaker Review & Price Check 2024", "link": "https://www.rtings.com/grace-digital-tv-speaker", "snippet": "Currently selling for $79.99 on Amazon, $84.99 at Best Buy. Features voice enhancement EQ and Bluetooth streaming. Battery life up to 6 hours.", "position": 2}
        ],
        "knowledge_graph": {"title": "Grace Digital GDI-BTTV100", "type": "Product", "description": "Wireless TV speaker with voice enhancement", "attributes": {"Price": "$79.99", "Range": "30 feet", "Battery": "6 hours"}},
    },
    "Jawbone BIG JAMBOX Wireless Bluetooth Speaker price": {
        "results": [
            {"title": "Jawbone BIG JAMBOX Bluetooth Speaker - White Wave (Discontinued)", "link": "https://www.amazon.com/dp/B0061JPXLU", "snippet": "Discontinued by manufacturer. Used/Renewed prices range from $89.99 to $149.99. Original MSRP was $299.99. Powerful stereo sound with LiveAudio technology.", "position": 1},
            {"title": "Jawbone BIG JAMBOX Price Guide 2024 - eBay", "link": "https://www.ebay.com/jawbone-big-jambox", "snippet": "Used: $75-$120, Refurbished: $99-$150, New (sealed): $180-$250. White Wave color most popular. Features 15-hour battery, built-in speakerphone.", "position": 2}
        ],
        "knowledge_graph": {"title": "Jawbone BIG JAMBOX", "type": "Product", "description": "Discontinued premium Bluetooth speaker", "attributes": {"Original MSRP": "$299.99", "Used Price": "$89-$149", "Battery": "15 hours"}},
    },
    "Honeywell Ademco 958 Overhead Door Contacts price": {
        "results": [
            {"title": "Honeywell Ademco 958 Overhead Door Contacts - Amazon.com", "link": "https://www.amazon.com/dp/B0006M1I1W", "snippet": "Price: $14.50. Designed for overhead garage doors. Includes track-mounted sensor and magnet. Compatible with most alarm panels. UL listed.", "position": 1},
            {"title": "Ademco 958 Door Contact Review - Is It Worth It?", "link": "https://www.safehome.org/ademco-958-review", "snippet": "At $14.50, the Ademco 958 is one of the most affordable and reliable overhead door contacts available. Easy to install, works with Honeywell Vista and other panels. Highly recommended for garage security.", "position": 2}
        ],
        "knowledge_graph": {"title": "Honeywell Ademco 958", "type": "Product", "description": "Overhead garage door contact sensor", "attributes": {"Price": "$14.50", "Type": "Track-mounted", "Certification": "UL Listed"}},
    },
    "OMOTON Screen Protector Fire HD 10 specs": {
        "results": [
            {"title": "OMOTON Screen Protector for Fire HD 10 - Amazon.com", "link": "https://www.amazon.com/dp/B0144ARCNY", "snippet": "9H hardness tempered glass, HD clarity, fits Fire HD 10 and Fire HD 10 Kids Edition. 0.26mm ultra-thin, 2.5D rounded edges, anti-fingerprint oleophobic coating. Includes alignment frame for easy install.", "position": 1},
            {"title": "OMOTON Fire HD 10 Screen Protector Specifications", "link": "https://www.omoton.com/fire-hd-10-protector", "snippet": "Material: Tempered Glass. Hardness: 9H. Thickness: 0.26mm. Transmittance: 99.9% HD. Coating: Oleophobic anti-fingerprint. Edge: 2.5D rounded. Pack: 2 pieces. Compatible with Fire HD 10 (2017/2019).", "position": 2}
        ],
        "knowledge_graph": {"title": "OMOTON Fire HD 10 Screen Protector", "type": "Product", "description": "Tempered glass screen protector for Fire HD 10", "attributes": {"Hardness": "9H", "Thickness": "0.26mm", "Pack Size": "2"}},
    },
    "AmazonBasics AC Powered Speakers specs comparison": {
        "results": [
            {"title": "AmazonBasics AC Powered Computer Speakers Review & Specs", "link": "https://www.amazon.com/dp/B00GHY5JAO", "snippet": "Output power: 2.4W (1.2W per speaker). Frequency response: 80Hz-20kHz. USB powered with 3.5mm aux input. Dimensions: 2.8 x 3.0 x 4.5 inches per speaker. Weight: 0.85 lbs total.", "position": 1},
            {"title": "Budget Desktop Speakers Comparison: AmazonBasics vs Logitech vs Creative", "link": "https://www.tomsguide.com/budget-speakers-comparison", "snippet": "AmazonBasics ($15): 2.4W, USB powered, no Bluetooth. Logitech S120 ($12): 2.3W, 3.5mm only. Creative Pebble ($20): 4.4W, USB-C. AmazonBasics offers decent sound for basic use but lacks bass compared to Creative Pebble.", "position": 2}
        ],
        "knowledge_graph": {"title": "AmazonBasics Computer Speakers", "type": "Product", "description": "Budget USB-powered desktop speakers", "attributes": {"Power": "2.4W", "Input": "3.5mm + USB", "Price": "~$15"}},
    },
    "Konica Minolta Dimage Z6 price": {
        "results": [
            {"title": "Konica Minolta Dimage Z6 6MP Digital Camera - Price Guide", "link": "https://www.amazon.com/dp/B000AOFVZK", "snippet": "Discontinued. Used prices on Amazon: $29.99-$59.99. Features 6MP CCD sensor, 12x optical anti-shake zoom (35-420mm equivalent), 2.0-inch LCD.", "position": 1},
            {"title": "Konica Minolta Dimage Z6 Value in 2024 - KEH Camera", "link": "https://www.keh.com/konica-minolta-dimage-z6", "snippet": "Fair condition: $25-$35, Good: $40-$55, Excellent: $60-$75. A classic point-and-shoot from 2005, collectible value is minimal. 12x Anti-Shake zoom was advanced for its era.", "position": 2}
        ],
        "knowledge_graph": {"title": "Konica Minolta Dimage Z6", "type": "Product", "description": "6MP digital camera with 12x zoom (2005)", "attributes": {"Used Price": "$30-$75", "Sensor": "6MP CCD", "Zoom": "12x optical"}},
    },
}


def _find_mock(query: str):
    """Fuzzy match query against mock database keys."""
    query_lower = query.lower()
    best_key = None
    best_score = 0
    for key in MOCK_RESULTS:
        key_words = set(key.lower().split())
        query_words = set(query_lower.split())
        overlap = len(key_words & query_words)
        if overlap > best_score:
            best_score = overlap
            best_key = key
    # Require at least 2 word overlap
    if best_score >= 2:
        return MOCK_RESULTS[best_key]
    return None


@mcp.tool()
async def web_search(query: str, num_results: int = 10) -> str:
    """Search the web for external information NOT available in the local database.

    Use this tool ONLY when the requested information cannot be found through other local tools:
    - Current market prices (e.g., "how much does X cost now")
    - Detailed product specifications not in the database (e.g., "what are the specs of X")
    - External reviews and comparisons (e.g., "X vs Y comparison")
    - Product availability on other platforms (e.g., "where to buy X")
    - Any real-time or up-to-date information

    Do NOT use this tool if the query can be answered by local tools like search_keyword, filter_items_by_attributes, or get_item_details.

    Args:
        query: Search query (e.g., 'iPhone 15 Pro review', 'Sony speaker price 2024')
        num_results: Number of search results to return (default: 10)

    Returns:
        JSON string with search results including title, link, snippet, and optional knowledge graph
    """
    # Try mock data first
    mock = _find_mock(query)
    if mock:
        results = mock["results"][:num_results]
        return json.dumps({
            "query": query,
            "total_results": len(results),
            "results": results,
            "knowledge_graph": mock.get("knowledge_graph"),
            "answer_box": None
        }, indent=2, ensure_ascii=False)

    # Fallback to Serper API
    if not SERPER_API_KEY:
        return json.dumps({"error": "No results found and SERPER_API_KEY not set", "query": query})

    try:
        url = "https://google.serper.dev/search"
        headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
        payload = {"q": query, "num": num_results}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        organic_results = data.get("organic", [])
        results = [{
            "title": item.get("title", ""),
            "link": item.get("link", ""),
            "snippet": item.get("snippet", ""),
            "position": item.get("position", 0)
        } for item in organic_results[:num_results]]

        kg = data.get("knowledgeGraph", {})
        kg_info = {
            "title": kg.get("title", ""),
            "type": kg.get("type", ""),
            "description": kg.get("description", ""),
            "attributes": kg.get("attributes", {})
        } if kg else None

        ab = data.get("answerBox", {})
        answer = {
            "title": ab.get("title", ""),
            "answer": ab.get("answer", "") or ab.get("snippet", "")
        } if ab else None

        return json.dumps({
            "query": query,
            "total_results": len(results),
            "results": results,
            "knowledge_graph": kg_info,
            "answer_box": answer
        }, indent=2, ensure_ascii=False)

    except httpx.HTTPStatusError as e:
        return json.dumps({"error": f"HTTP error: {e.response.status_code}", "query": query})
    except Exception as e:
        return json.dumps({"error": str(e), "query": query})


if __name__ == "__main__":
    mcp.run()
