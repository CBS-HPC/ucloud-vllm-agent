# UCloud vLLM agent

The **UCloud vLLM** self-hosting provider (`ucloud-vllm`) for
[CBS Model Agent](https://github.com/CBS-HPC/model-agent).
This repository owns UCloud model sizing, hosting and lifecycle. Cross-provider
selection and LUMI AITTA integration live in the wrapper project. This CLI remains
usable independently; it has no LUMI dependency or credential requirement.
The future UCloud AI fixed inference platform is a separate provider (`ucloud-ai`).

**New researcher:** start with [installation and first deployment](docs/researcher-onboarding.md).
It covers the published wrapper v0.1.3 / provider v0.1.5 pair, required access
and settings, and the choice between bootstrap and existing templates.

A Git workspace and Python CLI for asking Codex or Claude to set up Hugging Face
models on UCloud. It follows the operator's **moody_agent** workflow with model
hosting as the workload:

**Request -> model inspection -> resource estimate -> deployment bundle -> explicit template or finalized bootstrap specification -> vLLM -> HTTPS verification.**

For an existing setup, the operator supplies template IDs and its nginx/URL.
For a new project, [bootstrap](docs/bootstrap.md) prepares a fresh persistent folder
and packaged nginx configuration through a bounded CPU job without prior job IDs.
The agent owns model selection/configuration and serving. A successful hosting job stays running.

The default execution path is CPU preparation followed by nginx's Initialization
script; UCloud interactive SHELL is the diagnostics/recovery path. Start with
[the hosting profile](config/hosting.qwen-small.json) and
[deterministic workflow](docs/deterministic-hosting.md). `prepare-profile` generates
runtime and allocation settings; `preview-profile` validates the selected serving
source and builds a read-only job preview. `deploy` implements the full journaled workflow;
see [deployment and recovery](docs/automated-lifecycle.md) for commands and validation limits.

Recovery can replace an ended CPU preparation attempt before activation. Explicit
`rollback` restores the previous reviewed profile; `renew --hours N` replaces an
allocation using the same pinned model and machine. These safeguards passed live
validation and preserve caches. Rollback and renewal require downtime and new
allocations; measured outages are recorded in [live validation](docs/live-validation.md).

Use `vllm-agent models` for the [model catalog](docs/model-catalog.md): tested chat
and anonymisation models, plus classification candidates. It records pinned
revisions, parameter counts, machine capacities, input limits and test evidence.

| Model type | Model | Parameters | Tested UCloud selection |
| --- | --- | ---: | --- |
| Chat | Qwen2.5-1.5B-Instruct | 1.54B | 1 × B200 MIG 1g.23gb; 20.5 GiB VRAM, 30 GiB RAM allowance |
| Anonymisation | PII-Tracer-vLLM | 596M | 1 × B200 MIG 1g.23gb; 20.5 GiB VRAM, 30 GiB RAM allowance |
| Classification candidate | CLAES preview | 322M | Runtime review and sizing pending |

These selections were tested with bfloat16 and 4096-token context; recorded
concurrency is 1–2 for Qwen and 2 for PII. They are not universal minimums.
A validated entry is historical evidence, not a current uptime claim. Jobs from
the 2026-10-06 session were released; the later bootstrap trial has its own recorded
expiry. Use deployment status before reporting uptime. Deploying again is explicit.

```powershell
vllm-agent models --status validated
vllm-agent models --type classification --status candidate
```

The offline model catalog is distinct from `vllm-agent catalog`, which reads
the project's current UCloud machine products and wallets.

The full CLI workflow, replacement, recovery and restart passed live tests on
2026-10-06. See [live validation](docs/live-validation.md). The Qwen deployment
passed all seven checks through loopback, nginx and public HTTPS. See [workspace evidence/context](docs/workspace-readme.md)
for the dated job and expiry; that record is not a current uptime claim.

For an interactive client test, open [notebooks/test_model.ipynb](notebooks/test_model.ipynb)
in Jupyter and run the cells from top to bottom. It reads the local `.env` and
hosting profile, then tests model listing, chat, streaming and incorrect-key rejection.
The first cell installs the pinned client dependencies into your notebook kernel.

For the hosted PII classifier, use [notebooks/test_pii_tracer.ipynb](notebooks/test_pii_tracer.ipynb)
to edit and submit a synthetic email. It shows spans, sensitivity and masked text.
See [PII-Tracer hosting](docs/pii-tracer.md): this service uses scoring/masking APIs
rather than the chat notebook.

## Current capabilities

- Inspect HF configuration and pin the resolved model commit without downloading weights.
- Estimate weights, KV cache, per-device VRAM, RAM and storage for context/concurrency.
- Compare editable machine candidates, including MIG versus full GPUs.
- List tested models and candidates with parameter counts, machine capacities,
  profiles, notebooks and evidence.
- Prepare reproducible plans and a standalone remote vLLM helper.
- Prepare a model/machine hosting profile and preview its initialization-based job.
- Check model listing, chat inference, SSE completion and rejected anonymous requests.
- Check PII scoring, span offsets, masking, concurrency and authentication rejection.
- Deploy through CPU preparation, nginx initialization and public-route registration;
  recover, restart, replace, roll back, renew by replacement and release exact owned jobs.
- Preserve model and compilation caches, and benchmark chat/PII through public HTTPS.
- Inspect the configured UCloud template, preview GPU/MIG job specifications and
  check the expiry of the exact token identified by UCLOUD_TOKEN_ID.
- Plan/apply/reconcile separate persistent Link and optional account public-key
  setup, protecting reused resources and uncertain outcomes. No jobs are started.
- Add a timestamped queue snapshot with `catalog --live`; availability remains
  distinct from memory fit, entitlement and a successful allocation.
- Bootstrap a fresh namespace, starter files and bounded CPU setup from reviewed
  application definitions, then deploy without prior job IDs. Credentials remain
  a separate explicit exclusive-write action; lifecycle pins the source snapshot.

**The adapter uses released ucloud-api v0.1.7.** The automated CPU/GPU
lifecycle is implemented and unit-tested; template-based live validation passed on 2026-10-06. Earlier
manual hosting passed all three endpoint paths. Ownership mismatches block deployment.
The [2026-10-20 isolated bootstrap trial](docs/bootstrap-live-validation.md) also
passed actual-image nginx syntax and all seven checks on loopback, nginx and
public HTTPS, using a fresh folder on an existing drive and no template IDs. Colleague-led acceptance
remains separate.

## Setup on Windows

**New researcher:** follow [installation and first deployment](docs/researcher-onboarding.md).
For other coding-agent harnesses, use the [subprocess CLI contract and instruction
snippet](docs/harness-integration.md). Day-to-day costs, expiry and recovery are in
[operations](docs/researcher-operations.md).

For first-time resource reservation, use [Link and optional public-key setup](docs/resource-setup.md).
The remaining [onboarding roadmap](TODO.md#researcher-onboarding-roadmap) covers
additional scoped live tests and independent researcher acceptance. The
[bootstrap guide](docs/bootstrap.md) covers first-time shared folders/uploads and
explicit credential provisioning. Template mode requires both explicit IDs;
bootstrap mode requires its finalized artifact. Resource setup alone does not
configure or validate an inference endpoint.

The [UCloud workspace and job templates](docs/ucloud-workspace-template.md)
describe packaged assets and the alternative manual template-ID setup.
They include the remote nginx.conf, credential-free .env.example, initialization
script, generic workspace README and CPU/GPU template recipes. Export them locally
with `vllm-agent workspace-template --output artifacts/ucloud-workspace`.
The existing root `.env.example` is for local credentials/settings, not remote upload.

The [onboarding guide](docs/researcher-onboarding.md) is the complete Windows/Linux
install path. The following shorter example is for **provider-only template mode**
from this checkout. Keep the venv outside synchronised storage:

```powershell
.\scripts\init_project.ps1
& "$env:LOCALAPPDATA\ucloud-vllm-agent\venv\Scripts\Activate.ps1"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
python -m pip install -e '.[ucloud]'
# Edit .env: project, both explicit template IDs, token/ID, existing URL and serving key.
vllm-agent doctor
```

The core planning CLI uses only the standard library. Optional UCloud integration
is pinned to ucloud-workflow v0.1.7; install it with `pip install -e '.[ucloud]'`
inside this environment. Product previews use the released builder directly.

`doctor` exits nonzero for missing local prerequisites; it never allocates a job.
After configuring a reviewed profile, `doctor --online --profile FILE` adds
read-only source/project/link/token checks. Bootstrap users must add
`--bootstrap run/bootstrap/first/bootstrap.json` to doctor, preview-profile and
first deploy; omitting it selects template mode. Neither doctor mode verifies remote
credentials, nginx syntax or model readiness; inspect the report's limits.

The template workspace is `/work/vllm`: nginx loads `/work/vllm/nginx.conf`.
Generated runtime configuration reads both HF_TOKEN and VLLM_API_KEY from
the existing `/work/vllm/.env` (mode 0600).
Keep the local project `.env` for UCloud configuration and client verification.
The local file is never uploaded. UCLOUD_HF_ENV_FILE can override the remote
workspace environment path; it supplies both keys by default.

UCLOUD_PUBLIC_BASE_URL accepts a bare hostname or full HTTPS URL; plans normalize
it to an HTTPS API base ending in /v1. This is formatting, not proof that TLS or
the proxy route works. The actual endpoint must still pass verification.

```powershell
vllm-agent token-status --hours 4
vllm-agent preview-job --hours 4
# No product flags keeps the explicit template's GPU product.
# A product override requires --product-id, --product-category and --product-provider.
```

Token checks select UCLOUD_TOKEN_ID from non-secret API metadata and require it
to outlast the requested allocation plus one hour. They do not create or rotate
tokens. Neither command submits a job. VLLM_API_KEY may remain empty during
planning, but launching and authenticated endpoint checks require it.

## Ask the agent

> Set up <owner/model> using my configured template. Estimate the GPU machine
> required for 8 concurrent requests with an 8192-token total context.

> Prepare two alternatives for this model: shorter context on a smaller allocation
> and longer context on a larger allocation. Use my existing nginx and URL.

`context_length` includes input plus generated tokens. Machine examples are sizing
candidates, not a live availability/price catalog or a guarantee of performance.

## Prepare a deployment

```powershell
Copy-Item config/request.example.json config/local.request.json
# Edit the HF model, context/concurrency and a verified exact vLLM version.
vllm-agent estimate --request config/local.request.json
vllm-agent prepare --request config/local.request.json
```

HF metadata is fetched read-only; gated models may require HF_TOKEN. Preparation
writes `plan.json`, `checks.json` and a README to deployments/<name>/<run-id>/.
When memory fits, it also generates `runtime.json` and a standalone `remote.py`.
The example has no vLLM version selected intentionally; review GPU compatibility
before selecting one. Each blocker remains visible in the plan.

Use `--metadata path/to/saved-metadata.json` for offline preparation, and
`--machines path/to/project-machines.json` for project-specific candidates.
The saved model metadata contains model, pinned revision, parameters and config;
it must match the requested model. The machine JSON format is shown in
src/ucloud_vllm_agent/data/machines.json. Verify candidate capacities and product
identity against the actual project before submission.

The estimator supports conventional dense MHA/GQA decoders, including AWQ/GPTQ/FP8
with pinned checkpoint sizes. MoE, MLA, recurrent hybrid, multimodal and unknown
quantization remain review cases. `catalog` maps project products to conservative
B200 full-GPU/MIG capacities; `size` returns minimum/recommended machines and
memory margins. PII-Tracer uses a separate encoder activation estimate without
decoder KV cache. CLAES classification is a candidate, not an implemented serving
task. See [capacity assumptions](docs/capacity.md) and [tool comparison](docs/sizing-research.md).

## Automated hosting and lifecycle

These examples use existing template IDs. For a new workspace, finish
[bootstrap](docs/bootstrap.md) and pass its finalized `--bootstrap FILE` to deploy.
Recovery and subsequent lifecycle commands use the recorded source automatically.

```powershell
vllm-agent size --profile config/hosting.pii-tracer.json
# Allocate only after reviewing the pinned model, license and runtime:
vllm-agent deploy --profile config/hosting.pii-tracer.json --auto-size --reviewed
vllm-agent status --deployment deployments/NAME/RUN
vllm-agent recover --deployment deployments/NAME/RUN
vllm-agent rollback --deployment deployments/FAILED_REPLACEMENT/RUN
vllm-agent renew --deployment deployments/NAME/RUN --hours 4
vllm-agent release --deployment deployments/NAME/RUN
```

Use the exact deployment path returned by the preceding operation. `stop` stops
the owned service while retaining the allocation; `release` ends the recorded jobs.
Recovery blocks unknown submission outcomes until their exact job ID is reconciled.
Rollback and renewal create replacement allocations and involve downtime;
renewal does not extend a job in place or run automatically. See
[lifecycle commands and recovery](docs/automated-lifecycle.md).

## Remote execution after review

Prefer the [automated lifecycle](docs/automated-lifecycle.md). For manual diagnostics, use an existing authorized UCloud job.
Confirm the template's persistent mount, GPU allocation, nginx upstream port,
driver and job expiry. Upload only the prepared bundle to its exact `remote_dir`.
The runtime reads HF_TOKEN from the existing template `hf_env_file`. Provision
VLLM_API_KEY together with HF_TOKEN in the workspace `.env` and restrict that
file to owner access (chmod 600). Use the same key for local endpoint checks. Never upload this
repository's .env or overwrite the template's HF token file.

```bash
# Run inside the uploaded bundle on the selected Linux job.
# Environment setup belongs to the CPU preparation workflow.
/work/vllm/.venv/bin/python remote.py preflight
/work/vllm/.venv/bin/python remote.py start
/work/vllm/.venv/bin/python remote.py status
```

`start` checks the pinned runtime, visible GPU count/memory, disk, credentials and
port, then launches an isolated tmux session. vLLM binds to 127.0.0.1; template
nginx must run in the same job/network namespace and proxy the configured port.
No nginx changes or UCloud job termination happen in this helper. System RAM and
mounted persistence need a separate host check; the runtime report says so.

```powershell
# With VLLM_API_KEY configured locally, test the operator's actual template URL.
vllm-agent check --base-url https://YOUR-HOST/v1 --model DEPLOYMENT-NAME
vllm-agent check --task pii --base-url https://YOUR-HOST/v1 --model pii-tracer
# The same deterministic connectivity smoke test through Python:
python -m ucloud_vllm_agent check --base-url https://YOUR-HOST/v1 --model DEPLOYMENT-NAME --output artifacts/checks.json
```

Check output records each result without returning model response text or secrets.
Seven checks verify the expected model, completed chat inference, completed SSE
inference, and rejection of both missing and incorrect keys on model-listing and
chat endpoints. Fixed requests and explicit assertions make this a repeatable
connectivity test; generated wording and measured timings need not be identical.
The command exits with 0 when every check passes, 1 on failed verification,
and writes a JSON report suitable for agent workflows. A passing nginx health
page alone does not count as working LLM connectivity.
Streaming timings are recorded; they alone do not establish absence of buffering.
To stop the exact deployment session when requested, run `/work/vllm/.venv/bin/python remote.py stop`
in its recorded bundle. This stops the service only; release of GPU allocation
remains a separate, explicit UCloud operation.

## Development

```powershell
python -m pip install -e '.[dev,ucloud]'
python -m pytest -q
```

Read AGENTS.md, WORKFLOW_CONTRACT.md and skills/vllm-hosting/SKILL.md for operating
instructions. docs/capacity.md explains estimates; docs/ucloud-access.md tracks
the release boundary. docs/references.md records source projects and documentation.

The private repository is [CBS-HPC/ucloud-vllm-agent](https://github.com/CBS-HPC/ucloud-vllm-agent),
with GitHub CI for Python 3.11 and 3.13. Credentials, deployment bundles and detailed
runtime records stay outside Git; saved notebooks contain no outputs.

Further reading: [model catalog](docs/model-catalog.md),
[benchmark protocol](docs/benchmarks.md), [measured live validation](docs/live-validation.md)
and [remaining work](TODO.md). Controlled Qwen startup measured 148 seconds cold
and 45 seconds warm; PII full-context load passed with two clients. These are
dated results for the recorded workload and hardware.

## License

Code, configuration/runtime templates and code examples use MIT. Documentation
uses CC BY 4.0. Notebook code cells use MIT; notebook prose uses CC BY 4.0.
See [license scope and attribution](LICENSE.md) and the full texts in
[LICENSES/](LICENSES/). Dependencies and model weights retain their own licenses.
