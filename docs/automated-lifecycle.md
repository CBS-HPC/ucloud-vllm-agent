# Automated deployment and recovery

The CLI implements CPU preparation, upload verification, environment setup,
pinned model caching, active-bundle selection, GPU submission through nginx,
WEB route registration and three-path inference checks. Full CLI deployment and replacement passed on 2026-10-06; recovery and restart
reuse the recorded allocation. See live-validation.md for evidence and limits.

```powershell
vllm-agent catalog --output artifacts/machines.json
vllm-agent size --profile config/hosting.qwen-small.json
vllm-agent deploy --profile config/hosting.qwen-small.json --auto-size --reviewed
```

`--reviewed` records model/license/runtime review; it does not enable repository
code. UCLOUD_PROJECT must be the UUID that owns both explicit templates.
Both templates mount the same workspace. Preparation needs CPU and SSH;
serving preserves the configured nginx application and public link.

Remote HF_TOKEN and VLLM_API_KEY share `/work/vllm/.env` with mode 0600.
The local project `.env` remains for UCloud settings and client verification.
Local VLLM_API_KEY must match;
only its SHA256 comparison value is sent to preparation. Both application images
must support the prepared Python 3.12 environment.

`run/current.json` identifies the bundle; its `deployment.json` journals exact
job IDs and submission intent before network calls. A process lock prevents
concurrent mutations. Unknown outcomes block resubmission and duplicate GPUs.

```powershell
vllm-agent status --deployment deployments/NAME/RUN
vllm-agent recover --deployment deployments/NAME/RUN
# Resolve acknowledgement loss by identifying the exact existing job first:
vllm-agent recover --deployment deployments/NAME/RUN --kind hosting --submission-job-id ID
vllm-agent restart --deployment deployments/NAME/RUN
vllm-agent stop --deployment deployments/NAME/RUN
vllm-agent release --deployment deployments/NAME/RUN
vllm-agent rollback --deployment deployments/FAILED_REPLACEMENT/RUN
vllm-agent renew --deployment deployments/NAME/RUN --hours 4
vllm-agent deploy --profile config/hosting.qwen-small.json --auto-size --reviewed --replace deployments/NAME/RUN
```

Recovery resumes saved bundles and known allocations. Reconciliation checks the
unique job name and project. Restart reuses the exact allocation/session. Stop
stops the owned tmux session while retaining GPU allocation; release ends only
recorded ownership-checked jobs. Artifacts and caches remain.

Replacement prepares files first, releases its own CPU clone and the previous
owned GPU, then submits the new GPU. This entails downtime and is not
transactional; failures retain the journal. The predecessor is marked
`replacement_pending` at cutover and `replaced` only after the successor passes
verification. Operator template jobs remain.
Legacy nohup deployments support replacement/release, not managed restart.

`recover` automatically archives an ended owned CPU preparation job and creates
one new CPU attempt when activation is unfinished. Each attempt has a distinct
submission name, and stale remote preparation results are removed before launch.
Downloads and validated environments are reused. Completed activation does not
allocate another CPU job. Unknown submissions still require reconciliation;
recovery never guesses whether a request succeeded. Released or retired bundles
cannot be recovered into service.

`rollback` restores the failed replacement's recorded predecessor profile,
including its pinned revision, machine, context and concurrency, in a new bundle.
It prepares first, releases only the failed replacement's known owned job, then
submits and verifies the restored model. Repeated rollback resumes the same
bundle, including after submission acknowledgement loss; reconcile its exact
job ID before continuing. If the predecessor is still active and the replacement
has not submitted a GPU job, restart the predecessor instead. Rollback requires
a reviewed predecessor profile and available allocation capacity; it is explicit
and incurs downtime. No automatic rollback allocates GPU time on failure.

`renew --hours N` uses the same pinned profile and machine in a replacement
allocation, with a new duration and token-coverage preflight. It preserves model
and compilation caches. This replaces the job with downtime; it does not extend
the existing job in place or schedule automatic renewals. Repeated renewal of
the same source resumes its recorded renewal. To renew again later, use the new
deployment path returned by the command.

Models persist under `/work/vllm/cache/huggingface`. Kernel caches persist under
`/work/vllm/cache/kernels/HASH`, separated by runtime, CUDA compiler, driver,
GPU capability and platform evidence. vLLM, FlashInfer, Triton, TorchInductor
and CUDA cache paths are configured before launch. Stable linker paths avoid
deployment-specific inputs; caches are never cleared implicitly. Cache loads were observed across two GPU jobs with an identical namespace;
a measured restart with verification took 46 seconds. A controlled follow-up
measured 148.089 seconds cold and 45.176/45.162 seconds warm in the same job
and cache group; see live-validation.md for the measured scope. See
[vLLM environment variables](https://docs.vllm.ai/en/stable/configuration/env_vars/)
and [FlashInfer workspace configuration](https://github.com/flashinfer-ai/flashinfer/blob/v0.7.0.post1/flashinfer/jit/env.py).

Success leaves hosting running and records expiry; invoking renewal before
expiry remains the operator's responsibility. Verification failure retains the known allocation
for diagnosis, recovery or explicit release.
