"""Reviewed no-prior-job bootstrap into a fresh project-owned namespace."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path, PurePosixPath
import re
from uuid import uuid4

from .config import normalize_public_url
from .resource_setup import _digest, _scope, SetupOutcomeUnknownError
from .state import Journal, load, operation_lock, save
from .ucloud_access import require_hosting_adapter, token_status

CONTROL = Path("run/bootstrap-current.json")
LOCK = Path("run/bootstrap.lock")
ASSETS = ("nginx.conf", "init_vllm.sh", "README.md", ".env.example")


def _path(value) -> str:
    if (not isinstance(value, str) or not value.startswith("/") or value == "/"
            or any(c in value for c in "\r\n\x00\\") or ".." in value.split("/")
            or str(PurePosixPath(value)) != value):
        raise ValueError("Select a normalized absolute UCloud Files path")
    return value


def _request(value: dict) -> dict:
    if (not isinstance(value, dict) or set(value) != {"schema", "project", "storage_parent", "namespace", "cpu_product", "link_id", "public_base_url", "ssh_public_key"}
            or value.get("schema") != "ucloud.vllm.bootstrap_request.v1"):
        raise ValueError("Unsupported bootstrap request schema or fields")
    result = deepcopy(value)
    result["storage_parent"] = _path(value["storage_parent"])
    if not isinstance(value["namespace"], str) or not re.fullmatch(r"[a-z][a-z0-9-]{3,62}", value["namespace"]):
        raise ValueError("Use a fresh namespace of 4..63 lowercase letters, digits and hyphens")
    product = value["cpu_product"]
    if (not isinstance(product, dict) or set(product) != {"id", "category", "provider"}
            or any(not isinstance(v, str) or not v.strip() or any(c in v for c in "\r\n\x00") for v in product.values())
            or not product["category"].startswith("cpu-")):
        raise ValueError("Bootstrap requires a complete, explicitly selected CPU product")
    if not isinstance(value["link_id"], str) or not value["link_id"].strip():
        raise ValueError("Select the exact reserved Public Link ID")
    result["public_base_url"] = normalize_public_url(value["public_base_url"])
    if not isinstance(value["ssh_public_key"], str) or Path(value["ssh_public_key"]).suffix != ".pub":
        raise ValueError("Select an existing local .pub file; private keys remain local")
    result["ssh_public_key"] = str(Path(value["ssh_public_key"]).expanduser().resolve())
    return result


def application_contract(client, reference: dict) -> dict:
    """Read public application definitions, never a historical job's parameters."""
    app = client.request("GET", "/api/hpc/apps/byNameAndVersion",
                         params={"appName": reference["name"], "appVersion": reference["version"]}).json()
    invocation = app.get("invocation", {})
    tool = (invocation.get("tool") or {}).get("tool", {}).get("description", {})
    parameters = sorted([{"name": p.get("name"), "type": p.get("type"), "optional": p.get("optional"),
                          "has_default": p.get("defaultValue") is not None} for p in invocation.get("parameters", [])], key=lambda p: p["name"])
    contract = {"application": {k: app.get("metadata", {}).get(k) for k in ("name", "version")},
                "application_type": invocation.get("applicationType"), "backend": tool.get("backend"),
                "allow_additional_mounts": invocation.get("allowAdditionalMounts"), "allow_public_link": invocation.get("allowPublicLink"),
                "ssh_mode": (invocation.get("ssh") or {}).get("mode"), "parameters": parameters}
    reviewed = json.loads(files("ucloud_vllm_agent").joinpath("data/bootstrap_applications.json").read_text())
    expected = next((item for item in reviewed["applications"] if item["application"] == reference), None)
    if contract != expected:
        raise ValueError("Application schema differs from the reviewed bootstrap baseline")
    return contract


def directory(client, path: str, provider: str, *, missing: bool = False) -> dict | None:
    path = _path(path)
    if missing:
        from ucloud_workflow.resources import browse_all
        parent = str(PurePosixPath(path).parent)
        directory(client, parent, provider)
        # Providers differ on the status code for a missing file. Only a full
        # successful listing of its verified parent establishes absence.
        children = browse_all(lambda next_page=None: client.request("GET", "/api/files/browse", params={
            "path": parent, "itemsPerPage": 250, "filterHiddenFiles": "false",
            **({"next": next_page} if next_page else {})}).json())
        if not any(item.get("id") == path for item in children):
            return None
    item = client.request("GET", "/api/files/retrieve", params={"id": path, "includePermissions": "true"}).json()
    if (item.get("id") != path or item.get("owner", {}).get("project") != client.settings.project
            or item.get("status", {}).get("type") != "DIRECTORY"
            or item.get("specification", {}).get("collection") != path.split("/")[1]
            or item.get("specification", {}).get("product", {}).get("provider") != provider
            or not {"EDIT", "ADMIN"}.intersection(item.get("permissions", {}).get("myself", []))):
        raise ValueError("Storage must be a writable directory owned by this project on the selected provider")
    return item


