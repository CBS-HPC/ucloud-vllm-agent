# CLI contract for coding-agent harnesses

Use the CLI as a subprocess with an explicit workspace. There is no native MCP
server or general hosted agent service here. A harness needs a local command tool
and instructions that distinguish planning from authorized resource use. Direct
repeated calls to provider `main()` in a long-running Python process are not the
supported public interface. CBS Model Agent delegates UCloud calls to a child
process and does not mutate its own cwd or load provider credentials.

## Invocation, settings and output

```sh
cbs-model ucloud-vllm --workspace /absolute/path/ucloud-vllm-agent models
cbs-model ucloud-vllm --workspace /absolute/path/ucloud-vllm-agent doctor
```

Use an absolute workspace path and executable from your chosen venv. Provider
relative paths (`config/local.qwen.json`, deployments, run, artifacts) resolve in
that workspace. The wrapper validates its pyproject project name. Keep one
authoritative workspace/journal per deployment; copying journals to another
computer does not share locks. Explicit caller environment overrides the provider
workspace's .env. Never put tokens in argv or print environment dumps.

Successful operational commands emit one JSON value on stdout. Help/version
are human-readable exceptions. Deployment progress is on stderr. On failure,
provider errors use a final single-line stderr record:

```json
{"schema":"ucloud.vllm.error.v1","error":{"code":"operation_failed","message":"sanitized reason"}}
```

Codes include invalid_arguments, operation_failed, deployment_blocked, resource_outcome_uncertain and
template_export_failed. Wrapper-level failures have schema cbs.model.error.v1.
Stderr may contain progress before the final error record. Accept unknown fields
and retain the raw sanitized report for diagnosis; do not parse human progress.

| Exit | Meaning |
| --- | --- |
| 0 | Command succeeded / requested checks passed. A preview is still not a deployment. |
| 1 | Operation failed, doctor requirements missing, endpoint checks failed, or no sizing recommendation. A failed check may still emit a report on stdout. |
| 2 | Invalid arguments, a review/dependency gate or an uncertain resource outcome. Inspect the error/report. |

No global result envelope replaces task-specific outputs. Doctor has schema
ucloud.vllm.diagnostics.v1: configured means local requirements passed;
preflight_passed additionally means read-only API checks passed. Even then,
runtime_verified and endpoint_verified remain false. Deployment success requires
the actual deployment/check evidence, not just a zero exit from another command.

Minimal local harness adapter (no new dependencies):

```python
import json
import subprocess
from pathlib import Path

python = Path('/absolute/path/to/venv/bin/python')  # Windows: Scripts/python.exe
workspace = Path('/absolute/path/to/ucloud-vllm-agent')
result = subprocess.run(
    [str(python), '-m', 'cbs_model_agent', 'ucloud-vllm', '--workspace',
     str(workspace), 'models'],
    cwd=workspace, capture_output=True, text=True, timeout=60, shell=False,
)
report = json.loads(result.stdout) if result.stdout.strip() else None
if result.returncode:
    raise RuntimeError('Agent command failed; inspect its sanitized stderr report')
```

The short timeout above is for offline discovery. Configure substantially longer
timeouts for deployment: queue waits, dependency installation, model downloads
and readiness checks can take over an hour. A local timeout or interrupted CLI
does not cancel remote jobs. Never automatically repeat a deployment after a
timeout. Use its authoritative journal, status and recover; unresolved submission
IDs require explicit reconciliation. A harness should persist the returned
deployment path and surface operator decisions, not invent a restart policy.

## Copyable agent instructions

> Use CBS Model Agent with the explicit UCloud provider workspace. Read its
> AGENTS.md, WORKFLOW_CONTRACT.md and onboarding/operations docs. Ask for the
> model/task, total context, concurrency and intended provider. Inspect and size
> before proposing a reviewed profile. Planning and API previews do not authorize
> CPU/GPU allocation. Deploy only within the user's requested workload. Use
> subprocess arguments, not shell-built commands. Keep credentials out of prompts,
> argv, logs and Git. Preserve existing nginx, files and template resources.
> Record exact deployment/job identity and expiry. After failure or timeout,
> inspect/recover the journal; never blindly resubmit or clear it. Leave a
> successfully hosted model running. Stop/release/replace/renew only the requested
> owned deployment. UCloud AI is a separate planned provider; do not route it
> through UCloud vLLM job controls.
> For first-time Link/key setup, use setup-plan and review before setup-apply --yes.
> Resource setup is separate from deployment and starts no jobs. Preserve upstream
> receipts and created/reused ownership. Do not infer ownership from a matching
> hostname/key or bypass unknown outcomes. Cleanup requires an exact requested
> created resource; account keys may be used by other projects/jobs.
> If the user has no template jobs, use docs/bootstrap.md and an explicit
> bootstrap-plan. Apply can allocate a bounded CPU job; credential provisioning is
> a separate selected-value stdin operation. Finish releases the owned CPU and
> emits bootstrap.json. Pass --bootstrap explicitly to first deploy/doctor/preview;
> recovery and replacements use the recorded snapshot. Never create dummy GPU
> template jobs or infer folder ownership from existence after an unknown write.

## Operation boundaries

| Operation | Effect |
| --- | --- |
| providers, models, workspace-template, doctor | Local discovery/configuration/export; no allocation. Export writes only a new local directory. |
| doctor --online, inspect-template, token-status, preview-profile, size/catalog | Read-only API/metadata requests; catalog may write local evidence. No allocation. |
| catalog --live, setup-plan | Read-only API discovery/queue snapshot and local evidence. No reservation or job allocation. |
| setup-apply, setup-cleanup | Preview by default. --yes creates/reuses or deletes the selected persistent resource; no jobs. Requires resource-specific authorization. |
| setup-status, setup-reconcile | Saved state / remote reads plus receipt reconciliation; no resource writes. Unresolved reconciliation returns exit 2. |
| bootstrap-plan, bootstrap-status | Read-only API discovery/status plus local plan output; no allocation. |
| bootstrap-apply | Preview by default; --yes creates fresh folders/uploads and a bounded CPU job, with no GPU. |
| bootstrap-credentials, bootstrap-finish, bootstrap-release | Preview by default; --yes respectively creates the fixed remote .env exclusively, verifies it and releases the owned CPU, or releases that CPU preserving storage. |
| bootstrap-reconcile | Remote reads and exact CPU submission reconciliation in the local journal; no allocation. |
| prepare/prepare-profile | Model metadata plus local bundle writes; no upload/allocation. |
| deploy, replace, rollback, renew, recover | Can create CPU/GPU jobs, upload/activate files or resume mutations. Require workload authorization. |
| restart, stop, release | Mutate the exact recorded runtime/job; stop leaves allocation charged. |
| check | Sends synthetic inference/auth tests to the endpoint; consumes serving capacity. |

Review flags express the caller's assertion; they do not perform license review
or decide authorization. API credentials, private Git access and model data-use
approval are separate prerequisites. Release packages should be pinned and updated
deliberately. See researcher-onboarding.md for install and compatibility limits.
