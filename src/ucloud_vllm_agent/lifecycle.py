"""Template-based hosting, resumable journals and exact owned lifecycle operations."""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import sys
import time
from pathlib import Path, PurePosixPath

from .checks import check_endpoint
from .config import load_json
from .hosting import hosting_job_specification, prepare_profile, validate_profile
from .huggingface import inspect_model
from .state import Journal, load, save, operation_lock
from .transport import PreparationSSH, ServingShell, register_web_route
from .ucloud_access import token_status

TERMINAL = {"SUCCESS", "FAILURE", "EXPIRED", "CANCELLED", "EXIT"}
CONTROL_ROOT = Path("run")


def job_state(job: dict) -> str:
    from ucloud_workflow.jobs import latest_update_state
    return latest_update_state(job)


def wait_job(client, job_id: str, *, ssh: bool = False, timeout: float = 600) -> dict:
    from ucloud_workflow.jobs import extract_ssh_command
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.retrieve_job(job_id, include_updates=True)
        if job_state(job) == "RUNNING" and (not ssh or extract_ssh_command(job)):
            return job
        if job_state(job) in TERMINAL:
            raise ValueError("The recorded job ended before it became ready")
        time.sleep(5)
    raise ValueError("The recorded job did not become ready within the bounded wait")


def _owned_job(client, journal: Journal, kind: str = "hosting") -> dict:
    job_id = journal.data.get(kind + "_job_id")
    if not job_id:
        raise ValueError("No known job ID; resolve the journal's submission outcome first")
    job = client.retrieve_job(job_id, include_updates=True)
    expected = journal.data.get(kind + "_submission_name")
    if expected and job.get("specification", {}).get("name") != expected:
        raise ValueError("Recorded job does not match this deployment's ownership evidence")
    if job.get("owner", {}).get("project") != client.settings.project:
        raise ValueError("Recorded job belongs to another project")
    return job


def adopt_legacy(root: Path, client) -> Journal:
    journal = Journal(root)
    if not journal.data and (root / "job.json").exists():
        legacy = load_json(root / "job.json")
        if legacy.get("template_job_id") != client.settings.template_job_id:
            raise ValueError("Legacy record does not identify the configured serving template")
        job = client.retrieve_job(legacy["job_id"], include_updates=True)
        if job.get("specification", {}).get("application") != {"name": "nginx", "version": "1.31.2"}:
            raise ValueError("Legacy job is not the verified nginx application")
        if job.get("owner", {}).get("project") != client.settings.project:
            raise ValueError("Legacy hosting job belongs to another project")
        journal.update("legacy_hosting", hosting_job_id=legacy["job_id"], hosting_submission="known",
                       hosting_submission_name=job["specification"].get("name"),
                       legacy_runtime=True, public_base_url=load_json(root / "plan.json")["request"]["public_base_url"])
    return journal


def _links(template: dict) -> list[str]:
    values = [*template.get("resources", []), *template.get("parameters", {}).values()]
    return [v["id"] for v in values if isinstance(v, dict) and v.get("type") == "ingress"]


def _template_contract(client, serving: dict, preparation: dict, expected_url: str) -> None:
    from urllib.parse import urlsplit
    if not preparation.get("product", {}).get("category", "").startswith("cpu-"):
        raise ValueError("Preparation template must be a CPU product")
    folder = str(PurePosixPath(serving["parameters"]["configFile"]["path"]).parent)
    for template in (serving, preparation):
        mounts = [v.get("path") for v in template.get("resources", []) if v.get("type") == "file"]
        if folder not in mounts:
            raise ValueError("Both templates must mount the same nginx workspace folder")
    links = _links(serving)
    if not links:
        raise ValueError("Serving template must preserve an operator public link")
    host = urlsplit(expected_url).hostname
    if not any(client.request("GET", "/api/ingresses/retrieve", params={"id": link}).json()
               .get("specification", {}).get("domain") == host for link in links):
        raise ValueError("Template public-link domain differs from the configured API URL")


def _validate_template_ownership(client) -> None:
    for template_id in (client.settings.template_job_id, os.environ["UCLOUD_PREPARATION_TEMPLATE_JOB_ID"]):
        job = client.retrieve_job(template_id, include_updates=False)
        if not client.settings.project or job.get("owner", {}).get("project") != client.settings.project:
            raise ValueError("UCLOUD_PROJECT must match the project UUID owning both template jobs; no job was submitted")


