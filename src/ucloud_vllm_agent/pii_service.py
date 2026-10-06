"""Authenticated PII-Tracer adapter and owned pooling-process supervisor.

Implements the published 37-label BIOES contract; runs no model repository code.
"""

import json
import math
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

CATEGORIES = ('private_person', 'private_email', 'private_phone', 'private_address',
              'private_url', 'private_date', 'account_number', 'secret', 'other_pii')


def tag(label):
    return 'O' if label == 0 else 'BIES'[(label - 1) % 4]


def category(label):
    return None if label == 0 else (label - 1) // 4


def allowed(previous, current):
    if tag(previous) in ('O', 'E', 'S'):
        return tag(current) in ('O', 'B', 'S')
    return category(previous) == category(current) and tag(current) in ('I', 'E')


def decode(rows, offsets, text):
    if not rows or len(rows) != len(offsets) or any(len(row) != 38 for row in rows):
        raise ValueError('Invalid token-logit alignment')
    if any(not math.isfinite(x) for row in rows for x in row):
        raise ValueError('Nonfinite model logits')
    predecessors = [[i for i in range(37) if allowed(i, j)] for j in range(37)]
    scores = [rows[0][j] if tag(j) in ('O', 'B', 'S') else -math.inf for j in range(37)]
    back = []
    for row in rows[1:]:
        best = [max(predecessors[j], key=lambda i: scores[i]) for j in range(37)]
        back.append(best)
        scores = [scores[best[j]] + row[j] for j in range(37)]
    last = max((i for i in range(37) if tag(i) in ('O', 'E', 'S')), key=lambda i: scores[i])
    path = [last]
    for best in reversed(back):
        last = best[last]
        path.append(last)
    path.reverse()
    spans = []
    start = None
    for index, label in enumerate(path):
        if tag(label) in ('B', 'S'):
            start = index
        if tag(label) in ('E', 'S') and start is not None:
            begin, end = offsets[start][0], offsets[index][1]
            if begin < end:
                probabilities = []
                for n in range(start, index + 1):
                    logits = rows[n][:37]; peak = max(logits)
                    probabilities.append(math.exp(logits[path[n]] - peak) / sum(math.exp(x - peak) for x in logits))
                spans.append({'start': begin, 'end': end, 'pii_type': CATEGORIES[category(label)],
                              'text': text[begin:end], 'score': sum(probabilities) / len(probabilities)})
            start = None
    masked = text
    for span in reversed(spans):
        masked = masked[:span['start']] + '[' + span['pii_type'].upper() + ']' + masked[span['end']:]
    sensitivity = sum(row[37] for row in rows) / len(rows)
    probability = 1 / (1 + math.exp(-max(-700, min(700, sensitivity))))
    return {'spans': spans, 'masked_text': masked, 'sensitivity': probability, 'token_count': len(rows)}


def cached_snapshot(config):
    from huggingface_hub import hf_hub_download
    # Request the required cached file, not a complete repository snapshot.
    # Runtime preparation deliberately excludes repository source code.
    return Path(hf_hub_download(config['model'], 'tokenizer.json', revision=config['revision'],
                cache_dir=str(Path(config['cache_dir']) / 'hub'), local_files_only=True)).parent


