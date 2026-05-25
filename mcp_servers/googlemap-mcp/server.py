import asyncio
import math
import json
import sys
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("googlemap-mcp-server")
# MCP imports
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types
# Create Server instance named "my-custom-tools"
# app = Server("my-custom-tools")

# （Tools）（Resources�?import aiohttp

# ========== Required Configuration ==========
# Amap Web Service API Key
# Get it at: https://lbs.amap.com/dev/
# GOOGLE_API_KEY=''

# ========== API URL Configuration (optional, use defaults) ==========
# Geocoding
# GOOGLE_GEO_URL='https://maps.googleapis.com/maps/api/geocode/json?'
# GOOGLE_REGEO_URL='https://maps.googleapis.com/maps/api/geocode/json?'
# GOOGLE_DIRECTION_MATRIX_URL='https://maps.googleapis.com/maps/api/distancematrix/json?'
# # Route planning
# AMAP_DRIVING_URL='https://restapi.amap.com/v5/direction/driving'
# AMAP_WALKING_URL='https://restapi.amap.com/v5/direction/walking'
# AMAP_BICYCLING_URL='https://restapi.amap.com/v5/direction/bicycling'
# AMAP_EBIKE_URL='https://restapi.amap.com/v5/direction/electrobike'
# AMAP_BUS_URL='https://restapi.amap.com/v5/direction/transit/integrated'
# AMAP_SUBWAY_TRANSIT='https://restapi.amap.com/v5/direction/transit/integrated'

# # POI search
# AMAP_SEARCH_POI_URL='https://restapi.amap.com/v5/place/text'
# AMAP_SEARCH_POI_AROUND_URL='https://restapi.amap.com/v5/place/around'
# AMAP_SEARCH_POI_POLYGON_URL='https://restapi.amap.com/v5/place/polygon'
# AMAP_SEARCH_POI_DETAIL_URL='https://restapi.amap.com/v5/place/detail'
# AMAP_AOI_POLYLINE_URL='https://restapi.amap.com/v5/aoi/polyline'

