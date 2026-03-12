import random
from urllib.parse import urlparse
from services.analyzer import classify_anchor

PURCHASE_ORDER = {
    "priority": 1,
    "recommended": 2,
    "needs_support": 3,
    "has_potential": 4,
    "observe": 5,
    "not_recommended": 6,
}


def generate_anchor_plan(analysis: list[dict], settings: dict, selected_urls: list[str] | None = None) -> list[dict]:
    brand_name = settings.get("brand_name", "")
    distribution = settings.get("anchor_distribution", {})
    links_per_page = settings.get("links_per_page", 3)
    planned_links_count = settings.get("planned_links_count", 0)

    pages_for_plan = []
    for page in analysis:
        url = page["url"]
        if selected_urls is not None and url not in selected_urls:
            continue
        pages_for_plan.append(page)

    if planned_links_count > 0 and pages_for_plan:
        links_allocation = _distribute_links(pages_for_plan, planned_links_count)
    else:
        links_allocation = {p["url"]: links_per_page for p in pages_for_plan}

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

        strategy = determine_anchor_strategy(
            best_keyword=best_kw,
            keywords=keywords_data,
            recommendation=recommendation,
            current_dist=current_dist,
            distribution=distribution,
        )

        recommended = generate_smart_recommendations(
            strategy=strategy,
            keywords=keywords_data,
            best_keyword=best_kw,
            brand_name=brand_name,
            url=url,
            existing_anchors=existing_anchors,
            current_dist=current_dist,
            distribution=distribution,
            count=page_link_count,
        )

        purchase_order = PURCHASE_ORDER.get(recommendation, 6)

        for rec in recommended:
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


