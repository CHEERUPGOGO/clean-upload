#!/usr/bin/env python3
"""
Load Amazon Electronics data into the new retrieval MCP server database
Reads from preprocessed jsonl files and populates the SQLite database
"""

import json
import sqlite3
import argparse
from pathlib import Path
from typing import Dict, List
import sys


def normalize_text(value):
    """Normalize text value (handle None, lists, etc.)"""
    if value is None:
        return ""
    if isinstance(value, list):
        if not value:
            return ""
        # Join list items or take first
        return " ".join(str(x) for x in value if x) if len(value) > 1 else str(value[0])
    return str(value)


def extract_price(value) -> float:
    """Extract numeric price from string or return None"""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).strip()
        if not s:
            return None
        # Remove currency symbols and extract number
        import re
        match = re.search(r"[-+]?[0-9]*\.?[0-9]+", s)
        if match:
            return float(match.group(0))
    except Exception:
        pass
    return None


def load_item_metadata(jsonl_path: Path) -> Dict[str, Dict]:
    """Load item metadata from jsonl file"""
    business_id_to_meta = {}
    
    print(f"üìñ Loading metadata from: {jsonl_path}")
    
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                # print("line=",line)
                item = json.loads(line)
                
# ÔøΩ?business_id
                business_id = item.get('business_id')
                if not business_id:
                    continue
                
                # # Extract brand (try multiple fields)
                # brand = item.get('name')
                
                # # Extract category (try multiple fields)
                # category = item.get('category')
                
                # Extract description
                description = item.get('text')
                if isinstance(description, list):
                    description = ' '.join(str(d) for d in description if d)
                
                # Extract fields
                business_id_to_meta[business_id] = {
                    'business_id': business_id,
                    'name': normalize_text(item.get('name')),
                    'address': normalize_text(item.get('address')),
                    'city': normalize_text(item.get('city')),
                    'state': normalize_text(item.get('state')),
                    'postal_code': normalize_text(item.get('postal_code')),
                    'latitude': item.get('latitude'),
                    'longitude': item.get('longitude'),
                    'stars': item.get('stars'),
                    'review_count': item.get('review_count'),
                    'is_open': item.get('is_open'),
                    'categories': normalize_text(item.get('categories')),
                    'hours': normalize_text(item.get('hours')),
                    'text': normalize_text(description),
                    'review_rating': item.get('review_rating')
                }
                
                if (line_num <= 3):
                    print(f"  Sample item {line_num}: {business_id} - {business_id_to_meta[business_id]['name'][:50]}...")
                
            except json.JSONDecodeError as e:
                print(f"‚ö†Ô∏è  Line {line_num}: JSON decode error - {e}")
                continue
            except Exception as e:
                print(f"‚ö†Ô∏è  Line {line_num}: Error - {e}")
                continue
    
    print(f"‚ú?Loaded {len(business_id_to_meta)} items")
    return business_id_to_meta


