"""Task verification using the separately released LUMI AITTA API client."""
from __future__ import annotations

from .checks import check_endpoint


def _client():
    try:
        from lumi_aitta_api import AittaClient, Settings
    except ImportError:
        raise ValueError("Install this project's optional [aitta] extra before using AITTA") from None
    return AittaClient(Settings.from_env())


def list_models() -> dict:
    return _client().models()


def service_status() -> dict:
    return _client().status()


def workers(model: str) -> dict:
    return _client().workers(model)


def preload(model: str) -> dict:
    return _client().preload(model)


def check_model(model: str, *, timeout: int = 300) -> dict:
    if not 30 <= timeout <= 900:
        raise ValueError("AITTA timeout must be between 30 and 900 seconds")
    from lumi_aitta_api.client import OPENAI_URL
    client = _client()
    details = client.model(model)
    if "openai-chat-completion" not in details["capabilities"]:
        raise ValueError("Requested AITTA model does not advertise chat capability")
    result = check_endpoint(OPENAI_URL, model, client.settings.api_key,
                            include_models=False, timeout=timeout)
    result.update(platform="lumi-aitta", managed_service=True,
                  note="Inference may load a model on LUMI. No availability guarantee; "
                       "AITTA owns machine selection and allocations. No automatic retry.")
    return result
