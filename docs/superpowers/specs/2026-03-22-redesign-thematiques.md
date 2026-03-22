# Redesign des pages thématiques

## Goal

Retravailler les pages thématiques pour qu'elles soient immédiatement lisibles par des habitant·es engagé·es et des militant·es : **ce qui évolue** et **ce qu'il faut surveiller**. Réserver le score A–E aux indicateurs ayant une référence externe robuste ou un objectif légal.

## Architecture

- `app/templates/public/thematique.html` — restructuration (4 sections par tendance)
- `app/templates/public/_ind_card.html` — phrase courte visible par défaut, suppression boutons téléchargement
- `app/routes/public.py` — `grouped` par tendance (↗/↘/→/historique)
- `app/models/indicateur.py` — nouveaux labels et questions thématiques
- `app/database.py` — nouvelle table `syntheses_thematiques`
- `app/models/synthese_thematique.py` (nouveau) — get/upsert des synthèses
- `app/services/ollama_service.py` — nouvelle fonction `generer_synthese_thematique()`
- `app/routes/admin.py` — route pour générer/éditer la synthèse thématique

## Tech Stack

Flask 3.0 · PostgreSQL 16 · Jinja2/Tailwind · Mistral API (existant)

---

## Nouvelles étiquettes thématiques

Les slugs d'URL ne changent pas. Seuls les labels et questions sont mis à jour.

| Slug | Ancien label | Nouveau label | Icône |
|---|---|---|---|
| `finances` | Soin des finances | Soin de la maison | 🏠 |
| `cadre_vie` | Soin du cadre de vie | Soin du territoire | 🌳 |
| `personnes` | Soin des personnes | Soin des habitant·es | ❤️ |
| `lien_social` | Soin du lien social | Soin du lien | 🤝 |
| `democratie` | Soin de la démocratie | Soin de la parole | 🏛️ |
| `vivant` | Soin du vivant | Soin du vivant | 🌿 |

### Nouvelles questions thématiques

```python
THEMATIQUE_QUESTIONS = {
    "finances":    "La commune se donne-t-elle les moyens d'agir ?",
    "cadre_vie":   "La commune entretient-elle son territoire ?",
    "personnes":   "La commune prend-elle soin de ses habitant·es ?",
    "lien_social": "La commune fait-elle vivre sa communauté ?",
    "democratie":  "La commune gouverne-t-elle avec transparence ?",
    "vivant":      "La commune ménage-t-elle son environnement ?",
    "portrait":    "",
}
```

---

## Structure de la page thématique

### Largeur

`max-w-6xl mx-auto` — identique à la homepage et au dashboard.

### 1. Navigation thématique (existante, inchangée)

Tags horizontaux, actif en vert.

### 2. En-tête thématique

Grille `lg:grid-cols-3` :
- **2/3** : icône (5xl) + titre + question + légende des scores A–E (5 lettres)
- **1/3** : bloc "Ce qu'il faut retenir" (voir ci-dessous)

### 3. Bloc "Ce qu'il faut retenir"

- Fond `emerald-50`, border `emerald-200`
- Titre : `📌 Ce qu'il faut retenir`
- 2–3 bullet points avec icône tendance (↗ vert / ⚠ amber)
- Texte généré par Mistral, stocké en base, éditable par l'admin
- Affiché uniquement si une synthèse existe en base (sinon absent)
- **Aucune mention de génération automatique** dans l'interface publique

### 4. Sections par tendance (4 sections)

#### ↗ En amélioration
Indicateurs dont `tendance == '↗'`. Header vert. Espace `space-y-3` (1 colonne).

#### ↘ À surveiller
Indicateurs dont `tendance == '↘'`. Header rouge. Espace `space-y-3` (1 colonne).

