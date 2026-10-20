# Deterministic hosting configuration

Begin with [researcher onboarding](researcher-onboarding.md). Choose either
[bootstrap without prior jobs](bootstrap.md) or the manual
[template-ID path and asset inventory](ucloud-workspace-template.md).
Both use the same packaged initialization script in generated deployment bundles.

Use `config/hosting.qwen-small.json` as the starting profile. It records the
configuration verified on UCloud on 2026-10-06. Credentials, project, template
IDs and public hostname remain in local `.env`; credentials never enter profiles
or generated bundles.
For anonymisation, use `config/hosting.pii-tracer.json` with `request.task=pii`.
The [model catalog](model-catalog.md) lists pinned revisions, parameters, tested
machine capacities and notebooks. CLAES is a classification candidate without a
hosting profile; do not copy a chat/PII task value to imply classification support.

Change these profile values for a new workload:

| Value | Effect |
| --- | --- |
| `request.name` | Served model alias and deployment name. |
| `request.task` | `chat` for generative chat; `pii` for the reviewed token-classification adapter. |
| `request.model`, `request.revision` | Hugging Face repository and pinned revision. Preparation resolves an unpinned revision into the bundle's exact commit. |
| `request.context_length`, `request.concurrency` | Context and simultaneous sequence limits; both affect the memory estimate. |
| `request.dtype`, `request.gpu_memory_utilization` | Model dtype and GPU memory budget. |
| `machine.product` | Exact UCloud product ID, category and provider. |
| `machine.gpu_count`, `machine.vram_gib_per_gpu`, `machine.ram_gib`, `machine.mig` | Capacity evidence for that product; update together with the product. Never add MIG slices as one GPU. |
| `machine.verified` | Whether the configured product and capacities have been checked in the project. |
| `hours` | Allocation duration. |

The example uses 20.5 GiB measured visible GPU memory and a conservative 30 GiB
host RAM allowance below the free RAM observed during startup. These values
belong to the tested B200 MIG product and are not a general machine catalog.
Changing a product ID alone does not verify its capacity or live availability.
Use `size` for model-to-machine comparison and `deploy --auto-size` to select
from project products; see sizing-research.md for assumptions and tool comparison.

```powershell
python -m ucloud_vllm_agent prepare-profile --profile config/hosting.qwen-small.json
python -m ucloud_vllm_agent preview-profile --profile config/hosting.qwen-small.json
```

`prepare-profile` estimates the specified workload against the specified machine
and refuses an estimated non-fit before writing a bundle. It generates the pinned
`runtime.json`, `remote.py`, normalized `hosting-profile.json`, `job-settings.json`
and existing planning evidence. `--metadata FILE` supports offline preparation.
`preview-profile` reads the explicit serving template, or the finalized source
selected with `--bootstrap FILE`, and builds its specification with SSH disabled,
the exact machine product and the initialization script file beside nginx.conf
in UCloud Files. It prints a sanitized preview. Bootstrap users also pass that
artifact to doctor and first deploy; prepare-profile does not take --bootstrap.
Neither command submits a job, uploads files or replaces the running model.

The initialization workflow currently accepts only the live-tested baseline:
`/work/vllm`, `/work/vllm/.venv`, vLLM 0.31.0 and nginx 1.31.2. Preparation pins
CUDA compiler/CRT/NVVM to 13.0.88 for PyTorch cu130; the initialization script
checks that baseline. A runtime upgrade requires a new compatibility validation.
No model repository code is enabled by this profile.

## Default execution sequence

1. Prepare the model/profile, inspect its pinned metadata and review the blockers.
2. Use the explicit CPU preparation template, or the finalized bootstrap's CPU
   specification, and verify the persistent shared mount.
3. Upload the reviewed bundle and stable initialization script. Preserve the
   mounted workspace README; maintain its context when explicitly needed. Prepare
   the verified environment and cache the pinned model using the remote HF token.
4. Select the reviewed bundle with `/work/vllm/active`. Confirm both remote keys in the workspace `.env` (mode 0600). Refuse an implicit replacement of another deployment.
5. Build from the explicit nginx serving template or bootstrap source. Preserve mounts, nginx and
   public-link resources; set only the reviewed product, duration, name and initScript.
6. Submit once and persist the job ID immediately. An uncertain submit outcome
   requires recovery rather than another allocation.
7. Register the WEB session on the running job. Confirm the returned host matches
   the configured public URL, then wait for model readiness.
8. Run task-specific checks on loopback, nginx and external HTTPS: seven for chat
   or ten for PII. Save
   evidence, current job state and allocation expiry. Keep a verified job running.

UCloud interactive SHELL is the recovery path for inspecting a failed startup
or running the same initialization script after a reviewed correction. A startup
retry first checks the owned process and port; it does not create a second job.
Successful script execution and a RUNNING job alone are not model readiness.

Automated CPU provisioning, submit recovery, route registration and tmux lifecycle
are implemented and tested. Deployment, ended-preparation recovery, replacement,
rollback and renewal passed live validation on 2026-10-06. Rollback and renewal
create replacement allocations with downtime; repeated commands resume their
recorded bundle. See [commands and recovery semantics](automated-lifecycle.md)
and [dated validation evidence](live-validation.md). The validation jobs were
explicitly released; historical success does not imply a currently running service.
