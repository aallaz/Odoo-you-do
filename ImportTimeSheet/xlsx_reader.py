#!/usr/bin/env python3
"""
Lecture d'un fichier .xlsx en grille de texte (bibliothèque standard uniquement : zipfile + ElementTree).

Chaque ligne du tableau renvoyé correspond au numéro de ligne Excel (les lignes vides sont conservées),
ce qui permet à la page d'import de parler en « lignes 8 à 12 » comme dans Excel.

Les cellules numériques au format date/heure sont converties en texte, comme dans un CSV :
    date       -> "AAAA-MM-JJ"
    heure      -> "HH:MM:SS"   (0,3493 au format hh:mm  ->  "08:23:00")
    date+heure -> "AAAA-MM-JJ HH:MM:SS"
Les autres nombres restent des nombres (2,5 -> "2.5").
"""

import io
import re
import zipfile
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

MAX_ROWS = 5000
MAX_COLS = 60

BUILTIN_KINDS = {14: "date", 15: "date", 16: "date", 17: "date", 22: "datetime"}
BUILTIN_KINDS.update({i: "time" for i in (18, 19, 20, 21, 45, 46, 47)})


def _kind_from_code(code):
    """Classe un format de nombre personnalisé : 'date', 'time', 'datetime' ou None."""
    code = re.sub(r'"[^"]*"', "", code)                                  # texte entre guillemets
    code = re.sub(r"\\.", "", code)                                      # caractère échappé
    code = re.sub(r"\[(?![hms]+\])[^\]]*\]", "", code, flags=re.I)       # [Red], [$-409]...
    low = code.lower()
    has_time = bool(re.search(r"[hs]", low)) or "am/pm" in low
    has_date = bool(re.search(r"[yd]", low))
    if has_time and has_date:
        return "datetime"
    if has_time:
        return "time"
    if has_date or "m" in low:
        return "date"
    return None


def _si_text(si):
    parts = []
    for child in si:
        if child.tag == M + "t":
            parts.append(child.text or "")
        elif child.tag == M + "r":
            parts.extend(t.text or "" for t in child.findall(M + "t"))
    return "".join(parts)


def _read_shared_strings(zf):
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    return [_si_text(si) for si in root.findall(M + "si")]


def _read_style_kinds(zf):
    """Pour chaque style de cellule (index s=), le type de format : 'date', 'time', 'datetime' ou None."""
    if "xl/styles.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/styles.xml"))
    custom = {}
    numfmts = root.find(M + "numFmts")
    if numfmts is not None:
        for nf in numfmts.findall(M + "numFmt"):
            custom[int(nf.get("numFmtId"))] = nf.get("formatCode", "")
    kinds = []
    xfs = root.find(M + "cellXfs")
    for xf in (xfs.findall(M + "xf") if xfs is not None else []):
        fmt_id = int(xf.get("numFmtId", 0))
        kinds.append(_kind_from_code(custom[fmt_id]) if fmt_id in custom else BUILTIN_KINDS.get(fmt_id))
    return kinds


def _sheet_paths(zf):
    """[(nom, chemin dans le zip)] dans l'ordre des onglets, et True si le classeur est en base 1904."""
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    targets = {rel.get("Id"): rel.get("Target") for rel in rels}
    sheets = []
    for sheet in wb.find(M + "sheets"):
        target = targets[sheet.get(R + "id")]
        path = target.lstrip("/") if target.startswith("/") else "xl/" + target
        sheets.append((sheet.get("name"), path))
    props = wb.find(M + "workbookPr")
    return sheets, props is not None and props.get("date1904") in ("1", "true")


def _col_index(ref):
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _number_to_text(value, kind, base):
    if kind == "date":
        return (base + timedelta(days=int(value))).strftime("%Y-%m-%d")
    if kind == "time":
        seconds = round(value * 86400)
        return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"
    if kind == "datetime":
        return (base + timedelta(seconds=round(value * 86400))).strftime("%Y-%m-%d %H:%M:%S")
    return str(int(value)) if value == int(value) else format(value, ".10g")


def read_xlsx(data: bytes, sheet_index: int = 0) -> dict:
    """Renvoie {"sheets": [noms], "sheet": index lu, "rows": [[texte, ...], ...]}. Lève ValueError si illisible."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        sheets, is_1904 = _sheet_paths(zf)
        if not sheets:
            raise ValueError("Aucun onglet dans le fichier")
        sheet_index = min(max(sheet_index, 0), len(sheets) - 1)
        shared = _read_shared_strings(zf)
        kinds = _read_style_kinds(zf)
        root = ET.fromstring(zf.read(sheets[sheet_index][1]))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise ValueError(f"Fichier .xlsx illisible ({exc})") from exc

    base = datetime(1904, 1, 1) if is_1904 else datetime(1899, 12, 30)
    cells = {}
    max_row = max_col = 0
    row_no = 0
    for row in root.iter(M + "row"):
        row_no = int(row.get("r") or row_no + 1)
        if row_no > MAX_ROWS:
            break
        col_no = -1
        for c in row.findall(M + "c"):
            col_no = _col_index(c.get("r")) if c.get("r") else col_no + 1
            if col_no >= MAX_COLS:
                continue
            v = c.find(M + "v")
            kind = c.get("t")
            if kind == "inlineStr":
                text = _si_text(c.find(M + "is")) if c.find(M + "is") is not None else ""
            elif v is None or v.text is None:
                text = ""
            elif kind == "s":
                text = shared[int(v.text)]
            elif kind in ("str", "e", "b"):
                text = v.text
            else:
                style = int(c.get("s", 0))
                fmt_kind = kinds[style] if style < len(kinds) else None
                text = _number_to_text(float(v.text), fmt_kind, base)
            if text != "":
                cells[(row_no, col_no)] = text
                max_row = max(max_row, row_no)
                max_col = max(max_col, col_no + 1)

    rows = [[cells.get((r, c), "") for c in range(max_col)] for r in range(1, max_row + 1)]
    return {"sheets": [name for name, _ in sheets], "sheet": sheet_index, "rows": rows}


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        sys.exit("Usage : python xlsx_reader.py fichier.xlsx")
    with open(sys.argv[1], "rb") as fh:
        print(json.dumps(read_xlsx(fh.read()), ensure_ascii=False, indent=1))
