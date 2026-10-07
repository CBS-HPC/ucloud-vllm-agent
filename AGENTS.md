# UCloud vLLM hosting agent

## Mission and reference
Use the same request-to-case-to-UCloud pattern as the operator's moody_agent,
with model hosting as the workload. Codex/Claude is the conversational agent;
the Python CLI provides deterministic planning, artifacts and verification.
Read skills/vllm-hosting/SKILL.md for model setup and WORKFLOW_CONTRACT.md for
the execution contract. Respond in the operator's language; repository text is English.
Use config/hosting.qwen-small.json and docs/deterministic-hosting.md as the tested
configuration baseline. Prefer prepare-profile/preview-profile for model/machine
changes. The default startup path is nginx initScript after CPU preparation;
interactive SHELL is for diagnostics/recovery. Read docs/automated-lifecycle.md for deploy/recover/status/restart/release/rollback/renew.
Do not equate a preview with submission; live CLI deployment/replacement passed on 2026-10-06.

## Ownership
- This is the UCloud vLLM self-hosting provider agent. Cross-provider selection and LUMI
  AITTA integration belong to CBS Model Agent: https://github.com/CBS-HPC/model-agent.
  Keep this package free of LUMI API dependencies, commands and credentials.
  The wrapper delegates to this CLI in an explicit UCloud workspace; this project
  retains its profiles, notebooks, sizing, deployment journals and lifecycle.
  The future UCloud AI fixed platform is a separate wrapper provider (`ucloud-ai`),
  not this vLLM provider (`ucloud-vllm`). Do not mix their credentials or controls.
- The operator configures the URL and nginx in a known-good UCloud template.
- UCLOUD_TEMPLATE_JOB_ID is mandatory for submission. Never fall back to the
  latest job. Inspect and preserve template mounts, application and networking.
- ucloud-api owns generic job/product selection, credentials and SSH transport.
  Consume a released package. Do not edit dependency repositories or duplicate
  their submission logic here. The product adapter uses released v0.1.6;
  hosting provisioning/recovery is implemented and unit-tested.
- This project owns HF inspection, sizing, model configuration, deployment
  evidence and the vLLM serving lifecycle. Never copy Moody's data-specific logic.

## Planning and operation
Read pyproject.toml for the installed dependency boundary and docs/ucloud-access.md
before remote actions. Use the CLI rather than reinventing its estimates/configs.
Inspect HF model metadata/card, then size weights, KV cache, runtime allowance,
system RAM and disk for the actual context length and concurrency. Report the
assumptions and alternatives; memory fit does not prove throughput or compatibility.
Unrecognized architectures, quantization, multimodal or MoE layouts need an
appropriate estimator/manual analysis, not guessed dense-model numbers.
Record the model commit and chosen vLLM release. Never enable remote repository
code without reviewing the pinned revision and obtaining the operator's decision.

## Template and runtime invariants
- Reuse template nginx/URL. Validate its upstream port against the model request;
  do not install/reconfigure/start a second nginx server by default.
- Model cache, environment and deployment evidence live on a verified mount.
  A /work prefix alone does not establish persistence.
- Start one base model per owned process/session. Multiple models need separate
  ports and explicit GPU budgets or a deliberate replacement of a serving model.
- Never aggregate MIG slice memory as if it were one device. Check CUDA visibility
  and per-device memory before launch and test tensor-parallel compatibility.
- Never change CUDA drivers, global compiler symlinks, or architecture flags by
  copying a workaround from another host. Use the verified runtime's instructions.
- Never terminate a hosting job after successful setup, a local agent exit or
  completion of endpoint checks. Record allocation expiry and renewal responsibility.
- Stop only the exact owned session/job when the operator requests that action.
  No broad process-name/port kills, shared cache clearing or implicit replacement.
- Test the actual task: chat includes SSE; PII uses scoring, masking and offsets.
  Read docs/pii-tracer.md for the task=pii profile. Test authentication rejection and the
  actual external HTTPS endpoint before calling the service publicly verified.

## Authorization and secrets
Local preparation and read-only inspection are part of ordinary setup work.
Deploy when requested within the identified target; preserve existing authorization
without repeated confirmations. Planning alone does not authorize allocating GPU
time. Ask only for missing decisions or actions outside the requested scope.
Never print tokens, private keys, environment dumps or raw credentialed responses.
Do not read .env contents into model context. Local settings may be read by code;
remote HF_TOKEN and VLLM_API_KEY both come from /work/vllm/.env (mode 0600).
Keep the operator's local project .env. Do not create duplicate credential files
or rewrite their contents unless explicitly requested.
Do not transfer local .env, use credentials as CLI arguments or commit run artifacts.

## State and maintenance
Prepared bundles live in deployments/<name>/<run-id>/, ignored by Git. A plan
is not a launch; a session is not readiness; an endpoint check is not a durable
allocation. Report the actual status, artifact path, recommendation and blockers.
Keep README, WORKFLOW_CONTRACT and TODO synchronized with behavior. v0.1.6 is
pinned and product previews are tested. Live deployment/replacement/recovery/restart were validated on the baseline;
see docs/live-validation.md for scope and remaining limits.
Ended-preparation recovery, explicit rollback and renewal-by-replacement passed
live validation on 2026-10-06; see docs/live-validation.md for fault injection and limits. Never renew or
rollback automatically after an operator stops a job. Both commands can allocate
GPU time and involve downtime; use them only when requested.
Require UCLOUD_PROJECT to match both templates before allocating any jobs.
## Model catalog and documentation
Consult `vllm-agent models` and docs/model-catalog.md before selecting a known
model. The packaged source of truth is src/ucloud_vllm_agent/data/model_catalog.json.
Keep exact parameter counts and their pinned HF metadata sources, tested machine
capacity (GPU count, per-device VRAM and RAM allowance), context/concurrency,
runtime/task, profile, notebook and validation evidence synchronized after changes.
Parameter counts alone do not establish machine fit. A tested allocation is a
validated selection for its recorded settings, not a universal minimum.
Keep untested candidates explicit: no invented machine size, endpoint, hosting
profile or validation evidence. CLAES needs Laya/runtime review and a tested
adapter; its preview's 1024-token limit must not be confused with encoder capacity.
Reinspect the full release before introducing a new pinned classification profile.

Historical validation does not establish current uptime. The 2026-10-06 validation
jobs were released; use recorded job status before reporting a live service.
Read docs/live-validation.md and docs/benchmark-results.json for measured results;
keep workload, hardware, timing boundaries and remaining limits with each claim.
README.md is the entry point; WORKFLOW_CONTRACT.md defines execution invariants;
TODO.md tracks remaining work. Update related docs when changing behavior.
The GitHub repository is private: https://github.com/CBS-HPC/ucloud-vllm-agent.
Keep credentials, detailed runtime journals, deployment bundles and notebook
outputs excluded from commits. Documentation maintenance does not authorize
starting UCloud jobs or silently updating the mounted workspace.
