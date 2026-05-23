#!/usr/bin/env python3
"""
Train SASRec model on user sequences data.
"""
import json
import random
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from tqdm import tqdm

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
        
        # Embeddings
        self.item_emb = nn.Embedding(item_num + 1, hidden_units, padding_idx=0)
        self.pos_emb = nn.Embedding(maxlen, hidden_units)
        self.emb_dropout = nn.Dropout(p=dropout_rate)
        
        # Transformer encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_units,
            nhead=num_heads,
            dim_feedforward=hidden_units * 4,
            dropout=dropout_rate,
            batch_first=True,
            norm_first=True
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_blocks)
        self.layer_norm = nn.LayerNorm(hidden_units)
        
        # Initialize
        self._init_weights()
    
    def _init_weights(self):
        nn.init.normal_(self.item_emb.weight, std=0.01)
        nn.init.normal_(self.pos_emb.weight, std=0.01)
        with torch.no_grad():
            self.item_emb.weight[0].fill_(0)
    
    def forward(self, item_seq: torch.Tensor) -> torch.Tensor:
        """
        Args:
            item_seq: (batch, seq_len) item indices
        Returns:
            (batch, seq_len, hidden) sequence representations
        """
        batch_size, seq_len = item_seq.shape
        
        # Embeddings
        item_embs = self.item_emb(item_seq)
        item_embs *= self.hidden_units ** 0.5
        
        positions = torch.arange(seq_len, device=item_seq.device).unsqueeze(0)
        pos_embs = self.pos_emb(positions)
        
        seq_embs = self.emb_dropout(item_embs + pos_embs)
        
        # Masks
        padding_mask = (item_seq == 0)  # (batch, seq)
        causal_mask = nn.Transformer.generate_square_subsequent_mask(seq_len, device=item_seq.device)
        
        # Encode
        output = self.encoder(seq_embs, mask=causal_mask, src_key_padding_mask=padding_mask)
        output = self.layer_norm(output)
        
        return output
    
    def predict(self, item_seq: torch.Tensor, item_indices: torch.Tensor) -> torch.Tensor:
        """
        Predict scores for candidate items.
        """
        output = self.forward(item_seq)
        final_feat = output[:, -1, :]  # Last position
        
        item_embs = self.item_emb(item_indices)
        
        if item_indices.dim() == 1:
            return torch.matmul(final_feat, item_embs.T)
        else:
            return (final_feat.unsqueeze(1) * item_embs).sum(dim=-1)


class SASRecDataset(Dataset):
    """Dataset for SASRec training."""
    
    def __init__(self, sequences: List[List[int]], item_num: int, maxlen: int = 50):
        self.item_num = item_num
        self.maxlen = maxlen
        self.sequences = [seq for seq in sequences if len(seq) >= 3]
        print(f"Valid sequences: {len(self.sequences)}")
    
    def __len__(self):
        return len(self.sequences)
    
    def __getitem__(self, idx):
        seq = self.sequences[idx]
        
        # Input: all but last, Target pos: all but first
        input_seq = seq[:-1]
        target_pos = seq[1:]
        
        # Truncate
        if len(input_seq) > self.maxlen:
            input_seq = input_seq[-self.maxlen:]
            target_pos = target_pos[-self.maxlen:]
        
        # Pad from left
        pad_len = self.maxlen - len(input_seq)
        input_seq = [0] * pad_len + input_seq
        target_pos = [0] * pad_len + target_pos
        
        # Negative sampling for each position
        seq_set = set(seq)
        target_neg = []
        for _ in range(self.maxlen):
            neg = random.randint(1, self.item_num)
            while neg in seq_set:
                neg = random.randint(1, self.item_num)
            target_neg.append(neg)
        
        return {
            'input_seq': torch.tensor(input_seq, dtype=torch.long),
            'target_pos': torch.tensor(target_pos, dtype=torch.long),
            'target_neg': torch.tensor(target_neg, dtype=torch.long)
        }


