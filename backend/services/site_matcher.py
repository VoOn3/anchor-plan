import math
from services.site_filter import filter_sites


PRICE_FIELD = "Ціна розміщення стаття, UAH"

ANCHOR_TYPE_PRIORITY = {
    "exact_match": 1,
    "partial_match": 2,
    "branded": 3,
    "url": 4,
}

MIN_QUALITY_BY_TYPE = {
    "exact_match": 40,
    "partial_match": 30,
    "branded": 20,
    "url": 0,
}

BUDGET_FLEX_BY_TYPE = {
    "exact_match": 1.4,
    "partial_match": 1.2,
    "branded": 1.0,
    "url": 0.9,
}


def match_sites_to_plan(plan: list[dict], sites: list[dict], filters: list[dict],
                         budget: float, domain: str = "") -> dict:
    filtered = filter_sites(sites, filters) if filters else sites
    scored = _score_sites(filtered, domain)
    scored.sort(key=lambda x: x["_quality_score"], reverse=True)

    sorted_plan = _sort_plan_by_anchor_priority(plan)

    total_rows = len(sorted_plan)
    remaining_budget = budget if budget > 0 else float("inf")
    used_domains: set[str] = set()
    results: dict[int, dict] = {}
    total_cost = 0.0

    # --- Pass 1: strict quality + budget per link ---
    unmatched_indexes = []
    for entry in sorted_plan:
        idx = entry["original_index"]
        anchor_type = entry["anchor_type"]
        rows_left = total_rows - len(results)
        budget_per_link = remaining_budget / rows_left if rows_left > 0 else 0

        flex = BUDGET_FLEX_BY_TYPE.get(anchor_type, 1.0)
        max_price = budget_per_link * flex
        min_quality = MIN_QUALITY_BY_TYPE.get(anchor_type, 0)

        site = _find_site(scored, used_domains, max_price, min_quality)
        if site:
            assignment = _make_assignment(idx, site)
            results[idx] = assignment
            used_domains.add(site["_domain_key"])
            price = assignment["site_price"]
            remaining_budget -= price
            total_cost += price
        else:
            unmatched_indexes.append(entry)

    # --- Pass 2: relaxed — lower quality threshold, use remaining budget ---
    still_unmatched = []
    for entry in unmatched_indexes:
        idx = entry["original_index"]
        rows_left = len(unmatched_indexes) - len(still_unmatched)
        if rows_left <= 0:
            rows_left = 1
        budget_per_link = remaining_budget / rows_left

        site = _find_site(scored, used_domains, budget_per_link * 1.1, min_quality=0)
        if site:
            assignment = _make_assignment(idx, site)
            results[idx] = assignment
            used_domains.add(site["_domain_key"])
            price = assignment["site_price"]
            remaining_budget -= price
            total_cost += price
        else:
            still_unmatched.append(entry)

    # --- Build ordered assignments list ---
    assignments = []
    for i in range(len(plan)):
        if i in results:
            assignments.append(results[i])
        else:
            assignments.append(_empty_assignment(i))

    matched = sum(1 for a in assignments if a["assigned_site"])

    return {
        "assignments": assignments,
        "total_plan": len(plan),
        "matched": matched,
        "not_matched": len(plan) - matched,
        "total_cost": round(total_cost, 2),
        "remaining_budget": round(remaining_budget, 2) if budget > 0 else 0,
        "filtered_sites_count": len(filtered),
    }


def _sort_plan_by_anchor_priority(plan: list[dict]) -> list[dict]:
    indexed = []
    for i, row in enumerate(plan):
        anchor_type = row.get("anchor_type", "url")
        type_prio = ANCHOR_TYPE_PRIORITY.get(anchor_type, 4)
        purchase_order = row.get("purchase_order", 6)
        priority_score = row.get("priority_score", 0)
        indexed.append({
            "original_index": i,
            "anchor_type": anchor_type,
            "sort_key": (type_prio, purchase_order, -priority_score),
        })
    indexed.sort(key=lambda x: x["sort_key"])
    return indexed


def _find_site(scored_sites: list[dict], used_domains: set,
               max_price: float, min_quality: float) -> dict | None:
    for site in scored_sites:
        dk = site["_domain_key"]
        if dk in used_domains:
            continue
        if site["_quality_score"] < min_quality:
            continue
        price = _site_price(site)
        if price > max_price:
            continue
        return site
    return None


def _site_price(site: dict) -> float:
    p = site.get(PRICE_FIELD)
    if p and isinstance(p, (int, float)):
        return float(p)
    return 0.0


def _make_assignment(plan_index: int, site: dict) -> dict:
    price = _site_price(site)
    return {
        "plan_index": plan_index,
        "assigned_site": site.get("Домен", ""),
        "site_url": site.get("URL Коллаборатора", ""),
        "site_dr": site.get("DR"),
        "site_traffic": site.get("Трафік на місяць"),
        "site_organic": site.get("Органічний трафік"),
        "site_price": price,
        "site_quality": site["_quality_score"],
        "site_theme": site.get("Тематика", ""),
    }


def _empty_assignment(plan_index: int) -> dict:
    return {
        "plan_index": plan_index,
        "assigned_site": None,
        "site_url": None,
        "site_dr": None,
        "site_traffic": None,
        "site_organic": None,
        "site_price": 0,
        "site_quality": 0,
        "site_theme": "",
    }


def _score_sites(sites: list[dict], domain: str) -> list[dict]:
    if not sites:
        return []

    max_dr = max((_num(s.get("DR")) or 0 for s in sites), default=1) or 1
    max_traffic = max((_num(s.get("Органічний трафік")) or 0 for s in sites), default=1) or 1
    max_age = max((_num(s.get("Вік сайту, років")) or 0 for s in sites), default=1) or 1

    prices = [_num(s.get(PRICE_FIELD)) for s in sites if _num(s.get(PRICE_FIELD))]
    max_price = max(prices, default=1) or 1

    domain_lower = domain.lower().strip() if domain else ""

    for site in sites:
        dr = _num(site.get("DR")) or 0
        traffic = _num(site.get("Органічний трафік")) or 0
        age = _num(site.get("Вік сайту, років")) or 0
        price = _num(site.get(PRICE_FIELD)) or 0

        dr_score = (dr / max_dr) * 100
        traffic_score = (math.log1p(traffic) / math.log1p(max_traffic)) * 100
        age_score = (age / max_age) * 100
        price_score = (1 - price / max_price) * 100 if max_price > 0 else 50

        theme_score = 50.0
        theme = str(site.get("Тематика", "")).lower()
        if domain_lower and domain_lower in theme:
            theme_score = 100.0

        total = (
            dr_score * 0.30 +
            traffic_score * 0.25 +
            theme_score * 0.20 +
            price_score * 0.15 +
            age_score * 0.10
        )

        site["_quality_score"] = round(total, 1)
        site_domain = str(site.get("Домен", "")).lower().strip()
        site["_domain_key"] = site_domain.replace("https://", "").replace("http://", "").rstrip("/")

    return sites


def _num(val) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None
