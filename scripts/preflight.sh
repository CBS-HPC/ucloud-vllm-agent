#!/usr/bin/env bash
# Read-only inventory; run inside the target Linux job.
set -euo pipefail
if [[ "$(uname -s)" != Linux ]]; then
    echo 'Run preflight on the Linux UCloud host.' >&2
    exit 1
fi
printf 'Host kernel: '; uname -sr
if [[ -r /etc/os-release ]]; then cat /etc/os-release; fi
for tool in python3 vllm nginx nvidia-smi tmux; do
    if command -v "$tool" >/dev/null 2>&1; then
        printf '%s: %s\n' "$tool" "$(command -v "$tool")"
    else
        printf '%s: missing\n' "$tool"
    fi
done
if command -v python3 >/dev/null 2>&1; then
    python3 --version
    python3 -c 'from importlib.metadata import version, PackageNotFoundError
try: print("vLLM package:", version("vllm"))
except PackageNotFoundError: print("vLLM package: missing")'
fi
if command -v nginx >/dev/null 2>&1; then nginx -v; fi
if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=name,driver_version,memory.total,memory.free --format=csv
    nvidia-smi -L
fi
df -h -- "${1:-/work}"
if command -v ss >/dev/null 2>&1; then ss -ltn; fi
