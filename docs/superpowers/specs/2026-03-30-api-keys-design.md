# Gestion des clés API par ville — Design

**Goal:** Permettre à chaque gestionnaire de ville de configurer ses propres clés API (INSEE et Mistral) depuis l'espace admin, sans intervention du super_admin sur le `.env`.

**Approach:** Approche A — colonnes sur la table `villes`. Trois nouvelles colonnes stockent les clés en clair. Les fetchers et `ai_service.py` acceptent la clé en paramètre avec fallback sur les variables d'environnement si la colonne est vide.

---

## Architecture

### Fichiers modifiés
- `app/database.py` — migration : 3 nouvelles colonnes sur `villes`
- `app/models/ville.py` — `get_by_id()` et `update()` incluent les nouvelles colonnes
- `app/services/ai_service.py` — `_appel_mistral()` accepte `api_key` et `model` en paramètres optionnels avec fallback env
- `app/services/fetchers/insee_rp.py` — `fetch_insee_rp_data()` accepte `api_key=None` avec fallback env
- `app/services/fetchers/sirene.py` — `fetch_sirene_data()` accepte `api_key=None` avec fallback env
- `app/routes/admin.py` — nouvelle route `/integrations` (gestionnaire) + `modifier_ville` étendu (super_admin) + routes fetch passent la clé de la ville
- `app/templates/admin/integrations.html` — nouveau template (gestionnaire)
- `app/templates/admin/modifier_ville.html` — section API keys ajoutée pour super_admin
- `app/config.py` — suppression des variables mortes `GROQ_API_KEY` / `GROQ_MODEL`

### Nouveau schéma — table `villes`

```sql
ALTER TABLE villes ADD COLUMN insee_api_key TEXT DEFAULT NULL;
ALTER TABLE villes ADD COLUMN mistral_api_key TEXT DEFAULT NULL;
ALTER TABLE villes ADD COLUMN mistral_model TEXT DEFAULT NULL;
```

Les colonnes sont nullables. Si vides, les services tombent en fallback sur les variables d'environnement (`INSEE_API_KEY`, `MISTRAL_API_KEY`, `MISTRAL_MODEL`).

### Flux de résolution de la clé

```
1. Récupérer la ville via _get_current_ville()
2. Lire la clé depuis ville["insee_api_key"] (ou mistral_api_key)
3. Si vide → fallback os.environ.get("INSEE_API_KEY")
4. Passer la clé résolue au fetcher / ai_service
```

La résolution et la vérification de présence se font **dans le fetcher/service** (pas dans la route), pour centraliser la logique :

```python
# Exemple dans fetch_insee_rp_data() :
def fetch_insee_rp_data(code_insee: str, api_key: str = None) -> dict:
    api_key = api_key or os.environ.get("INSEE_API_KEY", "")
    if not api_key:
        return {"ok": False, "error": "INSEE_API_KEY non configurée...", ...}
```

### Routes admin à modifier

Les routes suivantes passent la clé résolue à chaque appel :

| Route | Appel modifié |
|-------|--------------|
| `fetch_insee_rp()` | `fetch_insee_rp_data(code_insee, api_key=ville.get("insee_api_key"))` |
| `fetch_sirene()` | `fetch_sirene_data(code_insee, api_key=ville.get("insee_api_key"))` |
| `interpretation_generer_ia()` (~ligne 438) | `generer_interpretation_indicateur(..., api_key=..., model=...)` |
| `conseil_generer_resume()` (~ligne 2199) | `generer_resume_pv(..., api_key=..., model=...)` |
| `generer_synthese_thematique()` (~ligne 2623) | `generer_synthese_thematique(..., api_key=..., model=...)` |

La suppression de la vérification `if not os.environ.get("INSEE_API_KEY")` existante dans `fetch_sirene()` est incluse dans cette tâche (remplacée par le check dans le fetcher).

### Signature `ville.py update()` étendue

```python
def update(ville_id, nom, slug, population=None, actif=1, code_insee=None,
           nb_conseillers=None, whatsapp_url=None, indicateurs_vedettes=None,
           prochain_conseil=None, prochain_conseil_heure=None,
           insee_api_key=None, mistral_api_key=None, mistral_model=None):
```

