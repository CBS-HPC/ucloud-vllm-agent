---
name: vllm-hosting
description: Prepare, size, launch and verify Hugging Face model hosting in this UCloud workspace using an operator-configured template job, URL and nginx.
---

# Template-based model hosting

Read [the workflow contract](../../WORKFLOW_CONTRACT.md) before running a deployment.
Use the CLI for model metadata, estimates and preparation; see
[capacity assumptions](../../docs/capacity.md) when comparing machine choices.

Gather the model/capability, total context length and concurrency from the request.
Use UCLOUD_TEMPLATE_JOB_ID explicitly. The operator already owns template URL and
nginx; verify its vLLM upstream port instead of creating another proxy.

For an ordinary request create a local request JSON and run estimate/prepare.
Inspect plan blockers before allocating resources or launching runtime. Unknown
architectures and quantization are review cases, not permission to guess memory.
Research their actual layout or propose a supported alternative when appropriate.

Automatic submission awaits the released upstream GPU API. Read
[the integration boundary](../../docs/ucloud-access.md) before remote work.
Keep existing authorization, but do not equate a prepare request with permission
to consume allocation. Run a reviewed bundle in an identified authorized job only.

Keep the hosting job alive after successful setup and agent exit. Test the actual
HTTPS endpoint and record results. A stop request targets its exact session;
releasing the UCloud job is a separate explicit operation.
