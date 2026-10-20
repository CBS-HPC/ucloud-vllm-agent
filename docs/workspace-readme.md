# UCloud vLLM workspace

This document retains sanitized, dated validation history. Job names are role
labels; URLs and run/cache identifiers are examples or placeholders. Measurements
and pinned model revisions are retained. Consult private journals for exact
operational identities. For a new project, export the generic README and starter
files described in [workspace templates](ucloud-workspace-template.md).

This shared folder contains the persistent files used to prepare and host
Hugging Face models with vLLM behind the operator's nginx server on UCloud.
It is the runtime workspace for the **UCloud vLLM agent** Git project, operated
through Codex/Claude using the repository's AGENTS.md instructions.

## How the jobs use this folder

The CPU preparation job and GPU serving job mount the same UCloud Files folder
at `/work/vllm`. Files here survive job termination. Processes and packages
installed into a container's system directories do not.

1. An SSH-capable CPU preparation job uploads reviewed runtime files and prepares
   the Python environment. Its template is configured locally through
   `UCLOUD_PREPARATION_TEMPLATE_JOB_ID`.
2. The GPU serving job uses `UCLOUD_TEMPLATE_JOB_ID`, preserving the operator's
   nginx configuration, public URL and mounts. The nginx application does not
   support SSH; its validated Initialization script starts vLLM inside the GPU job.
3. CUDA checks and model-serving tests run on the GPU job. Installing packages
   on a CPU job alone does not establish GPU or serving-image compatibility.

The automatic two-stage workflow is implemented and unit-tested; live CLI deployment/replacement passed on 2026-10-06. A file
bundle or installed environment does not mean that a model is running.

## Files and directories

| Path | Purpose |
| --- | --- |
| `README.md` | Context for this mounted workspace. Maintained from `docs/workspace-readme.md` in the agent repository. |
| `.venv/` | Prepared Python virtual environment. Use `.venv/bin/python` or activate with `source .venv/bin/activate`. |
| `.env` | Operator-managed HF_TOKEN and VLLM_API_KEY, mode 0600. Single remote credential source; never print, commit or overwrite its contents implicitly. |
| `nginx.conf` | Operator-managed proxy configuration loaded by the nginx job. Inspect routing before selecting a vLLM port. |
| `init_vllm.sh` | Default nginx Initialization script; validates the environment and launches the active deployment in the background. |
| `active` | Symlink selecting the reviewed deployment bundle for the next startup. |
| `bootstrap/` | Preparation scripts, agent wheel, installation logs and verification evidence, grouped by preparation job. |
| `deployments/<name>/<run-id>/` | Location used by prepared deployment bundles for `runtime.json`, `remote.py`, state and `vllm.log`; created when bundles are uploaded. |
| `cache/huggingface/` | Persistent pinned model cache (`HF_HOME`). |
| `cache/kernels/<hash>/` | Persistent compilation caches separated by runtime/CUDA/driver/GPU compatibility evidence. |

Some paths are created only when the corresponding stage runs. Runtime bundles
may specify a versioned environment instead of `.venv`; check `runtime.json`
before starting anything.

## Preparation verified on 2026-10-06

The environment at `/work/vllm/.venv` was installed and checked in a
`coder-python` 1.89.1 preparation job:

- Python 3.12; vLLM 0.31.0; PyTorch 2.13.0 with CUDA runtime 13.0.
- Dependency consistency and vLLM import passed.
- A CUDA tensor operation passed on a B200 MIG device.
- The original `.env` and `nginx.conf` were preserved.
- Evidence is in `bootstrap/job-preparation-validation/result.json` and
  `bootstrap/job-preparation-validation/installed-requirements.txt`.

That GPU preparation job has been stopped. These checks apply to the preparation
image, not yet to the nginx serving image. No model was launched by this preparation
run. The serving-key file was absent at the time of verification. Consult current
job state and deployment evidence rather than treating this dated record as live status.

## First hosting deployment verified on 2026-10-06

Job `manual-qwen-gpu` hosted `Qwen/Qwen2.5-1.5B-Instruct` at revision
`989aa7980e4cf806f80c7fef2b1adb7bc71aa306`, served as `qwen-small`, on one
B200 MIG 1g.23gb device (20.5 GiB visible memory). Context is 4096 tokens,
concurrency is 1, dtype is bfloat16, and GPU memory utilization is 0.85.

