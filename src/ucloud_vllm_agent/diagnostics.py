"""Sanitized local requirements and opt-in read-only API preflight."""
from __future__ import annotations

import os
from pathlib import Path
import shutil

from . import __version__
from .config import load_json, normalize_public_url
from .ucloud_access import integration_status, token_status

REQUIRED = ("UCLOUD_PROJECT", "UCLOUD_TOKEN", "UCLOUD_TOKEN_ID", "UCLOUD_TEMPLATE_JOB_ID",
            "UCLOUD_PREPARATION_TEMPLATE_JOB_ID", "UCLOUD_PUBLIC_BASE_URL", "VLLM_API_KEY")


def diagnose(*, online: bool = False, profile: Path | None = None) -> dict:
    checks = []
    def check(name, passed, remedy):
        checks.append({"check": name, "passed": bool(passed), "remedy": None if passed else remedy})

    integration = integration_status()
    check("ucloud_dependency", integration["installed_ucloud_workflow"] == "0.1.6",
          "Install this provider's [ucloud] extra with the reviewed ucloud-workflow v0.1.6 dependency.")
    configured = {key: bool(os.getenv(key, "").strip()) for key in REQUIRED}
    for key, present in configured.items():
        check(key, present, "Set " + key + " in this provider workspace's local .env or caller environment.")
    for executable in ("git", "ssh", "scp"):
        check("executable_" + executable, shutil.which(executable) is not None,
              "Install " + executable + " and make it available on PATH.")
    check("workspace_mount_path", os.getenv("UCLOUD_WORK_FOLDER", "/work/vllm") == "/work/vllm",
          "Use the supported /work/vllm mount in both templates.")
    url_valid = False
    if configured["UCLOUD_PUBLIC_BASE_URL"]:
        try:
            normalize_public_url(os.environ["UCLOUD_PUBLIC_BASE_URL"])
            url_valid = True
        except ValueError:
            pass
    check("public_url_format", url_valid, "Use your reserved HTTPS hostname or /v1 URL without credentials, query or fragment.")
    identity = os.getenv("UCLOUD_SSH_IDENTITY_FILE")
    if identity:
        keys = [Path(identity)]
    else:
        # Use the dependency's discovery rule; do not read key/config contents.
        from .ucloud_access import require_hosting_adapter
        keys = []
        if integration["installed_ucloud_workflow"] == "0.1.6":
            require_hosting_adapter()
            from ucloud_workflow.settings import discover_ssh_identity_files
            config = Path(os.getenv("UCLOUD_SSH_CONFIG_PATH") or Path.home() / ".ssh/config")
            keys = discover_ssh_identity_files(config)
    check("local_ssh_identity", bool(keys) and all(path.is_file() for path in keys),
          "Set UCLOUD_SSH_IDENTITY_FILE to an existing local private key whose public key is registered on UCloud.")
    local_passed = all(item["passed"] for item in checks)
    remote = "not_requested"
    if online and local_passed:
        if profile is None:
            check("hosting_profile", False, "Supply --profile with doctor --online.")
            remote = "blocked"
        else:
            remote = "checked"
            # Never return an exception body, request headers, application
            # parameters or credential-file contents in the diagnostics report.
            try:
                _online_preflight(profile)
                check("api_preflight", True, "")
            except Exception:
                check("api_preflight", False,
                      "Verify profile, token coverage, both templates' project/application/mounts and the unoccupied public link. "
                      "Use token-status, inspect-template and preview-profile for sanitized details.")
    elif online:
        remote = "blocked_by_local_requirements"
    passed = all(item["passed"] for item in checks)
    return {"schema": "ucloud.vllm.diagnostics.v1", "agent_version": __version__,
            "state": "preflight_passed" if passed and online else "configured" if passed else "blocked",
            "passed": passed, "configured": configured, "local_checks_passed": local_passed,
            "ucloud_integration": integration, "api_preflight": remote, "checks": checks,
            "ready_for_submission": bool(passed and online), "job_submitted": False,
            "runtime_verified": False, "endpoint_verified": False,
            "limits": ["Local identity presence does not prove registration or SSH authentication.",
                       "API preflight does not execute SSH, inspect remote secrets, validate nginx syntax or prove runtime readiness.",
                       "Resource availability and token coverage can change after preflight."]}


def _online_preflight(profile_path: Path) -> None:
    from ucloud_workflow.client import UCloudClient
    from ucloud_workflow.jobs import template_job_specification
    from ucloud_workflow.settings import Settings
    from .hosting import hosting_job_specification, validate_profile
    from .lifecycle import _check_bound_jobs, _template_contract, _validate_template_ownership
    profile = validate_profile(load_json(profile_path))
    settings = Settings.from_env()
    with UCloudClient(settings) as client:
        _validate_template_ownership(client)
        serving = template_job_specification(client, template_job_id=settings.template_job_id)
        preparation = template_job_specification(client, template_job_id=os.environ["UCLOUD_PREPARATION_TEMPLATE_JOB_ID"])
        hosting_job_specification(serving, profile)
        if preparation.get("application") != {"name": "coder-python", "version": "1.89.1"}:
            raise ValueError("Preparation application needs baseline compatibility review")
        _template_contract(client, serving, preparation, normalize_public_url(os.environ["UCLOUD_PUBLIC_BASE_URL"]))
        _check_bound_jobs(client, serving, set())
    if not token_status(profile["hours"])["supports_allocation"]:
        raise ValueError("Token does not cover allocation and safety margin")
