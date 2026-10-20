---
name: vllm-hosting
description: Prepare, size, launch and verify Hugging Face model hosting in this UCloud workspace using an operator-configured template job, URL and nginx.
---

# Template-based model hosting

Read [the workflow contract](../../WORKFLOW_CONTRACT.md) before running a deployment.
Use the CLI for model metadata, estimates and preparation; see
[capacity assumptions](../../docs/capacity.md) when comparing machine choices.

Gather the model/capability, total context length and concurrency from the request.
Consult `vllm-agent models` and [the model catalog](../../docs/model-catalog.md)
for pinned revisions, parameter counts, tested machine capacities, profiles and
notebooks. Historical validation is not current uptime or authorization to deploy.
Keep candidates separate; CLAES needs a reviewed serving path before classification
can be hosted. Use `catalog`/`size` for current UCloud product selection and sizing.
Use UCLOUD_TEMPLATE_JOB_ID explicitly. The operator already owns template URL and
nginx; verify its vLLM upstream port instead of creating another proxy.

For an ordinary request create a local request JSON and run estimate/prepare.
Inspect plan blockers before allocating resources or launching runtime. Unknown
architectures and quantization are review cases, not permission to guess memory.
Research their actual layout or propose a supported alternative when appropriate.

Product selection and automated lifecycle use released ucloud-api v0.1.7.
For first-time Link and optional account-key reservation, use the separate
[resource setup workflow](../../docs/resource-setup.md). It does not start jobs,
configure nginx or replace the mandatory template IDs. Preserve uncertain outcomes
and reused resources; never wrap persistent hosting in upstream auto-cleanup helpers.
Live CLI deployment/replacement passed on 2026-10-06; read docs/automated-lifecycle.md and
[the integration boundary](../../docs/ucloud-access.md) before remote work.
Keep existing authorization, but do not equate a prepare request with permission
to consume allocation. Run a reviewed bundle in an identified authorized job only.

Keep the hosting job alive after successful setup and agent exit. Test the actual
HTTPS endpoint and record results. A stop request targets its exact session;
releasing the UCloud job is a separate explicit operation.
After live validation, maintain the catalog's exact counts/sources, machine
capacity, dtype/context/concurrency and evidence, plus relevant task docs and TODO.
Use the task's actual checks: chat/SSE for chat, scoring/masking/offsets for PII.
