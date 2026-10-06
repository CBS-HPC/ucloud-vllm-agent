from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .capacity import estimate_capacity
from .config import validate_request


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def prepare(request: dict, metadata: dict, machines: list[dict], output_root: Path) -> Path:
    request = validate_request(request)
    if metadata.get("model") != request["model"]:
        raise ValueError("Model metadata does not match the requested repository")
    revision = metadata.get("revision", "")
    if not isinstance(revision, str) or not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("Model metadata must include a pinned HF commit hash")
    if re.fullmatch(r"[a-f0-9]{40}", request["revision"]) and request["revision"] != revision:
        raise ValueError("Metadata revision differs from the requested pinned revision")
    capacity = estimate_capacity(request, metadata, machines)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    root = output_root.resolve() / request["name"] / run_id
    root.mkdir(parents=True, exist_ok=False)
    blockers = list(capacity["blockers"])
    selected = capacity["recommendation"]
    if not request["vllm_version"]:
        blockers.append("choose_verified_vllm_release")
    if not os.getenv("UCLOUD_TEMPLATE_JOB_ID"):
        blockers.append("configure_UCLOUD_TEMPLATE_JOB_ID")
    if not request["public_base_url"]:
        blockers.append("confirm_template_https_api_url")
    if not os.getenv("VLLM_API_KEY"):
        blockers.append("configure_vllm_serving_key_before_launch")
    if selected and not selected.get("verified"):
        blockers.append("verify_machine_capacity_and_product_in_project")
    blockers.extend(["review_model_license_and_runtime_compatibility",
                     "inspect_template_nginx_upstream_mounts_and_secret_file"])
    plan = {"schema": "ucloud.vllm.deployment_plan.v1", "run_id": run_id,
            "state": "prepared", "request": request,
            "template_job_id": os.getenv("UCLOUD_TEMPLATE_JOB_ID") or None,
            "model_metadata": metadata, "capacity": capacity, "blockers": blockers,
            "job_id": None, "notes": ["No job was submitted.",
                "Operator owns URL and nginx setup in the template.",
                "Successful hosting must keep the allocated job running."]}
    write_json(root / "plan.json", plan)
    write_json(root / "checks.json", {"state": "not_run", "checks": []})
    # Only generate runtime files when the estimator has a suitable candidate.
    # They do not constitute a permission/compatibility review or remote launch.
    if selected:
        remote_dir = request["work_folder"].rstrip("/") + "/deployments/" + request["name"] + "/" + run_id
        runtime = {"schema": "ucloud.vllm.runtime.v1", "name": request["name"],
                   "task": request["task"],
                   "remote_dir": remote_dir, "session": "vllm-" + request["name"] + "-" + run_id[-8:],
                   "model": request["model"], "revision": revision,
                   "dtype": request["dtype"], "context_length": request["context_length"],
                   "kv_cache_dtype": request["kv_cache_dtype"],
                   "concurrency": request["concurrency"], "port": request["vllm_port"],
                   "gpu_memory_utilization": request["gpu_memory_utilization"],
                   "gpu_count": selected["gpu_count"],
                   "required_gib_per_gpu": selected["required_gib_per_gpu"],
                   "required_disk_gib": capacity["required_disk_gib_estimate"],
                   "required_ram_gib": capacity["required_system_ram_gib_estimate"],
                   "vllm_version": request["vllm_version"], "secret_file": request["secret_file"],
                   "hf_env_file": request["hf_env_file"], "nginx_config": request["nginx_config"],
                   "cache_dir": request["work_folder"].rstrip("/") + "/cache/huggingface",
                   "venv_dir": request["work_folder"].rstrip("/") + "/environments/vllm-" + (request["vllm_version"] or "UNSELECTED")}
        write_json(root / "runtime.json", runtime)
        shutil.copyfile(Path(__file__).with_name("remote.py"), root / "remote.py")
    text = f"# Deployment {request['name']}\n\nState: prepared. No job submitted.\n\n"
    text += f"Model: {request['model']} at {revision}\n\n"
    if selected:
        text += (f"Estimated machine: {selected['name']} ({selected['gpu_count']} devices).\n\n"
                 f"VRAM needed per device: {selected['required_gib_per_gpu']} GiB; "
                 f"usable allowance: {selected['usable_gib_per_gpu']} GiB.\n\n"
                 f"System RAM allowance: {capacity['required_system_ram_gib_estimate']} GiB. "
                 f"Disk allowance: {capacity['required_disk_gib_estimate']} GiB.\n\n")
    text += "Before deployment:\n\n" + "\n".join("- " + item for item in blockers) + "\n"
    (root / "README.md").write_text(text, encoding="utf-8")
    return root
