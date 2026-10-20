# Sources and design basis

Originally reviewed 2026-10-06; release/startup references checked again 2026-10-20.
Runtime links below target the selected vLLM 0.31.0 baseline where available.
Earlier evidence is historical; changes in mutable platform docs require review.

- Operator's local moody_agent: AGENTS.md, README, orchestration skill/contract,
  capacity.py, ucloud_runner.py, run_recovery.py and remote_environment.py.
  Adopted request-to-case planning, estimates backed by evidence, pinned runtime,
  upstream reuse and isolated state. Its CPU/data estimates do not apply to vLLM,
  and its automatic batch job termination must not be copied into hosting.
- [CBS-HPC/ucloud-api v0.1.7](https://github.com/CBS-HPC/ucloud-api/releases/tag/v0.1.7):
  current pinned integration for jobs/products, SSH, Link and optional key setup.
  Reviewed commit and consumed contracts are in [resource-setup.md](resource-setup.md).
  Bootstrap's application/Files routes and exact official source revision are in
  [SPEC.md](../SPEC.md). Earlier v0.1.6 template-mode validation remains in
  [live-validation.md](live-validation.md); the newer isolated trial is in
  [bootstrap-live-validation.md](bootstrap-live-validation.md).
- [CBS-HPC/chatbot](https://github.com/CBS-HPC/chatbot): vLLM model serving and
  nginx streaming configuration provide hosting context. GPU/compiler workarounds
  and broad process cleanup are not adopted as general hosting rules.
- [HF Hub API](https://huggingface.co/docs/huggingface_hub/en/package_reference/hf_api):
  repository commit metadata and safetensors total parameter count; configuration
  is fetched without executing model repository code.
- [vLLM parallelism](https://docs.vllm.ai/en/v0.31.0/serving/parallelism_scaling/)
  and [KV head replication](https://vllm.ai/blog/2026-08-07-decode-context-parallelism):
  multi-device sizing must account for head sharding/replication.
- [vLLM serving](https://docs.vllm.ai/en/v0.31.0/cli/serve/)
  and [security](https://github.com/vllm-project/vllm/blob/v0.31.0/docs/usage/security.md):
  serving arguments and VLLM_API_KEY. Expose only the template's intended API
  routes; authentication does not cover every server route.
- [UCloud products](https://docs.cloud.sdu.dk/guide/resources-products.html):
  GPU/MIG product context. Candidate VRAM allowances require actual-host checks;
  system RAM must never be mistaken for device VRAM.
- [UCloud VM guide](https://docs.cloud.sdu.dk/Apps/vm_apps.html): mounted storage,
  link port selection, session persistence and allocation/data lifecycle.
- [nginx proxy module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html):
  URI-preserving proxy and streaming configuration. nginx belongs to the template.
- [UCloud nginx](https://docs.cloud.sdu.dk/Apps/nginx.html) and
  [initialization scripts](https://docs.cloud.sdu.dk/hands-on/init-sh.html):
  configuration file selection, HTTP port 8080 and the startup script mechanism.
  Actual-image syntax and Qwen checks are recorded in the isolated trial.
