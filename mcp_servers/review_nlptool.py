#!/usr/bin/env python3
"""
Extract sentiments and summaries from item reviews using lightweight NLP tools.

Dependencies: textblob (no model download needed)
"""
import json
import argparse
from collections import Counter
from pathlib import Path
from textblob import TextBlob


def load_reviews(item_meta_path: str) -> list[dict]:
    """Load reviews from item_meta.jsonl."""
    items_with_reviews = []
    
    with open(item_meta_path, 'r', encoding='utf-8') as f:
        for line in f:
            item = json.loads(line.strip())
            reviews = item.get('reviews', [])
            
            if reviews:
                items_with_reviews.append({
                    'asin': item.get('asin'),
                    'title': item.get('title'),
                    'reviews': reviews
                })
    return items_with_reviews


def _flatten_reviews(raw_reviews: list) -> list[str]:
    """Flatten reviews: [["review1"], ["review2"]] -> ["review1", "review2"]."""
    flat = []
    for review in raw_reviews:
        if isinstance(review, list):
            flat.append(" ".join(review))
        else:
            flat.append(review)
    return flat


def _polarity_to_label(polarity: float) -> str:
    """Convert TextBlob polarity (-1~1) to sentiment label."""
    if polarity > 0.1:
        return 'Positive'
    elif polarity < -0.1:
        return 'Negative'
    return 'Neutral'


def extract_sentiments(items_with_reviews: list[dict], **kwargs) -> list[dict]:
    """Extract overall sentiment for each review using TextBlob."""
    results = []
    
    for item in items_with_reviews:
        asin = item['asin']
        title = item['title']
        flat_reviews = _flatten_reviews(item['reviews'])
        
        if not flat_reviews:
            continue
        
        review_sentiments = []
        for idx, review_text in enumerate(flat_reviews):
            blob = TextBlob(review_text)
            polarity = blob.sentiment.polarity
            overall = _polarity_to_label(polarity)
            confidence = abs(polarity)
            
            review_sentiments.append({
                'review_index': idx,
                'sentiment': overall,
                'confidence': round(confidence, 4)
            })
        
        results.append({
            'asin': asin,
            'title': title,
            'review_sentiments': review_sentiments
        })
    
    return results


def extract_key_opinions(items_with_reviews: list[dict], **kwargs) -> list[dict]:
    """Extract key opinions using TextBlob noun phrase extraction + sentiment.
    
    Uses noun phrases as aspect proxies and sentence-level sentiment.
    """
    results = []
    
    for item in items_with_reviews:
        asin = item['asin']
        title = item['title']
        flat_reviews = _flatten_reviews(item['reviews'])
        
        if not flat_reviews:
            continue
        
        all_opinions = []
        aspect_stats = {}
        
        for review_text in flat_reviews:
            blob = TextBlob(review_text)
            noun_phrases = blob.noun_phrases
            
            for sentence in blob.sentences:
                sent_polarity = sentence.sentiment.polarity
                sent_label = _polarity_to_label(sent_polarity)
                sent_text = str(sentence).lower()
                
                sentence_nps = [np for np in noun_phrases if np in sent_text]
                if not sentence_nps:
                    words = [w for w, tag in sentence.tags if tag.startswith('NN')]
                    sentence_nps = words[:3] if words else []
                
                for np in sentence_nps:
                    aspect = np.strip()
                    if len(aspect) < 2:
                        continue
                    
                    all_opinions.append({
                        'aspect': aspect,
                        'opinion': str(sentence)[:80],
                        'sentiment': sent_label,
                        'confidence': round(abs(sent_polarity), 4)
                    })
                    
                    if aspect not in aspect_stats:
                        aspect_stats[aspect] = {'positive': 0, 'negative': 0, 'neutral': 0, 'opinions': []}
                    
                    aspect_stats[aspect][sent_label.lower()] += 1
                    aspect_stats[aspect]['opinions'].append(str(sentence)[:80])
        
        key_aspects = []
        for aspect, stats in sorted(
            aspect_stats.items(),
            key=lambda x: x[1]['positive'] + x[1]['negative'] + x[1]['neutral'],
            reverse=True
        ):
            total = stats['positive'] + stats['negative'] + stats['neutral']
            opinion_counts = Counter(stats['opinions'])
            top_opinions = [op for op, _ in opinion_counts.most_common(3)]
            
            key_aspects.append({
                'aspect': aspect,
                'total_mentions': total,
                'positive': stats['positive'],
                'negative': stats['negative'],
                'neutral': stats['neutral'],
                'top_opinions': top_opinions
            })
        
        results.append({
            'asin': asin,
            'title': title,
            'key_aspects': key_aspects[:20],
            'total_opinions': len(all_opinions)
        })
    
    return results


def _extractive_summarize(text: str, num_sentences: int = 2) -> str:
    """Simple extractive summarization: pick top sentences by keyword density."""
    blob = TextBlob(text)
    sentences = [str(s).strip() for s in blob.sentences if len(str(s).strip()) > 10]
    if not sentences:
        return text[:200]
    if len(sentences) <= num_sentences:
        return " ".join(sentences)
    
    # Score each sentence by noun phrase density
    word_freq = Counter(blob.words.lower())
    scored = []
    for s in sentences:
        s_blob = TextBlob(s)
        score = sum(word_freq.get(w.lower(), 0) for w in s_blob.words)
        score /= max(len(s_blob.words), 1)
        scored.append((score, s))
    scored.sort(reverse=True)
    return " ".join(s for _, s in scored[:num_sentences])


