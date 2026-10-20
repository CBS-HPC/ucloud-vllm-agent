"""Exercise the released client/helpers against an in-memory HTTP service."""
from base64 import b64encode
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

httpx = pytest.importorskip("httpx")
pytest.importorskip("ucloud_workflow")
from ucloud_workflow.client import UCloudClient
from ucloud_workflow.settings import Settings

from ucloud_vllm_agent import resource_setup as setup
from ucloud_vllm_agent.state import load, save

PROJECT = "11111111-1111-4111-8111-111111111111"
PRODUCT = {"id": "link", "category": "link", "provider": "test"}
ALGORITHM = b"ssh-ed25519"
PUBLIC_KEY = "ssh-ed25519 " + b64encode(len(ALGORITHM).to_bytes(4, "big") + ALGORITHM
                                          + (32).to_bytes(4, "big") + bytes(range(32))).decode()


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(setup, "CONTROL", tmp_path / "current.json")
    monkeypatch.setattr(setup, "LOCK", tmp_path / "setup.lock")
    service = SimpleNamespace(links={}, keys={}, calls=[], mode=None)
    client = UCloudClient(Settings(server="https://ucloud.invalid", token="synthetic-secret", project=PROJECT))
    client._client.close()

    def handler(request):
        service.calls.append(request)
        path, method = request.url.path, request.method
        assert "/jobs" not in path, "Resource setup must never touch jobs"
        collection = service.links if path.startswith("/api/ingresses") else service.keys
        if method == "GET" and path.endswith("retrieveProducts"):
            return httpx.Response(200, json={"productsByProvider": {"test": [{"support": {
                "product": PRODUCT, "domainPrefix": "", "domainSuffix": ".example.invalid"}}]}})
        if method == "GET" and path.endswith("browse"):
            return httpx.Response(200, json={"items": list(collection.values())})
        if method == "GET" and path.endswith("retrieve"):
            return httpx.Response(200, json=collection[request.url.params["id"]])
        body = json.loads(request.content)["items"][0]
        identifier = "link-created" if collection is service.links else "key-created"
        if method == "POST":
            if service.mode == "rejected":
                return httpx.Response(402, text="synthetic-secret")
            collection[identifier] = {"id": identifier, "specification": body,
                                      "owner": {"project": PROJECT}, "status": {"state": "READY", "boundTo": []}}
            if service.mode == "lost_ack":
                raise httpx.ReadTimeout("synthetic-secret")
            return httpx.Response(200, json={"responses": [{"id": identifier}]})
        if method == "DELETE":
            del collection[body["id"]]
            if service.mode == "lost_delete_ack":
                raise httpx.ReadTimeout("synthetic-secret")
            return httpx.Response(200, json={})
        pytest.fail("Unexpected request")

    client._client = httpx.Client(base_url=client.settings.server, transport=httpx.MockTransport(handler))
    service.client = client
    yield service
    client.close()


def request():
    return {"schema": "ucloud.vllm.resource_setup.v1", "project": PROJECT, "link": {
        "domain": "model.example.invalid", "product": PRODUCT, "existing_id": None}, "ssh_public_key": None}


def existing(api, **changes):
    item = {"id": "existing", "owner": {"project": PROJECT}, "specification": {
        "domain": "model.example.invalid", "product": PRODUCT}, "status": {"state": "READY", "boundTo": []}}
    item.update(changes)
    api.links["existing"] = item


def mutations(api):
    return [call for call in api.calls if call.method != "GET"]


def test_preview_creation_resume_and_exact_cleanup(api, tmp_path):
    plan = setup.plan_setup(api.client, request())
    root = tmp_path / "setup"
    assert setup.apply_setup(api.client, plan, root)["state"] == "preview"
    assert not mutations(api) and not root.exists()
    report = setup.apply_setup(api.client, plan, root, yes=True)
    assert report["resources"]["link"]["ownership"] == "created"
    assert report["state"] == "resources_ready" and not report["deployment_ready"]
    setup.apply_setup(api.client, plan, root, yes=True)
    assert len(mutations(api)) == 1
    assert setup.cleanup_setup(api.client, root, "link")["state"] == "cleanup_preview"
    assert len(mutations(api)) == 1
    setup.cleanup_setup(api.client, root, "link", yes=True)
    setup.cleanup_setup(api.client, root, "link", yes=True)
    assert len(mutations(api)) == 2 and not api.links
    assert all("/api/ssh" not in call.url.path for call in api.calls)


def test_reuse_never_grants_cleanup_ownership(api, tmp_path):
    existing(api)
    plan = setup.plan_setup(api.client, request())
    assert plan["actions"]["link"] == {"action": "reuse", "id": "existing"}
    setup.apply_setup(api.client, plan, tmp_path / "setup", yes=True)
    with pytest.raises(ValueError, match="reused"):
        setup.cleanup_setup(api.client, tmp_path / "setup", "link", yes=True)
    assert not mutations(api)


