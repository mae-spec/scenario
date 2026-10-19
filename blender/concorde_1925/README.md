# Place de la Concorde, juin 1925 — scène Blender

Scène générée entièrement par script (aucune texture ni modèle externe), inspirée de la
carte postale *« A C. 17 — Paris — Perspective de la Place et du Pont de la Concorde »*,
avec le contrechamp sur l'Hôtel de Crillon et la vue depuis une chambre du 2ᵉ étage.

Testé avec Blender 5.2 LTS (rendu Cycles).

## Générer le .blend

```bash
blender -b -P blender/concorde_1925/build.py -- --out concorde_1925.blend
# avec des aperçus basse définition de chaque caméra :
blender -b -P blender/concorde_1925/build.py -- --out concorde_1925.blend --previews apercus/
```

La génération prend environ 15 s. Le fichier pèse environ 12 Mo (il est ignoré par git).

## Géographie réelle

- Dans le .blend, **+Y = nord géographique, +X = est**. L'objet vide `REPERE_PLACE` porte la
  rotation de la place : l'axe rue Royale → Madeleine a un azimut de **25,6°**
  (perpendiculaire à l'axe historique Louvre → Arc de Triomphe). Tous les décors sont enfants
  de ce repère : origine = l'obélisque.
- Les positions viennent des coordonnées WGS84 des monuments, projetées localement
  (`geo.py`) : la Madeleine, le Palais-Bourbon, le dôme des Invalides (1,34 km),
  la tour Eiffel (2,1 km), le Grand et le Petit Palais, le pont Alexandre-III et le cours de la
  Seine.
- Dimensions, recalées sur les coordonnées des monuments :
  - emprise de la place, anciens fossés compris : 359 × 212 m ;
  - octogone intérieur à balustrades : côté nord à 85 m de l'obélisque (statues de Strasbourg
    et de Brest), côtés est et ouest à 160 m ;
  - fontaines à 64 m de l'obélisque, sur l'axe ;
  - façades des palais de Gabriel à 148 m ;
  - centre du pont de la Concorde à 247 m, Palais-Bourbon à 420 m, Madeleine à 562 m ;
  - obélisque de 22,83 m sur un socle de 9,2 m ;
  - palais de Gabriel de 96 m chacun de part et d'autre de la rue Royale, avec une colonnade
    de 12 colonnes corinthiennes entre deux avant-corps à fronton.
- Le **Crillon** occupe la partie ouest du palais ouest (côté rue Boissy-d'Anglas) ;
  l'Automobile Club de France est côté rue Royale. Le palais est est l'Hôtel de la Marine.

Les cotes sont justes à quelques mètres près. Je n'ai pas eu accès à un relevé (cadastre,
OSM, IGN) pendant la construction : toutes les valeurs sont regroupées dans `geo.py`
pour pouvoir les recaler facilement.

## Détails d'époque (1925)

- **Pas de pyramidion doré** sur l'obélisque : la coiffe date de 1998.
- **Pont de la Concorde à sa largeur d'origine** (15,5 m) : il n'a été élargi qu'en 1930-1932.
- **Pierre noircie** par la suie : les ravalements datent de la loi Malraux (1962).
- **Dorure ternie** du dôme des Invalides (il a été redoré en 1937 puis en 1989).
- **Air chargé** de fumées de charbon : densité d'aérosols du ciel augmentée, et un volume
  de brume (`BRUME_PARIS_1925`) qui fond les lointains comme sur la photo.
- **Chevaux de Marly** à l'entrée des Champs-Élysées (les originaux n'ont été déplacés au
  Louvre qu'en 1984). Renommées de Coysevox à l'entrée des Tuileries, statues des huit villes,
  colonnes rostrales et candélabres de Hittorff.
