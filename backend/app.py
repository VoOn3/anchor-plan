from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import uuid
from services.parser import parse_positions_file, parse_ahrefs_file, parse_collaborator_file, get_collaborator_columns
from services.analyzer import analyze_pages, classify_anchor
from services.planner import generate_anchor_plan, calculate_current_distribution
from services.exporter import export_to_xlsx
from services.site_filter import filter_sites
from services.site_matcher import match_sites_to_plan
from services.database import (
    init_db, list_projects_with_stats, get_project,
    create_project, update_project, delete_project,
)

app = Flask(__name__)
CORS(app)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

init_db()


# ========== Projects CRUD ==========

@app.route("/api/projects", methods=["GET"])
def api_list_projects():
    projects = list_projects_with_stats()
    return jsonify({"projects": projects})


@app.route("/api/projects", methods=["POST"])
def api_create_project():
    """Create empty project (without files)."""
    data = request.json or {}
    name = data.get("name", "").strip()
    brand_name = data.get("brand_name", "").strip()
    domain = data.get("domain", "").strip()

    if not name:
        return jsonify({"error": "Назва проекту обов'язкова"}), 400

    project_id = str(uuid.uuid4())
    settings = get_default_settings()
    settings["brand_name"] = brand_name

    create_project(project_id, name, brand_name, domain, settings)
    return jsonify({"id": project_id, "name": name})


@app.route("/api/projects/<project_id>", methods=["GET"])
def api_get_project(project_id):
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404
    return jsonify(project)


@app.route("/api/projects/<project_id>", methods=["PUT"])
def api_update_project(project_id):
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404

    data = request.json or {}
    kwargs = {}
    if "name" in data:
        kwargs["name"] = data["name"].strip()
    if "brand_name" in data:
        kwargs["brand_name"] = data["brand_name"].strip()
    if "domain" in data:
        kwargs["domain"] = data["domain"].strip()

    if kwargs:
        update_project(project_id, **kwargs)

    return jsonify({"ok": True})


@app.route("/api/projects/<project_id>", methods=["DELETE"])
def api_delete_project(project_id):
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404
    delete_project(project_id)
    return jsonify({"ok": True})


# ========== Upload & Analyze (tied to project) ==========

@app.route("/api/projects/<project_id>/upload", methods=["POST"])
def upload_files(project_id):
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404

    positions_file = request.files.get("positions")
    ahrefs_file = request.files.get("ahrefs")
    brand_name = request.form.get("brand_name", project.get("brand_name", ""))

    if not positions_file or not ahrefs_file:
        return jsonify({"error": "Потрібно завантажити обидва файли"}), 400

    session_dir = os.path.join(UPLOAD_DIR, project_id)
    os.makedirs(session_dir, exist_ok=True)

    pos_path = os.path.join(session_dir, "positions" + os.path.splitext(positions_file.filename)[1])
    ahrefs_path = os.path.join(session_dir, "ahrefs" + os.path.splitext(ahrefs_file.filename)[1])

    positions_file.save(pos_path)
    ahrefs_file.save(ahrefs_path)

    try:
        positions_data = parse_positions_file(pos_path)
        ahrefs_data = parse_ahrefs_file(ahrefs_path)
    except Exception as e:
        return jsonify({"error": f"Помилка парсингу файлів: {str(e)}"}), 400

    settings = project.get("settings") or get_default_settings()
    settings["brand_name"] = brand_name

    analysis = analyze_pages(positions_data, ahrefs_data)

    auto_selected = [
        p["url"] for p in analysis
        if p.get("recommendation") in ("priority", "recommended")
    ]

    plan = generate_anchor_plan(analysis, settings, selected_urls=auto_selected)

    update_project(
        project_id, settings=settings, analysis=analysis,
        plan=plan, brand_name=brand_name, selected_urls=auto_selected,
    )

    return jsonify({
        "project_id": project_id,
        "analysis": analysis,
        "plan": plan,
        "settings": settings,
        "selected_urls": auto_selected,
    })


# ========== Recalculate ==========

