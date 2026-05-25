import os
import gzip
import json
import argparse


def _iter_json_file(path):
    """Auto-detect file type and read json/jsonl/json.gz files"""
    try:
# �?gzip
        if path.endswith('.gz'):
            f = gzip.open(path, "rt", encoding="utf-8", errors="ignore")
        else:
            f = open(path, "r", encoding="utf-8", errors="ignore")
        
        with f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue
    except Exception:
        return


def _initial_counts(path):
    """Count user-item interactions"""
    u, i = {}, {}
    for obj in _iter_json_file(path):
        uid = obj.get("reviewerID")
        asin = obj.get("asin")
        if uid and asin:
            u[uid] = u.get(uid, 0) + 1
            i[asin] = i.get(asin, 0) + 1
    return u, i


def _build_user_sequences(path, valid_users, valid_items, min_rating=3.0):
    """Build user interaction sequences"""
    import random
    
    seqs = {}
    used_items = set()
    filtered_count = 0
    
    for obj in _iter_json_file(path):
        uid = obj.get("reviewerID")
        asin = obj.get("asin")
        ts = obj.get("unixReviewTime")
        rating = obj.get("overall")
        
        if not (uid and asin and ts):
            continue
        if uid not in valid_users or asin not in valid_items:
            continue
        if rating is not None and float(rating) < min_rating:
            filtered_count += 1
            continue
        
        if uid not in seqs:
            seqs[uid] = []
        seqs[uid].append((int(ts), asin, float(rating) if rating else None))
        used_items.add(asin)
    
# �? for uid in seqs:
        seqs[uid].sort(key=lambda x: x[0])
    
    print(f"Filtered {filtered_count} interactions with rating < {min_rating}")
    print(f"Total user sequences: {len(seqs)}")
    
    return seqs, used_items

def _write_user_sequences(out_path, seqs):
    """Write user sequence file"""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for uid, lst in seqs.items():
            f.write(json.dumps({
                "user_id": uid,
                "items": [{"asin": asin, "timestamp": ts, "rating": rating} for ts, asin, rating in lst],
                "count": len(lst),
            }) + "\n")


def _collect_reviews_by_asin(review_path, keep_items):
    reviews_by_asin = {}
    ratings_by_asin = {}
    
    for obj in _iter_json_file(review_path):
        asin = obj.get("asin")
        review_text = obj.get("reviewText")
        rating = obj.get("overall")
        
        if asin and asin in keep_items:
            # Collect reviews
            if review_text:
                if asin not in reviews_by_asin:
                    reviews_by_asin[asin] = []
                reviews_by_asin[asin].append([review_text])
            
# �? if rating is not None:
                if asin not in ratings_by_asin:
                    ratings_by_asin[asin] = []
                ratings_by_asin[asin].append(float(rating))
    
# �? avg_ratings_by_asin = {}
    for asin, ratings in ratings_by_asin.items():
        avg_ratings_by_asin[asin] = round(sum(ratings) / len(ratings), 2)
    
    return reviews_by_asin, avg_ratings_by_asin


def _load_meta_items(meta_path):
""" meta asin/parent_asin ，�?""
    resolved = meta_path
    if not os.path.isfile(resolved):
        candidates = []
        if meta_path.endswith(".jsonl"):
            candidates = [
                meta_path + ".gz",
                meta_path.replace(".jsonl", ".json"),
                meta_path.replace(".jsonl", ".json.gz"),
            ]
        elif meta_path.endswith(".json"):
            candidates = [meta_path + ".gz", meta_path + "l", meta_path + "l.gz"]
        for cand in candidates:
            if os.path.isfile(cand):
                print(f"Meta file not found at {meta_path}, using fallback {cand}")
                resolved = cand
                break
        else:
            print(f"Warning: meta file not found at {meta_path}, skip meta-based item filtering")
            return set()
    
    meta_items = set()
    for obj in _iter_json_file(resolved) or []:
        asin = obj.get("asin") or obj.get("parent_asin")
        if asin:
            meta_items.add(asin)
    print(f"Loaded {len(meta_items)} items from meta file")
    return meta_items


def _write_item_meta(meta_path, out_path, keep_items, reviews_by_asin=None, avg_ratings_by_asin=None):
"""�?""
    if not keep_items:
        print("Warning: keep_items is empty, skip writing item metadata")
        return

# �?meta
    if not os.path.isfile(meta_path):
        candidates = []
        if meta_path.endswith(".jsonl"):
            candidates = [
                meta_path + ".gz",
                meta_path.replace(".jsonl", ".json"),
                meta_path.replace(".jsonl", ".json.gz"),
            ]
        elif meta_path.endswith(".json"):
            candidates = [meta_path + ".gz", meta_path + "l", meta_path + "l.gz"]
        for cand in candidates:
            if os.path.isfile(cand):
                print(f"Meta file not found at {meta_path}, using fallback {cand}")
                meta_path = cand
                break
        else:
            print(f"Warning: meta file not found at {meta_path}, skip writing item metadata")
            return

# （，�? exclude_fields = {"videos", "bought_together"} #
    
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    written_count = 0
    
    with open(out_path, "w", encoding="utf-8") as f:
        for obj in _iter_json_file(meta_path) or []:
