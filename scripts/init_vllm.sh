#!/usr/bin/env bash
set -euo pipefail
deployment="$(readlink -f /work/vllm/active)"
case "$deployment" in /work/vllm/deployments/*) ;; *) exit 1 ;; esac
exec >> "$deployment/initialization.log" 2>&1
exec /work/vllm/.venv/bin/python "$deployment/remote.py" initialize
