# Cahier des charges — CommuneSanté

**Sous-titre** : L'observatoire citoyen de Sautron
**Stack** : Flask + SQLite + Docker
**Déploiement cible** : VPS existant, reverse proxy Apache2, domaine dédié (ex: communesante.sautronautrement.fr)
**Auteur** : Raphaël Deux, liste Sautron Autrement
**Date** : Mars 2026

---

## 1. Vision du projet

CommuneSanté est une application web autonome qui agrège, interprète et publie les indicateurs de santé de la commune de Sautron sur l'ensemble des dimensions de la vie locale : finances, écologie, social, gouvernance, services publics, vitalité économique.

**Principe éditorial** : chaque indicateur est exprimé en langage citoyen, interprété automatiquement via l'API Claude, et sourcé de façon transparente. Les données manquantes sont affichées comme telles — l'honnêteté sur les lacunes fait partie du propos.

**Public cible** : citoyens de Sautron, non experts, cherchant à comprendre comment leur commune est gérée.

**Modèle d'alimentation** : double — upload de fichiers CSV pour les données structurées (comptes financiers, exports open data) et saisie manuelle via interface admin pour les données ponctuelles ou non disponibles en open data.

---

## 2. Architecture technique

### 2.1 Stack

- **Backend** : Python 3.11 + Flask
- **Base de données** : SQLite (fichier unique `/data/communesante.db`)
- **Conteneurisation** : Docker + Docker Compose
- **Templates** : Jinja2
- **CSS** : Tailwind CSS (CDN, pas de compilation)
- **JS** : Vanilla JS + Chart.js (CDN) pour les graphiques
- **API IA** : Anthropic Claude (claude-sonnet-4-5) pour les interprétations

### 2.2 Structure des dossiers

```
communesante/
├── app/
│   ├── __init__.py              # Application factory
│   ├── config.py                # Configuration (env vars, chemins)
│   ├── database.py              # Connexion SQLite, init schéma
│   ├── auth.py                  # Auth admin simple (login/logout)
│   ├── models/
│   │   ├── indicateur.py        # CRUD indicateurs
│   │   ├── donnee.py            # CRUD données historiques
│   │   └── interpretation.py    # CRUD cache interprétations Claude
│   ├── services/
│   │   ├── parser_csv.py        # Parsing + validation CSV uploadés
│   │   ├── parser_ofgl.py       # Parsing spécifique format OFGL
│   │   ├── scoring.py           # Calcul scores A–E
│   │   └── claude.py            # Appels API Claude + mise en cache
│   ├── routes/
│   │   ├── public.py            # Routes publiques : /, /thematique/<slug>
│   │   └── admin.py             # Routes admin : /admin, /admin/upload, /admin/saisie
│   └── templates/
│       ├── base.html
│       ├── public/
│       │   ├── dashboard.html
│       │   └── thematique.html
│       └── admin/
│           ├── login.html
│           ├── dashboard.html
│           ├── upload.html
│           └── saisie.html
├── data/
│   └── communesante.db
├── uploads/                     # CSV uploadés (temporaires)
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── seed.py                      # Initialisation du référentiel d'indicateurs
└── .env                         # ANTHROPIC_API_KEY, ADMIN_PASSWORD, SECRET_KEY
```

### 2.3 Docker Compose

```yaml
version: '3.8'
services:
  web:
    build: .
    restart: always
    ports:
      - "5001:5000"
    volumes:
      - ./data:/app/data
      - ./uploads:/app/uploads
    env_file: .env
```

### 2.4 Variables d'environnement (.env)

```
ANTHROPIC_API_KEY=sk-ant-...
ADMIN_PASSWORD=...
SECRET_KEY=...
FLASK_ENV=production
```

---

## 3. Modèle de données SQLite

