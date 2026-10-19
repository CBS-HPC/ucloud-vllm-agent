# Remaining work

## Researcher onboarding roadmap

Updated 2026-10-19 after the adoption audit. The next milestone is a researcher
onboarding release: a colleague can install this provider, connect their own
project, integrate it with a coding harness, deploy a small model and release
its allocation without access to the original operator's setup.

### 1. Finish local setup and the harness contract

- [x] Package remote nginx/environment/startup/README templates and CPU/GPU job
  recipes; export locally without credentials, uploads or overwrites.
- [x] Provide one clean-machine installation path: required private-repository
  access, Git, supported local Python/OS, OpenSSH, environment activation and
  provider workspace creation. Explain source checkout versus installed package.
- [x] Make doctor distinguish installed/configured/ready, report actionable
  missing requirements and fail when deployment prerequisites are absent.
  Include the preparation template, SSH identity and supported runtime baseline.
- [x] Add a read-only readiness check for token lifetime, both templates' project
  ownership, shared storage, public-link mapping and application compatibility.
  Clearly distinguish local checks from checks requiring a setup job.
- [x] Document subprocess CLI invocation as the initial harness integration path:
  cwd, environment, commands, allocation boundaries, timeouts and recovery records.
  Send progress to stderr; define stable JSON results/errors and exit codes.
- [x] Fix/test wrapper workspace isolation through a separate child per invocation.
  Repeated direct provider main() embedding remains unsupported. The audit's
  A-to-B settings leak is covered by a regression using two real subprocesses.
- [x] Add a copyable harness instruction snippet and one end-to-end synthetic
  example from request to preview, explicit deployment, verification and release.

### 2. Consume the forthcoming ucloud-api resource-management release

Dependency gate: the operator is developing UCloud Link management in ucloud-api;
SSH public-key management is a possible addition, not a confirmed capability.
The installed dependency remains v0.1.6 until a new release is reviewed and pinned.
Do not implement generic resource APIs here or require unreleased dependency code.

- [ ] Review the released Link API: create/reserve, list/retrieve, ownership/scope,
  current job bindings, conflicts and deletion behavior. Confirm authorization
  requirements and whether attachment is represented through job specifications.
- [ ] If released, review SSH public-key discovery/registration/removal and its
  actual user/account scope. Reuse a matching registered public-key fingerprint;
  local private-key possession and working SSH still require separate checks.
- [ ] Pin the reviewed release and add provider contract tests. Public-key
  registration must remain optional: existing registered keys stay supported.
- [ ] Preserve the current explicit-ID/manual setup path for projects that
  already have working links, SSH registration and CPU/nginx templates.

### 3. Add explicit first-time resource setup

This is a planned workflow, not an available command. Resource setup is separate
from model deployment; reserving a link or registering a key must not allocate a
GPU. Any setup step requiring a real job needs scoped allocation authorization.

- [ ] Gather the researcher's project, desired hostname, local public key, shared
  folder and existing resource/template choices; show a plan before mutations.
- [ ] Discover/reuse existing resources or create the requested Link through the
  released API. Block occupied/foreign resources; never silently replace a route.
- [ ] Optionally register only a selected public key. Keep private keys local;
  never duplicate them, upload the local .env or place secrets in command arguments.
- [ ] Journal setup intent and returned resource IDs, scope, public-key fingerprint
  and whether each resource was created or reused. Reconcile uncertain outcomes;
  retries must not create duplicate links or registrations.
- [ ] Guide or automate shared-folder setup and reviewed template uploads using
  released file/transport capabilities. Preserve existing nginx and secret files.
  Credential provisioning remains explicit and separate from template export.
- [ ] Support two explicit setup modes: reuse known template job IDs, or bootstrap
  from reviewed application specifications when the researcher has no prior jobs.
  UCloud can submit a complete job specification without cloning a historical job;
  this agent currently implements only the template-ID path.
- [ ] For bootstrap mode, discover/validate the application version and parameter
  schema, exact products, project, mounts and link; build complete CPU and serving
  specifications through released ucloud-api capabilities. Request generic schema/
  builder improvements upstream where needed; do not invent missing parameters.
- [ ] Start a bounded CPU setup job from that specification when authorized,
  upload/prepare the reviewed files and journal its ID. Defer the GPU serving job
  until the model deployment is requested; do not allocate a dummy GPU merely to
  manufacture a template job ID. Report CPU/GPU cost and allocation lifetime.
- [ ] Persist the reviewed application-spec provenance and all created job/resource
  IDs. Permit recovery from those exact records with the same ownership and
  duplicate-prevention rules as template mode. Current template mode keeps both
  explicit IDs mandatory; bootstrap must never become a latest-job fallback.
- [ ] Provide a non-secret setup report and instructions for updating local
  settings; never silently rewrite the operator's .env.
- [ ] Add explicit exact-resource cleanup: verify current scope/bindings, protect
  reused resources and active jobs, and delete only recorded created resources
  when requested. Job release must not implicitly delete links or SSH keys.

### 4. Validate and publish the onboarding release

- [ ] Validate generic nginx syntax in the supported serving image and public
  chat/PII/auth/SSE behavior in an authorized small deployment.
- [ ] Test interrupted setup/reconciliation, duplicate prevention, foreign/occupied
  links, existing-key reuse, absent optional key support and preserved credentials.
