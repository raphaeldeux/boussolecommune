# ZAN — Source automatique artificialisation des sols

## Goal

Ajouter une source automatique ZAN (Zéro Artificialisation Nette) dans la page import admin, suivant le même pattern fetch→preview→confirm que les sources SRU, OFGL et ma-cantine.

## Architecture

Fetcher `app/services/fetchers/zan.py` qui streame le CSV commune Cerema (170 Mo, 33 Mo gzip), filtre les lignes de la commune par `geocode_commune == code_insee`, agrège par année, et calcule le quota ZAN. Route admin `fetch_zan` stocke le preview en session. Route `confirm_zan` importe en base. Carte dans la section "En fonctionnement" de `upload.html`.

## Tech Stack

Flask 3.0 · PostgreSQL 16 · psycopg2 · requests (stream=True) · Jinja2

---

## Data Source

**URL :** `https://static.data.gouv.fr/resources/consommation-despaces-naturels-agricoles-et-forestiers/20260128-170657/consommation-d-espaces-naturels-agricoles-et-forestiers-commune.csv`

**Format :** CSV, colonnes : `date_mesure, geocode_commune, libelle_commune, secteur, valeur`

- `date_mesure` : ISO date (ex. `2011-01-01T00:00:00.000`) — consommation pendant l'année
- `geocode_commune` : code INSEE
- `secteur` : `Habitat`, `Activité`, `Route`, `Mixte`, `Fer`, `Inconnu`
- `valeur` : hectares consommés (float)

**Couverture :** France entière, 2009–2023, ~3 M lignes

**Taille :** 170 Mo non compressé, 33 Mo gzip — streaming avec `requests(stream=True, decode_content=True)` + `Accept-Encoding: gzip`, durée ~15-20 s pour une commune

**Licence :** Open Licence v2.0

**Source officielle :** Cerema — Fichiers Fonciers (MAJIC / DGFIP)

---

## Indicators

### `zan_conso_enaf_annuelle`

| Champ | Valeur |
|---|---|
| thematique | vivant |
| libelle_citoyen | Combien d'hectares de terres naturelles ou agricoles ont été artificialisés ? |
| unite | ha/an |
| sens_positif | bas |
| seuil_vert | 1.0 |
| seuil_orange | 3.0 |
| seuil_rouge | 6.0 |
| source_type | api_cerema |

Stocké : une ligne dans `donnees` par année (2009–2023). Valeur = somme de tous les secteurs pour l'année. Le champ `source` contient le détail par secteur (ex. `Habitat: 4.58 ha, Route: 1.36 ha`).

### `zan_quota_restant_2031`

| Champ | Valeur |
|---|---|
| thematique | vivant |
| libelle_citoyen | Combien d'hectares d'artificialisation reste-t-il d'ici 2031 (objectif loi ZAN) ? |
| unite | ha |
| sens_positif | haut |
| seuil_vert | 5.0 |
| seuil_orange | 2.0 |
| seuil_rouge | 0.0 |
| source_type | api_cerema |

Stocké : une seule ligne dans `donnees` pour l'année de la dernière donnée disponible (ex. 2023). Valeur = quota_2021_2031 - consommation_depuis_2021.

**Calcul du quota :**
- `baseline` = somme des consommations 2011–2020 (10 ans)
- `quota_2021_2031` = `baseline / 2` (objectif : diviser par 2 la consommation vs la décennie précédente)
- `consommation_depuis_2021` = somme des consommations 2021, 2022, 2023…
- `quota_restant` = `quota_2021_2031 - consommation_depuis_2021`

**Pour Sautron (44194) :**
- Baseline 2011–2020 : 18.30 ha → Quota 2021–2031 : 9.15 ha
- Consommé depuis 2021 : 1.89 ha → Restant : 7.25 ha

---

## Fetcher (`app/services/fetchers/zan.py`)

```python
def fetch_zan_data(code_insee: str) -> dict:
    """
    Retourne :
    {
        "ok": True,
        "lignes": [{"indicateur_id", "annee", "valeur", "source"}],
        "annees": [int],
        "quota_restant": float,
        "quota_total": float,
        "erreurs": [str],
    }
    ou {"ok": False, "error": str}
    """
```

Interne :
1. `requests.get(URL, stream=True, headers={"Accept-Encoding": "gzip"}, timeout=90)`
2. `resp.iter_lines()` → parse CSV ligne par ligne
3. Collect rows where `geocode_commune == code_insee`
4. Agrège par année : `{annee: {secteur: valeur}}`
5. Calcule `zan_conso_enaf_annuelle` par année (total + source = détail secteurs)
6. Calcule `zan_quota_restant_2031` (valeur unique, annee = dernière année disponible)
7. Retourne le dict

---

## Admin Routes (dans `app/routes/admin.py`)

### `POST /upload/fetch-zan`

- Vérifie `ville.code_insee`
- Appelle `fetch_zan_data(code_insee)`
- Stocke `session["zan_preview"] = json.dumps(result)`
- Flash + redirect vers upload

### `POST /upload/confirm-zan`

- Lit `session.pop("zan_preview")`
- Insère dans `donnees` avec `mode_saisie = 'api'` et `ON CONFLICT DO NOTHING` (ou DO UPDATE si force)
- Enregistre dans `imports`
- Flash + redirect

### `POST /upload/cancel-preview/zan`

- Géré par la route générique `cancel_preview` — **ajouter `"zan": "zan_preview"` dans le `key_map`** de cette route (actuellement seulement mc, ofgl, sru)

---

## Template (`app/templates/admin/upload.html`)

### Carte source active

Dans la grille "En fonctionnement" (même style que ma-cantine, OFGL, SRU) :

```
🌱 ZAN / Cerema
   Artificialisation ENAF (2009–2023)
   [Récupérer]
```

### Section prévisualisation

Après les autres previews, avant la section CSV. Affiche :
- Tableau : Année | Total (ha) | Détail secteurs
- Encart récapitulatif ZAN : Quota 2021–2031 / Déjà consommé / Restant
- Checkbox "Forcer la mise à jour (écraser les données existantes)" — même comportement que les autres previews
- Boutons "Confirmer l'import" et "Annuler"

---

## Seed (`seed.py`)

Deux nouveaux indicateurs ajoutés au tableau `INDICATEURS` avec `source_type = 'api_cerema'`.

## Database (`app/database.py`)

Ajouter `'api_cerema'` à la contrainte CHECK sur `source_type` dans la table `indicateurs` :
- Modifier la ligne `source_type TEXT CHECK(source_type IN (...))` dans `init_db()`
- Ajouter une migration `ALTER TABLE indicateurs DROP CONSTRAINT ... ADD CONSTRAINT ...` pour la base live

---

## Error handling

- Commune absente du fichier → `{"ok": False, "error": "Commune non couverte par les Fichiers Fonciers"}`
- Timeout (90 s) → `{"ok": False, "error": "Délai dépassé lors du téléchargement"}`
- Erreur réseau → `{"ok": False, "error": "..."}`

---

## Out of scope

- Breakdown par secteur comme indicateurs séparés (Habitat, Activité, Route…) — le détail est dans le champ `source` de chaque ligne
- Historique antérieur à 2009
- Calcul du taux d'artificialisation (%) — nécessite la surface communale totale, non disponible dans ce dataset
