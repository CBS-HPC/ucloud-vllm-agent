# Model types and run history

The catalog records **previously validated models** and **untested candidates**.
It is not a list of currently running jobs. All jobs from the 2026-10-06 validation
session were released; use deployment status to inspect current allocations.

The source of truth is
[`model_catalog.json`](../src/ucloud_vllm_agent/data/model_catalog.json), included in
the Python package. It records parameter counts, HF revisions, runtime/API, tested machine and input
limits, profiles, notebooks and evidence. Model types describe the use case;
serving tasks describe the implemented runtime path.

| Type | Model | Parameters | UCloud machine size (tested) | Status | Serving path | Test notebook |
| --- | --- | ---: | --- | --- | --- | --- |
| Chat | [Qwen2.5-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct) | 1.54B (1,543,714,304) | 1 × B200 MIG 1g.23gb; 20.5 GiB VRAM, 30 GiB RAM | Validated | vLLM chat and streaming | [Chat notebook](../notebooks/test_model.ipynb) |
| Anonymisation / PII masking | [PII-Tracer-vLLM](https://huggingface.co/perplexity-ai/PII-Tracer-vLLM) | 596M (596,088,870) | 1 × B200 MIG 1g.23gb; 20.5 GiB VRAM, 30 GiB RAM | Validated | vLLM pooling plus reviewed scoring/masking adapter | [Danish/English email notebook](../notebooks/test_pii_tracer.ipynb) |
| Classification | [CLAES preview](https://huggingface.co/syvai/claes-preview) | 322M (321,908,998) | Pending runtime review and sizing | Candidate | Laya; adapter and vLLM compatibility unverified | Not yet created |

Parameter counts come from Hugging Face metadata for the pinned revisions; source
URLs and exact counts are included in the JSON catalog. Machine sizes are the
validated selections for bfloat16, 4096-token context, and the recorded concurrency
(Qwen: 1–2; PII: 2). They are not universal minimums: context, concurrency, dtype
and serving runtime affect memory needs. The product's advertised 23 GB slice was
measured as 20.5 GiB visible VRAM. CLAES has no verified machine recommendation yet.

```powershell
vllm-agent models
vllm-agent models --status validated
vllm-agent models --type anonymisation
vllm-agent models --type classification --status candidate
```

These commands read the packaged catalog without network requests or allocations.
Catalog entries do not bypass model review, sizing or deployment authorization.

## CLAES preview

The inspected revision is `85bfaef5d5f7c81d0efcb9c6b72ca6c8ee165d17`.
The preview is a roughly 322M-parameter Danish Laya decision model using an
mmBERT encoder. It scores supplied choices and presence decisions rather than
generating answers. Its current `max_len` is 1024; the card warns that longer
inputs are silently truncated. A future adapter should reject oversized inputs.
Sources: [pinned model card](https://huggingface.co/syvai/claes-preview/blob/85bfaef5d5f7c81d0efcb9c6b72ca6c8ee165d17/README.md),
[pinned runtime configuration](https://huggingface.co/syvai/claes-preview/blob/85bfaef5d5f7c81d0efcb9c6b72ca6c8ee165d17/rl_agent_config.json).

Reinspect the actual full release when available. Its revision, dependencies,
serving API and machine needs must be tested before adding a hosting profile.
The catalog contains no invented machine recommendation or deployment proof.

## Maintaining the catalog

For each newly tested model, record the pinned revision, parameter count/source, actual task/API, machine capacity,
context, concurrency, reproducible profile, notebook and live verification evidence.
Keep candidate entries separate until their endpoint, authentication and task
checks pass. Retest changed revisions or runtime versions; historical validation
does not automatically apply to them.
