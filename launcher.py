#!/usr/bin/env python3
"""Lanceur multiplateforme (Windows, macOS, Linux).

Démarre server.py en arrière-plan s'il ne tourne pas déjà, puis ouvre l'app dans une fenêtre
Chrome/Edge/Chromium sans barre d'adresse (mode --app), à taille fixe.

    python launcher.py
    python launcher.py --port 8080
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WIN_W, WIN_H = 980, 820


def is_up(url):
    try:
        with urllib.request.urlopen(url, timeout=0.5) as r:
            return r.status == 200
    except Exception:
        return False


def start_server(port):
    cmd = [sys.executable, str(ROOT / "server.py"), "--port", str(port)]
    kwargs = {"cwd": str(ROOT), "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)


def find_browser():
    if sys.platform == "win32":
        bases = [os.environ.get(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        rels = [r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"]
        candidates = [Path(b) / r for r in rels for b in bases if b]
    elif sys.platform == "darwin":
        apps = [
            "Google Chrome.app/Contents/MacOS/Google Chrome",
            "Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "Chromium.app/Contents/MacOS/Chromium",
        ]
        candidates = [Path(base) / a for base in ("/Applications", str(Path.home() / "Applications")) for a in apps]
    else:
        names = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"]
        candidates = [Path(p) for p in (shutil.which(n) for n in names) if p]
    return next((str(c) for c in candidates if c.is_file()), None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    url = f"http://127.0.0.1:{args.port}/"

    if not is_up(url):
        start_server(args.port)
        for _ in range(20):
            time.sleep(0.25)
            if is_up(url):
                break

    browser = find_browser()
    if browser:
        subprocess.Popen(
            [browser, f"--app={url}", f"--window-size={WIN_W},{WIN_H}"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    else:
        webbrowser.open(url)


if __name__ == "__main__":
    main()
