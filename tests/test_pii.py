import math
import pytest

from ucloud_vllm_agent.pii_service import decode
from ucloud_vllm_agent.capacity import estimate_capacity
from ucloud_vllm_agent.config import validate_request


def test_bioes_decoding_preserves_offsets_masks_and_sensitivity():
    text = 'Eva eve@example.org'
    rows = [[-10.] * 38 for _ in range(2)]
    rows[0][4] = 10.; rows[1][8] = 10.
    rows[0][37] = rows[1][37] = 2.
    result = decode(rows, [(0, 3), (4, len(text))], text)
    assert result['masked_text'] == '[PRIVATE_PERSON] [PRIVATE_EMAIL]'
    assert [s['text'] for s in result['spans']] == ['Eva', 'eve@example.org']
    assert all(text[s['start']:s['end']] == s['text'] for s in result['spans'])
    assert result['sensitivity'] == pytest.approx(1 / (1 + math.exp(-2)))


def test_decoder_rejects_nonfinite_and_misaligned_logits():
    with pytest.raises(ValueError): decode([[0.] * 37], [(0, 1)], 'x')
    with pytest.raises(ValueError): decode([[math.nan] * 38], [(0, 1)], 'x')


def test_viterbi_does_not_use_illegal_start_or_end_tags():
    row = [-10.] * 38
    row[6] = 100.  # Illegal I-email at start/end.
    row[5] = 99.   # Illegal unclosed B-email at end.
    row[8] = 10.
    assert decode([row], [(0, 5)], 'email')['masked_text'] == '[PRIVATE_EMAIL]'


def test_bidirectional_encoder_has_activation_allowance_without_decoder_kv():
    request = validate_request({'name': 'pii', 'model': 'perplexity-ai/PII-Tracer-vLLM', 'task': 'pii', 'concurrency': 2})
    metadata = {'model': request['model'], 'parameters': 596088870,
                'config': {'model_type': 'qwen3', 'architectures': ['Qwen3ForTokenClassification'],
                           'num_labels': 38, 'is_causal': False, 'num_hidden_layers': 28,
                           'num_attention_heads': 16, 'num_key_value_heads': 8, 'hidden_size': 1024, 'head_dim': 128}}
    machines = [{'name': 'slice', 'gpu_count': 1, 'vram_gib_per_gpu': 20.5, 'ram_gib': 30, 'mig': True}]
    result = estimate_capacity(request, metadata, machines)
    assert result['kv_cache_gib_total'] == 0
    assert result['encoder_activation_gib_allowance'] > 0
    assert result['recommendation']
    assert estimate_capacity({**request, 'task': 'chat'}, metadata, machines)['recommendation'] is None
    assert estimate_capacity({**request, 'context_length': 4097}, metadata, machines)['recommendation'] is None


def test_cached_snapshot_requires_only_the_prepared_tokenizer_file(monkeypatch, tmp_path):
    import sys
    from types import SimpleNamespace
    from ucloud_vllm_agent.pii_service import cached_snapshot
    observed = []
    def download(*args, **kwargs):
        observed.append((args, kwargs))
        return str(tmp_path / 'snapshot' / 'tokenizer.json')
    monkeypatch.setitem(sys.modules, 'huggingface_hub', SimpleNamespace(hf_hub_download=download))
    config = {'model': 'perplexity-ai/PII-Tracer-vLLM', 'revision': 'a'*40, 'cache_dir': '/work/vllm/cache/huggingface'}
    assert cached_snapshot(config) == tmp_path / 'snapshot'
    assert observed[0][0] == (config['model'], 'tokenizer.json')
    assert observed[0][1]['local_files_only'] is True
    assert observed[0][1]['revision'] == config['revision']
