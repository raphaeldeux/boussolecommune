# Indicateurs automatiques INSEE — Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatiser l'import de données démographiques, économiques et de logement depuis les APIs INSEE (RP, SIRENE, BPE) avec validation humaine avant enregistrement.

**Approach:** Approche A — APIs INSEE directes. Trois nouveaux fetchers, intégration dans la page Import existante, étape de prévisualisation/validation avant commit en base.

---

## Architecture

### Fichiers créés
- `app/services/fetchers/insee_rp.py` — Recensement de la Population via `api-stat-v2.insee.fr`
- `app/services/fetchers/sirene.py` — Entreprises et associations via API SIRENE v3
- `app/services/fetchers/bpe.py` — Commerces et services via fichier BPE data.gouv.fr (CSV annuel)

### Fichiers modifiés
- `app/routes/admin.py` — 3 nouvelles routes fetch + 3 routes de validation
- `app/templates/admin/upload.html` — 3 nouvelles cartes dans "Sources automatiques"
- `app/templates/admin/upload_preview.html` — nouvelle page de prévisualisation/validation (créée)
- `seed.py` — nouveaux indicateurs RP + mise à jour `source_type` des indicateurs existants

### Flux par fetcher (identique pour les 3)
1. Admin clique "Récupérer" → POST `/admin/fetch/<source>`
2. Le fetcher appelle l'API externe, construit une liste de `{indicateur_id, annee, valeur, source}`
3. Redirect vers `/admin/fetch/<source>/preview` avec les données en session
4. Admin voit la prévisualisation des valeurs et clique "Valider et enregistrer"
5. POST `/admin/fetch/<source>/confirm` → `donnee.upsert()` pour chaque ligne + flash confirmation
6. Pour INSEE RP uniquement : les tranches d'âge alimentent aussi `pyramide.upsert_year()`

### Stockage
- Données indicateurs → table `donnees` via `donnee.upsert()` (pattern existant)
- Pyramide des âges → table `pyramide_ages` via `pyramide.upsert_year()` (INSEE RP uniquement)
- Les données de prévisualisation transitent en session Flask (pas de table intermédiaire)
- Le `ville_id` n'est **pas** stocké dans la session : lors du confirm, il est récupéré via `_get_current_ville()` et passé à chaque `donnee.upsert()`

---

## Nouveaux indicateurs (seed.py)

### RP — Population
| id | libelle_technique | unité | thématique |
|----|-------------------|-------|------------|
| `pop_total` | Population municipale | hab | portrait |
| `pop_evolution_10ans` | Évolution de la population sur 10 ans | % | portrait |
| `pop_menages_solo` | Part des ménages d'une personne | % | lien_social |
| `pop_taille_menages` | Taille moyenne des ménages | pers/ménage | portrait |

### RP — Logement
| id | libelle_technique | unité | thématique |
|----|-------------------|-------|------------|
| `log_vacants_taux` | Taux de logements vacants | % | cadre_vie |
| `log_residences_secondaires_taux` | Part des résidences secondaires | % | portrait |
| `log_proprietaires_taux` | Part des ménages propriétaires | % | portrait |
| `log_anciennete_avant1946` | Part du parc construit avant 1946 | % | cadre_vie |
| `log_anciennete_1946_1990` | Part du parc construit entre 1946 et 1990 | % | cadre_vie |
| `log_anciennete_post1990` | Part du parc construit après 1990 | % | cadre_vie |

### RP — Emploi
| id | libelle_technique | unité | thématique |
|----|-------------------|-------|------------|
| `eco_emplois_actifs_ratio` | Rapport emplois sur commune / actifs résidents | ratio | finances |

### RP — Âges (7 tranches — alimentent aussi la pyramide)
| id | libelle_technique | unité | thématique |
|----|-------------------|-------|------------|
| `pop_age_0_14` | Part des 0–14 ans | % | portrait |
| `pop_age_15_29` | Part des 15–29 ans | % | portrait |
| `pop_age_30_44` | Part des 30–44 ans | % | portrait |
| `pop_age_45_59` | Part des 45–59 ans | % | portrait |
| `pop_age_60_74` | Part des 60–74 ans | % | portrait |
| `pop_age_75_89` | Part des 75–89 ans | % | portrait |
| `pop_age_90_plus` | Part des 90 ans et plus | % | portrait |

Note : ces 7 tranches correspondent exactement aux tranches du modèle `pyramide_ages` existant (`"0-14"`, `"15-29"`, `"30-44"`, `"45-59"`, `"60-74"`, `"75-89"`, `"90+"`). Le fetcher RP récupère hommes + femmes séparément pour la pyramide, et calcule le pourcentage total pour l'indicateur.

### Indicateurs existants — changement de source_type
| id | ancienne source | nouvelle source |
|----|----------------|----------------|
| `eco2_nb_commerces` | csv_generique | api_bpe |
| `eco2_evolution_entreprises` | csv_generique | api_sirene |
| `eco2_emplois_commune` | csv_generique | api_insee_rp |
| `soc_associations_nb` | saisie_manuelle | api_sirene |

---

## User Stories

### US-1 — Fetcher INSEE RP
**En tant qu'admin**, je clique "Récupérer" sur la carte INSEE RP dans la page Import.

