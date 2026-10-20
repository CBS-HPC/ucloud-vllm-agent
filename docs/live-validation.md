# Live CLI validation — 2026-10-06

Publication note: historical operational identifiers use role labels and example URLs; measurements and runtime behavior are retained. Exact identities belong in private journals.

The later [2026-10-20 isolated bootstrap trial](bootstrap-live-validation.md)
validates the no-prior-job path. The historical template-mode evidence below
remains unchanged and does not establish current uptime.

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
comparison had not been run at this earlier stage; the follow-up below records
the completed comparison.

Live findings fixed in code and regression tests:

- Accept secure `wss://` provider URLs as well as HTTPS origins.
- Generate Linux shell line endings on Windows and set initialization mode 0755.
- Wait for the owned session's port to be released before restart; never kill by port/name.
- Retry Windows journal replacement on transient sharing violations, without retrying submission.
- Isolate unit-test lifecycle locks from the real deployment lock.

The follow-up below covers preparation recovery, full-context PII load and explicit
rollback/renewal. Remaining limits include specialized architectures/other hardware,
multi-MIG parallelism, long-duration load, automatic scheduled renewal and
transactional replacement without downtime.

## Follow-up benchmarks on 2026-10-06

Public HTTPS measurements used the pinned Qwen and PII profiles on a single
B200 MIG 1g.23gb slice. Sanitized numeric evidence is committed in
[benchmark-results.json](benchmark-results.json); commands and measurement
boundaries are documented in [benchmarks.md](benchmarks.md).

Three Qwen restarts in job **lifecycle-qwen-gpu** used identical engine settings (4096
context, concurrency 1) and the same isolated compilation-cache group. Every
measurement started with an already stopped service. Cold compilation took
**148.089 seconds**; two warm starts took **45.176** and **45.162 seconds**.
The mean warm run was about **3.28 times faster**, a 69.5% reduction in this
startup-and-verification interval. Model weights and the environment were already
cached for all runs; no shared caches were cleared. This measures compilation
reuse, not download performance or GPU provisioning time.

| Public HTTP workload | Successful requests | Clients | Input tokens/request | Median seconds | p95 seconds | Requests/second |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen short chat | 32/32 | 1 | 41–42 | 0.225 | 0.273 | 4.285 |
| PII synthetic Danish email | 64/64 | 2 | 67 | 0.1705 | 0.376 | 8.462 |
| PII full-context synthetic text | 32/32 | 2 | 4096 | 0.3495 | 0.412 | 5.548 |

PII ran in job **lifecycle-pii-gpu**. The full-context fixture was constructed using the
actual cached tokenizer; every returned token count was exactly 4096. Checks
validated model identity and PII span offsets. These short runs include network
and proxy overhead and do not measure Danish PII detection accuracy or establish
sustained throughput across other models.

During full-context PII load, 200 device-memory samples at 0.1-second intervals
reported 1,896,153,088 bytes used (about 1.77 GiB) on a 22,011,707,392-byte slice.
The sampler's CUDA context is included, and brief allocator peaks may be missed.
The existing encoder activation allowance and 3 GiB runtime reserve are retained;
the measured workload supports the selected slice without justifying smaller
unverified products or lower safety margins.

Live restart findings fixed and regression-tested:

- The transport now allows 180 seconds for the helper's bounded per-port shutdown waits.
- Linux port probes use address reuse to distinguish a live listener from closed
  connections in TIME_WAIT. A focused live reproducer failed before the fix and
  passed afterward; a Linux regression test also checks that live listeners block.
- The final comparison was rerun after those fixes. Failed pilot measurements are
  excluded from the benchmark table.

## Recovery, rollback and renewal follow-up

All three endpoint paths and their task/authentication checks passed after each
operation. These were temporary validation allocations; **all nine recorded CPU
and GPU jobs ended with SUCCESS** after explicit cleanup. Templates, mounted
credentials, model downloads and compilation caches were preserved.

- Preparation: owned CPU job **lifecycle-ended-cpu** was deliberately ended after preparation
  but before activation. Recovery archived it, created **lifecycle-recovery-cpu**, reused the
  cached environment/model, activated the bundle and submitted GPU **lifecycle-qwen-gpu**.
  This tests the terminal-state recovery path without spending an hour waiting
  for literal allocation expiry; naturally expired-job recovery remains covered
  by the same branch rather than a separately observed clock-expiry event.
- Replacement: Qwen **lifecycle-qwen-gpu** was replaced by PII **lifecycle-pii-gpu**; observed public
  model-listing unavailability was **43.809 seconds**.
- Rollback: the exact owned PII process was stopped to simulate failure. Rollback
  restored the pinned predecessor Qwen profile in **rollback-qwen-gpu**, passing inference
  and streaming. The command took **72.9 seconds**, with **68.014 seconds** of
  observed public unavailability including the injected failure. Repeating
  rollback reused job rollback-qwen-gpu without another bundle/allocation.
- Renewal: the same pinned Qwen model/machine profile was replaced with a new
  one-hour allocation **renewed-qwen-gpu**. The observed outage was **46.236 seconds**.
  Repeating renewal reused that same job and passed verification. The renewed
  allocation was then explicitly released with the other validation records.

Availability was polled through public HTTPS `/v1/models` every 0.5 seconds with
a two-second request timeout. Outage durations are observations at that sampling
resolution, not guaranteed bounds. Rollback was tested using an injected stopped
process, not every possible submission/startup failure. Unknown submission outcomes
remain blocking and are exercised by regression tests.

The private [GitHub repository](https://github.com/CBS-HPC/ucloud-vllm-agent)
contains the source, notebooks, model catalog and sanitized benchmark evidence.
Local credentials and detailed runtime journals remain excluded from Git.
