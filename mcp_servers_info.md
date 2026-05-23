# MCP Server Information Summary

## Summary Information

- **Collection Time**: 2026-05-05T21:24:38.528055
- **Connection Mode**: INDIVIDUAL
- **Total Servers**: 5
- **Successful Connections**: 5
- **Failed Connections**: 0
- **Total Tools Discovered**: 17

## Server Details

###  retrieval-mcp-yelp-server

**Description**: 

**Connection Status**: success

**Available Tools** (4 ):

#### get_business_details

**Description**: Get details of a business by business name or business_id.

**Input Parameters**:
```json
{
  "type": "object",
  "properties": {
    "business_name": {
      "type": "string",
      "description": "Business name to get details for"
    },
    "business_id": {
      "type": "string",
      "description": "Business ID to get details for"
    }
  },
  "required": []
}
```

#### search_businesses

**Description**: Search businesses by keyword and optional nearby coordinates.

**Input Parameters**:
```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "Fuzzy search query to match against business name, address and/or categories"
    },
    "categories": {
      "type": "string",
      "description": "Exact category filter (e.g., 'Bars', 'Italian', 'Coffee')"
    },
    "location": {
      "type": "array",
      "description": "Filter businesses near [latitude, longitude] coordinates"
    },
    "business_ids": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "Optional candidate business_id whitelist"
    },
    "top_k": {
      "type": "integer",
      "description": "Maximum number of results to return",
      "default": 100
    }
  },
  "required": []
}
```

#### filter_businesses

**Description**: Filter businesses by category, optional nearby coordinates, optional open timestamp, and optional candidate IDs.

**Input Parameters**:
```json
{
  "type": "object",
  "properties": {
    "categories": {
      "type": "string",
      "description": "Category filter (e.g., 'Restaurants', 'Pizza')"
    },
    "location": {
      "type": "array",
      "description": "Filter businesses near [latitude, longitude] coordinates"
    },
    "open_timestamp": {
      "type": "number",
      "description": "UTC timestamp to check if business is open at that time"
    },
    "business_ids": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "Optional candidate business_id whitelist"
    },
    "top_k": {
      "type": "integer",
      "description": "Maximum number of results to return",
      "default": 100
    }
  },
  "required": []
}
```

#### recall_similar_items

**Description**: Collaborative filter: find businesses frequently visited together based on business name.

**Input Parameters**:
```json
{
  "type": "object",
  "properties": {
    "query_text": {
      "type": "string",
      "description": "Business name to find similar businesses for"
    },
    "top_k": {
      "type": "integer",
      "description": "Maximum number of similar businesses to return",
      "default": 100
    }
  },
  "required": [
    "query_text"
  ]
}
```

---

###  nlptool-mcp-yelp-server

**Description**: 

**Connection Status**: success

**Available Tools** (3 ):

#### query_sentiment

**Description**: Filter businesses by review sentiment. Find businesses with a minimum positive review rate.

Args:
    min_positive_rate: Minimum positive review rate (0-100). E.g., 80 means >80% positive.
    business_ids: Optional list of business_ids to restrict the filter to. When provided, ONLY
                  these businesses are evaluated and returned (as a whitelist). Use this to apply
                  sentiment filters to a specific candidate set. If omitted, all businesses are considered.

Returns:
    JSON string with matching businesses sorted by positive rate descending.

**Input Parameters**:
```json
{
  "properties": {
    "min_positive_rate": {
      "type": "number"
    },
    "business_ids": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    }
  },
  "required": [
    "min_positive_rate"
  ],
  "type": "object"
}
```

#### query_opinion

**Description**: Search review opinion aspects for the requested keywords.

**Input Parameters**:
```json
{
  "properties": {
    "keywords": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "keyword": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "business_ids": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    }
  },
  "type": "object"
}
```

#### query_summary

**Description**: Search review summary text for the requested keywords.

**Input Parameters**:
```json
{
  "properties": {
    "keywords": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "keyword": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "business_ids": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    }
  },
  "type": "object"
}
```

---