```sql
-- Référentiel des indicateurs (initialisé par seed.py, jamais modifié par l'app)
CREATE TABLE indicateurs (
    id TEXT PRIMARY KEY,                        -- ex: 'fin_epargne_brute'
    thematique TEXT NOT NULL,                   -- 'finances', 'ecologie', 'social',
                                                --   'gouvernance', 'services', 'economie'
    libelle_citoyen TEXT NOT NULL,              -- "La commune met-elle de l'argent de côté ?"
    libelle_technique TEXT,                     -- "Taux d'épargne brute"
    unite TEXT,                                 -- '%', '€/hab', 'années', 'kg/hab/an', etc.
    sens_positif TEXT                           -- 'haut', 'bas', 'neutre'
        CHECK(sens_positif IN ('haut','bas','neutre')),
    seuil_vert REAL,                            -- valeur à partir de laquelle score = A ou B
    seuil_orange REAL,                          -- valeur à partir de laquelle score = C
    seuil_rouge REAL,                           -- valeur à partir de laquelle score = D ou E
    valeur_reference REAL,                      -- médiane nationale / seuil légal de référence
    libelle_reference TEXT,                     -- ex: "Médiane communes 5k–10k hab. (OFGL)"
    description TEXT,                           -- explication longue affichée au citoyen
    source_type TEXT                            -- 'csv_ofgl', 'csv_generique', 'saisie_manuelle'
        CHECK(source_type IN ('csv_ofgl','csv_generique','saisie_manuelle')),
    actif INTEGER DEFAULT 1
);

-- Données historiques
CREATE TABLE donnees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    indicateur_id TEXT NOT NULL REFERENCES indicateurs(id),
    annee INTEGER NOT NULL,
    valeur REAL,
    source TEXT,                                -- texte libre affiché publiquement
    commentaire TEXT,                           -- note interne admin (non affichée)
    date_saisie TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    mode_saisie TEXT CHECK(mode_saisie IN ('csv', 'manuel')),
    UNIQUE(indicateur_id, annee)
);

-- Cache des interprétations générées par Claude
CREATE TABLE interpretations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    indicateur_id TEXT NOT NULL REFERENCES indicateurs(id),
    annee INTEGER NOT NULL,
    score TEXT CHECK(score IN ('A','B','C','D','E')),
    phrase_courte TEXT,                         -- 1 phrase, affichée sur le dashboard
    phrase_longue TEXT,                         -- 2-3 phrases, affichées au détail
    date_generation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(indicateur_id, annee)
);

-- Log des imports CSV
CREATE TABLE imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fichier TEXT,
    thematique TEXT,
    nb_lignes_traitees INTEGER,
    nb_lignes_importees INTEGER,
    nb_erreurs INTEGER,
    rapport TEXT,                               -- JSON avec détail des erreurs ligne par ligne
    date_import TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    statut TEXT CHECK(statut IN ('succes','partiel','echec'))
);
```

---

## 4. Référentiel des indicateurs

Le script `seed.py` initialise ces indicateurs au premier lancement. Il ne les écrase pas s'ils existent déjà.

### 4.1 Finances publiques (`thematique = 'finances'`)

| ID | Libellé citoyen | Unité | Sens | Source type |
|----|----------------|-------|------|-------------|
| `fin_epargne_brute` | La commune met-elle de l'argent de côté ? | % recettes | haut | csv_ofgl |
| `fin_dette_habitant` | Combien la commune doit-elle par habitant ? | €/hab | bas | csv_ofgl |
| `fin_capacite_desendettement` | En combien d'années pourrait-elle rembourser sa dette ? | années | bas | csv_ofgl |
| `fin_investissement_habitant` | Combien investit-on par habitant chaque année ? | €/hab | haut | csv_ofgl |
| `fin_rigidite_charges` | Quelle part du budget est impossible à réduire ? | % | bas | csv_ofgl |
| `fin_taux_taxe_fonciere` | La taxe foncière a-t-elle augmenté ? | % | bas | saisie_manuelle |
| `fin_masse_salariale_ratio` | Quelle part du budget part aux salaires ? | % dép. fonct. | bas | csv_ofgl |