########## 
# this method should not be used in production, it is only for testing
# this method is a cheap bypass to get location and lonlat from source data
def load_item_meta(DATA_DIR: Path, bypass_index: int, items: list[dict]) -> list[dict]:

    META_FILE = DATA_DIR / "item_meta.jsonl"
    """Load item metadata with rating information."""
    if not META_FILE.exists():
        return items
    with open(META_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                item={}
                retrieved_item = json.loads(line)
                item['index'] = bypass_index
                item['latitude'] = retrieved_item.get('latitude', 0.0)
                item['longitude'] = retrieved_item.get('longitude', 0.0)
                item['address'] = retrieved_item.get('address', '')
                item['city'] = retrieved_item.get('city', '')
                items.append(item)
                bypass_index += 1
    return items
# this method should not be used in production, it is only for testing
# this method is a cheap bypass to get location and lonlat from source data
##########

class GoogleMapServer:
    def __init__(self):
        self.server = Server("googlemap-tools")

        ########## 
        # this method should not be used in production, it is only for testing
        # this method is a cheap bypass to get location and lonlat from source data
        # Load data at startup
        bypass_index = 0
        self.item_data = []
        DATA_DIR = Path(__file__).parent.parent.parent / "data" / "foursquare"
        self.item_data = load_item_meta(DATA_DIR, bypass_index, self.item_data)
        DATA_DIR = Path(__file__).parent.parent.parent / "data" / "yelp"
        self.item_data = load_item_meta(DATA_DIR, bypass_index + len(self.item_data), self.item_data)
        print(f"Loaded {len(self.item_data)} items with address info", file=sys.stderr, flush=True)
        # this method should not be used in production, it is only for testing
        # this method is a cheap bypass to get location and lonlat from source data
        ##########

        @self.server.list_tools()
        async def handle_list_tools() -> list[types.Tool]:
            """List available retrieval tools"""
            return [
                types.Tool(
                    name="google_geo",
                    description="Convert a street address to latitude and longitude coordinates (geocoding). Use this when the user provides an address and needs coordinates.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "address": {
                                "type": "string",
                                "description": "Street address (e.g., '4265 Reavis Barracks Rd')"
                            },
                            "city": {
                                "type": "string",
                                "description": "City name (e.g., 'St. Louis')"
                            }
                        },
                        "required": ["address"]
                    }
                ),
                types.Tool(
                    name="google_regeo",
                    description="Convert latitude and longitude coordinates to a street address (reverse geocoding). Use this when the user provides coordinates and needs the address.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "latlng": {
                                "type": "string",
                                "description": "Comma-separated latitude,longitude (e.g., '38.5325582,-90.3090247')"
                            }
                        },
                        "required": ["latlng"]
                    }
                ),
                types.Tool(
                    name="google_distance",
                    description="Calculate the distance and travel time between two locations given their coordinates. Use this when the user asks 'how far' or 'how long to travel' between two points.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "origin": {
                                "type": "string",
                                "description": "Origin coordinates as 'latitude,longitude' (e.g., '38.5325582,-90.3090247')"
                            },
                            "destination": {
                                "type": "string",
                                "description": "Destination coordinates as 'latitude,longitude' (e.g., '27.930772,-82.4571776')"
                            },
                            "mode": {
                                "type": "string",
                                "description": "Optional travel mode from the task, such as walking or driving"
                            }
                        },
                        "required": ["origin", "destination"]
                    }
                )
            ]
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
            """Handle tool calls"""
            try:
                if name == "google_geo":
                    result = await self._google_geo(**arguments)
                elif name == "google_regeo":
                    result = await self._google_regeo(**arguments)
                elif name == "google_distance":
                    result = await self._google_distance(**arguments)
                # elif name == "filter_businesses":
                #     result = await self._filter_businesses(**arguments)
                # elif name == "item2item_search":
                #     result = await self._recall_similar_items(**arguments)
                else:
                    raise ValueError(f"Unknown tool: {name}")
                
                return [types.TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
                
            except Exception as e:
                logger.error(f"Error in tool {name}: {e}", exc_info=True)
                return [types.TextContent(type="text", text=json.dumps({"error": str(e), "tool": name}))]



    async def _google_geo(self, address: str, city: str = None) -> dict:
        """get latitude and longitude from address, uses bypasses and do not actual query google map api
        Args:
            address: detailed address
        Returns:
            return latitude and longitude
        """
        # formatted_address = address.replace(' ', '+')
        # # Build request URL
        # url = f"{GOOGLE_GEO_URL}key={GOOGLE_API_KEY}&address={formatted_address}"
        # if city:
        #     url += f"&city={city}"

# # Error handling and timeout control： aiohttp �?asyncio.timeout
        # try:
        #     async with aiohttp.ClientSession() as session:
# # Use asyncio.wait_for for timeout control（�?Python�? # async def fetch():
        #             async with session.get(url) as response:
# # �?HTTP
        #                 response.raise_for_status()
        #                 return await response.json()
                
        #         data = await asyncio.wait_for(fetch(), timeout=10)
                
# # �?API
        #         if data.get('status') != '1':
        #             error_info = data.get('info', 'Unknown error')
        #             return {"error": f"Geocoding API error: {error_info}"}

# # �? # geocodes = data.get('geocodes', [])
        #         if not geocodes:
        #             return {"error": "No results found for the given address."}

        #         location = geocodes[0].get('location')
        #         formatted_address = geocodes[0].get('formatted_address')
        #         result_text = f"Address '{formatted_address}' coordinates: {location}"

        #         return {"location": location, "formatted_address": formatted_address}

        # except asyncio.TimeoutError:
        #     return {"error": "Geocoding request timed out after 10 seconds."}
        # except aiohttp.ClientResponseError as e:
        #     return {"error": f"HTTP error occurred: {e.status} - {e.message}"}
        # except Exception as e:
        #     return {"error": f"An unexpected error occurred: {str(e)}"}

        ########## 
        # this method should not be used in production, it is only for testing
        # this method is a cheap bypass to get location and lonlat from source data
        for item in self.item_data:
            if item.get('address') == address:
                location = f"{item.get('latitude')},{item.get('longitude')}"
                formatted_address = f"{item.get('address')}, {item.get('city')}"
                return {"location": location, "formatted_address": formatted_address}

        return {"error": "No results found for the given address."}
        # this method should not be used in production, it is only for testing
        # this method is a cheap bypass to get location and lonlat from source data
        ##########
    
    async def _google_regeo(self, latlng: str) -> dict:
        """get address from latitude and longitude, uses bypasses and do not actual query google map api
        Args:
            latlng: latitude and longitude, e.g. 116.397428,39.90923
        Returns:
            return address
        """
        # # Build request URL
        # url = f"{GOOGLE_REGEO_URL}?key={GOOGLE_API_KEY}&latlng={latlng}"

# # Error handling and timeout control： aiohttp �?asyncio.timeout
        # try:
        #     async with aiohttp.ClientSession() as session:
# # Use asyncio.wait_for for timeout control（�?Python�? # async def fetch():
        #             async with session.get(url) as response:
# # �?HTTP
        #                 response.raise_for_status()
        #                 return await response.json()
                
        #         data = await asyncio.wait_for(fetch(), timeout=10)
                
# # �?API
        #         if data.get('status') != '1':
        #             error_info = data.get('info', 'Unknown error')
        #             return {"error": f"Geocoding API error: {error_info}"}

# # �? # geocodes = data.get('geocodes', [])
        #         if not geocodes:
        #             return {"error": "No results found for the given address."}

        #         location = geocodes[0].get('location')
        #         formatted_address = geocodes[0].get('formatted_address')
        #         result_text = f"Address '{formatted_address}' coordinates: {location}"

        #         return {"location": location, "formatted_address": formatted_address}

        # except asyncio.TimeoutError:
        #     return {"error": "Geocoding request timed out after 10 seconds."}
        # except aiohttp.ClientResponseError as e:
        #     return {"error": f"HTTP error occurred: {e.status} - {e.message}"}
        # except Exception as e:
        #     return {"error": f"An unexpected error occurred: {str(e)}"}

        ########## 
        # this method should not be used in production, it is only for testing
        # this method is a cheap bypass to get location and lonlat from source data
        query_latitude, query_longitude = latlng.split(',')
        lat_min = float(query_latitude) - 0.01
        lat_max = float(query_latitude) + 0.01
        lon_min = float(query_longitude) - 0.01
        lon_max = float(query_longitude) + 0.01
        for item in self.item_data:
            if lat_min <= float(item.get('latitude')) <= lat_max and lon_min <= float(item.get('longitude')) <= lon_max:
                location = f"{item.get('latitude')},{item.get('longitude')}"
                formatted_address = f"{item.get('address')}, {item.get('city')}"
                return {"location": location, "formatted_address": formatted_address}
        
        return {"error": "No results found for the given coordinates."}
        # this method should not be used in production, it is only for testing
        # this method is a cheap bypass to get location and lonlat from source data
        ##########

    async def _google_distance(self, origin: str, destination: str, mode: str = None) -> dict:
        """get distance between two points, uses bypasses and do not actual query google map api
        Args:
            origin: origin point, e.g. 116.397428,39.90923
            destination: destination point, e.g. 116.407395,39.916527
        Returns:
            return distance and travel time(by driving) between two points
        """
        # # Build request URL
        # url = f"{GOOGLE_DISTANCE_MATRIX_URL}key={GOOGLE_API_KEY}&origins={origin}&destinations={destination}&mode=driving"

# # Error handling and timeout control： aiohttp �?asyncio.timeout
        # try:
        #     async with aiohttp.ClientSession() as session:
# # Use asyncio.wait_for for timeout control（�?Python�? # async def fetch():
        #             async with session.get(url) as response:
# # �?HTTP
        #                 response.raise_for_status()
        #                 return await response.json()
                
        #         data = await asyncio.wait_for(fetch(), timeout=10)
                
# # �?API
        #         if data.get('status') != '1':
        #             error_info = data.get('info', 'Unknown error')
        #             return {"error": f"Geocoding API error: {error_info}"}

# # �? # rows = data.get('rows', [])
        #         if not rows:
        #             return {"error": "No results found for the given address."}

# # （：�? # distance_meters = rows[0].get('elements', [{}])[0].get('distance', {}).get('value', None)
        #         if distance_meters is None:
        #             return {"error": "Distance value not found in the response."}

        #         return {"distance_meters": distance_meters}

        #         return {"location": location, "formatted_address": formatted_address}

        # except asyncio.TimeoutError:
        #     return {"error": "Geocoding request timed out after 10 seconds."}
        # except aiohttp.ClientResponseError as e:
        #     return {"error": f"HTTP error occurred: {e.status} - {e.message}"}
        # except Exception as e:
        #     return {"error": f"An unexpected error occurred: {str(e)}"}

        ########## 
        # this method should not be used in production, it is only for testing
        # this method is a cheap bypass to get location and lonlat from source data
        origin_latitude, origin_longitude = origin.split(',')
        destination_latitude, destination_longitude = destination.split(',')

# （�? R = 6371000
        
# �? lat1_rad = math.radians(float(origin_latitude))
        lon1_rad = math.radians(float(origin_longitude))
        lat2_rad = math.radians(float(destination_latitude))
        lon2_rad = math.radians(float(destination_longitude))
        
# �? dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        
        # Haversine formula
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        # Calculate distance
        distance = R * c
        
# （ 30 km/h�?13.41m/s�? travel_time_seconds = distance / 13.41
        
        return {"distance": distance, "travel_time": travel_time_seconds}
        # this method should not be used in production, it is only for testing
        # this method is a cheap bypass to get location and lonlat from source data
        ##########

async def main():
    """Main server entry point"""
    
    server_instance = GoogleMapServer()
    logger.info("Starting new Google Map server...")
    
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server_instance.server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="google-map-server",
                server_version="1.0.0",
                capabilities=server_instance.server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities=None,
                )
            )
        )

if __name__ == "__main__":
    asyncio.run(main())
