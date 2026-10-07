#!/usr/bin/env python3
"""
Stockage SQLite pour l'app Timer : projets + temps passé par jour.

Un seul timer peut tourner à la fois (table `running_state`, une seule ligne).
Le temps est stocké en secondes par (projet, jour) dans `time_entries`.
"""

import sqlite3
import time
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "timer.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS time_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id),
            day TEXT NOT NULL,
            seconds INTEGER NOT NULL DEFAULT 0,
            UNIQUE(project_id, day)
        );
        CREATE TABLE IF NOT EXISTS running_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            project_id INTEGER REFERENCES projects(id),
            started_at REAL
        );
        """
    )
    conn.commit()
    conn.close()


def get_or_create_project(conn, name):
    row = conn.execute("SELECT id FROM projects WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO projects (name) VALUES (?)", (name,))
    return cur.lastrowid


def add_entry_seconds(conn, project_id, day, seconds):
    if seconds <= 0:
        return
    conn.execute(
        """
        INSERT INTO time_entries (project_id, day, seconds) VALUES (?, ?, ?)
        ON CONFLICT(project_id, day) DO UPDATE SET seconds = seconds + excluded.seconds
        """,
        (project_id, day, int(round(seconds))),
    )


def seed_entry(name, day, seconds):
    """Ajoute une entrée d'historique si elle n'existe pas déjà (idempotent, pour les données de départ)."""
    conn = get_connection()
    project_id = get_or_create_project(conn, name)
    existing = conn.execute(
        "SELECT 1 FROM time_entries WHERE project_id = ? AND day = ?", (project_id, day)
    ).fetchone()
    if existing is None:
        conn.execute("INSERT INTO time_entries (project_id, day, seconds) VALUES (?, ?, ?)", (project_id, day, seconds))
    conn.commit()
    conn.close()


def _fmt_hm(hours):
    total = round(hours * 60)
    return f"{total // 60}h{total % 60:02d}"


def import_entries(entries, replace=True):
    """
    Écrit des entrées {"name", "date" (AAAA-MM-JJ), "hours"} dans le Timer.

    replace=True remplace le temps déjà enregistré pour (projet, jour), ce qui rend l'import
    rejouable ; replace=False s'y ajoute. Renvoie {"imported", "errors", "ignored"}, comme l'export Odoo.
    """
    report = {"imported": [], "errors": [], "ignored": []}
    conn = get_connection()
    try:
        for entry in entries:
            name = entry["name"].strip()
            row = {"name": name, "date": entry["date"], "hours": entry["hours"]}
            try:
                date.fromisoformat(entry["date"])
            except ValueError:
                report["errors"].append({**row, "reason": "Date invalide"})
                continue
            seconds = int(round(entry["hours"] * 3600))
            if not name:
                report["ignored"].append({**row, "reason": "Nom de projet vide"})
                continue
            if seconds <= 0:
                report["ignored"].append({**row, "reason": "Durée nulle"})
                continue

            project_id = get_or_create_project(conn, name)
            previous = conn.execute(
                "SELECT seconds FROM time_entries WHERE project_id = ? AND day = ?", (project_id, entry["date"])
            ).fetchone()
            if replace:
                conn.execute(
                    """
                    INSERT INTO time_entries (project_id, day, seconds) VALUES (?, ?, ?)
                    ON CONFLICT(project_id, day) DO UPDATE SET seconds = excluded.seconds
                    """,
                    (project_id, entry["date"], seconds),
                )
            else:
                add_entry_seconds(conn, project_id, entry["date"], seconds)

            if previous is None:
                note = "nouvelle entrée"
            else:
                verb = "remplace" if replace else "s'ajoute à"
                note = f"{verb} {_fmt_hm(previous['seconds'] / 3600)}"
            report["imported"].append({**row, "note": note})
        conn.commit()
    finally:
        conn.close()
    return report


def _get_running(conn):
    return conn.execute("SELECT project_id, started_at FROM running_state WHERE id = 1").fetchone()


def _stop_running(conn):
    """Encaisse le temps écoulé du timer en cours (s'il y en a un) et vide running_state."""
    running = _get_running(conn)
    if not running or running["project_id"] is None:
        return
    elapsed = time.time() - running["started_at"]
    if elapsed > 0:
        add_entry_seconds(conn, running["project_id"], date.today().isoformat(), elapsed)
    conn.execute("DELETE FROM running_state WHERE id = 1")


def build_state(conn):
    projects = conn.execute("SELECT id, name FROM projects ORDER BY id").fetchall()
    entries = conn.execute("SELECT project_id, day, seconds FROM time_entries ORDER BY day ASC").fetchall()
    running = _get_running(conn)

    history_by_project = {}
    for e in entries:
        history_by_project.setdefault(e["project_id"], []).append({"date": e["day"], "minutes": e["seconds"] / 60})

    project_list = [
        {"id": p["id"], "name": p["name"], "history": history_by_project.get(p["id"], [])}
        for p in projects
    ]

    running_data = None
    if running and running["project_id"] is not None:
        proj = next((p for p in project_list if p["id"] == running["project_id"]), None)
        running_data = {
            "projectId": running["project_id"],
            "projectName": proj["name"] if proj else None,
            "startedAt": running["started_at"],
        }

    return {"projects": project_list, "running": running_data}


def get_state():
    conn = get_connection()
    state = build_state(conn)
    conn.close()
    return state


def start_project(name):
    name = (name or "").strip()
    if not name:
        raise ValueError("Nom de projet vide")

    conn = get_connection()
    _stop_running(conn)  # un seul timer actif à la fois

    project_id = get_or_create_project(conn, name)
    conn.execute(
        """
        INSERT INTO running_state (id, project_id, started_at) VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET project_id = excluded.project_id, started_at = excluded.started_at
        """,
        (project_id, time.time()),
    )
    conn.commit()
    state = build_state(conn)
    conn.close()
    return state


def stop_project():
    conn = get_connection()
    _stop_running(conn)
    conn.commit()
    state = build_state(conn)
    conn.close()
    return state
