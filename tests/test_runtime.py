from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ucloud_vllm_agent import remote


def test_stop_targets_only_the_owned_unique_session(tmp_path, monkeypatch):
    config = {"session": "vllm-model-12345678"}
    monkeypatch.setattr(remote, "read_runtime", lambda root: config)
    monkeypatch.setattr(remote, "__file__", str(tmp_path / "remote.py"))
    monkeypatch.setattr("sys.argv", ["remote.py", "stop"])
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(remote.subprocess, "run", run)
    assert remote.main() == 0
    assert calls == [["tmux", "kill-session", "-t", "=vllm-model-12345678"]]
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["state"] == "stopped"
    assert "allocation remains" in state["note"]


def test_start_detaches_and_does_not_stop_after_return(tmp_path, monkeypatch):
    config = {"session": "vllm-model-12345678"}
    monkeypatch.setattr(remote, "read_runtime", lambda root: config)
    monkeypatch.setattr(remote, "preflight", lambda config, root: {"state": "preflight_passed"})
    monkeypatch.setattr(remote, "load_runtime_secrets", lambda config: {"VLLM_API_KEY": "private"})
    monkeypatch.setattr(remote, "__file__", str(tmp_path / "remote.py"))
    monkeypatch.setattr("sys.argv", ["remote.py", "start"])
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 1 if command[1] == "has-session" else 0)

    monkeypatch.setattr(remote.subprocess, "run", run)
    assert remote.main() == 0
    assert calls[1][:3] == ["tmux", "new-session", "-d"]
    assert len(calls) == 2
    assert "private" not in (tmp_path / "state.json").read_text()