def _check_bound_jobs(client, template: dict, allowed: set[str]) -> None:
    for link in _links(template):
        resource = client.request("GET", "/api/ingresses/retrieve", params={"id": link}).json()
        bound = set(resource.get("status", {}).get("boundTo", []))
        for job_id in bound - allowed:
            if job_state(client.retrieve_job(job_id, include_updates=True)) not in TERMINAL:
                raise ValueError("Public URL is occupied; specify replacement of its recorded owned deployment")


def _stop_job(client, journal: Journal, kind: str = "hosting") -> None:
    job = _owned_job(client, journal, kind)
    if job_state(job) in TERMINAL:
        journal.update(**{kind + "_job_state": job_state(job)})
        return
    journal.update(kind + "_release_requested")
    client.terminate_job(job["id"])
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        observed = client.retrieve_job(job["id"], include_updates=True)
        if job_state(observed) in TERMINAL:
            journal.update(**{kind + "_job_state": job_state(observed)})
            return
        time.sleep(3)
    raise ValueError("Termination requested; wait for the recorded job to end before another allocation")


def _manifest(root: Path) -> list[Path]:
    files = [root / name for name in ("runtime.json", "remote.py", "remote_prepare.py", "init_vllm.sh")]
    files.extend(sorted((root / "endpoint_probe").glob("*.py")))
    if (root / "pii_service.py").exists():
        files.append(root / "pii_service.py")
    manifest = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    save(root / "payload-manifest.json", manifest)
    return [*files[:4], root / "endpoint_probe", *([root / "pii_service.py"] if (root / "pii_service.py").exists() else []), root / "payload-manifest.json"]


def _prepare_remote(client, settings, journal: Journal, preparation_template: dict, runtime: dict) -> None:
    from ucloud_workflow.jobs import build_job_specification
    # Once activation finished, a released CPU clone is expected. Otherwise an
    # ended clone must be replaced, even if it finished downloading the model.
    if journal.data.get("preparation_complete") and journal.data.get("activated"):
        return
    if journal.data.get("preparation_job_id"):
        job = _owned_job(client, journal, "preparation")
        if job_state(job) in TERMINAL:
            history = [*journal.data.get("preparation_history", []), {
                "job_id": job["id"], "submission_name": journal.data.get("preparation_submission_name"),
                "state": job_state(job),
            }]
            journal.update("preparation_retry", preparation_history=history,
                           preparation_job_id=None, preparation_submission=None,
                           preparation_submission_name=None, preparation_job_state=None,
                           preparation_launched=False, preparation_complete=False, activated=False)
    if journal.data.get("preparation_complete"):
        return
    attempt = len(journal.data.get("preparation_history", [])) + 1
    spec = build_job_specification(preparation_template, hours=1, ssh_enabled=True,
                                   name="vllm-prepare-" + journal.root.name[-8:] + "-" + str(attempt))
    job_id = journal.submitted("preparation", client, spec)
    print("Waiting for CPU preparation job " + job_id, file=sys.stderr, flush=True)
    job = wait_job(client, job_id, ssh=True)
    transport = PreparationSSH(settings, job, journal.root)
    remote = runtime["remote_dir"]
    if not journal.data.get("preparation_launched"):
        transport.run(["mkdir", "-p", remote])
        for path in _manifest(journal.root):
            transport.upload(path, remote + "/" + path.name)
        verify = "import hashlib,json,sys;from pathlib import Path;r=Path(sys.argv[1]);m=json.loads((r/'payload-manifest.json').read_text());assert all(hashlib.sha256((r/p).read_bytes()).hexdigest()==h for p,h in m.items())"
        transport.run(["python3", "-c", verify, remote])
        # Never accept a result left by an expired attempt as proof of this one.
        transport.run(["python3", "-c", "from pathlib import Path;import sys;Path(sys.argv[1]).unlink(missing_ok=True)",
                       remote + "/preparation-result.json"])
        digest = hashlib.sha256(os.environ["VLLM_API_KEY"].encode()).hexdigest()
        # The journal does not persist the key or its digest. SSH carries only a
        # high-entropy key fingerprint, never the actual local credential.
        command = "cd " + shlex.quote(remote) + " && nohup " + shlex.join([
            "python3", "remote_prepare.py", "--key-sha256", digest]) + " > preparation.log 2>&1 < /dev/null &"
        journal.update("preparing_remote", preparation_launched=True)
        transport.run(["bash", "-c", command])
    deadline = time.monotonic() + 3000
    while time.monotonic() < deadline:
        output = transport.run(["python3", "-c", "from pathlib import Path;import sys;p=Path(sys.argv[1]);print(p.read_text() if p.exists() else '{}')",
                                remote + "/preparation-result.json"])
        evidence = json.loads(output)
        if evidence:
            save(journal.root / "preparation-result.json", evidence)
            if evidence.get("state") != "prepared":
                journal.update("preparation_failed")
                raise ValueError("CPU preparation failed; inspect preparation-result.json and the remote logs")
            break
        time.sleep(10)
    else:
        raise ValueError("CPU preparation is still unresolved; inspect/recover the recorded job")
    journal.update("prepared_remote", preparation_complete=True)


