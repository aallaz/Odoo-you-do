#!/usr/bin/env python3
"""
Heures de pointage Odoo (hr.attendance) totalisées par jour, en LECTURE SEULE.

Le seul appel fait à Odoo est `search_read` sur hr.attendance : ce module n'écrit rien.
Les datetimes Odoo sont en UTC naïf ; les jours sont calculés en heure locale de la machine.
Un pointage sans check-out (personne n'a encore pointé la sortie) compte jusqu'à maintenant.
"""

from datetime import date, datetime, time, timedelta, timezone

from odoo_projects import odoo_call

ODOO_FORMAT = "%Y-%m-%d %H:%M:%S"


def _to_local(odoo_dt: str) -> datetime:
    return datetime.strptime(odoo_dt, ODOO_FORMAT).replace(tzinfo=timezone.utc).astimezone()


def _to_odoo(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime(ODOO_FORMAT)


def _local_midnight(d: date) -> datetime:
    return datetime.combine(d, time.min).astimezone()


def aggregate(records: list[dict], start: date, end: date, now: datetime) -> list[dict]:
    """Découpe chaque pointage par jour local et additionne. Renvoie [{date, minutes, open}] trié."""
    minutes: dict[date, float] = {}
    open_days: set[date] = set()

    for rec in records:
        begin = _to_local(rec["check_in"])
        finish = _to_local(rec["check_out"]) if rec["check_out"] else now
        is_open = not rec["check_out"]

        cursor = begin
        while cursor < finish:
            day = cursor.date()
            segment_end = min(finish, _local_midnight(day + timedelta(days=1)))
            if start <= day <= end:
                minutes[day] = minutes.get(day, 0) + (segment_end - cursor).total_seconds() / 60
                if is_open:
                    open_days.add(day)
            cursor = segment_end

    return [{"date": d.isoformat(), "minutes": round(m, 2), "open": d in open_days} for d, m in sorted(minutes.items())]


def fetch_daily_attendance(url: str, db: str, api_key: str, employee_id: int, start: date, end: date) -> list[dict]:
    range_start = _local_midnight(start)
    range_end = _local_midnight(end + timedelta(days=1))

    # A ET B ET (C OU D) : pointages qui touchent la période (sortie dans la période, ou pas encore de sortie).
    domain = [
        ["employee_id", "=", employee_id],
        ["check_in", "<", _to_odoo(range_end)],
        "|",
        ["check_out", ">=", _to_odoo(range_start)],
        ["check_out", "=", False],
    ]
    records = odoo_call(url, db, api_key, "hr.attendance", "search_read", {
        "domain": domain,
        "fields": ["check_in", "check_out"],
        "order": "check_in asc",
    })
    return aggregate(records, start, end, datetime.now().astimezone())
