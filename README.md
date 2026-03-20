# BoussoleCommune

**L'observatoire citoyen de la vie communale.**

BoussoleCommune est une application web libre et open source qui agrège et publie les indicateurs clés d'une commune sur 6 dimensions : finances, cadre de vie, personnes, lien social, démocratie et vivant. Chaque indicateur est noté de A à E et commenté par les administrateurs en langage citoyen.

L'objectif : rendre les données publiques lisibles par tous, pas seulement par les élus et les techniciens.

**Stack** : Flask + SQLite + Docker

---

## Fonctionnalités

- **Dashboard public** avec scores A–E par thématique et score global pondéré
- **41 indicateurs** répartis sur 6 thématiques
- **Comparaison intercommunale** — jusqu'à 4 communes côte à côte (`/comparer`)
- **Subventions** — tableau public des subventions aux associations, par domaine et thématique
- **Portrait démographique** — pyramide des âges par commune
- **Interprétations manuelles** — phrases courte et longue rédigées par les administrateurs
- **Page Méthodologie** publique expliquant le calcul des scores
- **Interface d'administration** : saisie, import CSV, gestion des références

---

## Les 6 thématiques

| Thématique | Slug |
|------------|------|
| Soin des finances | `finances` |
| Soin du cadre de vie | `cadre_vie` |
| Soin des personnes | `personnes` |
| Soin du lien social | `lien_social` |
| Soin de la démocratie | `democratie` |
| Soin du vivant | `vivant` |

---

## Démarrage rapide

### Prérequis

- Docker + Docker Compose

### Installation

```bash
# 1. Cloner le dépôt
git clone <url-du-repo>
cd boussolecommune

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
| `ANTHROPIC_API_KEY` | Clé API Anthropic (Claude) pour les interprétations | Oui |
| `ADMIN_PASSWORD` | Mot de passe interface admin | Oui |
| `SECRET_KEY` | Clé secrète Flask (sessions) | Oui |
| `FLASK_ENV` | `production` ou `development` | Non (défaut : development) |
| `DATABASE_PATH` | Chemin vers le fichier SQLite | Non (défaut : `data/boussolecommune.db`) |

---

## Alimentation des données

Les 41 indicateurs se divisent en deux familles selon leur mode d'alimentation.

### Données automatiques

Ces indicateurs sont récupérés sans intervention manuelle.

**ma-cantine (API gouvernementale)**
Les 4 indicateurs EGAlim (bio, produits durables, viandes de qualité, poissons durables) sont récupérés automatiquement depuis [ma-cantine.agriculture.gouv.fr](https://ma-cantine.agriculture.gouv.fr).

**OFGL (finances)**
Les 6 indicateurs financiers sont alimentés par import du fichier brut exporté depuis [ofgl.fr](https://www.ofgl.fr), filtré sur votre commune :

```csv
code_commune;libelle_commune;annee;libelle_compte;montant
12345;Ma Commune;2023;Épargne brute;1250000
12345;Ma Commune;2023;Encours de dette;8400000
```

Aller sur `/admin/upload` → format OFGL → déposer le fichier → valider l'aperçu.

### Données manuelles

Les 31 indicateurs restants sont alimentés de deux façons.

**Saisie directe**
Aller sur `/admin/saisie` → sélectionner l'indicateur → saisir l'année, la valeur et la source.

**Import CSV générique**
Aller sur `/admin/upload` → format générique → déposer le fichier → valider l'aperçu.

```csv
annee,indicateur_id,valeur,source
2024,eco_part_bio_cantine,42,Rapport DRAAF 2024
2024,soc_logements_sociaux_taux,18.3,Bilan SRU préfecture 2024
```

### Références — communes similaires

Aller sur `/admin/references` → sélectionner un indicateur → saisir une valeur de référence (ex : moyenne de strate OFGL) et son libellé. Une barre de comparaison apparaît alors automatiquement sur la page publique.

### Subventions

Aller sur `/admin/subventions` → saisie ligne par ligne ou import CSV. Les subventions sont affichées publiquement avec un classement par domaine (sport, culture, social, environnement, éducation, santé).

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
Le score global est une moyenne pondérée des 6 thématiques : Finances 25%, Vivant 20%, Personnes 20%, Lien social 15%, Démocratie 10%, Cadre de vie 10%.

La méthodologie complète est disponible sur `/methodologie`.

---

## Déploiement sur VPS (Nginx + HTTPS)

L'application tourne dans Docker, exposée uniquement en local sur le port 5001. Nginx assure le reverse proxy et HTTPS via Let's Encrypt.

```bash
# Prérequis
apt install nginx certbot python3-certbot-nginx

# Copier la config Nginx
cp nginx/boussolecommune.conf /etc/nginx/sites-available/boussolecommune
ln -s /etc/nginx/sites-available/boussolecommune /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# Obtenir le certificat SSL
certbot --nginx -d votre-commune.example.fr

# Lancer l'application
docker compose up -d --build
docker compose exec web python seed.py
```

La configuration Nginx complète est dans [`nginx/boussolecommune.conf`](nginx/boussolecommune.conf).

---

## Structure du projet

```
boussolecommune/
├── app/
│   ├── __init__.py              # Application factory
│   ├── config.py                # Variables d'environnement
│   ├── database.py              # SQLite : init schéma
│   ├── auth.py                  # Auth admin (session + décorateur)
│   ├── models/                  # Accès base de données
│   │   ├── indicateur.py
│   │   ├── donnee.py
│   │   ├── interpretation.py
│   │   ├── subvention.py
│   │   └── pyramide.py
│   ├── services/
│   │   ├── scoring.py           # Calcul scores A–E
│   │   ├── parser_csv.py        # Parser format générique
│   │   ├── parser_ofgl.py       # Parser format OFGL (finances)
│   │   └── fetchers/
│   │       └── macantine.py     # Récupération données EGAlim
│   ├── routes/
│   │   ├── public.py            # Routes publiques
│   │   └── admin.py             # Routes admin (protégées)
│   └── templates/
│       ├── base.html
│       ├── public/              # dashboard, thematique, comparer, methodologie
│       └── admin/               # login, dashboard, saisie, upload, subventions
├── data/                        # Base SQLite (volume Docker)
├── uploads/                     # CSV uploadés temporairement
├── seed.py                      # Initialisation des 41 indicateurs
├── wsgi.py                      # Point d'entrée Flask
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## Roadmap

- [ ] **Visualisation de tendances** — graphiques d'évolution pluriannuelle pour chaque indicateur
- [ ] **Export des données** — téléchargement public des données brutes en CSV
- [ ] **Journal d'audit** — traçabilité des saisies admin (qui, quand, quelle valeur)
- [ ] **Intégrations supplémentaires** — connecteurs automatiques vers INSEE et data.gouv.fr
- [ ] **API publique JSON** — exposer les données pour intégration dans d'autres outils (site municipal, etc.)

---

*Projet open source — contributions bienvenues.*
