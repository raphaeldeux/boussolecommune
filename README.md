# CommuneSanté — Sautron

L'observatoire citoyen de la commune de Sautron (Loire-Atlantique).

Application web qui agrège, interprète et publie les indicateurs de santé de la commune sur 6 dimensions : finances, écologie, social, gouvernance, services publics, vitalité économique. Chaque indicateur est exprimé en langage citoyen et interprété automatiquement via l'API Claude.

**Stack** : Flask + SQLite + Docker · **Déploiement** : VPS + reverse proxy Apache2

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
# Éditer .env avec vos valeurs :
#   ANTHROPIC_API_KEY=sk-ant-...
#   ADMIN_PASSWORD=votre-mot-de-passe
#   SECRET_KEY=une-clé-aléatoire-longue

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

## Alimentation des données

### Saisie manuelle

Aller sur `/admin/saisie` → sélectionner l'indicateur → saisir l'année, la valeur et la source.

### Upload CSV

Aller sur `/admin/upload` → choisir le format → déposer le fichier → valider l'aperçu.

**Format générique** (toutes thématiques) :
```csv
annee,indicateur_id,valeur,source
2024,eco_part_bio_cantine,42,Rapport DRAAF Pays de la Loire 2024
2024,soc_logements_sociaux_taux,18.3,Bilan SRU préfecture 2024
```

**Format OFGL** (finances uniquement) — export brut depuis [ofgl.fr](https://www.ofgl.fr), filtré sur Sautron (code commune 44202) :
```csv
code_commune;libelle_commune;annee;libelle_compte;montant
44202;Sautron;2023;Épargne brute;1250000
44202;Sautron;2023;Encours de dette;8400000
```

### Références — communes similaires

Aller sur `/admin/references` → sélectionner un indicateur → saisir :
- **Valeur de référence** : moyenne de la strate (ex : `6.8`)
- **Année** : année de la donnée de référence (ex : `2022`)
- **Source / libellé** : description de la strate (ex : `Moyenne communes 5 000–10 000 hab. (OFGL)`)

Quand une référence est saisie pour un indicateur, une barre de comparaison apparaît automatiquement
sur la page publique de la thématique. Les références existantes peuvent être éditées ou supprimées
depuis le tableau récapitulatif de la même page.

---

## Scoring A–E

| Score | Couleur | Signification |
|-------|---------|---------------|
| A | Vert foncé | Très satisfaisant |
| B | Vert | Satisfaisant |
| C | Orange | À surveiller |
| D | Rouge | Préoccupant |
| E | Rouge foncé | Critique |

Le score thématique est calculé dès que **3 indicateurs minimum** sont renseignés. Le score global est une moyenne pondérée des 6 thématiques (Finances 25%, Écologie 20%, Social 20%, Gouvernance 15%, Services 10%, Économie 10%).

---

## Déploiement VPS (Apache2 reverse proxy)

```apache
<VirtualHost *:443>
    ServerName communesante.sautronautrement.fr

    ProxyPass / http://127.0.0.1:5001/
    ProxyPassReverse / http://127.0.0.1:5001/

    # SSL via Certbot
</VirtualHost>
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

## Cahier des charges

Le cahier des charges complet est disponible dans [`CAHIER_DES_CHARGES.md`](CAHIER_DES_CHARGES.md).

---

*Projet porté par [Sautron Autrement](mailto:contact@sautronautrement.fr)*
