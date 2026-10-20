from copy import deepcopy
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("ucloud_workflow")
from ucloud_workflow.client import UCloudAPIError
from ucloud_vllm_agent import bootstrap as b, lifecycle, remote_bootstrap as remote
from ucloud_vllm_agent.config import load_json
from ucloud_vllm_agent.hosting import validate_profile
from ucloud_vllm_agent.resource_setup import SetupOutcomeUnknownError
from ucloud_vllm_agent.state import Journal, save

PROJECT = "3b43523f-524d-4c69-98eb-cbd1f1ef981e"
CPU = {"id": "cpu-1", "category": "cpu-test", "provider": "ucloud"}
CONTRACTS = json.loads(files("ucloud_vllm_agent").joinpath("data/bootstrap_applications.json").read_text())["applications"]


class Client:
    def __init__(self):
        self.settings = SimpleNamespace(project=PROJECT, server="https://cloud.example", template_job_id=None)
        self.folders = {"/drive"}
        self.calls, self.submissions, self.terminated = [], [], []
        self.jobs = {}
        self.lose_folder = self.lose_job = False
        self.bound, self.foreign, self.gpu_on_cpu, self.changed_app = [], False, False, False

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, deepcopy(kwargs)))
        params = kwargs.get("params", {})
        if path == "/api/files/retrieve":
            name = params["id"]
            if name not in self.folders:
                raise UCloudAPIError("synthetic missing", status_code=404)
            result = {"id": name, "owner": {"project": "foreign" if self.foreign else PROJECT},
                      "status": {"type": "DIRECTORY"}, "specification": {"collection": "drive", "product": {"provider": "ucloud"}},
                      "permissions": {"myself": ["EDIT"]}}
        elif path == "/api/files/folder":
            item, = kwargs["json"]["items"]
            assert item["conflictPolicy"] == "REJECT" and item["id"] not in self.folders
            self.folders.add(item["id"])
            if self.lose_folder:
                raise TimeoutError("synthetic-private-body")
            result = {"responses": [{}]}
        elif path == "/api/hpc/apps/byNameAndVersion":
            contract = next(c for c in CONTRACTS if c["application"]["name"] == params["appName"])
            result = {"metadata": contract["application"], "invocation": {
                "applicationType": "WEB", "tool": {"tool": {"description": {"backend": "DOCKER"}}},
                "allowAdditionalMounts": not self.changed_app, "allowPublicLink": True,
                "ssh": {"mode": contract["ssh_mode"]},
                "parameters": [{"name": p["name"], "type": p["type"], "optional": p["optional"]} for p in contract["parameters"]]}}
        elif path == "/api/ingresses/retrieve":
            result = self.retrieve_resource("ingresses", "link")
        else:
            raise AssertionError("Unreviewed route")
        return SimpleNamespace(json=lambda: deepcopy(result))

    def _validate_resource_namespace(self, ns):
        assert ns == "ingresses"

    def browse_resources(self, ns, **kwargs):
        return {"items": [{"id": "link"}]}

    def retrieve_resource(self, ns, identifier):
        assert ns == "ingresses" and identifier == "link"
        return {"id": "link", "owner": {"project": PROJECT},
                "specification": {"domain": "test.example", "product": {"id": "link", "category": "link", "provider": "ucloud"}},
                "status": {"state": "READY", "boundTo": self.bound}}

    def retrieve_resource_products(self, ns):
        return {"productsByProvider": {"ucloud": [{"support": {"product": {"id": "link", "category": "link", "provider": "ucloud"}}}]}}

    def retrieve_compute_products(self):
        gpu = load_json(Path(__file__).parents[1] / "config/hosting.qwen-small.json")["machine"]["product"]
        return {"productsByProvider": {"ucloud": [{"product": {"gpu": int(self.gpu_on_cpu) if p == CPU else 1},
                    "support": {"product": p, "docker": {"enabled": True, "web": True}}} for p in (CPU, gpu)]}}

    def submit_job(self, spec):
        self.submissions.append(deepcopy(spec))
        identifier = str(100 + len(self.submissions))
        self.jobs[identifier] = {"id": identifier, "owner": {"project": PROJECT},
                                 "specification": deepcopy(spec), "updates": [{"state": "RUNNING"}]}
        if self.lose_job:
            raise TimeoutError("synthetic-private-body")
        return {"responses": [{"id": identifier}]}

    def retrieve_job(self, identifier, **kwargs):
        return deepcopy(self.jobs[identifier])

    def terminate_job(self, identifier):
        self.terminated.append(identifier)
        self.jobs[identifier]["updates"].append({"state": "SUCCESS"})


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(b, "CONTROL", tmp_path / "run/bootstrap-current.json")
    monkeypatch.setattr(b, "LOCK", tmp_path / "run/bootstrap.lock")
    monkeypatch.setattr(lifecycle, "CONTROL_ROOT", tmp_path / "run")
    monkeypatch.setattr(b, "token_status", lambda h: {"supports_allocation": True})
    monkeypatch.setenv("VLLM_API_KEY", "synthetic-serving-key")
    monkeypatch.setenv("HF_TOKEN", "synthetic-hf-token")
    monkeypatch.setenv("UCLOUD_TOKEN", "synthetic-ucloud-token-must-stay-local")
    monkeypatch.setenv("UCLOUD_PUBLIC_BASE_URL", "https://test.example/v1")
    monkeypatch.delenv("UCLOUD_PREPARATION_TEMPLATE_JOB_ID", raising=False)
    monkeypatch.delenv("UCLOUD_TEMPLATE_JOB_ID", raising=False)
    monkeypatch.setattr("ucloud_workflow.ssh_keys.check_ssh_key", lambda *a: {"state": "MATCHED", "matches": [{"fingerprint": "SHA256:synthetic"}]})
    value = {"schema": "ucloud.vllm.bootstrap_request.v1", "project": PROJECT,
             "storage_parent": "/drive", "namespace": "onboarding-test", "cpu_product": CPU,
             "link_id": "link", "public_base_url": "https://test.example/v1", "ssh_public_key": str(tmp_path / "id.pub")}
    return Client(), value, tmp_path / "state"


