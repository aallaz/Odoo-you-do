# Fichiers de test de l'import

Données fictives. Les projets `99xxx_TEST_...` n'existent pas dans Odoo : un export vers Odoo doit
donc renvoyer « Aucun projet Odoo avec le numéro 99xxx » (test du chemin d'erreur).
Le chemin « succès » se teste avec `import-test.xlsx` à la racine (projets 26006 et 26048).

Règles de calcul testées : chaque paire `timein`/`timeout` = `out − in`, les paires d'une ligne sont
additionnées, `out < in` = passage de minuit, les lignes de même date + projet sont sommées.

| Fichier | Séparateur | Lignes | Pattern des colonnes | Résultat attendu |
|---|---|---|---|---|
| `01_in-out-simple.csv` | `;` | 4–5 | `date;project;timein;timeout;timein;timeout` | 26.08 : 8,5167 h (3:38 + 4:53) · 28.08 : 7,7 h (3:49 + 3:53) |
| `02_duree-directe.csv` | `,` | 2–6 | `date,project,duration,ignore` | 01.09 Alpha : 2 h (1:30 + 0:30 sommés) · 01.09 Gamma : 2,5 h · 02.09 Alpha : 0,75 h · 02.09 Beta : 3,25 h |
| `03_totaltime.csv` | `;` | 2–4 | `date;project;timein;timeout;timein;timeout;totaltime` | 07.09 : 8 h · 08.09 : 7,5 h calculé, **alerte** car total = 8:30 · 09.09 : 6,25 h (pas de in/out, `totaltime` sert de durée) |
| `04_minuit-et-3-plages.csv` | `;` | 2–4 | `date;project;timein;timeout;timein;timeout;timein;timeout` | 10.09 : 6 h (3 plages, pauses exclues) · 11.09 : 3,5 h (22:00 → 01:30) · 12.09 : durée nulle, **ignorée** |
| `05_projets-sans-numero.csv` | `;` | 2–5 | `date;project;timein;timeout` | `Séance` et `Réunion interne` : **sans numéro, recherche Odoo proposée** · 14.09 Alpha : 1 h · 15.09 Beta : 1,5 h (espaces autour du nom retirés) |
| `06_desordre-bom-crlf.csv` | `;` | 4–7 | `date;project;timein;timeout;ignore` | 1.9 Alpha : 8,2583 h (3:55 + 4:20:30 sommés, nom entre guillemets avec `;`) · 2.9 Beta : 0,75 h · ligne vide ignorée |

`06` cumule les pièges de format : BOM UTF-8, fins de ligne Windows, deux lignes de titre avant l'en-tête,
dates sans zéro (`1.9.2026`), heures avec secondes (`12:00:00`) ou sans zéro (`8:05`).

`import-test.xlsx` (fourni) : dates en texte `jj.mm.aaaa`, heures en fraction de jour (`0,3493` = 8:23),
lignes 4–5, pattern `date;project;timein;timeout;timein;timeout`.
Attendu : 26.08 = 8,5167 h (projet 26006) · 28.08 = 7,7 h (projet 26048).
`import-test.csv` (fourni) est vide (0 octet).
