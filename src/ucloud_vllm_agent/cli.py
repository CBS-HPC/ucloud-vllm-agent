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
from .hosting import prepare_profile, validate_profile, hosting_job_specification
from .planner import prepare, write_json
from .ucloud_access import (ReleasePendingError, inspect_template, integration_status,
                           require_hosting_adapter, token_status, preview_job)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan and verify vLLM hosting from an operator-owned UCloud template")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("aitta", help="Use LUMI's managed inference service")
    aitta_commands = command.add_subparsers(dest="aitta_command", required=True)
    aitta_commands.add_parser("models", help="Read the live AITTA model catalog")
    aitta_commands.add_parser("status", help="Read service availability")
    for action in ("workers", "preload"):
        aitta_action = aitta_commands.add_parser(action, help=("Inspect workers" if action == "workers" else
                                                             "Explicitly request loading an offline model"))
        aitta_action.add_argument("--model", required=True)
    aitta_check = aitta_commands.add_parser("check", help="Send synthetic chat/SSE requests; may load a model")
    aitta_check.add_argument("--model", required=True)
    aitta_check.add_argument("--timeout", type=int, default=300)
    aitta_check.add_argument("--output", type=Path, default=Path("artifacts/aitta-checks.json"))
    for name in ("estimate", "prepare"):
        command = commands.add_parser(name)
        command.add_argument("--request", type=Path, required=True)
        command.add_argument("--metadata", type=Path, help="Saved model metadata for offline planning")
        command.add_argument("--machines", type=Path, help="Project-verified machine candidate JSON")
        if name == "prepare":
            command.add_argument("--output", type=Path, default=Path("deployments"))
    commands.add_parser("doctor")
    command = commands.add_parser("models", help="List previously validated model types and untested candidates offline")
    command.add_argument("--type", choices=("chat", "anonymisation", "classification"))
    command.add_argument("--status", choices=("validated", "candidate"))
    for name in ("prepare-profile", "preview-profile"):
        command = commands.add_parser(name)
        command.add_argument("--profile", type=Path, required=True)
        if name == "prepare-profile":
            command.add_argument("--metadata", type=Path, help="Saved model metadata for offline planning")
            command.add_argument("--output", type=Path, default=Path("deployments"))
    commands.add_parser("inspect-template")
    command = commands.add_parser("deploy", help="Prepare and host from explicit CPU/nginx templates")
    command.add_argument("--profile", type=Path)
    command.add_argument("--replace", type=Path, help="Exact owned deployment whose allocation should be replaced")
    command.add_argument("--output", type=Path, default=Path("deployments"))
    command.add_argument("--reviewed", action="store_true", help="Model license and pinned runtime compatibility have been reviewed")
    command.add_argument("--auto-size", action="store_true", help="Choose from the live project B200 GPU/MIG catalog")
    for name in ("status", "restart", "stop", "release", "recover", "rollback", "renew"):
        command = commands.add_parser(name)
        command.add_argument("--deployment", type=Path, required=True)
        if name == "renew":
            command.add_argument("--hours", type=int, required=True, help="New allocation duration; renewal replaces the owned job")
        if name == "recover":
            command.add_argument("--submission-job-id")
            command.add_argument("--kind", choices=("hosting", "preparation"), default="hosting")
    command = commands.add_parser("catalog")
    command.add_argument("--output", type=Path, default=Path("artifacts/machines.json"))
    command = commands.add_parser("size")
    command.add_argument("--profile", type=Path, required=True)
    command.add_argument("--metadata", type=Path)
    command.add_argument("--machines", type=Path)
    command = commands.add_parser("token-status")
    command.add_argument("--hours", type=int, default=1)
    command = commands.add_parser("preview-job")
    command.add_argument("--hours", type=int, required=True)
    command.add_argument("--product-id")
    command.add_argument("--product-category")
    command.add_argument("--product-provider")
    command = commands.add_parser("check")
    command.add_argument("--base-url", required=True)
    command.add_argument("--model", required=True)
    command.add_argument("--task", choices=["chat", "pii"], default="chat")
    command.add_argument("--output", type=Path, default=Path("artifacts/checks.json"))
    args = parser.parse_args(argv)
    load_env()
    try:
        if args.command == "aitta":
            from . import aitta
            if args.aitta_command == "models":
                result = aitta.list_models()
            elif args.aitta_command == "status":
                result = aitta.service_status()
            elif args.aitta_command in ("workers", "preload"):
                result = getattr(aitta, args.aitta_command)(args.model)
            else:
                result = aitta.check_model(args.model, timeout=args.timeout)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                write_json(args.output, result)
            print(json.dumps(result, indent=2))
            return 0 if result.get("passed", True) else 1
        elif args.command == "models":
            from .model_catalog import list_models
            print(json.dumps(list_models(args.type, args.status), indent=2))
        elif args.command in ("prepare-profile", "preview-profile"):
            profile = validate_profile(load_json(args.profile))
            if args.command == "prepare-profile":
                request = profile["request"]
                metadata = load_json(args.metadata) if args.metadata else inspect_model(request["model"], request["revision"])
                root = prepare_profile(profile, metadata, args.output)
                print(json.dumps({"state": "prepared", "path": str(root), "job_submitted": False}, indent=2))
            else:
                from ucloud_workflow.client import UCloudClient
                from ucloud_workflow.settings import Settings
                from ucloud_workflow.jobs import template_job_specification
                if not os.getenv("UCLOUD_TEMPLATE_JOB_ID"):
                    raise ValueError("UCLOUD_TEMPLATE_JOB_ID is required; no latest-job fallback")
                settings = Settings.from_env()
                with UCloudClient(settings) as client:
                    template = template_job_specification(client, template_job_id=settings.template_job_id)
                spec = hosting_job_specification(template, profile)
                print(json.dumps({"template_job_id": settings.template_job_id, "job_submitted": False,
                                  "product": spec["product"], "allocation": spec["timeAllocation"],
                                  "application": spec["application"], "ssh_enabled": spec["sshEnabled"],
                                  "startup": "nginx_init_script", "web_route_registration_required": True}, indent=2))
        elif args.command == "deploy" and not args.profile:
            raise ReleasePendingError("Select --profile and --reviewed before allocating resources")
        elif args.command in ("deploy", "status", "restart", "stop", "release", "recover", "rollback", "renew", "catalog", "size"):
            require_hosting_adapter()
            from ucloud_workflow.client import UCloudClient
            from ucloud_workflow.settings import Settings
            from . import lifecycle
            from .catalog import sync_catalog
            if args.command == "size" and args.metadata and args.machines:
                profile = validate_profile(load_json(args.profile))
                result = estimate_capacity(profile["request"], load_json(args.metadata), load_json(args.machines)["machines"])
            else:
                with UCloudClient(Settings.from_env()) as client:
                    if args.command == "deploy":
                        result = lifecycle.deploy(client, load_json(args.profile), output=args.output,
                                                  replace=args.replace, reviewed=args.reviewed, auto_size=args.auto_size)
                    elif args.command == "recover":
                        if args.submission_job_id:
                            result = lifecycle.reconcile(client, args.deployment.resolve(), args.submission_job_id, args.kind)
                        else:
                            from .state import Journal
                            result = lifecycle.deploy(client, None, root=args.deployment,
                                                      reviewed=Journal(args.deployment).data.get("reviewed", False))
                    elif args.command == "renew":
                        result = lifecycle.renew(client, args.deployment.resolve(), args.hours)
                    elif args.command in ("status", "restart", "stop", "release", "rollback"):
                        result = getattr(lifecycle, args.command)(client, args.deployment.resolve())
                    elif args.command == "catalog":
                        result = sync_catalog(client)
                        write_json_target = args.output
                        write_json_target.parent.mkdir(parents=True, exist_ok=True)
                        write_json(write_json_target, result)
                    else:
                        profile = validate_profile(load_json(args.profile))
                        request = profile["request"]
                        metadata = load_json(args.metadata) if args.metadata else inspect_model(request["model"], request["revision"])
                        machines = load_json(args.machines) if args.machines else sync_catalog(client)
                        result = estimate_capacity(request, metadata, machines["machines"])
            print(json.dumps(result, indent=2))
            if args.command == "size":
                return 0 if result.get("recommendation") else 1
        elif args.command == "doctor":
            result = {"agent_version": __version__, "ucloud_integration": integration_status(),
                      "configured": {key: bool(os.getenv(key)) for key in (
                          "UCLOUD_PROJECT", "UCLOUD_TOKEN", "UCLOUD_TOKEN_ID", "UCLOUD_TEMPLATE_JOB_ID",
                          "UCLOUD_PUBLIC_BASE_URL", "VLLM_API_KEY")}}
            print(json.dumps(result, indent=2))
        elif args.command == "inspect-template":
            print(json.dumps(inspect_template(), indent=2))
        elif args.command == "token-status":
            result = token_status(args.hours)
            print(json.dumps(result, indent=2))
            return 0 if result["supports_allocation"] else 1
        elif args.command == "preview-job":
            selection = [args.product_id, args.product_category, args.product_provider]
            if any(selection) and not all(selection):
                raise ValueError("Product override requires id, category and provider together")
            product = dict(zip(("id", "category", "provider"), selection)) if all(selection) else None
            print(json.dumps(preview_job(hours=args.hours, product=product), indent=2))
        elif args.command == "check":
            checker = check_endpoint
            if args.task == "pii":
                from .pii_checks import check_pii_endpoint
                checker = check_pii_endpoint
            result = checker(args.base_url, args.model)
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
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, ImportError) as exc:
        # Do not print upstream response bodies, credentials or a stack trace.
        reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        print("Operation failed: " + reason, file=sys.stderr)
        return 1
