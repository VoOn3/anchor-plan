"""
Міграція: застосувати канонічні URL (www/non-www, http/https) до існуючих проектів.
Об'єднує сторінки з однаковим канонічним URL.
"""
from collections import defaultdict

from services.parser import url_to_canonical
from services.analyzer import (
    build_anchor_profile,
    get_best_keyword,
    calculate_priority,
    calculate_url_recommendation,
    calculate_recommended_links,
)
from services.database import get_db, list_projects, get_project, update_project
import json


def _merge_analysis_pages(analysis: list[dict], priority_ranges: dict | None) -> list[dict]:
    """Об'єднує сторінки з однаковим канонічним URL."""
    if not analysis:
        return analysis

    grouped = defaultdict(list)
    for page in analysis:
        canonical = url_to_canonical(page.get("url", ""))
        if canonical:
            grouped[canonical].append(page)

    results = []
    for canonical_url in sorted(grouped.keys()):
        pages = grouped[canonical_url]
        if len(pages) == 1:
            p = pages[0]
            if url_to_canonical(p.get("url", "")) == p.get("url", ""):
                results.append(p)
                continue
            pages = [p]

        # Мерджимо ключові слова
        kw_merged = {}
        for p in pages:
            for kw in p.get("keywords", []):
                key = (kw.get("keyword") or "").strip().lower()
                if not key:
                    continue
                pos = kw.get("positions_history") or kw.get("positions", {})
                if isinstance(pos, dict):
                    pos = dict(pos)
                else:
                    pos = {}
                if key not in kw_merged:
                    kw_merged[key] = {"keyword": kw.get("keyword", ""), "positions": pos, "volume": kw.get("volume")}
                else:
                    for date, pval in pos.items():
                        existing = kw_merged[key]["positions"].get(date)
                        if existing is None or (pval is not None and pval < existing):
                            kw_merged[key]["positions"][date] = pval
                    if kw.get("volume") is not None and (
                        kw_merged[key]["volume"] is None or kw["volume"] > kw_merged[key]["volume"]
                    ):
                        kw_merged[key]["volume"] = kw["volume"]

        keyword_analysis = []
        for kw in kw_merged.values():
            positions = kw["positions"]
            sorted_dates = sorted(positions.keys())
            current_pos = positions[sorted_dates[-1]] if sorted_dates else None
            prev_pos = positions[sorted_dates[-2]] if len(sorted_dates) >= 2 else None
            first_pos = positions[sorted_dates[0]] if sorted_dates else None
            from services.analyzer import calculate_dynamics, get_dynamics_label
            dynamics = calculate_dynamics(current_pos, prev_pos, first_pos)
            keyword_analysis.append({
                "keyword": kw["keyword"],
                "current_position": current_pos,
                "previous_position": prev_pos,
                "first_position": first_pos,
                "dynamics": dynamics,
                "dynamics_label": get_dynamics_label(dynamics),
                "positions_history": positions,
                "volume": kw.get("volume"),
            })

        # Мерджимо raw_anchors
        all_anchors = []
        for p in pages:
            all_anchors.extend(p.get("raw_anchors", []))

        keyword_strings = [kw["keyword"] for kw in keyword_analysis]
        anchor_profile = build_anchor_profile(all_anchors, keyword_strings)
        best_keyword = get_best_keyword(keyword_analysis)
        priority = calculate_priority(keyword_analysis, priority_ranges)
        recommendation = calculate_url_recommendation(keyword_analysis)
        total_volume = sum(kw.get("volume", 0) or 0 for kw in keyword_analysis)
        best_volume = best_keyword.get("volume") if best_keyword else None

        merged_page = {
            "url": canonical_url,
            "keywords": keyword_analysis,
            "best_keyword": best_keyword,
            "total_volume": total_volume if total_volume else None,
            "best_keyword_volume": best_volume,
            "priority": priority["level"],
            "priority_score": priority["score"],
            "recommendation": recommendation["label"],
            "recommendation_order": recommendation["order"],
            "recommendation_reason": recommendation["reason"],
            "anchor_profile": anchor_profile,
            "existing_anchors": [a["anchor"] for a in all_anchors],
            "raw_anchors": all_anchors,
            "total_backlinks": len(all_anchors),
            "dofollow_count": sum(1 for a in all_anchors if "dofollow" in (a.get("link_type") or "")),
            "nofollow_count": sum(1 for a in all_anchors if "nofollow" in (a.get("link_type") or "")),
            "unique_donors": len({a.get("referring_url", "") for a in all_anchors if a.get("referring_url")}),
        }
        merged_page["recommended_links"] = calculate_recommended_links(merged_page)
        results.append(merged_page)

    results.sort(key=lambda x: x["priority_score"], reverse=True)
    return results


def migrate_project(project_id: str) -> bool:
    """Мігрує один проект. Повертає True якщо були зміни."""
    project = get_project(project_id)
    if not project:
        return False

    analysis = project.get("analysis", [])
    if not analysis:
        return False

    settings = project.get("settings") or {}
    priority_ranges = settings.get("priority_ranges")

    new_analysis = _merge_analysis_pages(analysis, priority_ranges)

    # Оновлюємо plan: url -> canonical
    plan = project.get("plan", [])
    plan_changed = False
    for item in plan:
        old_url = item.get("url", "")
        new_url = url_to_canonical(old_url)
        if new_url != old_url:
            item["url"] = new_url
            plan_changed = True

    # Оновлюємо selected_urls
    selected_urls = project.get("selected_urls", [])
    new_selected = list({url_to_canonical(u) for u in selected_urls})
    selected_changed = new_selected != selected_urls

    # Оновлюємо custom_links: старі ключі -> канонічні
    custom_links = project.get("custom_links", {})
    new_custom = {}
    for url, count in custom_links.items():
        canonical = url_to_canonical(url)
        if canonical not in new_custom or count > new_custom[canonical]:
            new_custom[canonical] = count
    custom_changed = new_custom != custom_links

    kwargs = {"analysis": new_analysis}
    if plan_changed:
        kwargs["plan"] = plan
    if selected_changed:
        kwargs["selected_urls"] = new_selected
    if custom_changed:
        kwargs["custom_links"] = new_custom
    update_project(project_id, **kwargs)
    return True


def run_migration():
    """Застосовує міграцію до всіх проектів у базі."""
    projects = list_projects()
    migrated = 0
    for p in projects:
        if migrate_project(p["id"]):
            migrated += 1
            print(f"  Мігровано: {p.get('name', p['id'])}")
    return migrated


if __name__ == "__main__":
    print("Міграція канонічних URL...")
    n = run_migration()
    print(f"Готово. Мігровано проектів: {n}")
