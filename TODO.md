# Remaining work

Publication note: historical operational identifiers use role labels and example URLs; measurements and runtime behavior are retained. Exact identities belong in private journals.

## Licensing (2026-10-20)

The operator selected MIT for code and CC BY 4.0 for documentation. LICENSE.md
defines the split, including configuration/code examples and notebook cells;
LICENSES/ carries the full texts. Package metadata declares the combined SPDX
expression and includes both texts in new builds. Existing tags/release assets
and provider dependency pins are unchanged. Repository visibility and publication
of historical operational details remain separate decisions. Isolated wheel and
source builds were verified to include the scope notice, both full license texts
and the SPDX metadata.

## Documentation review (2026-10-20)

Reviewed the tracked provider/wrapper guides, agent contracts/skill, environment
examples and notebook instructions against the published 0.1.5/0.1.3/0.1.7 chain.
Corrected stale bootstrap/nginx claims and source-mode examples. The canonical
researcher guide now separates API-only use, bootstrap and template-ID setup,
required/optional settings, installation, deployment and exact-job release.
The wrapper's docs/onboarding-plan.md defines the colleague-led pilot and evidence.
No runtime/dependency/credential changes or live cloud actions are part of this review.
Offline QA passed: 33 Markdown files, 102 relative links, 108 parsed CLI examples,
10 JSON files and two output-free notebooks (all 12 code cells unchanged).
The bundled hosting skill passed its validator. Runtime suites were not rerun for
these documentation-only changes; the published release evidence remains dated.

## Isolated bootstrap continuation (2026-10-20)

Work is in onboarding-sandbox-20261020 on bootstrap-onboarding; original checkouts
and deployed folder remain untouched. No-prior-job bootstrap passed live in the
operator-selected **isolated validation project** project. Read docs/bootstrap.md,
docs/bootstrap-live-validation.md and SPEC.md before continuing.

Link bootstrap-link and /<DRIVE_ID>/<NAMESPACE>/vllm were newly created with durable
ownership records. Bootstrap CPU bootstrap-cpu and preparation CPU bootstrap-preparation-cpu were released
and confirmed SUCCESS. MIG serving job bootstrap-qwen-gpu passed nginx 1.31.2 image syntax
and all seven chat/auth/SSE checks on loopback, nginx and public HTTPS, using pinned
Qwen, 4096 context, concurrency 1 and vLLM 0.31.0. Both template IDs are null.
Recorded GPU expiry: 2026-10-20 14:04:09 Europe/Copenhagen; query status before
reporting current uptime. Never renew, replace or release this job implicitly.

The local root .env remains operator-owned. Commands used confirmed non-secret
project/token IDs and the fresh URL through process overrides in ignored
config/local.operator.json; no secret file was copied or rewritten. The public
key was already registered. Only the new remote root .env was exclusively created
through selected-value SSH stdin. Existing Link existing-link remained READY/unbound.

Live preflight exposed provider HTTP 400 for missing files; fix reviewed-change uses complete
verified-parent listing and passed Windows/Linux CI. Local 146 tests passed with
two platform skips before the additional SSH polling-recovery regression; the final
local suite passed 147 tests with two platform skips. The observed local exception
left pip active; recovery reused CPU bootstrap-preparation-cpu and the
same installer, then completed serving. Preserve all journals and receipts.

