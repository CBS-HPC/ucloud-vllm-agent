from copy import deepcopy
from pathlib import Path

import pytest

from ucloud_vllm_agent.config import load_json
from ucloud_vllm_agent.hosting import prepare_profile, validate_profile, hosting_job_specification


@pytest.fixture
def profile():
    return load_json(Path(__file__).parents[1] / "config/hosting.qwen-small.json")


@pytest.fixture
def template():
    return {"application": {"name": "nginx", "version": "1.31.2"},
            "product": {"id": "old", "category": "gpu", "provider": "ucloud"},
            "parameters": {"configFile": {"type": "file", "path": "/drive/vllm/nginx.conf"},
                           "custom": {"type": "text", "value": "preserve"}},
            "resources": [{"type": "ingress", "id": "operator-link"},
                          {"type": "file", "path": "/drive/vllm"}], "sshEnabled": True}


def test_hosting_spec_preserves_resources_and_overrides_only_hosting_settings(profile, template):
    pytest.importorskip("ucloud_workflow")
    before = deepcopy(template)
    profile["hours"] = 3
    spec = hosting_job_specification(template, profile)
    assert template == before
    assert spec["resources"] == template["resources"]
    assert spec["parameters"]["configFile"] == template["parameters"]["configFile"]
    assert spec["parameters"]["custom"] == template["parameters"]["custom"]
    assert spec["parameters"]["initScript"]["path"] == "/drive/vllm/init_vllm.sh"
    assert spec["product"] == profile["machine"]["product"]
    assert spec["sshEnabled"] is False
    assert spec["timeAllocation"]["hours"] == 3


@pytest.mark.parametrize("invalid", [None, "raw-path", {"type": "file", "path": "/drive/../other/nginx.conf"}])
def test_template_with_unverified_config_mapping_is_rejected(profile, template, invalid):
    pytest.importorskip("ucloud_workflow")
    template["parameters"]["configFile"] = invalid
    with pytest.raises(ValueError, match="nginx.conf"):
        hosting_job_specification(template, profile)


def test_model_change_is_bound_to_supplied_machine_and_runtime(profile, tmp_path):
    profile["request"].update(name="different-model", model="test/model", revision="a" * 40)
    metadata = {"model": "test/model", "revision": "a" * 40, "parameters": 1_000_000_000,
                "config": {"model_type": "llama", "num_hidden_layers": 16,
                           "num_attention_heads": 16, "num_key_value_heads": 4,
                           "hidden_size": 2048, "max_position_embeddings": 8192}}
    root = prepare_profile(profile, metadata, tmp_path)
    assert b"\r" not in (root / "init_vllm.sh").read_bytes()
    runtime = load_json(root / "runtime.json")
    assert runtime["model"] == "test/model"
    assert runtime["revision"] == "a" * 40
    assert runtime["venv_dir"] == "/work/vllm/.venv"
    assert load_json(root / "job-settings.json")["product"] == profile["machine"]["product"]
    profile["machine"]["vram_gib_per_gpu"] = 1
    before = list(tmp_path.rglob("runtime.json"))
    with pytest.raises(ValueError, match="does not fit"):
        prepare_profile(profile, metadata, tmp_path)
    assert list(tmp_path.rglob("runtime.json")) == before


def test_profile_rejects_secrets_and_unsupported_environment(profile):
    with pytest.raises(ValueError, match="schema or fields"):
        validate_profile({**profile, "api_key": "must-use-env"})
    profile["venv_dir"] = "/some/other/environment"
    with pytest.raises(ValueError, match="prepared"):
        validate_profile(profile)
