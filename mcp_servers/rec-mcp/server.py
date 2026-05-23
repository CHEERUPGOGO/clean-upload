#!/usr/bin/env python3
"""
Recommendation MCP Server based on SASRec model.
Uses FastMCP for simplified server setup.
"""
import json
import sys
from pathlib import Path
from typing import List, Dict, Optional
import torch
import torch.nn as nn
from fastmcp import FastMCP

# Data paths
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "amazon-electronics" / "processed"
USER_SEQ_FILE = DATA_DIR / "user_sequences.jsonl"
MODEL_PATH = Path(__file__).parent / "sasrec_model.pt"
MAPPING_PATH = Path(__file__).parent / "item_mapping.json"


class SASRec(nn.Module):
    """Self-Attentive Sequential Recommendation Model."""
    
    def __init__(self, item_num: int, maxlen: int = 50, hidden_units: int = 64,
                 num_blocks: int = 2, num_heads: int = 1, dropout_rate: float = 0.2):
        super().__init__()
        self.item_num = item_num
        self.maxlen = maxlen
        self.hidden_units = hidden_units
        
        self.item_emb = nn.Embedding(item_num + 1, hidden_units, padding_idx=0)
        self.pos_emb = nn.Embedding(maxlen, hidden_units)
        self.emb_dropout = nn.Dropout(p=dropout_rate)
        
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_units, nhead=num_heads,
            dim_feedforward=hidden_units * 4, dropout=dropout_rate,
            batch_first=True, norm_first=True
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_blocks)
        self.layer_norm = nn.LayerNorm(hidden_units)
    
    def forward(self, item_seq: torch.Tensor) -> torch.Tensor:
        batch_size, seq_len = item_seq.shape
        item_embs = self.item_emb(item_seq) * (self.hidden_units ** 0.5)
        pos_embs = self.pos_emb(torch.arange(seq_len, device=item_seq.device).unsqueeze(0))
        seq_embs = self.emb_dropout(item_embs + pos_embs)
        
        padding_mask = (item_seq == 0)
        causal_mask = nn.Transformer.generate_square_subsequent_mask(seq_len, device=item_seq.device)
        output = self.encoder(seq_embs, mask=causal_mask, src_key_padding_mask=padding_mask)
        return self.layer_norm(output)
    
    def predict(self, item_seq: torch.Tensor, item_indices: torch.Tensor) -> torch.Tensor:
        final_feat = self.forward(item_seq)[:, -1, :]
        item_embs = self.item_emb(item_indices)
        if item_indices.dim() == 1:
            return torch.matmul(final_feat, item_embs.T)
        return (final_feat.unsqueeze(1) * item_embs).sum(dim=-1)


# Global state
model: Optional[SASRec] = None
asin_to_idx: Dict[str, int] = {}
idx_to_asin: Dict[int, str] = {}
user_sequences: Dict[str, List[str]] = {}
device = torch.device("cpu")


def load_user_sequences(user_seq_file: Path) -> Dict[str, List[str]]:
    """Load user interaction sequences."""
    sequences = {}
    with open(user_seq_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                user_id = data['user_id']
                items = [item['asin'] for item in data.get('items', [])]
                if items:
                    sequences[user_id] = items
    return sequences


def init_model_and_data():
    """Initialize model and load data."""
    global model, asin_to_idx, idx_to_asin, user_sequences
    
    if MAPPING_PATH.exists():
        with open(MAPPING_PATH, 'r', encoding='utf-8') as f:
            asin_to_idx = json.load(f)
        idx_to_asin = {idx: asin for asin, idx in asin_to_idx.items()}
        print(f"Loaded item mapping: {len(asin_to_idx)} items", file=sys.stderr, flush=True)
    else:
        print("ERROR: Item mapping not found!", file=sys.stderr, flush=True)
        return
    
    user_sequences = load_user_sequences(USER_SEQ_FILE)
    print(f"Loaded {len(user_sequences)} user sequences", file=sys.stderr, flush=True)
    
    model = SASRec(item_num=len(asin_to_idx), maxlen=50, hidden_units=64, num_blocks=2, num_heads=1)
    
    if MODEL_PATH.exists():
        try:
            model.load_state_dict(torch.load(MODEL_PATH, map_location=device))
            print(f"Loaded model from {MODEL_PATH}", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"Could not load model: {e}", file=sys.stderr, flush=True)
    
    model.eval()


# Initialize data on module load
init_model_and_data()

# Create FastMCP server
mcp = FastMCP("rec-mcp")


@mcp.tool()
def rank_items(user_id: str, item_ids: List[str]) -> str:
    """Rank a list of candidate items for a user based on predicted relevance scores using SASRec model.

    This tool takes BOTH user_id AND item_ids as input in a single call.
    Do NOT call get_user_history first â€?this tool already uses the user's full history internally.

    Args:
        user_id: User identifier (e.g., 'A1XEWKJCBGDAXJ')
        item_ids: List of item ASINs to rank (e.g., ['B00HAWW590', 'B00BX7TJ2O'])

    Returns:
        JSON string with ranked items, each containing item_id, score, and rank
    """
    if model is None:
        return json.dumps({"error": "Model not loaded"})
    
    # Deduplicate item_ids while preserving order
    seen = set()
    unique_ids = []
    for aid in item_ids:
        if aid not in seen:
            seen.add(aid)
            unique_ids.append(aid)
    item_ids = unique_ids
    
    user_seq = user_sequences.get(user_id, [])
    if not user_seq:
        results = [{"item_id": asin, "score": 0.5, "rank": i+1} for i, asin in enumerate(item_ids)]
        return json.dumps(results, ensure_ascii=False, indent=2)
    
    max_len = model.maxlen
    seq_indices = [asin_to_idx.get(asin, 0) for asin in user_seq[-max_len:]]
    if len(seq_indices) < max_len:
        seq_indices = [0] * (max_len - len(seq_indices)) + seq_indices
    
    candidate_indices = [asin_to_idx.get(asin, 0) for asin in item_ids]
    valid_candidates = [(i, idx) for i, idx in enumerate(candidate_indices) if idx > 0]
    
    if not valid_candidates:
        results = [{"item_id": asin, "score": 0.0, "rank": i+1} for i, asin in enumerate(item_ids)]
        return json.dumps(results, ensure_ascii=False, indent=2)
    
    with torch.no_grad():
        seq_tensor = torch.tensor([seq_indices], dtype=torch.long, device=device)
        valid_indices = torch.tensor([idx for _, idx in valid_candidates], device=device)
        scores = torch.sigmoid(model.predict(seq_tensor, valid_indices)).squeeze(0).cpu().numpy()
    
    score_map = {valid_candidates[i][0]: float(scores[i]) for i in range(len(valid_candidates))}
    results = [{"item_id": asin, "score": round(score_map.get(i, 0.0), 4)} for i, asin in enumerate(item_ids)]
    results.sort(key=lambda x: x["score"], reverse=True)
    for i, item in enumerate(results):
        item["rank"] = i + 1
    
    return json.dumps(results, ensure_ascii=False, indent=2)


@mcp.tool()
def get_user_history(user_id: str) -> str:
    """Get a user's interaction history.
    
    Args:
        user_id: User identifier
    
    Returns:
        JSON string with user_id, history_length, and last 20 items
    """
    history = user_sequences.get(user_id, [])
    result = {"user_id": user_id, "history_length": len(history), "items": history[-20:]}
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
