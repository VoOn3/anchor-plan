from services.analyzer import classify_anchor

PURCHASE_ORDER = {
    "priority": 1,
    "recommended": 2,
    "needs_support": 3,
    "has_potential": 4,
    "observe": 5,
    "not_recommended": 6,
}


def generate_anchor_plan(analysis: list[dict], settings: dict,
                         selected_urls: list[str] | None = None,
                         custom_links: dict | None = None) -> list[dict]:
    brand_name = settings.get("brand_name", "")
    distribution = settings.get("anchor_distribution", {})
    links_per_page = settings.get("links_per_page", 3)
    planned_links_count = settings.get("planned_links_count", 0)
    custom_links = custom_links or {}

    pages_for_plan = []
    for page in analysis:
        url = page["url"]
        if selected_urls is not None and url not in selected_urls:
            continue
        pages_for_plan.append(page)

    if planned_links_count > 0 and pages_for_plan:
        links_allocation = _distribute_links(pages_for_plan, planned_links_count)
    else:
        links_allocation = {}
        for p in pages_for_plan:
            links_allocation[p["url"]] = p.get("recommended_links", links_per_page)

    for url, count in custom_links.items():
        if url in links_allocation:
            links_allocation[url] = max(1, int(count))

    plan = []

    for page in pages_for_plan:
        url = page["url"]
        page_link_count = links_allocation.get(url, links_per_page)
        if page_link_count <= 0:
            continue

        keywords_data = page.get("keywords", [])
        keywords = [kw["keyword"] for kw in keywords_data]
        existing_anchors = page.get("existing_anchors", [])
        best_kw = page.get("best_keyword")
        recommendation = page.get("recommendation", "not_recommended")

        current_dist = calculate_current_distribution(
            existing_anchors, keywords, brand_name, url
        )

        strategy = _build_strategy(
            best_keyword=best_kw,
            keywords_data=keywords_data,
            current_dist=current_dist,
            distribution=distribution,
        )

        anchors = _generate_anchors(
            strategy=strategy,
            keywords_data=keywords_data,
            best_keyword=best_kw,
            brand_name=brand_name,
            url=url,
            existing_anchors=existing_anchors,
            count=page_link_count,
        )

        purchase_order = PURCHASE_ORDER.get(recommendation, 6)

        for rec in anchors:
            plan.append({
                "url": url,
                "priority": page["priority"],
                "priority_score": page["priority_score"],
                "recommendation": recommendation,
                "purchase_order": purchase_order,
                "recommended_anchor": rec["anchor"],
                "anchor_type": rec["type"],
                "target_keyword": rec.get("target_keyword", ""),
                "current_position": best_kw["current_position"] if best_kw else None,
                "dynamics": best_kw["dynamics_label"] if best_kw else "n/a",
                "rationale": rec.get("rationale", ""),
                "is_manual": False,
            })

    plan.sort(key=lambda x: (x["purchase_order"], -x["priority_score"]))
    return plan


def _is_type_allowed(anchor_type: str, distribution: dict) -> bool:
    """Type is forbidden if its max is explicitly set to 0."""
    cfg = distribution.get(anchor_type)
    if cfg is None:
        return True
    return cfg.get("max", 100) > 0


def _filter_allowed(types: list[str], distribution: dict) -> list[str]:
    return [t for t in types if _is_type_allowed(t, distribution)]