### 4.2 Écologie & environnement (`thematique = 'ecologie'`)

| ID | Libellé citoyen | Unité | Sens | Source type |
|----|----------------|-------|------|-------------|
| `eco_espaces_verts_habitant` | Surface d'espaces verts par habitant | m²/hab | haut | saisie_manuelle |
| `eco_fluides_global` | Dépenses eau + énergie des bâtiments publics | €/an | bas | csv_generique |
| `eco_dpe_batiments` | Note énergétique moyenne des bâtiments communaux | score 1–7 | haut | csv_generique |
| `eco_dechets_habitant` | Déchets produits par habitant | kg/hab/an | bas | csv_generique |
| `eco_taux_tri` | Taux de tri sélectif | % | haut | csv_generique |
| `eco_part_bio_cantine` | Part du bio et local à la cantine | % | haut | saisie_manuelle |
| `eco_arbres_plantes` | Arbres plantés depuis le début de la mandature | nb | haut | saisie_manuelle |

### 4.3 Social & cohésion (`thematique = 'social'`)

| ID | Libellé citoyen | Unité | Sens | Source type |
|----|----------------|-------|------|-------------|
| `soc_logements_sociaux_taux` | Part de logements sociaux (seuil légal SRU : 25%) | % | haut | saisie_manuelle |
| `soc_places_creche_attente` | Enfants en liste d'attente en crèche | nb | bas | saisie_manuelle |
| `soc_tarif_cantine_evolution` | Évolution du tarif cantine (quotient médian) | €/repas | bas | saisie_manuelle |
| `soc_associations_nb` | Nombre d'associations actives | nb | haut | saisie_manuelle |
| `soc_subventions_associations` | Budget alloué aux associations | €/an | haut | csv_generique |
| `soc_participation_citoyenne` | Réunions publiques organisées par an | nb/an | haut | saisie_manuelle |
| `soc_budget_jeunesse_habitant` | Budget jeunesse et animation par habitant | €/hab | haut | csv_generique |

### 4.4 Gouvernance & transparence (`thematique = 'gouvernance'`)

| ID | Libellé citoyen | Unité | Sens | Source type |
|----|----------------|-------|------|-------------|
| `gouv_taux_presence_conseil` | Taux de présence moyen au conseil municipal | % | haut | saisie_manuelle |
| `gouv_delai_publication_pv` | Délai moyen de publication des PV (légal : 8 jours) | jours | bas | saisie_manuelle |
| `gouv_deliberations_unanimes` | Part des délibérations votées à l'unanimité | % | neutre | saisie_manuelle |
| `gouv_reponses_questions_ecrites` | Taux de réponse aux questions de l'opposition | % | haut | saisie_manuelle |
| `gouv_seances_par_an` | Séances du conseil par an (minimum légal : 4) | nb | haut | saisie_manuelle |
| `gouv_decisions_delegation_maire` | Décisions prises par délégation du maire | nb/an | neutre | saisie_manuelle |

### 4.5 Services publics & patrimoine (`thematique = 'services'`)

| ID | Libellé citoyen | Unité | Sens | Source type |
|----|----------------|-------|------|-------------|
| `serv_etat_patrimoine_score` | État général des bâtiments publics | score 1–5 | haut | saisie_manuelle |
| `serv_accessibilite_pmr` | Équipements accessibles aux personnes handicapées | % | haut | saisie_manuelle |
| `serv_horaires_mairie` | Heures d'ouverture de la mairie par semaine | h/sem | haut | saisie_manuelle |
| `serv_delai_urbanisme` | Délai moyen d'instruction des permis de construire | jours | bas | saisie_manuelle |
| `serv_demarches_en_ligne` | Part des démarches disponibles en ligne | % | haut | saisie_manuelle |

### 4.6 Vitalité économique (`thematique = 'economie'`)