###  rating-mcp-yelp-server

**Description**: 

**Connection Status**: success

**Available Tools** (5 ):

#### get_top_rated

**Description**: Get top-rated Yelp businesses, optionally restricted by category and candidate business IDs.

**Input Parameters**:
```json
{
  "properties": {
    "category": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "business_ids": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "item_ids": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "limit": {
      "default": 20,
      "type": "integer"
    }
  },
  "type": "object"
}
```

#### get_most_reviewed

**Description**: Get businesses with the largest review counts, optionally restricted by category and candidate IDs.

**Input Parameters**:
```json
{
  "properties": {
    "category": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "business_ids": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "item_ids": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "limit": {
      "default": 20,
      "type": "integer"
    }
  },
  "type": "object"
}
```

#### filter_by_rating

**Description**: Filter businesses by rating range, category, and optional candidate IDs.

**Input Parameters**:
```json
{
  "properties": {
    "min_rating": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "max_rating": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "category": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "business_ids": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "item_ids": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "limit": {
      "default": 20,
      "type": "integer"
    }
  },
  "type": "object"
}
```

#### filter_by_rating_count

**Description**: Filter businesses by review-count thresholds and optional candidate IDs.

**Input Parameters**:
```json
{
  "properties": {
    "min_count": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "max_count": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "min_reviews": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "max_reviews": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "category": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "business_ids": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "item_ids": {
      "anyOf": [
        {
          "items": {
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null
    },
    "limit": {
      "default": 20,
      "type": "integer"
    }
  },
  "type": "object"
}
```

#### compare_ratings

**Description**: Compare ratings of multiple businesses side by side.

Args:
    item_ids: List of business_ids to compare.

Returns:
    JSON string with rating comparison, sorted by rating descending.

**Input Parameters**:
```json
{
  "properties": {
    "item_ids": {
      "items": {
        "type": "string"
      },
      "type": "array"
    }
  },
  "required": [
    "item_ids"
  ],
  "type": "object"
}
```

---

###  rec-mcp-yelp-server

**Description**: 

**Connection Status**: success

**Available Tools** (2 ):

#### rank_items

**Description**: Rank a list of candidate items for a user based on predicted relevance scores using SASRec model.

Args:
    user_id: User identifier
    item_ids: List of item business_ids to rank

Returns:
    JSON string with ranked items, each containing item_id, score, and rank

**Input Parameters**:
```json
{
  "properties": {
    "user_id": {
      "type": "string"
    },
    "item_ids": {
      "items": {
        "type": "string"
      },
      "type": "array"
    }
  },
  "required": [
    "user_id",
    "item_ids"
  ],
  "type": "object"
}
```

#### get_user_history

**Description**: Get a user's interaction history.

Args:
    user_id: User identifier

Returns:
    JSON string with user_id, history_length, and last 20 items

**Input Parameters**:
```json
{
  "properties": {
    "user_id": {
      "type": "string"
    }
  },
  "required": [
    "user_id"
  ],
  "type": "object"
}
```

---

###  googlemap-mcp-server

**Description**: 

**Connection Status**: success

**Available Tools** (3 ):

#### google_geo

**Description**: Convert a street address to latitude and longitude coordinates (geocoding). Use this when the user provides an address and needs coordinates.

**Input Parameters**:
```json
{
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
  "required": [
    "address"
  ]
}
```

#### google_regeo

**Description**: Convert latitude and longitude coordinates to a street address (reverse geocoding). Use this when the user provides coordinates and needs the address.

**Input Parameters**:
```json
{
  "type": "object",
  "properties": {
    "latlng": {
      "type": "string",
      "description": "Comma-separated latitude,longitude (e.g., '38.5325582,-90.3090247')"
    }
  },
  "required": [
    "latlng"
  ]
}
```

#### google_distance

**Description**: Calculate the distance and travel time between two locations given their coordinates. Use this when the user asks 'how far' or 'how long to travel' between two points.

**Input Parameters**:
```json
{
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
  "required": [
    "origin",
    "destination"
  ]
}
```

---

