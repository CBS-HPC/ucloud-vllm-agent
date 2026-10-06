from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version


class ReleasePendingError(RuntimeError):
    pass


def integration_status() -> dict:
    try:
        installed = version("ucloud-workflow")
    except PackageNotFoundError:
        installed = None
    return {
        "installed_ucloud_workflow": installed,
        "gpu_submission_enabled": False,
        "reason": "Await released GPU/product API, review its contract, update dependency pin and add adapter tests.",
    }


def require_hosting_adapter() -> None:
    # Intentionally fail before client construction, template lookup or submission.
    # The operator is implementing GPU selection upstream. Do not invent its API
    # or work around the CPU-only helper in the meantime.
    raise ReleasePendingError(integration_status()["reason"])


def inspect_template() -> dict:
    if not os.getenv("UCLOUD_TEMPLATE_JOB_ID"):
        raise ValueError("UCLOUD_TEMPLATE_JOB_ID is required; never select the latest job implicitly")
    try:
        from ucloud_workflow.client import UCloudClient
        from ucloud_workflow.settings import Settings
    except ImportError:
        raise ValueError("Install the optional ucloud dependency for read-only template inspection") from None
    settings = Settings.from_env()
    with UCloudClient(settings) as client:
        job = client.retrieve_job(settings.template_job_id, include_updates=False)
    spec = job.get("specification", {})
    # Do not return application parameters or raw job data: they may contain
    # credentials. Report selected metadata and resource *types* only.
    return {
        "template_job_id": settings.template_job_id,
        "product": spec.get("product"),
        "application": spec.get("application"),
        "ssh_enabled": spec.get("sshEnabled"),
        "resource_types": [item.get("type") for item in spec.get("resources", []) if isinstance(item, dict)],
        "note": "Read-only summary. Verify URL, nginx upstream, mounts and GPU availability in the template.",
    }
