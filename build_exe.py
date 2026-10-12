#!/usr/bin/env python3
"""Construit un exécutable autonome, sans besoin de Python installé pour l'utiliser :
dist/OdooYouDo.exe sur Windows, dist/OdooYouDo.app sur macOS. PyInstaller ne cross-compile pas :
ce script doit tourner sur chaque OS cible (localement, ou via le workflow GitHub Actions
.github/workflows/build.yml qui le fait sur windows-latest et macos-latest).

    pip install pyinstaller
    python build_exe.py

Ne bundle PAS `.env` ni `Timer/timer.db` (données propres à chaque utilisateur) : à copier à
côté de l'exécutable après distribution (voir `.env.example`). Au premier lancement, l'exe copie
ses pages HTML/CSS embarquées dans un dossier `_assets/` persistant à côté de lui-même (voir
`paths.py`) ; `Timer/timer.db` et `launcher.ini` y sont aussi créés à côté de l'exe.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Pages HTML/CSS à embarquer (lues comme fichiers statiques par server.py) ; PAS les .py (résolus
# par --paths ci-dessous via l'import normal, ni .env/.db (jamais embarqués, voir paths.py).
STATIC_ASSETS = [
    ("Menu/index.html", "Menu"),
    ("GoHome/index.html", "GoHome"),
    ("ImportTimeSheet/index.html", "ImportTimeSheet"),
    ("ExportTimeSheet/index.html", "ExportTimeSheet"),
    ("Timer/index.html", "Timer"),
    ("Report/index.html", "Report"),
    ("Hours/index.html", "Hours"),
    ("shared/style.css", "shared"),
    ("shared/heartbeat.js", "shared"),
]

# Dossiers contenant les modules importés dynamiquement par server.py (sys.path.insert) : il faut
# les indiquer à PyInstaller pour qu'il les résolve (sinon ImportError au lancement de l'exe).
MODULE_DIRS = ["GoHome", "Timer", "ExportTimeSheet", "Hours", "ImportTimeSheet"]


def main():
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--windowed", "--name", "OdooYouDo",
    ]
    for d in MODULE_DIRS:
        cmd += ["--paths", d]
    for src, dest in STATIC_ASSETS:
        cmd += ["--add-data", f"{ROOT / src}{os.pathsep}{dest}"]
    cmd.append(str(ROOT / "launcher.py"))

    subprocess.run(cmd, cwd=str(ROOT), check=True)
    output = "dist/OdooYouDo.app" if sys.platform == "darwin" else "dist/OdooYouDo.exe"
    print(f"\nOK : {output}")
    print("Avant de distribuer/lancer : copier .env.example en .env (complete) a cote de l'exe.")


if __name__ == "__main__":
    main()