def load_data() -> Tuple[Dict[str, int], List[List[int]]]:
    """Load user sequences and build item mapping."""
    print(f"Loading data from {USER_SEQ_FILE}...")
    
    asins = set()
    raw_sequences = []
    
    with open(USER_SEQ_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                items = [item['asin'] for item in data.get('items', [])]
                if items:
                    raw_sequences.append(items)
                    asins.update(items)
    
    asin_to_idx = {asin: idx + 1 for idx, asin in enumerate(sorted(asins))}
    sequences = [[asin_to_idx[asin] for asin in raw_seq] for raw_seq in raw_sequences]
    
    print(f"Loaded {len(sequences)} sequences, {len(asin_to_idx)} items")
    avg_len = np.mean([len(s) for s in sequences])
    print(f"Average sequence length: {avg_len:.2f}")
    
    return asin_to_idx, sequences


def train_sasrec(
    sequences: List[List[int]],
    item_num: int,
    maxlen: int = 50,
    hidden_units: int = 64,
    num_blocks: int = 2,
    num_heads: int = 1,
    dropout_rate: float = 0.2,
    batch_size: int = 128,
    lr: float = 0.001,
    num_epochs: int = 50,
    device: str = 'cuda' if torch.cuda.is_available() else 'cpu'
):
    """Train SASRec model."""
    print(f"\nTraining on device: {device}")
    print(f"Config: hidden={hidden_units}, heads={num_heads}, blocks={num_blocks}, maxlen={maxlen}")
    
    dataset = SASRecDataset(sequences, item_num, maxlen)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=0)
    
    model = SASRec(
        item_num=item_num,
        maxlen=maxlen,
        hidden_units=hidden_units,
        num_blocks=num_blocks,
        num_heads=num_heads,
        dropout_rate=dropout_rate
    ).to(device)
    
    print(f"Parameters: {sum(p.numel() for p in model.parameters()):,}")
    
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, betas=(0.9, 0.98))
    bce_loss = nn.BCEWithLogitsLoss(reduction='none')
    
    best_loss = float('inf')
    
    for epoch in range(1, num_epochs + 1):
        model.train()
        losses = []
        
        pbar = tqdm(loader, desc=f"Epoch {epoch}/{num_epochs}")
        for batch in pbar:
            input_seq = batch['input_seq'].to(device)
            target_pos = batch['target_pos'].to(device)
            target_neg = batch['target_neg'].to(device)
            
            # Forward
            seq_output = model(input_seq)  # (batch, seq, hidden)
            
            # Get embeddings
            pos_emb = model.item_emb(target_pos)
            neg_emb = model.item_emb(target_neg)
            
            # Scores
            pos_scores = (seq_output * pos_emb).sum(dim=-1)
            neg_scores = (seq_output * neg_emb).sum(dim=-1)
            
            # Loss on valid positions only
            mask = (target_pos != 0).float()
            pos_loss = bce_loss(pos_scores, torch.ones_like(pos_scores)) * mask
            neg_loss = bce_loss(neg_scores, torch.zeros_like(neg_scores)) * mask
            
            loss = (pos_loss.sum() + neg_loss.sum()) / (mask.sum() + 1e-8)
            
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
            
            losses.append(loss.item())
            pbar.set_postfix({'loss': f'{loss.item():.4f}'})
        
        avg_loss = np.mean(losses)
        print(f"Epoch {epoch}: Loss = {avg_loss:.4f}")
        
        if avg_loss < best_loss:
            best_loss = avg_loss
            torch.save(model.state_dict(), MODEL_PATH)
            print(f"  -> Saved (loss={best_loss:.4f})")
    
    print(f"\nDone! Best loss: {best_loss:.4f}")
    return model


def main():
    random.seed(42)
    np.random.seed(42)
    torch.manual_seed(42)
    
    asin_to_idx, sequences = load_data()
    item_num = len(asin_to_idx)
    
    with open(MAPPING_PATH, 'w', encoding='utf-8') as f:
        json.dump(asin_to_idx, f)
    print(f"Saved mapping to {MAPPING_PATH}")
    
    train_sasrec(
        sequences=sequences,
        item_num=item_num,
        maxlen=50,
        hidden_units=64,
        num_blocks=2,
        num_heads=1,
        dropout_rate=0.2,
        batch_size=128,
        lr=0.001,
        num_epochs=100
    )


if __name__ == "__main__":
    main()
