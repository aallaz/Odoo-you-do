#!/usr/bin/env python3
"""
Stockage SQLite pour l'app Timer : projets + temps passé par jour.

Un seul timer peut tourner à la fois (table `running_state`, une seule ligne).
Le temps est stocké en secondes par (projet, jour) dans `time_entries`.
"""

import math
import sqlite3
import time
from datetime import date, datetime, timedelta

import paths

# A côté de l'exécutable (ou du script) : doit survivre d'un lancement à l'autre, jamais embarqué.
DB_PATH = paths.data_root() / "Timer" / "timer.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


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
            first_start_at REAL,
            UNIQUE(project_id, day)
        );
        CREATE TABLE IF NOT EXISTS running_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            project_id INTEGER REFERENCES projects(id),
            started_at REAL
        );
        CREATE TABLE IF NOT EXISTS session_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id),
            day TEXT NOT NULL,
            start_at REAL NOT NULL,
            end_at REAL
        );
        CREATE TABLE IF NOT EXISTS round_backup (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id),
            day TEXT NOT NULL,
            seconds_before INTEGER NOT NULL,
            seconds_after INTEGER NOT NULL,
            created_at REAL NOT NULL
        );
        """
    )
    # Migrations pour une base déjà existante (créée avant l'ajout de ces colonnes).
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(time_entries)").fetchall()}
    if "first_start_at" not in cols:
        conn.execute("ALTER TABLE time_entries ADD COLUMN first_start_at REAL")
    if "archived" not in cols:
        conn.execute("ALTER TABLE time_entries ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
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


def mark_entries_archived(entries):
    """
    Marque comme archivées les entrées {"name", "date"} déjà exportées vers Odoo — typiquement les
    lignes "imported" du rapport d'export. N'efface rien : juste un drapeau, pour que Report puisse
    les masquer par défaut (case « Afficher les archives ») sans perdre la donnée. Un nom sans projet
    correspondant ou un (projet, jour) sans entrée est silencieusement ignoré.
    """
    conn = get_connection()
    try:
        marked = 0
        for e in entries:
            name = str(e["name"]).strip()
            day = str(e["date"])
            project = conn.execute("SELECT id FROM projects WHERE name = ?", (name,)).fetchone()
            if not project:
                continue
            cur = conn.execute(
                "UPDATE time_entries SET archived = 1 WHERE project_id = ? AND day = ?",
                (project["id"], day),
            )
            marked += cur.rowcount
        conn.commit()
        return marked
    finally:
        conn.close()


def _get_running(conn):
    return conn.execute("SELECT project_id, started_at FROM running_state WHERE id = 1").fetchone()


def _mark_first_start(conn, project_id, day, started_at):
    """Note l'heure réelle de début pour (projet, jour), seulement si on n'en a pas déjà une
    (le premier départ du jour l'emporte ; des reprises suivantes ne l'écrasent pas)."""
    conn.execute(
        "UPDATE time_entries SET first_start_at = ? WHERE project_id = ? AND day = ? AND first_start_at IS NULL",
        (started_at, project_id, day),
    )


def _close_session_log(conn, project_id, start_at, end_at):
    """Clôt la ligne de journal ouverte (end_at NULL) qui correspond à ce (projet, début réel)."""
    conn.execute(
        "UPDATE session_log SET end_at = ? WHERE project_id = ? AND start_at = ? AND end_at IS NULL",
        (end_at, project_id, start_at),
    )


def _stop_running(conn):
    """Encaisse le temps écoulé du timer en cours (s'il y en a un) et vide running_state."""
    running = _get_running(conn)
    if not running or running["project_id"] is None:
        return
    now = time.time()
    elapsed = now - running["started_at"]
    if elapsed > 0:
        day = date.today().isoformat()
        add_entry_seconds(conn, running["project_id"], day, elapsed)
        _mark_first_start(conn, running["project_id"], day, running["started_at"])
    _close_session_log(conn, running["project_id"], running["started_at"], now)
    conn.execute("DELETE FROM running_state WHERE id = 1")


def get_day_log(day=None):
    """Journal in/out des sessions d'une journée (toutes projets confondus), triées par heure de début.
    Une ligne avec endAt=None est une session encore en cours. Ne couvre que les sessions démarrées
    depuis l'ajout de cette fonctionnalité (rien de rétroactif sur les anciennes données)."""
    day = day or date.today().isoformat()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT sl.project_id, p.name AS project_name, sl.start_at, sl.end_at
            FROM session_log sl
            JOIN projects p ON p.id = sl.project_id
            WHERE sl.day = ?
            ORDER BY sl.start_at ASC
            """,
            (day,),
        ).fetchall()
        return [
            {
                "projectId": r["project_id"],
                "projectName": r["project_name"],
                "startAt": r["start_at"],
                "endAt": r["end_at"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def build_state(conn):
    projects = conn.execute("SELECT id, name FROM projects ORDER BY id").fetchall()
    entries = conn.execute(
        "SELECT project_id, day, seconds, first_start_at, archived FROM time_entries ORDER BY day ASC"
    ).fetchall()
    running = _get_running(conn)

    history_by_project = {}
    for e in entries:
        history_by_project.setdefault(e["project_id"], []).append({
            "date": e["day"],
            "minutes": e["seconds"] / 60,
            "startedAt": e["first_start_at"],
            "archived": bool(e["archived"]),
        })

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
    started_at = time.time()
    conn.execute(
        """
        INSERT INTO running_state (id, project_id, started_at) VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET project_id = excluded.project_id, started_at = excluded.started_at
        """,
        (project_id, started_at),
    )
    conn.execute(
        "INSERT INTO session_log (project_id, day, start_at, end_at) VALUES (?, ?, ?, NULL)",
        (project_id, date.today().isoformat(), started_at),
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


def _parse_hhmm(value):
    try:
        h, m = str(value).split(":")
        h, m = int(h), int(m)
    except (ValueError, AttributeError):
        raise ValueError("Heure invalide (attendu HH:MM)")
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError("Heure invalide (attendu HH:MM)")
    return h, m


def rename_project(project_id, new_name):
    """Renomme un projet. Refuse si un autre projet porte déjà ce nom (pas de fusion automatique)."""
    new_name = (new_name or "").strip()
    if not new_name:
        raise ValueError("Nom de projet vide")

    conn = get_connection()
    try:
        clash = conn.execute(
            "SELECT id FROM projects WHERE name = ? AND id != ?", (new_name, project_id)
        ).fetchone()
        if clash:
            raise ValueError("Un projet avec ce nom existe déjà")
        conn.execute("UPDATE projects SET name = ? WHERE id = ?", (new_name, project_id))
        conn.commit()
        return build_state(conn)
    finally:
        conn.close()


ROUND_UNITS_MINUTES = (5, 10, 15, 30, 60)


def _validate_round_args(start_day, end_day, unit_minutes):
    if unit_minutes not in ROUND_UNITS_MINUTES:
        raise ValueError(f"Unité d'arrondi invalide (attendu {ROUND_UNITS_MINUTES})")
    try:
        start_date = date.fromisoformat(start_day)
        end_date = date.fromisoformat(end_day)
    except ValueError:
        raise ValueError("Date invalide (attendu AAAA-MM-JJ)")
    if end_date < start_date:
        raise ValueError("end doit être après start")


def _compute_round_changes(conn, start_day, end_day, unit_minutes, day_caps=None):
    """
    Calcule, sans rien écrire, les changements (projet, jour, avant, après) qu'un arrondi à
    `unit_minutes` provoquerait sur [start_day, end_day].

    `day_caps` : {jour: minutes} optionnel — la référence « heures de la journée » à ne pas dépasser
    (typiquement le pointage Odoo réel, plus fiable que la somme du Timer qui peut sous-compter le
    temps réellement présent). Un jour absent de `day_caps` retombe sur la somme brute du Timer pour
    ce jour (archives incluses).

    Les entrées déjà archivées (exportées vers Odoo) ne sont jamais arrondies ni réduites — elles
    comptent dans le total du jour (`day_totals`) et dans l'occupation de la référence de la journée,
    mais ne peuvent pas absorber l'écart : seules les entrées non archivées sont candidates.

    Chaque entrée non nulle (et non archivée) est arrondie vers le haut au prochain multiple de
    l'unité (jamais à 0, puisqu'arrondir vers le haut une valeur positive donne au moins une unité).
    Si la somme arrondie du jour dépasse la marge disponible, on retire l'excédent par paliers d'une
    unité sur la ou les plus grosses entrées du jour (elles ont le plus de marge), sans jamais faire
    descendre une entrée sous une unité — au besoin, le dépassement n'est alors pas totalement résorbé
    plutôt que de ramener une entrée à 0.
    """
    unit_seconds = unit_minutes * 60
    day_caps = day_caps or {}

    def round_up(seconds):
        return int(math.ceil(seconds / unit_seconds) * unit_seconds)

    rows = conn.execute(
        "SELECT project_id, day, seconds, archived FROM time_entries WHERE day BETWEEN ? AND ? AND seconds > 0",
        (start_day, end_day),
    ).fetchall()

    by_day = {}
    archived_totals = {}  # day -> secondes déjà archivées (fixes, non arrondissables)
    for r in rows:
        if r["archived"]:
            archived_totals[r["day"]] = archived_totals.get(r["day"], 0) + r["seconds"]
        else:
            by_day.setdefault(r["day"], []).append({"project_id": r["project_id"], "seconds": r["seconds"]})

    changes = []  # {"project_id", "day", "seconds_before", "seconds_after"}
    day_totals = {}  # day -> total secondes après arrondi, toutes entrées confondues (changées ou pas)
    for day, items in by_day.items():
        archived_seconds = archived_totals.get(day, 0)
        cap_minutes = day_caps.get(day)
        if cap_minutes is not None:
            full_cap_seconds = int(round(cap_minutes * 60))
        else:
            full_cap_seconds = sum(it["seconds"] for it in items) + archived_seconds
        raw_total = full_cap_seconds - archived_seconds  # marge dispo pour les entrées arrondissables
        for it in items:
            it["rounded"] = round_up(it["seconds"])

        excess = sum(it["rounded"] for it in items) - raw_total
        if excess > 0:
            # Les plus grosses entrées d'abord : elles ont le plus de marge pour absorber l'écart
            # sans jamais être réduites sous une unité (donc jamais à 0).
            candidates = sorted(items, key=lambda it: it["rounded"], reverse=True)
            for it in candidates:
                while excess > 0 and it["rounded"] > unit_seconds:
                    it["rounded"] -= unit_seconds
                    excess -= unit_seconds
                if excess <= 0:
                    break

        day_totals[day] = archived_seconds + sum(it["rounded"] for it in items)
        for it in items:
            if it["rounded"] != it["seconds"]:
                changes.append({
                    "project_id": it["project_id"],
                    "day": day,
                    "seconds_before": it["seconds"],
                    "seconds_after": it["rounded"],
                })

    changes.sort(key=lambda c: (c["day"], c["project_id"]))
    return changes, day_totals


def preview_round_entries(start_day, end_day, unit_minutes, day_caps=None):
    """
    Aperçu des changements qu'un arrondi provoquerait, sans rien écrire en base.

    `day_caps` : voir `_compute_round_changes` (pointage Odoo réel par jour, si disponible).

    `dayTotals` donne le total après arrondi de chaque jour touché, toutes entrées confondues (y
    compris celles qui ne changent pas et n'apparaissent donc pas dans `changes`) — nécessaire pour
    afficher un total de journée correct.
    """
    _validate_round_args(start_day, end_day, unit_minutes)
    conn = get_connection()
    try:
        changes, day_totals = _compute_round_changes(conn, start_day, end_day, unit_minutes, day_caps)
        names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM projects").fetchall()}
        return {
            "changes": [
                {
                    "projectId": c["project_id"],
                    "projectName": names.get(c["project_id"], "?"),
                    "day": c["day"],
                    "beforeMinutes": c["seconds_before"] / 60,
                    "afterMinutes": c["seconds_after"] / 60,
                }
                for c in changes
            ],
            "dayTotals": {day: seconds / 60 for day, seconds in day_totals.items()},
        }
    finally:
        conn.close()


def apply_round_changes(changes):
    """
    Applique une liste de changements choisis par l'utilisateur (projet, jour, minutes finales) —
    typiquement l'aperçu de `preview_round_entries`, éventuellement corrigé à la main. Contrairement
    à l'arrondi automatique, une valeur à 0 est acceptée ici puisqu'elle a été choisie explicitement.

    `changes` : liste de {"project_id": int, "day": "AAAA-MM-JJ", "minutes": float}.
    La valeur d'avant modification de chaque entrée touchée est conservée dans `round_backup` avant
    d'écraser `time_entries`. Les entrées dont la valeur finale est inchangée sont ignorées.
    """
    conn = get_connection()
    try:
        current = {
            (r["project_id"], r["day"]): r["seconds"]
            for r in conn.execute("SELECT project_id, day, seconds FROM time_entries").fetchall()
        }

        now = time.time()
        applied = 0
        for c in changes:
            project_id = int(c["project_id"])
            day = str(c["day"])
            seconds_after = max(0, int(round(float(c["minutes"]) * 60)))
            seconds_before = current.get((project_id, day), 0)
            if seconds_after == seconds_before:
                continue

            conn.execute(
                """
                INSERT INTO round_backup (project_id, day, seconds_before, seconds_after, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (project_id, day, seconds_before, seconds_after, now),
            )
            if seconds_after > 0:
                conn.execute(
                    """
                    INSERT INTO time_entries (project_id, day, seconds) VALUES (?, ?, ?)
                    ON CONFLICT(project_id, day) DO UPDATE SET seconds = excluded.seconds
                    """,
                    (project_id, day, seconds_after),
                )
            else:
                conn.execute("DELETE FROM time_entries WHERE project_id = ? AND day = ?", (project_id, day))
            applied += 1

        conn.commit()
        state = build_state(conn)
        state["rounded"] = applied
        return state
    finally:
        conn.close()


def set_running_start(start_hhmm):
    """Change l'heure de début du chronomètre en cours (aujourd'hui), SANS l'arrêter — pour redéfinir
    quand une reprise de travail a réellement commencé si le clic sur Démarrer est arrivé en retard."""
    h, m = _parse_hhmm(start_hhmm)

    conn = get_connection()
    try:
        running = _get_running(conn)
        if not running or running["project_id"] is None:
            raise ValueError("Aucun chronométrage en cours")

        old_start = datetime.fromtimestamp(running["started_at"])
        new_start = old_start.replace(hour=h, minute=m, second=0, microsecond=0)
        if new_start > datetime.now():
            raise ValueError("L'heure de début ne peut pas être dans le futur")

        conn.execute(
            "UPDATE session_log SET start_at = ? WHERE project_id = ? AND start_at = ? AND end_at IS NULL",
            (new_start.timestamp(), running["project_id"], running["started_at"]),
        )
        conn.execute("UPDATE running_state SET started_at = ? WHERE id = 1", (new_start.timestamp(),))
        conn.commit()
        return build_state(conn)
    finally:
        conn.close()


def stop_running_at(end_hhmm):
    """Comme stop_project(), mais avec une heure de fin choisie (HH:MM, aujourd'hui) plutôt que
    "maintenant" — pour corriger un chronomètre qu'on a oublié d'arrêter au bon moment."""
    h, m = _parse_hhmm(end_hhmm)

    conn = get_connection()
    try:
        running = _get_running(conn)
        if not running or running["project_id"] is None:
            raise ValueError("Aucun chronométrage en cours")

        start_dt = datetime.fromtimestamp(running["started_at"])
        end_dt = start_dt.replace(hour=h, minute=m, second=0, microsecond=0)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)  # passage de minuit
        elapsed = (end_dt - start_dt).total_seconds()

        day = start_dt.date().isoformat()
        add_entry_seconds(conn, running["project_id"], day, elapsed)
        _mark_first_start(conn, running["project_id"], day, running["started_at"])
        _close_session_log(conn, running["project_id"], running["started_at"], end_dt.timestamp())
        conn.execute("DELETE FROM running_state WHERE id = 1")
        conn.commit()
        return build_state(conn)
    finally:
        conn.close()


