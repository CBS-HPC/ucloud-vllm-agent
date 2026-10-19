from copy import deepcopy
import json

import pytest

from ucloud_vllm_agent.cli import main
from ucloud_vllm_agent import diagnostics


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for key in list(__import__('os').environ):
        if key.startswith(("UCLOUD_", "VLLM_", "HF_")):
            monkeypatch.delenv(key)
    for key in diagnostics.REQUIRED:
        monkeypatch.setenv(key, "synthetic-secret" if key.endswith(("TOKEN", "KEY")) else "test-id")
    monkeypatch.setenv("UCLOUD_PUBLIC_BASE_URL", "https://model.example/v1")
    key = tmp_path / "key"
    key.write_text("synthetic placeholder; never parsed")
    monkeypatch.setenv("UCLOUD_SSH_IDENTITY_FILE", str(key))
    monkeypatch.setattr(diagnostics, "integration_status", lambda: {"installed_ucloud_workflow": "0.1.6"})
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: "/tools/" + name)
    return tmp_path


def test_empty_doctor_fails_with_missing_cpu_template_and_no_network(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    for key in diagnostics.REQUIRED:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(diagnostics, "_online_preflight", lambda _: pytest.fail("Unexpected network"))
    assert main(["doctor"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert not result["configured"]["UCLOUD_PREPARATION_TEMPLATE_JOB_ID"]
    assert result["state"] == "blocked" and not result["ready_for_submission"]
    assert not result["job_submitted"]


def test_local_doctor_is_not_live_readiness(configured, monkeypatch, capsys):
    monkeypatch.setattr(diagnostics, "_online_preflight", lambda _: pytest.fail("Unexpected network"))
    assert main(["doctor"]) == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["state"] == "configured"
    assert not result["ready_for_submission"] and not result["runtime_verified"]
    assert "synthetic-secret" not in captured.out + captured.err


def test_missing_key_or_invalid_url_blocks_preflight(configured, monkeypatch):
    monkeypatch.setenv("UCLOUD_SSH_IDENTITY_FILE", str(configured / "missing-key"))
    monkeypatch.setenv("UCLOUD_PUBLIC_BASE_URL", "https://name:synthetic-secret@example.org")
    monkeypatch.setattr(diagnostics, "_online_preflight", lambda _: pytest.fail("Unexpected network"))
    report = diagnostics.diagnose(online=True, profile=configured / "profile.json")
    assert not report["passed"]
    assert report["api_preflight"] == "blocked_by_local_requirements"
    assert "synthetic-secret" not in json.dumps(report)


def test_online_requires_profile_and_sanitizes_upstream_failure(configured, monkeypatch):
    assert not diagnostics.diagnose(online=True)["passed"]
    def fail(_):
        raise RuntimeError("credential-bearing upstream body")
    monkeypatch.setattr(diagnostics, "_online_preflight", fail)
    report = diagnostics.diagnose(online=True, profile=configured / "profile.json")
    assert not report["ready_for_submission"] and "credential-bearing" not in json.dumps(report)


def test_online_success_remains_distinct_from_runtime_and_endpoint(configured, monkeypatch):
    calls = []
    monkeypatch.setattr(diagnostics, "_online_preflight", lambda path: calls.append(path))
    report = diagnostics.diagnose(online=True, profile=configured / "profile.json")
    assert calls == [configured / "profile.json"]
    assert report["ready_for_submission"] and not report["runtime_verified"] and not report["endpoint_verified"]


@pytest.mark.parametrize("foreign,expired,occupied", [(False, False, False), (True, False, False),
                                                     (False, True, False), (False, False, True)])
def test_actual_api_preflight_is_read_only_and_checks_target(configured, monkeypatch, foreign, expired, occupied):
    pytest.importorskip("ucloud_workflow")
    from pathlib import Path
    from types import SimpleNamespace
    from ucloud_vllm_agent.config import load_json
    profile = load_json(Path(__file__).parents[1] / "config/hosting.qwen-small.json")
    profile_path = configured / "profile.json"
    profile_path.write_text(json.dumps(profile))
    serving = {"application": {"name": "nginx", "version": "1.31.2"},
        "product": profile["machine"]["product"],
        "parameters": {"configFile": {"type": "file", "path": "/files/vllm/nginx.conf"}},
        "resources": [{"type": "file", "path": "/files/vllm"}, {"type": "ingress", "id": "link"}]}
    preparation = {"application": {"name": "coder-python", "version": "1.89.1"},
        "product": {"id": "cpu", "category": "cpu-small", "provider": "ucloud"},
        "resources": [{"type": "file", "path": "/files/vllm"}], "parameters": {}}
    class Client:
        def __init__(self, settings):
            self.settings = settings
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def retrieve_job(self, job_id, **kwargs):
            return {"owner": {"project": "foreign" if foreign else "test-id"}, "updates": [{"state": "RUNNING"}]}
        def request(self, method, path, **kwargs):
            assert method == "GET" and path == "/api/ingresses/retrieve"
            return SimpleNamespace(json=lambda: {"specification": {"domain": "model.example"},
                                                 "status": {"boundTo": ["occupied"] if occupied else []}})
        def submit_job(self, *args):
            pytest.fail("Preflight must never submit")
    monkeypatch.setattr("ucloud_workflow.settings.Settings.from_env", lambda: SimpleNamespace(project="test-id", template_job_id="test-id"))
    monkeypatch.setattr("ucloud_workflow.client.UCloudClient", Client)
    calls = []
    def template(client, template_job_id):
        calls.append(template_job_id)
        return deepcopy(serving if len(calls) == 1 else preparation)
    monkeypatch.setattr("ucloud_workflow.jobs.template_job_specification", template)
    monkeypatch.setattr(diagnostics, "token_status", lambda hours: {"supports_allocation": not expired})
    report = diagnostics.diagnose(online=True, profile=profile_path)
    assert report["passed"] == (not foreign and not expired and not occupied)


def test_cli_errors_are_json_without_echoing_arguments(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as caught:
        main(["--synthetic-secret"])
    assert caught.value.code == 2
    output = capsys.readouterr()
    assert not output.out and "synthetic-secret" not in output.err
    assert json.loads(output.err)["error"]["code"] == "invalid_arguments"
