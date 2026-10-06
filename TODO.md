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
- [x] Controlled cold/warm compilation startup comparison with identical engine
  configuration in the same job: 148.089 seconds cold, 45.176/45.162 seconds warm.
- [x] Baseline chat and concurrent PII load, including exact 4096-token inputs;
  sampled device memory supports existing conservative runtime allowances.
  Numeric evidence and limits: docs/benchmark-results.json and docs/live-validation.md.
- [ ] Long-duration load and broader model/hardware calibration when workloads require it.
- [x] PII-Tracer bidirectional token-classification deployment, authenticated scoring/masking,
  encoder-specific sizing, full-context checks and synthetic-email notebook.
- [ ] Specialized MoE/MLA/recurrent/multimodal sizing when workloads require it.
- [ ] Additional GPU families and multi-MIG parallelism need hardware/runtime evidence.
- [x] Recover ended CPU preparation stages automatically, with archived ownership
  evidence, distinct attempts and stale-result removal; unknown submissions block retries.
- [x] Explicit rollback to the reviewed predecessor and renewal by same-profile
  replacement; durable retry/resume without duplicate allocations. Live and regression-tested.
- [x] Live validation of ended-preparation recovery, rollback and renewal, including
  repeated-command reuse; controlled CPU termination exercised the expiry recovery branch.
- [ ] Automatic scheduled renewal and transactional replacement without downtime.
  Explicit replacement/rollback/renewal currently require downtime and new allocations.
- [x] Published to private GitHub repository CBS-HPC/ucloud-vllm-agent with CI;
  credentials and runtime artifacts are excluded.
- [x] Offline model catalog of tested chat/anonymisation models and classification
  candidates, including the inspected CLAES preview revision.
- [ ] Review CLAES's full release, serving dependencies/API, sizing and Danish task
  fixtures before adding hosting support; no classification model has been hosted yet.