def _link(client, request: dict, *, allow_bound: bool = False) -> dict:
    from urllib.parse import urlsplit
    from ucloud_workflow.resources import product_support, scoped_resource
    item = scoped_resource(client, "ingresses", request["link_id"])
    spec, status = item.get("specification", {}), item.get("status", {})
    if (item.get("owner", {}).get("project") != client.settings.project
            or spec.get("domain") != urlsplit(request["public_base_url"]).hostname
            or spec.get("product", {}).get("provider") != request["cpu_product"]["provider"]
            or status.get("state") != "READY" or not isinstance(status.get("boundTo"), list)
            or (status["boundTo"] and not allow_bound)):
        raise ValueError("Bootstrap Link scope/domain/provider/readiness/bindings do not match")
    product_support(client, "ingresses", spec["product"])
    return item


def _compute_support(client, product: dict, *, web: bool = False) -> None:
    from ucloud_workflow.resources import find_product_support
    catalog = client.retrieve_compute_products()
    support = find_product_support(catalog, product)
    if product["category"].startswith("cpu-"):
        for item in catalog["productsByProvider"][product["provider"]]:
            if (item.get("support") or {}).get("product") == product and (item.get("product") or {}).get("gpu"):
                raise ValueError("Bootstrap CPU product unexpectedly advertises a GPU")
    backend = support.get("docker") or {}
    if backend.get("enabled") is not True or (web and backend.get("web") is not True):
        raise ValueError("Selected product does not advertise the required Docker/web support")


def seeds(request: dict, storage: str) -> tuple[dict, dict]:
    from ucloud_workflow.jobs import build_job_specification
    base = {"product": request["cpu_product"], "replicas": 1, "parameters": {},
            "resources": [{"type": "file", "path": storage, "readOnly": False}]}
    preparation = build_job_specification({**base, "application": {"name": "coder-python", "version": "1.89.1"}},
                                          hours=1, ssh_enabled=True, name="vllm-preparation")
    serving = build_job_specification({**deepcopy(base), "application": {"name": "nginx", "version": "1.31.2"}},
                                      hours=1, ssh_enabled=False, name="vllm-serving")
    serving["parameters"] = {name: {"type": "file", "path": storage + "/" + filename, "readOnly": True}
                             for name, filename in (("configFile", "nginx.conf"), ("initScript", "init_vllm.sh"))}
    serving["resources"].append({"type": "ingress", "id": request["link_id"]})
    # The serving seed is never submitted. hosting_job_specification replaces its
    # product/duration with the reviewed model profile at actual deployment.
    return preparation, serving


def plan_bootstrap(client, value: dict) -> dict:
    require_hosting_adapter()
    from ucloud_workflow.ssh_keys import check_ssh_key
    request = _request(value)
    scope = _scope(client)
    if request["project"] != scope["project"]:
        raise ValueError("Bootstrap project must match UCLOUD_PROJECT")
    cpu = request["cpu_product"]
    directory(client, request["storage_parent"], cpu["provider"])
    namespace = request["storage_parent"] + "/" + request["namespace"]
    if directory(client, namespace, cpu["provider"], missing=True) is not None:
        raise ValueError("Namespace already exists; choose a fresh directory or resume its exact journal")
    _compute_support(client, cpu)
    _link(client, request)
    registered = check_ssh_key(client, client.settings, Path(request["ssh_public_key"]))
    if registered["state"] != "MATCHED":
        raise ValueError("Register the selected public key first using the separate resource setup workflow")
    contracts = [application_contract(client, ref) for ref in ({"name": "coder-python", "version": "1.89.1"},
                                                              {"name": "nginx", "version": "1.31.2"})]
    reviewed = json.loads(files("ucloud_vllm_agent").joinpath("data/bootstrap_applications.json").read_text())
    data = {"schema": "ucloud.vllm.bootstrap_plan.v1", "scope": scope, "request": request,
            "namespace_path": namespace, "storage_path": namespace + "/vllm", "contracts": contracts,
            "application_review": {k: reviewed[k] for k in ("api_source_commit", "reviewed_at")},
            "public_key_fingerprints": sorted({item["fingerprint"] for item in registered["matches"]}),
            "payload_sha256": {name: hashlib.sha256(content).hexdigest() for name, content in _payload_bytes().items()},
            "cpu_hours": 1, "gpu_jobs": 0, "job_submitted": False,
            "effect": "Create a fresh namespace/vllm directory and one bounded CPU upload job. Secrets are a separate explicit action; GPU deployment remains separate."}
    return {**data, "digest": _digest(data)}


