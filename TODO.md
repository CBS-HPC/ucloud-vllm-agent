# Remaining work

- [x] Consume released ucloud-api v0.1.6 for GPU/MIG products and submission.
- [x] Deterministic profile, pinned HF revision, nginx initScript and endpoint tests.
- [x] Compare llm-checker, llmfit, GPUStack, Accelerate and Can I Use LLM.
  Decision and sources: docs/sizing-research.md. No required external sizing tool.
- [x] Dense MHA/GQA sizing with quantized checkpoint bytes, explicit KV dtype,
  context/concurrency, per-device limits, RAM/disk and minimum/recommended machines.
- [x] Project wallet/product catalog mapping for B200 full GPU and 1g.23gb MIG.
- [x] CPU-first preparation, reviewed uploads, environment validation/model cache,
  GPU submission, initialization and WEB registration in one deploy command.
- [x] Durable submission intent/job IDs, operation lock, recovery/reconciliation,
  status, exact-session restart/stop, replacement and exact-job release.
- [x] Runtime-specific persistent vLLM/FlashInfer/Triton/TorchInductor/CUDA caches.
- [x] Numeric startup capacity extraction and three-path checks in verification.
- [x] Manual Qwen hosting on B200 MIG passed loopback/nginx/public checks.
- [x] Full live CLI deployment, replacement, recovery, restart and exact-job release.
  Evidence and remaining limits: docs/live-validation.md.
- [x] Observe model and compilation-cache reuse across GPU jobs; measure restarts.
- [ ] Controlled cold/warm startup comparison with identical configuration.
- [ ] Representative concurrent load testing; calibrate runtime allowances.
- [x] PII-Tracer bidirectional token-classification deployment, authenticated scoring/masking,
  encoder-specific sizing, full-context checks and synthetic-email notebook.
- [ ] Specialized MoE/MLA/recurrent/multimodal sizing when workloads require it.
- [ ] Additional GPU families and multi-MIG parallelism need hardware/runtime evidence.
- [x] Recover ended CPU preparation stages automatically, with archived ownership
  evidence, distinct attempts and stale-result removal; unknown submissions block retries.
- [x] Explicit rollback to the reviewed predecessor and renewal by same-profile
  replacement; durable retry/resume without duplicate allocations. Offline regression-tested.
- [ ] Live validation of preparation expiry recovery, rollback and renewal.
- [ ] Automatic scheduled renewal and transactional replacement without downtime.
  Explicit replacement/rollback/renewal currently require downtime and new allocations.
- [ ] Choose GitHub destination and publish when requested.
