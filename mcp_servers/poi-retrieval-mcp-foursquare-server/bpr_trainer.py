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
        self.business_id_to_idx = {}
        self.idx_to_business_id = {}
        self.pos_by_user = {} # user_idx -> set of business_id_idxs
        self.pos_by_item = defaultdict(set) # business_id_idx -> set of user_idxs (inverse index for eval)
        
        # Model parameters
        self.U = None # User embeddings
        self.V = None # Business ID embeddings
        
    def load_data(self, user_sequences_path):
        """Load user sequences and build indices"""
        print(f"📖 Loading data from {user_sequences_path}...")
        users = set()
        business_ids = set()
        
        # First pass: collect unique users and business_ids
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
                            business_id = x.get('business_id')
                        else:
                            business_id = x
                        if business_id:
                            business_ids.add(business_id)
                except:
                    continue
                    
        # Create mappings
        self.user_to_idx = {u: i for i, u in enumerate(sorted(list(users)))}
        self.business_id_to_idx = {a: i for i, a in enumerate(sorted(list(business_ids)))}
        self.idx_to_business_id = {i: a for a, i in self.business_id_to_idx.items()}
        
        print(f"�?Found {len(users)} users and {len(business_ids)} business_ids")
        
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
                            business_id = x.get('business_id')
                        else:
                            business_id = x
                        if business_id and business_id in self.business_id_to_idx:
                            i_idx = self.business_id_to_idx[business_id]
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
        num_business_ids = len(self.business_id_to_idx)
        
        # Initialize embeddings
        self.U = np.random.normal(0, 0.1, (num_users, self.dims)).astype(np.float32)
        self.V = np.random.normal(0, 0.1, (num_business_ids, self.dims)).astype(np.float32)
        
        user_list = list(self.pos_by_user.keys())
        total_samples = sum(len(pos_items) for pos_items in self.pos_by_user.values())
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
                j = random.randint(0, num_business_ids - 1)
                while j in self.pos_by_user[u]:
                    j = random.randint(0, num_business_ids - 1)
                    
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
        
        emb_path = out / "bpr_business_id_embeddings.npy"
        map_path = out / "bpr_business_id_map.json"
        
        np.save(emb_path, self.V)
        with open(map_path, 'w', encoding='utf-8') as f:
            json.dump({"business_id_to_idx": self.business_id_to_idx}, f)
            
        print(f"💾 Saved embeddings to {emb_path}")

    def get_similar_items(self, business_id, top_k=10):
        """Find similar items using trained embeddings (Cosine Similarity)"""
        if business_id not in self.business_id_to_idx:
            return []
            
        idx = self.business_id_to_idx[business_id]
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
            results.append((self.idx_to_business_id[i], float(sims[i])))
            if len(results) >= top_k:
                break
                
        return results

    def evaluate_precision_for_business_id(self, business_id, top_k=10):
        """
        Calculate precision for a specific business_id.
        Precision is based on 'co-occurrence' in user histories.
        Ground Truth = Top K items that co-occur most frequently with this Business ID.
        """
        if business_id not in self.business_id_to_idx:
            print(f"⚠️ Business ID {business_id} not found in training data.")
            return None
            
        # 1. Get Model Recommendations
        recs = self.get_similar_items(business_id, top_k=top_k)
        rec_business_ids = [r[0] for r in recs]
        
        # 2. Get Ground Truth (Co-occurring items)
        idx = self.business_id_to_idx[business_id]
        users_who_bought = self.pos_by_item[idx]
        
        if not users_who_bought:
            print(f"⚠️ No user interactions found for {business_id}")
            return None
            
        co_occur_counts = Counter()
        for u_idx in users_who_bought:
            user_items = self.pos_by_user[u_idx]
            for i_idx in user_items:
                if i_idx != idx:
                    co_occur_counts[self.idx_to_business_id[i_idx]] += 1
        
        if not co_occur_counts:
            print(f"⚠️ No co-occurring items found for {business_id}")
            return None
            
        # Top K most co-occurring Business IDs
        ground_truth = [business_id for business_id, count in co_occur_counts.most_common(top_k)]
        
        # 3. Calculate Precision
        # How many recommended Business IDs are in the ground truth set?
        # Note: We can define ground truth as the set of ALL co-occurring Business IDs, 
        # or just the Top K co-occurring. Using Top K is a stricter "Hit Ratio" style metric.
        # Let's use intersection with Top K Ground Truth.
        
        hits = set(rec_business_ids) & set(ground_truth)
        precision = len(hits) / top_k
        
        return {
            "business_id": business_id,
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
    parser.add_argument("--demo_business_id", type=str, help="Business ID to run demo/eval on after training")
    
    args = parser.parse_args()
    
    # Initialize and Load
    model = BPRItem2Item(dims=args.dims, epochs=args.epochs)
    model.load_data(args.user_sequences_path)
    
    # Train
    model.train()
    
    # Save
    model.save_embeddings(args.output_dir)
    
    # Demo / Evaluation
    demo_business_ids = []
    if args.demo_business_id:
        demo_business_ids.append(args.demo_business_id)
    else:
        # Pick a popular item if none provided
        popular_item_idx = max(model.pos_by_item.keys(), key=lambda k: len(model.pos_by_item[k]))
        demo_business_ids.append(model.idx_to_business_id[popular_item_idx])
        print(f"ℹ️ No demo Business ID provided. Selected popular item: {demo_business_ids[0]}")

    for business_id in demo_business_ids:
        print(f"\n📊 Evaluating Precision for Business ID: {business_id}")
        result = model.evaluate_precision_for_business_id(business_id, top_k=100)
        
        if result:
            print(f"  Precision@10: {result['precision']:.2%}")
            print("\n  Top 10 Recommendations (BPR):")
            for i, (business_id, score) in enumerate(result['recommendations'], 1):
                is_hit = "�? if business_id in result['ground_truth_top_k'] else "  "
                print(f"    {i}. {business_id} (Score: {score:.4f}) {is_hit}")
                
            print("\n  Top 10 Ground Truth (Co-occurrences):")
            for i, business_id in enumerate(result['ground_truth_top_k'], 1):
                count = result['co_occurrence_counts'][business_id]
                print(f"    {i}. {business_id} (Count: {count})")

if __name__ == "__main__":
    main()

