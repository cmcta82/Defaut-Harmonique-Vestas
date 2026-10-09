# Défaut Harmonique Vestas

Application locale de comparaison de la puissance active, du réactif, du vent et des événements de Richebourg, Côte Noire et Champ l’épée 2.

## Installation

Python 3.10 ou plus récent ; aucune dépendance Python supplémentaire.

1. Téléchargez ou clonez ce dépôt.
2. Placez la DB séparée dans `donnees/eolien.sqlite`, à côté du dossier `application`.
3. Sous Windows : lancez `application/Demarrer_Windows.bat`. Sous Linux/macOS : `python3 application/server.py`.
4. Consultez `http://127.0.0.1:8765` ou l’adresse affichée dans la console.

Le code est versionné sur GitHub. La DB, les sauvegardes et les fichiers sources restent séparés et sont exclus de Git. Fermez le serveur avant de remplacer la DB. Vérifiez le chemin « Base séparée » dans la console si plusieurs copies du projet existent.

Pour un autre emplacement : `python application/server.py --db /chemin/vers/eolien.sqlite`.

## Fonctions disponibles

- Choix du parc et d’une seule turbine ; aucune turbine sélectionnée à l’ouverture.
- Calendrier initial sur les sept derniers jours disponibles ; période conservée au changement de turbine ou de parc.
- Actif en bleu et réactif en rouge sur le même graphique avec deux axes indépendants.
- Vent moyen 10 minutes sur un deuxième graphique synchronisé.
- Zoom, déplacement, survol et export CSV brut.
- Zones à partir de deux heures après le début d’un arrêt, avec seuil actif réglable.
- Alarmes TempSwitch0GridFilter : horaires complets Detected → Device ack.
- Prix négatifs communs aux trois parcs et arrêts chiro par turbine.
- Points Herbissonne PDL sur une ligne par turbine, sans fin inventée.
- Simplification des grandes fenêtres conservant les extrema et les ruptures.
- Base SQLite consultée en lecture seule par le serveur.

## Horaires et interprétation

Les horaires stockés sont affichés tels quels, sans conversion automatique été/hiver. Les fichiers déjà corrigés doivent être importés sans correction supplémentaire. Une concordance temporelle ne démontre pas une causalité. Les zones après deux heures repèrent un arrêt prolongé de puissance active et ne confirment pas à elles seules une perte de régulation réactive.

Les unités kW, kvar et m/s sont supposées lorsque les sources ne les précisent pas. Les puissances sont des valeurs Max. ; le vent une moyenne sur dix minutes.

## Imports et évolution

Voir [le guide détaillé](application/LIRE_MOI.md) pour les imports, sauvegardes et le schéma. L’importeur fourni attend les formats décrits dans ce guide ; les CSV corrigés avec d’autres en-têtes nécessitent une adaptation explicite.

Le code peut évoluer sans remplacer la DB. Améliorations envisagées : import depuis l’interface, traçabilité du référentiel horaire et analyse statistique des corrélations.
