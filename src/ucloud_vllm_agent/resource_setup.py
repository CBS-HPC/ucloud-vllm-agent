"""Explicit persistent Link/key setup; no jobs, mounts or credentials are created."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from .state import load, operation_lock, save
from .ucloud_access import require_hosting_adapter

CONTROL = Path("run/resource-setup-current.json")
LOCK = Path("run/resource-setup.lock")
UNRESOLVED = {"creating", "unknown", "deleting", "delete_unknown"}


class SetupOutcomeUnknownError(RuntimeError):
    """A sanitized instruction to preserve state and reconcile instead of retry."""


def _digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _scope(client) -> dict:
    # A project name is insufficient ownership evidence for persistent resources.
    try:
        UUID(client.settings.project)
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Resource setup requires the exact UCLOUD_PROJECT UUID") from None
    server = urlsplit(client.settings.server)
    if server.scheme != "https" or not server.hostname or server.username or server.password or server.query or server.fragment:
        raise ValueError("Resource setup requires an HTTPS UCloud server without embedded credentials")
    return {"server": client.settings.server.rstrip("/"), "project": client.settings.project}


def _link(client, identifier: str, expected: dict, *, ready: bool = True) -> dict:
    from ucloud_workflow.resources import scoped_resource
    item = scoped_resource(client, "ingresses", identifier)
    spec, status = item.get("specification", {}), item.get("status", {})
    if (item.get("owner", {}).get("project") != client.settings.project
            or spec.get("domain") != expected["domain"] or spec.get("product") != expected["product"]):
        raise ValueError("Link does not match the selected project, hostname and product")
    if not isinstance(status, dict) or not isinstance(status.get("boundTo"), list) or status["boundTo"]:
        raise ValueError("Link bindings are unknown or occupied; no route will be replaced")
    if ready and status.get("state") != "READY":
        raise ValueError("Link is not READY")
    return item


def _keys(client, fingerprint: str) -> list[dict]:
    from ucloud_workflow.ssh_keys import list_ssh_keys, ssh_key_summary
    return [summary for item in list_ssh_keys(client)
            if (summary := ssh_key_summary(item))["fingerprint"] == fingerprint]


def plan_setup(client, request: dict) -> dict:
    """Read-only discovery. Public-key bytes never enter the returned plan."""
    require_hosting_adapter()
    from ucloud_workflow.resources import list_resources, prepare_resource
    from ucloud_workflow.ssh_keys import key_fingerprint, read_public_key
    if (not isinstance(request, dict) or set(request) != {"schema", "project", "link", "ssh_public_key"}
            or request["schema"] != "ucloud.vllm.resource_setup.v1"):
        raise ValueError("Unsupported resource setup request schema or fields")
    scope = _scope(client)
    if request["project"] != scope["project"]:
        raise ValueError("Setup request project must match UCLOUD_PROJECT")
    normalized, actions = deepcopy(request), {}
    link = normalized["link"]
    if link is not None:
        if not isinstance(link, dict) or set(link) != {"domain", "product", "existing_id"}:
            raise ValueError("Link selection requires domain, product and existing_id (or null)")
        if not isinstance(link["product"], dict) or set(link["product"]) != {"id", "category", "provider"}:
            raise ValueError("Link product requires exact id, category and provider fields")
        if link["existing_id"] is not None and (not isinstance(link["existing_id"], str) or not link["existing_id"].strip()):
            raise ValueError("existing_id must be a nonempty Link ID or null")
        prepared = prepare_resource(client, "ingresses", {"domain": link["domain"], "product": link["product"]})
        link.update(domain=prepared["domain"], product=prepared["product"])
        matches = [item for item in list_resources(client, "ingresses")
                   if item.get("specification", {}).get("domain") == link["domain"]]
        if len(matches) > 1:
            raise ValueError("Ambiguous hostname discovery; resolve existing Links first")
        identifier = link["existing_id"] or (str(matches[0]["id"]) if matches else None)
        if identifier:
            _link(client, identifier, link)
        actions["link"] = {"action": "reuse" if identifier else "create", "id": identifier}
    key = normalized["ssh_public_key"]
    if key is not None:
        if (not isinstance(key, dict) or set(key) != {"path", "title", "register_if_missing"}
                or not isinstance(key["path"], str) or not isinstance(key["title"], str) or not key["title"].strip()
                or type(key["register_if_missing"]) is not bool):
            raise ValueError("SSH selection requires a .pub path, title and boolean register_if_missing")
        path = Path(key["path"]).expanduser().resolve()
        fingerprint = key_fingerprint(read_public_key(path))
        key["path"] = str(path)
        matches = _keys(client, fingerprint)
        if len(matches) > 1:
            raise ValueError("Multiple registered keys match; resolve duplicate registration first")
        if not matches and not key["register_if_missing"]:
            raise ValueError("Public key is not registered; explicitly enable register_if_missing or register it manually")
        actions["ssh_key"] = {"action": "reuse" if matches else "create", "id": matches[0]["id"] if matches else None,
                              "fingerprint": fingerprint, "scope": "authenticated_account"}
    if not actions:
        raise ValueError("Select a Link or an optional SSH public key")
    result = {"schema": "ucloud.vllm.resource_plan.v1", "scope": scope, "request": normalized, "actions": actions,
              "job_submitted": False, "resources_mutated": False,
              "effect": "Apply may reserve a persistent public Link and register an account public key. No jobs or secret files are created."}
    return {**result, "digest": _digest(result)}


def _validate_plan(client, plan: dict) -> None:
    require_hosting_adapter()
    unsigned = {key: value for key, value in plan.items() if key != "digest"}
    if plan.get("schema") != "ucloud.vllm.resource_plan.v1" or plan.get("digest") != _digest(unsigned):
        raise ValueError("Invalid setup plan; regenerate with setup-plan")
    if plan.get("scope") != _scope(client):
        raise ValueError("Setup plan server/project differs from the configured target")


def _read_state(client, root: Path) -> dict:
    data = load(root / "setup.json")
    if data.get("schema") != "ucloud.vllm.resource_state.v1":
        raise ValueError("No supported setup journal in the selected directory")
    _validate_plan(client, data["plan"])
    return data


def _save(root: Path, data: dict) -> None:
    save(root / "setup.json", data)


def _report(root: Path, data: dict) -> dict:
    link = data["plan"]["request"]["link"]
    return {"schema": "ucloud.vllm.resource_report.v1", "state": data["state"], "path": str(root.resolve()),
            "scope": data["plan"]["scope"], "resources": data["resources"], "job_submitted": False,
            "deployment_ready": False, "public_endpoint_verified": False,
            "suggested_public_base_url": "https://" + link["domain"] + "/v1" if link else None,
            "settings_written": False}


def _verify(client, plan: dict, kind: str, identifier: str, *, ready: bool = True) -> None:
    if kind == "link":
        _link(client, identifier, plan["request"]["link"], ready=ready)
    elif not any(str(item["id"]) == identifier for item in _keys(client, plan["actions"][kind]["fingerprint"])):
        raise ValueError("Recorded key ID/fingerprint is not registered to this account")


def apply_setup(client, plan: dict, root: Path, *, yes: bool = False) -> dict:
    _validate_plan(client, plan)
    if not yes:
        return {"state": "preview", "plan": plan, "resources_mutated": False, "job_submitted": False}
    from ucloud_workflow.resources import create_resource, wait_for_resource
    from ucloud_workflow.ssh_keys import key_fingerprint, read_public_key, register_public_key
    root = root.resolve()
    with operation_lock(LOCK):
        pointer = load(CONTROL)
        if pointer.get("path") and Path(pointer["path"]).resolve() != root:
            previous = _read_state(client, Path(pointer["path"]))
            if any(entry["state"] in UNRESOLVED for entry in previous["resources"].values()):
                raise ValueError("Another setup has an uncertain outcome; reconcile its journal first")
        data = load(root / "setup.json")
        if data:
            data = _read_state(client, root)
            if data["plan"] != plan:
                raise ValueError("Setup journal belongs to a different plan")
        else:
            if plan_setup(client, plan["request"]) != plan:
                raise ValueError("Setup discovery changed; generate and review a new plan")
            data = {"schema": "ucloud.vllm.resource_state.v1", "state": "applying", "plan": plan, "resources": {}}
            _save(root, data)
        save(CONTROL, {"path": str(root)})
        if any(entry["state"] in UNRESOLVED for entry in data["resources"].values()):
            raise ValueError("Setup outcome is uncertain; use setup-reconcile before another apply")
        for kind, action in plan["actions"].items():
            entry = data["resources"].get(kind)
            if entry:
                if entry["state"] != "known":
                    raise ValueError("This setup was rejected or cleaned up; review a new plan")
                _verify(client, plan, kind, entry["id"], ready=False)
            elif action["action"] == "reuse":
                _verify(client, plan, kind, str(action["id"]))
                entry = {"id": str(action["id"]), "ownership": "reused", "state": "known"}
                data["resources"][kind] = entry
                _save(root, data)
            else:
                public_key = None
                if kind == "ssh_key":
                    key = plan["request"]["ssh_public_key"]
                    public_key = read_public_key(Path(key["path"]))
                    if key_fingerprint(public_key) != action["fingerprint"]:
                        raise ValueError("Selected public-key file changed after planning")
                entry = {"id": None, "ownership": "uncertain", "state": "creating"}
                data["resources"][kind] = entry
                _save(root, data)  # Persist intent before upstream's POST/receipt.
                try:
                    operations = root / "operations" / kind
                    if kind == "link":
                        link = plan["request"]["link"]
                        result = create_resource(client, "ingresses", {"domain": link["domain"], "product": link["product"]},
                                                 operation_dir=operations)
                    else:
                        result = register_public_key(client, key["title"], public_key, operation_dir=operations)
                    entry.update(id=str(result["id"]), ownership="reused" if result.get("already_registered") else "created",
                                 state="known", operation_record=result.get("operation_record"))
                    _save(root, data)
                except BaseException:
                    entry["state"] = "unknown"
                    data["state"] = "uncertain"
                    _save(root, data)
                    raise SetupOutcomeUnknownError("Setup creation outcome needs reconciliation; no automatic retry") from None
            if kind == "link":
                wait_for_resource(client, "ingresses", entry["id"], timeout_seconds=180)
            _verify(client, plan, kind, entry["id"])
        data["state"] = "resources_ready"
        _save(root, data)
        return _report(root, data)


def _receipt(root: Path, kind: str, path: Path, scope: dict) -> dict:
    folder = (root / "operations" / kind).resolve()
    if not path.resolve().is_relative_to(folder):
        raise ValueError("Creation receipt must be inside this setup's operation directory")
    receipt = load(path)
    if (receipt.get("operation") != "create" or receipt.get("namespace") != ("ingresses" if kind == "link" else "ssh")
            or receipt.get("project") != (scope["project"] if kind == "link" else None)):
        raise ValueError("Creation receipt has different ownership scope")
    return receipt


def reconcile_setup(client, root: Path) -> dict:
    """Recover confirmed receipts only; names/fingerprints never imply ownership."""
    root = root.resolve()
    with operation_lock(LOCK):
        data = _read_state(client, root)
        if not any(entry["state"] in UNRESOLVED for entry in data["resources"].values()):
            return _report(root, data)
        for kind, entry in data["resources"].items():
            if entry["state"] not in {"creating", "unknown"}:
                continue
            paths = list((root / "operations" / kind).glob("*.json"))
            if len(paths) != 1:
                continue  # No POST retry or adoption from a matching name.
            receipt = _receipt(root, kind, paths[0], data["plan"]["scope"])
            if receipt["outcome"] == "created" and receipt.get("resource_id"):
                identifier = str(receipt["resource_id"])
                _verify(client, data["plan"], kind, identifier, ready=False)
                entry.update(id=identifier, state="known", ownership="created", operation_record=str(paths[0].resolve()))
            elif receipt["outcome"] == "failed":
                entry.update(state="rejected", ownership="none", operation_record=str(paths[0].resolve()))
        data["state"] = "uncertain" if any(e["state"] in UNRESOLVED for e in data["resources"].values()) else "reconciled"
        _save(root, data)
        return _report(root, data)


def cleanup_setup(client, root: Path, kind: str, *, yes: bool = False) -> dict:
    from ucloud_workflow.resources import delete_resource
    from ucloud_workflow.ssh_keys import delete_public_key
    if kind not in {"link", "ssh_key"}:
        raise ValueError("Select exactly link or ssh_key for cleanup")
    root = root.resolve()
    with operation_lock(LOCK):
        data = _read_state(client, root)
        if any(entry["state"] in UNRESOLVED for entry in data["resources"].values()):
            raise ValueError("Uncertain setup/deletion outcome; reconcile before cleanup")
        entry = data["resources"].get(kind)
        if not entry or entry["ownership"] != "created":
            raise ValueError("Cleanup protects reused resources and keys")
        if entry["state"] == "deleted":
            return _report(root, data)
        receipt = _receipt(root, kind, Path(entry["operation_record"]), data["plan"]["scope"])
        if receipt.get("outcome") != "created" or str(receipt.get("resource_id")) != entry["id"]:
            raise ValueError("Cleanup requires a confirmed creation receipt for the exact ID")
        _verify(client, data["plan"], kind, entry["id"])
        if not yes:
            return {"state": "cleanup_preview", "kind": kind, "id": entry["id"], "job_submitted": False,
                    "resources_mutated": False, "account_scoped": kind == "ssh_key", "scope": data["plan"]["scope"],
                    "fingerprint": data["plan"]["actions"][kind].get("fingerprint"),
                    "domain": data["plan"]["request"]["link"]["domain"] if kind == "link" else None}
        entry["state"] = "deleting"
        _save(root, data)
        try:
            if kind == "link":
                delete_resource(client, "ingresses", entry["id"])
            else:
                delete_public_key(client, entry["id"])
        except BaseException:
            entry["state"] = "delete_unknown"
            data["state"] = "uncertain"
            _save(root, data)
            raise SetupOutcomeUnknownError("Deletion outcome is uncertain; inspect the exact resource before further action") from None
        entry["state"] = "deleted"
        data["state"] = "cleanup_recorded"
        _save(root, data)
        return _report(root, data)


def setup_status(client, root: Path) -> dict:
    return _report(root, _read_state(client, root))
