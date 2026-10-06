from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("ucloud_workflow")

from ucloud_vllm_agent.ucloud_access import preview_job_specification, token_status


@pytest.mark.parametrize("product", [
    {"id": "gpu-nvidia-b200-1-gpu", "category": "gpu-nvidia-b200", "provider": "ucloud"},
    {"id": "gpu-nvidia-b200-1-mig.1g", "category": "gpu-nvidia-b200", "provider": "ucloud"},
    None,
])
def test_released_builder_preserves_template_and_uses_exact_product(product):
    template = {"product": {"id": "template-gpu", "category": "gpu", "provider": "ucloud"},
                "resources": [{"type": "file", "path": "/drive/vllm"}, {"type": "ingress", "id": "link"}],
                "application": {"name": "nginx", "version": "1.31.2"},
                "parameters": {"config": "/work/vllm/nginx.conf"}}
    before = deepcopy(template)
    result = preview_job_specification(template, hours=4, product=product)
    assert template == before
    assert result["resources"] == before["resources"]
    assert result["parameters"] == before["parameters"]
    assert result["application"] == before["application"]
    assert result["product"] == (product or before["product"])
    assert result["timeAllocation"]["hours"] == 4


def test_expiry_uses_the_configured_token_id_not_first_item(monkeypatch):
    monkeypatch.setenv("UCLOUD_TOKEN_ID", "chosen-token")
    expiry = int((datetime.now(timezone.utc) + timedelta(days=10)).timestamp() * 1000)
    response = {"items": [
        {"id": "other-token", "specification": {"expiresAt": 1}},
        {"id": "chosen-token", "specification": {"expiresAt": expiry}},
    ]}

    class Client:
        def __init__(self, settings):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def browse_api_tokens(self, **kwargs):
            return response

    monkeypatch.setattr("ucloud_workflow.client.UCloudClient", Client)
    monkeypatch.setattr("ucloud_workflow.settings.Settings.from_env", lambda: object())
    assert token_status(hours=4)["supports_allocation"]
    assert not token_status(hours=300)["supports_allocation"]
