# TODO

## Prochaine session : import avec les vrais fichiers
- [ ] Ouvrir `/import-timesheet` (redémarrer le serveur d'abord) et déposer un vrai fichier
- [ ] Vérifier l'aperçu : lignes détectées, colonnes, durées
- [ ] Créer un modèle par type de fichier (à me demander au cas par cas, ils vont dans `BUILTIN_TEMPLATES`)
- [ ] Vérifier l'import dans le Timer, puis l'envoi vers Odoo (jamais testé avec de vraies données)

## À vérifier (rien n'a été testé dans un vrai navigateur)
- [ ] Affichage de la page d'import : tableau, listes déroulantes, recherche de projet Odoo, rapport
- [ ] Envoi direct vers Odoo depuis l'import
- [ ] `totaltime` : confirmer le sens (total du jour répété sur chaque ligne, ou une seule fois par jour ?)

## Nettoyage
- [ ] Supprimer les projets `99xxx_TEST_...` du Timer si les fichiers de test y ont été importés
- [ ] `import-test.csv` (racine) est vide : le remplir ou le supprimer

## Idées / limites connues
- [ ] Dates lues « jour d'abord » (`01.02.2026` = 1er février) : pas de choix du format
- [ ] Heures CSV en AM/PM non reconnues (le xlsx est converti en 24 h côté serveur)
- [ ] Aperçu du fichier limité à 300 lignes (la lecture et l'import prennent tout)
- [ ] Un xlsx multi-onglets lit un onglet à la fois ; un import ne mélange pas les onglets
- [ ] Sélection de plusieurs plages de lignes (ex. 8 à 12 et 20 à 25) : une seule plage aujourd'hui
- [ ] Un plugin Super Productivity pourrait envoyer les temps directement au Timer, sans fichier
- [ ] Toujours sauvegarder `Timer/timer.db` avant les gros imports (non versionné, exclu par `.gitignore`)
- [ ] Exécutable macOS : à construire sur un Mac (PyInstaller ne cross-compile pas), ou via une
      pipeline GitHub Actions à mettre en place. L'exe Windows existe déjà (`build_exe.py`).
