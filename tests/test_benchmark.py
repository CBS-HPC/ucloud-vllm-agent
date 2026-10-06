import importlib.util
import json
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize('task', ['chat', 'pii'])
def test_benchmark_checks_task_and_never_records_synthetic_text_or_key(tmp_path, monkeypatch, task):
    spec = importlib.util.spec_from_file_location('benchmark_endpoint', Path(__file__).parents[1] / 'scripts/benchmark_endpoint.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'load_env', lambda: None)
    monkeypatch.setenv('VLLM_API_KEY', 'private-test-key')
    profile = {'request': {'name': 'test', 'task': task, 'concurrency': 2, 'public_base_url': 'https://test.example/v1'}}
    monkeypatch.setattr(module, 'load_json', lambda p: profile)
    monkeypatch.setattr(module, 'validate_profile', lambda p: p)
    text = 'Hej Mikkel. Syntetisk testmail.'
    source = tmp_path / 'input.txt'; source.write_text(text, encoding='utf-8')
    output = tmp_path / 'report.json'
    monkeypatch.setattr(sys, 'argv', ['benchmark', '--profile', 'unused', '--requests', '4',
                                    '--input-file', str(source), '--output', str(output)])
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit):
            if task == 'pii':
                result = {'model': 'test', 'results': [{'token_count': 10, 'masked_text': text,
                          'spans': [{'start': 4, 'end': 10, 'text': 'Mikkel'}]}]}
            else:
                result = {'model': 'test', 'choices': [{'message': {'content': text}, 'finish_reason': 'stop'}],
                          'usage': {'prompt_tokens': 10, 'completion_tokens': 6}}
            return json.dumps(result).encode()
    class Opener:
        def open(self, request, timeout):
            assert request.full_url.endswith('/pii' if task == 'pii' else '/chat/completions')
            body = json.loads(request.data)
            assert (body['sequences'][0] if task == 'pii' else body['messages'][0]['content']) == text
            return Response()
    monkeypatch.setattr(module, 'build_opener', lambda *args: Opener())
    assert module.main() == 0
    report = json.loads(output.read_text())
    assert report['passed'] and report['workers'] == 2 and report['task'] == task
    assert all(row['input_tokens'] == 10 for row in report['results'])
    assert 'private-test-key' not in output.read_text() and text not in output.read_text()