def _activate(client, settings, journal: Journal, runtime: dict) -> None:
    # Activation uses the existing owned CPU clone while it is still available.
    # Preparation release is delayed until after this transfer/activation stage.
    job = _owned_job(client, journal, "preparation")
    if job_state(job) != "RUNNING":
        raise ValueError("Preparation job ended before activation; recover with a new preparation stage")
    transport = PreparationSSH(settings, job, journal.root)
    transport.upload(journal.root / "init_vllm.sh", "/work/vllm/init_vllm.sh")
    transport.run(["chmod", "755", "/work/vllm/init_vllm.sh"])
    code = "import os,sys;from pathlib import Path;root=Path('/work/vllm');tmp=root/'active.next';tmp.unlink(missing_ok=True);tmp.symlink_to(sys.argv[1]);os.replace(tmp,root/'active')"
    transport.run(["python3", "-c", code, runtime["remote_dir"]])
    journal.update("activated", activated=True)


def verify_host(client, journal: Journal, runtime: dict, timeout: float = 900) -> dict:
    job = _owned_job(client, journal)
    route = register_web_route(client, job["id"], journal.data["public_base_url"])
    journal.update("waiting_for_model", web_route=route)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        from urllib.request import Request, build_opener
        from urllib.error import HTTPError, URLError
        from .checks import NoRedirects
        try:
            request = Request(journal.data["public_base_url"] + "/models", headers={"Authorization": "Bearer " + os.environ["VLLM_API_KEY"]})
            with build_opener(NoRedirects()).open(request, timeout=5) as response:
                values = json.loads(response.read(1_000_000))
            if any(m.get("id") == runtime["name"] for m in values.get("data", [])):
                break
        except (HTTPError, URLError, OSError, ValueError):
            pass
        if job_state(client.retrieve_job(job["id"], include_updates=True)) in TERMINAL:
            raise ValueError("Serving allocation ended before endpoint readiness")
        time.sleep(5)
    else:
        journal.update("readiness_failed")
        raise ValueError("Endpoint readiness timed out; the owned allocation is preserved for recovery")
    shell = ServingShell(client, job)
    helper = [str(PurePosixPath(runtime["venv_dir"]) / "bin/python"), runtime["remote_dir"] + "/remote.py"]
    internal = shell.json([*helper, "verify"], timeout=120)
    checker = check_endpoint
    if runtime.get("task") == "pii":
        from .pii_checks import check_pii_endpoint
        checker = check_pii_endpoint
    external = checker(journal.data["public_base_url"], runtime["name"])
    save(journal.root / "checks.json", external)
    save(journal.root / "checks-internal.json", internal)
    process = shell.json([*helper, "status"])
    save(journal.root / "runtime-evidence.json", process)
    measured = process.get("profile", {})
    capacity_ok = (measured.get("gpu_kv_tokens", 0) >= runtime["context_length"] * runtime["concurrency"]
                   and measured.get("max_full_context_concurrency", 0) >= runtime["concurrency"])
    if runtime.get("task") == "pii":
        capacity_ok = internal["passed"] and external["passed"]  # No retained decoder KV for this encoder.
    passed = external["passed"] and internal["passed"] and process["running"] and capacity_ok
    journal.update("endpoint_verified" if passed else "verification_failed", endpoint_verified=passed,
                   profile=process.get("profile"), runtime_capacity_verified=capacity_ok, cache=process.get("cache"),
                   expires_at=job.get("status", {}).get("expiresAt"))
    if not passed:
        raise ValueError("Endpoint verification failed; the owned allocation is preserved")
    return journal.data


