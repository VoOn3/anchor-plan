from flask import Flask, request, jsonify, send_file, send_from_directory, abort
from flask_cors import CORS
import os
import uuid
from services.parser import (
    parse_positions_file, parse_ahrefs_file, parse_collaborator_file,
    get_collaborator_columns, parse_anchor_plan_file,
)
from services.analyzer import analyze_pages, classify_anchor, calculate_recommended_links, calculate_priority
from services.planner import generate_anchor_plan, calculate_current_distribution
from services.exporter import export_to_xlsx
from services.site_filter import filter_sites
from services.site_matcher import match_sites_to_plan
from services.database import (
    init_db, list_projects_with_stats, get_project,
    create_project, update_project, delete_project,
    update_project_with_history, add_settings_to_history,
    list_settings_presets, create_settings_preset, delete_settings_preset,
)

app = Flask(__name__)
CORS(app)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
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

    migrated = False
    for page in project.get("analysis", []):
        if "recommended_links" not in page:
            page["recommended_links"] = calculate_recommended_links(page)
            migrated = True
    if migrated:
        update_project(project_id, analysis=project["analysis"])

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


# ========== Upload Validation (background) ==========

@app.route("/api/projects/<project_id>/validate-upload", methods=["POST"])
def validate_upload(project_id):
    """Валідація файлів без повного аналізу. Повертає ok/error для кожного файлу."""
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404

    result = {"positions": {"ok": False}, "ahrefs": {"ok": False}}

    session_dir = os.path.join(UPLOAD_DIR, project_id)
    os.makedirs(session_dir, exist_ok=True)

    positions_file = request.files.get("positions")
    if positions_file and positions_file.filename:
        pos_path = os.path.join(session_dir, "validate_positions" + os.path.splitext(positions_file.filename)[1])
        try:
            positions_file.save(pos_path)
            data = parse_positions_file(pos_path)
            result["positions"] = {"ok": True, "rows": len(data)}
        except ValueError as e:
            result["positions"] = {"ok": False, "error": str(e)}
        except Exception as e:
            result["positions"] = {"ok": False, "error": f"Помилка читання файлу: {str(e)}"}

    ahrefs_file = request.files.get("ahrefs")
    if ahrefs_file and ahrefs_file.filename:
        ahrefs_path = os.path.join(session_dir, "validate_ahrefs" + os.path.splitext(ahrefs_file.filename)[1])
        try:
            ahrefs_file.save(ahrefs_path)
            data = parse_ahrefs_file(ahrefs_path)
            result["ahrefs"] = {"ok": True, "rows": len(data)}
        except ValueError as e:
            result["ahrefs"] = {"ok": False, "error": str(e)}
        except Exception as e:
            result["ahrefs"] = {"ok": False, "error": f"Помилка читання файлу: {str(e)}"}

    return jsonify(result)


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

    analysis = analyze_pages(positions_data, ahrefs_data, settings.get("priority_ranges"))

    auto_selected = [
        p["url"] for p in analysis
        if p.get("recommendation") in ("priority", "recommended")
    ]

    custom_links = project.get("custom_links", {})
    plan = generate_anchor_plan(analysis, settings, selected_urls=auto_selected, custom_links=custom_links)

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
        "custom_links": custom_links,
    })


# ========== Settings (save only) ==========

def _validate_settings(settings):
    """Валідація налаштувань. Повертає (ok: bool, error: str|None)."""
    dist = settings.get("anchor_distribution", {})
    for key, val in dist.items():
        mn = val.get("min", 0)
        mx = val.get("max", 0)
        if mn < 0 or mx < 0 or mn > 100 or mx > 100:
            return False, f"Розподіл анкорів '{key}': значення мають бути 0–100"
        if mn > mx:
            return False, f"Розподіл анкорів '{key}': min не може бути більше max"
    prio = settings.get("priority_ranges", {})
    ranges = [(v.get("from", 1), v.get("to", 1), k) for k, v in prio.items()]
    for i, (a1, a2, n1) in enumerate(ranges):
        for j, (b1, b2, n2) in enumerate(ranges):
            if i >= j:
                continue
            if not (a2 < b1 or b2 < a1):
                return False, f"Діапазони пріоритетів '{n1}' та '{n2}' перекриваються"
    return True, None


