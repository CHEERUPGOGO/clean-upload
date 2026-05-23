#!/usr/bin/env python3
"""
Generate item_sentiment.jsonl, item_opinion.jsonl, item_summary.jsonl
from item_meta.jsonl (which contains reviews, average_rating, rating_number).

No LLM needed â€?uses rule-based extraction from existing review text.
Processes item_meta.jsonl in a single streaming pass to minimize memory.

Usage:
    # Amazon: meta and NLP data both in same dir
    python generate_nlp_data.py --meta_dir data/amazon-electronics/processed --data_dir data/amazon-electronics/processed

    # Yelp: meta in yelp/processed, NLP output in yelp/
    python generate_nlp_data.py --meta_dir data/yelp/processed --data_dir data/yelp --id_field business_id --name_field name --reviews_field text
"""
import json
import argparse
import re
import os
import sys
import shutil
from pathlib import Path
from collections import Counter


def load_jsonl(path):
    items = []
    if not os.path.exists(path):
        return items
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    items.append(json.loads(line))
                except Exception:
                    continue
    return items


def load_jsonl_ids(path, id_field):
    """Load only IDs from a jsonl file for fast set construction."""
    ids = set()
    if not os.path.exists(path):
        return ids
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    item = json.loads(line)
                    ids.add(item.get(id_field, item.get('asin', '')))
                except Exception:
                    continue
    return ids


def write_jsonl(path, items):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')


