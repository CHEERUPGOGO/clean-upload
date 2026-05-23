#!/bin/bash
# Quick start script for the new retrieval MCP server

set -e

echo "🚀 New Retrieval MCP Server - Quick Start"
echo "=========================================="

# Check if requirements are installed
echo ""
echo "📦 Checking dependencies..."
if ! python -c "import mcp" 2>/dev/null; then
    echo "⚠️  MCP not found. Installing dependencies..."
    pip install -r new_requirements.txt
else
    echo "✅ Dependencies OK"
fi

# Check if data exists
DATA_DIR="./data"
DB_PATH="$DATA_DIR/products.db"

if [ ! -f "$DB_PATH" ]; then
    echo ""
    echo "⚠️  Database not found at $DB_PATH"
    echo ""
    echo "Please load data first using one of these methods:"
    echo ""
    echo "1. Load from Amazon data:"
    echo "   python load_amazon_data.py --meta_file /path/to/item_meta.jsonl"
    echo ""
    echo "2. Run tests with sample data:"
    echo "   python test_new_server.py"
    echo ""
    exit 1
fi

echo ""
echo "✅ Database found: $DB_PATH"

# Check database stats
echo ""
echo "📊 Database Statistics:"
sqlite3 "$DB_PATH" "SELECT COUNT(*) as total FROM products" | while read count; do
    echo "   Total products: $count"
done

echo ""
echo "🎯 Starting server..."
echo "=========================================="
echo ""

# Start the server
python new_retrieval_server.py "$DATA_DIR"