def _verify_digest(data: dict, schema: str) -> None:
    if data.get("schema") != schema or data.get("digest") != _digest({k: v for k, v in data.items() if k != "digest"}):
        raise ValueError("Unsupported or changed bootstrap artifact")


def read_bootstrap(path: Path) -> dict:
    data = load(path)
    _verify_digest(data, "ucloud.vllm.bootstrap_spec.v1")
    request = _request(data["request"])
    storage = request["storage_parent"] + "/" + request["namespace"] + "/vllm"
    preparation, serving = seeds(request, storage)
    reviewed = json.loads(files("ucloud_vllm_agent").joinpath("data/bootstrap_applications.json").read_text())
    if (data["storage_path"] != storage or data["preparation"] != preparation or data["serving"] != serving
            or data["contracts"] != reviewed["applications"]
            or data.get("application_review") != {k: reviewed[k] for k in ("api_source_commit", "reviewed_at")}
            or not data.get("credentials_verified_at")):
        raise ValueError("Bootstrap specifications do not match their reviewed request")
    return data


def validate_bootstrap(client, data: dict, *, profile: dict | None = None) -> tuple[dict, dict]:
    _verify_digest(data, "ucloud.vllm.bootstrap_spec.v1")
    if data["scope"] != _scope(client):
        raise ValueError("Bootstrap server/project differs from this workspace")
    request = _request(data["request"])
    directory(client, data["storage_path"], request["cpu_product"]["provider"])
    _link(client, request, allow_bound=True)
    contracts = [application_contract(client, contract["application"]) for contract in data["contracts"]]
    if contracts != data["contracts"]:
        raise ValueError("Bootstrap application provenance changed")
    _compute_support(client, request["cpu_product"])
    if profile:
        if profile["request"]["public_base_url"] != request["public_base_url"]:
            raise ValueError("Hosting URL differs from the selected bootstrap namespace")
        if profile["machine"]["product"]["provider"] != request["cpu_product"]["provider"]:
            raise ValueError("Bootstrap storage/Link and hosting product providers differ")
        _compute_support(client, profile["machine"]["product"], web=True)
    return deepcopy(data["preparation"]), deepcopy(data["serving"])


def _payload_bytes() -> dict[str, bytes]:
    assets = {name: files("ucloud_vllm_agent").joinpath("data/ucloud-workspace/" + name).read_text(encoding="utf-8").replace("\r\n", "\n").encode()
              for name in ASSETS}
    manifest = {name: hashlib.sha256(value).hexdigest() for name, value in assets.items()}
    return {**assets, "manifest.json": (json.dumps(manifest, sort_keys=True) + "\n").encode(),
            **{name: Path(__file__).with_name(name).read_text(encoding="utf-8").replace("\r\n", "\n").encode()
               for name in ("remote.py", "remote_bootstrap.py")}}


def _journal(client, root: Path) -> Journal:
    journal = Journal(root)
    if journal.data.get("workflow") != "ucloud.vllm.bootstrap_state.v1":
        raise ValueError("No bootstrap ownership journal in the selected directory")
    _verify_digest(journal.data["bootstrap_plan"], "ucloud.vllm.bootstrap_plan.v1")
    if journal.data["bootstrap_plan"]["scope"] != _scope(client):
        raise ValueError("Bootstrap journal belongs to a different server/project")
    return journal


def _report(journal: Journal) -> dict:
    return {"schema": "ucloud.vllm.bootstrap_report.v1", "state": journal.data.get("state"),
            "path": str(journal.root), "scope": journal.data["bootstrap_plan"]["scope"],
            "storage_path": journal.data["bootstrap_plan"]["storage_path"],
            "folders": journal.data.get("folders", {}), "cpu_job_id": journal.data.get("bootstrap_job_id"),
            "cpu_hours": 1, "cpu_expires_at": journal.data.get("cpu_expires_at"), "gpu_jobs": 0,
            "bootstrap_file": str(journal.root / "bootstrap.json") if (journal.root / "bootstrap.json").is_file() else None,
            "assets_ready": journal.data.get("assets_ready", False),
            "credentials_verified": bool(journal.data.get("credentials_verified_at")),
            "deployment_ready": False, "settings_written": False}