def append_jsonl(path, items):
    """Append items to an existing jsonl file."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'a', encoding='utf-8') as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')


# ---------- sentiment ----------
POSITIVE_WORDS = {
    'great', 'excellent', 'amazing', 'love', 'perfect', 'awesome', 'fantastic',
    'wonderful', 'best', 'good', 'nice', 'happy', 'pleased', 'recommend',
    'reliable', 'easy', 'comfortable', 'solid', 'well', 'superb', 'outstanding',
    'impressive', 'satisfied', 'brilliant', 'flawless', 'quality', 'durable',
    'fast', 'smooth', 'beautiful', 'sturdy', 'handy', 'convenient', 'works',
}
NEGATIVE_WORDS = {
    'bad', 'terrible', 'awful', 'hate', 'worst', 'poor', 'disappointed',
    'horrible', 'broken', 'defective', 'waste', 'useless', 'junk', 'cheap',
    'slow', 'annoying', 'flimsy', 'difficult', 'problem', 'fail', 'error',
    'return', 'refund', 'damage', 'faulty', 'unreliable', 'frustrating',
    'mediocre', 'overpriced', 'noisy', 'uncomfortable', 'fragile',
}


def flatten_reviews(reviews, max_reviews=50):
    """Extract flat list of text strings from reviews field.

    Handles multiple formats:
    - List[str]: each element is a review text
    - List[List[str]]: each element is [text] or [text, ...]
    - List[dict]: each element has 'text' key
    - str: treated as a single review

    max_reviews: only keep the first N review texts (avoids extreme
    slowdown on items with hundreds/thousands of reviews).
    """
    if isinstance(reviews, str):
        return [reviews]
    texts = []
    for review in reviews:
        if len(texts) >= max_reviews:
            break
        if isinstance(review, str):
            texts.append(review)
        elif isinstance(review, list):
            for item in review:
                if len(texts) >= max_reviews:
                    break
                if isinstance(item, str):
                    texts.append(item)
        elif isinstance(review, dict):
            t = review.get('text', '')
            if t:
                texts.append(t)
    return texts


def compute_sentiment(texts):
    """Compute positive/negative/total counts from review texts."""
    positive = 0
    negative = 0
    total = 0
    for text in texts:
        if not text or len(text) < 5:
            continue
        total += 1
        words = set(re.findall(r'[a-z]+', text.lower()))
        pos_hits = len(words & POSITIVE_WORDS)
        neg_hits = len(words & NEGATIVE_WORDS)
        if pos_hits > neg_hits:
            positive += 1
        elif neg_hits > pos_hits:
            negative += 1
    return positive, negative, total


# ---------- opinion ----------
ASPECT_PATTERNS = [
    (r'\b(sound quality|audio quality|sound)\b', 'sound quality'),
    (r'\b(battery life|battery)\b', 'battery life'),
    (r'\b(durability|durable|build quality|sturdy)\b', 'durability'),
    (r'\b(compatibility|compatible)\b', 'compatibility'),
    (r'\b(ease of use|easy to use|easy setup|user friendly)\b', 'ease of use'),
    (r'\b(design|look|appearance)\b', 'design'),
    (r'\b(value|price|worth|bang for buck)\b', 'value'),
    (r'\b(performance|speed|fast)\b', 'performance'),
    (r'\b(reliability|reliable)\b', 'reliability'),
    (r'\b(connectivity|connection|wireless|bluetooth)\b', 'connectivity'),
    (r'\b(signal strength|signal|reception)\b', 'signal strength'),
    (r'\b(comfort|comfortable|ergonomic)\b', 'comfort'),
    (r'\b(installation|install|setup)\b', 'installation'),
    (r'\b(quality|build)\b', 'quality'),
    (r'\b(software|firmware|driver)\b', 'software'),
    (r'\b(screen|display|resolution)\b', 'screen'),
    (r'\b(storage|capacity|memory)\b', 'storage'),
    (r'\b(port|usb|hdmi|adapter)\b', 'ports'),
]


def extract_aspects(texts, max_aspects=8):
    """Extract key product aspects mentioned across review texts."""
    aspect_counts = Counter()
    for text in texts:
        text_lower = text.lower()
        for pattern, aspect_name in ASPECT_PATTERNS:
            if re.search(pattern, text_lower):
                aspect_counts[aspect_name] += 1
    return [aspect for aspect, _ in aspect_counts.most_common(max_aspects)]


def get_fallback_aspects(item):
    """Fallback: derive aspects from category/brand."""
    cat = item.get('category', item.get('main_category', ''))
    brand = item.get('brand', item.get('store', ''))
    fallback = []
    if brand and isinstance(brand, str):
        fallback.append(brand.lower())
    if cat:
        if isinstance(cat, list):
            fallback.extend(str(c).lower() for c in cat[-2:])
        elif isinstance(cat, str):
            parts = [p.strip() for p in re.split(r'[&>,]', cat) if p.strip()]
            fallback.extend(p.lower() for p in parts[-2:])
    return fallback[:5]


# ---------- summary ----------
def extract_summary_snippets(texts, max_reviews=5, max_chars=500):
    """Generate short summary snippets from the first few reviews."""
    snippets = []
    total_len = 0
    for text in texts[:max_reviews]:
        if not text:
            continue
        sentence = re.split(r'[.!?]', text)[0].strip()
        if len(sentence) > 120:
            sentence = sentence[:120] + '...'
        if sentence:
            snippets.append(sentence)
            total_len += len(sentence)
            if total_len > max_chars:
                break
    return snippets


def process_item(item, id_field, name_field, reviews_field):
    """Process a single item: returns (sentiment_entry, opinion_entry, summary_entry) or Nones."""
    item_id = item.get(id_field) or item.get('asin', '')
    title = item.get(name_field, item.get('title', item.get('name', '')))
    reviews = item.get(reviews_field, [])
    if not reviews:
        return None, None, None

    texts = flatten_reviews(reviews)
    if not texts:
        return None, None, None

    # Sentiment
    positive, negative, total = compute_sentiment(texts)
    sentiment_entry = None
    if total > 0:
        sentiment_entry = {
            id_field: item_id,
            'title': title,
            'key_aspects': [f'positive:{positive}', f'negative:{negative}', f'total:{total}'],
        }

    # Opinion
    aspects = extract_aspects(texts)
    if not aspects:
        aspects = get_fallback_aspects(item)
    opinion_entry = None
    if aspects:
        opinion_entry = {
            id_field: item_id,
            'title': title,
            'key_aspects': aspects,
        }

    # Summary
    snippets = extract_summary_snippets(texts)
    summary_entry = None
    if snippets:
        summary_entry = {
            id_field: item_id,
            'title': title,
            'key_aspects': snippets,
        }

    return sentiment_entry, opinion_entry, summary_entry


def main():
    parser = argparse.ArgumentParser(description='Generate NLP data from item metadata')
    parser.add_argument('--meta_dir', type=str, required=True,
                        help='Directory containing item_meta.jsonl (source of review text)')
    parser.add_argument('--data_dir', type=str, default=None,
                        help='Directory for output NLP files (default: same as meta_dir)')
    parser.add_argument('--id_field', type=str, default='asin',
                        help='ID field name (asin for Amazon, business_id for Yelp)')
    parser.add_argument('--name_field', type=str, default='title',
                        help='Name field name (title for Amazon, name for Yelp)')
    parser.add_argument('--reviews_field', type=str, default='reviews',
                        help='Field containing reviews (reviews for Amazon, text for Yelp)')
    args = parser.parse_args()

    meta_dir = Path(args.meta_dir)
    data_dir = Path(args.data_dir) if args.data_dir else meta_dir
    meta_path = meta_dir / 'item_meta.jsonl'

    # Load existing NLP IDs (only IDs, not full data, to save memory)
    print('Loading existing NLP data IDs...')
    existing_sentiment_ids = load_jsonl_ids(data_dir / 'item_sentiment.jsonl', args.id_field)
    existing_opinion_ids = load_jsonl_ids(data_dir / 'item_opinion.jsonl', args.id_field)
    existing_summary_ids = load_jsonl_ids(data_dir / 'item_summary.jsonl', args.id_field)
    print(f'  Existing sentiment: {len(existing_sentiment_ids)}, opinion: {len(existing_opinion_ids)}, summary: {len(existing_summary_ids)}')

    # Backup existing files
    for fname in ['item_sentiment.jsonl', 'item_opinion.jsonl', 'item_summary.jsonl']:
        p = data_dir / fname
        if p.exists():
            backup = p.with_suffix('.jsonl.bak')
            if not backup.exists():
                try:
                    shutil.copy2(p, backup)
                    print(f'  Backed up {fname} â†?{backup.name}')
                except PermissionError:
                    print(f'  Warning: cannot backup {fname} (permission denied), skipping backup')

    # Streaming pass: read meta line-by-line, process, accumulate new entries
    new_sentiment = []
    new_opinion = []
    new_summary = []
    total_items = 0

    print('Processing item_meta.jsonl (streaming)...')
    with open(meta_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue
            total_items += 1

            item_id = item.get(args.id_field) or item.get('asin', '')

            # Only process items not already covered
            need_sentiment = item_id not in existing_sentiment_ids
            need_opinion = item_id not in existing_opinion_ids
            need_summary = item_id not in existing_summary_ids

            if not (need_sentiment or need_opinion or need_summary):
                continue

            s_entry, o_entry, s2_entry = process_item(
                item, args.id_field, args.name_field, args.reviews_field
            )

            if need_sentiment and s_entry:
                new_sentiment.append(s_entry)
            if need_opinion and o_entry:
                new_opinion.append(o_entry)
            if need_summary and s2_entry:
                new_summary.append(s2_entry)

            if line_num % 2000 == 0:
                print(f'  Processed {line_num} lines, new entries: sentiment={len(new_sentiment)} opinion={len(new_opinion)} summary={len(new_summary)}', flush=True)

    print(f'  Total items in meta: {total_items}')
    print(f'  New sentiment: {len(new_sentiment)}')
    print(f'  New opinion: {len(new_opinion)}')
    print(f'  New summary: {len(new_summary)}')

    # Append new entries to existing files
    print('Writing new entries...')
    output_files = {
        'sentiment': data_dir / 'item_sentiment.jsonl',
        'opinion': data_dir / 'item_opinion.jsonl',
        'summary': data_dir / 'item_summary.jsonl',
    }
    new_data = {
        'sentiment': new_sentiment,
        'opinion': new_opinion,
        'summary': new_summary,
    }
    for key, path in output_files.items():
        data = new_data[key]
        if not data:
            print(f'  {path.name}: no new entries, skipping')
            continue
        try:
            append_jsonl(str(path), data)
            print(f'  {path.name}: appended {len(data)} entries')
        except PermissionError:
            # Try writing to a new file next to it
            alt_path = data_dir / f'{path.stem}_new.jsonl'
            print(f'  Warning: cannot write to {path.name} (permission denied)')
            print(f'  Writing to {alt_path.name} instead')
            write_jsonl(str(alt_path), data)

    # Final counts
    final_s = len(existing_sentiment_ids) + len(new_sentiment)
    final_o = len(existing_opinion_ids) + len(new_opinion)
    final_su = len(existing_summary_ids) + len(new_summary)
    print(f'\nDone! Final counts:')
    print(f'  item_sentiment.jsonl: {final_s}')
    print(f'  item_opinion.jsonl: {final_o}')
    print(f'  item_summary.jsonl: {final_su}')


if __name__ == '__main__':
    main()