def deploy(client, profile: dict | None, *, output: Path = Path("deployments"), root: Path | None = None,
           replace: Path | None = None, reviewed: bool = False, auto_size: bool = False,
           rollback: bool = False, renew_hours: int | None = None, bootstrap: Path | None = None) -> dict:
    settings = client.settings
    if not reviewed:
        raise ValueError("Deployment requires --reviewed after model/license/runtime review")
    if not os.getenv("VLLM_API_KEY"):
        raise ValueError("Local VLLM_API_KEY is required for remote-key matching and endpoint verification")
    from ucloud_workflow.jobs import template_job_specification
    with operation_lock(CONTROL_ROOT / "lifecycle.lock"):
        pointer = load(CONTROL_ROOT / "current.json")
        previous = adopt_legacy(replace.resolve(), client) if replace else None
        if renew_hours is not None:
            if not previous or isinstance(renew_hours, bool) or not isinstance(renew_hours, int) or renew_hours < 1:
                raise ValueError("Renewal requires a recorded deployment and a positive whole number of hours")
            if not previous.data.get("reviewed"):
                raise ValueError("The deployment has no recorded model/runtime review")
            profile = load_json(previous.root / "hosting-profile.json")
            profile["hours"] = renew_hours
            profile = validate_profile(profile)
            active = Journal(Path(pointer["deployment"])) if pointer.get("deployment") else None
            if active and active.data.get("renewal_of") == str(previous.root):
                root = active.root
                if load_json(root / "hosting-profile.json")["hours"] != renew_hours:
                    raise ValueError("An existing renewal has different hours; recover it or renew its deployment instead")
        if rollback:
            if not previous or not previous.data.get("replacement"):
                raise ValueError("Rollback requires a recorded replacement deployment")
            source = Journal(Path(previous.data["replacement"]))
            profile = validate_profile(load_json(source.root / "hosting-profile.json"))
            reviewed = source.data.get("reviewed", False)
            if not reviewed:
                raise ValueError("The previous deployment has no recorded model/runtime review")
            if (not previous.data.get("hosting_job_id") and source.data.get("hosting_job_id") and
                    job_state(_owned_job(client, source)) not in TERMINAL):
                raise ValueError("The previous allocation is still active; restart its recorded deployment instead of rollback")
            # Repeated rollback resumes its durable bundle; never create another
            # allocation after an acknowledgement loss or an interrupted prepare.
            active = Journal(Path(pointer["deployment"])) if pointer.get("deployment") else None
            if active and active.data.get("rollback_of") == str(previous.root):
                root = active.root
        if previous and any(previous.data.get(k + "_submission") in ("pending", "unknown")
                            for k in ("preparation", "hosting")):
            raise ValueError("Replacement submission outcome is unknown; reconcile it before replacement or rollback")
        # A recovery/replacement inherits its recorded source. An explicit file
        # cannot redirect an existing deployment to different storage or a Link.
        from .bootstrap import read_bootstrap, validate_bootstrap
        if root and previous is None:
            replacement = Journal(root).data.get("replacement")
            if replacement:
                previous = adopt_legacy(Path(replacement), client)
        blueprint = read_bootstrap(bootstrap) if bootstrap else None
        recorded = [j for j in (Journal(root) if root else None, previous,
                                source if rollback else None) if j and j.data]
        for record in recorded:
            if record.data.get("source_mode", "template") == "bootstrap":
                saved = read_bootstrap(record.root / "bootstrap.json")
                if saved["digest"] != record.data.get("bootstrap_digest"):
                    raise ValueError("Recorded bootstrap snapshot changed")
                if blueprint and blueprint["digest"] != saved["digest"]:
                    raise ValueError("Replacement/recovery must preserve its bootstrap source")
                blueprint = saved
        if blueprint and any(j.data.get("source_mode", "template") != "bootstrap" for j in recorded):
            raise ValueError("Cannot replace or recover across template and bootstrap sources")
        if blueprint is None:
            if not settings.template_job_id or not os.getenv("UCLOUD_PREPARATION_TEMPLATE_JOB_ID"):
                raise ValueError("Both explicit serving and preparation template IDs are required; bootstrap must be selected explicitly")
            _validate_template_ownership(client)
        if root is None and pointer.get("deployment"):
            active = Journal(Path(pointer["deployment"]))
            if not active.data.get("hosting_job_id") and active.data.get("state") != "released":
                raise ValueError("An existing deployment is unresolved; recover it before creating another")
            if active.data.get("hosting_job_id") and job_state(_owned_job(client, active)) not in TERMINAL:
                if not previous or previous.root != active.root:
                    raise ValueError("A hosting allocation is active; use its recorded deployment with --replace")
        if root is None:
            profile = validate_profile(profile)
            metadata = inspect_model(profile["request"]["model"], profile["request"]["revision"])
            if auto_size:
                from .catalog import sync_catalog
                from .capacity import estimate_capacity
                catalog = sync_catalog(client)
                capacity = estimate_capacity(profile["request"], metadata, catalog["machines"])
                machine = capacity.get("recommendation")
                if not machine:
                    raise ValueError("No project machine fits, or this architecture/quantization needs review")
                profile["machine"] = {key: machine[key] for key in profile["machine"]}
                profile["request"]["revision"] = metadata["revision"]
            root = prepare_profile(profile, metadata, output)
            if auto_size:
                save(root / "machine-catalog.json", catalog)
        else:
            root = root.resolve()
            profile = validate_profile(load_json(root / "hosting-profile.json"))
        runtime = load_json(root / "runtime.json")
        journal = Journal(root)
        if journal.data.get("state") in ("released", "replaced", "rolled_back", "renewed"):
            raise ValueError("This deployment was retired; use a new deployment instead of recover")
        if previous is None and journal.data.get("replacement"):
            previous = adopt_legacy(Path(journal.data["replacement"]), client)
        if blueprint:
            save(root / "bootstrap.json", blueprint)
        save(CONTROL_ROOT / "current.json", {"deployment": str(root.resolve())})
        journal.update(public_base_url=profile["request"]["public_base_url"],
                       reviewed=True,
                       source_mode="bootstrap" if blueprint else "template",
                       bootstrap_digest=blueprint["digest"] if blueprint else None,
                       serving_template_id=None if blueprint else settings.template_job_id,
                       preparation_template_id=None if blueprint else os.environ["UCLOUD_PREPARATION_TEMPLATE_JOB_ID"],
                       replacement=str(previous.root) if previous else journal.data.get("replacement"))
        if rollback:
            journal.update(rollback_of=str(previous.root), restored_from=str(source.root))
        if renew_hours is not None:
            journal.update(renewal_of=str(previous.root))
        if not token_status(max(profile["hours"], 1))["supports_allocation"]:
            raise ValueError("Configured token does not cover the requested allocation")
        if blueprint:
            prep, template = validate_bootstrap(client, blueprint, profile=profile)
        else:
            template = template_job_specification(client, template_job_id=settings.template_job_id)
            prep = template_job_specification(client, template_job_id=os.environ["UCLOUD_PREPARATION_TEMPLATE_JOB_ID"])
        spec = hosting_job_specification(template, profile)
        _template_contract(client, template, prep, profile["request"]["public_base_url"])
        allowed = {journal.data.get("hosting_job_id"), previous.data.get("hosting_job_id") if previous else None} - {None}
        _check_bound_jobs(client, template, allowed)
        if not journal.data.get("hosting_job_id"):
            _prepare_remote(client, settings, journal, prep, runtime)
            if not journal.data.get("activated"):
                _activate(client, settings, journal, runtime)
            # Files and selection are ready: release only this owned CPU clone.
            _stop_job(client, journal, "preparation")
            if previous:
                journal.update("replacement_cutover_requested", endpoint_verified=False)
                # A failure after releasing the predecessor but before GPU
                # submission has no new hosting job to terminate. Unknown
                # submissions were rejected before preparation above.
                if previous.data.get("hosting_job_id"):
                    _stop_job(client, previous)
                previous.update("replacement_pending", replacement_candidate=str(journal.root), endpoint_verified=False)
            spec["name"] += "-" + journal.root.name[-8:]
            journal.submitted("hosting", client, spec)
        print("Waiting for GPU hosting job " + journal.data["hosting_job_id"], file=sys.stderr, flush=True)
        wait_job(client, journal.data["hosting_job_id"])
        result = verify_host(client, journal, runtime)
        if previous:
            retirement = ("rolled_back" if journal.data.get("rollback_of") else
                          "renewed" if journal.data.get("renewal_of") else "replaced")
            previous.update(retirement, replaced_by=str(journal.root),
                            endpoint_verified=False)
        return result


