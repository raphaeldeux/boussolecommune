# BoussoleCommune

**L'observatoire citoyen de la vie communale.**

BoussoleCommune est une application web libre et open source qui agrège et publie les indicateurs clés d'une commune sur 6 dimensions : soin de la maison (finances), soin du territoire, soin des habitant·es, soin du lien, soin de la parole et soin du vivant. Chaque indicateur est présenté avec sa tendance d'évolution et commenté par les administrateurs en langage citoyen.

L'objectif : rendre les données publiques lisibles par tous, pas seulement par les élus et les techniciens.

**Stack** : Flask + PostgreSQL + Docker

---

## Fonctionnalités

- **Dashboard public** avec scores A–E par thématique et score global pondéré
- **Pages thématiques par tendance** — indicateurs groupés en "En amélioration / À surveiller / Stable / Manque d'historique"
- **41 indicateurs** répartis sur 6 thématiques (dont 2 indicateurs ZAN loi Climat & Résilience)
- **Synthèses thématiques** — bloc "Ce qu'il faut retenir" généré par Mistral AI, éditable par l'admin
- **Comparaison intercommunale** — jusqu'à 4 communes côte à côte (`/comparer`)
- **Subventions** — tableau public des subventions aux associations, par domaine et thématique
- **Portrait démographique** — pyramide des âges par commune
- **Vie municipale** — PV de conseils uploadés en PDF, résumés citoyens générés par Mistral AI, délibérations structurées par thématique avec résultat des votes
- **Documents publics** — espace de publication de documents administratifs (arrêtés, délibérations, comptes-rendus) avec catégorisation
- **Interprétations manuelles** — phrases courte et longue rédigées par les administrateurs
- **Page Méthodologie** publique expliquant le calcul des scores
- **Interface d'administration** : saisie, import CSV (OFGL, générique, Cerema ENAF), gestion des références

---

## Les 6 thématiques

| Icône | Thématique | Slug | Question |
|-------|-----------|------|---------|
| 🏠 | Soin de la maison | `finances` | La commune se donne-t-elle les moyens d'agir ? |
| 🌳 | Soin du territoire | `cadre_vie` | La commune entretient-elle son territoire ? |
| ❤️ | Soin des habitant·es | `personnes` | La commune prend-elle soin de ses habitant·es ? |
| 🤝 | Soin du lien | `lien_social` | La commune fait-elle vivre sa communauté ? |
| 🏛️ | Soin de la parole | `democratie` | La commune gouverne-t-elle avec transparence ? |
| 🌿 | Soin du vivant | `vivant` | La commune ménage-t-elle son environnement ? |

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

# 5. (Optionnel) Charger les données de référence communes INSEE (~35k communes)
docker compose exec web python seed_communes.py
```

L'application est accessible sur **http://localhost:5001**

---

## Sans Docker (développement local)

Un serveur PostgreSQL doit être disponible localement.

```bash
pip install -r requirements.txt
cp .env.example .env  # puis éditer (DATABASE_URL vers votre PostgreSQL local)

python seed.py           # initialiser les indicateurs
python seed_communes.py  # référentiel communes INSEE (optionnel)
python wsgi.py           # lancer le serveur
```

---

## Variables d'environnement

| Variable | Description | Requis |
|----------|-------------|--------|
| `DATABASE_URL` | URL de connexion PostgreSQL | Oui (défaut : `postgresql://boussole:boussole@localhost:5432/boussolecommune`) |
| `POSTGRES_PASSWORD` | Mot de passe PostgreSQL (utilisé par le conteneur `db`) | Oui |
| `ADMIN_USERNAME` | Nom d'utilisateur interface admin | Oui |
| `ADMIN_PASSWORD` | Mot de passe interface admin | Oui |
| `SECRET_KEY` | Clé secrète Flask (sessions) | Oui |
| `FLASK_ENV` | `production` ou `development` | Non (défaut : development) |
| `MISTRAL_API_KEY` | Clé API Mistral AI (résumés PV conseils + synthèses thématiques) | Non |
| `MISTRAL_MODEL` | Modèle Mistral à utiliser | Non (défaut : `mistral-small-latest`) |

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

**Cerema ENAF — Zéro Artificialisation Nette**
Les 2 indicateurs ZAN (consommation annuelle d'espaces NAF et quota restant 2031) sont récupérés depuis les Fichiers Fonciers Cerema. La commune doit avoir son code INSEE renseigné dans sa fiche.

Aller sur `/admin/upload` → "Données ZAN (Cerema ENAF)" → cliquer "Récupérer" → valider l'aperçu.

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

### Conseils municipaux

Aller sur `/admin/conseils` → créer un conseil → uploader le PDF du procès-verbal → générer le résumé citoyen via Mistral AI. Le résumé est structuré en thématiques avec les délibérations et résultats de votes.

### Documents publics

Aller sur `/admin/documents` → publier un document (arrêté, compte-rendu, délibération, etc.) avec titre, catégorie et fichier PDF. Les documents sont accessibles publiquement sur la page Vie municipale.

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
Le score global est une moyenne pondérée des 6 thématiques : Finances 25%, Cadre de vie 20%, Personnes 20%, Lien social 15%, Démocratie 12%, Vivant 8%.

**Affichage du badge A–E :** le badge n'est affiché sur la page publique que pour les indicateurs ayant une référence externe robuste (`valeur_reference` renseignée) ou une source légale reconnue (`api_rpls`, `api_cerema`). Les autres indicateurs affichent uniquement la valeur et la tendance d'évolution.

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
│   ├── database.py              # PostgreSQL : connexion psycopg2 + init schéma
│   ├── auth.py                  # Auth admin (session + décorateur)
│   ├── models/                  # Accès base de données
│   │   ├── indicateur.py
│   │   ├── donnee.py
│   │   ├── interpretation.py
│   │   ├── synthese_thematique.py  # Synthèses "Ce qu'il faut retenir"
│   │   ├── subvention.py
│   │   ├── conseil.py
│   │   ├── document.py
│   │   └── pyramide.py
│   ├── services/
│   │   ├── scoring.py           # Calcul scores A–E
│   │   ├── parser_csv.py        # Parser format générique
│   │   ├── parser_ofgl.py       # Parser format OFGL (finances)
│   │   ├── ai_service.py        # Génération IA via Mistral (PV + synthèses)
│   │   └── fetchers/
│   │       ├── macantine.py     # Récupération données EGAlim
│   │       └── zan.py           # Récupération données ENAF (Cerema, ZAN)
│   ├── routes/
│   │   ├── public.py            # Routes publiques
│   │   └── admin.py             # Routes admin (protégées)
│   └── templates/
│       ├── base.html
│       ├── public/              # dashboard, thematique, comparer, conseils, documents
│       └── admin/               # login, dashboard, saisie, upload, subventions, conseils
├── uploads/                     # Fichiers uploadés (PDF, CSV)
├── seed.py                      # Initialisation des 41 indicateurs
├── seed_communes.py             # Référentiel communes INSEE (~35k communes)
├── wsgi.py                      # Point d'entrée Flask
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## Roadmap

- [ ] **Export des données** — téléchargement public des données brutes en CSV
- [ ] **Journal d'audit** — traçabilité des saisies admin (qui, quand, quelle valeur)
- [ ] **Intégrations supplémentaires** — connecteurs automatiques vers INSEE et data.gouv.fr
- [ ] **API publique JSON** — exposer les données pour intégration dans d'autres outils (site municipal, etc.)

---

*Projet open source — contributions bienvenues.*
