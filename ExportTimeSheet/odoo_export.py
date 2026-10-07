#!/usr/bin/env python3
"""
Export des heures du Timer vers Odoo (lignes de feuille de temps : account.analytic.line).

Chaque entrée = {"name": nom du projet Timer, "date": "AAAA-MM-JJ", "hours": heures décimales}.
Le rapport renvoyé sépare trois listes : imported, errors, ignored.
"""

from odoo_projects import OdooAuthError, OdooError, extract_job_number, find_projects, odoo_call


def _export_one(url, db, api_key, employee_id, entry, project_cache):
    """Crée la ligne dans Odoo. Renvoie (id créé, nom du projet) ; lève OdooError si l'entrée est refusée."""
    job_number = extract_job_number(entry["name"])
    if job_number not in project_cache:
        project_cache[job_number] = find_projects(url, db, api_key, job_number)
    projects = project_cache[job_number]

    if not projects:
        raise OdooError(f"Aucun projet Odoo avec le numéro {job_number}")
    if len(projects) > 1:
        names = " / ".join(p["name"] for p in projects)
        raise OdooError(f"Plusieurs projets Odoo avec le numéro {job_number} : {names}")
    project = projects[0]

    # Évite les doublons si on exporte deux fois la même période.
    existing = odoo_call(url, db, api_key, "account.analytic.line", "search_read", {
        "domain": [
            ["employee_id", "=", employee_id],
            ["project_id", "=", project["id"]],
            ["date", "=", entry["date"]],
        ],
        "fields": ["unit_amount"],
    })
    if existing:
        hours = sum(line["unit_amount"] for line in existing)
        raise OdooError(f"Déjà {hours:g} h dans Odoo pour {project['name']} le {entry['date']}")

    created = odoo_call(url, db, api_key, "account.analytic.line", "create", {
        "vals_list": [{
            "name": entry["name"],
            "date": entry["date"],
            "project_id": project["id"],
            "employee_id": employee_id,
            "unit_amount": entry["hours"],
        }],
    })
    return created[0], project["name"]


def export_entries(url, db, api_key, employee_id, entries, ignore_no_number=True):
    """
    Envoie les entrées valides et range chacune dans imported / errors / ignored.
    OdooAuthError et requests.RequestException remontent : l'appelant arrête tout.
    """
    report = {"imported": [], "errors": [], "ignored": []}
    project_cache = {}

    for entry in entries:
        row = {"name": entry["name"], "date": entry["date"], "hours": entry["hours"]}

        if extract_job_number(entry["name"]) is None:
            if ignore_no_number:
                report["ignored"].append({**row, "reason": "Pas de numéro d'affaire"})
            else:
                report["errors"].append({**row, "reason": "Pas de numéro d'affaire"})
            continue

        if entry["hours"] <= 0:
            report["ignored"].append({**row, "reason": "Durée nulle"})
            continue

        try:
            line_id, project_name = _export_one(url, db, api_key, employee_id, entry, project_cache)
        except OdooAuthError:
            raise
        except OdooError as exc:
            report["errors"].append({**row, "reason": str(exc)})
            continue

        report["imported"].append({**row, "odoo_id": line_id, "project": project_name})

    return report
