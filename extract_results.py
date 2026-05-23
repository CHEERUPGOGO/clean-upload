#!/usr/bin/env python3
"""
Extract and format key results from benchmark output.

This script extracts:
1. Model's planned tool calls
2. Model's executed tool calls  
3. Ground truth expected tool calls
4. Simple comparison metrics

Usage:
    python extract_results.py benchmark_results.json
    python extract_results.py benchmark_results.json --output simplified_results.json
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any


def extract_tool_call_info(execution_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract tool call information from execution results."""
    tool_calls = []
    
    for result in execution_results:
        tool_info = {
            'tool_name': result.get('tool_name', 'unknown'),
            'server': result.get('server_name', 'unknown'),
            'parameters': result.get('parameters', {}),
            'status': result.get('status', 'unknown'),
            'round': result.get('round', 0)
        }
        
        # Add result summary if available
        if result.get('status') == 'success':
            tool_info['success'] = True
            # Optionally include truncated result
            content = result.get('content', '')
            if content:
                tool_info['result_preview'] = str(content)[:200] + '...' if len(str(content)) > 200 else str(content)
        else:
            tool_info['success'] = False
            tool_info['error'] = result.get('error', 'Unknown error')
            
        tool_calls.append(tool_info)
    
    return tool_calls


def normalize_tool_call(tool_call: Dict[str, Any]) -> str:
    """Normalize a tool call to a comparable format."""
    if isinstance(tool_call, str):
        return tool_call
    
    # Handle different formats
    if 'tool' in tool_call:
        tool_str = tool_call['tool']
    elif 'tool_name' in tool_call:
        server = tool_call.get('server', tool_call.get('server_name', ''))
        tool_name = tool_call['tool_name']
        tool_str = f"{server}:{tool_name}" if server else tool_name
    else:
        tool_str = str(tool_call)
    
    return tool_str.lower().strip()


def compare_tool_calls(executed: List[Dict], expected: List[Dict]) -> Dict[str, Any]:
    """Compare executed tool calls with expected ones."""
    
    # Normalize both lists
    executed_normalized = set()
    for call in executed:
        if call.get('success', False):
            executed_normalized.add(normalize_tool_call(call))
    
    expected_normalized = set()
    for call in expected:
        expected_normalized.add(normalize_tool_call(call))
    
    # Calculate metrics
    correct = executed_normalized & expected_normalized
    missing = expected_normalized - executed_normalized
    extra = executed_normalized - expected_normalized
    
    precision = len(correct) / len(executed_normalized) if executed_normalized else 0
    recall = len(correct) / len(expected_normalized) if expected_normalized else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    
    return {
        'precision': round(precision, 3),
        'recall': round(recall, 3),
        'f1_score': round(f1, 3),
        'correct_tools': list(correct),
        'missing_tools': list(missing),
        'extra_tools': list(extra),
        'executed_count': len(executed_normalized),
        'expected_count': len(expected_normalized),
        'correct_count': len(correct)
    }


