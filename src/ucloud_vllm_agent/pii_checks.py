"""Deterministic PII inference and authentication checks using synthetic text."""
import json
import os
import secrets
from urllib.request import Request, build_opener
from urllib.error import HTTPError
from concurrent.futures import ThreadPoolExecutor

from .checks import NoRedirects
from .config import validate_base_url


def check_pii_endpoint(base_url, model, token=None):
    base_url = validate_base_url(base_url)
    token = token or os.environ['VLLM_API_KEY']
    checks = []
    text = "Hi, I'm Daniel Whitfield. Email daniels@meridiancap.com or call 415-555-0123."
    def request(route, payload=None, key=token):
        headers = {'Content-Type': 'application/json'}
        if key is not None: headers['Authorization'] = 'Bearer ' + key
        body = json.dumps(payload).encode() if payload is not None else None
        with build_opener(NoRedirects()).open(Request(base_url + route, data=body, headers=headers), timeout=120) as r:
            return json.loads(r.read(8_000_000))
    body = {'model': model, 'sequences': [text]}
    def listing():
        assert model in [m['id'] for m in request('/models')['data']]
    def masking():
        response = request('/pii', body); assert response['model'] == model
        result = response['results'][0]
        assert isinstance(result['sensitivity'], (int, float)) and 0 <= result['sensitivity'] <= 1
        assert result['token_count'] > 0
        assert any(s['pii_type'] == 'private_email' and 'daniels@meridiancap.com' in s['text'] for s in result['spans'])
        assert 'daniels@meridiancap.com' not in result['masked_text']
        assert all(text[s['start']:s['end']] == s['text'] for s in result['spans'])
    def scoring():
        r = request('/scoring', body)
        assert r['model'] == model and len(r['pruning_scores'][0]) == len(r['token_ids'][0]) > 0
        assert all(len(row) == 37 for row in r['pruning_scores'][0])
        assert len(r['ranking_scores'][0]) == 1
    def reject(route, key):
        try: request(route, body if route != '/models' else None, key)
        except HTTPError as e:
            status = e.code; e.close(); assert status in (401, 403); return
        raise AssertionError('Invalid credential accepted')
    def concurrent():
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: masking(), range(4)))
    cases = [('expected_model', listing), ('pii_masking_and_offsets', masking), ('raw_scoring_alignment', scoring),
             ('concurrent_pii_inference', concurrent)]
    for route in ('/models', '/scoring', '/pii'):
        cases += [(route[1:] + '_rejects_missing_key', lambda r=route: reject(r, None)),
                  (route[1:] + '_rejects_invalid_key', lambda r=route: reject(r, 'invalid-' + secrets.token_hex(32)))]
    for name, function in cases:
        try: function(); checks.append({'name': name, 'passed': True})
        except Exception as e: checks.append({'name': name, 'passed': False, 'reason': type(e).__name__})
    return {'base_url': base_url, 'model': model, 'passed': all(c['passed'] for c in checks), 'checks': checks,
            'note': 'Synthetic PII smoke test; detection quality requires evaluation on target data. No streaming task.'}
