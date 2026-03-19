# CommuneSanté

**L'observatoire citoyen de la vie communale.**

CommuneSanté est une application web libre et open source qui agrège, interprète et publie les indicateurs clés d'une commune sur 6 dimensions : finances, écologie, social, gouvernance, services publics et vitalité économique. Chaque indicateur est exprimé en langage citoyen et analysé automatiquement via l'API Claude (Anthropic).

L'objectif : rendre les données publiques lisibles par tous, pas seulement par les élus et les techniciens.

**Stack** : Flask + SQLite + Docker

---

## Fonctionnalités

- **Dashboard public** avec scores A–E par thématique et score global pondéré
- **37 indicateurs** couvrant 6 thématiques (finances, écologie, social, gouvernance, services, économie)
- **Interprétation automatique** des données via Claude (Anthropic)
- **Comparaison avec des communes similaires** (valeurs de référence saisies par l'admin)
- **Interface d'administration** : saisie manuelle, import CSV, gestion des références
- **Intégration ma-cantine** : récupération automatique des données EGAlim
- **Déploiement simplifié** via Docker

---

## Démarrage rapide

### Prérequis

- Docker + Docker Compose

### Installation

```bash
# 1. Cloner le dépôt
git clone <url-du-repo>
cd communesante

# 2. Configurer les variables d'environnement
cp .env.example .env
# Éditer .env avec vos valeurs (voir section Variables d'environnement)

# 3. Lancer l'application
docker compose up -d

# 4. Initialiser les indicateurs
docker compose exec web python seed.py
```

L'application est accessible sur **http://localhost:5001**

---

## Sans Docker (développement local)

```bash
pip install -r requirements.txt
cp .env.example .env  # puis éditer

python seed.py        # initialiser les indicateurs
python wsgi.py        # lancer le serveur
```

---

## Variables d'environnement

| Variable | Description | Requis |
|----------|-------------|--------|
| `ANTHROPIC_API_KEY` | Clé API Anthropic (Claude) | Oui pour les interprétations |
| `ADMIN_PASSWORD` | Mot de passe interface admin | Oui |
| `SECRET_KEY` | Clé secrète Flask (sessions) | Oui |
| `FLASK_ENV` | `production` ou `development` | Non (défaut : development) |
| `DATABASE_PATH` | Chemin vers le fichier SQLite | Non (défaut : `data/communesante.db`) |

---

## Alimentation des données

### Saisie manuelle

Aller sur `/admin/saisie` → sélectionner l'indicateur → saisir l'année, la valeur et la source.

### Import CSV

Aller sur `/admin/upload` → choisir le format → déposer le fichier → valider l'aperçu.

**Format générique** (toutes thématiques) :
```csv
annee,indicateur_id,valeur,source
2024,eco_part_bio_cantine,42,Rapport DRAAF 2024
2024,soc_logements_sociaux_taux,18.3,Bilan SRU préfecture 2024
```

**Format OFGL** (finances uniquement) — export brut depuis [ofgl.fr](https://www.ofgl.fr), filtré sur votre commune :
```csv
code_commune;libelle_commune;annee;libelle_compte;montant
12345;Ma Commune;2023;Épargne brute;1250000
12345;Ma Commune;2023;Encours de dette;8400000
```

### Références — communes similaires

Aller sur `/admin/references` → sélectionner un indicateur → saisir :
- **Valeur de référence** : moyenne de la strate (ex : `6.8`)
- **Année** : année de la donnée de référence
- **Source / libellé** : description de la strate (ex : `Moyenne communes 5 000–10 000 hab. (OFGL)`)

Quand une référence est renseignée, une barre de comparaison apparaît automatiquement sur la page publique.

---

## Scoring A–E

| Score | Couleur | Signification |
|-------|---------|---------------|
| A | Vert foncé | Très satisfaisant |
| B | Vert | Satisfaisant |
| C | Orange | À surveiller |
| D | Rouge | Préoccupant |
| E | Rouge foncé | Critique |

Le score thématique est calculé dès que **3 indicateurs minimum** sont renseignés.
Le score global est une moyenne pondérée des 6 thématiques : Finances 25%, Écologie 20%, Social 20%, Gouvernance 15%, Services 10%, Économie 10%.

---

## Déploiement (reverse proxy)

Exemple de configuration Apache2 pour un déploiement en HTTPS :

```apache
<VirtualHost *:443>
    ServerName votre-commune.example.fr

    ProxyPass / http://127.0.0.1:5001/
    ProxyPassReverse / http://127.0.0.1:5001/

    # SSL via Certbot / Let's Encrypt
</VirtualHost>
```

---

## Structure du projet

```
communesante/
├── app/
│   ├── __init__.py              # Application factory
│   ├── config.py                # Variables d'environnement
│   ├── database.py              # SQLite : init schéma
│   ├── auth.py                  # Auth admin (session + décorateur)
│   ├── models/                  # Accès base de données
│   │   ├── indicateur.py
│   │   ├── donnee.py
│   │   └── interpretation.py
│   ├── services/
│   │   ├── scoring.py           # Calcul scores A–E
│   │   ├── claude.py            # Appels API Claude + cache
│   │   ├── parser_csv.py        # Parser format générique
│   │   └── parser_ofgl.py       # Parser format OFGL (finances)
│   ├── routes/
│   │   ├── public.py            # Routes publiques
│   │   └── admin.py             # Routes admin (protégées)
│   └── templates/
│       ├── base.html
│       ├── public/              # dashboard.html, thematique.html
│       └── admin/               # login, dashboard, saisie, upload
├── data/                        # Base SQLite (volume Docker)
├── uploads/                     # CSV uploadés temporairement
├── seed.py                      # Initialisation des 37 indicateurs
├── wsgi.py                      # Point d'entrée Flask
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## Roadmap

### Court terme

- [ ] **Indicateur de fraîcheur des données** — afficher publiquement la date de dernière mise à jour de chaque indicateur
- [ ] **Export CSV/JSON public** — permettre aux citoyens de télécharger les données brutes
- [ ] **Meilleur rapport d'erreurs CSV** — indiquer précisément les lignes rejetées lors d'un import et pourquoi
- [ ] **Recherche d'indicateurs** — barre de recherche par mot-clé dans l'interface admin

### Moyen terme

- [ ] **Visualisation de tendances** — graphiques d'évolution sur plusieurs années pour chaque indicateur
- [ ] **Alertes de mise à jour** — notifications admin quand une donnée dépasse X mois sans actualisation
- [ ] **Détection de doublons à l'import** — avertissement si un indicateur/année existe déjà avant d'écraser
- [ ] **Journal d'audit** — tracer qui a saisi quoi et quand, pour renforcer la transparence
- [ ] **Intégrations supplémentaires** — connecteurs automatiques vers INSEE, OFGL, data.gouv.fr

### Long terme

- [ ] **Multi-communes** — permettre à une même instance de gérer plusieurs communes (comparaisons intercommunales)
- [ ] **Exports PDF** — rapport thématique ou global téléchargeable, adapté aux conseils municipaux
- [ ] **Personnalisation des pondérations** — permettre à chaque commune d'ajuster les poids du score global
- [ ] **API publique JSON** — exposer les données pour intégration dans d'autres outils (site municipal, etc.)
- [ ] **Modélisation de scénarios** — simuler l'impact d'une amélioration sur le score global

---

## Cahier des charges

Le cahier des charges complet est disponible dans [`CAHIER_DES_CHARGES.md`](CAHIER_DES_CHARGES.md).

---

*Projet open source — contributions bienvenues.*