- **Soleil réel** du **12 juin 1925 à 15 h 30** (heure d'été française, UTC+1) :
  azimut 245°, hauteur 49,5°, calculé dans `geo.sun_direction()`. Pour changer l'heure,
  modifiez `SHOOT_DATE` / `SHOOT_LOCAL_TIME` dans `geo.py` et relancez le script.

## Véhicules

Construits dans `vehicles.py` à partir des proportions des modèles réels : Citroën 5 HP
Trèfle, Citroën B12, taxi Renault KZ de la G7, Renault NN, Ford T, Hispano-Suiza H6B,
fourgonnette Citroën, autobus Schneider H de la STCRP (vert et crème, plate-forme arrière) et
un fiacre attelé. La circulation se fait à droite.

- **En circulation** : six trajectoires (Champs-Élysées ↔ Rivoli, quai, rue Royale ↔ pont,
  devant les palais, Cours-la-Reine), avec une contrainte *Follow Path* animée sur
  240 images à 24 i/s. Les roues tournent grâce à un pilote (driver) sans Python, qui
  fonctionne même sans « Auto Run Python Scripts ».
- **À l'arrêt devant le Crillon** : deux taxis G7, une Hispano-Suiza, une B12 et une fourgonnette.
- Chaque voiture a sa propre peinture (emplacement de matériau lié à l'objet) : vous pouvez
  la changer voiture par voiture sans toucher aux autres.

## Caméras — ARRI Alexa 65, 2,40:1

Capteur de l'Alexa 65 en *Open Gate* : 54,12 mm de large. Extraction 2,40:1 sur toute la
largeur, soit 54,12 × 22,55 mm, rendue en **6560 × 2733 px**. Le *sensor fit* est horizontal.
Profondeur de champ activée (diaphragme à 9 lames), flou de mouvement à 180°.

| Caméra | Plan | Optique |
|---|---|---|
| `CAM_01_CARTE_POSTALE` | Plongée depuis le toit de l'Hôtel de la Marine, cadrée comme la carte postale | 55 mm, T8 |
| `CAM_02_CONTRECHAMP_LARGE` | Contrechamp depuis la place : le Crillon, la rue Royale, l'Hôtel de la Marine | 45 mm, T5.6 |
| `CAM_03_CONTRECHAMP_CRILLON` | Contrechamp serré sur la façade du Crillon, avec la fenêtre de la chambre | 80 mm, T4 |
| `CAM_04_CHAMBRE_CRILLON` | Intérieur de la chambre Louis XVI, fenêtre ouverte sur la place | 35 mm, T4 |
| `CAM_05_VUE_FENETRE_2E` | La vue du 2ᵉ étage à travers la colonnade : obélisque, Palais-Bourbon, Invalides | 40 mm, T5.6 |

Les plans 3, 4 et 5 raccordent : c'est la même fenêtre, dans la 3ᵉ travée de la colonnade en
partant de l'ouest (`architecture.ROOM_BAY`). Le 2ᵉ étage est l'étage aux fenêtres carrées, au-dessus
de l'étage noble. Le plancher est à 14,6 m et l'œil de la caméra à 16,2 m.

En vérifiant la géométrie, une remarque : la carte postale n'est sans doute pas prise du Crillon. Le dôme
des Invalides y apparaît à gauche du Palais-Bourbon. Cela suppose un point de vue nettement à l'est de
l'axe, donc sur l'Hôtel de la Marine. Depuis le Crillon (`CAM_05`), le dôme passe à droite du Palais-Bourbon.

## Organisation du .blend

| Collection | Contenu |
|---|---|
| `TERRAIN_SEINE` | Sol, Seine, quais et parapets, pont de la Concorde, pont Alexandre-III |
| `PLACE_AMENAGEMENTS` | Terre-pleins, balustrades, refuges, candélabres, colonnes rostrales, passants |
| `MONUMENTS` | Obélisque, fontaines des Fleuves et des Mers, statues des villes, chevaux de Marly |
| `BATIMENTS` | Palais de Gabriel, Madeleine, Palais-Bourbon, Invalides, tour Eiffel, Grand et Petit Palais, îlots haussmanniens |
| `CHAMBRE_CRILLON_2E` | Chambre : parquet, boiseries, rideaux, bergères, cheminée, croisée ouverte |
| `VEGETATION` | Environ 4 200 arbres en copies liées (Champs-Élysées, Tuileries, quais, Invalides) |
| `VEHICULES_1925` | Prototypes (masqués), véhicules en circulation et à l'arrêt, trajectoires |
| `CAMERAS_ALEXA65` | Les cinq caméras |
| `LUMIERES_ATMOSPHERE` | Soleil, rebond de lumière dans la chambre, volume de brume |

## Rendu

- Le moteur est Cycles, configuré sur le GPU, avec 256 échantillons et le débruitage.
  Gestion des couleurs AgX *Medium High Contrast*, exposition à −0,5.
- Pour les essais, baissez `Output > Resolution %` à 25 %. Masquer `BRUME_PARIS_1925` accélère
  beaucoup le rendu, au prix de lointains moins fondus.
- Le look « carte postale » (sépia, grain) est à faire à l'étalonnage. La scène est en couleur.

## Fichiers

| Fichier | Rôle |
|---|---|
| `build.py` | Point d'entrée ; options en tête de fichier |
| `geo.py` | Coordonnées, dimensions, date, calcul du soleil |
| `helpers.py` | Primitives de maillage, collections, copies liées |
| `materials.py` | Matériaux procéduraux |
| `city.py` | Sol, Seine, ponts, aménagement de la place, monuments lointains, îlots |
| `monuments.py` | Obélisque, fontaines, statues, candélabres, passants |
| `architecture.py` | Palais de Gabriel et chambre du Crillon |
| `vegetation.py` | Arbres |
| `vehicles.py` | Véhicules et circulation |
| `scene_setup.py` | Caméras Alexa 65, soleil, ciel, brume, réglages de rendu |
| `apercus/` | Aperçus basse définition de chaque caméra |
