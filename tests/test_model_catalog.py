from pathlib import Path

from ucloud_vllm_agent.config import load_json
from ucloud_vllm_agent.model_catalog import list_models


def test_validated_catalog_entries_match_reproducible_profiles_and_evidence():
    root=Path(__file__).parents[1]
    entries=list_models(status='validated')['models']
    assert {e['use_case'] for e in entries}=={'chat','anonymisation'}
    for entry in entries:
        profile=load_json(root/entry['profile'])
        assert profile['request']['model']==entry['model']
        assert profile['request']['revision']==entry['revision']
        assert profile['request'].get('task','chat')==entry['serving_task']
        assert profile['request']['context_length']==entry['tested_context_tokens']
        assert profile['request']['concurrency'] in entry['tested_concurrency']
        assert (root/entry['notebook']).is_file()
        assert all((root/path).is_file() for path in entry['evidence'])


def test_classification_candidate_does_not_imply_implemented_hosting_support():
    candidates=list_models(use_case='classification',status='candidate')['models']
    assert len(candidates)==1
    candidate=candidates[0]
    assert candidate['model']=='syvai/claes-preview'
    assert candidate['serving_task'] is None and candidate['profile'] is None
    assert candidate['tested_machine'] is None and not candidate['evidence']
    assert candidate['preview_metadata']['max_len']==1024
