# Migration INSEE RP vers l'API Melodi — Design

**Goal:** Remplacer le fetcher `insee_rp.py` (API Données locales, OAuth2) par l'API Melodi d'INSEE (open, pas de clé), et adapter les indicateurs d'âge aux tranches Melodi.

**Approach:** Réécriture complète de `app/services/fetchers/insee_rp.py`. Suppression de l'OAuth2. Les 7 indicateurs d'âge sont renommés pour correspondre aux tranches natives de Melodi. SIRENE ne change pas.

---

## Architecture

### Fichiers modifiés

| Fichier | Action |
|---------|--------|
| `app/services/fetchers/insee_rp.py` | Réécriture complète — Melodi, pas d'OAuth2 |
| `app/routes/admin.py` | Supprimer `api_key=ville.get("insee_api_key")` dans `fetch_insee_rp()` |
| `seed.py` | Renommer les 7 indicateurs d'âge |
| `app/database.py` | Migration : renommer les indicateurs + suppression données orphelines |
| `app/templates/admin/integrations.html` | "INSEE API Key" → "Clé API SIRENE" |
| `app/templates/admin/modifier_ville.html` | Idem |

### Fichiers inchangés

- `app/services/fetchers/sirene.py` — reste sur OAuth2 + INSEE_API_KEY
- `app/models/ville.py` — `update_api_keys()` inchangé
- `app/routes/admin.py` (autres routes) — `fetch_sirene` continue de passer `api_key`

---

## API Melodi

**Base URL :** `https://api.insee.fr/melodi`

**Authentification :** aucune (open data)

**Format de requête :**
```
GET /data/{dataset}?GEO=COM-{code_insee}&TIME_PERIOD={annee}&maxResult=1000
```

**Format de réponse :**
```json
{
  "observations": [
    {
      "dimensions": {
        "GEO": {"id": "2025-COM-44202"},
        "SEX": {"id": "_T"},
        "AGE": {"id": "Y_LT15"},
        "TIME_PERIOD": {"id": "2022"}
      },
      "measures": {
        "OBS_VALUE_NIVEAU": {"value": 1820.0}
      }
    }
  ]
}
```

**Helper interne :**
```python
def _get_melodi(dataset: str, code_insee: str, extra_params: dict = None) -> list[dict]:
    """Appelle Melodi et retourne la liste d'observations."""
    params = {"GEO": f"COM-{code_insee}", "maxResult": 1000}
    if extra_params:
        params.update(extra_params)
    resp = requests.get(f"{MELODI_URL}/data/{dataset}", params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json().get("observations", [])

def _obs_value(obs: dict) -> float | None:
    """Extrait OBS_VALUE_NIVEAU.value d'une observation."""
    try:
        return obs["measures"]["OBS_VALUE_NIVEAU"]["value"]
    except (KeyError, TypeError):
        return None

def _filter_obs(obs_list, **dims) -> list[dict]:
    """Filtre les observations selon les dimensions données."""
    result = []
    for obs in obs_list:
        if all(obs["dimensions"].get(k, {}).get("id") == v for k, v in dims.items()):
            result.append(obs)
    return result
```

---

## Datasets et indicateurs

### DS_RP_POPULATION_PRINC

Filtre de base : `TIME_PERIOD=2022`

| Indicateur | Filtre | Valeur |
|---|---|---|
| pop_total | SEX=_T, AGE=_T | OBS_VALUE_NIVEAU |
| pop_evolution_10ans | SEX=_T, AGE=_T, TIME_PERIOD=2012 | `(2022 - 2012) / 2012 * 100` |
| pop_age_lt15 | SEX=_T, AGE=Y_LT15 | % de pop_total |
| pop_age_15_24 | SEX=_T, AGE=Y15T24 | % de pop_total |
| pop_age_25_39 | SEX=_T, AGE=Y25T39 | % de pop_total |
| pop_age_40_54 | SEX=_T, AGE=Y40T54 | % de pop_total |
| pop_age_55_64 | SEX=_T, AGE=Y55T64 | % de pop_total |
| pop_age_65_79 | SEX=_T, AGE=Y65T79 | % de pop_total |
| pop_age_ge80 | SEX=_T, AGE=Y_GE80 | % de pop_total |

**Pyramide :** pour chaque tranche, récupérer SEX=M et SEX=F séparément.

### DS_RP_LOGEMENT_PRINC

Filtre de base : `TIME_PERIOD=2022`

