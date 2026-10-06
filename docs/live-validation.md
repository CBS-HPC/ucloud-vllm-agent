# Live CLI validation — 2026-10-06

Publication note: historical operational identifiers use role labels and example URLs; measurements and runtime behavior are retained. Exact identities belong in private journals.

The full CPU preparation → upload verification → pinned environment/model cache
→ nginx GPU initialization → WEB registration → three-path verification sequence
passed on the B200 MIG baseline. UCLOUD_PROJECT was corrected to the UUID that
owns both explicit templates; credentials were preserved.

| Stage | Job | Result |
| --- | --- | --- |
| First CPU preparation | initial-qwen-cpu | Persistent Weka mount, key match and cached environment/model verified; released |
| First managed GPU | initial-qwen-gpu | Initialization repaired during diagnosis; all checks passed; subsequently replaced/released |
| Replacement CPU preparation | replacement-qwen-cpu | Prepared files and cached model; released |
| Replacement GPU | replacement-qwen-gpu | Initialized automatically; loopback/nginx/public checks passed; retained running |

The replacement serves `Qwen/Qwen2.5-1.5B-Instruct` at commit
`989aa7980e4cf806f80c7fef2b1adb7bc71aa306` as `qwen-small`, with bfloat16,
4096-token context and concurrency 2, on one B200 MIG 1g.23gb slice.
Public API: `https://inference.example.org/v1`.
Recorded allocation expiry: **2026-10-06 13:02:57 Europe/Copenhagen**.
These are dated results; query `status` before assuming current availability.

Durable local evidence is in the ignored bundle
`deployments/qwen-small/<RUN_ID>/`: deployment.json,
hosting-profile.json, checks.json, checks-internal.json, runtime-evidence.json,
restart-timing.json, restart-second-timing.json and concurrent-check*.json.
Detailed per-path checks also reside in the corresponding remote bundle.

Recovery reused job replacement-qwen-gpu without submission. Two restarts passed verification
in the same allocation: 46.385 seconds from an already stopped service, then
78.151 seconds including shutdown of the running service. Eight short requests
with two concurrent clients passed before restart (1.54 seconds total).
This smoke test does not establish sustained throughput or full-context latency.

Runtime profiling reported 2.98 GiB model weights, 13.37 GiB available KV cache,
500,848 KV tokens and theoretical full-context concurrency 122.28. Serving remains
capped at the requested concurrency 2. Weight planning was approximately 2.875 GiB;
its overhead allowance covers the observed difference. The KV capacity figure is
a memory budget, not a throughput or supported client-count claim.

Both GPU jobs used kernel namespace `runtime-cache-a`. It contained 468
files after restart; cache-load messages appeared in the runtime log. The pinned
3,087,467,144-byte weight file retained its earlier timestamp. Models and kernel
caches therefore survived GPU replacement. A controlled cold-versus-warm
performance comparison remains future work.

Live findings fixed in code and regression tests:

- Accept secure `wss://` provider URLs as well as HTTPS origins.
- Generate Linux shell line endings on Windows and set initialization mode 0755.
- Wait for the owned session's port to be released before restart; never kill by port/name.
- Retry Windows journal replacement on transient sharing violations, without retrying submission.
- Isolate unit-test lifecycle locks from the real deployment lock.

Remaining limits: sizing for specialized architectures/other hardware, multi-MIG
parallelism validation, sustained/full-context benchmarks, automatic renewal,
expired preparation-stage recovery and transactional replacement rollback.
