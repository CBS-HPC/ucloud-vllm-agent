# Reproducible hosting benchmarks

Run benchmarks only in an authorized owned allocation. Results are synthetic
workload measurements, not general throughput guarantees or PII accuracy scores.
Never clear shared model or compilation caches to manufacture a cold start.

## Concurrent HTTP workloads

```powershell
python scripts/benchmark_endpoint.py --profile config/hosting.qwen-small.json --requests 32 --output artifacts/chat-benchmark.json
python scripts/benchmark_endpoint.py --profile config/hosting.pii-tracer.json --requests 32 --output artifacts/pii-short-benchmark.json
python scripts/benchmark_endpoint.py --profile config/hosting.pii-tracer.json --requests 16 --input-file SYNTHETIC_FULL_CONTEXT.txt --output artifacts/pii-context-benchmark.json
```

The script uses the profile's configured concurrency and authenticates through
the public HTTPS proxy. Chat validates a completed response; PII validates the
returned model, token counts and span offsets. Reports contain request durations,
median and nearest-rank p95 latency, requests/second, and token throughput. Input
and response text and credentials are never recorded. Input-file contents should
be synthetic. Token counts returned by the model establish the actual workload
size; repeating a fixture does not establish full-context coverage.

## Compilation cache comparison

For a reviewed local runtime bundle, an optional `kernel_cache_group` field in
`runtime.json` isolates an experiment under
`/work/vllm/cache/kernels/experiments/GROUP/HARDWARE_RUNTIME_HASH`. The group must
be a lowercase name without path separators. Production defaults are unchanged;
the Hugging Face model cache and pinned environment remain shared.

Prepare a fresh group, then measure one cold-compilation restart and two warm
restarts in the **same GPU job**, with identical model, revision, context,
concurrency and cache group. A restart includes preflight, process shutdown when
needed, engine startup, public readiness and endpoint validation. It excludes
GPU queueing, CPU preparation, downloads and first-time system package setup.
Stop the exact owned service before each measured restart so cold and warm runs
start from the same state. Exclude those explicit stop operations from the timing.
If comparing a restart from a running process, record it separately: its shutdown
duration changes the timing boundary. The final live comparison used already
stopped processes for all three measurements.
Use cache evidence and runtime profiles to verify identical compatibility hashes.
These measurements compare compilation reuse with warm checkpoint storage; they
are not a cold model-download benchmark.

Observed results and job IDs are recorded in live-validation.md after validation.