def extract_review_summaries(items_with_reviews: list[dict], **kwargs) -> list[dict]:
    """Extract review summary using extractive summarization (no model download needed).
    
    Stage 1: Pick the most representative sentence from each review.
    Stage 2: Combine top sentences across all reviews into a final summary.
    """
    results = []
    
    for item in items_with_reviews:
        asin = item['asin']
        title = item['title']
        flat_reviews = _flatten_reviews(item['reviews'])
        
        if not flat_reviews:
            continue
        
        # Stage 1: extract one key sentence per review
        individual_summaries = []
        for review in flat_reviews:
            if len(review.strip()) < 10:
                continue
            summary = _extractive_summarize(review, num_sentences=1)
            if summary:
                individual_summaries.append(summary)
        
        if not individual_summaries:
            results.append({
                'asin': asin,
                'title': title,
                'review_summary': "",
                'individual_summaries': [],
                'num_reviews_used': 0
            })
            continue
        
        # Stage 2: combine all individual summaries, then extract top sentences
        combined = " ".join(individual_summaries)
        final_summary_text = _extractive_summarize(combined, num_sentences=3)
        
        results.append({
            'asin': asin,
            'title': title,
            'review_summary': final_summary_text,
            'individual_summaries': individual_summaries,
            'num_reviews_used': len(flat_reviews)
        })
    
    return results


def main():
    parser = argparse.ArgumentParser(description='Extract aspects from item reviews')
    parser.add_argument(
        '--input', '-i',
        default='data/amazon-electronics/processed/item_meta.jsonl',
        help='Path to item_meta.jsonl'
    )
    parser.add_argument(
        '--output', '-o',
        default='../data/amazon-electronics/processed/item_aspects.jsonl',
        help='Output path for extracted aspects'
    )
    parser.add_argument(
        '--task', '-t',
        default='sentiment',
        choices=['sentiment', 'summary', 'opinions', 'both'],
        help='Task to perform: sentiment analysis, summarization, key opinions extraction, or both (sentiment+summary)'
    )
    args = parser.parse_args()
    
    print(f"Loading reviews from {args.input}...")
    items_with_reviews = load_reviews(args.input)
    print(f"Found {len(items_with_reviews)} items with reviews")
    
    if not items_with_reviews:
        return
    
    # Sentiment analysis
    sentiment_results = {}
    if args.task == 'sentiment':
        print("Extracting sentiments using TextBlob...")
        results = extract_sentiments(items_with_reviews)
        sentiment_results = {r['asin']: r for r in results}
    
    # Summarization
    summary_results = {}
    if args.task == 'summary':
        print("Extracting summaries using extractive summarization...")
        summaries = extract_review_summaries(items_with_reviews)
        summary_results = {r['asin']: r for r in summaries}
    
    # Key opinions extraction
    opinions_results = {}
    if args.task == 'opinions':
        print("Extracting key opinions using TextBlob...")
        opinions = extract_key_opinions(items_with_reviews)
        opinions_results = {r['asin']: r for r in opinions}
    
    # Save results - each task writes to a distinct file
    base_output = Path(args.output)
    base_output.parent.mkdir(parents=True, exist_ok=True)
    stem = base_output.stem
    suffix = base_output.suffix or '.jsonl'

    def _write_items(filename: str, data_items: list[dict]):
        path = base_output.parent / filename
        with open(path, 'w', encoding='utf-8') as f:
            for item_out in data_items:
                f.write(json.dumps(item_out, ensure_ascii=False) + '\n')
        print(f"Saved {len(data_items)} items to {path}")

    if args.task == 'sentiment':
        out_items = []
        for item in items_with_reviews:
            asin = item['asin']
            if asin not in sentiment_results:
                continue
            sentiments = sentiment_results[asin]['review_sentiments']
            pos = sum(1 for r in sentiments if r['sentiment'] == 'Positive')
            neg = sum(1 for r in sentiments if r['sentiment'] == 'Negative')
            out_items.append({
                'asin': asin,
                'title': item['title'],
                'key_aspects': [f"positive:{pos}", f"negative:{neg}", f"total:{len(sentiments)}"]
            })
        _write_items(f"{stem}_sentiment{suffix}", out_items)

    elif args.task == 'summary':
        out_items = []
        for item in items_with_reviews:
            asin = item['asin']
            if asin not in summary_results:
                continue
            out_items.append({
                'asin': asin,
                'title': item['title'],
                'key_aspects': [summary_results[asin]['review_summary']]
            })
        _write_items(f"{stem}_summary{suffix}", out_items)

    elif args.task == 'opinions':
        out_items = []
        for item in items_with_reviews:
            asin = item['asin']
            if asin not in opinions_results:
                continue
            key_aspects = [asp['aspect'] for asp in opinions_results[asin]['key_aspects'][:3]]
            out_items.append({
                'asin': asin,
                'title': item['title'],
                'key_aspects': key_aspects
            })
        _write_items(f"{stem}_opinions{suffix}", out_items)
    

  

if __name__ == '__main__':
    main()