def rollback(client, root: Path, *, output: Path = Path("deployments")) -> dict:
    """Restore the reviewed predecessor through the same journalled deploy path."""
    return deploy(client, None, replace=root.resolve(), output=output, reviewed=True, rollback=True)


def renew(client, root: Path, hours: int, *, output: Path = Path("deployments")) -> dict:
    """Renew by replacement with the same pinned profile, preserving shared caches."""
    return deploy(client, None, replace=root.resolve(), output=output, reviewed=True, renew_hours=hours)


def status(client, root: Path) -> dict:
    journal = adopt_legacy(root.resolve(), client)
    result = {"deployment": str(root.resolve()), **journal.data}
    for kind in ("preparation", "hosting"):
        if journal.data.get(kind + "_job_id"):
            job = _owned_job(client, journal, kind)
            result[kind + "_job_state"] = job_state(job)
            if kind == "hosting":
                result["expires_at"] = job.get("status", {}).get("expiresAt")
                if job_state(job) in TERMINAL:
                    result["last_endpoint_verified"] = result.get("endpoint_verified", False)
                    result["endpoint_verified"] = False
    if result.get("hosting_job_state") == "RUNNING" and not journal.data.get("legacy_runtime"):
        runtime = load_json(root / "runtime.json")
        result["process"] = ServingShell(client, _owned_job(client, journal)).json([
            runtime["venv_dir"] + "/bin/python", runtime["remote_dir"] + "/remote.py", "status"])
    return result