def _build_strategy(
    best_keyword: dict | None,
    keywords_data: list[dict],
    current_dist: dict,
    distribution: dict,
) -> list[str]:
    """Return ordered list of anchor types to fill."""
    if not best_keyword or not keywords_data:
        return _filter_allowed(["branded", "url"], distribution) or ["url"]

    pos = best_keyword.get("current_position")
    dyn = best_keyword.get("dynamics_label", "stable")

    exact_pct = current_dist.get("exact_match", 0)
    exact_max = distribution.get("exact_match", {}).get("max", 15)
    exact_ok = exact_pct <= exact_max

    branded_pct = current_dist.get("branded", 0)
    branded_min = distribution.get("branded", {}).get("min", 20)
    branded_deficit = branded_pct < branded_min

    has_multiple_kw = len(keywords_data) > 1

    if pos and 4 <= pos <= 10 and dyn == "growth":
        types = []
        if exact_ok:
            types.append("exact_match")
        if has_multiple_kw:
            types.append("partial_match")
        if branded_deficit:
            types.append("branded")
        types.append("url")
        return _filter_allowed(types, distribution) or _filter_allowed(["branded", "url"], distribution) or ["url"]

    if pos and 4 <= pos <= 10 and dyn == "stable":
        types = []
        if has_multiple_kw:
            types.append("partial_match")
        if exact_ok:
            types.append("exact_match")
        if branded_deficit:
            types.append("branded")
        types.append("url")
        return _filter_allowed(types, distribution) or _filter_allowed(["branded", "url"], distribution) or ["url"]

    if pos and 4 <= pos <= 10 and dyn == "decline":
        types = []
        if has_multiple_kw:
            types.append("partial_match")
        types.append("branded")
        types.append("url")
        return _filter_allowed(types, distribution) or _filter_allowed(["branded", "url"], distribution) or ["url"]

    if pos and 11 <= pos <= 20 and dyn == "growth":
        types = []
        if exact_ok:
            types.append("exact_match")
        if has_multiple_kw:
            types.append("partial_match")
        if branded_deficit:
            types.append("branded")
        types.append("url")
        return _filter_allowed(types, distribution) or _filter_allowed(["branded", "url"], distribution) or ["url"]

    if pos and 11 <= pos <= 20:
        types = []
        if has_multiple_kw:
            types.append("partial_match")
        types.append("branded")
        types.append("url")
        return _filter_allowed(types, distribution) or _filter_allowed(["branded", "url"], distribution) or ["url"]

    if pos and 21 <= pos <= 50 and dyn == "growth":
        types = []
        if has_multiple_kw:
            types.append("partial_match")
        if branded_deficit:
            types.append("branded")
        types.append("url")
        return _filter_allowed(types, distribution) or _filter_allowed(["branded", "url"], distribution) or ["url"]

    if pos and 21 <= pos <= 50:
        types = ["branded", "url"]
        if has_multiple_kw:
            types.append("partial_match")
        return _filter_allowed(types, distribution) or ["url"]

    if pos and 1 <= pos <= 3:
        return _filter_allowed(["branded", "url"], distribution) or ["url"]

    return _filter_allowed(["branded", "url"], distribution) or ["url"]


def _generate_anchors(
    strategy: list[str],
    keywords_data: list[dict],
    best_keyword: dict | None,
    brand_name: str,
    url: str,
    existing_anchors: list[str],
    count: int,
) -> list[dict]:
    results = []
    used_anchors = {a.lower().strip() for a in existing_anchors}
    used_keywords = set()

    ranked_kw = _rank_keywords(keywords_data)

    for anchor_type in strategy:
        if len(results) >= count:
            break

        anchor = _create_anchor(
            anchor_type, ranked_kw, best_keyword,
            brand_name, url, used_keywords, used_anchors,
        )
        if anchor:
            results.append(anchor)
            used_anchors.add(anchor["anchor"].lower().strip())

    cycle_idx = 0
    while len(results) < count and cycle_idx < 50:
        anchor_type = strategy[cycle_idx % len(strategy)]
        cycle_idx += 1

        anchor = _create_anchor(
            anchor_type, ranked_kw, best_keyword,
            brand_name, url, used_keywords, used_anchors,
        )
        if anchor:
            results.append(anchor)
            used_anchors.add(anchor["anchor"].lower().strip())

    return results[:count]


def _rank_keywords(keywords_data: list[dict]) -> list[dict]:
    """Sort keywords by priority: position 4-20 decline first, then growth, then stable."""
    scored = []
    for kw in keywords_data:
        pos = kw.get("current_position")
        if pos is None:
            scored.append((-1000, kw))
            continue
        dyn = kw.get("dynamics", 0)
        dyn_label = kw.get("dynamics_label", "stable")

        if 4 <= pos <= 10:
            base = 200
        elif 11 <= pos <= 20:
            base = 150
        elif 21 <= pos <= 50:
            base = 80
        elif 1 <= pos <= 3:
            base = 50
        else:
            base = 10

        dyn_bonus = 0
        if dyn_label == "decline":
            dyn_bonus = 20
        elif dyn_label == "growth":
            dyn_bonus = 10

        score = base - pos + dyn_bonus + dyn
        scored.append((score, kw))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [kw for _, kw in scored]


