# Odoo : outils de suivi du temps

Petit serveur local (Python, sans framework) qui sert plusieurs pages pour suivre ses heures et les
synchroniser avec Odoo (feuilles de temps et pointages).

## Démarrage

Prérequis : [Python 3](https://www.python.org/downloads/) (Windows : cocher « Add python.exe to PATH ») et,
pour la fenêtre « app », Chrome, Edge ou Chromium (sinon le navigateur par défaut est utilisé).

```bash
pip install -r requirements.txt
python launcher.py             # démarre le serveur et ouvre l'app (Windows, macOS, Linux)
python launcher.py --port 8080
```

Sous Windows, double-cliquer `lancer.vbs` fait la même chose sans fenêtre de console.

Pour lancer le serveur seul : `python server.py` (http://127.0.0.1:8000).

Fichier `.env` à la racine :

```
ODOO_URL=https://...
ODOO_DB=...              # facultatif
ODOO_API_KEY=...
ODOO_EMPLOYEE_ID=...
```

Le `.env` contient une clé API : ne pas le partager ni le versionner.

## Statut

Projet en cours de test. À faire plus tard : packager avec PyInstaller (un exécutable par système,
construit sur chaque système) pour distribuer sans installer Python.

## Style

Toutes les pages chargent `shared/style.css` (couleurs, police, composants communs), servi sur `/shared/style.css`.
Une page n'ajoute dans son `<style>` que ses règles propres. Les pages de l'ancien style sont dans `_ancien-style/`.

## Les pages

| Route | Dossier | Rôle |
|---|---|---|
| `/` | `Menu/` | Accueil, liens vers les pages |
| `/timer` | `Timer/` | Chronomètre par projet, temps stocké par jour dans `Timer/timer.db` (SQLite) |
| `/import-timesheet` | `ImportTimeSheet/` | Importe un CSV ou un xlsx vers le Timer ou vers Odoo |
| `/export-timesheet` | `ExportTimeSheet/` | Envoie les heures du Timer vers Odoo (`account.analytic.line`) ou en CSV |
| `/hours` | `Hours/` | Heures de pointage Odoo par jour (lecture seule) |
| `/gohome` | `GoHome/` | Heure de sortie calculée depuis les pointages du jour |
| `/report` | `Report/` | Rapport journalier par projet |

`daily-project-report/` est un plugin Super Productivity (le rapport `/report` en vient).
Les données Super Productivity ne sont pas utilisées par l'import.

## Règle des noms de projet

Un projet est rattaché à Odoo par son **numéro d'affaire** : le nom commence par des chiffres suivis de `_`
(`26006_EXH_W&W2027_Scéno LAB & EXPO` → 26006). Un nom sans numéro (`Séance`) reste utilisable dans le Timer
mais est ignoré (ou refusé) à l'envoi vers Odoo. L'export refuse aussi d'écrire une ligne s'il en existe déjà une
pour le même projet, le même jour et le même employé.

## Import TimeSheet

Flux : fichier → lecture (lignes + colonnes) → aperçu → destination (Timer ou Odoo).

Rôle des colonnes (choisi dans l'en-tête du tableau, ou tapé sous la forme `date;project;timein;timeout`) :

| Jeton | Rôle |
|---|---|
| `ignore` | colonne sautée |
| `date` | jour (`jj.mm.aaaa`, `aaaa-mm-jj`, `j.m.aaaa`) |
| `project` | nom du projet |
| `timein` / `timeout` | début / fin ; les paires sont prises dans l'ordre (début, fin, début, fin…) |
| `duration` | durée directe (`1:30`, `1h30`, `2.5`, `2,5`) |
| `totaltime` | total du jour : contrôle, ou durée s'il n'y a ni heures ni `duration` |

Règles de calcul :
- Chaque paire vaut `fin − début`, les pauses entre deux paires sont donc exclues. `fin < début` = passage de minuit.
- Les lignes de même date et de même projet sont sommées.
- Une durée nulle n'est jamais envoyée.
- Vers le Timer, le temps existant est **remplacé** par défaut (sinon un même fichier importé deux fois doublerait
  les heures). La case « Remplacer » permet d'ajouter à la place.
- Un nom sans numéro peut être rattaché à un projet Odoo (bouton « chercher dans Odoo ») ; le choix est mémorisé
  dans le navigateur.
- Modèles : « Enregistrer comme modèle » garde séparateur, lignes et colonnes dans le navigateur. Les modèles
  livrés avec la page se déclarent dans `BUILTIN_TEMPLATES` (`ImportTimeSheet/index.html`).

Fichiers de test fictifs et résultats attendus : `ImportTimeSheet/samples/README.md`.
Les fichiers `import-test.xlsx` et `import-test.csv` à la racine sont des exemples fournis à la main.

## API du serveur

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/api/timer/state` | État du Timer (projets, historique, timer en cours) |
| POST | `/api/timer/start`, `/api/timer/stop` | Démarre / arrête le timer |
| POST | `/api/export/odoo` | `{entries: [{name, date, hours}]}` → lignes de feuille de temps Odoo |
| POST | `/api/import/timer` | `{entries, mode: "replace" \| "add"}` → écrit dans le Timer |
| POST | `/api/import/parse-xlsx` | `{data: base64, sheet}` → grille de texte, une ligne par ligne Excel |
| GET | `/api/odoo/projects?q=` | Recherche de projets Odoo par nom |
| GET | `/api/attendance?start=&end=` | Pointages Odoo par jour |
| GET | `/api/pointages` | Pointages Odoo du jour |

Le serveur n'écoute que sur `127.0.0.1`.

## Structure

```
server.py                  serveur + routes
Menu/ GoHome/ Hours/ Report/ Timer/ ImportTimeSheet/ ExportTimeSheet/    une page (index.html) par dossier
Timer/timer_store.py       base SQLite du Timer
ExportTimeSheet/odoo_projects.py, odoo_export.py    appels Odoo (API JSON-2) et export
ImportTimeSheet/xlsx_reader.py    lecture xlsx (bibliothèque standard uniquement)
```
