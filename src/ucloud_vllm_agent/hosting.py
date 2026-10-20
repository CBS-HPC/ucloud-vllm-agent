"""Deterministic configuration for the verified nginx initialization workflow."""
from __future__ import annotations

import math
from copy import deepcopy
from importlib.resources import files
from pathlib import Path, PurePosixPath

from .capacity import estimate_capacity
from .config import load_json, positive_int, validate_request
from .planner import prepare, write_json
from .ucloud_access import require_hosting_adapter

INIT_SCRIPT = files("ucloud_vllm_agent").joinpath("data/ucloud-workspace/init_vllm.sh").read_text(encoding="utf-8")


def validate_profile(profile: dict) -> dict:
    allowed = {"schema", "request", "machine", "hours", "venv_dir"}
    if set(profile) != allowed or profile.get("schema") != "ucloud.vllm.hosting_profile.v1":
        raise ValueError("Unsupported hosting profile schema or fields")
    if not isinstance(profile["request"], dict):
        raise ValueError("Hosting profile request must be an object")
    result = deepcopy(profile)
    result["request"] = validate_request(profile["request"])
    request = result["request"]
    # Startup/provisioning scripts currently implement this verified baseline.
    if request["work_folder"] != "/work/vllm" or request["vllm_version"] != "0.31.0":
        raise ValueError("Initialization profile requires /work/vllm and verified vLLM 0.31.0")
    if profile.get("venv_dir") != "/work/vllm/.venv":
        raise ValueError("Initialization profile requires the prepared /work/vllm/.venv")
    positive_int(profile["hours"], "hours")
    machine = result["machine"]
    allowed_machine = {"name", "gpu_count", "vram_gib_per_gpu", "ram_gib", "mig", "verified", "product"}
    if not isinstance(machine, dict) or set(machine) != allowed_machine:
        raise ValueError("Machine must contain capacity, verification and exact product fields")
    if not isinstance(machine["name"], str) or not machine["name"].strip():
        raise ValueError("Machine name is required")
    positive_int(machine["gpu_count"], "gpu_count")
    for key in ("vram_gib_per_gpu", "ram_gib"):
        value = machine[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError("Machine capacity must be finite and positive")
    for key in ("mig", "verified"):
        if not isinstance(machine[key], bool):
            raise ValueError("Machine mig and verified must be boolean")
    product = machine["product"]
    if not isinstance(product, dict) or set(product) != {"id", "category", "provider"}:
        raise ValueError("Machine product requires id, category and provider")
    if any(not isinstance(v, str) or not v.strip() or any(c in v for c in "\r\n\x00") for v in product.values()):
        raise ValueError("Invalid machine product identifier")
    return result


def prepare_profile(profile: dict, metadata: dict, output: Path) -> Path:
    profile = validate_profile(profile)
    capacity = estimate_capacity(profile["request"], metadata, [profile["machine"]])
    if not capacity["recommendation"]:
        raise ValueError("Selected machine does not fit the model/context/concurrency estimate")
    root = prepare(profile["request"], metadata, [profile["machine"]], output)
    runtime = load_json(root / "runtime.json")
    runtime["venv_dir"] = profile["venv_dir"]
    write_json(root / "runtime.json", runtime)
    write_json(root / "hosting-profile.json", profile)
    (root / "init_vllm.sh").write_text(INIT_SCRIPT, encoding="utf-8", newline="\n")
    from shutil import copyfile
    copyfile(Path(__file__).with_name("remote_prepare.py"), root / "remote_prepare.py")
    if profile["request"]["task"] == "pii":
        copyfile(Path(__file__).with_name("pii_service.py"), root / "pii_service.py")
    probe = root / "endpoint_probe"
    probe.mkdir()
    (probe / "__init__.py").write_text("")
    for name in ("config.py", "checks.py", "pii_checks.py"):
        copyfile(Path(__file__).with_name(name), probe / name)
    write_json(root / "job-settings.json", {
        "hours": profile["hours"], "product": profile["machine"]["product"],
        "startup": "nginx_init_script", "ssh_enabled": False,
        "remote_dir": runtime["remote_dir"], "init_script": "/work/vllm/init_vllm.sh",
        "web_route_registration_required": True, "job_submitted": False,
    })
    return root


def hosting_job_specification(template: dict, profile: dict) -> dict:
    """Build an allocation spec without submitting or changing template resources."""
    profile = validate_profile(profile)
    require_hosting_adapter()
    if template.get("application") != {"name": "nginx", "version": "1.31.2"}:
        raise ValueError("Hosting profile requires verified nginx 1.31.2 template")
    config = template.get("parameters", {}).get("configFile", {})
    path = config.get("path") if isinstance(config, dict) else None
    if (not isinstance(config, dict) or config.get("type") != "file" or not isinstance(path, str) or not path.startswith("/")
            or ".." in path.split("/") or any(c in path for c in "\r\n\x00")
            or PurePosixPath(path).name != "nginx.conf"):
        raise ValueError("Template must identify the operator nginx.conf as a UCloud file")
    from ucloud_workflow.jobs import build_job_specification
    spec = build_job_specification(template, hours=profile["hours"],
                                   product=profile["machine"]["product"],
                                   name="vllm-" + profile["request"]["name"], ssh_enabled=False)
    spec["parameters"]["initScript"] = {
        "type": "file", "path": str(PurePosixPath(path).parent / "init_vllm.sh"), "readOnly": True,
    }
    return spec
