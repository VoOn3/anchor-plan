import sqlite3
import json
import os
from datetime import datetime

if os.environ.get("VERCEL"):
    DB_PATH = "/tmp/anchor_plan.db"
else:
    DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "anchor_plan.db")


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
    for col, default in [("selected_urls", "'[]'"), ("collaborator_sites", "'[]'")]:
        try:
            conn.execute(f"ALTER TABLE projects ADD COLUMN {col} TEXT DEFAULT {default}")
            conn.commit()
        except sqlite3.OperationalError:
            pass
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
        if key in ("settings", "analysis", "plan", "selected_urls", "collaborator_sites"):
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