class Transport:
    def __init__(self):
        self.calls, self.uploads = [], []
        self.lose_credentials = False

    def run(self, args, **kwargs):
        self.calls.append((deepcopy(args), deepcopy(kwargs)))
        if args[1] == "-c":
            return json.dumps({"stage": "/work/vllm/.bootstrap/" + args[-1]})
        if "provision-credentials" in args:
            if self.lose_credentials:
                raise TimeoutError("synthetic-private-body")
            return '{"state":"credentials_provisioned"}'
        if "verify-credentials" in args:
            return '{"state":"credentials_verified","key_matches":true}'
        return json.dumps({"state": "assets_ready", "files": json.loads(b._payload_bytes()["manifest.json"])})

    def upload(self, local, target):
        assert local.name not in (".env", "id.pub")
        self.uploads.append(target)


def apply(setup, monkeypatch):
    client, value, root = setup
    transport = Transport()
    monkeypatch.setattr(b, "_transport", lambda *a: transport)
    plan = b.plan_bootstrap(client, value)
    result = b.apply_bootstrap(client, plan, root, yes=True)
    return client, plan, root, transport, result


def test_bootstrap_plan_is_read_only_and_has_no_job_dependency(setup):
    client, value, root = setup
    plan = b.plan_bootstrap(client, value)
    assert plan["gpu_jobs"] == 0 and plan["cpu_hours"] == 1
    assert plan["storage_path"] == "/drive/onboarding-test/vllm"
    b.apply_bootstrap(client, plan, root)
    assert all(method == "GET" for method, _, _ in client.calls)
    assert not client.submissions and not root.exists()
    assert "synthetic-serving-key" not in json.dumps(plan)


@pytest.mark.parametrize("problem", ["foreign", "bound", "gpu_on_cpu", "changed_app"])
def test_invalid_bootstrap_contract_blocks_before_writes(setup, problem):
    client, value, root = setup
    setattr(client, problem, ["occupied"] if problem == "bound" else True)
    with pytest.raises(ValueError):
        b.plan_bootstrap(client, value)
    assert all(method == "GET" for method, _, _ in client.calls)
    assert not client.submissions


