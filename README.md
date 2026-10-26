# Odoo : outils de suivi du temps

Petit serveur local (Python, sans framework) qui sert plusieurs pages pour suivre ses heures et les
synchroniser avec Odoo (feuilles de temps et pointages).

## Installer l'application (sans Python)

Les exécutables sont construits automatiquement par [GitHub Actions](.github/workflows/build.yml)
(PyInstaller ne cross-compile pas : Windows build le `.exe`, macOS build le `.app`). Pour les récupérer :
sur la page [Actions](../../actions/workflows/build.yml) du dépôt, ouvrir le dernier run réussi
(ou lancer **Run workflow** s'il n'y en a pas) ; les fichiers `OdooYouDo-windows` et `OdooYouDo-macos`
sont en bas de page, sous **Artifacts**. Si un tag `v*` a été poussé, ils sont aussi attachés directement
à la [Release](../../releases) correspondante, sous forme de `.zip`.

Dans les deux cas, il faut aussi récupérer **`.env.example`** depuis le dépôt (bouton *Code* → *Download*,
ou copier son contenu) : c'est le fichier à compléter avec les identifiants Odoo (jamais embarqué dans
l'exécutable, à garder uniquement en local).

### Windows

1. Télécharger `OdooYouDo-windows` (ou le `.zip` de la Release) et en extraire `OdooYouDo.exe` dans un
   dossier à soi (ex. `Documents\OdooYouDo\`).
2. Copier `.env.example` dans ce **même dossier**, le renommer en `.env`, et le compléter :
   ```
   ODOO_URL=https://...
   ODOO_DB=...              # facultatif
   ODOO_API_KEY=...
   ODOO_EMPLOYEE_ID=...
   ```
3. Double-cliquer `OdooYouDo.exe`. Une fenêtre sans barre d'adresse s'ouvre avec le menu de l'app
   (nécessite Chrome ou Edge déjà installés — c'est le cas par défaut sur Windows 10/11).
4. Au premier lancement, l'exe crée à côté de lui `_assets\` (pages embarquées), `Timer\timer.db` et
   `launcher.ini` : c'est normal, ce sont les données qui persistent d'un lancement à l'autre.

Pour relancer plus tard : ressortir le même `OdooYouDo.exe` (créer un raccourci sur le Bureau si besoin).

### macOS

1. Télécharger `OdooYouDo-macos` (ou le `.zip` de la Release) et en extraire `OdooYouDo.app` dans un
   dossier à soi (ex. `Documents/OdooYouDo/`).
2. Copier `.env.example` dans ce **même dossier**, le renommer en `.env`, et le compléter (voir le
   contenu ci-dessus, section Windows).
3. L'app n'est **pas signée** (pas de compte développeur Apple) : un double-clic direct sera bloqué par
   Gatekeeper (« ne peut pas être ouvert »). Pour l'autoriser une fois :
   - clic droit (ou Ctrl+clic) sur `OdooYouDo.app` → **Ouvrir** → confirmer **Ouvrir** dans la boîte de
     dialogue ; ou
   - en Terminal, depuis le dossier : `xattr -cr OdooYouDo.app`, puis double-cliquer normalement.
4. Une fenêtre Chrome/Edge sans barre d'adresse s'ouvre avec le menu de l'app (il faut l'un des deux
   déjà installé ; sinon ça ouvre le navigateur par défaut).

Pour relancer plus tard : double-cliquer `OdooYouDo.app` normalement (l'étape 3 n'est nécessaire
qu'une fois, sauf si macOS re-bloque après une mise à jour de l'app).

## Démarrage depuis les sources (pour développer)

Prérequis : [Python 3](https://www.python.org/downloads/) (Windows : cocher « Add python.exe to PATH ») et,
pour la fenêtre « app », Chrome, Edge ou Chromium (sinon le navigateur par défaut est utilisé).

```bash
pip install -r requirements.txt
python launcher.py             # démarre le serveur et ouvre l'app (Windows, macOS, Linux)
python launcher.py --port 8080
```

Sous Windows, double-cliquer `lancer.vbs` fait la même chose sans fenêtre de console.

Pour lancer le serveur seul : `python server.py` (http://127.0.0.1:8000).

Copier `.env.example` en `.env` à la racine et compléter (voir le contenu plus haut).

Le `.env` contient une clé API : ne pas le partager ni le versionner (`.gitignore` l'exclut déjà).

## Construire l'exécutable soi-même

```bash
pip install -r requirements-build.txt
python build_exe.py            # produit dist/OdooYouDo.exe (Windows) ou dist/OdooYouDo.app (macOS)
```

PyInstaller ne cross-compile pas : lancer cette commande sur chaque OS cible (ou passer par le
workflow GitHub Actions, voir plus haut, qui le fait automatiquement sur Windows et macOS).

## Données locales non versionnées

`Odoo.zip` et `tasks*.csv` à la racine sont des sauvegardes/exports personnels (vraies heures, vrais noms de
projets) : ils restent sur le disque mais sont exclus par `.gitignore`, à ne jamais ajouter au dépôt.

## Sauvegarde automatique du Timer

Le serveur copie `Timer/timer.db` vers `Timer/backups/timer-AAAA-MM-JJ.db` au démarrage, puis vérifie une
fois par heure (une copie par jour, les plus vieilles de 30 jours sont supprimées — voir `timer_store.backup_now`).
C'est un filet de sécurité purement local (même disque que la base) après une édition malheureuse dans Report,
pas une vraie sauvegarde externe.

## Déconnexion et chrono oublié

Chaque page envoie un signal (« heartbeat ») au serveur toutes les 15 secondes (`shared/heartbeat.js`). Si plus
aucun signal n'arrive pendant 5 minutes (fenêtre fermée, PC en veille...), le chrono en cours est arrêté
automatiquement. Éditer le journal du jour (Report) alors qu'un chrono tourne aujourd'hui le demande d'abord à
l'ouverture de l'éditeur (jamais après coup, à l'enregistrement) pour ne jamais perdre la session en cours.

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
| `/report` | `Report/` | Rapport journalier par projet, éditable jour par jour : par projet (durée, ou sessions détaillées) ou par heure (journal chronologique tous projets confondus) |

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
| GET | `/api/timer/log?day=AAAA-MM-JJ` | Journal in/out de la journée (tous projets), triés par heure de début ; `day` par défaut = aujourd'hui |
| POST | `/api/timer/start`, `/api/timer/stop` | Démarre / arrête le timer |
| POST | `/api/timer/set-sessions` | `{id, date, sessions: [{start, end}, ...]}` → remplace les sessions d'un (projet, jour) sans perdre un éventuel temps déjà enregistré sans session (arrondi, saisie manuelle...) ; refusé si ce projet est le chrono en cours et que `date` est aujourd'hui |
| POST | `/api/timer/set-day-log` | `{date, sessions: [{start, end, project}, ...]}` → pareil, mais remplace tout le journal d'un jour, tous projets confondus (vue « Par heure » de Report) ; refusé si un chrono tourne et que `date` est aujourd'hui |
| POST | `/api/timer/set-start` | `{start: "HH:MM"}` → redéfinit le début du chrono en cours sans l'arrêter |
| POST | `/api/timer/rename` | `{id, name}` → renomme un projet du Timer |
| POST | `/api/timer/stop-at` | `{end: "HH:MM"}` → arrête le timer en cours à une heure choisie plutôt que "maintenant" |
| POST | `/api/timer/set-duration` | `{id, date, start: "HH:MM", end: "HH:MM"}` → remplace la durée du (projet, jour) par fin − début |
| POST | `/api/timer/set-minutes` | `{id, date, minutes}` → remplace directement la durée du (projet, jour), sans début/fin |
| POST | `/api/timer/delete-entry` | `{id, date}` → supprime définitivement l'entrée (durée + journal in/out) du (projet, jour) ; refusé si ce projet est le chrono en cours et que `date` est aujourd'hui |

`time_entries` garde aussi `first_start_at` (l'heure réelle du premier démarrage du jour, remplie automatiquement
à l'arrêt du chrono, ou explicitement par `/api/timer/set-duration`) : l'édition d'une bulle déjà arrêtée peut
donc pré-remplir Début même après coup. Elle est vidée par `/api/timer/set-minutes`, puisqu'on vient de fixer
une durée sans référence d'heure.
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
