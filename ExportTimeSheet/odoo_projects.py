#!/usr/bin/env python3
"""
Appels Odoo (API JSON-2) + recherche du projet correspondant à un nom du Timer.

Règle : un nom valide commence par un numéro d'affaire (chiffres) suivi de "_".
    "26006_EXH_W&W2027_Scéno LAB & EXPO"   -> 26006
    "20250744_Hublot_Manufacture H3_Nyon"  -> 20250744
    "Séance"                               -> aucun numéro (invalide)

Le projet Odoo correspondant est celui dont le nom commence par "<numéro>_".

Usage :
    python odoo_projects.py "26006_EXH_W&W2027_Scéno LAB & EXPO"
"""

import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

NUMERO_RE = re.compile(r"^(\d+)_")


class OdooError(Exception):
    """Erreur renvoyée par Odoo pour un appel précis."""


class OdooAuthError(OdooError):
    """Clé invalide ou droits insuffisants : inutile de continuer."""


def extract_job_number(name: str) -> str | None:
    """Renvoie le numéro d'affaire au début du nom, ou None s'il n'y en a pas."""
    match = NUMERO_RE.match(name.strip())
    return match.group(1) if match else None


def odoo_call(url: str, db: str, api_key: str, model: str, method: str, payload: dict):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"bearer {api_key}",
    }
    if db:
        headers["X-Odoo-Database"] = db

    resp = requests.post(f"{url.rstrip('/')}/json/2/{model}/{method}", headers=headers, json=payload, timeout=15)

    if resp.status_code == 401:
        raise OdooAuthError("Clé API invalide ou expirée (401).")
    if resp.status_code == 403:
        raise OdooAuthError("Accès refusé (403) : droits insuffisants pour cette clé API.")
    if not resp.ok:
        try:
            message = resp.json().get("message") or resp.text
        except ValueError:
            message = resp.text
        raise OdooError(f"Odoo {resp.status_code} : {message}")
    return resp.json()


def find_projects(url: str, db: str, api_key: str, job_number: str) -> list[dict]:
    """Projets Odoo dont le nom commence par '<job_number>_'."""
    # "=like" avec "%" en préfiltre ; le "_" est un joker SQL, donc on re-filtre en Python.
    payload = {
        "domain": [["name", "=like", f"{job_number}%"]],
        "fields": ["name"],
    }
    projects = odoo_call(url, db, api_key, "project.project", "search_read", payload)
    return [p for p in projects if extract_job_number(p["name"]) == job_number]


def search_projects(url: str, db: str, api_key: str, query: str, limit: int = 15) -> list[dict]:
    """Projets Odoo dont le nom contient `query` (les numéros d'affaire les plus récents d'abord)."""
    payload = {
        "domain": [["name", "ilike", query]],
        "fields": ["name"],
        "limit": limit,
        "order": "name desc",
    }
    return odoo_call(url, db, api_key, "project.project", "search_read", payload)


def main():
    if len(sys.argv) != 2:
        sys.exit('Usage : python odoo_projects.py "<nom du projet>"')
    name = sys.argv[1]

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    url = os.getenv("ODOO_URL")
    db = os.getenv("ODOO_DB", "")
    api_key = os.getenv("ODOO_API_KEY")
    if not url or not api_key:
        sys.exit("ODOO_URL ou ODOO_API_KEY manquant dans le .env")

    job_number = extract_job_number(name)
    if job_number is None:
        sys.exit(f"Nom invalide, pas de numéro d'affaire : {name!r}")
    print(f"Numéro d'affaire : {job_number}")

    try:
        projects = find_projects(url, db, api_key, job_number)
    except OdooError as exc:
        sys.exit(str(exc))
    if not projects:
        sys.exit("Aucun projet Odoo avec ce numéro.")
    for p in projects:
        print(f"  id={p['id']}  {p['name']}")
    if len(projects) > 1:
        print(f"Attention : {len(projects)} projets ont ce numéro.")


if __name__ == "__main__":
    main()