@pytest.mark.parametrize("lost", ["folder", "job"])
def test_unknown_folder_or_job_blocks_duplicate_creation(setup, monkeypatch, lost):
    client, value, root = setup
    plan = b.plan_bootstrap(client, value)
    setattr(client, "lose_" + lost, True)
    with pytest.raises((SetupOutcomeUnknownError, RuntimeError)):
        b.apply_bootstrap(client, plan, root, yes=True)
    writes = [c for c in client.calls if c[0] == "POST"]
    with pytest.raises(ValueError, match="unresolved|unknown"):
        b.apply_bootstrap(client, plan, root, yes=True)
    assert len([c for c in client.calls if c[0] == "POST"]) == len(writes)
    assert len(client.submissions) == (1 if lost == "job" else 0)
    if lost == "job":
        client.jobs["101"]["specification"]["resources"] = []
        with pytest.raises(ValueError, match="exact recorded"):
            b.reconcile_bootstrap(client, root, "101")
        client.jobs["101"]["specification"] = deepcopy(client.submissions[0])
        b.reconcile_bootstrap(client, root, "101")
        assert b.status_bootstrap(client, root)["cpu_job_state"] == "RUNNING"


def test_malformed_folder_acknowledgement_never_proves_creation_ownership(setup, monkeypatch):
    client, value, root = setup
    plan = b.plan_bootstrap(client, value)
    request = client.request
    def malformed(method, path, **kwargs):
        response = request(method, path, **kwargs)
        return SimpleNamespace(json=lambda: {"responses": [{"error": "synthetic"}]}) if method == "POST" else response
    monkeypatch.setattr(client, "request", malformed)
    with pytest.raises(SetupOutcomeUnknownError):
        b.apply_bootstrap(client, plan, root, yes=True)
    assert Journal(root).data["folders"][plan["namespace_path"]]["ownership"] == "uncertain"
    assert client.submissions == []


def test_bootstrap_finish_releases_only_cpu_and_publishes_inert_spec(setup, monkeypatch):
    client, plan, root, transport, result = apply(setup, monkeypatch)
    assert result["assets_ready"] and result["gpu_jobs"] == 0
    spec, = client.submissions
    assert spec["product"] == CPU and spec["sshEnabled"] is True
    assert spec["timeAllocation"] == {"hours": 1, "minutes": 0, "seconds": 0}
    b.apply_bootstrap(client, plan, root, yes=True)
    assert len(client.submissions) == 1
    b.finish_bootstrap(client, root, yes=True)
    data = b.read_bootstrap(root / "bootstrap.json")
    assert data["serving"]["application"]["name"] == "nginx"
    assert data["serving"]["product"] == CPU  # placeholder, never submitted
    assert client.terminated == ["101"]
    b.finish_bootstrap(client, root, yes=True)
    b.release_bootstrap(client, root, yes=True)
    assert client.terminated == ["101"] and len(client.submissions) == 1
    assert set(client.folders) == {"/drive", plan["namespace_path"], plan["storage_path"]}


def test_secrets_use_stdin_exclusive_creation_and_unknown_write_guard(setup, monkeypatch):
    client, plan, root, transport, _ = apply(setup, monkeypatch)
    preview = b.provision_bootstrap_credentials(client, root)
    assert preview["state"] == "credential_preview"
    transport.lose_credentials = True
    with pytest.raises(SetupOutcomeUnknownError):
        b.provision_bootstrap_credentials(client, root, yes=True, include_hf_token=True)
    args, kwargs = transport.calls[-1]
    assert "synthetic-serving-key" not in json.dumps(args)
    assert json.loads(kwargs["input"]) == {"VLLM_API_KEY": "synthetic-serving-key", "HF_TOKEN": "synthetic-hf-token"}
    count = len(transport.calls)
    with pytest.raises(ValueError, match="unknown"):
        b.provision_bootstrap_credentials(client, root, yes=True)
    assert len(transport.calls) == count
    assert "synthetic-serving-key" not in (root / "deployment.json").read_text()
    assert "synthetic-ucloud-token" not in json.dumps(transport.calls)
    assert not list(root.rglob(".env"))
    b.finish_bootstrap(client, root, yes=True)  # verify an uncertain write, never repeat it
    assert b.read_bootstrap(root / "bootstrap.json")["credentials_verified_at"]


