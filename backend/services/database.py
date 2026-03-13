import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "anchor_plan.db")


def _parse_json_safe(row, key, default):
    try:
        val = row[key]
        return json.loads(val or "[]") if val is not None else default
    except (KeyError, TypeError, ValueError):
        return default


def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            brand_name TEXT DEFAULT '',
            domain TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            settings TEXT DEFAULT '{}',
            analysis TEXT DEFAULT '[]',
            plan TEXT DEFAULT '[]',
            selected_urls TEXT DEFAULT '[]',
            collaborator_sites TEXT DEFAULT '[]'
        );
    """)
    for col, default in [("selected_urls", "'[]'"), ("collaborator_sites", "'[]'"), ("custom_links", "'{}'"), ("settings_history", "'[]'")]:
        try:
            conn.execute(f"ALTER TABLE projects ADD COLUMN {col} TEXT DEFAULT {default}")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS settings_presets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            settings TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)
    # Seed default presets if empty
    count = conn.execute("SELECT COUNT(*) FROM settings_presets").fetchone()[0]
    if count == 0:
        now = datetime.utcnow().isoformat()
        defaults = [
            ("preset-conservative", "Консервативний", json.dumps({
                "anchor_distribution": {"exact_match": {"min": 15, "max": 20}, "partial_match": {"min": 25, "max": 30},
                    "branded": {"min": 25, "max": 35}, "generic": {"min": 10, "max": 15}, "url": {"min": 5, "max": 10}},
                "priority_ranges": {"high": {"from": 4, "to": 20}, "medium": {"from": 21, "to": 50},
                    "low_top": {"from": 1, "to": 3}, "low_bottom": {"from": 51, "to": 1000}},
                "links_per_page": 2,
            }, ensure_ascii=False)),
            ("preset-aggressive", "Агресивний", json.dumps({
                "anchor_distribution": {"exact_match": {"min": 5, "max": 10}, "partial_match": {"min": 15, "max": 25},
                    "branded": {"min": 15, "max": 25}, "generic": {"min": 20, "max": 30}, "url": {"min": 15, "max": 25}},
                "priority_ranges": {"high": {"from": 4, "to": 30}, "medium": {"from": 31, "to": 80},
                    "low_top": {"from": 1, "to": 3}, "low_bottom": {"from": 81, "to": 1000}},
                "links_per_page": 5,
            }, ensure_ascii=False)),
            ("preset-brand-focus", "Бренд-фокус", json.dumps({
                "anchor_distribution": {"exact_match": {"min": 10, "max": 15}, "partial_match": {"min": 15, "max": 20},
                    "branded": {"min": 35, "max": 45}, "generic": {"min": 10, "max": 15}, "url": {"min": 5, "max": 10}},
                "priority_ranges": {"high": {"from": 4, "to": 20}, "medium": {"from": 21, "to": 50},
                    "low_top": {"from": 1, "to": 3}, "low_bottom": {"from": 51, "to": 1000}},
                "links_per_page": 3,
            }, ensure_ascii=False)),
        ]
        for pid, pname, pset in defaults:
            conn.execute("INSERT OR IGNORE INTO settings_presets (id, name, settings, created_at) VALUES (?, ?, ?, ?)",
                         (pid, pname, pset, now))
    conn.commit()
    conn.close()


def list_projects():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, brand_name, domain, created_at, updated_at FROM projects ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()
    results = []
    for r in rows:
        results.append({
            "id": r["id"],
            "name": r["name"],
            "brand_name": r["brand_name"],
            "domain": r["domain"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        })
    return results


def get_project(project_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "brand_name": row["brand_name"],
        "domain": row["domain"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "settings": json.loads(row["settings"]),
        "analysis": json.loads(row["analysis"]),
        "plan": json.loads(row["plan"]),
        "selected_urls": json.loads(row["selected_urls"] or "[]"),
        "collaborator_sites": json.loads(row["collaborator_sites"] or "[]"),
        "custom_links": json.loads(row["custom_links"] or "{}"),
        "settings_history": _parse_json_safe(row, "settings_history", []),
    }


def create_project(project_id, name, brand_name="", domain="", settings=None, analysis=None, plan=None):
    now = datetime.utcnow().isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO projects (id, name, brand_name, domain, created_at, updated_at, settings, analysis, plan) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            project_id,
            name,
            brand_name,
            domain,
            now,
            now,
            json.dumps(settings or {}, ensure_ascii=False),
            json.dumps(analysis or [], ensure_ascii=False),
            json.dumps(plan or [], ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()


def update_project(project_id, **kwargs):
    conn = get_db()
    sets = []
    vals = []
    for key, val in kwargs.items():
        if key in ("settings", "analysis", "plan", "selected_urls", "collaborator_sites", "custom_links"):
            sets.append(f"{key} = ?")
            vals.append(json.dumps(val, ensure_ascii=False))
        elif key in ("name", "brand_name", "domain"):
            sets.append(f"{key} = ?")
            vals.append(val)
    sets.append("updated_at = ?")
    vals.append(datetime.utcnow().isoformat())
    vals.append(project_id)
    conn.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id = ?", vals)
    conn.commit()
    conn.close()


def delete_project(project_id):
    conn = get_db()
    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()


def add_settings_to_history(project_id, settings, max_entries=10):
    """Додає поточні налаштування в історію перед оновленням."""
    conn = get_db()
    row = conn.execute("SELECT settings, settings_history FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        conn.close()
        return
    try:
        history = json.loads(row["settings_history"] or "[]")
    except (TypeError, ValueError):
        history = []
    current = json.loads(row["settings"] or "{}")
    if current:
        history.insert(0, {"settings": current, "created_at": datetime.utcnow().isoformat()})
        history = history[:max_entries]
        conn.execute("UPDATE projects SET settings_history = ? WHERE id = ?", (json.dumps(history, ensure_ascii=False), project_id))
        conn.commit()
    conn.close()


def update_project_with_history(project_id, settings):
    """Оновлює налаштування та додає попередні в історію."""
    add_settings_to_history(project_id, None)
    update_project(project_id, settings=settings)


def list_settings_presets():
    conn = get_db()
    rows = conn.execute("SELECT id, name, settings, created_at FROM settings_presets ORDER BY name").fetchall()
    conn.close()
    return [{"id": r["id"], "name": r["name"], "settings": json.loads(r["settings"]), "created_at": r["created_at"]} for r in rows]


def create_settings_preset(preset_id, name, settings):
    now = datetime.utcnow().isoformat()
    conn = get_db()
    conn.execute(
        "INSERT INTO settings_presets (id, name, settings, created_at) VALUES (?, ?, ?, ?)",
        (preset_id, name, json.dumps(settings, ensure_ascii=False), now),
    )
    conn.commit()
    conn.close()


def delete_settings_preset(preset_id):
    conn = get_db()
    conn.execute("DELETE FROM settings_presets WHERE id = ?", (preset_id,))
    conn.commit()
    conn.close()


def get_project_summary(project_id):
    """Повертає проект без analysis (легкий варіант для списку)."""
    conn = get_db()
    row = conn.execute(
        "SELECT id, name, brand_name, domain, created_at, updated_at, "
        "json_array_length(analysis) as pages_count, "
        "json_array_length(plan) as plan_count "
        "FROM projects WHERE id = ?",
        (project_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "brand_name": row["brand_name"],
        "domain": row["domain"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "pages_count": row["pages_count"],
        "plan_count": row["plan_count"],
    }


def list_projects_with_stats():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, brand_name, domain, created_at, updated_at, "
        "json_array_length(analysis) as pages_count, "
        "json_array_length(plan) as plan_count "
        "FROM projects ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()
    results = []
    for r in rows:
        results.append({
            "id": r["id"],
            "name": r["name"],
            "brand_name": r["brand_name"],
            "domain": r["domain"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "pages_count": r["pages_count"],
            "plan_count": r["plan_count"],
        })
    return results
