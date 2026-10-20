from __future__ import annotations

import os
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version

REVIEWED_UCLOUD_VERSION = "0.1.7"

class ReleasePendingError(RuntimeError):
    pass


def integration_status() -> dict:
    try:
        installed = version("ucloud-workflow")
    except PackageNotFoundError:
        installed = None
    return {
        "installed_ucloud_workflow": installed,
        "gpu_product_selection_enabled": installed == REVIEWED_UCLOUD_VERSION,
        "gpu_submission_enabled": installed == REVIEWED_UCLOUD_VERSION,
        "resource_setup_enabled": installed == REVIEWED_UCLOUD_VERSION,
        "reason": "Hosting and separate Link/key setup require the reviewed v" + REVIEWED_UCLOUD_VERSION + " package.",
    }


def require_hosting_adapter() -> None:
    if integration_status()["installed_ucloud_workflow"] != REVIEWED_UCLOUD_VERSION:
        raise ReleasePendingError("Install the reviewed ucloud-workflow v" + REVIEWED_UCLOUD_VERSION + " package")


def preview_job_specification(template: dict, *, hours: int, product: dict | None = None) -> dict:
    """Use the released builder; preserve template product unless explicitly set."""
    require_hosting_adapter()
    if isinstance(hours, bool) or not isinstance(hours, int) or hours <= 0:
        raise ValueError("hours must be a positive integer")
    from ucloud_workflow.jobs import build_job_specification
    return build_job_specification(template, hours=hours, product=product, ssh_enabled=True)


def token_status(hours: int = 1) -> dict:
    """Select non-secret expiry metadata using the explicit managed token ID."""
    token_id = os.getenv("UCLOUD_TOKEN_ID")
    if not token_id:
        raise ValueError("UCLOUD_TOKEN_ID is required for unambiguous token expiry checks")
    if isinstance(hours, bool) or not isinstance(hours, int) or hours < 1:
        raise ValueError("hours must be a positive integer")
    from ucloud_workflow.client import UCloudClient
    from ucloud_workflow.settings import Settings
    from ucloud_workflow.tokens import summarize_api_tokens
    with UCloudClient(Settings.from_env()) as client:
        response = client.browse_api_tokens(items_per_page=100, filter_hidden=False)
    summaries = summarize_api_tokens(response, expiring_within_days=30)
    selected = next((item for item in summaries if item.token_id == token_id), None)
    if selected is None:
        raise ValueError("Configured UCLOUD_TOKEN_ID is not visible in token metadata")
    required_seconds = (hours + 1) * 3600
    supports = (selected.expires_at is not None and
                (selected.expires_at - datetime.now(timezone.utc)).total_seconds() > required_seconds)
    return {"expiry_state": selected.expiry_state,
            "expires_at": selected.expires_at.isoformat() if selected.expires_at else None,
            "days_remaining": selected.days_remaining,
            "allocation_hours": hours, "safety_margin_hours": 1,
            "supports_allocation": supports,
            "note": "Token ID is operator-supplied; token identity cannot be inferred from its secret."}


def preview_job(*, hours: int, product: dict | None = None) -> dict:
    if not os.getenv("UCLOUD_TEMPLATE_JOB_ID"):
        raise ValueError("UCLOUD_TEMPLATE_JOB_ID is required; no latest-job fallback")
    from ucloud_workflow.client import UCloudClient
    from ucloud_workflow.jobs import template_job_specification
    from ucloud_workflow.settings import Settings
    settings = Settings.from_env()
    with UCloudClient(settings) as client:
        template = template_job_specification(client, template_job_id=settings.template_job_id)
    spec = preview_job_specification(template, hours=hours, product=product)
    return {"template_job_id": settings.template_job_id, "job_submitted": False,
            "product": spec["product"], "allocation": spec["timeAllocation"],
            "application": spec.get("application"),
            "resource_types": [item.get("type") for item in spec.get("resources", []) if isinstance(item, dict)],
            "note": "Read-only specification preview; nginx/URL/mount resources are preserved."}


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
