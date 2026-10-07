# LUMI AITTA managed inference

AITTA is an additional inference platform alongside custom UCloud hosting.
It provides a curated model catalog and manages Slurm resources and model loading.
The agent selects a model and verifies its API; AITTA handles machine selection.
UCloud profiles, nginx templates, caches and lifecycle commands apply to UCloud.

Source: [official AITTA guide](https://docs.lumi-supercomputer.eu/laif/inference/aitta/),
reviewed 2026-10-07. Access, catalog and limits may change.

## Dependency and access

Generic authentication, transport, discovery and preload are owned by the separate
private [CBS-HPC/lumi-aitta-api](https://github.com/CBS-HPC/lumi-aitta-api) project.
This workspace consumes release v0.1.0 through its optional `aitta` extra. It owns
model selection and task-specific connectivity verification. Do not copy the
dependency's control API or edit that repository as part of routine hosting work.

```powershell
python -m pip install -e ".[aitta]"
```

Installing a private Git dependency requires GitHub access. An active LUMI account
and project are required for inference. Obtain a project-bound token from
[AITTA token generation](https://aitta-auth.csc.fi/myToken) using the documented
Haka, MyAccessId/Puhuri or CSC login. Add `AITTA_API_KEY=<token>` to your existing
local project `.env`. Keep `VLLM_API_KEY` for the UCloud endpoint; these are
different credentials. Never upload the AITTA token to UCloud or paste it into
CLI arguments. No duplicate token file is created.

The documented token lifetime is currently 90 days, potentially shorter if the
project/account ends. Token renewal is the operator's responsibility. The service
origin is fixed to `https://aitta-api.csc.fi`; the inference base URL is
`https://aitta-api.csc.fi/openai/v1`.

## Discover, load and verify

```powershell
vllm-agent aitta status
vllm-agent aitta models
vllm-agent aitta workers --model "vendor/model-from-the-live-list"
```

These are read-only requests. Model discovery uses HAL `/model`, rather than
assuming an OpenAI `/models` endpoint. Empty workers means none are reported;
it is not a failed deployment. Service availability does not prove model readiness.

Offline models can be started manually from [the AITTA frontend](https://aitta.csc.fi/)
or explicitly requested through the API:

```powershell
vllm-agent aitta preload --model "vendor/model-from-the-live-list"
vllm-agent aitta workers --model "vendor/model-from-the-live-list"
vllm-agent aitta check --model "vendor/model-from-the-live-list" --timeout 300
```

Preload validates the model's advertised POST operation before requesting loading.
`preload_requested` is not readiness. No background polling is started. Inference
itself can also trigger loading. Both preload and check require an explicit
request to use that model because they may consume shared LUMI capacity.
Do not start every offline model, switch models silently or automatically retry
after a timeout: an earlier request may still be loading.

The chat check first verifies advertised chat capability, then tests nonempty
completed chat, SSE content/finish/DONE, and rejection of absent/incorrect keys
on chat. It saves a sanitized report at `artifacts/aitta-checks.json`, ignored by
Git. No token, generated text or raw service metadata is saved. Timeout may be
30–900 seconds for cold loading; it is a per-request transport timeout rather
than a total command deadline or allocation guarantee.

The platform also documents embedding support, but this integration verifies
chat only. Embedding-only models are rejected before inference. PII-Tracer's
custom API and CLAES's unimplemented classification path must not be assumed
available through AITTA.

## Platform selection and evidence

| Requirement | Path |
| --- | --- |
| Explore a model currently offered by AITTA | Discover capability/workers, preload if requested, verify AITTA |
| Host an exact HF revision or a custom task adapter | Reviewed UCloud profile and machine sizing |
| Control machine, concurrency, expiry and persistent caches | UCloud lifecycle |

Keep the live AITTA catalog separate from this project's historical model
catalog. Do not attach UCloud-tested machine sizes or pinned revisions to managed
service models without service-specific evidence. Contract tests are local;
authenticated AITTA live validation is pending. It requires an operator-selected
model and token. No model was loaded during integration development.

AITTA is intended for research/development without guaranteed availability.
Loading may wait for capacity or time out. HTTP 429 indicates a per-user rate
limit; the guide advises waiting a minute. Neither package nor agent automatically
retries. There are no AITTA stop/release/renew/rollback commands here; AITTA owns
its workers and allocation lifecycle.