def extract_task_results(task_result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract simplified results for a single task."""
    
    task_id = task_result.get('task_id', 'unknown')
    model_name = task_result.get('model_name', 'unknown')
    
    # Extract executed tool calls
    execution_results = task_result.get('execution_results', [])
    executed_tools = extract_tool_call_info(execution_results)
    
    # Extract expected tool calls (ground truth)
    expected_tools = task_result.get('expected_tool_calls', [])
    
    # Compare
    comparison = compare_tool_calls(executed_tools, expected_tools)
    
    result = {
        'task_id': task_id,
        'model': model_name,
        'task_description': task_result.get('task_description', ''),
        'status': task_result.get('status', 'unknown'),
        'total_rounds': task_result.get('total_rounds', 0),
        'executed_tools': executed_tools,
        'expected_tools': expected_tools,
        'comparison': comparison,
        'execution_time': task_result.get('execution_time', 0),
        'token_usage': {
            'prompt_tokens': task_result.get('total_prompt_tokens', 0),
            'output_tokens': task_result.get('total_output_tokens', 0),
            'total_tokens': task_result.get('total_tokens', 0)
        }
    }
    
    return result


def extract_all_results(benchmark_results: Dict[str, Any]) -> Dict[str, Any]:
    """Extract all results from benchmark output."""
    
    extracted = {
        'summary': {
            'total_tasks': 0,
            'successful_tasks': 0,
            'failed_tasks': 0,
            'average_f1': 0,
            'average_precision': 0,
            'average_recall': 0
        },
        'tasks': []
    }
    
    # Handle different result formats
    if isinstance(benchmark_results, dict):
        # Check if it's a wrapped result
        if 'results' in benchmark_results:
            results = benchmark_results['results']
        elif 'tasks' in benchmark_results:
            results = benchmark_results['tasks']
        else:
            # Assume it's the results dict itself
            results = benchmark_results
    elif isinstance(benchmark_results, list):
        results = benchmark_results
    else:
        results = []
    
    # Process each task
    f1_scores = []
    precision_scores = []
    recall_scores = []
    
    for task_result in results:
        if isinstance(task_result, dict):
            extracted_task = extract_task_results(task_result)
            extracted['tasks'].append(extracted_task)
            
            extracted['summary']['total_tasks'] += 1
            if extracted_task['status'] == 'completed':
                extracted['summary']['successful_tasks'] += 1
            else:
                extracted['summary']['failed_tasks'] += 1
            
            # Collect metrics
            comp = extracted_task['comparison']
            f1_scores.append(comp['f1_score'])
            precision_scores.append(comp['precision'])
            recall_scores.append(comp['recall'])
    
    # Calculate averages
    if f1_scores:
        extracted['summary']['average_f1'] = round(sum(f1_scores) / len(f1_scores), 3)
        extracted['summary']['average_precision'] = round(sum(precision_scores) / len(precision_scores), 3)
        extracted['summary']['average_recall'] = round(sum(recall_scores) / len(recall_scores), 3)
    
    return extracted


def print_summary(results: Dict[str, Any]):
    """Print a human-readable summary."""
    summary = results['summary']
    
    print("\n" + "="*80)
    print("BENCHMARK RESULTS SUMMARY")
    print("="*80)
    print(f"Total Tasks: {summary['total_tasks']}")
    print(f"Successful: {summary['successful_tasks']}")
    print(f"Failed: {summary['failed_tasks']}")
    print(f"\nAverage Metrics:")
    print(f"  Precision: {summary['average_precision']:.3f}")
    print(f"  Recall: {summary['average_recall']:.3f}")
    print(f"  F1 Score: {summary['average_f1']:.3f}")
    print("="*80 + "\n")
    
    # Print per-task summary
    for i, task in enumerate(results['tasks'], 1):
        comp = task['comparison']
        print(f"Task {i}: {task['task_id']}")
        print(f"  Status: {task['status']}")
        print(f"  F1: {comp['f1_score']:.3f} | P: {comp['precision']:.3f} | R: {comp['recall']:.3f}")
        print(f"  Executed: {comp['executed_count']} | Expected: {comp['expected_count']} | Correct: {comp['correct_count']}")
        
        if comp['missing_tools']:
            print(f"  Missing: {', '.join(comp['missing_tools'])}")
        if comp['extra_tools']:
            print(f"  Extra: {', '.join(comp['extra_tools'])}")
        print()


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python extract_results.py <benchmark_results.json> [--output <output.json>]")
        sys.exit(1)
    
    input_file = Path(sys.argv[1])
    
    # Parse optional output file
    output_file = None
    if '--output' in sys.argv:
        output_idx = sys.argv.index('--output')
        if output_idx + 1 < len(sys.argv):
            output_file = Path(sys.argv[output_idx + 1])
    
    if not input_file.exists():
        print(f"Error: File not found: {input_file}")
        sys.exit(1)
    
    # Load results
    print(f"Loading results from {input_file}...")
    with open(input_file, 'r', encoding='utf-8') as f:
        benchmark_results = json.load(f)
    
    # Extract
    print("Extracting key information...")
    extracted = extract_all_results(benchmark_results)
    
    # Save if output file specified
    if output_file:
        print(f"Saving extracted results to {output_file}...")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(extracted, f, indent=2, ensure_ascii=False)
    
    # Print summary
    print_summary(extracted)


if __name__ == "__main__":
    main()