def restart(client, root: Path) -> dict:
    with operation_lock(CONTROL_ROOT / "lifecycle.lock"):
        journal = adopt_legacy(root.resolve(), client)
        if journal.data.get("legacy_runtime"):
            raise ValueError("Legacy nohup deployment cannot be restarted as a managed tmux session; use --replace")
        job = _owned_job(client, journal)
        if job_state(job) != "RUNNING":
            raise ValueError("Restart requires a running owned allocation; deploy a replacement for an expired job")
        runtime = load_json(root / "runtime.json")
        command = [runtime["venv_dir"] + "/bin/python", runtime["remote_dir"] + "/remote.py"]
        shell = ServingShell(client, job)
        process = shell.json([*command, "status"])
        journal.update("restarting", endpoint_verified=False)
        if process["running"]:
            # The helper can wait 60 seconds per owned port (two for PII).
            # Leave transport margin so a completed shutdown is acknowledged.
            shell.run([*command, "stop"], timeout=180)
        shell.run([*command, "initialize"], timeout=180)
        return verify_host(client, journal, runtime)


def stop(client, root: Path) -> dict:
    with operation_lock(CONTROL_ROOT / "lifecycle.lock"):
        journal = adopt_legacy(root.resolve(), client)
        if journal.data.get("legacy_runtime"):
            raise ValueError("Legacy nohup process lacks managed-session ownership; use replacement or release its exact allocation")
        job = _owned_job(client, journal)
        if job_state(job) != "RUNNING":
            raise ValueError("Stop requires a running owned allocation")
        runtime = load_json(root / "runtime.json")
        shell = ServingShell(client, job)
        helper = [runtime["venv_dir"] + "/bin/python", runtime["remote_dir"] + "/remote.py"]
        if shell.json([*helper, "status"])["running"]:
            shell.run([*helper, "stop"], timeout=180)
        return journal.update("stopped", endpoint_verified=False)


def release(client, root: Path) -> dict:
    with operation_lock(CONTROL_ROOT / "lifecycle.lock"):
        journal = adopt_legacy(root.resolve(), client)
        for kind in ("hosting", "preparation"):
            if journal.data.get(kind + "_job_id"):
                _stop_job(client, journal, kind)
        if any(journal.data.get(k + "_submission") in ("pending", "unknown") for k in ("hosting", "preparation")):
            raise ValueError("Unknown submission outcome must be reconciled before this deployment can be released")
        return journal.update("released", endpoint_verified=False)


def reconcile(client, root: Path, job_id: str, kind: str) -> dict:
    with operation_lock(CONTROL_ROOT / "lifecycle.lock"):
        journal = Journal(root)
        if journal.data.get(kind + "_job_id"):
            raise ValueError("The submission already has a known job ID")
        job = client.retrieve_job(job_id, include_updates=True)
        if (job.get("owner", {}).get("project") != client.settings.project or
                job.get("specification", {}).get("name") != journal.data.get(kind + "_submission_name")):
            raise ValueError("Recovery job ID does not match the recorded submission intent")
        return journal.update("reconciled", **{kind + "_job_id": job_id, kind + "_submission": "known"})