def _create_folder(client, journal: Journal, path: str) -> None:
    from ucloud_workflow.client import UCloudAPIError
    folders = journal.data.get("folders", {})
    entry = folders.get(path)
    provider = journal.data["bootstrap_plan"]["request"]["cpu_product"]["provider"]
    if entry:
        if entry["state"] != "known":
            raise ValueError("Folder creation outcome is unresolved; do not retry or infer ownership")
        directory(client, path, provider)
        return
    folders[path] = {"state": "pending", "ownership": "uncertain"}
    journal.update("folder_creating", folders=folders)
    try:
        response = client.request("POST", "/api/files/folder", json={"items": [{"id": path, "conflictPolicy": "REJECT"}]}).json()
        if response.get("responses") != [{}]:
            raise ValueError("Folder acknowledgement is malformed")
    except BaseException as error:
        rejected = isinstance(error, UCloudAPIError) and error.status_code is not None and 400 <= error.status_code < 500 and error.status_code != 408
        folders[path].update(state="rejected" if rejected else "unknown", ownership="none" if rejected else "uncertain")
        journal.update("folder_rejected" if rejected else "folder_outcome_unknown", folders=folders)
        raise SetupOutcomeUnknownError("Folder request needs inspection; preserve its journal and do not repeat it") from None
    folders[path].update(state="known", ownership="created")
    journal.update("folder_created", folders=folders)
    directory(client, path, provider)


def _transport(client, journal: Journal):
    from .lifecycle import _owned_job, wait_job
    from .transport import PreparationSSH
    job = _owned_job(client, journal, "bootstrap")
    job = wait_job(client, job["id"], ssh=True)
    journal.update(cpu_expires_at=job.get("status", {}).get("expiresAt"))
    return PreparationSSH(client.settings, job, journal.root)


def apply_bootstrap(client, plan: dict, root: Path, *, yes: bool = False) -> dict:
    require_hosting_adapter()
    _verify_digest(plan, "ucloud.vllm.bootstrap_plan.v1")
    if plan["scope"] != _scope(client):
        raise ValueError("Bootstrap plan belongs to another server/project")
    if not yes:
        return {"state": "bootstrap_preview", "plan": plan, "job_submitted": False}
    payload = _payload_bytes()
    if {name: hashlib.sha256(value).hexdigest() for name, value in payload.items()} != plan["payload_sha256"]:
        raise ValueError("Bootstrap helper/asset version changed; resume with the originally reviewed provider version")
    from .lifecycle import _owned_job, job_state, TERMINAL
    from .remote_bootstrap import STAGE_PROGRAM
    root = root.resolve()
    with operation_lock(LOCK):
        pointer = load(CONTROL)
        if pointer.get("path") and Path(pointer["path"]).resolve() != root:
            old = _journal(client, Path(pointer["path"]))
            if old.data.get("state") not in {"bootstrap_ready", "bootstrap_released"}:
                raise ValueError("An existing bootstrap is unresolved; use its exact journal first")
        journal = Journal(root)
        if journal.data:
            journal = _journal(client, root)
            if journal.data["bootstrap_plan"] != plan:
                raise ValueError("Bootstrap journal belongs to a different plan")
            if journal.data.get("state") == "bootstrap_released":
                raise ValueError("Bootstrap was explicitly released; review a new namespace/plan")
        else:
            if root.exists() and any(root.iterdir()):
                raise ValueError("Use a new empty bootstrap state directory")
            if plan_bootstrap(client, plan["request"]) != plan:
                raise ValueError("Bootstrap discovery changed; generate and review a new plan")
            journal.update("bootstrap_planned", workflow="ucloud.vllm.bootstrap_state.v1", bootstrap_plan=plan, owner=uuid4().hex)
        save(CONTROL, {"path": str(root)})
        if (root / "bootstrap.json").is_file():
            read_bootstrap(root / "bootstrap.json")
            return _report(journal)
        if not token_status(1)["supports_allocation"]:
            raise ValueError("Token does not cover the bounded CPU allocation plus safety margin")
        request = plan["request"]
        directory(client, request["storage_parent"], request["cpu_product"]["provider"])
        _link(client, request)
        for contract in plan["contracts"]:
            application_contract(client, contract["application"])
        _compute_support(client, request["cpu_product"])
        for path in (plan["namespace_path"], plan["storage_path"]):
            _create_folder(client, journal, path)
        if journal.data.get("bootstrap_submission") in {"pending", "unknown"}:
            raise ValueError("CPU submission outcome is unknown; reconcile the exact job before resuming")
        if journal.data.get("bootstrap_job_id"):
            job = _owned_job(client, journal, "bootstrap")
            if job_state(job) in TERMINAL:
                history = [*journal.data.get("cpu_history", []), {"id": job["id"], "state": job_state(job), "name": journal.data.get("bootstrap_submission_name")}]
                journal.update("bootstrap_cpu_retry", cpu_history=history, bootstrap_job_id=None, bootstrap_submission=None,
                               bootstrap_submission_name=None, assets_ready=False, credentials_verified_at=None)
        preparation, _ = seeds(request, plan["storage_path"])
        preparation["name"] = "vllm-bootstrap-" + journal.data["owner"][:12] + "-" + str(len(journal.data.get("cpu_history", [])) + 1)
        try:
            journal.submitted("bootstrap", client, preparation)
        except RuntimeError:
            raise SetupOutcomeUnknownError("CPU submission outcome is unknown; preserve the journal and reconcile the exact job before resuming") from None
        transport = _transport(client, journal)
        stage = "/work/vllm/.bootstrap/" + journal.data["owner"]
        established = json.loads(transport.run(["python3", "-c", STAGE_PROGRAM, journal.data["owner"]]))
        if established.get("stage") != stage:
            raise ValueError("Unexpected remote bootstrap staging path")
        local = root / "payload"
        local.mkdir(exist_ok=True)
        for name, content in payload.items():
            (local / name).write_bytes(content)
            transport.upload(local / name, stage + "/" + name)
        result = json.loads(transport.run(["python3", stage + "/remote_bootstrap.py", "install", "--owner", journal.data["owner"]]))
        manifest = json.loads(payload["manifest.json"])
        if result.get("state") != "assets_ready" or result.get("files") != manifest:
            raise ValueError("Remote bootstrap asset verification failed; the owned CPU job is preserved")
        journal.update("assets_ready", assets_ready=True, asset_manifest=manifest, mount_type=result.get("mount_type"))
        return _report(journal)