| ID | Libellé citoyen | Unité | Sens | Source type |
|----|----------------|-------|------|-------------|
| `eco2_nb_commerces` | Nombre de commerces et services de proximité | nb | haut | csv_generique |
| `eco2_evolution_entreprises` | Évolution du nombre d'entreprises actives | nb | haut | csv_generique |
| `eco2_taux_vacance_commerciale` | Part des locaux commerciaux vides | % | bas | saisie_manuelle |
| `eco2_marches_evenements` | Marchés et événements économiques par an | nb/an | haut | saisie_manuelle |
| `eco2_emplois_commune` | Évolution des emplois sur la commune | nb | haut | csv_generique |

---

## 5. Alimentation des données

### 5.1 Upload CSV

#### Format OFGL (finances uniquement)

Export brut depuis ofgl.fr > Données > Comptes de gestion, filtré sur Sautron (code commune 44202).

```
code_commune;libelle_commune;annee;libelle_compte;montant
44202;Sautron;2023;Épargne brute;1250000
44202;Sautron;2023;Encours de dette;8400000
```

Le parser `parser_ofgl.py` mappe les libellés OFGL vers les `indicateur_id` de l'application via un dictionnaire de correspondance maintenu dans le code.

#### Format générique (toutes thématiques)

Format CSV simple, documenté dans l'interface admin, utilisable pour n'importe quel indicateur.

```
annee,indicateur_id,valeur,source
2024,eco_part_bio_cantine,42,Rapport DRAAF Pays de la Loire 2024
2024,soc_logements_sociaux_taux,18.3,Bilan SRU préfecture Loire-Atlantique 2024
2023,eco_taux_tri,68.4,Rapport annuel Nantes Métropole 2023
```

#### Workflow upload

1. Sélection du fichier + sélection du format (OFGL ou générique)
2. Parsing + validation (colonnes requises, types, cohérence des années)
3. **Aperçu obligatoire** : tableau des données parsées avec erreurs signalées ligne par ligne
4. Confirmation par l'admin → import en base
5. Déclenchement automatique de la génération des interprétations Claude pour les indicateurs mis à jour
6. Rapport d'import affiché (nb importés, nb ignorés, nb erreurs)

### 5.2 Saisie manuelle

Interface formulaire dans l'admin pour saisir un indicateur à la fois :

- Sélection de l'indicateur (liste déroulante groupée par thématique)
- Champ année
- Champ valeur (numérique)
- Champ source (texte libre, affiché publiquement)
- Champ commentaire interne (texte libre, non affiché)
- Bouton "Enregistrer et générer l'interprétation"

---

## 6. Interprétations via API Claude

### 6.1 Principe

Les interprétations sont générées **à l'import ou à la saisie**, pas à l'affichage. Résultats mis en cache dans la table `interpretations`. Un bouton "Regénérer" dans l'admin permet de forcer un nouvel appel sans re-saisir la donnée.

### 6.2 Prompt système

```
Tu es un expert en politiques publiques locales françaises, spécialisé dans
l'analyse des communes de taille moyenne (5 000 à 20 000 habitants).
Tu génères des interprétations factuelles et pédagogiques d'indicateurs
municipaux pour des citoyens non experts. Ton ton est neutre, honnête et
bienveillant. Tu ne portes aucun jugement politique. Tu contextualises
systématiquement avec des références nationales ou légales quand elles existent.
Tu réponds UNIQUEMENT en JSON valide, sans markdown, sans texte avant ou après,
avec exactement ces trois clés : "score", "phrase_courte", "phrase_longue".
- score : une lettre parmi A, B, C, D, E
- phrase_courte : une seule phrase, maximum 120 caractères
- phrase_longue : 2 à 3 phrases, maximum 400 caractères au total
```

### 6.3 Prompt utilisateur (template)

