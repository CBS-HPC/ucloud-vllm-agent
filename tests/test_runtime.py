from __future__ import annotations

import json
import subprocess
import pytest
from pathlib import Path

from ucloud_vllm_agent import remote


@pytest.mark.parametrize('task, ports', [('chat', [8000]), ('pii', [8000, 8001])])
def test_stop_targets_only_the_owned_unique_session(tmp_path, monkeypatch, task, ports):
    config = {"session": "vllm-model-12345678", "port": 8000, "task": task}
    waited = []
    monkeypatch.setattr(remote, "wait_for_port_release", waited.append)
    monkeypatch.setattr(remote, "read_runtime", lambda root: config)
    monkeypatch.setattr(remote, "__file__", str(tmp_path / "remote.py"))
    monkeypatch.setattr("sys.argv", ["remote.py", "stop"])
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(remote.subprocess, "run", run)
    assert remote.main() == 0
    assert waited == ports
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


def test_compilation_experiments_do_not_change_model_cache_or_production_cache():
    config = {'cache_dir': '/work/vllm/cache/huggingface'}
    assert remote.kernel_cache_base(config).as_posix() == '/work/vllm/cache/kernels'
    experiment = {**config, 'kernel_cache_group': 'validation-123'}
    assert remote.kernel_cache_base(experiment).as_posix() == '/work/vllm/cache/kernels/experiments/validation-123'
    assert experiment['cache_dir'] == config['cache_dir']
    for bad in ('../shared', '/work/vllm', '', 3):
        with pytest.raises(ValueError, match='experiment group'):
            remote.kernel_cache_base({**config, 'kernel_cache_group': bad})


@pytest.mark.skipif(__import__('sys').platform != 'linux', reason='Linux serving socket semantics')
def test_closed_connections_allow_restart_but_live_listener_still_blocks():
    import socket
    server=socket.socket()
    server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    server.bind(('127.0.0.1',0));server.listen(1)
    port=server.getsockname()[1]
    try:
        with pytest.raises(ValueError,match='port remains busy'):
            remote.wait_for_port_release(port,timeout=0.05)
        client=socket.create_connection(('127.0.0.1',port));peer,_=server.accept()
        peer.shutdown(socket.SHUT_WR);peer.close();client.recv(1);client.close()
    finally:
        server.close()
    # The listener exited, but an accepted connection is still in TIME_WAIT.
    remote.wait_for_port_release(port,timeout=0.05)