def set_entry_minutes(project_id, day, minutes):
    """Fixe directement la durée d'un (projet, jour) en minutes (remplace la valeur existante), sans
    passer par une plage début/fin — pour le cas où l'heure de début n'est pas connue. Si ce projet est
    celui actuellement en cours, arrête aussi le chronométrage (puisqu'on vient de lui donner un total
    final pour ce jour)."""
    seconds = max(0, int(round(minutes * 60)))

    conn = get_connection()
    try:
        project = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            raise ValueError("Projet introuvable")

        running = _get_running(conn)
        if running and running["project_id"] == project_id:
            conn.execute("DELETE FROM running_state WHERE id = 1")

        if seconds <= 0:
            conn.execute("DELETE FROM time_entries WHERE project_id = ? AND day = ?", (project_id, day))
        else:
            # first_start_at repassé à NULL : la durée vient d'être fixée à la main sans référence
            # d'heure, l'ancienne valeur (si il y en avait une) ne serait plus fiable.
            conn.execute(
                """
                INSERT INTO time_entries (project_id, day, seconds, first_start_at) VALUES (?, ?, ?, NULL)
                ON CONFLICT(project_id, day) DO UPDATE SET seconds = excluded.seconds, first_start_at = NULL
                """,
                (project_id, day, seconds),
            )
        conn.commit()
        return build_state(conn)
    finally:
        conn.close()