def provision_bootstrap_credentials(client, root: Path, *, yes: bool = False, include_hf_token: bool = False) -> dict:
    with operation_lock(LOCK):
        journal = _journal(client, root)
        if not journal.data.get("assets_ready") or (journal.root / "bootstrap.json").is_file():
            raise ValueError("Credential provisioning requires an unfinished bootstrap with verified assets")
        if not yes:
            return {"state": "credential_preview", "file": "/work/vllm/.env", "cpu_job_id": journal.data.get("bootstrap_job_id"),
                    "keys": ["VLLM_API_KEY", *(["HF_TOKEN"] if include_hf_token else [])], "settings_written": False}
        if journal.data.get("credential_provisioning") in {"pending", "unknown"}:
            raise ValueError("Credential outcome is unknown; use bootstrap-finish to verify, never resubmit or overwrite")
        if journal.data.get("credential_provisioning") in {"known", "verified"}:
            return _report(journal)
        values = {"VLLM_API_KEY": os.getenv("VLLM_API_KEY", ""), "HF_TOKEN": os.getenv("HF_TOKEN", "") if include_hf_token else ""}
        if not values["VLLM_API_KEY"] or (include_hf_token and not values["HF_TOKEN"]):
            raise ValueError("Configure the selected serving/HF credentials locally before provisioning")
        if any(any(c in v for c in "\r\n\x00\"'") for v in values.values()):
            raise ValueError("Selected credentials must be single-line values without quotes")
        transport = _transport(client, journal)
        helper = "/work/vllm/.bootstrap/" + journal.data["owner"] + "/remote_bootstrap.py"
        journal.update("credential_provisioning", credential_provisioning="pending")
        try:
            result = json.loads(transport.run(["python3", helper, "provision-credentials", "--owner", journal.data["owner"]], input=json.dumps(values)))
            if result.get("state") != "credentials_provisioned":
                raise ValueError("Credential provisioning was not confirmed")
        except BaseException:
            journal.update("credential_outcome_unknown", credential_provisioning="unknown")
            raise SetupOutcomeUnknownError("Credential creation needs verification; do not overwrite or resubmit it") from None
        journal.update("credentials_provisioned", credential_provisioning="known")
        return _report(journal)


