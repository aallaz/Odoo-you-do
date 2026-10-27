#!/usr/bin/env python3
"""Lanceur multiplateforme (Windows, macOS, Linux).

Démarre server.py en arrière-plan s'il ne tourne pas déjà, puis ouvre l'app dans une fenêtre
Chrome/Edge/Chromium sans barre d'adresse (mode --app), taille lue dans launcher.ini.

    python launcher.py
    python launcher.py --port 8080

Sur Windows, la taille/position sont aussi réappliquées de force après l'ouverture : Chromium
(--app=) n'honore --window-size/--window-position qu'au tout premier lancement d'un profil
d'app donné, puis restaure la géométrie qu'il a mémorisée lui-même et ignore les flags.
"""

import argparse
import configparser
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

import paths

INI_PATH = paths.data_root() / "launcher.ini"
DEFAULT_WIN_W, DEFAULT_WIN_H = 980, 800


def load_window_size():
    config = configparser.ConfigParser()
    config["window"] = {"width": str(DEFAULT_WIN_W), "height": str(DEFAULT_WIN_H)}
    if INI_PATH.exists():
        config.read(INI_PATH, encoding="utf-8")
    else:
        with open(INI_PATH, "w", encoding="utf-8") as f:
            config.write(f)
    try:
        return config.getint("window", "width"), config.getint("window", "height")
    except (configparser.Error, ValueError):
        return DEFAULT_WIN_W, DEFAULT_WIN_H


def is_up(url):
    try:
        with urllib.request.urlopen(url, timeout=0.5) as r:
            return r.status == 200
    except Exception:
        return False


def start_server(port):
    # Exécutable PyInstaller : pas de python.exe séparable, paths.spawn_server() se relance alors
    # soi-même avec un indicateur caché qui bascule main() vers server.main() (voir plus bas).
    paths.spawn_server(port)


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


def force_window_geometry_windows(width, height, title_contains="Accueil", timeout=8.0):
    """Retrouve la fenêtre de l'app par son titre et force sa taille/position (centrée sur
    l'écran principal), car Chromium ignore --window-size après le premier lancement du profil."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    screen_w = user32.GetSystemMetrics(0)
    screen_h = user32.GetSystemMetrics(1)
    x = max(0, (screen_w - width) // 2)
    y = max(0, (screen_h - height) // 2)

    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found = {"hwnd": None}

    def _callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        cls_buf = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls_buf, 64)
        if cls_buf.value != "Chrome_WidgetWin_1":
            return True
        title_buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title_buf, 256)
        if title_contains.lower() in title_buf.value.lower():
            found["hwnd"] = hwnd
            return False
        return True

    proc = EnumWindowsProc(_callback)
    deadline = time.time() + timeout
    while time.time() < deadline and not found["hwnd"]:
        user32.EnumWindows(proc, 0)
        if not found["hwnd"]:
            time.sleep(0.25)

    if found["hwnd"]:
        user32.MoveWindow(found["hwnd"], x, y, width, height, True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.serve:
        # Relancé par start_server() dans l'exécutable figé : devient le serveur lui-même.
        import server

        sys.argv = ["server.py", "--port", str(args.port)]
        server.main()
        return

    url = f"http://127.0.0.1:{args.port}/"
    win_w, win_h = load_window_size()

    if not is_up(url):
        start_server(args.port)
        for _ in range(20):
            time.sleep(0.25)
            if is_up(url):
                break

    browser = find_browser()
    if browser:
        subprocess.Popen(
            [
                browser,
                f"--app={url}",
                f"--window-size={win_w},{win_h}",
                # Sans ça, Chrome/Edge ralentit (voire gèle) les timers JS de la fenêtre dès qu'elle
                # est cachée derrière une autre fenêtre (pas besoin d'être minimisée) : le heartbeat
                # (shared/heartbeat.js) s'arrête silencieusement et le serveur coupe le chrono au bout
                # de HEARTBEAT_TIMEOUT alors que l'utilisateur travaille toujours.
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-background-timer-throttling",
            ],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if sys.platform == "win32":
            force_window_geometry_windows(win_w, win_h)
    else:
        webbrowser.open(url)


if __name__ == "__main__":
    main()
