import pytest

from ucloud_vllm_agent.capacity import estimate_capacity
from ucloud_vllm_agent.config import validate_request
from ucloud_vllm_agent.catalog import map_products, project_categories
from ucloud_vllm_agent.remote import cache_namespace, profiling_evidence


def inputs():
    return (validate_request({'name': 'model', 'model': 'test/model'}),
            {'model': 'test/model', 'parameters': 7_000_000_000,
             'config': {'model_type': 'llama', 'num_hidden_layers': 32,
                        'num_attention_heads': 32, 'num_key_value_heads': 8,
                        'hidden_size': 4096, 'max_position_embeddings': 131072}},
            [{'name': 'one-gpu', 'gpu_count': 1, 'vram_gib_per_gpu': 24,
              'ram_gib': 64, 'mig': False, 'verified': True}])


def test_quantized_checkpoint_bytes_and_explicit_kv_dtype_change_fit():
    request, model, machines = inputs()
    dense = estimate_capacity(request, model, machines)
    model['config']['quantization_config'] = {'quant_method': 'awq', 'bits': 4}
    unsupported = estimate_capacity(request, model, machines)
    assert unsupported['recommendation'] is None
    model['checkpoint_bytes'] = 4 * 1024 ** 3
    quantized = estimate_capacity(request, model, machines)
    assert quantized['weight_gib'] == 4
    assert quantized['kv_cache_gib_total'] == dense['kv_cache_gib_total']
    fp8 = estimate_capacity({**request, 'kv_cache_dtype': 'fp8'}, model, machines)
    assert fp8['kv_cache_gib_total'] == pytest.approx(quantized['kv_cache_gib_total'] / 2, abs=.001)
    busy = estimate_capacity({**request, 'context_length': 131072, 'concurrency': 8}, model, machines)
    assert busy['recommendation'] is None


def test_unknown_hybrid_and_moe_layouts_do_not_get_dense_recommendations():
    request, model, machines = inputs()
    model['config']['layer_types'] = ['full_attention', 'mamba']
    assert estimate_capacity(request, model, machines)['recommendation'] is None
    model['config'].pop('layer_types')
    model['config']['num_local_experts'] = 8
    assert estimate_capacity(request, model, machines)['recommendation'] is None


def test_live_products_require_project_wallet_and_do_not_pool_mig():
    category = {'name': 'gpu-nvidia-b200', 'provider': 'ucloud', 'productType': 'COMPUTE'}
    products = [{'name': 'gpu-nvidia-b200-1-mig.1g', 'category': category, 'gpu': 1, 'memoryInGigs': 36},
                {'name': 'gpu-nvidia-b200-2-mig.1g', 'category': category, 'gpu': 2, 'memoryInGigs': 72}]
    assert map_products(products, set()) == []
    wallets = [{'paysFor': category, 'maxUsable': 100}]
    machines = map_products(products, project_categories(wallets))
    assert machines[0]['product']['id'] == products[0]['name']
    assert machines[0]['vram_gib_per_gpu'] == machines[1]['vram_gib_per_gpu'] == 20.5
    request, metadata, _ = inputs()
    result = estimate_capacity(request, metadata, machines)
    assert not result['candidates'][1]['fits_estimate']
    assert 'multi_slice_mig_not_assumed_tensor_parallel' in result['candidates'][1]['reasons']


def test_cache_compatibility_is_order_independent_and_separates_driver_gpu_runtime():
    evidence = {'driver': '580', 'gpu': 'B200 MIG', 'vllm': '0.31.0'}
    assert cache_namespace(evidence) == cache_namespace(dict(reversed(list(evidence.items()))))
    for key in evidence:
        assert cache_namespace(evidence) != cache_namespace({**evidence, key: 'different'})


def test_numeric_runtime_evidence_does_not_expose_log_text(tmp_path):
    (tmp_path / 'vllm.log').write_text('private-token\nModel loading took 2.98 GiB\n'
                                    'Available KV cache memory: 12.00 GiB\nGPU KV cache size: 400,000 tokens\n'
                                    'Maximum concurrency for 4,096 tokens per request: 97.65x\n')
    evidence = profiling_evidence(tmp_path)
    assert evidence == {'model_weights_gib': 2.98, 'available_kv_gib': 12.,
                        'gpu_kv_tokens': 400000., 'max_full_context_concurrency': 97.65}
    assert 'private-token' not in str(evidence)


def test_opt_in_released_availability_keeps_capacity_and_selection_separate():
    pytest.importorskip("ucloud_workflow")
    from types import SimpleNamespace
    from ucloud_vllm_agent.catalog import sync_catalog
    category = {'name': 'gpu-nvidia-b200', 'provider': 'ucloud', 'productType': 'COMPUTE'}
    product = {'name': 'gpu-nvidia-b200-1-mig.1g', 'category': category, 'gpu': 1, 'memoryInGigs': 36}
    reference = {'id': product['name'], 'category': category['name'], 'provider': 'ucloud'}
    class Client:
        probes = 0
        def request(self, method, endpoint, **kwargs):
            assert method == 'GET'
            items = [{'paysFor': category, 'maxUsable': 100}] if 'Wallets' in endpoint else [product]
            return SimpleNamespace(json=lambda: {'items': items})
        def retrieve_compute_products(self):
            self.probes += 1
            return {'productsByProvider': {'ucloud': [{'product': product,
                    'support': {'product': reference, 'queueStatus': 'FULL'}}]}}
    client = Client()
    baseline = sync_catalog(client)
    assert client.probes == 0 and 'availability' not in baseline
    current = sync_catalog(client, live=True)
    assert client.probes == 1 and current['machines'] == baseline['machines']
    assert current['availability']['machines'][0]['queue_status'] == 'FULL'
    assert current['availability']['checked_at']
