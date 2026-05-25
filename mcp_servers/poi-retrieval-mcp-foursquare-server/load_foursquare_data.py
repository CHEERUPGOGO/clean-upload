#!/usr/bin/env python3
"""
Load foursquare data into the new retrieval MCP server database
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
    venue_id_to_meta = {}
    
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
                venue_id = item.get('venue_id')
                if not venue_id:
                    venue_id = None
                    continue
 
                # Extract fields
                venue_id_to_meta[venue_id] = {
                    'venue_id': venue_id,
                    'venue_category_id': item.get('venue_category_id'),
                    'venue_category_name': item.get('venue_category_name'),
                    'latitude': item.get('latitude'),
                    'longitude': item.get('longitude'),
                    'checkin_counts': item.get('checkin_counts')
                }
                
                if (line_num <= 3):
                    print(f"   Sample item {line_num}: {venue_id} - {venue_id_to_meta[venue_id]['venue_category_name'][:50]}...")
                
            except json.JSONDecodeError as e:
                print(f"‚ö†Ô∏è  Line {line_num}: JSON decode error - {e}")
                continue
            except Exception as e:
                print(f"‚ö†Ô∏è  Line {line_num}: Error - {e}")
                continue
    
    print(f"‚ú?Loaded {len(venue_id_to_meta)} items")
    return venue_id_to_meta


def create_database(db_path: Path, venue_id_to_meta: Dict[str, Dict], overwrite: bool = False):
    """Create and populate the database"""
    
    if db_path.exists():
        if overwrite:
            print(f"üóëÔ∏? Removing existing database: {db_path}")
            db_path.unlink()
        else:
            print(f"‚ö†Ô∏è  Database already exists: {db_path}")
            response = input("Overwrite? (y/n): ")
            if response.lower() != 'y':
                print("‚ù?Aborted")
                return False
            db_path.unlink()
    
    # Create database directory
    db_path.parent.mkdir(exist_ok=True, parents=True)
    
    print(f"üìù Creating database: {db_path}")
    
    with sqlite3.connect(db_path) as conn:
        # Create table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                venue_id TEXT PRIMARY KEY,
                venue_category_id TEXT,
                venue_category_name TEXT,
                latitude FLOAT,
                longitude FLOAT,
                checkin_counts INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_category_id ON products(venue_category_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_categoty_name ON products(venue_category_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_latitude ON products(latitude)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_longitude ON products(longitude)")
        
        print(f"üíæ Inserting {len(venue_id_to_meta)} products...")
        
        # Insert data
        inserted = 0
        skipped = 0
        
        for venue_id, meta in venue_id_to_meta.items():
            try:
                conn.execute("""
                    INSERT INTO products (venue_id, venue_category_id, venue_category_name, latitude, longitude, checkin_counts)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    meta['venue_id'],
                    meta['venue_category_id'],
                    meta['venue_category_name'],
                    meta['latitude'],
                    meta['longitude'],
                    meta['checkin_counts']
                ))
                inserted += 1
                
                if inserted % 1000 == 0:
                    print(f"  Inserted {inserted} items...")
                
            except sqlite3.IntegrityError:
                skipped += 1
            except Exception as e:
                print(f"‚ö†Ô∏è  Error inserting {venue_id}: {e}")
                skipped += 1
        
        conn.commit()
        
        print(f"‚ú?Inserted: {inserted} items")
        if skipped > 0:
            print(f"‚ö†Ô∏è  Skipped: {skipped} items")
    
    # Verify database
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM products")
        count = cursor.fetchone()[0]
        print(f"‚ú?Database contains {count} products")
        
        # Show sample statistics
        cursor = conn.execute("SELECT COUNT(DISTINCT venue_category_id) FROM products WHERE venue_category_id IS NOT NULL AND venue_category_id != ''")
        category_ids = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(DISTINCT venue_category_name) FROM products WHERE venue_category_name IS NOT NULL AND venue_category_name != ''")
        category_names = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM products WHERE latitude IS NOT NULL")
        with_latitude = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM products WHERE longitude IS NOT NULL")
        with_longitude = cursor.fetchone()[0]
        
        print(f"\nüìä Database Statistics:")
        print(f"  Total products: {count}")
        print(f"  Unique category ids: {category_ids}")
        print(f"  Unique category names: {category_names}")
        print(f"  Products with latitude: {with_latitude} ({100*with_latitude/count:.1f}%)")
        print(f"  Products with longitude: {with_longitude} ({100*with_longitude/count:.1f}%)")
    
    return True


def main():
    parser = argparse.ArgumentParser(description="Load Foursquare data into retrieval MCP server")
    parser.add_argument(
        "--meta_file",
        type=str,
        required=True,
        help="Path to item_meta.jsonl file"
    )
    parser.add_argument(
        "--db_path",
        type=str,
        default=None,
        help="Path to output database (default: ./data/foursquare.db)"
    )
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
    
    if args.db_path:
        db_path = Path(args.db_path)
    else:
        db_path = Path(__file__).parent / "data" / "foursquare.db"
    
    print("üöÄ Foursquare Data Loader for New Retrieval MCP Foursquare Server")
    print("=" * 60)
    print(f"Source: {meta_file}")
    print(f"Target: {db_path}")
    print("=" * 60)
    
    try:
        # Load metadata
        venue_id_to_meta = load_item_metadata(meta_file)
        
        if not venue_id_to_meta:
            print("‚ù?No items loaded from metadata file")
            return False
        
        # Create database
        success = create_database(db_path, venue_id_to_meta, overwrite=args.overwrite)
        
        if success:
            print("\n" + "=" * 60)
            print("‚ú?Data loading completed successfully!")
            print("=" * 60)
            print(f"\nNext steps:")
            print(f"1. Run the server:")
            print(f"   python new_retrieval_foursquare_server.py {db_path.parent}")
            print(f"2. Or run tests:")
            print(f"   python test_new_foursquare_server.py")
        
        return success
        
    except Exception as e:
        print(f"\n‚ù?Error during data loading: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