def delete_entry(project_id, day):
    """Supprime définitivement l'entrée (durée, heure de début) d'un (projet, jour), ainsi que les
    sessions du journal (in/out) de ce jour pour ce projet. Refuse si ce projet est le chrono en
    cours ET que le jour est aujourd'hui : il faut d'abord l'arrêter (voir /api/timer/stop ou
    /api/timer/stop-at)."""
    conn = get_connection()
    try:
        running = _get_running(conn)
        if running and running["project_id"] == project_id and day == date.today().isoformat():
            raise ValueError("Ce projet est en cours : arrêtez le chrono avant de supprimer aujourd'hui.")

        conn.execute("DELETE FROM time_entries WHERE project_id = ? AND day = ?", (project_id, day))
        conn.execute("DELETE FROM session_log WHERE project_id = ? AND day = ?", (project_id, day))
        conn.commit()
        return build_state(conn)
    finally:
        conn.close()


def set_entry_range(project_id, day, start_hhmm, end_hhmm):
    """Fixe la durée d'un (projet, jour) à partir d'une plage début/fin (HH:MM) : REMPLACE la durée
    déjà enregistrée pour ce jour (comme la case « Remplacer » de l'import de feuille de temps)."""
    try:
        day_date = date.fromisoformat(day)
    except ValueError:
        raise ValueError("Date invalide (attendu AAAA-MM-JJ)")

    sh, sm = _parse_hhmm(start_hhmm)
    eh, em = _parse_hhmm(end_hhmm)
    start_minutes = sh * 60 + sm
    end_minutes = eh * 60 + em
    if end_minutes <= start_minutes:
        end_minutes += 24 * 60  # passage de minuit
    seconds = (end_minutes - start_minutes) * 60
    # Début connu et fourni explicitement : on le garde, ça évitera de le redemander la prochaine fois.
    start_at = datetime.combine(day_date, datetime.min.time()).replace(hour=sh, minute=sm).timestamp()

    conn = get_connection()
    try:
        project = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            raise ValueError("Projet introuvable")

        if seconds <= 0:
            conn.execute("DELETE FROM time_entries WHERE project_id = ? AND day = ?", (project_id, day))
        else:
            conn.execute(
                """
                INSERT INTO time_entries (project_id, day, seconds, first_start_at) VALUES (?, ?, ?, ?)
                ON CONFLICT(project_id, day) DO UPDATE SET seconds = excluded.seconds, first_start_at = excluded.first_start_at
                """,
                (project_id, day, seconds, start_at),
            )
        conn.commit()
        return build_state(conn)
    finally:
        conn.close()
