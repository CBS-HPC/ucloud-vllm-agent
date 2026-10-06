# Template-based hosting workflow

## Intake and ownership
Model setup follows moody_agent's request/configuration/case/UCloud pattern.
The operator owns UCLOUD_TEMPLATE_JOB_ID, the mounted workspace, URL and nginx.
The hosting agent owns model inspection, capacity planning, vLLM and evidence.
Ask for missing model/capability, context/concurrency or target decisions; do not
repeat already-granted deployment authorization.

## Prepare
Consult `vllm-agent models` and docs/model-catalog.md for known model types and
previous validation. This offline history is distinct from the live UCloud
machine `catalog`. Candidate entries require runtime review before a hosting
profile is introduced; a parameter count alone is not a machine recommendation.

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
Automated hosting provisioning/recovery is implemented and unit-tested; live CLI deployment/replacement passed on 2026-10-06. Require matching template/project ownership before
submission. See docs/automated-lifecycle.md. Do not modify the dependency here.

## Runtime
The default startup path is the nginx application's initScript parameter,
pointing to the uploaded init_vllm.sh after CPU preparation. The active symlink
selects the reviewed runtime bundle. Interactive SHELL is reserved for bounded
diagnostics/recovery inside the serving job. Register a WEB session once the job
is running, validate its returned public hostname and then check model readiness.

For an existing authorized job, transfer only the reviewed bundle to remote_dir.
Read both HF_TOKEN and VLLM_API_KEY from /work/vllm/.env (mode 0600).
Keep the local project .env; never upload it or create another remote key file.
Do not overwrite the template environment contents. Provision a dedicated
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
Use the deterministic Python check command; both absent and incorrect serving
keys must be rejected. Inference must return the expected served model and a
completed response; SSE requires content, a finish reason and the DONE marker.
For non-chat capabilities use their actual API requests; chat checks are not proof
of embedding or multimodal functionality. Record streaming behavior through the
real proxy as well as the check's event timings.
The supported PII profile uses scoring/masking/offset checks instead of chat or
SSE. Use `check --task pii`; its ten checks cover model identity, masking, scoring,
concurrency and missing/incorrect credentials. CLAES has no implemented runtime
task or task-specific endpoint checks yet.

State meanings:
- prepared: plan and files exist; no job submitted.
- launched: session start requested; readiness is still unverified.
- endpoint_verified: the tested endpoint passed checks.
- verification_failed: one or more checks failed.
- stopped: the exact deployment session was stopped; allocation may remain active.
- released: exact recorded owned jobs ended; artifacts and caches remain.
- replaced / rolled_back / renewed: the predecessor was retired after successor verification.

Catalog `validated` is a separate historical status, not deployment readiness.
Record exact parameters and pinned metadata sources, tested machine GPU/VRAM/RAM
capacity, dtype/context/concurrency, profile, notebook and evidence after live
validation. Keep the catalog JSON, catalog table, README and relevant task docs
consistent. An untested candidate must retain null machine/profile/runtime-task
fields until it has an appropriate reviewed and verified serving implementation.

Do not call a prepared plan deployed, or a session publicly ready. Record job ID,
URL, allocation expiry, renewal responsibility and exact owned session before
reporting a durable deployment. Success and local process exit never terminate
a hosting job. Stop/replacement requests apply only to their named deployment.

## Job adapter
The adapter implements tested state persistence immediately after
job creation, bounded SSH provisioning, status/recovery, and explicit stop/release.
An unknown submit outcome must block duplicate submission. Provisioning failure
must preserve job/state for inspection without silently destroying a serving job.
Reuse upstream submission/transport; implement hosting-specific lifecycle here.

Ended preparation jobs can be replaced during explicit recovery before activation;
archive exact ownership evidence and remove stale results before the new attempt.
Unknown submission outcomes always block another allocation. Retired deployments
cannot be revived by recover. Replacement marks its predecessor retired only
after the successor passes verification. Explicit rollback restores the reviewed
predecessor in a new allocation; explicit renewal replaces the same pinned profile
with a new duration. Both preserve caches, require downtime, and resume their
journalled bundle on retry. An operator stopping a job never triggers either action.
