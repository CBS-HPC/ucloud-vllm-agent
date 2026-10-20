# PII-Tracer hosting

Profile: `config/hosting.pii-tracer.json`. Pinned model:
`perplexity-ai/PII-Tracer-vLLM`, revision
`9f34cd1f5010a1de5a7b464eaf3c3a39db01b15a` (MIT).
The [publisher's package](https://huggingface.co/perplexity-ai/PII-Tracer-vLLM)
is a bidirectional Qwen3 token classifier with 37 BIOES labels and one sensitivity
output. It uses pooling inference, not autoregressive chat or SSE.
The [vLLM 0.31.0 token-classification API](https://docs.vllm.ai/en/v0.31.0/models/pooling_models/token_classify/)
is supported by the prepared environment; the publisher's Docker example pins 0.26.0.

This workspace runs its own reviewed adapter, without model repository Python or
`trust_remote_code`. Both processes bind loopback: the adapter uses nginx's existing
port 8000, vLLM pooling uses 8001. A single owned supervisor/tmux session manages
them together. Authentication is required by the adapter and backend; existing
nginx is preserved. Both HF_TOKEN and VLLM_API_KEY are read from `/work/vllm/.env`
(mode 0600); the local project `.env` remains for client/UCloud configuration.
The publisher's unauthenticated adapter
is not deployed.

| API route | Behavior |
| --- | --- |
| `GET /v1/models` | Authenticated model listing/readiness |
| `POST /v1/scoring` | 37 raw token logits, sensitivity logit, token IDs and offsets |
| `POST /v1/pii` | BIOES-decoded spans, masked text, sensitivity and token count |

Both POST routes accept `{"model":"pii-tracer","sequences":["synthetic text"]}`.
Use the existing `Authorization: Bearer VLLM_API_KEY` header. The initial validated
envelope is bfloat16, one B200 MIG 1g.23gb slice, context 4096 and concurrency 2;
larger batches, overlong input and mismatched model names are rejected.
The masking endpoint always masks decoded spans. Sensitivity is a separate
conversation-level score; it does not decide whether spans are masked.

Sizing reserves approximately 1.11 GiB weights, 1.75 GiB encoder activations for
two full-context inputs and a 3 GiB runtime allowance. There is no retained
decoder KV cache. Runtime reported 1.12 GiB weights. This is a task-specific
conservative allowance, not a generic encoder estimator or throughput prediction.
The model has 596,088,870 parameters. The tested slice exposes 20.5 GiB VRAM;
the hosting profile uses a conservative 30 GiB RAM allowance. Exact count/source
and machine fields are maintained in the [model catalog](model-catalog.md).

## Live evidence, 2026-10-06

Job names below are publication-safe role labels, and the bundle run ID is a
placeholder. Measurements and the pinned model revision are unchanged. Consult
private deployment journals for exact operational identities.

CPU preparation job initial-pii-cpu cached the pinned model and ended. GPU job initial-pii-gpu
replaced Qwen job replacement-qwen-gpu. Its initial adapter needed a cached-file lookup repair;
recovery and restart used the same allocation. No second GPU was allocated for
the repair. Evidence is in the ignored local bundle
`deployments/pii-tracer/<RUN_ID>/`.

Ten task-specific checks passed on loopback, nginx and public HTTPS: model,
masking/offsets, scoring alignment, concurrency and absent/wrong-key rejection on
all routes. A batch of two 4096-token synthetic inputs passed; 4097 tokens was
rejected without truncation. Test data remained synthetic.

Open [the email notebook](../notebooks/test_pii_tracer.ipynb), choose
`selected_example = "møde"`, `"it-support"` or `"english"`, then edit the selected
synthetic email and run the cells in order. It shows detected spans, masked
email and sensitivity. Inference and scoring cells were tested against the live
endpoint; the saved notebook contains no output or credentials.

```powershell
vllm-agent check --task pii --model pii-tracer --base-url https://YOUR-HOST/v1
vllm-agent status --deployment deployments/NAME/RUN
```

Use your own endpoint and returned deployment path; the role labels above are
historical references, not setup defaults. If you rename request.name, change the notebook's
model alias and the check's --model too. The PII notebook reads local .env values
directly; process-only CLI overrides do not configure it.

Model detection quality and thresholds need evaluation on the intended data.
Chat-only benchmarks/notebooks do not apply to this service. Query status for the
current allocation and expiry; successful checks do not automatically renew jobs.
All jobs from the later validation session were released. The follow-up passed
64 short Danish-email requests and 32 exact 4096-token requests with two clients;
see [measured results and limits](live-validation.md) and [benchmark commands](benchmarks.md).
