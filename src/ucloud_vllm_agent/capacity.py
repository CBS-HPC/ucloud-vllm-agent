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
    if config.get("model_type") not in DENSE_TYPES:
        blockers.append("architecture_requires_specific_estimator")
    if config.get("quantization_config"):
        blockers.append("quantized_model_requires_specific_estimator")
    if any(config.get(key) for key in ("num_local_experts", "num_experts", "vision_config", "kv_lora_rank")):
        blockers.append("specialized_memory_layout_requires_review")
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
    weight_bytes = parameters * dtype_bytes
    tokens = request["context_length"] * request["concurrency"]
    kv_bytes = 2 * config["num_hidden_layers"] * kv_heads * head_dim * tokens * dtype_bytes
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
        if machine.get("mig") and count > 1:
            reasons.append("multi_slice_mig_not_assumed_tensor_parallel")
        if heads % count or (kv_heads % count if kv_heads >= count else count % kv_heads):
            reasons.append("attention_heads_not_compatible_with_tensor_parallel_size")
        # KV heads replicate when TP exceeds KV head count. Never divide by TP
        # unconditionally. Weight overhead also allows for imperfect sharding.
        per_device_kv = kv_bytes / min(count, kv_heads)
        required = (weight_bytes / count * (1 + request["weight_overhead_fraction"]) + per_device_kv) / GIB
        required += request["runtime_reserve_gib"]
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
                           "fits_estimate": not reasons, "reasons": reasons})
    fitting = [candidate for candidate in candidates if candidate["fits_estimate"]]
    # Prefer the least total allocated VRAM. This is a sizing choice, not a
    # price/latency ranking; rates and availability require project inspection.
    fitting.sort(key=lambda item: (item["gpu_count"] * item["vram_gib_per_gpu"], item["gpu_count"]))
    recommendation = fitting[0] if fitting else None
    return {
        "status": "estimated" if recommendation else "no_fit",
        "blockers": [] if recommendation else ["no_machine_fits_estimate"],
        "weight_gib": round(weight_bytes / GIB, 3), "kv_cache_gib_total": round(kv_bytes / GIB, 3),
        "required_system_ram_gib_estimate": round(weight_bytes / GIB * 1.5 + 8, 3),
        "required_disk_gib_estimate": round(weight_bytes / GIB * 2 + 10, 3),
        "assumptions": ["full context occupied for every concurrent request",
                        "KV cache uses the requested model dtype", "no prefix-sharing discount",
                        "10% weight allowance by default plus configurable per-device runtime reserve",
                        "RAM and disk allowances are heuristics; verify actual checkpoint/cache sizes",
                        "memory fit does not establish vLLM/kernel compatibility or throughput"],
        "recommendation": recommendation, "candidates": candidates,
    }
