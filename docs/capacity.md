# Capacity estimates

For supported conventional dense decoder models:

```
weights = total parameters * runtime dtype bytes
tokens = total context length * concurrent sequences
KV = 2 * layers * KV heads * head dimension * tokens * dtype bytes
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
runtime weight bytes plus 10 GiB. These are allowances, not measured checkpoint
sizes. Recalculate for dtype conversions, extra model revisions, tokenizer files,
download cache behavior and the chosen loader. Compare to actual container RAM,
mounted storage and checkpoint file sizes before launching.

The default candidate list is illustrative and uses conservative VRAM allowances.
It has no authoritative product/category/provider identifiers, prices or live
availability. Prefer the least total allocated VRAM among fitting candidates;
this is not a fastest/cheapest-machine claim. Replace it with project-verified
capacities and the product identifiers supported by the released v0.1.6 API.

Models with unknown architecture, quantization, MoE, MLA, hybrid or multimodal
layout require specific analysis. Model parameter count is total resident weights,
not the number of activated parameters per token. Do not estimate MoE weights
from active parameter count. This first release deliberately returns review cases
for those layouts rather than predicting their GPU fit.
