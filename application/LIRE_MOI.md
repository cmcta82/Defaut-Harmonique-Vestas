# Explorateur éolien local

Cette version sépare l’application de ses données. Elle fonctionne sans connexion Internet, avec Python 3.10 ou plus récent. Aucun module supplémentaire n’est nécessaire.

## Installation sur Windows

1. Créez un dossier `Explorateur_eolien` sur votre ordinateur.
2. Décompressez `Application_eolienne.zip` et `Donnees_eoliennes.zip` dans ce même dossier.
3. Vous devez obtenir deux dossiers côte à côte : `application` et `donnees`. Le fichier `eolien.sqlite` doit se trouver dans `donnees`.
4. Si Python n’est pas installé, installez Python 3.10 ou plus récent. Activez l’option d’ajout de Python au PATH si elle est proposée.
5. Dans `application`, double-cliquez sur `Demarrer_Windows.bat`.
6. Le navigateur s’ouvre sur `http://127.0.0.1:8765`. Sinon, ouvrez cette adresse vous-même. Gardez la fenêtre de commande ouverte ; pour arrêter, appuyez sur Ctrl+C.

Cette application ne s’ouvre pas en double-cliquant sur le HTML : le serveur local lit la base pour afficher les données.

Sur Linux ou Raspberry Pi : ouvrez un terminal dans `application`, puis lancez `python3 server.py`.

Pour une base placée ailleurs : `python server.py --db "D:\Mes_donnees\eolien.sqlite"`.

## Contenu et utilisation

Les trois parcs et les 39 turbines sont présents, avec actif et réactif Max., vent moyen 10 minutes, alarmes TempSwitch0GridFilter, prix négatifs communs et bridages chiroptères des trois parcs. Richebourg I et II sont regroupés sous Richebourg.

La base contient 7 730 213 lignes de mesures, 4 615 alarmes, 98 périodes de prix négatifs et 3 306 bridages. Côte Noire couvre le 1er janvier 2023 à 00:00 au 8 octobre 2026 à 10:00 pour ses sept turbines (1 387 435 lignes, 1 076 alarmes). Champ l’épée 2 couvre le 1er janvier 2023 à 00:00 au 8 octobre 2026 à 11:00 pour ses six turbines (1 189 266 lignes, 983 alarmes). Richebourg couvre le 1er janvier 2023 à 00:00 au 8 octobre 2026 à 11:10 pour ses 26 turbines (5 153 512 lignes, 2 556 alarmes). Les données manquantes restent manquantes.

L’application ouvre les sept derniers jours disponibles dans les données, sans turbine sélectionnée. Choisissez un parc puis une turbine. La période reste conservée entre turbines et parcs. Molette pour zoomer, glisser pour déplacer, survol pour les valeurs et événements. Les deux graphiques partagent la même période.

Les repères violets utilisent Detected → Device ack., secondes comprises. Les repères verts et roses restent sous les courbes. Les zones ambrées commencent 2 h après le début de P ≤ 10 kW (seuil réglable) et ne constituent pas une détection de perte de régulation. Un arrêt déjà présent au début des données a un début réel inconnu.

Pour plus de 40 000 points dans une fenêtre, une vue simplifiée conserve des points originaux, les extrema de chaque variable et les ruptures dues aux valeurs manquantes. Zoomez pour afficher les données exactes à 10 minutes. L’export CSV inclut toutes les lignes de la fenêtre, sans simplification.

Les unités kW, kvar et m/s sont supposées car les en-têtes sources ne les précisent pas. Les horaires restent ceux des fichiers, sans conversion de fuseau. Une correspondance temporelle ne suffit pas à démontrer une causalité entre arrêt, réactif et alarme.

## Ajouter des fichiers historiques

Arrêtez d’abord le serveur. Ouvrez un terminal dans `application`. L’import crée une sauvegarde de la base avant chaque opération. Il n’importe qu’un parc à la fois, explicitement nommé avec `--park`.

Exemples :

```bash
python importer.py "Richebourg_2023.xlsx" --park "Richebourg"
python importer.py "Richebourg_2023_WIND.xlsx" --park "Richebourg"
python importer.py "Cote_Noire_2023.xlsx" --park "Côte Noire"
python importer.py "Champ_2023.xlsx" --park "Champ l’épée 2"
python importer.py "PN_2023.csv" --kind price
python importer.py "Chiro_Cote_Noire.csv" --park "Côte Noire" --kind environment
```

L’import XLSX reconnaît les colonnes PCTimeStamp et les colonnes Max. d’actif / réactif ou Avg. de vent. Il reconnaît également les alarmes via Unit, Detected, Device ack., Description ou Remark. Un classeur peut contenir plusieurs feuilles. Le CSV attend le séparateur `;`, Date détection, Date reset et, pour un bridage, la turbine dans la colonne B.

Seules les alarmes nommées TempSwitch0GridFilter dans Description ou Remark sont importées. Les sources avec d’autres colonnes ou unités devront être adaptées avant import. Ne mélangez pas plusieurs parcs dans un fichier d’import.

Les mesures sont identifiées par parc + turbine + horodatage. Réimporter un fichier n’ajoute pas de doublons. Une nouvelle valeur non vide remplace la valeur du même point ; une cellule vide n’efface pas une valeur existante. Les événements identiques ne sont pas ajoutés deux fois. Si un événement existant change d’heure de fin, sa correction nécessite une mise à jour contrôlée : ce premier importeur ne devine pas quel événement remplacer.

## Faire évoluer l’application en gardant la base

Le serveur ouvre la base en lecture seule : consulter ou exporter ne modifie pas les données. L’importeur est le seul outil fourni qui écrit dans la base.

Pour installer une prochaine version, arrêtez l’application et remplacez uniquement le dossier `application`. Gardez votre dossier `donnees` et ses sauvegardes. Ne redécompressez pas la base initiale sur une base enrichie.

La version du schéma est enregistrée dans SQLite (`user_version=1`). Cette application refuse une version inconnue ; les futures migrations devront sauvegarder puis transformer la base explicitement.

Pour sauvegarder manuellement : arrêtez l’application et copiez `eolien.sqlite` dans un autre dossier. Pour restaurer : arrêtez l’application et remplacez la base avec votre sauvegarde.

## Limites de cette version d’essai

L’application écoute seulement sur votre ordinateur (`127.0.0.1`). Elle n’est pas publiée sur Internet et n’est pas configurée pour l’accès depuis d’autres appareils. Elle ne comporte ni comptes ni authentification.

L’import est lancé depuis le terminal ; il n’y a pas encore de bouton d’import dans l’interface. Les calculs de corrélation statistique restent à ajouter. La consultation et le chargement par fenêtre sont prêts pour les fichiers historiques, et l’historique 2023–2026 des trois parcs a été testé sur une semaine et sur la période complète.


## Arrêts Herbissonne PDL

Les événements externes du fichier AWES_UTC_plus_1(1).xlsx sont affichés par un point jaune au début, sur une ligne dédiée à chaque turbine (G10, G20, G21, G22, G23), identifiée dans la marge gauche. Ils sont communs aux trois parcs affichés, sans turbine supplémentaire dans les sélecteurs. Le fichier ne fournit pas de fin : aucune durée n’est inventée. Les horaires de ce fichier sont utilisés en UTC+1 fixe. Les autres sources restent sans conversion ; leur référentiel horaire doit être confirmé avant de conclure à une corrélation temporelle.