# �?asin
            asin = obj.get("asin") or obj.get("parent_asin")
            
            if asin and asin in keep_items:
                # Keep most fields, only exclude explicitly unwanted ones
                filtered_obj = {k: v for k, v in obj.items() if k not in exclude_fields}
                
                # Ensure asin field exists
                if "asin" not in filtered_obj:
                    filtered_obj["asin"] = asin
                
                # Add reviews
                if reviews_by_asin and asin in reviews_by_asin:
                    filtered_obj["reviews"] = reviews_by_asin[asin]
                
                # Add user average rating
                if avg_ratings_by_asin and asin in avg_ratings_by_asin:
                    filtered_obj["user_average_rating"] = avg_ratings_by_asin[asin]
                
# �? if "categories" in filtered_obj and "category" not in filtered_obj:
                    filtered_obj["category"] = filtered_obj["categories"]
                
                if "store" in filtered_obj and "brand" not in filtered_obj:
                    filtered_obj["brand"] = filtered_obj["store"]
                
                f.write(json.dumps(filtered_obj) + "\n")
                written_count += 1
    
    print(f"Written {written_count} item metadata records")


def _sample_users(seqs, sample_size):
    """Randomly sample users"""
    import random
    if len(seqs) <= sample_size:
        return seqs
    
    sampled_users = random.sample(list(seqs.keys()), sample_size)
    return {uid: seqs[uid] for uid in sampled_users}


def main():
    parser = argparse.ArgumentParser(description="Process Amazon Electronics data")
    parser.add_argument("--input_dir", type=str, required=True, help="Input directory containing review and meta files")
    parser.add_argument("--review_file", type=str, default="Electronics_5.json", help="Review file name")
    parser.add_argument("--meta_file", type=str, default="meta_Electronics.jsonl", help="Meta file name")
    parser.add_argument("--k", type=int, default=20, help="Minimum interactions threshold")
    parser.add_argument("--sample_users", type=int, default=None, help="Sample N users")
    parser.add_argument("--min_rating", type=float, default=3.0, help="Minimum rating threshold")
    args = parser.parse_args()

    # Set paths
    review_path = os.path.join(args.input_dir, args.review_file)
    meta_path = os.path.join(args.input_dir, args.meta_file)
    out_dir = os.path.join(args.input_dir, "processed")
    os.makedirs(out_dir, exist_ok=True)
    
    print(f"Processing files:")
    print(f"  Review: {review_path}")
    print(f"  Meta: {meta_path}")
    print(f"  Output: {out_dir}")
    
# user �?item
    print("\n=== Filtering users and items ===")
    
    meta_items = _load_meta_items(meta_path)
    
    u_counts, i_counts = {}, {}
    for obj in _iter_json_file(review_path):
        uid = obj.get("reviewerID")
        asin = obj.get("asin")
        if not (uid and asin):
            continue
        if meta_items and asin not in meta_items:
            continue
        u_counts[uid] = u_counts.get(uid, 0) + 1
        i_counts[asin] = i_counts.get(asin, 0) + 1
    
    print(f"Initial: {len(u_counts)} users, {len(i_counts)} items (meta-filtered)")
    
    valid_users = {u for u, c in u_counts.items() if c >= args.k}
    valid_items = {a for a, c in i_counts.items() if c >= args.k}
    
    if not valid_users:
        print(f"Warning: no users remain with k={args.k}, fallback to all users")
        valid_users = set(u_counts.keys())
    if not valid_items:
        print(f"Warning: no items remain with k={args.k}, fallback to all items")
        valid_items = set(i_counts.keys())
    
    print(f"Filtered: {len(valid_users)} users, {len(valid_items)} items")

    print("\n=== Building user sequences ===")
    seqs, used_items = _build_user_sequences(review_path, valid_users, valid_items, min_rating=args.min_rating)

    if not seqs:
        print("Warning: no sequences built after filtering, retrying with all users/items")
        seqs, used_items = _build_user_sequences(review_path, set(u_counts.keys()), set(i_counts.keys()), min_rating=args.min_rating)
    
    if args.sample_users:
        print(f"\n=== Sampling {args.sample_users} users ===")
        seqs = _sample_users(seqs, args.sample_users)
        used_items = {asin for user_seq in seqs.values() for _, asin, _ in user_seq}
        print(f"Sampled users: {len(seqs)}")
        print(f"Deduped items after sampling: {len(used_items)}")
    
    print("\n=== Collecting reviews ===")
    reviews_by_asin, avg_ratings_by_asin = _collect_reviews_by_asin(review_path, used_items)
    print(f"Collected reviews for {len(reviews_by_asin)} items")
    print(f"Calculated average ratings for {len(avg_ratings_by_asin)} items")
    
    print("\n=== Writing output files ===")
    print(f"User sequences: {len(seqs)}, Used items: {len(used_items)}")
    _write_user_sequences(os.path.join(out_dir, "user_sequences.jsonl"), seqs)
    _write_item_meta(meta_path, os.path.join(out_dir, "item_meta.jsonl"), used_items, reviews_by_asin, avg_ratings_by_asin)
    
    print(f"\n�?Done! Output saved to {out_dir}")
    print(f"  - user_sequences.jsonl: {len(seqs)} users")
    print(f"  - item_meta.jsonl: {len(used_items)} items")


if __name__ == "__main__":
    main()