@app.route("/api/projects/<project_id>/settings", methods=["PATCH"])
def save_settings(project_id):
    """Зберегти налаштування без перерахунку плану."""
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404

    data = request.json or {}
    new_settings = data.get("settings")
    if not new_settings:
        return jsonify({"error": "Немає налаштувань"}), 400

    settings = dict(project.get("settings") or get_default_settings())
    settings.update(new_settings)

    ok, err = _validate_settings(settings)
    if not ok:
        return jsonify({"error": err}), 400

    update_project_with_history(project_id, settings)
    project = get_project(project_id)
    return jsonify({"settings": settings, "settings_history": project.get("settings_history", [])})


@app.route("/api/projects/<project_id>/restore-settings", methods=["POST"])
def restore_settings(project_id):
    """Відновити налаштування з історії."""
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404

    data = request.json or {}
    index = data.get("index", 0)
    history = project.get("settings_history", [])

    if index < 0 or index >= len(history):
        return jsonify({"error": "Невірний індекс історії"}), 400

    restored = history[index]["settings"]
    update_project(project_id, settings=restored)
    project = get_project(project_id)
    return jsonify({"settings": restored, "settings_history": project.get("settings_history", [])})


# ========== Settings Presets ==========

@app.route("/api/settings-presets", methods=["GET"])
def api_list_presets():
    presets = list_settings_presets()
    return jsonify({"presets": presets})


@app.route("/api/settings-presets", methods=["POST"])
def api_create_preset():
    data = request.json or {}
    name = (data.get("name") or "").strip()
    settings = data.get("settings")
    if not name or not settings:
        return jsonify({"error": "Потрібні name та settings"}), 400
    preset_id = str(uuid.uuid4())
    create_settings_preset(preset_id, name, settings)
    return jsonify({"id": preset_id, "name": name, "settings": settings})


@app.route("/api/settings-presets/<preset_id>", methods=["DELETE"])
def api_delete_preset(preset_id):
    delete_settings_preset(preset_id)
    return jsonify({"ok": True})


# ========== Recalculate ==========

@app.route("/api/projects/<project_id>/recalculate", methods=["POST"])
def recalculate(project_id):
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404

    data = request.json or {}
    new_settings = data.get("settings")
    selected_urls = data.get("selected_urls")
    custom_links = data.get("custom_links")

    settings = project["settings"]
    if new_settings:
        settings.update(new_settings)

    ok, err = _validate_settings(settings)
    if not ok:
        return jsonify({"error": err}), 400

    if selected_urls is None:
        selected_urls = project.get("selected_urls", [])

    if custom_links is None:
        custom_links = project.get("custom_links", {})

    analysis = project["analysis"]
    prio_ranges = settings.get("priority_ranges")
    if prio_ranges and analysis:
        for page in analysis:
            kw_analysis = page.get("keywords", [])
            if kw_analysis:
                prio = calculate_priority(kw_analysis, prio_ranges)
                page["priority"] = prio["level"]
                page["priority_score"] = prio["score"]

    plan = generate_anchor_plan(analysis, settings, selected_urls=selected_urls, custom_links=custom_links)

    add_settings_to_history(project_id, None)
    update_project(project_id, settings=settings, analysis=analysis, plan=plan, selected_urls=selected_urls, custom_links=custom_links)

    project = get_project(project_id)
    return jsonify({
        "plan": plan,
        "analysis": analysis,
        "settings": settings,
        "selected_urls": selected_urls,
        "custom_links": custom_links,
        "settings_history": project.get("settings_history", []),
    })


