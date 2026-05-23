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
    asin_to_meta = {}
    
    print(f"📖 Loading metadata from: {jsonl_path}")
    
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                item = json.loads(line)
                
                # 尝试多个可能�?asin 字段
                asin = item.get('asin') or item.get('parent_asin')
                if not asin:
                    continue
                
                # 提取品牌（尝试多个字段）
                brand = item.get('brand') or item.get('store') or ''
                
                # 提取类别（尝试多个字段）
                category = item.get('category')
                if not category:
                    categories = item.get('categories')
                    if categories:
                        category = categories if isinstance(categories, str) else categories[0] if isinstance(categories, list) and categories else ''
                    else:
                        category = item.get('main_category') or ''
                
                # 提取描述
                description = item.get('description')
                if isinstance(description, list):
                    description = ' '.join(str(d) for d in description if d)
                
                # 提取评分
                rating = item.get('rating') or item.get('average_rating')
                if rating:
                    try:
                        rating = float(rating)
                    except (ValueError, TypeError):
                        rating = None
                
                # Extract fields
                asin_to_meta[asin] = {
                    'asin': asin,
                    'title': normalize_text(item.get('title')),
                    'brand': normalize_text(brand),
                    'category': normalize_text(category),
                    'price': extract_price(item.get('price')),
                    'rating': rating,
                    'description': normalize_text(description),
                    'features': normalize_text(item.get('features'))
                }
                
                if (line_num <= 3):
                    print(f"  Sample item {line_num}: {asin} - {asin_to_meta[asin]['title'][:50]}...")
                
            except json.JSONDecodeError as e:
                print(f"⚠️  Line {line_num}: JSON decode error - {e}")
                continue
            except Exception as e:
                print(f"⚠️  Line {line_num}: Error - {e}")
                continue
    
    print(f"�?Loaded {len(asin_to_meta)} items")
    return asin_to_meta


def create_database(db_path: Path, asin_to_meta: Dict[str, Dict], overwrite: bool = False):
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
    tmp_dir = tempfile.mkdtemp(prefix="amazon_db_")
    tmp_db = Path(tmp_dir) / "products.db"
    print(f"Building database in tmp: {tmp_db}")
    
    with sqlite3.connect(tmp_db) as conn:
        # Create table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                asin TEXT PRIMARY KEY,
                title TEXT,
                brand TEXT,
                category TEXT,
                price REAL,
                rating REAL,
                description TEXT,
                features TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON products(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_brand ON products(brand)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_price ON products(price)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rating ON products(rating)")
        
        print(f"Inserting {len(asin_to_meta)} products...")
        
        # Insert data
        inserted = 0
        skipped = 0
        
        for asin, meta in asin_to_meta.items():
            try:
                conn.execute("""
                    INSERT INTO products (asin, title, brand, category, price, rating, description, features)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    meta['asin'],
                    meta['title'],
                    meta['brand'],
                    meta['category'],
                    meta['price'],
                    meta['rating'],
                    meta['description'],
                    meta['features']
                ))
                inserted += 1
                
                if inserted % 1000 == 0:
                    print(f"  Inserted {inserted} items...")
                
            except sqlite3.IntegrityError:
                skipped += 1
            except Exception as e:
                print(f"Error inserting {asin}: {e}")
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
        print(f"�?Database contains {count} products")
        
        # Show sample statistics
        cursor = conn.execute("SELECT COUNT(DISTINCT category) FROM products WHERE category IS NOT NULL AND category != ''")
        categories = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(DISTINCT brand) FROM products WHERE brand IS NOT NULL AND brand != ''")
        brands = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM products WHERE price IS NOT NULL")
        with_price = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM products WHERE rating IS NOT NULL")
        with_rating = cursor.fetchone()[0]
        
        print(f"\n📊 Database Statistics:")
        print(f"  Total products: {count}")
        print(f"  Unique categories: {categories}")
        print(f"  Unique brands: {brands}")
        print(f"  Products with price: {with_price} ({100*with_price/count:.1f}%)")
        print(f"  Products with rating: {with_rating} ({100*with_rating/count:.1f}%)")
    
    return True


def main():
    parser = argparse.ArgumentParser(description="Load Amazon data into retrieval MCP server")
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
        help="Path to output database (default: ./data/products.db)"
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
        print(f"�?Error: Meta file not found: {meta_file}")
        return False
    
    if args.db_path:
        db_path = Path(args.db_path)
    else:
        db_path = Path(__file__).parents[2] / "data" / "amazon-electronics" / "products.db"
    
    print("🚀 Amazon Data Loader for New Retrieval MCP Server")
    print("=" * 60)
    print(f"Source: {meta_file}")
    print(f"Target: {db_path}")
    print("=" * 60)
    
    try:
        # Load metadata
        asin_to_meta = load_item_metadata(meta_file)
        
        if not asin_to_meta:
            print("�?No items loaded from metadata file")
            return False
        
        # Create database
        success = create_database(db_path, asin_to_meta, overwrite=args.overwrite)
        
        if success:
            print("\n" + "=" * 60)
            print("�?Data loading completed successfully!")
            print("=" * 60)
            print(f"\nNext steps:")
            print(f"1. Run the server:")
            print(f"   python new_retrieval_server.py {db_path.parent}")
            print(f"2. Or run tests:")
            print(f"   python test_new_server.py")
        
        return success
        
    except Exception as e:
        print(f"\n�?Error during data loading: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
