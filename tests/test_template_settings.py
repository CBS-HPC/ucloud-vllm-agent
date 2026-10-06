from __future__ import annotations

import json
from pathlib import Path

import pytest

from ucloud_vllm_agent.config import validate_request
from ucloud_vllm_agent.planner import prepare
from ucloud_vllm_agent.remote import load_runtime_secrets


def test_work_folder_drives_template_paths_and_hostname_normalization(monkeypatch):
    monkeypatch.setenv("UCLOUD_WORK_FOLDER", "/work/vllm")
    monkeypatch.setenv("UCLOUD_PUBLIC_BASE_URL", "inference.example.org")
    for key in ("UCLOUD_HF_ENV_FILE", "UCLOUD_VLLM_SECRET_FILE", "UCLOUD_NGINX_CONFIG"):
        monkeypatch.delenv(key, raising=False)
    request = validate_request({"name": "example", "model": "test/model"})
    assert request["hf_env_file"] == "/work/vllm/.env"
    assert request["nginx_config"] == "/work/vllm/nginx.conf"
    assert request["secret_file"] == "/work/vllm/.env"
    assert request["public_base_url"] == "https://inference.example.org/v1"


def test_template_hf_file_is_read_only_and_cannot_supply_serving_key(tmp_path, monkeypatch):
    monkeypatch.delenv("VLLM_API_KEY", raising=False)
    hf = tmp_path / ".env"
    key = tmp_path / "vllm.env"
    hf.write_text("HF_TOKEN=hf-test\nVLLM_API_KEY=wrong-source\nOTHER=ignore\n")
    key.write_text("VLLM_API_KEY=serving-test\nHF_TOKEN=wrong-source\n")
    before = hf.read_bytes()
    config = {"hf_env_file": str(hf), "secret_file": str(key), "cache_dir": "/work/vllm/cache"}
    env = load_runtime_secrets(config)
    assert env["HF_TOKEN"] == "hf-test"
    assert env["VLLM_API_KEY"] == "serving-test"
    assert hf.read_bytes() == before


def test_blank_serving_key_blocks_runtime_even_with_hf_access(tmp_path, monkeypatch):
    monkeypatch.delenv("VLLM_API_KEY", raising=False)
    hf = tmp_path / ".env"
    key = tmp_path / "vllm.env"
    hf.write_text("HF_TOKEN=hf-test\n")
    key.write_text("VLLM_API_KEY=\n")
    with pytest.raises(ValueError, match="VLLM_API_KEY"):
        load_runtime_secrets({"hf_env_file": str(hf), "secret_file": str(key), "cache_dir": "/work/vllm/cache"})


def test_plan_records_paths_but_not_local_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("VLLM_API_KEY", "private-serving-token")
    monkeypatch.setenv("HF_TOKEN", "private-hf-token")
    request = {"name": "example", "model": "test/model"}
    metadata = {"model": "test/model", "revision": "a" * 40, "parameters": 1_000_000_000,
                "config": {"model_type": "llama", "num_hidden_layers": 24,
                           "num_attention_heads": 16, "hidden_size": 2048}}
    machine = {"name": "single", "gpu_count": 1, "vram_gib_per_gpu": 40,
               "ram_gib": 100, "mig": False, "verified": True}
    root = prepare(request, metadata, [machine], tmp_path)
    for path in root.glob("*.json"):
        content = path.read_text()
        assert "private-serving-token" not in content
        assert "private-hf-token" not in content
    runtime = json.loads((root / "runtime.json").read_text())
    assert runtime["hf_env_file"].endswith("/.env")
    assert runtime["nginx_config"].endswith("/nginx.conf")


def test_shared_workspace_env_supplies_both_keys_without_modification(tmp_path, monkeypatch):
    monkeypatch.setenv('VLLM_API_KEY', 'ignored-inherited-key')
    monkeypatch.setenv('HF_TOKEN', 'ignored-inherited-hf')
    source = tmp_path / '.env'
    source.write_text('HF_TOKEN=workspace-hf\nVLLM_API_KEY=workspace-serving\nOTHER=ignored\n')
    before = source.read_bytes()
    env = load_runtime_secrets({'hf_env_file': str(source), 'secret_file': str(source), 'cache_dir': '/cache'})
    assert env['HF_TOKEN'] == 'workspace-hf'
    assert env['VLLM_API_KEY'] == 'workspace-serving'
    assert source.read_bytes() == before