| Indicateur | Filtre | Calcul |
|---|---|---|
| log_vacants_taux | OCS=DW_VAC et OCS=_T | DW_VAC / _T * 100 |
| log_residences_secondaires_taux | OCS=DW_SEC_DW_OCC et OCS=_T | DW_SEC_DW_OCC / _T * 100 |
| log_proprietaires_taux | TSH=? | codes à vérifier |
| log_anciennete_avant1946 | BUILD_END=codes 1919 et avant | % du total |
| log_anciennete_1946_1990 | BUILD_END=codes 1946–1990 | % du total |
| log_anciennete_post1990 | BUILD_END=codes post 1990 | % du total |

> **Note implémentation :** Les codes exacts de TSH (tenure/statut d'occupation) et BUILD_END (période de construction) doivent être découverts en inspectant les observations réelles lors de l'implémentation. Le fetcher doit gérer gracieusement l'absence de codes connus (ajouter à `erreurs[]`).

### DS_RP_MENAGES_PRINC

Filtre de base : `TIME_PERIOD=2022`

| Indicateur | Approche |
|---|---|
| pop_menages_solo | Dimension à explorer (COUPLE=0 + filtre 1 personne ?) |
| pop_taille_menages | pop_total (depuis DS_RP_POPULATION_PRINC) ÷ nb_ménages total |

> **Note implémentation :** Les dimensions exactes pour isoler les ménages d'une seule personne doivent être vérifiées sur l'API réelle.

### DS_RP_ACTIVITE_PRINC + DS_RP_EMPLOI_LT_PRINC

Filtre de base : `TIME_PERIOD=2022`

| Indicateur | Dataset | Filtre |
|---|---|---|
| eco2_emplois_commune | DS_RP_EMPLOI_LT_PRINC | total (SEX=_T, AGE=_T ou équivalent) |
| eco_emplois_actifs_ratio | DS_RP_EMPLOI_LT_PRINC ÷ DS_RP_ACTIVITE_PRINC | emplois / actifs résidents |

---

## Renommage des indicateurs d'âge

### Anciens → Nouveaux IDs

| Ancien ID | Nouvel ID | Nouveau libellé |
|---|---|---|
| pop_age_0_14 | pop_age_lt15 | Population moins de 15 ans |
| pop_age_15_29 | pop_age_15_24 | Population 15-24 ans |
| pop_age_30_44 | pop_age_25_39 | Population 25-39 ans |
| pop_age_45_59 | pop_age_40_54 | Population 40-54 ans |
| pop_age_60_74 | pop_age_55_64 | Population 55-64 ans |
| pop_age_75_89 | pop_age_65_79 | Population 65-79 ans |
| pop_age_90_plus | pop_age_ge80 | Population 80 ans et plus |

### Migration DB

Dans `init_db()` (pattern `_column_exists` adapté) :

```python
# Renommage des indicateurs d'âge (migration Melodi)
_AGE_RENAMES = {
    "pop_age_0_14":  "pop_age_lt15",
    "pop_age_15_29": "pop_age_15_24",
    "pop_age_30_44": "pop_age_25_39",
    "pop_age_45_59": "pop_age_40_54",
    "pop_age_60_74": "pop_age_55_64",
    "pop_age_75_89": "pop_age_65_79",
    "pop_age_90_plus": "pop_age_ge80",
}
for old_id, new_id in _AGE_RENAMES.items():
    # Vérifier si l'ancien ID existe encore
    row = conn.execute("SELECT id FROM indicateurs WHERE id=%s", (old_id,)).fetchone()
    if row:
        # Supprimer les données liées (orphelines)
        conn.execute("DELETE FROM donnees WHERE indicateur_id=%s", (old_id,))
        # Renommer l'indicateur
        conn.execute("UPDATE indicateurs SET id=%s WHERE id=%s", (new_id, old_id))
```

---

## Changements UI

### `integrations.html`

- Titre section : "INSEE" → ne change pas (Melodi est toujours INSEE)
- Label champ : "INSEE API Key" → **"Clé API SIRENE"**
- Description : "Requis pour l'import automatique des données INSEE RP et SIRENE." → **"Requis pour l'import automatique des données SIRENE (entreprises et associations)."**
- Lien aide : toujours `https://portail-api.insee.fr/`

### `modifier_ville.html`

- Label champ : "INSEE API Key" → **"Clé API SIRENE"**

---

## Signature de `fetch_insee_rp_data`

```python
def fetch_insee_rp_data(code_insee: str) -> dict:
```

Le paramètre `api_key` est **supprimé** (Melodi ne nécessite pas de clé). La route `fetch_insee_rp` dans `admin.py` est mise à jour pour ne plus passer ce paramètre.

---

## Millésime

Constante `RP_MILLESIME = "2022"` (Melodi couvre 2011-2022, millésime le plus récent).

---

## Hors scope

- SIRENE : inchangé
- BPE : inchangé (data.gouv.fr)
- Chiffrement des clés API
- Support multi-millésimes (comparaison RP 2017 vs 2022)