def determine_anchor_strategy(
    best_keyword: dict | None,
    keywords: list[dict],
    recommendation: str,
    current_dist: dict,
    distribution: dict,
) -> list[dict]:
    """Returns ordered list of anchor type strategies with weights and reasons."""
    if not best_keyword:
        return [
            {"type": "branded", "weight": 50, "reason": "Немає даних по ключах — безпечний branded"},
            {"type": "url", "weight": 50, "reason": "URL-анкор для природності"},
        ]

    pos = best_keyword.get("current_position")
    dyn = best_keyword.get("dynamics_label", "stable")

    exact_pct = current_dist.get("exact_match", 0)
    partial_pct = current_dist.get("partial_match", 0)
    branded_pct = current_dist.get("branded", 0)
    generic_pct = current_dist.get("generic", 0)

    exact_max = distribution.get("exact_match", {}).get("max", 15)
    branded_min = distribution.get("branded", {}).get("min", 20)

    exact_oversaturated = exact_pct > exact_max
    branded_deficit = branded_pct < branded_min

    strategies = []

    if pos and 4 <= pos <= 10 and dyn == "growth":
        if not exact_oversaturated:
            strategies.append({"type": "exact_match", "weight": 40,
                "reason": f"Позиція {pos}, зростання, exact {exact_pct}% (ліміт {exact_max}%) — дотиснути"})
        strategies.append({"type": "partial_match", "weight": 30,
            "reason": f"Позиція {pos}, partial підсилює сигнал"})
        if branded_deficit:
            strategies.append({"type": "branded", "weight": 20,
                "reason": f"Branded {branded_pct}% (мін. {branded_min}%) — дефіцит"})

    elif pos and 4 <= pos <= 10 and dyn == "stable":
        strategies.append({"type": "partial_match", "weight": 40,
            "reason": f"Позиція {pos}, стагнація — м'який сигнал через partial"})
        if not exact_oversaturated:
            strategies.append({"type": "exact_match", "weight": 25,
                "reason": f"Exact {exact_pct}% — є запас, обережний exact"})
        if branded_deficit:
            strategies.append({"type": "branded", "weight": 25,
                "reason": f"Branded {branded_pct}% (дефіцит) — розбавлення"})

    elif pos and 4 <= pos <= 10 and dyn == "decline":
        strategies.append({"type": "partial_match", "weight": 45,
            "reason": f"Позиція {pos}, падіння — partial без ризику переоптимізації"})
        strategies.append({"type": "branded", "weight": 35,
            "reason": f"Падіння, branded {branded_pct}% — безпечна підтримка"})
        strategies.append({"type": "url", "weight": 10,
            "reason": "URL-анкор для природності профілю"})

    elif pos and 11 <= pos <= 20 and dyn == "growth":
        if not exact_oversaturated:
            strategies.append({"type": "exact_match", "weight": 40,
                "reason": f"Позиція {pos}, зростання, exact {exact_pct}% — агресивніше"})
        strategies.append({"type": "partial_match", "weight": 30,
            "reason": f"Partial для підсилення сигналу"})
        if branded_deficit:
            strategies.append({"type": "branded", "weight": 20,
                "reason": f"Branded {branded_pct}% — дефіцит"})

    elif pos and 11 <= pos <= 20:
        strategies.append({"type": "partial_match", "weight": 45,
            "reason": f"Позиція {pos}, {'стагнація' if dyn == 'stable' else 'падіння'} — partial безпечніше"})
        strategies.append({"type": "branded", "weight": 30,
            "reason": f"Branded {branded_pct}% — розбавлення профілю"})
        strategies.append({"type": "url", "weight": 15,
            "reason": "URL-анкор для природності"})

    elif pos and 21 <= pos <= 50 and dyn == "growth":
        strategies.append({"type": "partial_match", "weight": 40,
            "reason": f"Позиція {pos}, зростання — partial сигнал без ризику"})
        strategies.append({"type": "url", "weight": 20,
            "reason": "URL-анкор для нарощування маси"})
        if branded_deficit:
            strategies.append({"type": "branded", "weight": 25,
                "reason": f"Branded дефіцит — безпечне нарощування"})

    elif pos and 21 <= pos <= 50:
        strategies.append({"type": "branded", "weight": 40,
            "reason": f"Позиція {pos} — branded для безпечного нарощування"})
        strategies.append({"type": "url", "weight": 35,
            "reason": f"Позиція {pos} — URL-анкор для маси"})
        strategies.append({"type": "partial_match", "weight": 15,
            "reason": "Partial для м'якого сигналу"})

    elif pos and 1 <= pos <= 3:
        strategies.append({"type": "branded", "weight": 50,
            "reason": f"ТОП-{pos} — branded для утримання без ризику"})
        strategies.append({"type": "url", "weight": 35,
            "reason": "URL-анкор для природності профілю"})

    else:
        strategies.append({"type": "branded", "weight": 50,
            "reason": "Далекі позиції — безпечний branded"})
        strategies.append({"type": "url", "weight": 35,
            "reason": "URL-анкор для нарощування маси"})

    if not strategies:
        strategies = [
            {"type": "branded", "weight": 50, "reason": "Fallback branded"},
            {"type": "url", "weight": 50, "reason": "Fallback URL-анкор"},
        ]

    strategies.sort(key=lambda x: x["weight"], reverse=True)
    return strategies


def generate_smart_recommendations(
    strategy: list[dict],
    keywords: list[dict],
    best_keyword: dict | None,
    brand_name: str,
    url: str,
    existing_anchors: list[str],
    current_dist: dict,
    distribution: dict,
    count: int,
) -> list[dict]:
    recommendations = []
    existing_lower = {a.lower().strip() for a in existing_anchors}
    used_kw_for_exact = set()

    for s in strategy:
        if len(recommendations) >= count:
            break
        anchor = create_smart_anchor(
            s["type"], keywords, best_keyword, brand_name, url, used_kw_for_exact
        )
        if anchor and anchor["anchor"].lower().strip() not in existing_lower:
            anchor["rationale"] = s["reason"]
            recommendations.append(anchor)
            existing_lower.add(anchor["anchor"].lower().strip())

    attempts = 0
    while len(recommendations) < count and attempts < 10:
        attempts += 1
        for s in strategy:
            if len(recommendations) >= count:
                break
            anchor = create_smart_anchor(
                s["type"], keywords, best_keyword, brand_name, url, used_kw_for_exact
            )
            if anchor and anchor["anchor"].lower().strip() not in existing_lower:
                anchor["rationale"] = s["reason"]
                recommendations.append(anchor)
                existing_lower.add(anchor["anchor"].lower().strip())

    return recommendations[:count]


