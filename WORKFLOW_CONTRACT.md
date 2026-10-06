# Template-based hosting workflow

## Intake and ownership
Model setup follows moody_agent's request/configuration/case/UCloud pattern.
The operator owns UCLOUD_TEMPLATE_JOB_ID, the mounted workspace, URL and nginx.
The hosting agent owns model inspection, capacity planning, vLLM and evidence.
Ask for missing model/capability, context/concurrency or target decisions; do not
repeat already-granted deployment authorization.

## Prepare
1. Normalize a request from config/request.example.json or the user's instructions.
2. Inspect HF metadata/config at the requested revision, resolving a commit hash.
3. Review model card, license, tokenizer/chat template and selected vLLM support.
4. Size model weights and KV cache with capacity.py; compare machine candidates.
5. Record RAM/disk allowances and explain why a full GPU or MIG slice was selected.
6. Persist a unique deployment plan with remaining blockers and generated runtime.

prepare never submits a job. Unsupported memory layouts return needs_review and
no machine recommendation rather than a plausible but ungrounded dense estimate.
Built-in candidate capacity is illustrative until verified against the project.

## Template and release preflight
Require explicit UCLOUD_TEMPLATE_JOB_ID and verify project/provider/product,
application, persistent mounts, nginx upstream, public-link mapping and expiry.
Product previews use the released v0.1.6 API, preserving template resources.
Token preflight selects UCLOUD_TOKEN_ID explicitly and checks allocation coverage.
Automatic hosting provisioning/recovery remains pending: deploy exits with code 2
before any network call. Do not modify the dependency in this project.

## Runtime
For an existing authorized job, transfer only the reviewed bundle to remote_dir.
Read HF_TOKEN from /work/vllm/.env and VLLM_API_KEY from its separate restricted
serving-key file. Do not overwrite the template environment file. Provision a dedicated
versioned vLLM environment after reviewing GPU/driver compatibility. No CUDA
driver or nginx installation is part of remote.py.

Runtime preflight verifies pinned vLLM, tmux, visible CUDA devices, actual VRAM,
storage, secret-file permissions and local port availability. Verify persistent
mount and container RAM allocation separately. A named tmux session runs vLLM
detached; output is written to vllm.log. Existing owned sessions are not replaced.

## Verify and report
Use check on loopback, then the template proxy, then the actual external HTTPS
base URL. It tests expected served model, real chat, complete SSE and unauthenticated
rejection on listing/chat routes. Preserve the results in checks.json.
For non-chat capabilities use their actual API requests; chat checks are not proof
of embedding or multimodal functionality. Record streaming behavior through the
real proxy as well as the check's event timings.

State meanings:
- prepared: plan and files exist; no job submitted.
- launched: session start requested; readiness is still unverified.
- endpoint_verified: the tested endpoint passed checks.
- verification_failed: one or more checks failed.
- stopped: the exact deployment session was stopped; allocation may remain active.

Do not call a prepared plan deployed, or a session publicly ready. Record job ID,
URL, allocation expiry, renewal responsibility and exact owned session before
reporting a durable deployment. Success and local process exit never terminate
a hosting job. Stop/replacement requests apply only to their named deployment.

## Upcoming job adapter
Before enabling submission, implement tested state persistence immediately after
job creation, bounded SSH provisioning, status/recovery, and explicit stop/release.
An unknown submit outcome must block duplicate submission. Provisioning failure
must preserve job/state for inspection without silently destroying a serving job.
Reuse upstream submission/transport; implement hosting-specific lifecycle here.
