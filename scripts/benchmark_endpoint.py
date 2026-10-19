"""Concurrent synthetic chat/PII benchmark; records metrics, never request text."""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, build_opener

from ucloud_vllm_agent.checks import NoRedirects
from ucloud_vllm_agent.config import load_env, load_json, positive_int
from ucloud_vllm_agent.hosting import validate_profile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--requests', type=int, default=8)
    parser.add_argument('--input-file', type=Path, help='Synthetic workload text; contents are never recorded in the report')
    parser.add_argument('--input-repeats', type=int, default=1, help='Repeat synthetic fixture for longer inputs')
    parser.add_argument('--max-tokens', type=int, default=64, help='Chat output limit')
    parser.add_argument('--output', type=Path, default=Path('artifacts/concurrent-check.json'))
    args = parser.parse_args()
    load_env()
    profile = validate_profile(load_json(args.profile))
    count = positive_int(args.requests, 'requests')
    request = profile['request']
    workers = request['concurrency']
    repeats = positive_int(args.input_repeats, 'input-repeats')
    max_tokens = positive_int(args.max_tokens, 'max-tokens')
    fixture = ('Hej Mikkel,\nKontakt Anna Lund via anna.lund@example.org eller +45 99 88 77 66.\n'
               'Mødet er på Eksempelvej 123, 1234 Eksempelby. Venlig hilsen Anna.\n')
    text = (args.input_file.read_text(encoding='utf-8') if args.input_file else fixture) * repeats
    token = os.environ.get('VLLM_API_KEY')
    if not token:
        raise ValueError('VLLM_API_KEY is required')

    def infer(index):
        started = time.monotonic()
        try:
            if request['task'] == 'pii':
                body = {'model': request['name'], 'sequences': [text]}
                endpoint = '/pii'
            else:
                body = {'model': request['name'], 'messages': [{'role': 'user', 'content':
                        text if args.input_file else f'Explain GPU memory in one sentence. Request {index}.'}],
                        'max_tokens': max_tokens, 'temperature': 0, 'stream': False}
                endpoint = '/chat/completions'
            req = Request(request['public_base_url'] + endpoint, data=json.dumps(body).encode(),
                          headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
            with build_opener(NoRedirects()).open(req, timeout=120) as response:
                result = json.loads(response.read(1_000_000))
            if request['task'] == 'pii':
                item = result['results'][0]
                passed = (result['model'] == request['name'] and len(result['results']) == 1
                          and isinstance(item['masked_text'], str) and item['token_count'] > 0
                          and all(text[s['start']:s['end']] == s['text'] for s in item['spans']))
                tokens = item['token_count']
            else:
                choice = result['choices'][0]
                passed = (result['model'] == request['name'] and bool(choice['message']['content'])
                          and choice['finish_reason'] in ('stop', 'length'))
                tokens = result.get('usage', {}).get('prompt_tokens', 0)
            return {'passed': passed, 'seconds': round(time.monotonic() - started, 3),
                    'input_tokens': tokens,
                    'completion_tokens': result.get('usage', {}).get('completion_tokens', 0)}
        except Exception as error:
            return {'passed': False, 'reason': type(error).__name__}

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(infer, range(count)))
    elapsed = time.monotonic() - started
    # A coarse clock can report zero for a fast/mock workload (Windows 3.11).
    # Missing timing evidence must not become fabricated throughput or a crash.
    def rate(total, digits):
        return round(total / elapsed, digits) if elapsed > 0 else None
    latencies = [r['seconds'] for r in results if r['passed']]
    report = {'passed': all(r['passed'] for r in results), 'model': request['name'], 'task': request['task'],
              'workers': workers, 'requests': count, 'wall_seconds': round(elapsed, 3),
              'median_request_seconds': statistics.median(latencies) if latencies else None,
              'p95_request_seconds': sorted(latencies)[math.ceil(len(latencies) * 0.95) - 1] if latencies else None,
              'successful_requests': sum(r['passed'] for r in results),
              'timing_valid': elapsed > 0,
              'requests_per_second': rate(sum(r['passed'] for r in results), 3),
              'input_tokens_per_second': rate(sum(r.get('input_tokens', 0) for r in results), 2),
              'completion_tokens_per_second': rate(sum(r.get('completion_tokens', 0) for r in results), 2),
              'results': results, 'note': 'Synthetic HTTP workload; latency includes network and proxy. Model quality is not measured.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
