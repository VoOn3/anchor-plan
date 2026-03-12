import re
from collections import defaultdict


def analyze_pages(positions_data: list[dict], ahrefs_data: list[dict]) -> list[dict]:
    page_keywords = defaultdict(list)
    for item in positions_data:
        page_keywords[item["url"]].append({
            "keyword": item["keyword"],
            "positions": item["positions"],
        })

    page_anchors = defaultdict(list)
    for item in ahrefs_data:
        if item["target_url"]:
            page_anchors[item["target_url"]].append(item)

    all_urls = set(page_keywords.keys()) | set(page_anchors.keys())

    results = []
    for url in sorted(all_urls):
        keywords = page_keywords.get(url, [])
        anchors = page_anchors.get(url, [])

        keyword_analysis = []
        for kw in keywords:
            positions = kw["positions"]
            sorted_dates = sorted(positions.keys())
            current_pos = positions[sorted_dates[-1]] if sorted_dates else None
            prev_pos = positions[sorted_dates[-2]] if len(sorted_dates) >= 2 else None
            first_pos = positions[sorted_dates[0]] if sorted_dates else None

            dynamics = calculate_dynamics(current_pos, prev_pos, first_pos)

            keyword_analysis.append({
                "keyword": kw["keyword"],
                "current_position": current_pos,
                "previous_position": prev_pos,
                "first_position": first_pos,
                "dynamics": dynamics,
                "dynamics_label": get_dynamics_label(dynamics),
                "positions_history": positions,
            })

        anchor_profile = build_anchor_profile(anchors)
        best_keyword = get_best_keyword(keyword_analysis)
        priority = calculate_priority(keyword_analysis)
        recommendation = calculate_url_recommendation(keyword_analysis)

        results.append({
            "url": url,
            "keywords": keyword_analysis,
            "best_keyword": best_keyword,
            "priority": priority["level"],
            "priority_score": priority["score"],
            "recommendation": recommendation["label"],
            "recommendation_order": recommendation["order"],
            "recommendation_reason": recommendation["reason"],
            "anchor_profile": anchor_profile,
            "existing_anchors": [a["anchor"] for a in anchors],
            "raw_anchors": anchors,
            "total_backlinks": len(anchors),
            "dofollow_count": sum(1 for a in anchors if "dofollow" in a.get("link_type", "")),
            "nofollow_count": sum(1 for a in anchors if "nofollow" in a.get("link_type", "")),
            "unique_donors": len({a.get("referring_url", "") for a in anchors if a.get("referring_url")}),
        })

    for page in results:
        page["recommended_links"] = calculate_recommended_links(page)

    results.sort(key=lambda x: x["priority_score"], reverse=True)
    return results


def calculate_dynamics(current: int | None, previous: int | None, first: int | None) -> float:
    if current is None:
        return 0.0
    if previous is not None:
        short_term = previous - current
    else:
        short_term = 0
    if first is not None:
        long_term = first - current
    else:
        long_term = 0
    return round(short_term * 0.6 + long_term * 0.4, 2)


def get_dynamics_label(dynamics: float) -> str:
    if dynamics > 5:
        return "growth"
    elif dynamics < -5:
        return "decline"
    else:
        return "stable"


def build_anchor_profile(anchors: list[dict]) -> dict:
    total = len(anchors) or 1

    unique_anchors = {}
    for a in anchors:
        text = a["anchor"].lower().strip()
        if text not in unique_anchors:
            unique_anchors[text] = {"text": a["anchor"], "count": 0, "type": "unknown"}
        unique_anchors[text]["count"] += 1

    return {
        "total_anchors": len(anchors),
        "unique_anchors": len(unique_anchors),
        "anchors_list": sorted(unique_anchors.values(), key=lambda x: x["count"], reverse=True),
        "distribution": {},
    }


def classify_anchor(anchor_text: str, target_keywords: list[str], brand_name: str, target_url: str) -> str:
    text = anchor_text.lower().strip()

    if not text or text in ["[image]", "[no anchor text]"]:
        return "generic"

    if re.match(r'^https?://\S+$', text) or re.match(r'^www\.\S+$', text):
        return "url"

    if brand_name and brand_name.lower() in text:
        return "branded"

    for kw in target_keywords:
        kw_lower = kw.lower().strip()
        if text == kw_lower:
            return "exact_match"
        if kw_lower in text or text in kw_lower:
            return "partial_match"

    kw_words = set()
    for kw in target_keywords:
        kw_words.update(kw.lower().split())
    text_words = set(text.split())
    overlap = len(kw_words & text_words)
    if overlap >= 2:
        return "partial_match"

    generic_anchors = [
        "тут", "тут.", "сюди", "далі", "детальніше", "дізнатися більше",
        "перейти", "на сайті", "на сайт", "посилання", "click here",
        "here", "read more", "learn more", "this", "link", "website",
        "visit", "source", "click", "check", "view", "see more",
    ]
    if text in generic_anchors:
        return "generic"

    return "other"