- [x] Add Windows/Linux CI matrices and isolated wheel asset-export checks.
  Test results must be checked for each release; colleague-led live onboarding
  remains a separate acceptance step below.
- [ ] Have a colleague follow the guide using a different project/workspace and
  record all undocumented prerequisites. Validate one small model through release.
- [ ] Publish a provider release with these changes, then update CBS Model Agent's
  pinned provider dependency and onboarding links in its own reviewed change.
- [x] Publish a short operations guide: costs, allocation expiry, renewal downtime,
  stop versus release, failures retaining allocations and support responsibilities.

UCloud AI remains a separate future managed provider in CBS Model Agent. It must
have its own access/authentication/model-use guide, without inheriting self-hosted
nginx, SSH, template-job or GPU-selection prerequisites.

### Continuation checkpoint (2026-10-19)

Independent local onboarding work is implemented; provider v0.1.3 and wrapper
v0.1.1 are the intended release pair. Verify release/CI status before assuming
publication is complete. No live jobs/resources were created during this work.
The latest upstream release checked was ucloud-api v0.1.6; Link/key provisioning
and application-spec bootstrap are still unimplemented. A future continuation
should first inspect new released API capabilities, then tackle sections 2–3.
Do not repeatedly re-run completed offline tests or allocate jobs merely to make
an unattended continuation appear active. Live UCloud validation and a colleague's
independent project need an identified, authorized target/workload. Keep those
items pending until that evidence is available.

## Existing implementation and further workload development

- [x] Packaged remote workspace templates: nginx.conf, remote .env.example,
  shared initialization source, generic README and CPU/GPU setup recipes.
  Offline export refuses overwrites; source/code inventory and setup guide included.
- [ ] Validate the new generic nginx configuration in the supported UCloud image
  and through public chat/PII/auth/SSE checks before recommending live adoption.

- [x] Separate UCloud hosting from cross-provider orchestration. CBS Model Agent
  owns the LUMI integration; this provider keeps its deterministic UCloud workflow.

- [x] Consume released ucloud-api v0.1.6 for GPU/MIG products and submission.
- [x] Deterministic profile, pinned HF revision, nginx initScript and endpoint tests.
- [x] Compare llm-checker, llmfit, GPUStack, Accelerate and Can I Use LLM.
  Decision and sources: docs/sizing-research.md. No required external sizing tool.
- [x] Dense MHA/GQA sizing with quantized checkpoint bytes, explicit KV dtype,
  context/concurrency, per-device limits, RAM/disk and minimum/recommended machines.
- [x] Project wallet/product catalog mapping for B200 full GPU and 1g.23gb MIG.
- [x] CPU-first preparation, reviewed uploads, environment validation/model cache,
  GPU submission, initialization and WEB registration in one deploy command.
- [x] Durable submission intent/job IDs, operation lock, recovery/reconciliation,
  status, exact-session restart/stop, replacement and exact-job release.
- [x] Runtime-specific persistent vLLM/FlashInfer/Triton/TorchInductor/CUDA caches.
- [x] Numeric startup capacity extraction and three-path checks in verification.
- [x] Manual Qwen hosting on B200 MIG passed loopback/nginx/public checks.
- [x] Full live CLI deployment, replacement, recovery, restart and exact-job release.
  Evidence and remaining limits: docs/live-validation.md.
- [x] Observe model and compilation-cache reuse across GPU jobs; measure restarts.
- [x] Controlled cold/warm compilation startup comparison with identical engine
  configuration in the same job: 148.089 seconds cold, 45.176/45.162 seconds warm.
- [x] Baseline chat and concurrent PII load, including exact 4096-token inputs;
  sampled device memory supports existing conservative runtime allowances.
  Numeric evidence and limits: docs/benchmark-results.json and docs/live-validation.md.
- [ ] Long-duration load and broader model/hardware calibration when workloads require it.
- [x] PII-Tracer bidirectional token-classification deployment, authenticated scoring/masking,
  encoder-specific sizing, full-context checks and synthetic-email notebook.
- [ ] Specialized MoE/MLA/recurrent/multimodal sizing when workloads require it.
- [ ] Additional GPU families and multi-MIG parallelism need hardware/runtime evidence.
- [x] Recover ended CPU preparation stages automatically, with archived ownership
  evidence, distinct attempts and stale-result removal; unknown submissions block retries.
- [x] Explicit rollback to the reviewed predecessor and renewal by same-profile
  replacement; durable retry/resume without duplicate allocations. Live and regression-tested.
- [x] Live validation of ended-preparation recovery, rollback and renewal, including
  repeated-command reuse; controlled CPU termination exercised the expiry recovery branch.
- [ ] Automatic scheduled renewal and transactional replacement without downtime.
  Explicit replacement/rollback/renewal currently require downtime and new allocations.
- [x] Published to private GitHub repository CBS-HPC/ucloud-vllm-agent with CI;
  credentials and runtime artifacts are excluded.
- [x] Offline model catalog of tested chat/anonymisation models and classification
  candidates, including pinned parameter counts/sources, tested GPU/VRAM/RAM
  capacity, profiles/notebooks and the inspected CLAES preview revision.
- [ ] Review CLAES's full release, serving dependencies/API, sizing and Danish task
  fixtures before adding hosting support; no classification model has been hosted yet.
