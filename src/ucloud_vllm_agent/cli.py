from __future__ import annotations

import argparse
import json
import os
import sys
from importlib.resources import files
from pathlib import Path

from . import __version__
from .capacity import estimate_capacity
from .checks import check_endpoint
from .config import load_env, load_json, validate_request
from .huggingface import inspect_model
from .planner import prepare, write_json
from .ucloud_access import ReleasePendingError, inspect_template, integration_status, require_hosting_adapter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan and verify vLLM hosting from an operator-owned UCloud template")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("estimate", "prepare"):
        command = commands.add_parser(name)
        command.add_argument("--request", type=Path, required=True)
        command.add_argument("--metadata", type=Path, help="Saved model metadata for offline planning")
        command.add_argument("--machines", type=Path, help="Project-verified machine candidate JSON")
        if name == "prepare":
            command.add_argument("--output", type=Path, default=Path("deployments"))
    commands.add_parser("doctor")
    commands.add_parser("inspect-template")
    commands.add_parser("deploy", help="Release gate: submission awaits the new upstream GPU API")
    command = commands.add_parser("check")
    command.add_argument("--base-url", required=True)
    command.add_argument("--model", required=True)
    command.add_argument("--output", type=Path, default=Path("artifacts/checks.json"))
    args = parser.parse_args(argv)
    load_env()
    try:
        if args.command == "deploy":
            require_hosting_adapter()
        elif args.command == "doctor":
            result = {"agent_version": __version__, "ucloud_integration": integration_status(),
                      "configured": {key: bool(os.getenv(key)) for key in (
                          "UCLOUD_PROJECT", "UCLOUD_TOKEN", "UCLOUD_TEMPLATE_JOB_ID", "UCLOUD_PUBLIC_BASE_URL")}}
            print(json.dumps(result, indent=2))
        elif args.command == "inspect-template":
            print(json.dumps(inspect_template(), indent=2))
        elif args.command == "check":
            result = check_endpoint(args.base_url, args.model)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            write_json(args.output, result)
            print(json.dumps(result, indent=2))
            return 0 if result["passed"] else 1
        else:
            request = validate_request(load_json(args.request))
            metadata = load_json(args.metadata) if args.metadata else inspect_model(request["model"], request["revision"])
            if metadata.get("model") != request["model"]:
                raise ValueError("Model metadata does not match requested repository")
            if args.machines:
                machine_data = load_json(args.machines)
            else:
                machine_data = json.loads(files("ucloud_vllm_agent").joinpath("data/machines.json").read_text())
            if machine_data.get("schema") != "ucloud.vllm.machine_candidates.v1":
                raise ValueError("Unsupported machine candidate schema")
            if args.command == "estimate":
                result = estimate_capacity(request, metadata, machine_data["machines"])
                print(json.dumps(result, indent=2))
                return 0 if result["recommendation"] else 1
            root = prepare(request, metadata, machine_data["machines"], args.output)
            print(json.dumps({"state": "prepared", "path": str(root), "job_submitted": False}, indent=2))
        return 0
    except ReleasePendingError as exc:
        print("Deployment blocked: " + str(exc), file=sys.stderr)
        return 2
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
        # Do not print upstream response bodies, credentials or a stack trace.
        reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        print("Operation failed: " + reason, file=sys.stderr)
        return 1
