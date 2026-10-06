from __future__ import annotations

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


def _get_json(url: str) -> dict:
    headers = {"Accept": "application/json"}
    if os.getenv("HF_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["HF_TOKEN"]
    try:
        with urlopen(Request(url, headers=headers), timeout=30) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("HF metadata exceeds the bounded metadata size")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("HF returned invalid metadata")
        return payload
    except HTTPError as exc:
        raise ValueError(f"Hugging Face metadata request failed: HTTP {exc.code}; check model access") from None
    except URLError:
        raise ValueError("Hugging Face metadata request failed; check connectivity") from None


def inspect_model(repo: str, revision: str = "main") -> dict:
    """Fetch only metadata/config, never model weights or repository Python code."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Invalid Hugging Face repository ID")
    info = _get_json(f"https://huggingface.co/api/models/{repo}/revision/{quote(revision, safe='')}?blobs=true")
    sha = info.get("sha")
    if not isinstance(sha, str) or not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise ValueError("HF did not return a pinned commit revision")
    config = _get_json(f"https://huggingface.co/{repo}/resolve/{sha}/config.json")
    sizes = {item.get("rfilename"): item.get("size") for item in info.get("siblings", [])}
    names = []
    if "model.safetensors.index.json" in sizes:
        index = _get_json(f"https://huggingface.co/{repo}/resolve/{sha}/model.safetensors.index.json")
        names = sorted(set(index.get("weight_map", {}).values()))
    elif "model.safetensors" in sizes:
        names = ["model.safetensors"]
    checkpoint_bytes = None
    if names and all(isinstance(sizes.get(name), int) and sizes[name] > 0 for name in names):
        checkpoint_bytes = sum(sizes[name] for name in names)
    return {
        "model": repo, "revision": sha, "config": config,
        "parameters": (info.get("safetensors") or {}).get("total"),
        "checkpoint_bytes": checkpoint_bytes, "checkpoint_files": names,
        "gated": info.get("gated", False),
        "license": (info.get("cardData") or {}).get("license"),
        "sources": [f"https://huggingface.co/{repo}/tree/{sha}",
                    f"https://huggingface.co/{repo}/blob/{sha}/config.json"],
    }