# ========== Select URLs & Generate Plan ==========

@app.route("/api/projects/<project_id>/select-urls", methods=["POST"])
def select_urls(project_id):
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404

    data = request.json or {}
    selected_urls = data.get("selected_urls", [])
    custom_links = data.get("custom_links")

    if custom_links is None:
        custom_links = project.get("custom_links", {})

    settings = project["settings"]
    plan = generate_anchor_plan(project["analysis"], settings, selected_urls=selected_urls, custom_links=custom_links)

    update_project(project_id, selected_urls=selected_urls, plan=plan, custom_links=custom_links)

    return jsonify({
        "plan": plan,
        "selected_urls": selected_urls,
        "custom_links": custom_links,
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


@app.route("/api/projects/<project_id>/collaborator-unique-values", methods=["GET"])
def collaborator_unique_values(project_id):
    """Повертає унікальні значення колонки для предиктивних фільтрів."""
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404

    column = request.args.get("column", "").strip()
    if not column:
        return jsonify({"error": "Параметр column обов'язковий"}), 400

    sites = project.get("collaborator_sites", [])
    if not sites:
        return jsonify({"values": [], "min": None, "max": None})

    seen = set()
    values = []
    min_val = None
    max_val = None

    for site in sites:
        v = site.get(column)
        if v is None or (isinstance(v, float) and (str(v) == "nan" or str(v) == "inf")):
            continue
        if isinstance(v, str) and not v.strip():
            continue
        parts = []
        if isinstance(v, (int, float)):
            parts = [v]
            try:
                f = float(v)
                if min_val is None or f < min_val:
                    min_val = f
                if max_val is None or f > max_val:
                    max_val = f
            except (TypeError, ValueError):
                pass
        else:
            parts = [p.strip() for p in str(v).split(",") if p.strip()]
        for p in parts:
            key = str(p).strip().lower()
            if key and key not in seen:
                seen.add(key)
                values.append(p if isinstance(p, (int, float)) else p)

    def sort_key(x):
        if isinstance(x, (int, float)):
            return (0, float(x))
        return (1, str(x).lower())

    values.sort(key=sort_key)
    out = [v if isinstance(v, (int, float)) else str(v) for v in values[:200]]
    return jsonify({"values": out, "min": min_val, "max": max_val})


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


@app.route("/api/projects/<project_id>/available-sites", methods=["POST"])
def available_sites(project_id):
    """Return scored & filtered sites for replacement modal."""
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404

    from services.site_matcher import _score_sites
    from services.site_filter import filter_sites as do_filter

    data = request.json or {}
    exclude_domains = set(data.get("exclude_domains", []))

    sites = project.get("collaborator_sites", [])
    settings = project["settings"]
    filters = settings.get("site_filters", [])
    domain = project.get("domain", "")

    filtered = do_filter(sites, filters) if filters else list(sites)
    scored = _score_sites(filtered, domain)
    scored.sort(key=lambda x: x["_quality_score"], reverse=True)

    result = []
    for s in scored:
        dk = s.get("_domain_key", "")
        if dk in exclude_domains:
            continue
        price = s.get("Ціна розміщення стаття, UAH")
        result.append({
            "domain": s.get("Домен", ""),
            "domain_key": dk,
            "url": s.get("URL Коллаборатора", ""),
            "dr": s.get("DR"),
            "traffic": s.get("Трафік на місяць"),
            "organic": s.get("Органічний трафік"),
            "price": price if isinstance(price, (int, float)) else 0,
            "quality": s["_quality_score"],
            "theme": s.get("Тематика", ""),
            "age": s.get("Вік сайту, років"),
        })

    return jsonify({"sites": result, "total": len(result)})


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

@app.route("/api/projects/<project_id>/plan/available-anchors", methods=["GET"])
def get_available_anchors(project_id):
    """Повертає анкори для URL: з реєстру позицій та з вигрузки беклінків (закуплені)."""
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404

    from services.parser import normalize_url
    url = request.args.get("url", "")
    url_norm = normalize_url(url)
    if not url_norm:
        return jsonify({"anchors": []})

    anchors = set()
    for page in project.get("analysis", []):
        if normalize_url(page.get("url", "")) != url_norm:
            continue
        for kw in page.get("keywords", []):
            k = (kw.get("keyword") or "").strip()
            if k:
                anchors.add(k)
        for a in page.get("existing_anchors", []):
            if a and isinstance(a, str):
                anchors.add(a.strip())
        for a in page.get("raw_anchors", []):
            anc = a.get("anchor") if isinstance(a, dict) else None
            if anc:
                anchors.add(str(anc).strip())

    return jsonify({"anchors": sorted(anchors)})


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
        plan[row_index]["target_keyword"] = new_anchor
        plan[row_index]["is_manual"] = True
        positions_set = _build_positions_keywords_set(project_id, project)
        if positions_set:
            from services.parser import normalize_url
            url = plan[row_index].get("url", "")
            url_norm = normalize_url(url)
            key = (url_norm, new_anchor.strip().lower())
            plan[row_index]["anchor_in_positions"] = key in positions_set

            if plan[row_index]["anchor_in_positions"]:
                page = next(
                    (p for p in project.get("analysis", [])
                    if normalize_url(p.get("url", "")) == url_norm
                ), None)
                if page:
                    anchor_lower = new_anchor.strip().lower()
                    matching_kw = next(
                        (kw for kw in page.get("keywords", [])
                        if (kw.get("keyword") or "").strip().lower() == anchor_lower
                    ), None)
                    if matching_kw:
                        plan[row_index]["current_position"] = matching_kw.get("current_position")
                        plan[row_index]["dynamics"] = matching_kw.get("dynamics_label", "n/a")
                    else:
                        plan[row_index]["current_position"] = None
                        plan[row_index]["dynamics"] = "n/a"
                else:
                    plan[row_index]["current_position"] = None
                    plan[row_index]["dynamics"] = "n/a"
            else:
                plan[row_index]["current_position"] = None
                plan[row_index]["dynamics"] = "Позицій не знайдено"
        else:
            plan[row_index]["anchor_in_positions"] = False
            plan[row_index]["current_position"] = None
            plan[row_index]["dynamics"] = "Позицій не знайдено"

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


def _build_positions_keywords_set(project_id: str, project: dict) -> set[tuple[str, str]]:
    """Побудова множини (url, keyword) з реєстру позицій для валідації анкорів."""
    from services.parser import normalize_url

    result = set()
    analysis = project.get("analysis", [])

    if analysis:
        for page in analysis:
            url = normalize_url(page.get("url", ""))
            for kw in page.get("keywords", []):
                k = (kw.get("keyword") or "").strip()
                if k:
                    result.add((url, k.lower()))
        return result

    session_dir = os.path.join(UPLOAD_DIR, project_id)
    for ext in [".csv", ".xlsx", ".xls"]:
        pos_path = os.path.join(session_dir, "positions" + ext)
        if os.path.isfile(pos_path):
            try:
                data = parse_positions_file(pos_path)
                for item in data:
                    url = item.get("url", "")
                    kw = (item.get("keyword") or "").strip()
                    if url and kw:
                        result.add((url, kw.lower()))
                return result
            except Exception:
                pass
    return result


@app.route("/api/projects/<project_id>/plan/upload", methods=["POST"])
def upload_anchor_plan(project_id):
    """Завантаження власного анкор-плану (CSV/XLSX). Обов'язкові колонки: URL, Анкор.
    Перевіряє наявність анкорів у реєстрі позицій."""
    project = get_project(project_id)
    if not project:
        return jsonify({"error": "Проект не знайдено"}), 404

    anchor_plan_file = request.files.get("anchor_plan")
    if not anchor_plan_file or not anchor_plan_file.filename:
        return jsonify({"error": "Потрібно завантажити файл анкор-плану"}), 400

    session_dir = os.path.join(UPLOAD_DIR, project_id)
    os.makedirs(session_dir, exist_ok=True)
    ext = os.path.splitext(anchor_plan_file.filename)[1]
    plan_path = os.path.join(session_dir, "custom_anchor_plan" + ext)

    try:
        anchor_plan_file.save(plan_path)
        rows = parse_anchor_plan_file(plan_path)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Помилка читання файлу: {str(e)}"}), 400

    positions_set = _build_positions_keywords_set(project_id, project)
    mode = request.form.get("mode", "replace")

    from services.parser import normalize_url
    from services.planner import PURCHASE_ORDER

    new_plan_rows = []
    for row in rows:
        url = row["url"]
        anchor = row["anchor"]
        anchor_lower = anchor.strip().lower()
        key = (url, anchor_lower)
        anchor_in_positions = key in positions_set if positions_set else False

        page = next(
            (p for p in project.get("analysis", [])
            if normalize_url(p.get("url", "")) == url
        ), None)
        recommendation = page.get("recommendation", "not_recommended") if page else "not_recommended"
        purchase_order = PURCHASE_ORDER.get(recommendation, 6)

        current_position = None
        dynamics = "Позицій не знайдено" if not anchor_in_positions else "n/a"
        if anchor_in_positions and page:
            matching_kw = next(
                (kw for kw in page.get("keywords", [])
                if (kw.get("keyword") or "").strip().lower() == anchor_lower
            ),
            None,
            )
            if matching_kw:
                current_position = matching_kw.get("current_position")
                dynamics = matching_kw.get("dynamics_label", "n/a")

        new_plan_rows.append({
            "url": url,
            "priority": page["priority"] if page else "medium",
            "priority_score": page["priority_score"] if page else 0,
            "recommendation": recommendation,
            "purchase_order": purchase_order,
            "recommended_anchor": anchor,
            "anchor_type": "partial_match",
            "target_keyword": anchor,
            "current_position": current_position,
            "dynamics": dynamics,
            "rationale": "Завантажено з файлу",
            "is_manual": True,
            "anchor_in_positions": anchor_in_positions,
        })

    if mode == "add":
        plan = list(project.get("plan", [])) + new_plan_rows
    else:
        plan = new_plan_rows

    plan.sort(key=lambda x: (x["purchase_order"], -x["priority_score"]))
    update_project(project_id, plan=plan)

    return jsonify({"plan": plan})


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

    positions_set = _build_positions_keywords_set(project_id, project)
    from services.parser import normalize_url
    key = (normalize_url(url), anchor.strip().lower())
    anchor_in_positions = key in positions_set if positions_set else False

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
        "anchor_in_positions": anchor_in_positions,
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
        "currency": "UAH",
        "anchor_distribution": {
            "exact_match": {"min": 10, "max": 15},
            "partial_match": {"min": 20, "max": 25},
            "branded": {"min": 20, "max": 30},
            "generic": {"min": 15, "max": 20},
            "url": {"min": 10, "max": 15},
        },
        "priority_ranges": {
            "high": {"from": 4, "to": 20, "base_score": 80},
            "medium": {"from": 21, "to": 50, "base_score": 40},
            "low_top": {"from": 1, "to": 3, "base_score": 20},
            "low_bottom": {"from": 51, "to": 1000, "base_score": 5},
        },
        "links_per_page": 3,
        "site_filters": [],
    }


# ========== Frontend (static) — має бути в кінці, після всіх API-маршрутів ==========

@app.route("/")
def serve_index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:path>")
def serve_frontend(path):
    if path.startswith("api/"):
        abort(404)
    full = os.path.join(FRONTEND_DIR, path)
    if os.path.isfile(full):
        return send_from_directory(FRONTEND_DIR, path)
    abort(404)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