All seven deterministic checks passed through loopback, nginx and the public
HTTPS API at `https://inference.example.org/v1`: model identity, chat,
complete SSE, and rejection of absent/incorrect keys on models and chat routes.
Evidence lives in `deployments/qwen-small/<RUN_ID>/`:
`job.json`, `checks.json`, `checks-loopback.json` and `checks-nginx.json`.
The allocation has ended. Its recorded expiry was **2026-10-06 11:43:01 Europe/Copenhagen**.
This is a dated verification record; check current job state before using it.

The default startup path is nginx's `initScript`, after CPU preparation.
UCloud's interactive SHELL API is available for recovery despite the SSH
restriction. Register the WEB session after job startup to activate the public
route, then verify the API. The pinned environment uses CUDA 13.0.88 compiler,
CRT and NVVM packages; the initialization script exposes their paths and a
deployment-local CUDA runtime linker alias. No driver changes are required.

## Operating notes

Keep tokens and serving keys out of logs and uploaded bundles. Do not source
credential files as arbitrary shell scripts. Reuse the template's nginx server
and public URL. Avoid modifying an environment while another job is using it.
Confirm Python, OS libraries and architecture compatibility across both job images.

Stop an owned preparation job once its work and transfers have completed.
A successfully deployed hosting job must remain running until the operator requests
release or its allocation expires; record allocation expiry and renewal responsibility.

Source documentation:
[UCloud nginx](https://docs.cloud.sdu.dk/Apps/nginx.html) and
[Initialization scripts](https://docs.cloud.sdu.dk/hands-on/init-sh.html).

## Managed CLI deployment verified on 2026-10-06

The full CLI workflow now prepares the CPU stage, selects the active bundle,
submits nginx with initScript, registers WEB routing and verifies all three API paths.
At this stage the recorded GPU job was replacement-qwen-gpu, alias qwen-small, context 4096,
concurrency 2, with allocation expiry 2026-10-06 13:02:57 Europe/Copenhagen.
The earlier job initial-qwen-gpu and temporary CPU jobs initial-qwen-cpu/replacement-qwen-cpu have ended.

Recorded bundle: deployments/qwen-small/<RUN_ID>/.
Recovery and two restarts reused the same GPU allocation; all endpoint checks passed.
Model weights were reused. Compilation caches survived replacement in
cache/kernels/runtime-cache-a/. Version/driver/GPU changes select a different
namespace. Short concurrent tests passed; memory capacity does not predict throughput.
Check the local deployment journal and CLI status before assuming the job is live.

## PII-Tracer deployment verified on 2026-10-06

PII-Tracer replaced the Qwen service in GPU job initial-pii-gpu. Recorded bundle:
deployments/pii-tracer/<RUN_ID>/.
Model: perplexity-ai/PII-Tracer-vLLM at 9f34cd1f5010a1de5a7b464eaf3c3a39db01b15a.
Served alias: pii-tracer. Context: 4096 tokens. Concurrency: 2.
Recorded expiry: 2026-10-06 13:20:40 Europe/Copenhagen; query current status.

This is a bidirectional token classifier, not a chat service. The authenticated
adapter on loopback 8000 exposes /v1/models, /v1/scoring and /v1/pii through the
existing nginx route. The vLLM pooling backend binds loopback 8001. A single
owned supervisor/tmux session manages both processes. No model repository Python
code runs. Both keys are read from the workspace .env; the existing nginx configuration is retained.

Task checks passed on loopback, nginx and public HTTPS. Two 4096-token inputs
passed together; 4097 tokens was rejected without truncation. Use the repository's
notebooks/test_pii_tracer.ipynb for synthetic email tests. Sensitivity is a separate
conversation-level score; masking uses decoded spans without a sensitivity gate.


## Validated lifecycle and benchmarks (2026-10-06)

Agent source: https://github.com/CBS-HPC/ucloud-vllm-agent (private).
Ended CPU preparation recovery, Qwen-to-PII replacement, rollback to Qwen,
and same-profile renewal passed loopback, nginx and public HTTPS checks.
Repeated rollback/renewal reused their recorded GPU jobs.
Qwen compilation startup: 148.089 seconds cold, 45.176/45.162 seconds warm.
PII: 64 short Danish emails and 32 exact 4096-token inputs passed with two clients.
See docs/live-validation.md and docs/benchmark-results.json in the Git checkout.

These were temporary validation allocations. Hosting is not intended to remain
running after the validation. Query UCloud job state before assuming availability.
Models and compilation caches are retained. Both credentials still come from
/work/vllm/.env; no duplicate credential files were introduced.