def finish_bootstrap(client, root: Path, *, yes: bool = False) -> dict:
    from .lifecycle import _stop_job
    with operation_lock(LOCK):
        journal = _journal(client, root)
        if (journal.root / "bootstrap.json").is_file():
            read_bootstrap(journal.root / "bootstrap.json")
            return _report(journal)
        if not journal.data.get("assets_ready"):
            raise ValueError("Apply the bootstrap plan and verify its assets first")
        if not yes:
            return {"state": "finish_preview", "cpu_job_id": journal.data.get("bootstrap_job_id"),
                    "effect": "Verify remote credentials and release only this bootstrap CPU job; publish an inert application specification."}
        if not journal.data.get("credentials_verified_at"):
            key = os.getenv("VLLM_API_KEY")
            if not key:
                raise ValueError("Local VLLM_API_KEY is required for bootstrap verification")
            transport = _transport(client, journal)
            helper = "/work/vllm/.bootstrap/" + journal.data["owner"] + "/remote_bootstrap.py"
            result = json.loads(transport.run(["python3", helper, "verify-credentials", "--owner", journal.data["owner"],
                                                "--key-sha256", hashlib.sha256(key.encode()).hexdigest()]))
            if result.get("state") != "credentials_verified" or result.get("key_matches") is not True:
                raise ValueError("Remote credentials are not verified; the owned CPU job is preserved")
            journal.update(credentials_verified_at=datetime.now(timezone.utc).isoformat(), credential_provisioning="verified")
        _stop_job(client, journal, "bootstrap")
        plan = journal.data["bootstrap_plan"]
        preparation, serving = seeds(plan["request"], plan["storage_path"])
        data = {"schema": "ucloud.vllm.bootstrap_spec.v1", "scope": plan["scope"], "request": plan["request"],
                "storage_path": plan["storage_path"], "contracts": plan["contracts"], "preparation": preparation, "serving": serving,
                "application_review": plan["application_review"],
                "asset_manifest": journal.data["asset_manifest"], "credentials_verified_at": journal.data["credentials_verified_at"],
                "bootstrap_job_id": journal.data["bootstrap_job_id"], "source_plan_digest": plan["digest"]}
        save(journal.root / "bootstrap.json", {**data, "digest": _digest(data)})
        journal.update("bootstrap_ready")
        return _report(journal)


def release_bootstrap(client, root: Path, *, yes: bool = False) -> dict:
    from .lifecycle import _stop_job
    with operation_lock(LOCK):
        journal = _journal(client, root)
        if not yes:
            return {"state": "release_preview", "cpu_job_id": journal.data.get("bootstrap_job_id"), "storage_preserved": True}
        if journal.data.get("bootstrap_submission") in {"pending", "unknown"} or any(e["state"] in {"pending", "unknown"} for e in journal.data.get("folders", {}).values()):
            raise ValueError("Unknown bootstrap outcome; reconcile before release")
        if journal.data.get("bootstrap_job_id"):
            _stop_job(client, journal, "bootstrap")
        journal.update("bootstrap_ready" if (journal.root / "bootstrap.json").exists() else "bootstrap_released")
        return _report(journal)


def reconcile_bootstrap(client, root: Path, job_id: str) -> dict:
    with operation_lock(LOCK):
        journal = _journal(client, root)
        if journal.data.get("bootstrap_submission") not in {"pending", "unknown"} or journal.data.get("bootstrap_job_id"):
            raise ValueError("No unknown bootstrap CPU submission to reconcile")
        job = client.retrieve_job(job_id, include_updates=True)
        expected, _ = seeds(journal.data["bootstrap_plan"]["request"], journal.data["bootstrap_plan"]["storage_path"])
        expected["name"] = journal.data["bootstrap_submission_name"]
        spec = job.get("specification", {})
        if job.get("owner", {}).get("project") != client.settings.project or any(spec.get(k) != v for k, v in expected.items()):
            raise ValueError("CPU job does not match the exact recorded bootstrap submission")
        journal.update("bootstrap_reconciled", bootstrap_job_id=job_id, bootstrap_submission="known")
        return _report(journal)


def status_bootstrap(client, root: Path) -> dict:
    journal = _journal(client, root)
    result = _report(journal)
    if journal.data.get("bootstrap_job_id"):
        from .lifecycle import _owned_job, job_state
        result["cpu_job_state"] = job_state(_owned_job(client, journal, "bootstrap"))
    return result