@app.route("/api/projects/<project_id>/recalculate", methods=["POST"])
def recalculate(project_id):
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404

    data = request.json or {}
    new_settings = data.get("settings")
    selected_urls = data.get("selected_urls")

    settings = project["settings"]
    if new_settings:
        settings.update(new_settings)

    if selected_urls is None:
        selected_urls = project.get("selected_urls", [])

    plan = generate_anchor_plan(project["analysis"], settings, selected_urls=selected_urls)

    update_project(project_id, settings=settings, plan=plan, selected_urls=selected_urls)

    return jsonify({
        "plan": plan,
        "settings": settings,
        "selected_urls": selected_urls,
    })


# ========== Select URLs & Generate Plan ==========

@app.route("/api/projects/<project_id>/select-urls", methods=["POST"])
def select_urls(project_id):
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404

    data = request.json or {}
    selected_urls = data.get("selected_urls", [])

    settings = project["settings"]
    plan = generate_anchor_plan(project["analysis"], settings, selected_urls=selected_urls)

    update_project(project_id, selected_urls=selected_urls, plan=plan)

    return jsonify({
        "plan": plan,
        "selected_urls": selected_urls,
    })


# ========== Collaborator Upload & Filter ==========

@app.route("/api/projects/<project_id>/upload-collaborator", methods=["POST"])
def upload_collaborator(project_id):
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404

    collab_file = request.files.get("collaborator")
    if not collab_file:
        return jsonify({"error": "Файл не завантажено"}), 400

    session_dir = os.path.join(UPLOAD_DIR, project_id)
    os.makedirs(session_dir, exist_ok=True)
    collab_path = os.path.join(session_dir, "collaborator" + os.path.splitext(collab_file.filename)[1])
    collab_file.save(collab_path)

    try:
        sites = parse_collaborator_file(collab_path)
    except Exception as e:
        return jsonify({"error": f"Помилка парсингу файлу: {str(e)}"}), 400

    columns = get_collaborator_columns(sites)
    update_project(project_id, collaborator_sites=sites)

    return jsonify({
        "count": len(sites),
        "columns": columns,
    })


@app.route("/api/projects/<project_id>/collaborator-columns", methods=["GET"])
def collaborator_columns(project_id):
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404

    sites = project.get("collaborator_sites", [])
    columns = get_collaborator_columns(sites)

    return jsonify({"count": len(sites), "columns": columns})


@app.route("/api/projects/<project_id>/filter-sites", methods=["POST"])
def filter_collaborator_sites(project_id):
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404

    data = request.json or {}
    filters = data.get("filters", [])

    sites = project.get("collaborator_sites", [])
    filtered = filter_sites(sites, filters)

    settings = project["settings"]
    settings["site_filters"] = filters
    update_project(project_id, settings=settings)

    budget = settings.get("monthly_budget", 0)
    price_field = "Ціна розміщення стаття, UAH"
    total_cost = 0
    within_budget = []
    for s in filtered:
        price = s.get(price_field)
        if price and isinstance(price, (int, float)):
            total_cost += price
            if budget <= 0 or total_cost <= budget:
                within_budget.append(s)
        else:
            within_budget.append(s)

    return jsonify({
        "total": len(sites),
        "filtered": len(filtered),
        "sites": filtered[:200],
        "total_cost": round(total_cost, 2),
        "within_budget": len(within_budget) if budget > 0 else len(filtered),
    })


# ========== Match Sites ==========

@app.route("/api/projects/<project_id>/match-sites", methods=["POST"])
def match_sites(project_id):
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404

    plan = project["plan"]
    sites = project.get("collaborator_sites", [])
    settings = project["settings"]
    filters = settings.get("site_filters", [])
    budget = settings.get("monthly_budget", 0)
    domain = project.get("domain", "")

    if not sites:
        return jsonify({"error": "Спочатку завантажте файл Collaborator"}), 400

    if not plan:
        return jsonify({"error": "Анкор-план порожній"}), 400

    result = match_sites_to_plan(plan, sites, filters, budget, domain)
    return jsonify(result)