def _create_anchor(
    anchor_type: str,
    ranked_kw: list[dict],
    best_keyword: dict | None,
    brand_name: str,
    url: str,
    used_keywords: set,
    used_anchors: set,
) -> dict | None:

    if anchor_type == "exact_match":
        kw = _pick_keyword(ranked_kw, used_keywords, prefer_best=True, best_keyword=best_keyword)
        if not kw:
            return None
        anchor_text = kw["keyword"]
        if anchor_text.lower().strip() in used_anchors:
            return None
        used_keywords.add(kw["keyword"])
        pos = kw.get("current_position")
        dyn = kw.get("dynamics_label", "stable")
        return {
            "anchor": anchor_text,
            "type": "exact_match",
            "target_keyword": kw["keyword"],
            "rationale": f"Exact «{kw['keyword']}» (поз. {pos}, {dyn})",
        }

    if anchor_type == "partial_match":
        kw = _pick_keyword(ranked_kw, used_keywords, prefer_best=False, best_keyword=best_keyword)
        if not kw:
            return None
        anchor_text = kw["keyword"]
        if anchor_text.lower().strip() in used_anchors:
            return None
        used_keywords.add(kw["keyword"])
        pos = kw.get("current_position")
        dyn = kw.get("dynamics_label", "stable")
        return {
            "anchor": anchor_text,
            "type": "partial_match",
            "target_keyword": kw["keyword"],
            "rationale": f"Ключ «{kw['keyword']}» (поз. {pos}, {dyn})",
        }

    if anchor_type == "branded":
        if brand_name:
            anchor_text = brand_name
        else:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            anchor_text = parsed.netloc.replace("www.", "")
        if anchor_text.lower().strip() in used_anchors:
            return None
        return {
            "anchor": anchor_text,
            "type": "branded",
            "target_keyword": "",
            "rationale": f"Брендовий анкор",
        }

    if anchor_type == "url":
        if url.lower().strip() in used_anchors:
            return None
        return {
            "anchor": url,
            "type": "url",
            "target_keyword": "",
            "rationale": "Безанкорне посилання (повний URL)",
        }

    return None


def _pick_keyword(
    ranked_kw: list[dict],
    used_keywords: set,
    prefer_best: bool,
    best_keyword: dict | None,
) -> dict | None:
    if prefer_best and best_keyword and best_keyword["keyword"] not in used_keywords:
        return best_keyword

    for kw in ranked_kw:
        if kw["keyword"] not in used_keywords:
            return kw
    return None


def calculate_current_distribution(
    anchors: list[str], keywords: list[str], brand_name: str, url: str
) -> dict:
    types_count = {
        "exact_match": 0, "partial_match": 0, "branded": 0,
        "generic": 0, "url": 0, "other": 0,
    }
    total = len(anchors) or 1
    for anchor in anchors:
        atype = classify_anchor(anchor, keywords, brand_name, url)
        if atype in types_count:
            types_count[atype] += 1
        else:
            types_count["other"] += 1
    return {atype: round((count / total) * 100, 1) for atype, count in types_count.items()}


def _distribute_links(pages: list[dict], total_links: int) -> dict:
    raw_weights = []
    for p in pages:
        raw_weights.append(p.get("recommended_links", 3))

    total_raw = sum(raw_weights) or len(pages)
    scale = total_links / total_raw

    allocation = {}
    remaining = total_links
    for i, page in enumerate(pages):
        if i == len(pages) - 1:
            count = max(1, remaining)
        else:
            count = max(1, round(raw_weights[i] * scale))
            count = min(count, remaining)
        allocation[page["url"]] = count
        remaining -= count
        if remaining <= 0:
            break

    return allocation
