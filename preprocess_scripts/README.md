# Amazon Electronics
```bash
python preprocess_scripts/amazon_electronics_preprocess.py --input_dir /data/zhendong_data/cx/ReCall/data/amazon-electronics/ --sample_users 5000 --max_records 5000
```

# Yelp
```bash
python preprocess_scripts/yelp_preprocess.py --input_dir ./data/yelp_dataset --sample_users 1000
```

<!-- # Amazon MCP Server Test
```bash
cd /data/agentic-rec/rec-mcp-bench/mcp_servers/amazon-mcp-server
python test_client.py
```

# Retrieval MCP Server
```bash
cd /data/agentic-rec/rec-mcp-bench/mcp_servers/retrieval-mcp-server
pip install -r enhanced_requirements.txt
python enhanced_server.py
``` -->