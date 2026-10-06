from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit


def load_env(path: Path = Path(".env")) -> None:
    """Read literal key/value settings without evaluating shell code."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if separator and re.fullmatch(r"[A-Z][A-Z0-9_]*", key.strip()):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object")
    return payload


def positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def validate_request(request: dict) -> dict:
    allowed = {
        "name", "model", "revision", "context_length", "concurrency", "dtype",
        "gpu_memory_utilization", "runtime_reserve_gib", "weight_overhead_fraction",
        "vllm_version", "vllm_port", "work_folder", "public_base_url", "secret_file",
    }
    if set(request) - allowed:
        raise ValueError("Unknown request fields: " + ", ".join(sorted(set(request) - allowed)))
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,47}", request.get("name", "")):
        raise ValueError("name must be a lowercase deployment name, up to 48 characters")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", request.get("model", "")):
        raise ValueError("model must be an owner/repository Hugging Face ID")
    result = {
        "revision": "main", "context_length": 4096, "concurrency": 1,
        "dtype": "bfloat16", "gpu_memory_utilization": 0.85,
        "runtime_reserve_gib": 3.0, "weight_overhead_fraction": 0.1,
        "vllm_version": None, "vllm_port": 8000,
        "work_folder": os.getenv("UCLOUD_WORK_FOLDER") or "/work/ucloud-vllm",
        "public_base_url": os.getenv("UCLOUD_PUBLIC_BASE_URL") or None,
        "secret_file": "/work/ucloud-vllm/secrets/runtime.env",
        **request,
    }
    for key in ("context_length", "concurrency", "vllm_port"):
        positive_int(result[key], key)
    if result["vllm_port"] > 65535:
        raise ValueError("vllm_port must be <= 65535")
    if result["dtype"] not in ("bfloat16", "float16", "float32"):
        raise ValueError("dtype must be bfloat16, float16 or float32")
    for key in ("gpu_memory_utilization", "runtime_reserve_gib", "weight_overhead_fraction"):
        value = result[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} must be numeric")
        import math
        if not math.isfinite(value):
            raise ValueError(f"{key} must be finite")
    if not 0 < result["gpu_memory_utilization"] <= 0.95:
        raise ValueError("gpu_memory_utilization must be in (0, 0.95]")
    if result["runtime_reserve_gib"] < 1 or not 0 <= result["weight_overhead_fraction"] <= 1:
        raise ValueError("Require at least 1 GiB runtime reserve and overhead fraction in [0, 1]")
    for key in ("work_folder", "secret_file"):
        value = result[key]
        if not isinstance(value, str) or not value.startswith("/work/") or ".." in value.split("/"):
            raise ValueError(f"{key} must be a path below the verified /work mount")
        if any(c in value for c in "\r\n\x00"):
            raise ValueError(f"Invalid {key}")
    version = result["vllm_version"]
    if version is not None and not re.fullmatch(r"\d+\.\d+\.\d+(?:[a-z0-9.]+)?", version):
        raise ValueError("vllm_version must be an exact release version")
    if result["public_base_url"]:
        validate_base_url(result["public_base_url"], external=True)
    if not isinstance(result["revision"], str) or not result["revision"]:
        raise ValueError("revision must be a non-empty HF revision")
    return result


def validate_base_url(url: str, *, external: bool = False) -> str:
    parts = urlsplit(url)
    if parts.username or parts.password or parts.query or parts.fragment or not parts.hostname:
        raise ValueError("API base URL must not contain credentials, query or fragment")
    loopback = parts.hostname in ("localhost", "127.0.0.1", "::1")
    if parts.scheme != "https" and not (parts.scheme == "http" and loopback and not external):
        raise ValueError("Use HTTPS externally; HTTP is allowed only for local checks")
    if not parts.path.rstrip("/").endswith("/v1"):
        raise ValueError("API base URL must include /v1")
    return url.rstrip("/")
