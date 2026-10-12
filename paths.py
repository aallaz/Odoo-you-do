"""Résolution des chemins, compatible script source et exécutable PyInstaller (onefile).

En exécutable onefile, `Path(__file__)` ne pointe pas vers un dossier utile (le code est dans
une archive interne) : les fichiers de données embarqués (HTML, CSS...) sont extraits à chaque
lancement dans un dossier temporaire (`sys._MEIPASS`), qui disparaît ensuite. Il faut donc
distinguer :
- `assets_root()` : où lire les fichiers embarqués en lecture seule (pages, style...).
- `data_root()`   : où lire/écrire les données propres à l'utilisateur (`.env`, `timer.db`),
  qui doivent survivre d'un lancement à l'autre et ne jamais être embarquées dans l'exécutable.
"""

import shutil
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))

# Dossiers d'assets embarqués (pages HTML, CSS) à rendre persistants - voir assets_root().
_ASSET_DIRS = ("Menu", "GoHome", "ImportTimeSheet", "ExportTimeSheet", "Timer", "Report", "Hours", "shared")


def data_root():
    if FROZEN:
        return Path(sys.executable).resolve().parent  # dossier où se trouve l'exécutable
    return Path(__file__).resolve().parent


def assets_root():
    if not FROZEN:
        return Path(__file__).resolve().parent

    # sys._MEIPASS est le dossier d'extraction TEMPORAIRE de ce process, nettoyé à sa sortie.
    # Le serveur tourne dans un second process (relancé par launcher.py --serve) : si le process
    # lanceur se termine avant lui, ce dossier disparaît alors que le serveur en a encore besoin.
    # On copie donc les assets une seule fois vers un dossier persistant à côté de l'exécutable,
    # regénéré seulement si l'exécutable a changé (sa date de modification sert de marqueur).
    bundled = Path(sys._MEIPASS)
    persistent = data_root() / "_assets"
    marker = persistent / ".source-mtime"
    exe_mtime = str(Path(sys.executable).stat().st_mtime)

    if not marker.exists() or marker.read_text(encoding="utf-8").strip() != exe_mtime:
        if persistent.exists():
            shutil.rmtree(persistent)
        persistent.mkdir(parents=True, exist_ok=True)
        for name in _ASSET_DIRS:
            src = bundled / name
            if src.exists():
                shutil.copytree(src, persistent / name)
        marker.write_text(exe_mtime, encoding="utf-8")

    return persistent