def create_smart_anchor(
    anchor_type: str,
    keywords: list[dict],
    best_keyword: dict | None,
    brand_name: str,
    url: str,
    used_kw_for_exact: set,
) -> dict | None:
    if anchor_type == "exact_match":
        return _create_exact(keywords, best_keyword, used_kw_for_exact)
    elif anchor_type == "partial_match":
        return _create_partial(keywords, best_keyword, used_kw_for_exact)
    elif anchor_type == "branded":
        return _create_branded(brand_name, url)
    elif anchor_type == "url":
        return _create_url(url)
    return None


def _select_keyword(keywords: list[dict], best_keyword: dict | None, exclude: set) -> dict | None:
    """Pick a keyword prioritizing position 4-20 with best dynamics, excluding already used."""
    candidates = []
    for kw in keywords:
        if kw["keyword"] in exclude:
            continue
        pos = kw.get("current_position")
        if pos is None:
            continue
        dyn = kw.get("dynamics", 0)
        if 4 <= pos <= 20:
            score = 100 - pos + dyn * 2
        elif 21 <= pos <= 50:
            score = 30 - (pos - 20) + dyn
        else:
            score = 5
        candidates.append((score, kw))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    if best_keyword and best_keyword["keyword"] not in exclude:
        return best_keyword
    for kw in keywords:
        if kw["keyword"] not in exclude:
            return kw
    return best_keyword or (keywords[0] if keywords else None)


def _create_exact(keywords: list[dict], best_keyword: dict | None, used: set) -> dict | None:
    kw = _select_keyword(keywords, best_keyword, used)
    if not kw:
        return None
    used.add(kw["keyword"])
    pos = kw.get("current_position")
    return {
        "anchor": kw["keyword"],
        "type": "exact_match",
        "target_keyword": kw["keyword"],
        "rationale": f"Exact match для «{kw['keyword']}» (поз. {pos})",
    }


def _create_partial(keywords: list[dict], best_keyword: dict | None, used: set) -> dict | None:
    kw = _select_keyword(keywords, best_keyword, set())
    if not kw:
        return None
    text = kw["keyword"]
    words = text.split()
    variations = []
    if len(words) >= 2:
        variations.extend([
            text + " ціна", text + " відгуки", "як вибрати " + text,
            "найкращий " + text, "про " + text, text + " огляд",
            "все про " + text, text + " рейтинг", "порівняння " + text,
        ])
    else:
        variations.extend([
            text + " у 2026", "послуги " + text, text + " поради",
            "гід по " + text, text + " для початківців", "що таке " + text,
        ])
    anchor = random.choice(variations) if variations else text
    return {
        "anchor": anchor,
        "type": "partial_match",
        "target_keyword": text,
        "rationale": f"Partial match для «{text}»",
    }


def _create_branded(brand_name: str, url: str) -> dict | None:
    if brand_name:
        options = [
            brand_name, brand_name.lower(), brand_name.capitalize(),
            f"сайт {brand_name}", f"{brand_name} — офіційний сайт",
            f"на {brand_name}", f"від {brand_name}",
        ]
        return {"anchor": random.choice(options), "type": "branded", "target_keyword": "", "rationale": ""}
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "")
    return {"anchor": domain, "type": "branded", "target_keyword": "", "rationale": ""}



def _create_url(url: str) -> dict:
    parsed = urlparse(url)
    options = [url, f"{parsed.scheme}://{parsed.netloc}", parsed.netloc, parsed.netloc.replace("www.", "")]
    return {"anchor": random.choice(options), "type": "url", "target_keyword": "", "rationale": ""}


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
    """Distribute total_links among pages proportionally to priority_score."""
    total_score = sum(p.get("priority_score", 1) for p in pages)
    if total_score <= 0:
        total_score = len(pages)

    allocation = {}
    remaining = total_links
    for i, page in enumerate(pages):
        score = page.get("priority_score", 1)
        share = score / total_score
        count = max(1, round(share * total_links))
        if i == len(pages) - 1:
            count = max(1, remaining)
        else:
            count = min(count, remaining)
        allocation[page["url"]] = count
        remaining -= count
        if remaining <= 0:
            break

    return allocation
