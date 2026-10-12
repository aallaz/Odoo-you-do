#!/usr/bin/env python3
"""
Petit serveur local qui sert les pages des différentes apps (Menu, GoHome,
ImportTimeSheet, ...) et expose /api/pointages (proxy vers Odoo) pour éviter
les soucis de CORS/file:// du navigateur.

Structure attendue (une app = un dossier) :
    Odoo/
        server.py
        .env
        Menu/index.html              -> servi sur /
        GoHome/index.html            -> servi sur /gohome
        GoHome/heure_sortie.py
        ImportTimeSheet/index.html   -> servi sur /import-timesheet (+ API POST /api/import/parse-xlsx, /api/import/timer,
                                        GET /api/odoo/projects?q=)
        ImportTimeSheet/xlsx_reader.py -> lecture d'un .xlsx en grille de texte
        ExportTimeSheet/index.html   -> servi sur /export-timesheet (+ API POST /api/export/odoo)
        ExportTimeSheet/odoo_export.py, odoo_projects.py -> envoi des heures vers Odoo
        Timer/index.html             -> servi sur /timer
        Timer/timer_store.py         -> base SQLite (Timer/timer.db) + API /api/timer/*
        Report/index.html            -> servi sur /report
        Hours/index.html             -> servi sur /hours (+ API GET /api/attendance, lecture seule)
        Hours/odoo_attendance.py     -> pointages Odoo (hr.attendance) par jour

Installation :
    pip install requests python-dotenv

Usage :
    python server.py               # démarre sur http://127.0.0.1:8000
    python server.py --port 8080
"""

import argparse
import base64
import binascii
import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent

sys.path.insert(0, str(ROOT / "GoHome"))
sys.path.insert(0, str(ROOT / "Timer"))
sys.path.insert(0, str(ROOT / "ExportTimeSheet"))
sys.path.insert(0, str(ROOT / "Hours"))
sys.path.insert(0, str(ROOT / "ImportTimeSheet"))
from heure_sortie import fetch_today_attendance  # noqa: E402
from odoo_attendance import fetch_daily_attendance  # noqa: E402
from odoo_export import export_entries  # noqa: E402
from odoo_projects import OdooError, find_projects, search_projects  # noqa: E402
from xlsx_reader import read_xlsx  # noqa: E402
import timer_store  # noqa: E402

load_dotenv(ROOT / ".env")

timer_store.init_db()
# Données de départ demandées : idempotent (n'ajoute rien si déjà présent).
timer_store.seed_entry("26006_EXH_W&W2027_Scéno LAB & EXPO", "2026-09-14", 4 * 3600)
timer_store.seed_entry("Séance", "2026-09-14", 1 * 3600)

