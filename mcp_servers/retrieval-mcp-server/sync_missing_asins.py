#!/usr/bin/env python3
"""
Sync missing ASINs into retrieval-mcp-server's products.db.

Finds ASINs present in rec-mcp's item_mapping.json but absent from
products.db, looks them up in item_meta.jsonl, and inserts them.

Usage:
    python sync_missing_asins.py \
        --item_mapping ../../mcp_servers/rec-mcp/item_mapping.json \
        --meta_file ../../data/amazon-electronics/processed/item_meta.jsonl \
        --db_path ./data/products.db
"""

import json
import sqlite3
import argparse
import re
from pathlib import Path


def normalize_text(value):
    if value is None:
        return ""
    if isinstance(value, list):
        if not value:
            return ""
        return " ".join(str(x) for x in value if x) if len(value) > 1 else str(value[0])
    return str(value)


def extract_price(value) -> float:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            return float(value)
        match = re.search(r"[-+]?[0-9]*\.?[0-9]+", str(value).strip())
        if match:
            return float(match.group(0))
    except Exception:
        pass
    return None


def main():
    parser = argparse.ArgumentParser(description="Sync missing ASINs into products.db")
    parser.add_argument("--item_mapping", type=str, required=True,
                        help="Path to rec-mcp item_mapping.json")
    parser.add_argument("--meta_file", type=str, required=True,
                        help="Path to item_meta.jsonl (product metadata)")
    parser.add_argument("--db_path", type=str, default=None,
                        help="Path to products.db (default: ./data/products.db)")
    args = parser.parse_args()

    db_path = Path(args.db_path) if args.db_path else Path(__file__).parent / "data" / "products.db"

    # 1. Load all ASINs from rec-mcp
    print(f"Loading item_mapping from {args.item_mapping} ...")
    with open(args.item_mapping, "r", encoding="utf-8") as f:
        item_mapping = json.load(f)
    rec_asins = set(item_mapping.keys())
    print(f"  rec-mcp ASINs: {len(rec_asins)}")

    # 2. Find which ASINs are already in products.db
    print(f"Checking products.db at {db_path} ...")
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT asin FROM products").fetchall()
        db_asins = {r[0] for r in rows}
    print(f"  products.db ASINs: {len(db_asins)}")

    missing = rec_asins - db_asins
    print(f"  Missing ASINs: {len(missing)}")

    if not missing:
        print("All ASINs already in products.db. Nothing to do.")
        return

    # 3. Load metadata for missing ASINs from item_meta.jsonl
    print(f"Scanning {args.meta_file} for {len(missing)} missing ASINs ...")
    found_meta = {}
    with open(args.meta_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            asin = item.get("asin") or item.get("parent_asin")
            if not asin or asin not in missing:
                continue

            brand = item.get("brand") or item.get("store") or ""
            category = item.get("category")
            if not category:
                categories = item.get("categories")
                if categories:
                    category = categories if isinstance(categories, str) else (categories[0] if isinstance(categories, list) and categories else "")
                else:
                    category = item.get("main_category") or ""

            description = item.get("description")
            if isinstance(description, list):
                description = " ".join(str(d) for d in description if d)

            rating = item.get("rating") or item.get("average_rating")
            if rating:
                try:
                    rating = float(rating)
                except (ValueError, TypeError):
                    rating = None

            found_meta[asin] = {
                "asin": asin,
                "title": normalize_text(item.get("title")),
                "brand": normalize_text(brand),
                "category": normalize_text(category),
                "price": extract_price(item.get("price")),
                "rating": rating,
                "description": normalize_text(description),
                "features": normalize_text(item.get("features")),
            }

    print(f"  Found metadata for {len(found_meta)} / {len(missing)} missing ASINs")

    still_missing = missing - set(found_meta.keys())
    if still_missing:
        print(f"  {len(still_missing)} ASINs not in item_meta.jsonl â€?inserting as placeholder rows")

    # 4. Insert into products.db
    inserted = 0
    with sqlite3.connect(db_path) as conn:
        for asin in missing:
            meta = found_meta.get(asin, {
                "asin": asin,
                "title": "",
                "brand": "",
                "category": "",
                "price": None,
                "rating": None,
                "description": "",
                "features": "",
            })
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO products (asin, title, brand, category, price, rating, description, features) VALUES (?,?,?,?,?,?,?,?)",
                    (meta["asin"], meta["title"], meta["brand"], meta["category"],
                     meta["price"], meta["rating"], meta["description"], meta["features"]),
                )
                inserted += 1
            except Exception as e:
                print(f"  Error inserting {asin}: {e}")
        conn.commit()

    # 5. Verify
    with sqlite3.connect(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        rec_in_db = conn.execute(
            f"SELECT COUNT(*) FROM products WHERE asin IN ({','.join('?' * len(rec_asins))})",
            list(rec_asins),
        ).fetchone()[0]

    print(f"\nDone. Inserted {inserted} rows.")
    print(f"  products.db total: {total}")
    print(f"  rec-mcp ASINs now in DB: {rec_in_db} / {len(rec_asins)}")
    if rec_in_db == len(rec_asins):
        print("  All rec-mcp ASINs are now covered!")
    else:
        print(f"  WARNING: {len(rec_asins) - rec_in_db} still missing")


if __name__ == "__main__":
    main()
