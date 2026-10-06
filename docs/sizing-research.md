# Machine sizing decision

Compared on 2026-10-06. Keep a project-owned estimator and validate it against
the pinned vLLM runtime. No compared tool certifies fit on a UCloud MIG allocation.
External tools remain optional second opinions, with no new required dependency.

| Candidate | Useful capability | Limit for this workflow | Decision |
| --- | --- | --- | --- |
| [llm-checker](https://github.com/signerless/llm-checker/blob/7b16fa1b36d0bce040b42ce6e3db4cfd925d6c19/src/models/deterministic-selector.js) | JSON CLI/API | Parameter-based KV approximation, no inspected concurrency term, pooled GPU capacity; restrictive NPDL license | Do not integrate |
| [llmfit](https://github.com/AlexsJones/llmfit/blob/f363a09dfc29cbf1b8cec042a3df473e9aba2b4f/llmfit-core/src/models.rs) | MIT; JSON CLI; vLLM quantization targets, GQA and concurrency support | Metadata fallbacks, fixed overhead and pooled GPU memory remain estimates | Best optional cross-check |
| [GPUStack](https://github.com/gpustack/gpustack/blob/4a1b963f99f434d9633510bbf47b51655f33328a/gpustack/policies/candidate_selectors/vllm_resource_fit_selector.py) | vLLM topology/parallelism scheduling | Weight/reserve heuristic does not fully budget requested context/concurrency; unnecessary server/worker stack | Architecture reference |
| [Accelerate](https://huggingface.co/docs/accelerate/en/usage_guides/model_size_estimator) | Weight/largest-layer estimates without loading weights | No complete vLLM KV, CUDA graph or concurrency budget | Optional weight cross-check |
| [Can I Use LLM](https://www.caniusellm.com/) | Interactive explanation | Name-based bands and fixed memory tables; no verified workflow API | Human exploration |

Dense MHA/GQA estimates use pinned configuration dimensions and reserve full
input-plus-output context for every concurrent sequence. AWQ/GPTQ/FP8 weights
require actual pinned checkpoint sizes, including scales and packed weights.
Quantized weights do not imply quantized KV: FP8 KV is requested separately.
Unknown architecture, MoE, MLA, recurrent hybrid and multimodal layouts produce
a review case without a machine recommendation.

`catalog` reads project wallets and actual compute products through released
ucloud-api. The initial mapping covers SDU B200 full GPUs and 1g.23gb slices.
Memory allowances are conservative: 160 GiB/full GPU and measured 20.5 GiB/slice.
Catalog membership does not establish immediate availability. Prices retain
original accounting units, without a currency or cheapest-machine claim.
See [UCloud products](https://docs.cloud.sdu.dk/guide/resources-products.html).

Fit is checked per device with attention/KV-head divisibility and replication.
Multiple MIG slices require manual runtime validation before tensor parallelism.
This is a validation limit: recent NCCL has
[experimental MIG communication](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/usage/communicators.html#using-mig-instances).

Reports include minimum/recommended allocations, memory margins, RAM/disk
allowances and rejection reasons. Memory fit does not predict throughput.
After launch, numeric vLLM profiling must confirm sufficient KV tokens and
full-context concurrency, alongside loopback/nginx/public inference checks.
See [vLLM runtime capacity](https://docs.vllm.ai/en/v0.18.0/serving/parallelism_scaling/).
Concurrent load testing remains necessary for performance targets.
