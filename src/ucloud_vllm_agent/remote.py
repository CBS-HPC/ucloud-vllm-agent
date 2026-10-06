"""Standalone runtime helper copied into each secret-free deployment bundle.

Run only inside the intended UCloud Linux job. nginx and job allocation are
owned by the template. This file never submits or terminates a UCloud job.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
import shlex

GIB = 1024 ** 3


def read_runtime(root: Path) -> dict:
    config = json.loads((root / "runtime.json").read_text(encoding="utf-8"))
    if config.get("schema") != "ucloud.vllm.runtime.v1":
        raise ValueError("Unsupported runtime configuration")
    if str(root) != config["remote_dir"]:
        raise ValueError("Upload bundle to its recorded remote_dir before execution")
    return config


def interpreter(config: dict) -> Path:
    return Path(config["venv_dir"]) / "bin" / "python"


def preflight(config: dict, root: Path) -> dict:
    if sys.platform != "linux":
        raise ValueError("Hosting runtime requires Linux")
    if not config.get("vllm_version"):
        raise ValueError("Choose a verified exact vLLM release first")
    if not interpreter(config).is_file():
        raise ValueError("Provision the pinned environment before launch")
    if not shutil.which("tmux"):
        raise ValueError("Template must provide tmux")
    if not Path(config["nginx_config"]).is_file():
        raise ValueError("The template nginx config is missing at its recorded path")
    if not Path(config["hf_env_file"]).is_file():
        raise ValueError("The template HF environment file is missing at its recorded path")
    secret = Path(config["secret_file"])
    if not secret.is_file() or secret.stat().st_mode & 0o077:
        raise ValueError("Remote runtime secret file must exist and be readable only by its owner")
    probe = '''import json, torch
from importlib.metadata import version
devices = []
for index in range(torch.cuda.device_count()):
    free, total = torch.cuda.mem_get_info(index)
    devices.append({"name": torch.cuda.get_device_name(index), "free_bytes": free, "total_bytes": total})
print(json.dumps({"vllm_version": version("vllm"), "devices": devices}))'''
    result = subprocess.run([str(interpreter(config)), "-c", probe], capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise ValueError("GPU/runtime probe failed; inspect the pinned environment on the host")
    gpu = json.loads(result.stdout)
    if gpu["vllm_version"] != config["vllm_version"]:
        raise ValueError("Installed vLLM differs from the pinned deployment release")
    if len(gpu["devices"]) != config["gpu_count"]:
        raise ValueError("Visible CUDA device count differs from the planned allocation")
    for device in gpu["devices"]:
        budget = min(device["free_bytes"], device["total_bytes"] * config["gpu_memory_utilization"])
        if budget < config["required_gib_per_gpu"] * GIB:
            raise ValueError("Measured per-device GPU memory is below the plan")
    if shutil.disk_usage(root).free < config["required_disk_gib"] * GIB:
        raise ValueError("Available disk is below the planned storage allowance")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", config["port"]))
    return {"state": "preflight_passed", "gpu": gpu,
            "note": "Verify mounted persistence and container RAM limits separately before launch."}


def write_state(root: Path, state: str, **details) -> None:
    temporary = root / "state.tmp"
    temporary.write_text(json.dumps({"state": state, **details}, indent=2) + "\n", encoding="utf-8")
    temporary.replace(root / "state.json")


def load_runtime_secrets(config: dict) -> dict:
    env = os.environ.copy()
    # Read only the intended key from each source; neither file is evaluated or
    # rewritten. A blank serving key can never disable authentication silently.
    for source, allowed_key in ((config["hf_env_file"], "HF_TOKEN"), (config["secret_file"], "VLLM_API_KEY")):
        for raw in Path(source).read_text(encoding="utf-8-sig").splitlines():
            key, separator, value = raw.strip().partition("=")
            if separator and key == allowed_key:
                env[key] = value.strip().strip("\"'")
    if not env.get("VLLM_API_KEY"):
        raise ValueError("Remote secret configuration must provide VLLM_API_KEY")
    env["HF_HOME"] = config["cache_dir"]
    env["VLLM_NO_USAGE_STATS"] = "1"
    return env


def serve(config: dict, root: Path) -> None:
    env = load_runtime_secrets(config)
    command = [str(Path(config["venv_dir"]) / "bin" / "vllm"), "serve", config["model"],
               "--revision", config["revision"], "--served-model-name", config["name"],
               "--host", "127.0.0.1", "--port", str(config["port"]),
               "--dtype", config["dtype"], "--max-model-len", str(config["context_length"]),
               "--max-num-seqs", str(config["concurrency"]),
               "--tensor-parallel-size", str(config["gpu_count"]),
               "--gpu-memory-utilization", str(config["gpu_memory_utilization"])]
    with (root / "vllm.log").open("a", encoding="utf-8") as logfile:
        os.dup2(logfile.fileno(), 1)
        os.dup2(logfile.fileno(), 2)
        os.execve(command[0], command, env)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["install", "preflight", "start", "serve", "status", "stop"])
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    try:
        config = read_runtime(root)
        if args.operation == "install":
            if sys.platform != "linux" or not config.get("vllm_version"):
                raise ValueError("Install requires Linux and a verified pinned vLLM release")
            if interpreter(config).exists():
                raise ValueError("Environment already exists; inspect it before replacement")
            subprocess.run([sys.executable, "-m", "venv", config["venv_dir"]], check=True, timeout=120)
            subprocess.run([str(interpreter(config)), "-m", "pip", "install", "vllm==" + config["vllm_version"]],
                           check=True, timeout=1800)
        elif args.operation == "preflight":
            result = preflight(config, root)
            (root / "preflight.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(result, indent=2))
        elif args.operation == "start":
            result = preflight(config, root)
            load_runtime_secrets(config)  # Validate credentials before creating a session.
            if subprocess.run(["tmux", "has-session", "-t", "=" + config["session"]], capture_output=True).returncode == 0:
                raise ValueError("Deployment session already exists; inspect it before replacement")
            command = shlex.join([sys.executable, str(root / "remote.py"), "serve"])
            subprocess.run(["tmux", "new-session", "-d", "-s", config["session"], "-c", str(root), command], check=True, timeout=30)
            write_state(root, "launched", session=config["session"], preflight=result,
                        note="nginx and UCloud job remain running; endpoint checks are still required")
        elif args.operation == "serve":
            serve(config, root)
        elif args.operation == "status":
            result = subprocess.run(["tmux", "has-session", "-t", "=" + config["session"]], capture_output=True, timeout=15)
            print(json.dumps({"session": config["session"], "running": result.returncode == 0,
                              "note": "Session presence is not model readiness or public verification."}))
        elif args.operation == "stop":
            subprocess.run(["tmux", "kill-session", "-t", "=" + config["session"]], check=True, timeout=15)
            write_state(root, "stopped", note="Only the exact deployment session stopped; UCloud allocation remains running.")
        return 0
    except (ValueError, OSError, KeyError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        # No raw response, command output, environment, or secret values in errors.
        reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        print("Runtime operation failed: " + reason, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
