# Model types and run history

The catalog records **previously validated models** and **untested candidates**.
It is not a list of currently running jobs. All jobs from the 2026-10-06 validation
session were released; use deployment status to inspect current allocations.

The source of truth is
[`model_catalog.json`](../src/ucloud_vllm_agent/data/model_catalog.json), included in
the Python package. It records HF revisions, runtime/API, tested machine and input
limits, profiles, notebooks and evidence. Model types describe the use case;
serving tasks describe the implemented runtime path.

| Type | Model | Status | Serving path | Test notebook |
| --- | --- | --- | --- | --- |
| Chat | [Qwen2.5-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct) | Validated | vLLM chat and streaming | [Chat notebook](../notebooks/test_model.ipynb) |
| Anonymisation / PII masking | [PII-Tracer-vLLM](https://huggingface.co/perplexity-ai/PII-Tracer-vLLM) | Validated | vLLM pooling plus reviewed scoring/masking adapter | [Danish/English email notebook](../notebooks/test_pii_tracer.ipynb) |
| Classification | [CLAES preview](https://huggingface.co/syvai/claes-preview) | Candidate | Laya; adapter and vLLM compatibility unverified | Not yet created |

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

For each newly tested model, record the pinned revision, actual task/API, machine,
context, concurrency, reproducible profile, notebook and live verification evidence.
Keep candidate entries separate until their endpoint, authentication and task
checks pass. Retest changed revisions or runtime versions; historical validation
does not automatically apply to them.
