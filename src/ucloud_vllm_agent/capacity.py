from __future__ import annotations

import math

from .config import positive_int

GIB = 1024 ** 3
# Initial estimator covers conventional dense decoder attention. MLA, hybrid,
# MoE and multimodal layouts need their own evidence rather than this formula.
DENSE_TYPES = {"llama", "qwen2", "qwen3", "mistral", "gemma", "gemma2", "gemma3_text"}


def estimate_capacity(request: dict, metadata: dict, machines: list[dict]) -> dict:
    config = metadata.get("config", {})
    blockers = []
    pooling = request.get("task") == "pii"
    if pooling:
        if (metadata.get("model") != "perplexity-ai/PII-Tracer-vLLM" or
            config.get("architectures") != ["Qwen3ForTokenClassification"] or
            config.get("is_causal") is not False or config.get("num_labels") != 38 or
            request["context_length"] > 4096 or request["concurrency"] > 2 or request["dtype"] != "bfloat16"):
            blockers.append("pii_pooling_configuration_requires_review")
    elif config.get("is_causal") is False or any("Classification" in a for a in config.get("architectures", [])):
        blockers.append("encoder_or_classifier_requires_task_specific_sizing")
    if config.get("model_type") not in DENSE_TYPES:
        blockers.append("architecture_requires_specific_estimator")
    quantization = config.get("quantization_config") or {}
    method = quantization.get("quant_method")
    checkpoint_bytes = metadata.get("checkpoint_bytes")
    if quantization and (method not in {"awq", "gptq", "fp8"} or
                         not isinstance(checkpoint_bytes, int) or isinstance(checkpoint_bytes, bool) or checkpoint_bytes <= 0):
        blockers.append("quantized_model_requires_pinned_checkpoint_sizes_and_supported_method")
    if ((method == "awq" and quantization.get("bits") != 4) or
        (method == "gptq" and quantization.get("bits") not in (4, 8))):
        blockers.append("quantized_bit_width_requires_review")
    if any(config.get(key) for key in ("num_local_experts", "num_experts", "vision_config", "kv_lora_rank")):
        blockers.append("specialized_memory_layout_requires_review")
    if config.get("layer_types") and any(kind not in ("full_attention", "sliding_attention") for kind in config["layer_types"]):
        blockers.append("hybrid_recurrent_layout_requires_review")
    parameters = metadata.get("parameters")
    required_fields = ("num_hidden_layers", "num_attention_heads", "hidden_size")
    try:
        parameters = positive_int(parameters, "model parameters")
        for key in required_fields:
            positive_int(config.get(key), key)
        heads = config["num_attention_heads"]
        kv_heads = positive_int(config.get("num_key_value_heads", heads), "num_key_value_heads")
        head_dim = config.get("head_dim")
        if head_dim is None:
            if config["hidden_size"] % heads:
                raise ValueError("hidden_size must divide into attention heads")
            head_dim = config["hidden_size"] // heads
        positive_int(head_dim, "head_dim")
    except ValueError:
        blockers.append("missing_or_invalid_model_dimensions")
    max_context = config.get("max_position_embeddings")
    if isinstance(max_context, int) and request["context_length"] > max_context:
        blockers.append("context_exceeds_model_config")
    if blockers:
        return {"status": "needs_review", "blockers": blockers, "recommendation": None, "candidates": []}
    dtype_bytes = 4 if request["dtype"] == "float32" else 2
    weight_bytes = checkpoint_bytes if quantization else parameters * dtype_bytes
    kv_dtype_bytes = 1 if request.get("kv_cache_dtype", "auto").startswith("fp8") else dtype_bytes
    tokens = request["context_length"] * request["concurrency"]
    kv_bytes = 2 * config["num_hidden_layers"] * kv_heads * head_dim * tokens * kv_dtype_bytes
    activation_bytes = 0
    if pooling:
        kv_bytes = 0  # Bidirectional encoder does not retain generative KV state.
        activation_bytes = tokens * config["hidden_size"] * config["num_hidden_layers"] * dtype_bytes * 4
    candidates = []
    for machine in machines:
        count = positive_int(machine.get("gpu_count"), "machine gpu_count")
        vram = machine.get("vram_gib_per_gpu")
        ram = machine.get("ram_gib")
        if not isinstance(vram, (int, float)) or not math.isfinite(vram) or vram <= 0:
            raise ValueError("Machine requires finite positive per-device VRAM")
        if not isinstance(ram, (int, float)) or not math.isfinite(ram) or ram <= 0:
            raise ValueError("Machine requires finite positive system RAM")
        reasons = []
        if pooling and count != 1:
            reasons.append("pii_pooling_parallelism_not_validated")
        if machine.get("mig") and count > 1:
            reasons.append("multi_slice_mig_not_assumed_tensor_parallel")
        if heads % count or (kv_heads % count if kv_heads >= count else count % kv_heads):
            reasons.append("attention_heads_not_compatible_with_tensor_parallel_size")
        # KV heads replicate when TP exceeds KV head count. Never divide by TP
        # unconditionally. Weight overhead also allows for imperfect sharding.
        per_device_kv = kv_bytes / min(count, kv_heads)
        required = (weight_bytes / count * (1 + request["weight_overhead_fraction"]) + per_device_kv) / GIB
        required += request["runtime_reserve_gib"]
        required += activation_bytes / GIB
        usable = vram * request["gpu_memory_utilization"]
        # Advisory RAM/storage allowances, recorded separately from GPU fit.
        host_ram = weight_bytes / GIB * 1.5 + 8
        if required > usable:
            reasons.append("insufficient_vram")
        if host_ram > ram:
            reasons.append("insufficient_estimated_system_ram")
        candidates.append({**machine, "tensor_parallel_size": count,
                           "required_gib_per_gpu": round(required, 3),
                           "usable_gib_per_gpu": round(usable, 3),
                           "memory_margin_gib_per_gpu": round(usable - required, 3),
                           "fits_estimate": not reasons, "reasons": reasons})
    fitting = [candidate for candidate in candidates if candidate["fits_estimate"]]
    # Prefer the least total allocated VRAM. This is a sizing choice, not a
    # price/latency ranking; rates and availability require project inspection.
    fitting.sort(key=lambda item: (item["gpu_count"] * item["vram_gib_per_gpu"], item["gpu_count"]))
    minimum = fitting[0] if fitting else None
    # Prefer >=10% headroom inside the serving budget, in addition to the
    # memory outside gpu_memory_utilization. This is not a throughput guarantee.
    comfortable = [m for m in fitting if m["required_gib_per_gpu"] <= m["usable_gib_per_gpu"] * 0.9]
    recommendation = comfortable[0] if comfortable else minimum
    return {
        "status": "estimated" if recommendation else "no_fit",
        "blockers": [] if recommendation else ["no_machine_fits_estimate"],
        "weight_gib": round(weight_bytes / GIB, 3), "kv_cache_gib_total": round(kv_bytes / GIB, 3),
        "encoder_activation_gib_allowance": round(activation_bytes / GIB, 3),
        "required_system_ram_gib_estimate": round(weight_bytes / GIB * 1.5 + 8, 3),
        "required_disk_gib_estimate": round((checkpoint_bytes or weight_bytes) / GIB * 2 + 10, 3),
        "weight_method": "pinned_quantized_checkpoint_bytes" if quantization else "dense_parameters_times_dtype",
        "quantization_method": method, "kv_cache_dtype": request.get("kv_cache_dtype", "auto"),
        "minimum_machine": minimum,
        "assumptions": (["bidirectional PII encoder: no retained generative KV cache",
                         "encoder activation allowance is four times all-layer hidden-state bytes plus runtime reserve",
                         "initial validated envelope: bfloat16, one GPU, at most two 4096-token inputs"] if pooling else []) + ["full context occupied for every concurrent request",
                        "KV cache uses the explicitly requested cache dtype", "no prefix-sharing discount",
                        "10% weight allowance by default plus configurable per-device runtime reserve",
                        "RAM and disk allowances are heuristics; verify actual checkpoint/cache sizes",
                        "memory fit does not establish vLLM/kernel compatibility or throughput",
                        "quantized checkpoint bytes include packed weights/scales; runtime/dequantization overhead still requires GPU profiling"],
        "recommendation": recommendation, "candidates": candidates,
    }
