import json
import numpy as np
from pathlib import Path
import argparse
import random
import sys
from collections import defaultdict, Counter

class BPRItem2Item:
    """
    BPR (Bayesian Personalized Ranking) Model for Item-to-Item Recommendation.
    Trains matrix factorization embeddings to optimize personalized ranking,
    then uses item embeddings for item-to-item similarity search.
    """
    def __init__(self, dims=64, lr=0.01, reg=0.001, epochs=100, seed=42):
        self.dims = dims
        self.lr = lr
        self.reg = reg
        self.epochs = epochs
        self.seed = seed
        
        # Data structures
        self.user_to_idx = {}
        self.asin_to_idx = {}
        self.idx_to_asin = {}
        self.pos_by_user = {} # user_idx -> set of item_idxs
        self.pos_by_item = defaultdict(set) # item_idx -> set of user_idxs (inverse index for eval)
        
        # Model parameters
        self.U = None # User embeddings
        self.V = None # Item embeddings
        
    def load_data(self, user_sequences_path):
        """Load user sequences and build indices"""
        print(f"📖 Loading data from {user_sequences_path}...")
        users = set()
        items = set()
        
        # First pass: collect unique users and items
        with open(user_sequences_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    data = json.loads(line)
                    u = data.get('user_id')
                    seq = data.get('items', [])
                    if not u or not seq: continue
                    
                    users.add(u)
                    for x in seq:
                        if isinstance(x, dict):
                            asin = x.get('asin')
                        else:
                            asin = x
                        if asin:
                            items.add(asin)
                except:
                    continue
                    
        # Create mappings
        self.user_to_idx = {u: i for i, u in enumerate(sorted(list(users)))}
        self.asin_to_idx = {a: i for i, a in enumerate(sorted(list(items)))}
        self.idx_to_asin = {i: a for a, i in self.asin_to_idx.items()}
        
        print(f"�?Found {len(users)} users and {len(items)} items")
        
        # Second pass: build interaction sets
        count = 0
        with open(user_sequences_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    data = json.loads(line)
                    u = data.get('user_id')
                    seq = data.get('items', [])
                    if not u or not seq: continue
                    
                    u_idx = self.user_to_idx[u]
                    if u_idx not in self.pos_by_user:
                        self.pos_by_user[u_idx] = set()
                        
                    for x in seq:
                        if isinstance(x, dict):
                            asin = x.get('asin')
                        else:
                            asin = x
                        if asin and asin in self.asin_to_idx:
                            i_idx = self.asin_to_idx[asin]
                            self.pos_by_user[u_idx].add(i_idx)
                            self.pos_by_item[i_idx].add(u_idx)
                            count += 1
                except:
                    continue
        print(f"�?Loaded {count} interactions")
                    
    def train(self):
        """Train BPR model using SGD"""
        print("🚀 Starting BPR training...")
        np.random.seed(self.seed)
        random.seed(self.seed)
        
        num_users = len(self.user_to_idx)
        num_items = len(self.asin_to_idx)
        
        # Initialize embeddings
        self.U = np.random.normal(0, 0.1, (num_users, self.dims)).astype(np.float32)
        self.V = np.random.normal(0, 0.1, (num_items, self.dims)).astype(np.float32)
        
        user_list = list(self.pos_by_user.keys())
        total_samples = sum(len(items) for items in self.pos_by_user.values())
        samples_per_epoch = total_samples * 2  # Adjust sampling rate as needed
        
        for epoch in range(self.epochs):
            loss = 0.0
            updates = 0
            
            # Simple SGD loop
            for _ in range(samples_per_epoch):
                u = random.choice(user_list)
                pos_items = list(self.pos_by_user[u])
                if not pos_items: continue
                
                i = random.choice(pos_items)
                j = random.randint(0, num_items - 1)
                while j in self.pos_by_user[u]:
                    j = random.randint(0, num_items - 1)
                    
                # Compute gradient
                u_vec = self.U[u]
                i_vec = self.V[i]
                j_vec = self.V[j]
                
                x_uij = np.dot(u_vec, i_vec) - np.dot(u_vec, j_vec)
                
                # Sigmoid
                if x_uij > 18: # Avoid overflow
                    sigmoid = 1.0
                elif x_uij < -18:
                    sigmoid = 0.0
                else:
                    sigmoid = 1.0 / (1.0 + np.exp(-x_uij))
                
                # Loss (log likelihood)
                loss += -np.log(sigmoid + 1e-10)
                
                # Gradient scalar: 1 - sigmoid(x_uij) = sigmoid(-x_uij)
                # Actually gradient of -ln(sigmoid(x)) is -1/sigmoid(x) * sigmoid(x)(1-sigmoid(x)) = -(1-sigmoid(x)) = sigmoid(x) - 1
                # But we want to MAXIMIZE likelihood, so minimize negative log likelihood.
                # Update rule: param += lr * gradient
                # Gradient of ln(sigmoid) wrt x is 1 - sigmoid(x).
                grad_common = 1.0 - sigmoid
                
                # Updates
                # U[u] += lr * (grad * (V[i] - V[j]) - reg * U[u])
                grad_u = grad_common * (i_vec - j_vec) - self.reg * u_vec
                grad_i = grad_common * (u_vec) - self.reg * i_vec
                grad_j = grad_common * (-u_vec) - self.reg * j_vec
                
                self.U[u] += self.lr * grad_u
                self.V[i] += self.lr * grad_i
                self.V[j] += self.lr * grad_j
                
                updates += 1
                
            avg_loss = loss / updates if updates > 0 else 0.0
            print(f"  Epoch {epoch+1}/{self.epochs} completed. Loss: {avg_loss:.4f} ({updates} updates)")

    def save_embeddings(self, output_dir):
        """Save item embeddings and mapping for retrieval server"""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        
        emb_path = out / "bpr_item_embeddings.npy"
        map_path = out / "bpr_asin_map.json"
        
        np.save(emb_path, self.V)
        with open(map_path, 'w', encoding='utf-8') as f:
            json.dump({"asin_to_idx": self.asin_to_idx}, f)
            
        print(f"💾 Saved embeddings to {emb_path}")

    def get_similar_items(self, asin, top_k=10):
        """Find similar items using trained embeddings (Cosine Similarity)"""
        if asin not in self.asin_to_idx:
            return []
            
        idx = self.asin_to_idx[asin]
        target_vec = self.V[idx]
        
        # Compute cosine similarity
        # Normalize target
        target_norm = np.linalg.norm(target_vec)
        if target_norm == 0: return []
        
        # Matrix multiplication
        dots = np.dot(self.V, target_vec)
        
        # Norms of all items
        norms = np.linalg.norm(self.V, axis=1)
        norms[norms == 0] = 1e-10
        
        sims = dots / (norms * target_norm)
        
        # Sort
        top_indices = np.argsort(sims)[::-1]
        
        results = []
        for i in top_indices:
            if i == idx: continue # Skip self
            results.append((self.idx_to_asin[i], float(sims[i])))
            if len(results) >= top_k:
                break
                
        return results

    def evaluate_precision_for_asin(self, asin, top_k=10):
        """
        Calculate precision for a specific ASIN.
        Precision is based on 'co-occurrence' in user histories.
        Ground Truth = Top K items that co-occur most frequently with this ASIN.
        """
        if asin not in self.asin_to_idx:
            print(f"⚠️ ASIN {asin} not found in training data.")
            return None
            
        # 1. Get Model Recommendations
        recs = self.get_similar_items(asin, top_k=top_k)
        rec_asins = [r[0] for r in recs]
        
        # 2. Get Ground Truth (Co-occurring items)
        idx = self.asin_to_idx[asin]
        users_who_bought = self.pos_by_item[idx]
        
        if not users_who_bought:
            print(f"⚠️ No user interactions found for {asin}")
            return None
            
        co_occur_counts = Counter()
        for u_idx in users_who_bought:
            user_items = self.pos_by_user[u_idx]
            for i_idx in user_items:
                if i_idx != idx:
                    co_occur_counts[self.idx_to_asin[i_idx]] += 1
        
        if not co_occur_counts:
            print(f"⚠️ No co-occurring items found for {asin}")
            return None
            
        # Top K most co-occurring items
        ground_truth = [item for item, count in co_occur_counts.most_common(top_k)]
        
        # 3. Calculate Precision
        # How many recommended items are in the ground truth set?
        # Note: We can define ground truth as the set of ALL co-occurring items, 
        # or just the Top K co-occurring. Using Top K is a stricter "Hit Ratio" style metric.
        # Let's use intersection with Top K Ground Truth.
        
        hits = set(rec_asins) & set(ground_truth)
        precision = len(hits) / top_k
        
        return {
            "asin": asin,
            "precision": precision,
            "recommendations": recs,
            "ground_truth_top_k": ground_truth,
            "co_occurrence_counts": {k: co_occur_counts[k] for k in ground_truth}
        }

def main():
    parser = argparse.ArgumentParser(description="BPR Item2Item Recommendation Trainer & Demo")
    parser.add_argument("--user_sequences_path", type=str, required=True, help="Path to user sequences jsonl")
    parser.add_argument("--output_dir", type=str, default="data", help="Output directory for embeddings")
    parser.add_argument("--dims", type=int, default=64, help="Embedding dimensions")
    parser.add_argument("--epochs", type=int, default=100, help="Training epochs")
    parser.add_argument("--demo_asin", type=str, help="ASIN to run demo/eval on after training")
    
    args = parser.parse_args()
    
    # Initialize and Load
    model = BPRItem2Item(dims=args.dims, epochs=args.epochs)
    model.load_data(args.user_sequences_path)
    
    # Train
    model.train()
    
    # Save
    model.save_embeddings(args.output_dir)
    
    # Demo / Evaluation
    demo_asins = []
    if args.demo_asin:
        demo_asins.append(args.demo_asin)
    else:
        # Pick a popular item if none provided
        popular_item_idx = max(model.pos_by_item.keys(), key=lambda k: len(model.pos_by_item[k]))
        demo_asins.append(model.idx_to_asin[popular_item_idx])
        print(f"ℹ️ No demo ASIN provided. Selected popular item: {demo_asins[0]}")

    for asin in demo_asins:
        print(f"\n📊 Evaluating Precision for ASIN: {asin}")
        result = model.evaluate_precision_for_asin(asin, top_k=100)
        
        if result:
            print(f"  Precision@10: {result['precision']:.2%}")
            print("\n  Top 10 Recommendations (BPR):")
            for i, (item, score) in enumerate(result['recommendations'], 1):
                is_hit = "�? if item in result['ground_truth_top_k'] else "  "
                print(f"    {i}. {item} (Score: {score:.4f}) {is_hit}")
                
            print("\n  Top 10 Ground Truth (Co-occurrences):")
            for i, item in enumerate(result['ground_truth_top_k'], 1):
                count = result['co_occurrence_counts'][item]
                print(f"    {i}. {item} (Count: {count})")

if __name__ == "__main__":
    main()