L'app interroge `api-stat-v2.insee.fr` avec le code INSEE de ma commune et récupère :
- Population totale + évolution 10 ans
- Structure par âge en 6 tranches (hommes + femmes pour la pyramide)
- Ménages (nombre solo + taille moyenne)
- Logements (vacants, secondaires, propriétaires, ancienneté)
- Emplois sur commune + actifs résidents

Je suis redirigé vers une page de **prévisualisation** listant les valeurs récupérées par indicateur et par année. Je clique "Valider et enregistrer" pour confirmer l'import.

**Critères d'acceptation :**
- Désactivé si `ville.code_insee` est absent
- Prévisualisation affiche : indicateur / année / valeur / unité
- Bouton "Annuler" retourne à la page Import sans rien enregistrer
- Après confirmation : flash "X valeurs importées depuis l'INSEE RP"
- Les tranches d'âge alimentent aussi `pyramide_ages` via `pyramide.upsert_year()`

### US-2 — Fetcher SIRENE
**En tant qu'admin**, je clique "Récupérer" sur la carte SIRENE.

L'app interroge l'API SIRENE v3 avec le code INSEE et calcule :
- Stock d'entreprises actives (hors associations) : `GET https://api.insee.fr/entreprises/sirene/V3/siret?q=etablissementSiege:true+AND+etatAdministratifEtablissement:A+AND+codePostalEtablissement:<code_insee_depart>` avec filtrage sur catégorie juridique ≠ 92xx
- Nombre d'associations actives : même endpoint, catégorie juridique filtrée sur `92*`
- Année retournée = année civile en cours

Prévisualisation → validation → enregistrement.

**Critères d'acceptation :**
- Clé API SIRENE configurée via variable d'env `SIRENE_API_KEY` (inscription gratuite sur api.insee.fr), Bearer token OAuth2
- Si la clé est absente, la carte affiche "Clé API manquante" en lieu du bouton
- Prévisualisation + confirmation avant enregistrement
- Si API timeout ou erreur HTTP : flash d'erreur, redirect vers page Import
- SIRENE n'alimente pas `pyramide_ages`

### US-3 — Fetcher BPE
**En tant qu'admin**, je clique "Récupérer" sur la carte BPE.

L'app télécharge le fichier BPE annuel depuis data.gouv.fr (dataset "Base permanente des équipements"), filtre par code INSEE de la commune et compte les établissements de commerce et services de proximité pour alimenter l'indicateur `eco2_nb_commerces`.

Dataset : `https://www.data.gouv.fr/fr/datasets/base-permanente-des-equipements/`
Fichier : `bpe<annee>_ensemble.csv.gz` (mis à jour annuellement, ~200 Mo compressé)
Catégories BPE retenues pour `eco2_nb_commerces` : types `A1` (hypermarché), `A2` (supermarché), `A3` (épicerie/supérette), `A4` (boucherie), `A5` (boulangerie), `B1-B9` (services aux personnes), `C1` (médecin), `C5` (pharmacie), `D1-D9` (enseignement), `F` (sport/loisirs).

Prévisualisation → validation → enregistrement.

**Critères d'acceptation :**
- Téléchargement du fichier CSV BPE (URL publique, pas d'auth)
- Filtrage sur le code INSEE communal (colonne `DEPCOM`)
- Agrégation par catégories définies ci-dessus
- Prévisualisation + confirmation avant enregistrement
- Si téléchargement échoue : flash d'erreur, redirect vers page Import
- BPE n'alimente pas `pyramide_ages`

### US-4 — Nouveaux indicateurs RP dans le référentiel
**En tant qu'admin**, les nouveaux indicateurs démographiques et de logement sont présents dans le référentiel après `python seed.py` et s'affichent dans le tableau de bord citoyen une fois les données importées.

**Critères d'acceptation :**
- `seed.py` idempotent : n'écrase pas les données existantes
- Les indicateurs ont des seuils et libellés citoyens pertinents
- Les indicateurs de portrait s'affichent dans la section portrait du dashboard

### US-5 — Pyramide des âges automatique
**En tant qu'admin**, après validation d'un import INSEE RP, la pyramide des âges de ma commune est automatiquement mise à jour avec les données de l'année importée.

**Critères d'acceptation :**
- Les 6 tranches (hommes + femmes) sont stockées dans `pyramide_ages`
- L'année de la pyramide correspond à l'année du recensement importé
- La visualisation pyramide existante affiche les nouvelles données sans modification du frontend

---

## Page de prévisualisation (upload_preview.html)

Template partagé par les 3 fetchers. Reçoit en contexte :
- `source` : nom de la source ("INSEE RP", "SIRENE", "BPE")
- `lignes` : liste de `{indicateur_id, libelle, annee, valeur, unite}`
- `erreurs` : liste de messages d'erreur non-bloquants
- `confirm_url` : URL du POST de confirmation

Affiche :
- Tableau des valeurs récupérées
- Avertissements non-bloquants (ex. "Données 2021 — dernier recensement disponible")
- Bouton "Valider et enregistrer" + lien "Annuler"

---

## Variables d'environnement

```
SIRENE_API_KEY    Clé API SIRENE (gratuit sur api.insee.fr) — optionnel
```

Les APIs INSEE RP et BPE data.gouv.fr ne nécessitent pas d'authentification.

---

## Hors scope

- Filosofi (revenus, pauvreté) — reporté
- Mise à jour automatique planifiée (cron) — reporté
- Gestion multi-années avancée (l'import écrase la valeur existante via upsert)