def test_payload_change_blocks_all_mutations(setup, monkeypatch):
    client, plan, root, transport, _ = apply(setup, monkeypatch)
    client.terminate_job("101")
    calls, submissions = len(client.calls), len(client.submissions)
    old = b._payload_bytes()
    monkeypatch.setattr(b, "_payload_bytes", lambda: {**old, "remote.py": b"changed"})
    with pytest.raises(ValueError, match="version changed"):
        b.apply_bootstrap(client, plan, root, yes=True)
    assert len(client.calls) == calls and len(client.submissions) == submissions


def test_bootstrap_deployment_recovery_and_template_mode(setup, monkeypatch):
    client, plan, state, transport, _ = apply(setup, monkeypatch)
    b.finish_bootstrap(client, state, yes=True)
    profile = validate_profile(load_json(Path(__file__).parents[1] / "config/hosting.qwen-small.json"))
    root = state.parent / "bundle"
    save(root / "hosting-profile.json", profile)
    save(root / "runtime.json", {"remote_dir": "/work/vllm/deployments/model/bundle"})
    monkeypatch.setattr(lifecycle, "token_status", lambda h: {"supports_allocation": True})
    monkeypatch.setattr(lifecycle, "_validate_template_ownership", lambda *a: pytest.fail("No template lookup in bootstrap mode"))
    monkeypatch.setattr("ucloud_workflow.jobs.template_job_specification", lambda *a, **k: pytest.fail("No prior-job dependency"))
    def prepare(c, settings, journal, prep, runtime):
        journal.submitted("preparation", c, {**prep, "name": "owned-cpu"})
        journal.update(preparation_complete=True)
    monkeypatch.setattr(lifecycle, "_prepare_remote", prepare)
    attempts = []
    def activate(*args):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("synthetic interrupted activation")
        args[2].update(activated=True)
    monkeypatch.setattr(lifecycle, "_activate", activate)
    monkeypatch.setattr(lifecycle, "wait_job", lambda c, job_id, **kw: c.retrieve_job(job_id))
    monkeypatch.setattr(lifecycle, "verify_host", lambda c, j, r: j.update("endpoint_verified", endpoint_verified=True))
    with pytest.raises(RuntimeError, match="interrupted"):
        lifecycle.deploy(client, None, root=root, reviewed=True, bootstrap=state / "bootstrap.json")
    assert len(client.submissions) == 2  # bootstrap CPU + deployment preparation CPU
    result = lifecycle.deploy(client, None, root=root, reviewed=True)
    assert result["source_mode"] == "bootstrap" and result["endpoint_verified"]
    assert result["serving_template_id"] is None
    assert client.submissions[-1]["product"] == profile["machine"]["product"]
    lifecycle.deploy(client, None, root=root, reviewed=True)
    assert len(client.submissions) == 3 and client.terminated == ["101", "102"]
    changed = b.read_bootstrap(state / "bootstrap.json")
    changed["credentials_verified_at"] = "different"
    changed["digest"] = b._digest({k: v for k, v in changed.items() if k != "digest"})
    save(state / "changed.json", changed)
    with pytest.raises(ValueError, match="preserve its bootstrap"):
        lifecycle.deploy(client, None, root=root, reviewed=True, bootstrap=state / "changed.json")
    assert len(client.submissions) == 3
    created = []
    def bundle(p, metadata, output):
        target = root.parent / ("replacement-" + str(len(created)))
        created.append(target)
        save(target / "hosting-profile.json", p)
        save(target / "runtime.json", {"remote_dir": "/work/vllm/" + target.name})
        return target
    monkeypatch.setattr(lifecycle, "inspect_model", lambda *a: {})
    monkeypatch.setattr(lifecycle, "prepare_profile", bundle)
    renewed = lifecycle.renew(client, root, 2)
    assert renewed["bootstrap_digest"] == result["bootstrap_digest"]
    assert client.submissions[-1]["timeAllocation"]["hours"] == 2
    count = len(client.submissions)
    lifecycle.renew(client, root, 2)
    assert len(client.submissions) == count
    restored = lifecycle.rollback(client, created[0])
    assert restored["restored_from"] == str(root)
    assert restored["bootstrap_digest"] == result["bootstrap_digest"]
    assert client.submissions[-1]["timeAllocation"]["hours"] == 1
    assert all(spec["resources"][0]["path"] == plan["storage_path"] for spec in client.submissions)