@app.route("/api/projects/<project_id>/reassign-site", methods=["POST"])
def reassign_site(project_id):
    """Manually reassign a specific site to a plan row."""
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404

    data = request.json or {}
    plan_index = data.get("plan_index")
    site_domain = data.get("site_domain", "").strip()

    sites = project.get("collaborator_sites", [])
    site = next((s for s in sites if str(s.get("Домен", "")).strip() == site_domain), None)

    if site is None:
        return jsonify({"error": "Площадку не знайдено"}), 404

    price = site.get("Ціна розміщення стаття, UAH")

    return jsonify({
        "plan_index": plan_index,
        "assigned_site": site.get("Домен", ""),
        "site_url": site.get("URL Коллаборатора", ""),
        "site_dr": site.get("DR"),
        "site_traffic": site.get("Трафік на місяць"),
        "site_organic": site.get("Органічний трафік"),
        "site_price": price if isinstance(price, (int, float)) else 0,
        "site_theme": site.get("Тематика", ""),
    })


# ========== Export ==========

@app.route("/api/projects/<project_id>/export", methods=["GET"])
def export_plan(project_id):
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404

    session_dir = os.path.join(UPLOAD_DIR, project_id)
    os.makedirs(session_dir, exist_ok=True)
    export_path = os.path.join(session_dir, "anchor_plan.xlsx")
    export_to_xlsx(project["plan"], project["analysis"], export_path)

    return send_file(export_path, as_attachment=True, download_name="anchor_plan.xlsx")


# ========== Plan Edit ==========

@app.route("/api/projects/<project_id>/plan/edit", methods=["POST"])
def edit_plan_row(project_id):
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404

    data = request.json
    row_index = data.get("row_index")
    new_anchor = data.get("anchor")
    new_anchor_type = data.get("anchor_type")

    plan = project["plan"]
    if 0 <= row_index < len(plan):
        plan[row_index]["recommended_anchor"] = new_anchor
        plan[row_index]["anchor_type"] = new_anchor_type
        plan[row_index]["is_manual"] = True

    update_project(project_id, plan=plan)
    return jsonify({"plan": plan})


@app.route("/api/projects/<project_id>/plan/delete", methods=["POST"])
def delete_plan_rows(project_id):
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404

    data = request.json or {}
    indexes = set(data.get("indexes", []))

    if not indexes:
        return jsonify({"error": "Не вказано індекси для видалення"}), 400

    plan = project["plan"]
    new_plan = [item for i, item in enumerate(plan) if i not in indexes]

    update_project(project_id, plan=new_plan)
    return jsonify({"plan": new_plan, "deleted": len(plan) - len(new_plan)})


@app.route("/api/projects/<project_id>/plan/add", methods=["POST"])
def add_plan_row(project_id):
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404

    data = request.json or {}
    url = data.get("url", "").strip()
    anchor = data.get("anchor", "").strip()
    anchor_type = data.get("anchor_type", "partial_match")
    target_keyword = data.get("target_keyword", "").strip()
    rationale = data.get("rationale", "").strip()

    if not url or not anchor:
        return jsonify({"error": "URL та анкор обов'язкові"}), 400

    page = next((p for p in project["analysis"] if p["url"] == url), None)

    best_kw = page.get("best_keyword") if page else None
    recommendation = page.get("recommendation", "not_recommended") if page else "not_recommended"

    from services.planner import PURCHASE_ORDER
    purchase_order = PURCHASE_ORDER.get(recommendation, 6)

    new_row = {
        "url": url,
        "priority": page["priority"] if page else "medium",
        "priority_score": page["priority_score"] if page else 0,
        "recommendation": recommendation,
        "purchase_order": purchase_order,
        "recommended_anchor": anchor,
        "anchor_type": anchor_type,
        "target_keyword": target_keyword,
        "current_position": best_kw["current_position"] if best_kw else None,
        "dynamics": best_kw["dynamics_label"] if best_kw else "n/a",
        "rationale": rationale or "Додано вручну",
        "is_manual": True,
    }

    plan = project["plan"]
    plan.append(new_row)
    plan.sort(key=lambda x: (x.get("purchase_order", 6), -x.get("priority_score", 0)))

    update_project(project_id, plan=plan)
    return jsonify({"plan": plan})


# ========== URL Detail ==========

