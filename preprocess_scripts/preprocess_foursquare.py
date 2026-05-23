import json
import random
from collections import defaultdict
from datetime import datetime
from typing import Any

# 输入文件路径
input_file = "./data/foursquare/dataset_TSMC2014_NYC.txt"
# 输出文件路径
user_sequences_file = "./data/foursquare/processed/user_sequences.jsonl"
item_meta_file = "./data/foursquare/processed/item_meta.jsonl"
# 随机抽取的用户数�?num_users = 1000

# 存储用户的checkin记录
user_checkins = defaultdict(list)
# 存储场馆的元数据
venue_metadata = {}

# 定义时间字符串的格式
# %a: 星期几缩写（�?Fri�?# %b: 月份缩写（如 Apr�?# %d: 日期（如 13�?# %H: 小时�?4小时制，�?15�?# %M: 分钟（如 02�?# %S: 秒（�?32�?# %z: 时区偏移（如 +0000�?# %Y: 四位年份（如 2012�?format_str = "%a %b %d %H:%M:%S %z %Y"

# 读取输入文件
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
        
        # 存储用户的checkin记录
        user_checkins[user_id].append({
            'venue_id': venue_id,
            'latitude': latitude,
            'longitude': longitude,
            'utc_time': utc_time
        })
        
        # 存储场馆的元数据（只需要存储一次）
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

# 随机抽取1000个用�?print(f"Randomly selecting {num_users} users...")
selected_users = random.sample(list(user_checkins.keys()), min(num_users, len(user_checkins)))

# 按时间顺序排序用户的checkin记录
print("Sorting checkin records by time...")
for user_id in selected_users:
    # 按utc_time排序
    user_checkins[user_id].sort(key=lambda x: x['utc_time'])

# 生成user_sequences.jsonl
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

# 收集所有在选中用户中出现过的场�?print("Collecting venues from selected users...")
selected_venues = dict[str, list[Any]]()
for user_id in selected_users:
    for checkin in user_checkins[user_id]:
        current_venue = checkin['venue_id']
        # create empty list for initial usage
        if current_venue not in selected_venues:
            selected_venues[current_venue] = []
        selected_venues[current_venue].append(checkin)

print(f"Total venues in selected users: {len(selected_venues)}")

# 生成item_meta.jsonl
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