def test_bootstrap_doctor_omits_template_requirements_and_reads_no_network_offline(setup, monkeypatch):
    from ucloud_vllm_agent import diagnostics
    client, plan, root, transport, _ = apply(setup, monkeypatch)
    b.finish_bootstrap(client, root, yes=True)
    for key in ("UCLOUD_PROJECT", "UCLOUD_TOKEN_ID"):
        monkeypatch.setenv(key, PROJECT)
    identity = root / "key-placeholder"
    identity.write_text("placeholder, never parsed")
    monkeypatch.setenv("UCLOUD_SSH_IDENTITY_FILE", str(identity))
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: "/tools/" + name)
    monkeypatch.setattr(diagnostics, "_online_preflight", lambda *a, **kw: pytest.fail("Offline means no API calls"))
    result = diagnostics.diagnose(bootstrap=root / "bootstrap.json")
    assert result["passed"] and not result["ready_for_submission"]
    assert "UCLOUD_TEMPLATE_JOB_ID" not in result["configured"]
    assert result["source_mode"] == "bootstrap"
    assert not diagnostics.diagnose()["passed"]  # no implicit mode change


def test_bootstrap_cannot_replace_template_deployment(setup, monkeypatch):
    client, plan, root, transport, _ = apply(setup, monkeypatch)
    b.finish_bootstrap(client, root, yes=True)
    old = root.parent / "old-template"
    Journal(old).update(reviewed=True, source_mode="template")
    count = len(client.submissions)
    with pytest.raises(ValueError, match="across template and bootstrap"):
        lifecycle.deploy(client, {}, replace=old, reviewed=True, bootstrap=root / "bootstrap.json")
    assert len(client.submissions) == count


def test_assets_preserve_conflicts_symlinks_and_secret_files(tmp_path):
    root, stage = tmp_path / "vllm", tmp_path / "stage"
    root.mkdir(); stage.mkdir()
    payload = b._payload_bytes()
    for name, value in payload.items():
        (stage / name).write_bytes(value)
    secret = root / ".env"
    secret.write_text("existing secret; never touched")
    (root / "README.md").write_text("existing researcher file")
    with pytest.raises(ValueError, match="preserved"):
        remote.install_assets(stage, root)
    assert not (root / "nginx.conf").exists()  # preflight before all writes
    (root / "README.md").unlink()
    result = remote.install_assets(stage, root)
    assert result["state"] == "assets_ready"
    assert secret.read_text() == "existing secret; never touched"
    assert remote.install_assets(stage, root) == result
    (stage / "nginx.conf").write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        remote.install_assets(stage, root)


@pytest.mark.skipif(os.name == "nt", reason="Remote helper uses Linux ownership and O_NOFOLLOW")
def test_remote_secret_exclusive_permissions_and_symlink_guard(tmp_path):
    values = {"HF_TOKEN": "", "VLLM_API_KEY": "synthetic"}
    remote.provision_credentials(values, tmp_path)
    assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        remote.provision_credentials(values, tmp_path)
    (tmp_path / ".env").unlink()
    target = tmp_path / "foreign"; target.write_text("preserved")
    (tmp_path / ".env").symlink_to(target)
    with pytest.raises(FileExistsError):
        remote.provision_credentials(values, tmp_path)
    assert target.read_text() == "preserved"
    stage = tmp_path / "stage"; stage.mkdir()
    for name, value in b._payload_bytes().items():
        (stage / name).write_bytes(value)
    (tmp_path / "nginx.conf").symlink_to(target)
    with pytest.raises(ValueError, match="preserved"):
        remote.install_assets(stage, tmp_path)
    assert target.read_text() == "preserved" and not (tmp_path / "README.md").exists()
