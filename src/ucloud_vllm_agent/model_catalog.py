"""Offline model history and candidates; entries never authorize deployment."""
import json
from importlib.resources import files


def list_models(use_case: str | None = None, status: str | None = None) -> dict:
    catalog = json.loads(files('ucloud_vllm_agent').joinpath('data/model_catalog.json').read_text(encoding='utf-8'))
    catalog['models'] = [entry for entry in catalog['models']
                         if (use_case is None or entry['use_case'] == use_case)
                         and (status is None or entry['status'] == status)]
    return catalog
