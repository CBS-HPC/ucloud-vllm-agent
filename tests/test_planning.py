from __future__ import annotations

import json
from pathlib import Path

import pytest

from ucloud_vllm_agent.capacity import GIB, estimate_capacity
from ucloud_vllm_agent.cli import main
from ucloud_vllm_agent.config import validate_request
from ucloud_vllm_agent.planner import prepare


@pytest.fixture
def workload():
    return validate_request({"name": "test-model", "model": "test/model", "context_length": 4096, "concurrency": 4})


@pytest.fixture
def metadata():
    return {"model": "test/model", "revision": "a" * 40, "parameters": 7_000_000_000,
            "config": {"model_type": "llama", "num_hidden_layers": 32,
                       "num_attention_heads": 32, "num_key_value_heads": 8,
                       "hidden_size": 4096, "max_position_embeddings": 32768}}


def machine(count=1, vram=40, **extra):
    return {"name": f"{count}-gpu", "gpu_count": count, "vram_gib_per_gpu": vram,
            "ram_gib": 256, "mig": False, "verified": True, **extra}


def test_concurrency_changes_machine_choice(workload, metadata):
    smaller = machine(vram=24)
    larger = machine(vram=80)
    baseline = estimate_capacity({**workload, "concurrency": 1}, metadata, [smaller, larger])
    busy = estimate_capacity({**workload, "concurrency": 64}, metadata, [smaller, larger])
    assert baseline["recommendation"]["vram_gib_per_gpu"] == 24
    assert busy["recommendation"]["vram_gib_per_gpu"] == 80
    assert busy["kv_cache_gib_total"] == baseline["kv_cache_gib_total"] * 64


def test_kv_heads_replicate_when_tp_exceeds_head_count(workload, metadata):
    metadata["config"]["num_key_value_heads"] = 1
    result = estimate_capacity(workload, metadata, [machine(count=8, vram=80)])
    expected = 7_000_000_000 * 2 / 8 * 1.1 / GIB + result["kv_cache_gib_total"] + 3
    assert result["candidates"][0]["required_gib_per_gpu"] == pytest.approx(expected, abs=0.001)


def test_mig_slices_are_not_combined(workload, metadata):
    result = estimate_capacity(workload, metadata, [machine(count=2, vram=24, mig=True)])
    assert result["recommendation"] is None
    assert "multi_slice_mig_not_assumed_tensor_parallel" in result["candidates"][0]["reasons"]


@pytest.mark.parametrize("change", [
    {"model_type": "deepseek_v3"}, {"quantization_config": {"quant_method": "awq"}},
    {"num_local_experts": 8}, {"vision_config": {"model_type": "clip"}},
])
def test_specialized_layout_needs_review(workload, metadata, change):
    metadata["config"].update(change)
    result = estimate_capacity(workload, metadata, [machine()])
    assert result["status"] == "needs_review"
    assert result["recommendation"] is None


def test_context_exceeding_model_is_blocked(workload, metadata):
    result = estimate_capacity({**workload, "context_length": 65536}, metadata, [machine()])
    assert "context_exceeds_model_config" in result["blockers"]


def test_prepare_keeps_revision_and_records_release_gate(tmp_path, monkeypatch, workload, metadata):
    monkeypatch.delenv("UCLOUD_TEMPLATE_JOB_ID", raising=False)
    root = prepare(workload, metadata, [machine()], tmp_path)
    plan = json.loads((root / "plan.json").read_text())
    runtime = json.loads((root / "runtime.json").read_text())
    assert plan["job_id"] is None
    assert "await_released_ucloud_gpu_submission_adapter" in plan["blockers"]
    assert runtime["revision"] == "a" * 40
    assert runtime["concurrency"] == workload["concurrency"]
    assert (root / "remote.py").exists()
    another = prepare(workload, metadata, [machine()], tmp_path)
    other_runtime = json.loads((another / "runtime.json").read_text())
    assert runtime["session"] != other_runtime["session"]


def test_metadata_mismatch_does_not_create_artifacts(tmp_path, workload, metadata):
    metadata["model"] = "different/model"
    with pytest.raises(ValueError, match="does not match"):
        prepare(workload, metadata, [machine()], tmp_path)
    assert not list(tmp_path.iterdir())


def test_prepare_rejects_wrong_pinned_revision(tmp_path, workload, metadata):
    with pytest.raises(ValueError, match="revision differs"):
        prepare({**workload, "revision": "b" * 40}, metadata, [machine()], tmp_path)


def test_release_gate_prevents_submission(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert main(["deploy"]) == 2
    assert "Deployment blocked" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())


def test_upstream_error_body_is_not_returned(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)

    def fail():
        raise RuntimeError("Upstream response containing private-credential")

    monkeypatch.setattr("ucloud_vllm_agent.cli.inspect_template", fail)
    assert main(["inspect-template"]) == 1
    output = capsys.readouterr()
    assert "private-credential" not in output.out + output.err
    assert "RuntimeError" in output.err


@pytest.mark.parametrize("field,value", [("concurrency", 0), ("context_length", True),
                                        ("gpu_memory_utilization", float("nan")),
                                        ("work_folder", "/work/../etc"), ("vllm_port", 70000)])
def test_invalid_requests_rejected(field, value):
    with pytest.raises(ValueError):
        validate_request({"name": "test", "model": "test/model", field: value})