#### → Stable
Indicateurs dont `tendance == '→'`. Header gris atténué. Grille `sm:grid-cols-2` (2 colonnes — pas d'accordéon = pas de décalage).

#### 📊 Manque d'historique
Indicateurs renseignés avec 1 seule année (pas de tendance calculable). Accordéon fermé par défaut, style grisé. Grille `sm:grid-cols-2` à l'intérieur.

**Indicateurs non renseignés** : conservés en accordéon fermé "Données non disponibles" (existant).

---

## Règle d'affichage du score A–E

Le badge score s'affiche **uniquement** si l'indicateur a une référence externe robuste ou un objectif légal :

```python
# Dans le template Jinja
{% if ind.valeur_reference is not none or ind.source_type in ('api_rpls', 'api_cerema') %}
  <div class="score-badge score-{{ ind.score }}">{{ ind.score }}</div>
{% endif %}
```

Les indicateurs sans référence affichent uniquement valeur + tendance. Le score global thématique (badge en en-tête) est calculé sur tous les indicateurs renseignés (inchangé).

---

## Carte indicateur (`_ind_card.html`)

### En-tête visible (sans clic)

- Libellé citoyen (font-semibold)
- Valeur + unité + tendance colorée (↗ vert / ↘ rouge / → gris)
- **Phrase courte d'interprétation** si disponible (text-xs text-gray-500) — **nouveau, visible sans accordéon**
- Badge score (si référence robuste)
- Chevron

### Détail accordéon (inchangé sauf suppression téléchargements)

- Libellé technique
- Comparaison barres (ville vs communes similaires) — si `valeur_reference`
- Graphique historique (Chart.js, lazy) — si `has_historique`
- Interprétation longue
- Source
- ~~Boutons export graphique et post Facebook~~ **SUPPRIMÉS**
- "En savoir plus ↓" (modale description) — conservé

Dans le détail ouvert, si `has_historique` ET `valeur_reference` : afficher en grille `sm:grid-cols-2` (comparaison | graphique côte à côte).

---

## Bloc "Ce qu'il faut retenir" — données et génération

### Table `syntheses_thematiques`

```sql
CREATE TABLE IF NOT EXISTS syntheses_thematiques (
    id            SERIAL PRIMARY KEY,
    ville_id      INTEGER NOT NULL REFERENCES villes(id) ON DELETE CASCADE,
    thematique    TEXT NOT NULL,
    annee         INTEGER NOT NULL,
    texte         TEXT NOT NULL,
    date_generation TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ville_id, thematique, annee)
);
```

### Modèle `app/models/synthese_thematique.py`

```python
def get(ville_id, thematique, annee) -> dict | None
def upsert(ville_id, thematique, annee, texte) -> None
def delete(ville_id, thematique, annee) -> None
```

### Génération Mistral (`app/services/ollama_service.py`)

Nouvelle fonction `generer_synthese_thematique(thematique_label, indicateurs_enrichis)` :
- Construit un prompt avec les 3-5 évolutions les plus notables (↗ les plus fortes, ↘ les plus préoccupantes)
- Appelle `_appel_mistral()` existant
- Retourne 2–3 bullet points (liste de strings), 1 phrase max chacun
- Gère les erreurs (retourne None si échec)

### Route admin `POST /admin/synthese-thematique/generer`

```
@login_required
Params: ville_id (session), thematique, annee
→ appelle generer_synthese_thematique()
→ upsert en base
→ flash + redirect dashboard
```

### Route admin `POST /admin/synthese-thematique/modifier`

```
Params: ville_id (session), thematique, annee, texte (textarea)
→ upsert en base
→ flash + redirect
```

L'interface admin (dashboard ou page dédiée) doit permettre de voir, générer et modifier la synthèse pour chaque thématique.

---

## Route publique (`app/routes/public.py`)

### `grouped` par tendance (remplace groupement par score)

```python
grouped = {
    "amelioration": [e for e in renseignes if e["tendance"] == "↗"],
    "surveiller":   [e for e in renseignes if e["tendance"] == "↘"],
    "stable":       [e for e in renseignes if e["tendance"] == "→"],
    "no_history":   [e for e in renseignes if not e["tendance"]],
    "unset":        [e for e in enrichis   if not e["donnee"]],
}
```

### Chargement de la synthèse

```python
from app.models import synthese_thematique as synthese_model

derniere_annee = max(e["donnee"]["annee"] for e in renseignes) if renseignes else None
synthese = synthese_model.get(ville["id"], slug, derniere_annee) if derniere_annee else None
```

Passer `synthese` au template.

---

## Affichage de la synthèse dans le template

La synthèse est stockée en texte libre (bullet points séparés par `\n`). Le template parse et affiche :

```jinja
{% if synthese %}
<div class="bg-emerald-50 border border-emerald-200 rounded-xl p-4 flex flex-col">
  <p class="text-xs font-semibold text-emerald-700 uppercase tracking-wide mb-2">📌 Ce qu'il faut retenir</p>
  <ul class="space-y-2">
    {% for ligne in synthese.texte.split('\n') if ligne.strip() %}
    <li class="text-sm text-gray-700 flex items-start gap-2">
      <span class="shrink-0">{% if '↗' in ligne %}↗{% elif '⚠' in ligne or '↘' in ligne %}⚠{% else %}•{% endif %}</span>
      {{ ligne.lstrip('↗↘⚠•- ') }}
    </li>
    {% endfor %}
  </ul>
</div>
{% endif %}
```

---

## Out of scope

- Boutons téléchargement graphique / post Facebook (supprimés, pas prêts)
- Changement des slugs d'URL (compatibility : slugs inchangés)
- Génération automatique de synthèse au chargement de page (trop lent — déclenché manuellement par l'admin)
- Modification des icônes autres que `finances` → 🏠
- Refonte des autres pages publiques (dashboard, portrait, comparer)
- Suppression de l'ancien groupement score (gardé en DB/scoring, juste non affiché en page thématique)
