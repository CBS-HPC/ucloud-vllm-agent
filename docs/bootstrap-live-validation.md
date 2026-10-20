# Isolated no-prior-job validation — 2026-10-20

Publication note: historical operational identifiers use role labels and example URLs; measurements and runtime behavior are retained. Exact identities belong in private journals.

An operator-led trial in **isolated validation project** passed the complete first-time
path without either template job ID. A separate local checkout/venv and a fresh
namespaced UCloud folder were used; no credentials were copied from the original
workspace. This is not the outstanding colleague-led onboarding acceptance test.

| Stage | Recorded job/resource | Result |
| --- | --- | --- |
| Separate Link setup | Link bootstrap-link | Created with upstream receipt and project ownership record |
| Bootstrap CPU | bootstrap-cpu; 2 vCPUs, 6 GB advertised RAM, one-hour limit | New namespace/vllm folder, persistent mount, private staging, packaged assets and exclusive credentials verified; released |
| Model-preparation CPU | bootstrap-preparation-cpu; same CPU product/limit | Fresh pinned environment installed and Qwen cached; recovered after local SSH polling failure using the same job/installer; released |
| Serving GPU | bootstrap-qwen-gpu; one B200 MIG 1g.23gb, one-hour limit | nginx initialization, route registration, runtime capacity and all three endpoint paths passed |

The model was `Qwen/Qwen2.5-1.5B-Instruct` at
`989aa7980e4cf806f80c7fef2b1adb7bc71aa306`, served as `qwen-onboarding` with
bfloat16, 4096-token context and concurrency 1. Runtime: vLLM 0.31.0, Python
3.12.3, torch 2.13.0+cu130, CUDA toolkit 13.0.88 and FlashInfer 0.7.0.post1.
The model card records Apache-2.0 and the same supported architecture:
[pinned source](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct/blob/989aa7980e4cf806f80c7fef2b1adb7bc71aa306/README.md).

The packaged nginx.conf passed `nginx -t` inside **nginx 1.31.2** itself. Its SHA256
was `99c31ed5272b11ba163c65bd3148fbe373001cd2fd6c6bf8b7293d14953ead3b`.
Seven checks passed independently on loopback, nginx and public HTTPS: expected
served model, chat, completed SSE, and HTTP 401 for missing and incorrect keys
on both model listing and chat. SSE timings alone do not prove no proxy buffering.
Runtime profiling reported 2.98 GiB weights, 13.37 GiB available KV memory and
500,848 KV tokens. These are capacity observations, not throughput guarantees.

The new Files path was `/<DRIVE_ID>/<NAMESPACE>/vllm`; its remote `.env` was
created exclusively through SSH stdin with the selected serving key and blank
HF_TOKEN. The UCloud credential stayed local. Both template IDs remained null in
the deployment journal. The existing Link existing-link remained READY/unbound; the new
Link was bound only to the recorded serving job. Existing inference files/URL
were not selected or changed.

Public URL at validation: `https://inference.example.org/v1`.
Recorded GPU expiry: **2026-10-20 14:04:09 Europe/Copenhagen**. Successful hosting
was retained under the one-hour allocation; this dated record does not establish
current uptime. Both CPU jobs were confirmed SUCCESS after release. Link/storage
persist independently and require separate explicit management.

Detailed non-secret operational records remain outside Git in the isolated
workspace: `run/setup/<SETUP_NAME>/`, `run/bootstrap/<BOOTSTRAP_NAME>/`,
`artifacts/trial-plan.json`, `artifacts/trial-evidence.json` and
`deployments/qwen-onboarding/<RUN_ID>/`. The latter contains the
bootstrap snapshot, deployment intent/IDs, preparation result, check summaries,
runtime/cache evidence and actual-image nginx evidence. A local output-free copy
of the chat notebook is configured at `artifacts/test_onboarding.ipynb`.

Live findings: the provider returns HTTP 400 for missing files, so namespace
absence is now established through a complete successful parent listing rather
than status-code assumptions. The local SSH polling exception's exact transport
cause was not observed; recovery resumed the same known CPU without a second
submission/installer. Both cases have regressions and SPEC.md records.

Limits: no new-project PII test, sustained benchmark, live fault injection for
uncertain folder/credential writes, optional key registration/removal, bootstrap
renewal/rollback, or independent colleague-led trial was performed. Existing
template-mode validation remains in [live-validation.md](live-validation.md).