```
Commune : Sautron (Loire-Atlantique, ~8 600 habitants, périurbain Nantes)
Indicateur : {libelle_citoyen}
Identifiant technique : {id}
Unité : {unite}
Sens de lecture : une valeur {sens} est meilleure
Valeur {annee} : {valeur} {unite}
Valeur {annee - 1} : {valeur_n1} {unite}  [si disponible, sinon omettre]
Référence nationale / seuil légal : {valeur_reference} {unite} ({libelle_reference})
Description de l'indicateur : {description}
Génère l'interprétation citoyenne.
```

### 6.4 Exemple de réponse attendue

```json
{
  "score": "C",
  "phrase_courte": "La cantine progresse mais reste sous l'obligation légale.",
  "phrase_longue": "Avec 42% de produits bio ou locaux, Sautron dépasse la moyenne nationale (30%), mais n'atteint pas encore les 50% exigés par la loi EGAlim de 2022. La progression depuis 2023 (35%) est encourageante et mérite d'être confirmée."
}
```

### 6.5 Gestion des erreurs API

- En cas d'échec de l'appel Claude : score et phrases laissés à NULL, indicateur affiché sans interprétation avec mention "Interprétation en cours de génération"
- Retry automatique une fois après 5 secondes
- Log de l'erreur dans la table `imports`

---

## 7. Scoring A–E

### Calcul par indicateur

Le score est calculé dans `scoring.py` à partir des seuils définis dans `indicateurs` :

```python
def calculer_score(valeur, seuil_vert, seuil_orange, seuil_rouge, sens):
    """
    sens = 'haut' : plus la valeur est haute, mieux c'est
    sens = 'bas'  : plus la valeur est basse, mieux c'est
    sens = 'neutre' : pas de score calculé automatiquement → Claude décide
    """
```

| Score | Couleur hex | Signification |
|-------|-------------|---------------|
| A | `#16a34a` | Très satisfaisant |
| B | `#65a30d` | Satisfaisant |
| C | `#d97706` | À surveiller |
| D | `#dc2626` | Préoccupant |
| E | `#7f1d1d` | Critique |

### Agrégation par thématique

Score thématique = moyenne des scores des indicateurs renseignés de la thématique (A=5, B=4, C=3, D=2, E=1), reconverti en lettre.

**Règle** : une thématique n'affiche de score que si au moins **3 indicateurs** sont renseignés pour l'année la plus récente.

### Score global commune

Moyenne pondérée des scores thématiques :

| Thématique | Pondération |
|-----------|-------------|
| Finances | 25% |
| Écologie | 20% |
| Social | 20% |
| Gouvernance | 15% |
| Services | 10% |
| Économie | 10% |

---

## 8. Interface publique

### Route `/` — Tableau de bord principal

**En-tête**
- Nom : "CommuneSanté — Sautron"
- Sous-titre : "Observatoire citoyen de la commune de Sautron (Loire-Atlantique)"
- Dernière mise à jour des données (date du dernier import)

**Score global**
- Jauge visuelle circulaire (SVG) avec la lettre du score global
- Phrase d'introduction générée automatiquement

**Grille des 6 thématiques**

Chaque carte affiche :
- Icône + nom de la thématique
- Score thématique (lettre + couleur)
- 3 indicateurs clés : libellé citoyen + valeur + flèche tendance (↗ ↘ →)
- Lien "Voir le détail →"
- Si moins de 3 indicateurs renseignés : mention "Données insuffisantes"

**Pied de page**
- Mention de la source des données et de la méthode
- Lien vers le code source (si open source)
- "Une donnée vous semble incorrecte ? Contactez-nous."

---

### Route `/thematique/<slug>` — Détail d'une thématique

**En-tête thématique**
- Nom + score + phrase courte d'interprétation

**Liste de tous les indicateurs de la thématique**