def get_best_keyword(keyword_analysis: list[dict]) -> dict | None:
    if not keyword_analysis:
        return None

    scored = []
    for kw in keyword_analysis:
        pos = kw["current_position"]
        if pos is None:
            continue
        if 4 <= pos <= 20:
            score = 100 - pos + kw["dynamics"] * 2
        elif 1 <= pos <= 3:
            score = 50 - pos
        elif 21 <= pos <= 50:
            score = 30 - (pos - 20)
        else:
            score = 0
        scored.append((score, kw))

    if not scored:
        return keyword_analysis[0] if keyword_analysis else None

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def calculate_priority(keyword_analysis: list[dict]) -> dict:
    if not keyword_analysis:
        return {"level": "low", "score": 0}

    best_pos = None
    best_dynamics = 0

    for kw in keyword_analysis:
        pos = kw["current_position"]
        if pos is None:
            continue
        if best_pos is None or pos < best_pos:
            best_pos = pos
            best_dynamics = kw["dynamics"]

    if best_pos is None:
        return {"level": "low", "score": 0}

    if 4 <= best_pos <= 20:
        base_score = 80
        pos_bonus = (20 - best_pos) * 2
    elif 21 <= best_pos <= 50:
        base_score = 40
        pos_bonus = (50 - best_pos)
    elif 1 <= best_pos <= 3:
        base_score = 20
        pos_bonus = 5
    else:
        base_score = 5
        pos_bonus = 0

    dynamics_bonus = max(-20, min(20, best_dynamics * 2))
    decline_penalty = -15 if best_dynamics < -5 else 0

    total_score = base_score + pos_bonus + dynamics_bonus + decline_penalty
    total_score = max(0, min(100, total_score))

    if total_score >= 60:
        level = "high"
    elif total_score >= 30:
        level = "medium"
    else:
        level = "low"

    return {"level": level, "score": round(total_score, 1)}


def calculate_recommended_links(page: dict) -> int:
    keywords = page.get("keywords", [])
    best_kw = page.get("best_keyword")
    anchor_profile = page.get("anchor_profile", {})
    total_backlinks = page.get("total_backlinks", 0)

    # Factor 1: positional need (0-5)
    pos = best_kw.get("current_position") if best_kw else None
    if pos is None:
        pos_links = 2
    elif 1 <= pos <= 3:
        pos_links = 1
    elif 4 <= pos <= 10:
        pos_links = 3
    elif 11 <= pos <= 20:
        pos_links = 4
    elif 21 <= pos <= 50:
        pos_links = 5
    else:
        pos_links = 2

    # Factor 2: dynamics multiplier
    dyn_label = best_kw.get("dynamics_label", "stable") if best_kw else "stable"
    if dyn_label == "decline":
        dyn_mult = 1.5
    elif dyn_label == "growth":
        dyn_mult = 1.3
    else:
        dyn_mult = 1.0

    # Factor 3: anchor profile deficit (0-3 extra)
    existing_anchors = page.get("existing_anchors", [])
    total_a = len(existing_anchors) or 1
    anchor_types = {"exact_match": 0, "partial_match": 0, "branded": 0, "url": 0}
    kw_list = [kw["keyword"] for kw in keywords]

    for anc in existing_anchors:
        atype = classify_anchor(anc, kw_list, "", page.get("url", ""))
        if atype in anchor_types:
            anchor_types[atype] += 1

    current_pcts = {t: round(c / total_a * 100, 1) for t, c in anchor_types.items()}
    target_mins = {"exact_match": 10, "partial_match": 20, "branded": 20, "url": 10}

    max_deficit = 0
    for atype, target_min in target_mins.items():
        deficit = target_min - current_pcts.get(atype, 0)
        if deficit > max_deficit:
            max_deficit = deficit

    if max_deficit > 10:
        deficit_extra = 2
    elif max_deficit > 5:
        deficit_extra = 1
    else:
        deficit_extra = 0

    result = round(pos_links * dyn_mult + deficit_extra)
    return max(1, min(10, result))


def calculate_url_recommendation(keyword_analysis: list[dict]) -> dict:
    if not keyword_analysis:
        return {"label": "not_recommended", "order": 6, "reason": "Немає даних по ключових словах"}

    best_pos = None
    best_dynamics = 0.0
    best_dynamics_label = "stable"

    for kw in keyword_analysis:
        pos = kw["current_position"]
        if pos is None:
            continue
        if best_pos is None or pos < best_pos:
            best_pos = pos
            best_dynamics = kw["dynamics"]
            best_dynamics_label = kw["dynamics_label"]

    if best_pos is None:
        return {"label": "not_recommended", "order": 6, "reason": "Немає позицій в індексі"}

    if 4 <= best_pos <= 15 and best_dynamics_label == "growth":
        return {
            "label": "priority",
            "order": 1,
            "reason": f"Позиція {best_pos}, зростання — дотиснути в ТОП-3",
        }

    if 4 <= best_pos <= 20 and best_dynamics_label in ("stable", "growth"):
        return {
            "label": "recommended",
            "order": 2,
            "reason": f"Позиція {best_pos}, {'стабільно' if best_dynamics_label == 'stable' else 'зростання'} — хороший кандидат",
        }

    if 4 <= best_pos <= 20 and best_dynamics_label == "decline":
        return {
            "label": "needs_support",
            "order": 3,
            "reason": f"Позиція {best_pos}, падіння — потребує підтримки посиланнями",
        }

    if 21 <= best_pos <= 50 and best_dynamics_label == "growth":
        return {
            "label": "has_potential",
            "order": 4,
            "reason": f"Позиція {best_pos}, зростання — є потенціал росту",
        }

    if 1 <= best_pos <= 3:
        return {
            "label": "observe",
            "order": 5,
            "reason": f"Позиція {best_pos} — вже в ТОП-3, тільки підтримка профілю",
        }

    return {
        "label": "not_recommended",
        "order": 6,
        "reason": f"Позиція {best_pos} — спочатку on-page оптимізація",
    }