@app.route("/api/projects/<project_id>/url-detail", methods=["POST"])
def url_detail(project_id):
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404

    data = request.json
    target_url = data.get("url")

    analysis = project["analysis"]
    plan = project["plan"]
    settings = project["settings"]
    brand_name = settings.get("brand_name", "")

    page = next((p for p in analysis if p["url"] == target_url), None)
    if not page:
        return jsonify({"error": "URL не знайдено"}), 404

    keywords = [kw["keyword"] for kw in page.get("keywords", [])]

    classified_anchors = []
    for a in page.get("raw_anchors", []):
        anchor_type = classify_anchor(a["anchor"], keywords, brand_name, target_url)
        classified_anchors.append({
            "anchor": a["anchor"],
            "referring_url": a.get("referring_url", ""),
            "link_type": a.get("link_type", "dofollow"),
            "dr": a.get("dr"),
            "traffic": a.get("traffic"),
            "type": anchor_type,
        })

    grouped = {}
    for a in classified_anchors:
        key = a["anchor"].lower().strip()
        if key not in grouped:
            grouped[key] = {
                "anchor": a["anchor"],
                "count": 0,
                "type": a["type"],
                "dofollow": 0,
                "nofollow": 0,
                "dr_values": [],
                "donors": [],
            }
        grouped[key]["count"] += 1
        if "dofollow" in a["link_type"]:
            grouped[key]["dofollow"] += 1
        else:
            grouped[key]["nofollow"] += 1
        if a["dr"] is not None:
            grouped[key]["dr_values"].append(a["dr"])
        if a["referring_url"]:
            grouped[key]["donors"].append(a["referring_url"])

    anchors_grouped = []
    for g in sorted(grouped.values(), key=lambda x: x["count"], reverse=True):
        avg_dr = round(sum(g["dr_values"]) / len(g["dr_values"]), 1) if g["dr_values"] else None
        anchors_grouped.append({
            "anchor": g["anchor"],
            "count": g["count"],
            "type": g["type"],
            "dofollow": g["dofollow"],
            "nofollow": g["nofollow"],
            "avg_dr": avg_dr,
            "donors": g["donors"],
        })

    current_dist = calculate_current_distribution(
        page.get("existing_anchors", []), keywords, brand_name, target_url
    )
    target_dist = settings.get("anchor_distribution", {})

    distribution_comparison = []
    for atype, target_range in target_dist.items():
        current_pct = current_dist.get(atype, 0)
        if current_pct > target_range["max"]:
            status = "oversaturated"
        elif current_pct < target_range["min"]:
            status = "deficit"
        else:
            status = "normal"
        distribution_comparison.append({
            "type": atype,
            "current_pct": current_pct,
            "target_min": target_range["min"],
            "target_max": target_range["max"],
            "status": status,
        })

    url_plan = [p for p in plan if p["url"] == target_url]

    return jsonify({
        "url": target_url,
        "priority": page["priority"],
        "priority_score": page["priority_score"],
        "total_backlinks": page["total_backlinks"],
        "dofollow_count": page["dofollow_count"],
        "nofollow_count": page.get("nofollow_count", 0),
        "unique_anchors": page["anchor_profile"]["unique_anchors"],
        "unique_donors": page.get("unique_donors", 0),
        "keywords": page["keywords"],
        "anchors_grouped": anchors_grouped,
        "distribution_comparison": distribution_comparison,
        "recommendations": url_plan,
    })


# ========== Helpers ==========

def get_default_settings():
    return {
        "brand_name": "",
        "monthly_budget": 0,
        "planned_links_count": 0,
        "anchor_distribution": {
            "exact_match": {"min": 10, "max": 15},
            "partial_match": {"min": 20, "max": 25},
            "branded": {"min": 20, "max": 30},
            "generic": {"min": 15, "max": 20},
            "url": {"min": 10, "max": 15},
        },
        "priority_ranges": {
            "high": {"from": 4, "to": 20},
            "medium": {"from": 21, "to": 50},
            "low_top": {"from": 1, "to": 3},
            "low_bottom": {"from": 51, "to": 1000},
        },
        "links_per_page": 3,
        "site_filters": [],
    }


if __name__ == "__main__":
    app.run(debug=True, port=5000)
