"""Project-filtered UCloud products with conservative per-device capacity evidence."""
from __future__ import annotations

from datetime import datetime, timezone

GIB = 1024 ** 3


def project_categories(wallets: list[dict]) -> set[tuple[str, str]]:
    return {(w["paysFor"]["provider"], w["paysFor"]["name"]) for w in wallets
            if w.get("maxUsable", 0) > 0 and w.get("paysFor", {}).get("productType") == "COMPUTE"}


def map_products(products: list[dict], categories: set[tuple[str, str]]) -> list[dict]:
    machines = []
    for product in products:
        category = product.get("category", {})
        identity = (category.get("provider"), category.get("name"))
        name = product.get("name", "")
        count = product.get("gpu")
        if identity not in categories or identity != ("ucloud", "gpu-nvidia-b200") or not count:
            continue
        # Exclude old aliases and unrelated products. IDs come from the API.
        if not (name.endswith("-gpu") or name.endswith("-mig.1g")):
            continue
        mig = name.endswith("-mig.1g")
        memory = product.get("memoryInGigs")
        if not isinstance(memory, (int, float)) or memory <= 0:
            continue
        fraction = product.get("fraction") or {"numerator": 1, "denominator": 1}
        machines.append({"name": name, "gpu_count": count, "vram_gib_per_gpu": 20.5 if mig else 160,
                         "ram_gib": round(memory * 1_000_000_000 / GIB, 2), "mig": mig, "verified": True,
                         "product": {"id": name, "category": category["name"], "provider": category["provider"]},
                         "capacity_evidence": "measured_B200_MIG_2026-10-06" if mig else "conservative_B200_documented_allowance",
                         "capacity_note": "Runtime must verify actual per-device memory; catalog match is not a free-GPU guarantee.",
                         "accounting": {"price": product.get("price"), "fraction": fraction,
                                        "unit": category.get("accountingUnit"),
                                        "frequency": category.get("accountingFrequency")}})
    return machines


def sync_catalog(client, *, live: bool = False) -> dict:
    wallets, products = [], []
    for endpoint, params, target in [
        ("/api/accounting/v2/browseWallets", {"includeChildren": "false", "itemsPerPage": 250}, wallets),
        ("/api/products/v2/browse", {"filterProductType": "COMPUTE", "filterProvider": "ucloud", "itemsPerPage": 250}, products),
    ]:
        seen = set()
        for _ in range(100):
            page = client.request("GET", endpoint, params=params).json()
            target.extend(page.get("items", []))
            token = page.get("next")
            if not token:
                break
            if token in seen:
                raise ValueError("Catalog pagination repeated a cursor")
            seen.add(token)
            params = {**params, "next": token}
        else:
            raise ValueError("Catalog exceeds bounded pagination")
    result = {"schema": "ucloud.vllm.machine_candidates.v1", "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "source": "UCloud products/v2 plus active project wallets",
            "hardware_source": "https://docs.cloud.sdu.dk/guide/resources-products.html",
            "note": "B200 baseline only; other families require measured hardware/runtime validation. No monetary pricing inferred.",
            "machines": map_products(products, project_categories(wallets))}
    if live:
        from dataclasses import asdict
        from ucloud_workflow.availability import check_machine_availability
        result["availability"] = asdict(check_machine_availability(client, products=[m["product"] for m in result["machines"]]))
    return result
