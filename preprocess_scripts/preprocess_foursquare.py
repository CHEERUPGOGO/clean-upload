import json
import random
from collections import defaultdict
from datetime import datetime
from typing import Any

# Input file path
input_file = "./data/foursquare/dataset_TSMC2014_NYC.txt"
# Output file path
user_sequences_file = "./data/foursquare/processed/user_sequences.jsonl"
item_meta_file = "./data/foursquare/processed/item_meta.jsonl"
# �?num_users = 1000

# Store user checkin records
user_checkins = defaultdict(list)
# Store venue metadata
venue_metadata = {}

# Define time string format
# %a: （�?Fri�?# %b: （ Apr�?# %d: （ 13�?# %H: �?4，�?15�?# %M: （ 02�?# %S: （�?32�?# %z: （ +0000�?# %Y: （ 2012�?format_str = "%a %b %d %H:%M:%S %z %Y"

# Read input files
print("Reading input file...")
with open(input_file, 'r', encoding='latin-1') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        parts = line.split('\t')
        if len(parts) != 8:
            continue
        
        user_id = parts[0]
        venue_id = parts[1]
        venue_category_id = parts[2]
        venue_category_name = parts[3]
        latitude = float(parts[4])
        longitude = float(parts[5])
        # timezone_offset = int(parts[6])
        utc_time = datetime.strptime(parts[7], format_str).timestamp()
        
        # Store user checkin records
        user_checkins[user_id].append({
            'venue_id': venue_id,
            'latitude': latitude,
            'longitude': longitude,
            'utc_time': utc_time
        })
        
# Store venue metadata（）
        if venue_id not in venue_metadata:
            venue_metadata[venue_id] = {
                'venue_id': venue_id,
                'venue_category_id': venue_category_id,
                'venue_category_name': venue_category_name,
                'latitude': latitude,
                'longitude': longitude
            }

print(f"Total users found: {len(user_checkins)}")
print(f"Total venues found: {len(venue_metadata)}")

# 1000�?print(f"Randomly selecting {num_users} users...")
selected_users = random.sample(list(user_checkins.keys()), min(num_users, len(user_checkins)))

# Sort user checkin records by time
print("Sorting checkin records by time...")
for user_id in selected_users:
    # Sort by utc_time
    user_checkins[user_id].sort(key=lambda x: x['utc_time'])

# Generate user_sequences.jsonl
print("Generating user_sequences.jsonl...")
with open(user_sequences_file, 'w', encoding='utf-8') as f:
    for user_id in selected_users:
        checkins = user_checkins[user_id]
        user_data = {
            'user_id': user_id,
            'list_checkin': checkins,
            'count': len(checkins)
        }
        if user_data['count'] < 10:
            print("DEBUG PRINT")
            print(user_data)
        f.write(json.dumps(user_data, ensure_ascii=False) + '\n')

# �?print("Collecting venues from selected users...")
selected_venues = dict[str, list[Any]]()
for user_id in selected_users:
    for checkin in user_checkins[user_id]:
        current_venue = checkin['venue_id']
        # create empty list for initial usage
        if current_venue not in selected_venues:
            selected_venues[current_venue] = []
        selected_venues[current_venue].append(checkin)

print(f"Total venues in selected users: {len(selected_venues)}")

# Generate item_meta.jsonl
print("Generating item_meta.jsonl...")
with open(item_meta_file, 'w', encoding='utf-8') as f:
    for venue_id in selected_venues:
        if not isinstance(venue_id, str) or venue_id == 'checkin_counts':
            continue
        
        if venue_id in venue_metadata:
            checkin_counts = len(selected_venues[venue_id])
            venue_metadata[venue_id]['checkin_counts'] = checkin_counts
            f.write(json.dumps(venue_metadata[venue_id], ensure_ascii=False) + '\n')

print("Preprocessing completed successfully!")
print(f"Output files:")
print(f"- {user_sequences_file}")
print(f"- {item_meta_file}")
