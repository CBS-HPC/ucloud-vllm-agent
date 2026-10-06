# Capacity estimates

For supported conventional dense decoder models:

```
weights = total parameters * runtime dtype bytes (dense)
        OR pinned checkpoint file bytes (supported quantization)
tokens = total context length * concurrent sequences
KV = 2 * layers * KV heads * head dimension * tokens * KV dtype bytes
per-device requirement = weights / TP * (1 + weight allowance)
                       + KV / min(TP, KV heads)
                       + per-device runtime reserve
usable per-device VRAM = device VRAM * gpu-memory-utilization
```

The factor 2 represents keys and values. KV heads can replicate once TP exceeds
their count; dividing KV unconditionally by GPU count underestimates memory.
The estimator requires compatible attention/KV-head division and does not assume
multi-slice MIG tensor parallelism. Memory is evaluated per device, not as one pool.

Defaults: 10% weight allowance, 3 GiB reserve per device, 85% VRAM utilization.
These are configurable planning heuristics. Attention/kernel workspaces, CUDA
graphs, weight replication, tokenizer/process RAM, allocator fragmentation and
actual request mix can change demand. No prefix-cache sharing discount is assumed.

RAM is provisionally 1.5 times runtime weight bytes plus 8 GiB; disk is twice
checkpoint bytes (when known, otherwise runtime weights) plus 10 GiB.
These are allowances, not a free-space measurement. Recalculate for dtype conversions, extra model revisions, tokenizer files,
download cache behavior and the chosen loader. Compare to actual container RAM,
mounted storage and checkpoint file sizes before launching.

The bundled default candidate list remains illustrative. `catalog` reads active
project wallets and actual UCloud products; `size` uses that catalog by default.
The initial automatic mapping covers B200 full GPU and 1g.23gb MIG. CUDA-visible
VRAM must still be checked during startup. Fit is per-device, never pooled.
Reports give the minimum fitting allocation and a recommendation preferring
10% extra headroom inside the utilization budget, plus memory margins. Selection
minimizes allocated VRAM, not price or latency. Accounting rates retain API units.
See [comparison and evidence](sizing-research.md).

AWQ 4-bit, GPTQ 4/8-bit and FP8 checkpoints require pinned file sizes; explicit
FP8 KV halves the KV estimate without assuming that weight quantization changes KV.
Models with unknown architecture/quantization, MoE, MLA, recurrent hybrid or multimodal
layout require specific analysis. Model parameter count is total resident weights,
not the number of activated parameters per token. Do not estimate MoE weights
from active parameter count. This first release deliberately returns review cases
for those layouts rather than predicting their GPU fit.
