# UCloud vLLM agent

A Git workspace and Python CLI for asking Codex or Claude to set up Hugging Face
models on UCloud. It follows the operator's **moody_agent** workflow with model
hosting as the workload:

**Request → model inspection → resource estimate → deployment package → job from
UCLOUD_TEMPLATE_JOB_ID → vLLM → verification through the template's nginx/URL.**

The operator sets up the URL and nginx in the template. The agent owns model
selection/configuration and serving. A successful hosting job stays running.

## Current capabilities

- Inspect HF configuration and pin the resolved model commit without downloading weights.
- Estimate weights, KV cache, per-device VRAM, RAM and storage for context/concurrency.
- Compare editable machine candidates, including MIG versus full GPUs.
- Prepare reproducible plans and a standalone remote vLLM helper.
- Check model listing, chat inference, SSE completion and rejected anonymous requests.
- Inspect configured UCloud template metadata through the existing package.

**Automatic job submission awaits the new ucloud-api GPU release.** The `deploy`
command fails before any UCloud call. Prepared bundles can be reviewed and run in
an existing authorized job; no live UCloud deployment has been verified yet.

## Setup on Windows

Keep the venv outside this OneDrive-backed repository, as in moody_agent:

```powershell
.\scripts\init_project.ps1
& "$env:LOCALAPPDATA\ucloud-vllm-agent\venv\Scripts\Activate.ps1"
Copy-Item .env.example .env
# Edit .env locally: project, explicit template ID and the existing HTTPS /v1 URL.
vllm-agent doctor
```

The core CLI uses only the standard library. Optional read-only UCloud integration
is pinned to ucloud-workflow v0.1.5; install it with `pip install -e '.[ucloud]'`
inside this environment. The GPU adapter will be added against a released API.

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

The first estimator supports conventional dense decoder models. Quantized,
MoE, MLA, hybrid and multimodal models remain explicit review cases; the agent
must research their memory layout and vLLM support before extending the estimator.

## Remote execution after review

Use an existing authorized UCloud job while submission integration is pending.
Confirm the template's persistent mount, GPU allocation, nginx upstream port,
driver and job expiry. Upload only the prepared bundle to its exact `remote_dir`.
Provision HF_TOKEN (if needed) and VLLM_API_KEY in the remote `secret_file`; restrict
it to owner access (chmod 600). Never upload this repository's .env.

```bash
# Run inside the uploaded bundle on the selected Linux job.
# Install is explicit: it creates the versioned environment and downloads pinned vLLM.
python3 remote.py install
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
```

Check output records each result without returning model response text or secrets.
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
