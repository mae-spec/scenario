# Comparateur de scénarios

Application web **100 % locale**, à installer sur le NAS (`10.10.30.56`), pour comparer
automatiquement les versions successives d'un scénario : dialogues, actions, séquences,
personnages, structure.

> **Confidentialité.** Rien n'est envoyé en ligne. L'interface ne charge aucune ressource
> externe (ni CDN, ni police, ni statistiques) et le serveur bloque toute connexion
> sortante au niveau du processus (voir [Garanties « hors ligne »](#garanties--hors-ligne-)).
> Les scénarios sont stockés uniquement dans le dossier de données du NAS.

## Fonctionnalités

**Import** — Final Draft (`.fdx`), Fountain (`.fountain`, `.spmd`), Word (`.docx`),
OpenDocument (`.odt`), PDF (avec texte), texte brut (`.txt`).

- FDX, DOCX et ODT : les styles de scénario (Séquence, Personnage, Dialogue, Parenthèse,
  Transition… en français ou en anglais) sont utilisés ; sans styles, la mise en page est déduite
  (retraits, majuscules).
- Word : les modifications suivies sont lues dans leur **état final**.
- PDF / texte : entêtes et pieds de page répétés, numéros de page, `(SUITE)`, `(MORE)`,
  `(CONT'D)`, astérisques de révision et numéros de séquence sont retirés ; une réplique ou un
  paragraphe coupé par un saut de page est recollé. Le même scénario exporté en PDF, FDX ou Fountain
  donne une analyse identique (vérifié par les tests).
- Entêtes reconnus : `INT. CUISINE - JOUR`, `12 EXT. RUE - NUIT 12`, `INT./EXT.`, `SÉQ. 4 - …`,
  `3. CUISINE - INT. JOUR`, `INTÉRIEUR …`, `#12#` (Fountain)…

**Comparaison**

- Séquences **ajoutées, supprimées, modifiées, déplacées** (changement d'ordre), entêtes modifiés
  (lieu, moment), renumérotation.
- Répliques **ajoutées, supprimées, modifiées mot à mot**, **réattribuées** à un autre personnage,
  extension changée (`OFF`, `V.O.`…).
- Actions/didascalies et transitions ajoutées, supprimées, modifiées.
- Éléments **déplacés** dans une séquence ou d'une séquence à une autre.
- Personnages apparus/disparus, **renommages probables**, évolution des répliques et des mots.
- Changements **mineurs** (ponctuation, casse) signalés et masquables.
- Options : ignorer la casse, ignorer la ponctuation, normaliser la typographie
  (’ ' « » " … espaces insécables). Les retours à la ligne ne comptent jamais comme des changements.

**Interface**

- Projets (un par scénario) avec l'historique des versions (nom, date, notes, réordonnables).
- Vue côte à côte ou fusionnée, filtres (type de séquence, répliques/actions, personnage,
  recherche), contexte dépliable, navigation au clavier (`j` / `k`).
- Onglets **Personnages** (répliques et mots par personnage, A vs B) et **Structure** (carte des
  séquences, déplacements, ajouts, suppressions).
- **Évolution** du projet : tableau des changements entre chaque version successive et nombre de
  répliques par personnage au fil des versions.
- Lecture d'une version telle qu'elle a été analysée (pour vérifier l'import), export Fountain.
- **Comparaison rapide** de deux fichiers sans les enregistrer.
- Exports : rapport **HTML** autonome (imprimable en PDF), **CSV** (Excel, séparateur `;`), JSON.
- Archive ZIP d'un projet (fichiers originaux + métadonnées), sauvegarde complète.
- Thème clair/sombre automatique.

## Installation sur le NAS (Docker)

Prérequis : Docker / Container Manager (Synology) ou Container Station (QNAP).

1. Copier ce dossier sur le NAS, par exemple `/volume1/docker/scenario`
   (partage réseau, ou `git clone` depuis le NAS).
2. Créer le fichier de configuration :

   ```sh
   cd /volume1/docker/scenario
   cp .env.example .env
   mkdir -p data
   id            # relever uid et gid de votre utilisateur
   ```

   Dans `.env`, renseigner `PUID`/`PGID` (valeurs de `id`), et de préférence un mot de passe
   `SCENARIO_PASSWORD`. `BIND_IP=10.10.30.56` limite l'écoute à l'adresse du NAS.
3. Démarrer :

   ```sh
   docker compose up -d --build
   ```

   **Synology (Container Manager)** : *Projet* → *Créer* → chemin `/volume1/docker/scenario`
   → *Utiliser le docker-compose.yml existant* → *Suivant* → *Terminé*.
   **QNAP (Container Station)** : *Applications* → *Créer* → coller le contenu de
   `docker-compose.yml` (et remplacer les variables `${…}` par vos valeurs).
4. Ouvrir **http://10.10.30.56:8765** depuis un poste du réseau local.

Le build télécharge l'image Python et 4 bibliothèques depuis les dépôts officiels
(téléchargement uniquement, rien n'est envoyé). Ensuite, l'application tourne sans Internet.

### NAS sans accès à Internet

Construire l'image sur un PC, puis la copier :

```sh
./scripts/export-image.sh                        # NAS Intel/AMD
PLATFORM=linux/arm64 ./scripts/export-image.sh   # NAS ARM
# copier scenario-comparateur-1.0.0.tar sur le NAS, puis sur le NAS :
docker load -i scenario-comparateur-1.0.0.tar
docker compose up -d                             # sans --build
```

### Sans Docker

Python 3.10 ou plus récent :

```sh
./scripts/run-sans-docker.sh     # écoute sur 10.10.30.56:8765, données dans ./data
```

## Configuration

| Variable (.env)          | Défaut        | Rôle                                                   |
|--------------------------|---------------|--------------------------------------------------------|
| `BIND_IP`                | `10.10.30.56` | Adresse du NAS sur laquelle le port est ouvert         |
| `PORT`                   | `8765`        | Port d'accès (8080 est souvent déjà pris, ex. Kitsu)   |
| `DATA_DIR`               | `./data`      | Dossier des données sur le NAS                         |
| `PUID` / `PGID`          | `1000`        | Utilisateur propriétaire du dossier de données         |
| `SCENARIO_USER`          | `scenario`    | Identifiant de connexion                               |
| `SCENARIO_PASSWORD`      | *(vide)*      | Mot de passe (authentification HTTP) — recommandé      |
| `SCENARIO_MAX_UPLOAD_MB` | `50`          | Taille maximale d'un fichier                           |

## Données, sauvegarde, mise à jour

- `data/scenario.db` : base SQLite (projets, versions, analyses) ;
  `data/files/` : fichiers originaux déposés.
- Sauvegarde cohérente (même application en marche) :

  ```sh
  docker compose exec scenario python -m app.backup /data/sauvegardes
  ```

  Les instantanés du NAS (Snapshot Replication, Hyper Backup…) sur `data/` conviennent aussi.
- Mise à jour : remplacer les fichiers de l'application puis `docker compose up -d --build`.
  Les données sont conservées ; si l'analyseur a évolué, les versions sont ré-analysées
  automatiquement à partir des fichiers originaux.

## Garanties « hors ligne »

- Interface : HTML/CSS/JS servis par l'application elle-même, sans aucune URL externe
  (vérifié par un test automatique). La politique de sécurité du navigateur (CSP
  `default-src 'self'`) interdit en plus tout chargement externe.
- Pas de page `/docs` FastAPI (elle chargerait Swagger depuis un CDN).
- Serveur : au démarrage, un verrou bloque toute connexion sortante et toute résolution DNS
  (`app/offline.py`) ; un test vérifie qu'une requête vers Internet échoue.
- Conteneur : DNS pointé sur `127.0.0.1`, système de fichiers en lecture seule, aucun privilège,
  utilisateur non-root, port ouvert uniquement sur `10.10.30.56`.
- Le dépôt Git ne contient que le code : `data/` est exclu par `.gitignore`. Ne déposez pas de
  scénarios dans le dépôt.

## Conseils pour de bonnes comparaisons

- Le format **FDX** (Final Draft, Fade In, WriterDuet, Arc Studio…) ou **Fountain** donne les
  résultats les plus fiables. Le PDF fonctionne bien s'il contient du texte (pas un scan).
- Après un import, ouvrez la version (*Texte analysé*) pour vérifier que personnages et entêtes
  sont bien reconnus.
- Comparer des formats différents (ex. PDF ancien vs FDX nouveau) est possible : l'analyse est
  normalisée.

## Développement

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest          # tests
SCENARIO_HOST=127.0.0.1 .venv/bin/python -m app.main
```

Organisation :

```
app/
  screenplay/   lecture des formats → modèle commun (séquences, répliques, actions)
  compare/      alignement des séquences et des répliques, différences mot à mot
  store.py      stockage SQLite + fichiers
  main.py       API HTTP et service de l'interface
  report.py     exports HTML / CSV
  offline.py    verrou anti-connexion sortante
  static/       interface web (sans dépendance)
tests/          tests (tous formats, moteur, API, garanties hors ligne)
```

## Autres contenus du dépôt

- [`blender/concorde_1925/`](blender/concorde_1925/README.md) : générateur de la scène Blender
  « Place de la Concorde, juin 1925 » (contrechamp sur le Crillon, caméras ARRI Alexa 65 en 2,40:1).
