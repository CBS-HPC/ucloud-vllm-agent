# UCloud vLLM agent

A Git workspace and Python CLI for asking Codex or Claude to set up Hugging Face
models on UCloud. It follows the operator's **moody_agent** workflow with model
hosting as the workload:

**Request -> model inspection -> resource estimate -> deployment bundle -> job from UCLOUD_TEMPLATE_JOB_ID -> vLLM -> verification through the template's nginx/URL.**

The operator sets up the URL and nginx in the template. The agent owns model
selection/configuration and serving. A successful hosting job stays running.

The default execution path is CPU preparation followed by nginx's Initialization
script; UCloud interactive SHELL is the diagnostics/recovery path. Start with
[the hosting profile](config/hosting.qwen-small.json) and
[deterministic workflow](docs/deterministic-hosting.md). `prepare-profile` generates
runtime and allocation settings; `preview-profile` validates the nginx template
and builds a read-only job preview. `deploy` implements the full journaled workflow;
see [deployment and recovery](docs/automated-lifecycle.md) for commands and validation limits.

Recovery can replace an ended CPU preparation attempt before activation. Explicit
`rollback` restores the previous reviewed profile; `renew --hours N` replaces an
allocation using the same pinned model and machine. These safeguards are offline
regression-tested and preserve caches. Rollback and renewal require downtime and
new allocations; their live validation remains pending.

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
- Prepare reproducible plans and a standalone remote vLLM helper.
- Prepare a model/machine hosting profile and preview its initialization-based job.
- Check model listing, chat inference, SSE completion and rejected anonymous requests.
- Inspect the configured UCloud template, preview GPU/MIG job specifications and
  check the expiry of the exact token identified by UCLOUD_TOKEN_ID.

**The GPU/product adapter uses released ucloud-api v0.1.6.** The automated CPU/GPU
lifecycle is implemented and unit-tested; template-based live validation passed on 2026-10-06. Earlier
manual hosting passed all three endpoint paths. Ownership mismatches block deployment.

## Setup on Windows

Keep the venv outside this OneDrive-backed repository, as in moody_agent:

```powershell
.\scripts\init_project.ps1
& "$env:LOCALAPPDATA\ucloud-vllm-agent\venv\Scripts\Activate.ps1"
Copy-Item .env.example .env
# Edit .env locally: project, explicit template ID and the existing HTTPS /v1 URL.
vllm-agent doctor
```

The core planning CLI uses only the standard library. Optional UCloud integration
is pinned to ucloud-workflow v0.1.6; install it with `pip install -e '.[ucloud]'`
inside this environment. Product previews use the released builder directly.

The template workspace is `/work/vllm`: nginx loads `/work/vllm/nginx.conf`, and
the existing `/work/vllm/.env` supplies HF_TOKEN. Generated runtime configuration
reads both HF_TOKEN and VLLM_API_KEY from `/work/vllm/.env` (mode 0600).
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
memory margins. See [tool comparison](docs/sizing-research.md).

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
python3 remote.py preflight
python3 remote.py start
python3 remote.py status
```

`start` checks the pinned runtime, visible GPU count/memory, disk, credentials and
port, then launches an isolated tmux session. vLLM binds to 127.0.0.1; template
nginx must run in the same job/network namespace and proxy the configured port.
No nginx changes or UCloud job termination happen in this helper. System RAM and
mounted persistence need a separate host check; the runtime report says so.

```powershell
# With VLLM_API_KEY configured locally, test the operator's actual template URL.
vllm-agent check --base-url https://YOUR-HOST/v1 --model DEPLOYMENT-NAME
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
To stop the exact deployment session when requested, run `python3 remote.py stop`
in its recorded bundle. This stops the service only; release of GPU allocation
remains a separate, explicit UCloud operation.

## Development

```powershell
python -m pip install -e '.[dev]'
python -m pytest -q
```

Read AGENTS.md, WORKFLOW_CONTRACT.md and skills/vllm-hosting/SKILL.md for operating
instructions. docs/capacity.md explains estimates; docs/ucloud-access.md tracks
the release boundary. docs/references.md records source projects and documentation.

This is a local Git repository on branch main. No GitHub remote is configured.