Provider [v0.1.5](https://github.com/CBS-HPC/ucloud-vllm-agent/releases/tag/v0.1.5)
is published at v0.1.5 with wheel/source/checksums and passing Windows/Linux
Python 3.11/3.13 CI. Wrapper
[v0.1.3](https://github.com/CBS-HPC/model-agent/releases/tag/v0.1.3) is published
at v0.1.3 after that publication, pins provider v0.1.5 and has passing CI/17 tests.
A fresh non-editable installation of the actual 0.1.3/0.1.5/0.1.7 Git releases
passed package-origin/version checks, wrapper delegation, local bootstrap doctor,
read-only preview, existing live-job status and pip check. It allocated no jobs.
Do not repeat publication/completed checks. Original local checkouts were not pulled.

Remaining external/scoped work: independent colleague-led onboarding in their own
project, new-workspace PII, optional key registration/removal and live uncertainty
fault injection when requested. A writable existing drive remains a bootstrap
prerequisite; creating a new drive is unsupported. Lost folder acknowledgements
need provider/audit confirmation; automatic folder adoption/deletion is unsupported.

## Researcher onboarding roadmap

Updated 2026-10-20 after publication and documentation review. The release pair
is published; the next milestone is colleague-led acceptance: install this provider, connect their own
project, integrate it with a coding harness, deploy a small model and release
its allocation without access to the original operator's setup.

### 1. Finish local setup and the harness contract

- [ ] Improve first-run discovery/diagnostics for project UUID, matching token
  metadata ID and drive/CPU selection. Current guides explain manual selection;
  a guided picker and clearer SSH polling errors are usability follow-ups.
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

### 2. Consume the released ucloud-api resource-management API

Reviewed and pinned ucloud-api v0.1.7 on 2026-10-20. It provides Link management,
account public-key registration and availability snapshots. See docs/resource-setup.md
for the exact reviewed commit, consumed helpers and limits. Generic payloads and
management contracts remain upstream; no dependency repository was modified.

- [x] Review the released Link API: create/reserve, list/retrieve, ownership/scope,
  current job bindings, conflicts and deletion behavior. Confirm authorization
  requirements and whether attachment is represented through job specifications.
- [x] Review released SSH public-key discovery/registration/removal and its
  actual user/account scope. Reuse a matching registered public-key fingerprint;
  local private-key possession and working SSH still require separate checks.
- [x] Pin the reviewed release and add provider contract tests. Public-key
  registration must remain optional: existing registered keys stay supported.
- [x] Preserve the current explicit-ID/manual setup path for projects that
  already have working links, SSH registration and CPU/nginx templates.

### 3. Add explicit first-time resource setup

Link/optional-key setup is available through setup-plan/apply/status/reconcile/cleanup;
see docs/resource-setup.md. Shared-folder/uploads and no-prior-job bootstrap use
the separate docs/bootstrap.md workflow in published provider v0.1.5. Resource setup is separate
from deployment and creates no jobs.
Any setup step requiring a real job needs scoped allocation authorization.

- [x] Gather the researcher's project, desired hostname, selected public key and
  existing Link choice; export a read-only plan before explicit apply.
- [x] Extend setup intake to shared folder/application/template choices for bootstrap.
- [x] Discover/reuse existing resources or create the requested Link through the
  released API. Block occupied/foreign resources; never silently replace a route.
- [x] Optionally register only a selected public key. Keep private keys local;
  never duplicate them, upload the local .env or place secrets in command arguments.
- [x] Journal setup intent and returned resource IDs, scope, public-key fingerprint
  and whether each resource was created or reused. Reconcile uncertain outcomes;
  retries must not create duplicate links or registrations.
- [x] Guide or automate shared-folder setup and reviewed template uploads using
  released file/transport capabilities. Preserve existing nginx and secret files.
  Credential provisioning remains explicit and separate from template export.
- [x] Support two explicit setup modes: reuse known template job IDs, or bootstrap
  from reviewed application specifications when the researcher has no prior jobs.
  UCloud can submit a complete job specification without cloning a historical job;
  provider v0.1.5 implements explicit bootstrap without a prior GPU job.
- [x] For bootstrap mode, discover/validate the application version and parameter
  schema, exact products, project, mounts and link; build complete CPU and serving
  specifications through released ucloud-api capabilities. Request generic schema/
  builder improvements upstream where needed; do not invent missing parameters.
- [x] Implement a bounded CPU setup job from that specification when authorized,
  upload/prepare the reviewed files and journal its ID. Defer the GPU serving job
  until the model deployment is requested; do not allocate a dummy GPU merely to
  manufacture a template job ID. Report CPU/GPU cost and allocation lifetime.
- [x] Persist the reviewed application-spec provenance and all created job/resource
  IDs. Permit recovery from those exact records with the same ownership and
  duplicate-prevention rules as template mode. Current template mode keeps both
  explicit IDs mandatory; bootstrap must never become a latest-job fallback.
- [x] Provide a non-secret setup report and instructions for updating local
  settings; never silently rewrite the operator's .env.
- [x] Add explicit exact-resource cleanup: verify current scope/bindings, protect
  reused resources and active jobs, and delete only recorded created resources
  when requested. Job release must not implicitly delete links or SSH keys.

### 4. Validate and publish the onboarding release

- [x] Validate generic nginx syntax in the actual serving image and public
  Qwen chat/auth/SSE behavior in the isolated authorized small deployment.
- [ ] Revalidate PII in a newly bootstrapped workspace when that workload is requested.
- [x] Contract-test interrupted Link/key setup/receipt reconciliation, duplicate
  prevention, foreign/occupied Links, existing-key reuse, optional key omission,
  exact cleanup, lost delete acknowledgements and preserved credentials.
- [x] Live-test separate Link setup, bootstrap folders/uploads/credentials, CPU
  finish and Qwen deployment in the identified authorized project. Existing key
  reuse was checked; optional registration/removal was not requested or tested.
- [x] Add Windows/Linux CI matrices and isolated wheel asset-export checks.
  Test results must be checked for each release; colleague-led live onboarding
  remains a separate acceptance step below.
- [ ] Have a colleague follow the guide using a different project/workspace and
  record all undocumented prerequisites. Validate one small model through release.
- [x] Publish a provider release with these changes, then update CBS Model Agent's
  pinned provider dependency and onboarding links in its own reviewed change.
- [x] Publish a short operations guide: costs, allocation expiry, renewal downtime,
  stop versus release, failures retaining allocations and support responsibilities.

UCloud AI remains a separate future managed provider in CBS Model Agent. It must
have its own access/authentication/model-use guide, without inheriting self-hosted
nginx, SSH, template-job or GPU-selection prerequisites.

### Previous published checkpoint (2026-10-20)

Historical snapshot before v0.1.5; its pending bootstrap statements are superseded
by the current continuation above. Keep it as release history, not current tasks.

New work consumes reviewed ucloud-api v0.1.7: independent Link/key plan/apply/
status/reconciliation/cleanup and opt-in catalog --live. No cloud jobs/resources
were created for implementation/testing. Provider v0.1.4 (v0.1.4) and wrapper
v0.1.2 (v0.1.2) are published with wheels/source/checksums and passing Windows/Linux
CI on Python 3.11/3.13. The wrapper pin was updated after provider publication.
Do not repeat publication or completed validation; inspect GitHub state first.
Local validation: 128 tests passed, one platform skip; wheel/source builds and
offline installed-layout template export passed. Source packaging includes the new
setup guide/example and excludes local credentials and operational journals.
The fresh external venv installed the actual 0.1.2/0.1.4/0.1.7 release chain and
passed delegation, missing-settings doctor, CLI help, packaged asset export and
mocked read-only resource planning. Seventeen wrapper tests passed locally.

Bootstrap is still unimplemented. v0.1.7's application-aware resource helper
obtains resolved application metadata from a prior job, while its low-level builder
accepts complete specifications. A no-prior-job adapter still needs reviewed CPU/
nginx application schemas, mount/product/link validation and provenance. Do not
invent those schemas, treat setup recipes as payloads or create a dummy GPU job.
Generic discovery/schema improvements, if needed, belong upstream. Shared-folder
setup, credentials/uploads and colleague-led live acceptance remain pending.

### Previous published checkpoint (2026-10-19)

Historical snapshot before v0.1.4/v0.1.5; use the current continuation for status.

Independent local onboarding work is published: provider v0.1.3 (v0.1.3) and
wrapper v0.1.1 (v0.1.1), each with wheel/source/checksums and passing Windows/Linux
CI on Python 3.11/3.13. Locally, 110 provider tests passed with one platform skip;
17 wrapper tests passed. A fresh venv installed the real released dependencies
and a new provider checkout, then passed offline discovery, missing-settings
doctor, template export and synthetic profile preparation. Generic nginx syntax
passed against Ubuntu's nginx package, not the actual UCloud serving image.
No live jobs/resources were created during this work.
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
- [x] Validate the generic nginx configuration in the supported UCloud image and
  through public chat/auth/SSE checks. New-workspace PII remains a separate workload.

- [x] Separate UCloud hosting from cross-provider orchestration. CBS Model Agent
  owns the LUMI integration; this provider keeps its deterministic UCloud workflow.

- [x] Consume released ucloud-api v0.1.7 for GPU/MIG products, submission and separate resource setup.
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