La valeur `None` conserve la valeur existante en base (UPDATE inclut toujours les 3 colonnes).

---

## User Stories

### US-1 — Gestionnaire configure ses clés API

**En tant que gestionnaire**, j'accède à une page `/admin/integrations` depuis mon menu admin.

Je vois deux sections :
- **INSEE** : champ `INSEE API Key` (format `consumer_key:consumer_secret`), lien vers api.insee.fr
- **Mistral AI** : champs `Clé API Mistral` et `Modèle` (défaut : `mistral-small-latest`)

Je peux saisir, modifier ou vider chaque champ. Les valeurs sont masquées (type `password`) mais révélables. Un bouton « Enregistrer » sauvegarde.

**Critères d'acceptation :**
- Accessible uniquement aux utilisateurs connectés (`login_required`)
- Scopé à la ville de la session (`admin_ville_id`)
- Validation : format `xxx:yyy` pour la clé INSEE (avertissement non-bloquant si format incorrect)
- Flash de confirmation après sauvegarde
- Si une clé est déjà configurée dans `.env`, la page affiche un message informatif « Clé héritée de la configuration serveur — la valeur ci-dessous la remplace si renseignée »

### US-2 — Super_admin configure les clés d'une ville

**En tant que super_admin**, dans la fiche de modification d'une ville (`/admin/villes/modifier/<id>`), je vois une section « Intégrations API » avec les mêmes champs qu'en US-1.

**Critères d'acceptation :**
- Section visible uniquement dans la fiche super_admin (pas dans le formulaire de création)
- Comportement identique à US-1 pour la sauvegarde

### US-3 — Les fetchers utilisent la clé de la ville

**En tant que gestionnaire**, quand je clique « Récupérer » sur la carte INSEE RP ou SIRENE, l'app utilise ma clé configurée en base (et non la variable d'env globale).

**Critères d'acceptation :**
- Si aucune clé en base ET aucune clé en env → flash d'erreur « INSEE_API_KEY non configurée »
- Si clé en base → priorité sur l'env
- Si clé en env seulement → fallback silencieux (comportement actuel préservé)

### US-4 — Mistral utilise la clé de la ville

**En tant que gestionnaire**, quand je génère un résumé citoyen depuis un PV, l'app utilise ma clé Mistral configurée.

**Critères d'acceptation :**
- Les fonctions `generer_resume_pv`, `generer_interpretation_indicateur`, `generer_synthese_thematique` reçoivent la clé et le modèle résolus depuis la ville
- Fallback env si non configuré en base
- Nettoyage : suppression de `GROQ_API_KEY` / `GROQ_MODEL` dans `config.py` (variables mortes)

---

## Page `/admin/integrations` (template)

Accessible via `login_required`. Reçoit en contexte :
- `ville` : dict de la ville en session (avec les nouveaux champs)
- `has_env_insee` : bool — `INSEE_API_KEY` est-elle définie dans l'env ?
- `has_env_mistral` : bool — `MISTRAL_API_KEY` est-elle définie dans l'env ?

Affiche :
- Section INSEE : champ password + lien aide + badge « hérité de .env » si applicable
- Section Mistral : champ password + champ modèle + badge si applicable
- Bouton « Enregistrer »

---

## Variables d'environnement

Inchangées — servent de fallback global :
```
INSEE_API_KEY        consumer_key:consumer_secret (optionnel si configuré par ville)
MISTRAL_API_KEY      Clé API Mistral (optionnel si configuré par ville)
MISTRAL_MODEL        Modèle Mistral (défaut : mistral-small-latest)
```

Supprimées :
```
GROQ_API_KEY         (mort — supprimé de config.py)
GROQ_MODEL           (mort — supprimé de config.py)
```

---

## Hors scope

- Chiffrement des clés en base (reporté)
- Rotation automatique des clés
- Audit log des changements de clés
- Support d'autres providers LLM (OpenAI, etc.)