@pytest.mark.parametrize("changes", [
    {"owner": {"project": "foreign"}}, {"status": {"state": "READY", "boundTo": ["job"]}},
    {"status": {"state": "READY"}}, {"status": {"state": "READY", "boundTo": None}},
    {"status": {"state": "PREPARING", "boundTo": []}},
])
def test_foreign_occupied_unknown_or_unready_link_blocks(api, changes):
    existing(api, **changes)
    with pytest.raises(ValueError):
        setup.plan_setup(api.client, request())
    assert not mutations(api)


def test_stale_plan_and_changed_target_block_before_mutations(api, tmp_path):
    plan = setup.plan_setup(api.client, request())
    existing(api)
    with pytest.raises(ValueError, match="discovery changed"):
        setup.apply_setup(api.client, plan, tmp_path / "setup", yes=True)
    api.client.settings = replace(api.client.settings, project="22222222-2222-4222-8222-222222222222")
    with pytest.raises(ValueError, match="differs"):
        setup.apply_setup(api.client, plan, tmp_path / "setup", yes=True)
    assert not mutations(api)


def test_unknown_creation_blocks_same_and_different_journal_without_blind_adoption(api, tmp_path):
    plan = setup.plan_setup(api.client, request())
    root = tmp_path / "setup"
    api.mode = "lost_ack"
    with pytest.raises(RuntimeError, match="reconciliation"):
        setup.apply_setup(api.client, plan, root, yes=True)
    assert api.links  # The POST succeeded, but its receipt has no confirmed ID.
    with pytest.raises(ValueError, match="uncertain"):
        setup.apply_setup(api.client, plan, root, yes=True)
    assert setup.reconcile_setup(api.client, root)["state"] == "uncertain"
    new_plan = setup.plan_setup(api.client, request())
    with pytest.raises(ValueError, match="Another setup"):
        setup.apply_setup(api.client, new_plan, tmp_path / "other", yes=True)
    with pytest.raises(ValueError, match="Uncertain"):
        setup.cleanup_setup(api.client, root, "link", yes=True)
    assert len(mutations(api)) == 1
    assert "synthetic-secret" not in (root / "setup.json").read_text()


def test_recover_receipt_after_local_ack_persistence_failure(api, tmp_path, monkeypatch):
    plan = setup.plan_setup(api.client, request())
    root = tmp_path / "setup"
    original = setup._save
    failed = []
    def interrupted(path, data):
        if data["resources"].get("link", {}).get("state") == "known" and not failed:
            failed.append(True)
            raise OSError("simulated local failure after the upstream receipt was saved")
        original(path, data)
    monkeypatch.setattr(setup, "_save", interrupted)
    with pytest.raises(RuntimeError):
        setup.apply_setup(api.client, plan, root, yes=True)
    assert setup.reconcile_setup(api.client, root)["resources"]["link"]["ownership"] == "created"
    assert setup.apply_setup(api.client, plan, root, yes=True)["state"] == "resources_ready"
    assert len(mutations(api)) == 1


def test_rejected_create_has_receipt_but_cannot_retry_same_state(api, tmp_path):
    plan = setup.plan_setup(api.client, request())
    root = tmp_path / "setup"
    api.mode = "rejected"
    with pytest.raises(RuntimeError):
        setup.apply_setup(api.client, plan, root, yes=True)
    report = setup.reconcile_setup(api.client, root)
    assert report["resources"]["link"]["state"] == "rejected"
    with pytest.raises(ValueError, match="rejected"):
        setup.apply_setup(api.client, plan, root, yes=True)
    assert len(mutations(api)) == 1


def test_cleanup_rechecks_ownership_and_binding_and_never_retries_unknown_delete(api, tmp_path):
    plan = setup.plan_setup(api.client, request())
    root = tmp_path / "setup"
    setup.apply_setup(api.client, plan, root, yes=True)
    api.links["link-created"]["owner"]["project"] = "foreign"
    with pytest.raises(ValueError, match="project"):
        setup.cleanup_setup(api.client, root, "link", yes=True)
    api.links["link-created"]["owner"]["project"] = PROJECT
    api.links["link-created"]["status"]["boundTo"] = ["active-job"]
    with pytest.raises(ValueError, match="occupied"):
        setup.cleanup_setup(api.client, root, "link", yes=True)
    api.links["link-created"]["status"]["boundTo"] = []
    api.mode = "lost_delete_ack"
    with pytest.raises(RuntimeError, match="Deletion"):
        setup.cleanup_setup(api.client, root, "link", yes=True)
    with pytest.raises(ValueError, match="Uncertain"):
        setup.cleanup_setup(api.client, root, "link", yes=True)
    assert len(mutations(api)) == 2