def create_database(db_path: Path, business_id_to_meta: Dict[str, Dict], overwrite: bool = False):
    """Create and populate the database.
    
    Builds the SQLite database in /tmp first (avoids CephFS I/O issues),
    then copies the completed file to the target path.
    """
    import shutil, tempfile
    
    if db_path.exists():
        if overwrite:
            print(f"Removing existing database: {db_path}")
            try:
                db_path.unlink()
            except PermissionError:
                print(f"Warning: cannot remove {db_path} (permission denied), will overwrite via copy")
        else:
            print(f"Database already exists: {db_path}")
            response = input("Overwrite? (y/n): ")
            if response.lower() != 'y':
                print("Aborted")
                return False
            try:
                db_path.unlink()
            except PermissionError:
                print(f"Warning: cannot remove {db_path} (permission denied), will overwrite via copy")
    
    # Create database directory
    db_path.parent.mkdir(exist_ok=True, parents=True)
    
    # Build database in /tmp to avoid CephFS SQLite I/O issues
    tmp_dir = tempfile.mkdtemp(prefix="yelp_db_")
    tmp_db = Path(tmp_dir) / "yelp.db"
    print(f"Building database in tmp: {tmp_db}")
    
    with sqlite3.connect(tmp_db) as conn:
        # Create table
        conn.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    business_id TEXT PRIMARY KEY,
                    name TEXT,
                    address TEXT,
                    city TEXT,
                    state TEXT,
                    postal_code TEXT,
                    latitude REAL,
                    longitude REAL,
                    stars REAL,
                    review_count INTEGER,
                    is_open BOOLEAN,
                    categories TEXT,
                    hours TEXT,
                    text TEXT,
                    review_rating REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_categories ON products(categories)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_name ON products(name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_address ON products(address)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_city ON products(city)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_state ON products(state)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_postal_code ON products(postal_code)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_latitude ON products(latitude)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_longitude ON products(longitude)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_stars ON products(stars)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_review_count ON products(review_count)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_review_rating ON products(review_rating)")
        
        print(f"Inserting {len(business_id_to_meta)} products...")
        
        # Insert data
        inserted = 0
        skipped = 0
        
        for business_id, meta in business_id_to_meta.items():
            try:
                conn.execute("""
                    INSERT INTO products (business_id, name, address, city, state, postal_code, latitude, longitude, stars, review_count, is_open, categories, hours, text, review_rating)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    meta['business_id'],
                    meta['name'],
                    meta['address'],
                    meta['city'],
                    meta['state'],
                    meta['postal_code'],
                    meta['latitude'],
                    meta['longitude'],
                    meta['stars'],
                    meta['review_count'],
                    meta['is_open'],
                    meta['categories'],
                    meta['hours'],
                    meta['text'],
                    meta['review_rating']
                ))
                inserted += 1
                
                if inserted % 1000 == 0:
                    print(f"  Inserted {inserted} items...")
                
            except sqlite3.IntegrityError:
                skipped += 1
            except Exception as e:
                print(f"‚ö†Ô∏è  Error inserting {business_id}: {e}")
                skipped += 1
        
        conn.commit()
        
        print(f"Inserted: {inserted} items")
        if skipped > 0:
            print(f"Skipped: {skipped} items")
    
    # Copy completed database to target path
    print(f"Copying database to {db_path}...")
    try:
        shutil.copy2(tmp_db, db_path)
    except PermissionError:
        print(f"Error: cannot write to {db_path} (permission denied)")
        print(f"Database is available at: {tmp_db}")
        return False
    finally:
        # Cleanup tmp
        try:
            shutil.rmtree(tmp_dir)
        except Exception:
            pass

    # Verify database
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM products")
        count = cursor.fetchone()[0]
        print(f"‚ú?Database contains {count} products")
        
        # Show sample statistics
        cursor = conn.execute("SELECT COUNT(DISTINCT categories) FROM products WHERE categories IS NOT NULL AND categories != ''")
        categories = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(DISTINCT name) FROM products WHERE name IS NOT NULL AND name != ''")
        name = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(DISTINCT address) FROM products WHERE address IS NOT NULL AND address != ''")
        address = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM products WHERE latitude IS NOT NULL")
        latitude = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM products WHERE longitude IS NOT NULL")
        longitude = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM products WHERE review_rating IS NOT NULL")
        with_review_rating = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM products WHERE review_count IS NOT NULL")
        with_review_count = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM products WHERE stars IS NOT NULL")
        with_stars = cursor.fetchone()[0]
        
        print(f"\nüìä Database Statistics:")
        print(f"  Total products: {count}")
        print(f"  Unique categories: {categories}")
        print(f"  Unique names: {name}")
        print(f"  Unique addresses: {address}")
        print(f"  Products with latitude: {latitude} ({100*latitude/count:.1f}%)")
        print(f"  Products with longitude: {longitude} ({100*longitude/count:.1f}%)")
        print(f"  Products with review rating: {with_review_rating} ({100*with_review_rating/count:.1f}%)")
        print(f"  Products with review count: {with_review_count} ({100*with_review_count/count:.1f}%)")
        print(f"  Products with stars: {with_stars} ({100*with_stars/count:.1f}%)")
        
    return True


def main():
    parser = argparse.ArgumentParser(description="Load Yelp data into retrieval2 MCP server")
    parser.add_argument(
        "--meta_file",
        type=str,
        required=True,
        help="Path to item_meta.jsonl file"
    )
    # parser.add_argument(
    #     "--db_path",
    #     type=str,
    #     default="./data/yelp/yelp.db",
    #     help="Path to output database (default: ./data/yelp.db)"
    # )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing database without prompting"
    )
    
    args = parser.parse_args()
    
    # Resolve paths
    meta_file = Path(args.meta_file)
    if not meta_file.exists():
        print(f"‚ù?Error: Meta file not found: {meta_file}")
        return False
    
    # if args.db_path:
    #     db_path = Path(args.db_path)
    # else:
    db_path = Path(__file__).parents[2] / "data" / "yelp" / "yelp.db"
    
    print("üöÄ Yelp Data Loader for New Retrieval MCP Yelp Server")
    print("=" * 60)
    print(f"Source: {meta_file}")
    print(f"Target: {db_path}")
    print("=" * 60)
    
    try:
        # Load metadata
        business_id_to_meta = load_item_metadata(meta_file)
        
        if not business_id_to_meta:
            print("‚ù?No items loaded from metadata file")
            return False
        
        # Create database
        success = create_database(db_path, business_id_to_meta, overwrite=args.overwrite)
        
        if success:
            print("\n" + "=" * 60)
            print("‚ú?Data loading completed successfully!")
            print("=" * 60)
            print(f"\nNext steps:")
            print(f"1. Run the server:")
            print(f"   python new_retrieval_yelp_server.py {db_path.parent}")
            print(f"2. Or run tests:")
            print(f"   python test_new_yelp_server.py")
        
        return success
        
    except Exception as e:
        print(f"\n‚ù?Error during data loading: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
