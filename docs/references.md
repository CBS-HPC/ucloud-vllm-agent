# Sources and design basis

Reviewed 2026-10-06. Recheck mutable docs against selected runtime releases.

- Operator's local moody_agent: AGENTS.md, README, orchestration skill/contract,
  capacity.py, ucloud_runner.py, run_recovery.py and remote_environment.py.
  Adopted request-to-case planning, estimates backed by evidence, pinned runtime,
  upstream reuse and isolated state. Its CPU/data estimates do not apply to vLLM,
  and its automatic batch job termination must not be copied into hosting.
- [CBS-HPC/ucloud-api v0.1.6](https://github.com/CBS-HPC/ucloud-api/releases/tag/v0.1.6):
  released wheel downloaded and SHA256 checked; GPU/MIG/template-product builder
  tested. Real token metadata and the operator's template were inspected read-only.
  This project implements the hosting-specific CPU/GPU provisioning and recovery
  workflow against that released adapter; see live-validation.md for evidence.
- [CBS-HPC/chatbot](https://github.com/CBS-HPC/chatbot): vLLM model serving and
  nginx streaming configuration provide hosting context. GPU/compiler workarounds
  and broad process cleanup are not adopted as general hosting rules.
- [HF Hub API](https://huggingface.co/docs/huggingface_hub/en/package_reference/hf_api):
  repository commit metadata and safetensors total parameter count; configuration
  is fetched without executing model repository code.
- [vLLM parallelism](https://docs.vllm.ai/en/stable/serving/parallelism_scaling/)
  and [KV head replication](https://vllm.ai/blog/2026-08-07-decode-context-parallelism):
  multi-device sizing must account for head sharding/replication.
- [vLLM serving](https://docs.vllm.ai/en/latest/cli/serve/)
  and [security](https://github.com/vllm-project/vllm/blob/main/docs/usage/security.md):
  serving arguments and VLLM_API_KEY. Expose only the template's intended API
  routes; authentication does not cover every server route.
- [UCloud products](https://docs.cloud.sdu.dk/guide/resources-products.html):
  GPU/MIG product context. Candidate VRAM allowances require actual-host checks;
  system RAM must never be mistaken for device VRAM.
- [UCloud VM guide](https://docs.cloud.sdu.dk/Apps/vm_apps.html): mounted storage,
  link port selection, session persistence and allocation/data lifecycle.
- [nginx proxy module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html):
  URI-preserving proxy and streaming configuration. nginx belongs to the template.