# Route (segment d'URL) -> dossier de l'app qui la sert.
APPS = {
    "": ROOT / "Menu",
    "gohome": ROOT / "GoHome",
    "import-timesheet": ROOT / "ImportTimeSheet",
    "export-timesheet": ROOT / "ExportTimeSheet",
    "timer": ROOT / "Timer",
    "report": ROOT / "Report",
    "hours": ROOT / "Hours",
    "shared": ROOT / "shared",  # CSS commun (style.css)
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Sous pythonw.exe (lancement en arrière-plan sans console),
        # sys.stderr peut être None -> on évite de crasher la requête.
        if sys.stderr is None:
            return
        try:
            sys.stderr.write(f"{self.address_string()} - {fmt % args}\n")
        except Exception:
            pass

    def do_GET(self):
        path, _, query = self.path.partition("?")

        if path == "/api/pointages":
            self._serve_pointages()
            return
        if path == "/api/attendance":
            self._serve_attendance(parse_qs(query))
            return
        if path == "/api/timer/state":
            self._send_json(timer_store.get_state())
            return
        if path == "/api/timer/log":
            day = (parse_qs(query).get("day") or [None])[0]
            self._send_json(timer_store.get_day_log(day))
            return
        if path == "/api/odoo/projects":
            self._serve_odoo_projects(parse_qs(query))
            return
        if path == "/api/odoo/projects/by-number":
            self._serve_odoo_project_by_number(parse_qs(query))
            return

        self._serve_static(path)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            self._send_json({"error": "JSON invalide"}, status=400)
            return

        if path == "/api/timer/start":
            try:
                state = timer_store.start_project(payload.get("name", ""))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json(state)
            return

        if path == "/api/timer/stop":
            self._send_json(timer_store.stop_project())
            return

        if path == "/api/timer/rename":
            try:
                state = timer_store.rename_project(int(payload.get("id")), payload.get("name", ""))
            except (TypeError, ValueError) as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json(state)
            return

        if path == "/api/timer/set-start":
            try:
                state = timer_store.set_running_start(payload.get("start", ""))
            except (TypeError, ValueError) as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json(state)
            return

        if path == "/api/timer/stop-at":
            try:
                state = timer_store.stop_running_at(payload.get("end", ""))
            except (TypeError, ValueError) as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json(state)
            return

        if path == "/api/timer/set-minutes":
            try:
                state = timer_store.set_entry_minutes(
                    int(payload.get("id")),
                    str(payload.get("date")),
                    float(payload.get("minutes")),
                )
            except (TypeError, ValueError) as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json(state)
            return

        if path == "/api/timer/set-duration":
            try:
                state = timer_store.set_entry_range(
                    int(payload.get("id")),
                    str(payload.get("date")),
                    payload.get("start", ""),
                    payload.get("end", ""),
                )
            except (TypeError, ValueError) as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json(state)
            return

        if path == "/api/timer/round/preview":
            start = str(payload.get("start"))
            end = str(payload.get("end"))
            day_caps = self._fetch_attendance_caps(start, end)
            try:
                preview = timer_store.preview_round_entries(start, end, int(payload.get("unit")), day_caps)
            except (TypeError, ValueError) as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json(preview)
            return

        if path == "/api/timer/round/apply":
            try:
                changes = [
                    {"project_id": c["projectId"], "day": c["day"], "minutes": c["afterMinutes"]}
                    for c in payload["changes"]
                ]
            except (KeyError, TypeError):
                self._send_json({"error": "Format invalide : changes = [{projectId, day, afterMinutes}, ...] attendu"}, status=400)
                return
            try:
                state = timer_store.apply_round_changes(changes)
            except (TypeError, ValueError) as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json(state)
            return

        if path == "/api/timer/delete-entry":
            try:
                state = timer_store.delete_entry(int(payload.get("id")), str(payload.get("date")))
            except (TypeError, ValueError) as exc:
                self._send_json({"error": str(exc)}, status=400)
                return
            self._send_json(state)
            return

        if path == "/api/export/odoo":
            self._export_to_odoo(payload)
            return

        if path == "/api/import/parse-xlsx":
            self._parse_xlsx(payload)
            return

        if path == "/api/import/timer":
            self._import_to_timer(payload)
            return

        self.send_error(404, "Not found")

    def _serve_static(self, path):
        segment, _, rest = path.lstrip("/").partition("/")
        app_dir = APPS.get(segment)
        if app_dir is None:
            self.send_error(404, "Not found")
            return

        rel_path = rest or "index.html"
        file_path = (app_dir / rel_path).resolve()

        # Empêche de sortir du dossier de l'app (../..).
        if app_dir.resolve() not in file_path.parents and file_path != app_dir.resolve():
            self.send_error(403, "Forbidden")
            return
        if not file_path.is_file():
            self.send_error(404, "Not found")
            return

        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_pointages(self):
        url = os.getenv("ODOO_URL")
        db = os.getenv("ODOO_DB", "")
        api_key = os.getenv("ODOO_API_KEY")
        employee_id = os.getenv("ODOO_EMPLOYEE_ID")

        missing = [name for name, val in [("ODOO_URL", url), ("ODOO_API_KEY", api_key), ("ODOO_EMPLOYEE_ID", employee_id)] if not val]
        if missing:
            self._send_json({"error": f"Variables manquantes dans le .env : {', '.join(missing)}"}, status=500)
            return

        try:
            records = fetch_today_attendance(url, db, api_key, int(employee_id))
        except SystemExit as exc:
            self._send_json({"error": str(exc)}, status=502)
            return
        except requests.RequestException as exc:
            self._send_json({"error": f"Erreur réseau : {exc}"}, status=502)
            return

        self._send_json(records, status=200)

    def _fetch_attendance_caps(self, start, end):
        """
        {jour: minutes pointées} pour [start, end], pour servir de référence « heures de la journée »
        à l'arrondi — plus fiable que la somme du Timer, qui peut sous-compter le temps réellement
        présent. Dégrade silencieusement vers None (pas de référence Odoo) si les identifiants
        manquent, les dates sont invalides, ou Odoo est inaccessible : l'arrondi retombe alors sur la
        somme du Timer pour ces jours (voir `timer_store._compute_round_changes`).
        """
        url = os.getenv("ODOO_URL")
        db = os.getenv("ODOO_DB", "")
        api_key = os.getenv("ODOO_API_KEY")
        employee_id = os.getenv("ODOO_EMPLOYEE_ID")
        if not (url and api_key and employee_id):
            return None

        try:
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end)
            if end_date < start_date:
                return None
            days = fetch_daily_attendance(url, db, api_key, int(employee_id), start_date, end_date)
        except (ValueError, OdooError, requests.RequestException):
            return None

        return {d["date"]: d["minutes"] for d in days}

    def _serve_attendance(self, query):
        """Heures de pointage Odoo par jour (?start=AAAA-MM-JJ&end=AAAA-MM-JJ). Lecture seule."""
        url = os.getenv("ODOO_URL")
        db = os.getenv("ODOO_DB", "")
        api_key = os.getenv("ODOO_API_KEY")
        employee_id = os.getenv("ODOO_EMPLOYEE_ID")

        missing = [name for name, val in [("ODOO_URL", url), ("ODOO_API_KEY", api_key), ("ODOO_EMPLOYEE_ID", employee_id)] if not val]
        if missing:
            self._send_json({"error": f"Variables manquantes dans le .env : {', '.join(missing)}"}, status=500)
            return

        try:
            start = date.fromisoformat(query["start"][0])
            end = date.fromisoformat(query["end"][0])
        except (KeyError, IndexError, ValueError):
            self._send_json({"error": "Paramètres start et end attendus (AAAA-MM-JJ)"}, status=400)
            return
        if end < start:
            self._send_json({"error": "end doit être après start"}, status=400)
            return

        try:
            days = fetch_daily_attendance(url, db, api_key, int(employee_id), start, end)
        except OdooError as exc:
            self._send_json({"error": str(exc)}, status=502)
            return
        except requests.RequestException as exc:
            self._send_json({"error": f"Erreur réseau : {exc}"}, status=502)
            return

        self._send_json(days)

    def _export_to_odoo(self, payload):
        url = os.getenv("ODOO_URL")
        db = os.getenv("ODOO_DB", "")
        api_key = os.getenv("ODOO_API_KEY")
        employee_id = os.getenv("ODOO_EMPLOYEE_ID")

        missing = [name for name, val in [("ODOO_URL", url), ("ODOO_API_KEY", api_key), ("ODOO_EMPLOYEE_ID", employee_id)] if not val]
        if missing:
            self._send_json({"error": f"Variables manquantes dans le .env : {', '.join(missing)}"}, status=500)
            return

        try:
            entries = [
                {"name": str(e["name"]), "date": str(e["date"]), "hours": float(e["hours"])}
                for e in payload["entries"]
            ]
        except (KeyError, TypeError, ValueError):
            self._send_json({"error": "Format invalide : entries = [{name, date, hours}, ...] attendu"}, status=400)
            return

        try:
            report = export_entries(url, db, api_key, int(employee_id), entries, bool(payload.get("ignore_no_number", True)))
        except OdooError as exc:
            self._send_json({"error": str(exc)}, status=502)
            return
        except requests.RequestException as exc:
            self._send_json({"error": f"Erreur réseau : {exc}"}, status=502)
            return

        # Marque comme archivées (dans le Timer) les lignes effectivement envoyées à Odoo, pour que
        # Report puisse les masquer par défaut sans rien supprimer.
        if report["imported"]:
            timer_store.mark_entries_archived(
                [{"name": i["name"], "date": i["date"]} for i in report["imported"]]
            )

        self._send_json(report)

    def _serve_odoo_project_by_number(self, query):
        """
        Projet(s) Odoo dont le nom commence par "<numéro>_" (?number=...). Pour un nom du Timer qui a
        un numéro d'affaire en tête mais pas suivi d'un "_" (ex. "20260186. Hotel Roc..."), ça permet
        de retrouver quand même le projet Odoo correspondant et de proposer un renommage.
        """
        url = os.getenv("ODOO_URL")
        db = os.getenv("ODOO_DB", "")
        api_key = os.getenv("ODOO_API_KEY")

        missing = [name for name, val in [("ODOO_URL", url), ("ODOO_API_KEY", api_key)] if not val]
        if missing:
            self._send_json({"error": f"Variables manquantes dans le .env : {', '.join(missing)}"}, status=500)
            return

        number = (query.get("number") or [""])[0].strip()
        if not number.isdigit():
            self._send_json({"error": "Numéro d'affaire invalide"}, status=400)
            return

        try:
            projects = find_projects(url, db, api_key, number)
        except OdooError as exc:
            self._send_json({"error": str(exc)}, status=502)
            return
        except requests.RequestException as exc:
            self._send_json({"error": f"Erreur réseau : {exc}"}, status=502)
            return

        self._send_json(projects)

    def _serve_odoo_projects(self, query):
        """Recherche de projets Odoo par nom (?q=...), pour rattacher un nom sans numéro d'affaire."""
        url = os.getenv("ODOO_URL")
        db = os.getenv("ODOO_DB", "")
        api_key = os.getenv("ODOO_API_KEY")

        missing = [name for name, val in [("ODOO_URL", url), ("ODOO_API_KEY", api_key)] if not val]
        if missing:
            self._send_json({"error": f"Variables manquantes dans le .env : {', '.join(missing)}"}, status=500)
            return

        text = (query.get("q") or [""])[0].strip()
        if len(text) < 2:
            self._send_json([])
            return

        try:
            projects = search_projects(url, db, api_key, text)
        except OdooError as exc:
            self._send_json({"error": str(exc)}, status=502)
            return
        except requests.RequestException as exc:
            self._send_json({"error": f"Erreur réseau : {exc}"}, status=502)
            return

        self._send_json(projects)

    def _parse_xlsx(self, payload):
        """Fichier .xlsx (base64) -> grille de texte, une ligne par ligne Excel."""
        try:
            data = base64.b64decode(payload["data"], validate=True)
            sheet = int(payload.get("sheet", 0))
        except (KeyError, TypeError, ValueError, binascii.Error):
            self._send_json({"error": "Format invalide : {data (base64), sheet} attendu"}, status=400)
            return
        try:
            self._send_json(read_xlsx(data, sheet))
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)

    def _import_to_timer(self, payload):
        """Écrit les entrées importées dans la base du Timer (mode 'replace' par défaut, ou 'add')."""
        try:
            entries = [
                {"name": str(e["name"]), "date": str(e["date"]), "hours": float(e["hours"])}
                for e in payload["entries"]
            ]
            replace = payload.get("mode", "replace") != "add"
        except (KeyError, TypeError, ValueError):
            self._send_json({"error": "Format invalide : entries = [{name, date, hours}, ...] attendu"}, status=400)
            return
        self._send_json(timer_store.import_entries(entries, replace))

    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description="Serveur local pour les apps Odoo (Menu, GoHome, ImportTimeSheet).")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    if sys.stdout is not None:
        try:
            print(f"Ouvre http://127.0.0.1:{args.port}/ dans ton navigateur (Ctrl+C pour arrêter).")
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