Pour chaque indicateur renseigné :
- Libellé citoyen (grand) + libellé technique (petit, gris)
- Valeur actuelle + année + unité
- Tendance vs année précédente (valeur absolue + % d'évolution)
- Valeur de référence nationale avec son libellé
- Score (badge coloré A–E)
- Phrase courte d'interprétation
- Graphique d'évolution sur les années disponibles (Chart.js, barres ou ligne)
- Phrase longue d'interprétation
- Source de la donnée (texte, affiché en italique)
- Bouton "En savoir plus" → modal avec `description` de l'indicateur

Pour chaque indicateur **non renseigné** :
- Libellé citoyen (grisé)
- Badge gris "Donnée non disponible"
- Mention : "Cette donnée n'est pas encore disponible. Elle sera mise à jour dès que possible."

---

## 9. Interface d'administration

### Route `/admin/login`

Formulaire login/password simple. Password défini dans `.env`. Session Flask.

### Route `/admin` — Dashboard admin

- Vue d'ensemble : nb d'indicateurs renseignés par thématique / nb total
- Tableau de tous les indicateurs avec : dernière valeur connue, année, date de saisie, score, statut interprétation Claude
- Boutons d'action rapide : "Saisir une valeur" / "Uploader un CSV" / "Regénérer les interprétations"

### Route `/admin/upload`

- Formulaire upload CSV
- Sélecteur de format (OFGL / Générique)
- Zone de drag & drop
- Aperçu des données parsées avant import
- Rapport d'import après confirmation

### Route `/admin/saisie`

- Formulaire de saisie manuelle (un indicateur à la fois)
- Sélecteur d'indicateur groupé par thématique
- Champs : année, valeur, source (public), commentaire (interne)
- Bouton "Enregistrer et générer l'interprétation Claude"
- Historique des saisies récentes en bas de page

---

## 10. Priorités de développement

### Phase 1 — Fondations (livrer en premier)

1. Structure Flask + SQLite + Docker opérationnelle
2. Script `seed.py` : initialise les ~40 indicateurs en base
3. Auth admin simple (session Flask, password en `.env`)
4. Saisie manuelle d'un indicateur (formulaire admin + stockage)
5. Affichage public minimal : dashboard + liste des indicateurs par thématique (sans graphiques ni scores)

### Phase 2 — Données & scoring

6. Upload CSV format générique avec validation + aperçu
7. Upload CSV format OFGL avec mapping automatique
8. Calcul des scores A–E (logique `scoring.py`)
9. Agrégation thématique + score global
10. Affichage des scores et tendances sur le dashboard public

### Phase 3 — Intelligence & polish

11. Intégration API Claude (génération interprétations)
12. Cache des interprétations + bouton "Regénérer"
13. Graphiques Chart.js sur les pages de détail thématique
14. Gestion des indicateurs non renseignés (badges, messages)
15. Page de détail thématique complète

---

## 11. Points d'attention pour Claude Code

- **Neutralité des interprétations** : le prompt Claude doit explicitement interdire tout jugement politique. Les phrases générées décrivent des faits, pas des responsabilités.
- **Traçabilité obligatoire** : aucune valeur ne s'affiche publiquement sans son champ `source` renseigné. Si source est vide, afficher "Source non renseignée" mais ne pas bloquer l'affichage.
- **Pas d'ORM** : requêtes SQLite directes via `sqlite3`, avec des fonctions utilitaires dans `database.py`. Pas de SQLAlchemy.
- **Pas de framework JS** : Jinja2 + JS vanilla + Chart.js CDN uniquement. Pas de React, pas de Vue.
- **Gestion des données manquantes** : ne jamais afficher `None`, `null` ou une cellule vide à l'utilisateur. Toujours une mention explicite ("Donnée non disponible").
- **Idempotence des imports** : un deuxième upload du même CSV pour la même année doit écraser les valeurs existantes sans créer de doublons (contrainte UNIQUE sur `indicateur_id + annee`).
- **Séparation stricte public/admin** : les routes `/admin/*` vérifient la session à chaque requête via un décorateur `@login_required`. Aucune donnée d'admin ne fuite dans les templates publics.