def test_readiness_failure_retains_confirmed_id_and_resume_preserves_credentials(api, tmp_path, monkeypatch):
    from ucloud_workflow import resources
    env = tmp_path / ".env"
    env.write_bytes(b"VLLM_API_KEY=synthetic-existing-key\nHF_TOKEN=synthetic-existing-token\n")
    before = env.read_bytes()
    plan = setup.plan_setup(api.client, request())
    root = tmp_path / "setup"
    wait = resources.wait_for_resource
    monkeypatch.setattr(resources, "wait_for_resource", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("wait interrupted")))
    with pytest.raises(RuntimeError, match="wait interrupted"):
        setup.apply_setup(api.client, plan, root, yes=True)
    assert load(root / "setup.json")["resources"]["link"]["id"] == "link-created"
    monkeypatch.setattr(resources, "wait_for_resource", wait)
    setup.apply_setup(api.client, plan, root, yes=True)
    assert env.read_bytes() == before and len(mutations(api)) == 1


def test_optional_public_key_registration_fingerprint_reuse_and_explicit_removal(api, tmp_path):
    key = tmp_path / "selected.pub"
    key.write_text(PUBLIC_KEY)
    value = request()
    value.update(link=None, ssh_public_key={"path": str(key), "title": "hosting", "register_if_missing": False})
    with pytest.raises(ValueError, match="not registered"):
        setup.plan_setup(api.client, value)
    value["ssh_public_key"]["register_if_missing"] = True
    plan = setup.plan_setup(api.client, value)
    root = tmp_path / "setup"
    report = setup.apply_setup(api.client, plan, root, yes=True)
    assert report["resources"]["ssh_key"]["ownership"] == "created"
    assert PUBLIC_KEY not in json.dumps(report) + (root / "setup.json").read_text()
    second_plan = setup.plan_setup(api.client, value)
    assert second_plan["actions"]["ssh_key"]["action"] == "reuse"
    second = tmp_path / "second"
    setup.apply_setup(api.client, second_plan, second, yes=True)
    with pytest.raises(ValueError, match="reused"):
        setup.cleanup_setup(api.client, second, "ssh_key", yes=True)
    setup.cleanup_setup(api.client, root, "ssh_key", yes=True)
    assert not api.keys and len(mutations(api)) == 2


def test_selected_private_key_path_is_rejected_before_reading(api, tmp_path, monkeypatch):
    from pathlib import Path
    value = request()
    private = tmp_path / "private"
    value.update(link=None, ssh_public_key={"path": str(private), "title": "hosting", "register_if_missing": True})
    original = Path.read_text
    def guarded_read(path, *args, **kwargs):
        # Guard the selected file; dependency-version checks read package metadata.
        if path == private:
            pytest.fail("Private key must not be read")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", guarded_read)
    with pytest.raises(ValueError, match=".pub"):
        setup.plan_setup(api.client, value)
    assert not mutations(api)


def test_cleanup_requires_exact_creation_receipt(api, tmp_path):
    root = tmp_path / "setup"
    setup.apply_setup(api.client, setup.plan_setup(api.client, request()), root, yes=True)
    receipt = next((root / "operations/link").glob("*.json"))
    data = load(receipt)
    data["resource_id"] = "different-id"
    save(receipt, data)
    with pytest.raises(ValueError, match="exact ID"):
        setup.cleanup_setup(api.client, root, "link", yes=True)
    assert len(mutations(api)) == 1


def test_cli_plan_apply_status_and_reconcile_json_without_template_ids(api, tmp_path, monkeypatch, capsys):
    from ucloud_vllm_agent.cli import main
    monkeypatch.setattr("ucloud_workflow.client.UCloudClient", lambda _: api.client)
    monkeypatch.setattr("ucloud_workflow.settings.Settings.from_env", lambda: api.client.settings)
    monkeypatch.setattr(api.client, "close", lambda: None)
    source, plan, root = tmp_path / "request.json", tmp_path / "plan.json", tmp_path / "setup"
    save(source, request())
    assert main(["setup-plan", "--request", str(source), "--output", str(plan)]) == 0
    assert json.loads(capsys.readouterr().out)["schema"] == "ucloud.vllm.resource_plan.v1"
    assert main(["setup-apply", "--plan", str(plan), "--state", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "preview"
    assert not mutations(api)
    assert main(["setup-apply", "--plan", str(plan), "--state", str(root), "--yes"]) == 0
    assert not json.loads(capsys.readouterr().out)["job_submitted"]
    assert main(["setup-status", "--state", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "resources_ready"