def api(root, config):
    import asyncio
    import secrets
    import httpx
    import uvicorn
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import JSONResponse
    from tokenizers import Tokenizer

    key = os.environ['VLLM_API_KEY']
    snapshot = cached_snapshot(config)
    tokenizer = Tokenizer.from_file(str(snapshot / 'tokenizer.json'))
    tokenizer.no_truncation()
    constraints = json.loads((snapshot / 'viterbi.json').read_text())
    expected = [[allowed(i, j) for j in range(37)] for i in range(37)]
    if (constraints['transition_mask'] != expected or constraints['b_bias'] != [0.0]
            or constraints['e_bias'] != [0.0] or constraints['sensitivity_logit_index'] != 37):
        raise ValueError('Pinned decoder constraints differ from the reviewed layout')
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    limit = asyncio.Semaphore(config['concurrency'])
    backend = 'http://127.0.0.1:' + str(config['port'] + 1)

    @app.middleware('http')
    async def authenticate(request, call_next):
        if not secrets.compare_digest(request.headers.get('authorization', ''), 'Bearer ' + key):
            return JSONResponse({'detail': 'Unauthorized'}, status_code=401)
        if int(request.headers.get('content-length', '0')) > 131072:
            return JSONResponse({'detail': 'Request too large'}, status_code=413)
        return await call_next(request)

    @app.get('/v1/models')
    async def models():
        try:
            async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
                response = await client.get(backend + '/v1/models', headers={'Authorization': 'Bearer ' + key})
        except httpx.HTTPError:
            raise HTTPException(503, 'Model is not ready') from None
        if response.status_code != 200:
            raise HTTPException(503, 'Model is not ready')
        return response.json()

    async def score(request):
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(422, 'Expected a JSON object')
        sequences = body.get('sequences')
        if (body.get('model') != config['name'] or not isinstance(sequences, list)
                or not 1 <= len(sequences) <= config['concurrency']
                or any(not isinstance(s, str) or not s.strip() for s in sequences)):
            raise HTTPException(422, 'Specify the served model and a nonempty bounded text batch')
        encodings = [tokenizer.encode(s, add_special_tokens=False) for s in sequences]
        if any(not e.ids or len(e.ids) > config['context_length'] for e in encodings):
            raise HTTPException(422, 'Input exceeds the token limit; split it explicitly')
        async with limit, httpx.AsyncClient(timeout=120, follow_redirects=False) as client:
            response = await client.post(backend + '/pooling', headers={'Authorization': 'Bearer ' + key},
                json={'model': config['name'], 'task': 'token_classify', 'input': [e.ids for e in encodings]})
        if response.status_code != 200:
            raise HTTPException(502, 'Pooling inference failed')
        items = sorted(response.json()['data'], key=lambda x: x['index'])
        if len(items) != len(encodings) or [i['index'] for i in items] != list(range(len(items))):
            raise HTTPException(502, 'Invalid pooling batch alignment')
        rows = [i['data'] for i in items]
        if any(len(r) != len(e.ids) or any(len(t) != 38 for t in r) for r, e in zip(rows, encodings)):
            raise HTTPException(502, 'Invalid pooling token alignment')
        return sequences, encodings, rows

    @app.post('/v1/scoring')
    async def scoring(request: Request):
        _, encodings, rows = await score(request)
        return {'model': config['name'], 'pruning_scores': [[r[:37] for r in rs] for rs in rows],
                'ranking_scores': [[sum(r[37] for r in rs) / len(rs)] for rs in rows],
                'token_ids': [e.ids for e in encodings], 'token_offsets': [e.offsets for e in encodings]}

    @app.post('/v1/pii')
    async def pii(request: Request):
        texts, encodings, rows = await score(request)
        return {'model': config['name'], 'results': [decode(r, e.offsets, t) for r, e, t in zip(rows, encodings, texts)]}

    uvicorn.run(app, host='127.0.0.1', port=config['port'], access_log=False)


def supervise(root, config):
    python = str(Path(config['venv_dir']) / 'bin/python')
    command = [str(Path(config['venv_dir']) / 'bin/vllm'), 'serve', config['model'],
               '--revision', config['revision'], '--served-model-name', config['name'],
               '--host', '127.0.0.1', '--port', str(config['port'] + 1),
               '--runner', 'pooling', '--convert', 'classify',
               '--pooler-config', '{"use_activation":false,"task":"token_classify"}',
               '--dtype', config['dtype'], '--max-model-len', str(config['context_length']),
               '--max-num-seqs', str(config['concurrency']), '--enforce-eager',
               '--gpu-memory-utilization', str(config['gpu_memory_utilization'])]
    stopping = [False]
    def stop(*_): stopping[0] = True
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP): signal.signal(sig, stop)
    with (root / 'vllm.log').open('a') as backend_log, (root / 'adapter.log').open('a') as adapter_log:
        children = []
        try:
            children.append(subprocess.Popen(command, stdout=backend_log, stderr=backend_log))
            children.append(subprocess.Popen([python, str(root / 'pii_service.py'), 'api'], stdout=adapter_log, stderr=adapter_log))
            while not stopping[0] and all(p.poll() is None for p in children): time.sleep(0.5)
        finally:
            for p in children:
                if p.poll() is None: p.terminate()
            for p in children:
                try: p.wait(timeout=30)
                except subprocess.TimeoutExpired: p.kill(); p.wait(timeout=10)


if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    config = json.loads((root / 'runtime.json').read_text())
    if sys.argv[1] == 'supervise': supervise(root, config)
    elif sys.argv[1] == 'api': api(root, config)
    else: raise SystemExit(1)
