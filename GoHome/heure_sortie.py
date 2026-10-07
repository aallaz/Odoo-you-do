#!/usr/bin/env python3
"""
Récupère les pointages du jour depuis Odoo (module Présences / hr.attendance)
et calcule l'heure de sortie prévue.

Installation :
    pip install requests python-dotenv

Fichier .env attendu dans le même dossier (ou ailleurs, voir load_dotenv) :
    ODOO_URL=https://tonentreprise.odoo.com
    ODOO_DB=tonentreprise
    ODOO_API_KEY=ta_cle_api
    ODOO_EMPLOYEE_ID=12

Usage :
    python heure_sortie.py               # heures visées = 8h par défaut
    python heure_sortie.py --heures 8.5  # heures visées = 8h30
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv()  # cherche un fichier .env dans le dossier courant (ou --env-file plus bas)


def odoo_datetime(dt: datetime) -> str:
    """Formate un datetime en UTC naïf, au format attendu par Odoo."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def parse_odoo_datetime(s: str) -> datetime:
    """Les datetimes Odoo sont en UTC naïf -> on les rend timezone-aware puis on convertit en heure locale."""
    dt_utc = datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return dt_utc.astimezone()  # heure locale de la machine


def fetch_today_attendance(url: str, db: str, api_key: str, employee_id: int) -> list[dict]:
    start_of_day_local = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"bearer {api_key}",
    }
    if db:
        headers["X-Odoo-Database"] = db

    payload = {
        "domain": [
            ["employee_id", "=", employee_id],
            ["check_in", ">=", odoo_datetime(start_of_day_local)],
        ],
        "fields": ["check_in", "check_out"],
        "order": "check_in asc",
    }

    resp = requests.post(f"{url.rstrip('/')}/json/2/hr.attendance/search_read", headers=headers, json=payload, timeout=15)

    if resp.status_code == 401:
        sys.exit("Clé API invalide ou expirée (401).")
    if resp.status_code == 403:
        sys.exit("Accès refusé (403) — l'API externe JSON-2 n'est disponible que sur le plan Odoo Online 'Custom'.")
    resp.raise_for_status()

    return resp.json()


def compute_exit_time(records: list[dict], target_hours: float) -> None:
    if not records:
        print("Aucun pointage trouvé aujourd'hui.")
        return

    intervals = [(parse_odoo_datetime(r["check_in"]), parse_odoo_datetime(r["check_out"]) if r["check_out"] else None) for r in records]

    arrival = intervals[0][0]

    pause = timedelta()
    for i in range(len(intervals) - 1):
        check_out_i = intervals[i][1]
        if check_out_i is not None:
            pause += intervals[i + 1][0] - check_out_i

    exit_time = arrival + timedelta(hours=target_hours) + pause

    print(f"Arrivée         : {arrival.strftime('%H:%M')}")
    print(f"Pause détectée  : {int(pause.total_seconds() // 60)} min")
    print(f"Heures visées   : {target_hours}h")
    print(f"Sortie prévue   : {exit_time.strftime('%H:%M')}")

    if intervals[-1][1] is None:
        print("(session en cours — dernier pointage sans check-out)")


def main():
    parser = argparse.ArgumentParser(description="Calcule l'heure de sortie depuis les pointages Odoo du jour.")
    parser.add_argument("--heures", type=float, default=8.0, help="Heures de travail visées (défaut : 8)")
    parser.add_argument("--env-file", type=str, default=None, help="Chemin vers un .env spécifique (défaut : ./.env)")
    args = parser.parse_args()

    if args.env_file:
        load_dotenv(args.env_file, override=True)

    url = os.getenv("ODOO_URL")
    db = os.getenv("ODOO_DB", "")
    api_key = os.getenv("ODOO_API_KEY")
    employee_id = os.getenv("ODOO_EMPLOYEE_ID")

    missing = [name for name, val in [("ODOO_URL", url), ("ODOO_API_KEY", api_key), ("ODOO_EMPLOYEE_ID", employee_id)] if not val]
    if missing:
        sys.exit(f"Variables manquantes dans le .env : {', '.join(missing)}")

    records = fetch_today_attendance(url, db, api_key, int(employee_id))
    compute_exit_time(records, args.heures)


if __name__ == "__main__":
    main()
