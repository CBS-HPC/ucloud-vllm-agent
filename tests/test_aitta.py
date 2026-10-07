from types import SimpleNamespace

import pytest

from ucloud_vllm_agent import aitta
from ucloud_vllm_agent.cli import main


@pytest.fixture
def client(monkeypatch):
    class Client:
        settings = SimpleNamespace(api_key="separate-aitta-key")
        capabilities = ["openai-chat-completion"]

        def model(self, model):
            return {"model": model, "capabilities": self.capabilities}

        def models(self):
            return {"models": ["vendor/model"]}

        def status(self):
            return {"is_available": True}

        def workers(self, model):
            return {"model": model, "workers": []}

        def preload(self, model):
            return {"model": model, "state": "preload_requested"}

    instance = Client()
    monkeypatch.setattr(aitta, "_client", lambda: instance)
    return instance


def test_discovery_and_preload_delegate_to_dependency(client):
    assert aitta.list_models()["models"] == ["vendor/model"]
    assert aitta.service_status()["is_available"]
    assert aitta.workers("vendor/model")["workers"] == []
    assert aitta.preload("vendor/model")["state"] == "preload_requested"


def test_inference_uses_separate_key_and_no_models_route(client, monkeypatch):
    # Tests run without optional dependencies in base CI.
    import sys
    monkeypatch.setitem(sys.modules, "lumi_aitta_api.client", SimpleNamespace(OPENAI_URL="https://aitta-api.csc.fi/openai/v1"))
    calls = []
    monkeypatch.setattr(aitta, "check_endpoint", lambda *args, **kwargs:
                        calls.append((args, kwargs)) or {"passed": True})
    assert aitta.check_model("vendor/model")["managed_service"]
    assert calls == [(("https://aitta-api.csc.fi/openai/v1", "vendor/model", "separate-aitta-key"),
                      {"include_models": False, "timeout": 300})]
    client.capabilities = ["openai-embedding"]
    with pytest.raises(ValueError, match="chat capability"):
        aitta.check_model("vendor/model")
    assert len(calls) == 1


@pytest.mark.parametrize("timeout", [0, 29, 901])
def test_invalid_timeout_prevents_client_creation(timeout, monkeypatch):
    monkeypatch.setattr(aitta, "_client", lambda: pytest.fail("Client must not be created"))
    with pytest.raises(ValueError, match="timeout"):
        aitta.check_model("vendor/model", timeout=timeout)


def test_cli_discovery_does_not_allocate_ucloud_jobs(client, capsys):
    assert main(["aitta", "models"]) == 0
    assert "vendor/model" in capsys.readouterr().out
