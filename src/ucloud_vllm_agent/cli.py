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
from .resource_setup import SetupOutcomeUnknownError
from .ucloud_access import (ReleasePendingError, inspect_template, integration_status,
                           require_hosting_adapter, token_status, preview_job)


def report_error(code: str, message: str) -> None:
    print(json.dumps({"schema": "ucloud.vllm.error.v1", "error": {"code": code, "message": message}}), file=sys.stderr)


class JSONArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        report_error("invalid_arguments", "Invalid command arguments; use --help.")
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    parser = JSONArgumentParser(description="Plan and verify vLLM hosting through explicit UCloud templates or reviewed bootstrap specifications")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("estimate", "prepare"):
        command = commands.add_parser(name)
        command.add_argument("--request", type=Path, required=True)
        command.add_argument("--metadata", type=Path, help="Saved model metadata for offline planning")
        command.add_argument("--machines", type=Path, help="Project-verified machine candidate JSON")
        if name == "prepare":
            command.add_argument("--output", type=Path, default=Path("deployments"))
    command = commands.add_parser("doctor", help="Check local requirements; --online adds read-only API preflight")
    command.add_argument("--online", action="store_true")
    command.add_argument("--profile", type=Path, help="Hosting profile required for API preflight")
    command.add_argument("--bootstrap", type=Path, help="Finalized bootstrap.json; omit for template-ID mode")
    command = commands.add_parser("workspace-template", help="Export remote workspace templates locally; no credentials or uploads")
    command.add_argument("--output", type=Path, required=True, help="New directory; existing targets are never overwritten")
    command = commands.add_parser("setup-plan", help="Read-only Link/key discovery; write a credential-free plan")
    command.add_argument("--request", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True, help="New plan file")
    command = commands.add_parser("setup-apply", help="Preview persistent resource setup; --yes applies, without starting jobs")
    command.add_argument("--plan", type=Path, required=True)
    command.add_argument("--state", type=Path, required=True, help="Durable setup journal directory")
    command.add_argument("--yes", action="store_true")
    for name in ("setup-status", "setup-reconcile", "setup-cleanup"):
        command = commands.add_parser(name)
        command.add_argument("--state", type=Path, required=True)
        if name == "setup-cleanup":
            command.add_argument("--kind", choices=("link", "ssh_key"), required=True)
            command.add_argument("--yes", action="store_true", help="Delete the exact recorded created resource; SSH keys are account-scoped")
    command = commands.add_parser("bootstrap-plan", help="Read-only application/storage discovery; no prior job IDs")
    command.add_argument("--request", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True, help="New credential-free plan file")
    for name in ("bootstrap-apply", "bootstrap-credentials", "bootstrap-finish", "bootstrap-status", "bootstrap-release", "bootstrap-reconcile"):
        command = commands.add_parser(name)
        command.add_argument("--state", type=Path, required=True)
        if name == "bootstrap-apply":
            command.add_argument("--plan", type=Path, required=True)
        if name in ("bootstrap-apply", "bootstrap-credentials", "bootstrap-finish", "bootstrap-release"):
            command.add_argument("--yes", action="store_true", help="Apply the previewed action")
        if name == "bootstrap-credentials":
            command.add_argument("--include-hf-token", action="store_true", help="Provision the selected local HF_TOKEN in addition to VLLM_API_KEY")
        if name == "bootstrap-reconcile":
            command.add_argument("--job-id", required=True, help="Exact CPU job matching the unknown submission")
    command = commands.add_parser("models", help="List previously validated model types and untested candidates offline")
    command.add_argument("--type", choices=("chat", "anonymisation", "classification"))
    command.add_argument("--status", choices=("validated", "candidate"))
    for name in ("prepare-profile", "preview-profile"):
        command = commands.add_parser(name)
        command.add_argument("--profile", type=Path, required=True)
        if name == "prepare-profile":
            command.add_argument("--metadata", type=Path, help="Saved model metadata for offline planning")
            command.add_argument("--output", type=Path, default=Path("deployments"))
        else:
            command.add_argument("--bootstrap", type=Path, help="Finalized bootstrap.json instead of a serving template")
    commands.add_parser("inspect-template")
    command = commands.add_parser("deploy", help="Prepare and host from explicit CPU/nginx templates")
    command.add_argument("--profile", type=Path)
    command.add_argument("--replace", type=Path, help="Exact owned deployment whose allocation should be replaced")
    command.add_argument("--output", type=Path, default=Path("deployments"))
    command.add_argument("--reviewed", action="store_true", help="Model license and pinned runtime compatibility have been reviewed")
    command.add_argument("--auto-size", action="store_true", help="Choose from the live project B200 GPU/MIG catalog")
    command.add_argument("--bootstrap", type=Path, help="Finalized bootstrap.json; recorded for recovery/renewal/rollback")
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
    command.add_argument("--live", action="store_true", help="Add a read-only queue snapshot; does not change sizing or allocate jobs")
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
    if args.command == "workspace-template":
        from .workspace import export_workspace
        try:
            print(json.dumps(export_workspace(args.output), indent=2))
            return 0
        except OSError:
            report_error("template_export_failed", "Use a new writable directory; existing files are never overwritten.")
            return 1
    try:
        load_env()
        if args.command.startswith("bootstrap-"):
            require_hosting_adapter()
            from ucloud_workflow.client import UCloudClient
            from ucloud_workflow.settings import Settings
            from . import bootstrap
            with UCloudClient(Settings.from_env()) as client:
                if args.command == "bootstrap-plan":
                    result = bootstrap.plan_bootstrap(client, load_json(args.request))
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    with args.output.open("x", encoding="utf-8") as stream:
                        stream.write(json.dumps(result, indent=2) + "\n")
                elif args.command == "bootstrap-apply":
                    result = bootstrap.apply_bootstrap(client, load_json(args.plan), args.state, yes=args.yes)
                elif args.command == "bootstrap-credentials":
                    result = bootstrap.provision_bootstrap_credentials(client, args.state, yes=args.yes, include_hf_token=args.include_hf_token)
                elif args.command == "bootstrap-finish":
                    result = bootstrap.finish_bootstrap(client, args.state, yes=args.yes)
                elif args.command == "bootstrap-release":
                    result = bootstrap.release_bootstrap(client, args.state, yes=args.yes)
                elif args.command == "bootstrap-reconcile":
                    result = bootstrap.reconcile_bootstrap(client, args.state, args.job_id)
                else:
                    result = bootstrap.status_bootstrap(client, args.state)
            print(json.dumps(result, indent=2))
            return 0
        elif args.command.startswith("setup-"):
            require_hosting_adapter()
            from ucloud_workflow.client import UCloudClient
            from ucloud_workflow.settings import Settings
            from .resource_setup import apply_setup, cleanup_setup, plan_setup, reconcile_setup, setup_status
            with UCloudClient(Settings.from_env()) as client:
                if args.command == "setup-plan":
                    result = plan_setup(client, load_json(args.request))
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    with args.output.open("x", encoding="utf-8") as stream:
                        stream.write(json.dumps(result, indent=2) + "\n")
                elif args.command == "setup-apply":
                    result = apply_setup(client, load_json(args.plan), args.state, yes=args.yes)
                elif args.command == "setup-cleanup":
                    result = cleanup_setup(client, args.state, args.kind, yes=args.yes)
                elif args.command == "setup-reconcile":
                    result = reconcile_setup(client, args.state)
                else:
                    result = setup_status(client, args.state)
            print(json.dumps(result, indent=2))
            return 2 if result.get("state") == "uncertain" else 0
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
                if not args.bootstrap and not os.getenv("UCLOUD_TEMPLATE_JOB_ID"):
                    raise ValueError("UCLOUD_TEMPLATE_JOB_ID is required; no latest-job fallback")
                settings = Settings.from_env()
                with UCloudClient(settings) as client:
                    if args.bootstrap:
                        from .bootstrap import read_bootstrap, validate_bootstrap
                        _, template = validate_bootstrap(client, read_bootstrap(args.bootstrap), profile=profile)
                    else:
                        template = template_job_specification(client, template_job_id=settings.template_job_id)
                spec = hosting_job_specification(template, profile)
                print(json.dumps({"source_mode": "bootstrap" if args.bootstrap else "template",
                                  "template_job_id": None if args.bootstrap else settings.template_job_id, "job_submitted": False,
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
                                                  replace=args.replace, reviewed=args.reviewed, auto_size=args.auto_size,
                                                  bootstrap=args.bootstrap)
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
                        result = sync_catalog(client, live=args.live)
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
            from .diagnostics import diagnose
            result = diagnose(online=args.online, profile=args.profile, bootstrap=args.bootstrap)
            print(json.dumps(result, indent=2))
            return 0 if result["passed"] else 1
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
    except SetupOutcomeUnknownError as exc:
        report_error("resource_outcome_uncertain", str(exc))
        return 2
    except ReleasePendingError as exc:
        report_error("deployment_blocked", "Deployment blocked: " + str(exc))
        return 2
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, ImportError) as exc:
        # Do not print upstream response bodies, credentials or a stack trace.
        reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        report_error("operation_failed", reason)
        return 1
