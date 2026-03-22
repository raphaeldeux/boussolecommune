# Redesign des pages thématiques — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retravailler les pages thématiques publiques pour afficher les indicateurs groupés par tendance (↗/↘/→), afficher une phrase courte visible sans clic, supprimer les boutons téléchargement, restreindre le badge A–E aux indicateurs avec référence robuste, et ajouter un bloc "Ce qu'il faut retenir" généré par Mistral.

**Architecture:** 8 fichiers modifiés/créés en séquence : labels → DB table → modèle → service Mistral → route publique → partial carte → template page → routes admin + dashboard. Chaque tâche est indépendante et testable à la main via Docker.

**Tech Stack:** Flask 3.0 · PostgreSQL 16 · Jinja2/Tailwind CSS · Mistral API (via `app/services/ollama_service.py`)

---

## File Map

| Fichier | Action | Contenu |
|---------|--------|---------|
| `app/models/indicateur.py` | Modifier | Nouveaux labels, questions, icône finances |
| `app/database.py` | Modifier | Nouvelle table `syntheses_thematiques` + auto-migration |
| `app/models/synthese_thematique.py` | Créer | get / upsert / delete synthèses |
| `app/services/ollama_service.py` | Modifier | Nouvelle fonction `generer_synthese_thematique()` |
| `app/routes/public.py` | Modifier | `grouped` par tendance + chargement synthèse |
| `app/templates/public/_ind_card.html` | Modifier | phrase_courte en en-tête + badge score conditionnel + supprimer exports |
| `app/templates/public/thematique.html` | Modifier | Nouvelle structure : en-tête + synthèse + 4 sections tendance |
| `app/routes/admin.py` | Modifier | 2 routes POST synthèse (generer / modifier) + passage `syntheses` au dashboard |
| `app/templates/admin/dashboard.html` | Modifier | Section "Synthèses thématiques" en bas |

---

## Task 1 : Nouveaux labels thématiques

**Files:**
- Modify: `app/models/indicateur.py`

**Context:** Le fichier définit `THEMATIQUE_LABELS`, `THEMATIQUE_QUESTIONS`, `THEMATIQUE_ICONS`. Les slugs URL ne changent pas.

- [ ] **Step 1 : Mettre à jour `THEMATIQUE_LABELS`**

Remplacer le bloc actuel (lignes 50–58) par :

```python
THEMATIQUE_LABELS = {
    "finances":    "Soin de la maison",
    "cadre_vie":   "Soin du territoire",
    "personnes":   "Soin des habitant·es",
    "lien_social": "Soin du lien",
    "democratie":  "Soin de la parole",
    "vivant":      "Soin du vivant",
    "portrait":    "Portrait de la commune",
}
```

- [ ] **Step 2 : Mettre à jour `THEMATIQUE_QUESTIONS`**

Remplacer le bloc actuel (lignes 60–68) par :

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

- [ ] **Step 3 : Changer uniquement l'icône de `finances`**

Dans `THEMATIQUE_ICONS`, remplacer `"finances": "💰"` par `"finances": "🏠"`. Ne pas toucher aux 5 autres (déjà corrects).

- [ ] **Step 4 : Vérifier visuellement**

Rebuild + naviguer sur la page thématique. Le titre doit afficher "Soin de la maison" pour finances, "Soin des habitant·es" pour personnes, etc.

```bash
docker compose up -d --build
```

Ouvrir http://localhost:5001/v/sautron/thematique/finances → vérifier label, question, icône.

- [ ] **Step 5 : Commit**

```bash
git add app/models/indicateur.py
git commit -m "feat: nouveaux labels thématiques Soin de..."
```

---

## Task 2 : Table `syntheses_thematiques`

**Files:**
- Modify: `app/database.py`

**Context:** `init_db()` crée toutes les tables. Les migrations auto utilisent `_table_exists()` déjà disponible. Le pattern existant pour les tables manquantes est : vérifier avec `_table_exists()`, puis `CREATE TABLE IF NOT EXISTS` + commit. Voir la migration `conseils` ou `documents` dans le fichier comme modèle.

- [ ] **Step 1 : Ajouter la table dans `init_db()`**

Trouver la fin de `init_db()` (avant `conn.execute("SELECT pg_advisory_unlock(42)")` ou avant le `conn.close()`). Ajouter le bloc suivant :

```python
    # Table synthèses thématiques (redesign-thematiques)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS syntheses_thematiques (
            id              SERIAL PRIMARY KEY,
            ville_id        INTEGER NOT NULL REFERENCES villes(id) ON DELETE CASCADE,
            thematique      TEXT NOT NULL,
            annee           INTEGER NOT NULL,
            texte           TEXT NOT NULL,
            date_generation TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ville_id, thematique, annee)
        )
    """)
```

- [ ] **Step 2 : Vérifier que la table est créée au démarrage**

```bash
docker compose up -d --build
docker compose exec db psql -U boussole -d boussolecommune -c "\dt syntheses_thematiques"
```

Résultat attendu : la table apparaît dans la liste.

- [ ] **Step 3 : Commit**

```bash
git add app/database.py
git commit -m "feat: table syntheses_thematiques"
```

---

## Task 3 : Modèle `synthese_thematique.py`

**Files:**
- Create: `app/models/synthese_thematique.py`

**Context:** Tous les modèles utilisent `get_db()` en context-manager (`with get_db() as conn`). `RealDictCursor` retourne des dicts. Exemple de pattern : voir `app/models/interpretation.py`.

- [ ] **Step 1 : Créer le fichier**

```python
from app.database import get_db


def get(ville_id: int, thematique: str, annee: int) -> dict | None:
    """Retourne la synthèse ou None si absente."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM syntheses_thematiques WHERE ville_id = %s AND thematique = %s AND annee = %s",
            (ville_id, thematique, annee),
        ).fetchone()
    return dict(row) if row else None


def upsert(ville_id: int, thematique: str, annee: int, texte: str) -> None:
    """Insère ou met à jour une synthèse (ON CONFLICT UPDATE)."""
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO syntheses_thematiques (ville_id, thematique, annee, texte, date_generation)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (ville_id, thematique, annee)
            DO UPDATE SET texte = EXCLUDED.texte, date_generation = CURRENT_TIMESTAMP
            """,
            (ville_id, thematique, annee, texte),
        )
        conn.commit()


def delete(ville_id: int, thematique: str, annee: int) -> None:
    """Supprime une synthèse."""
    with get_db() as conn:
        conn.execute(
            "DELETE FROM syntheses_thematiques WHERE ville_id = %s AND thematique = %s AND annee = %s",
            (ville_id, thematique, annee),
        )
        conn.commit()


def get_all_for_ville(ville_id: int) -> list[dict]:
    """Retourne toutes les synthèses d'une ville (pour l'admin dashboard)."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM syntheses_thematiques WHERE ville_id = %s ORDER BY thematique, annee DESC",
            (ville_id,),
        ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 2 : Vérifier l'import (pas de crash)**

```bash
docker compose exec web python -c "from app.models import synthese_thematique; print('OK')"
```

- [ ] **Step 3 : Commit**

```bash
git add app/models/synthese_thematique.py
git commit -m "feat: modèle synthese_thematique (get/upsert/delete)"
```

---

## Task 4 : Génération Mistral — `generer_synthese_thematique()`

**Files:**
- Modify: `app/services/ollama_service.py`

**Context:** Le fichier utilise déjà `_appel_mistral()` pour les PV de conseils. `MISTRAL_API_KEY` et `MISTRAL_MODEL` sont déjà importés. Ajouter la nouvelle fonction **à la fin** du fichier, avant `is_ollama_ready()`.

- [ ] **Step 1 : Ajouter la fonction**

```python
def generer_synthese_thematique(thematique_label: str, indicateurs_enrichis: list) -> list[str] | None:
    """
    Génère 2-3 bullet points de synthèse pour une thématique à partir des indicateurs enrichis.

    Args:
        thematique_label: Label d'affichage, ex. "Soin de la maison" (pas le slug).
        indicateurs_enrichis: Liste de dicts enrichis (tendance, libelle_citoyen, donnee, pct_evolution).

    Returns:
        list[str] avec 2-3 éléments, ou None si échec.
    """
    if not MISTRAL_API_KEY:
        return None

    # Sélection des évolutions les plus notables
    renseignes = [e for e in indicateurs_enrichis if e.get("donnee")]
    amelioration = sorted(
        [e for e in renseignes if e.get("tendance") == "↗"],
        key=lambda e: abs(e.get("pct_evolution") or 0),
        reverse=True,
    )[:3]
    surveiller = sorted(
        [e for e in renseignes if e.get("tendance") == "↘"],
        key=lambda e: abs(e.get("pct_evolution") or 0),
        reverse=True,
    )[:3]
    notables = amelioration + surveiller

    if not notables:
        return None

    lignes = []
    for e in notables:
        tendance = e.get("tendance", "")
        libelle = e.get("libelle_citoyen", "")
        valeur = e.get("donnee", {}).get("valeur", "")
        unite = e.get("unite", "")
        pct = e.get("pct_evolution")
        pct_str = f" ({'+' if pct and pct > 0 else ''}{pct}%)" if pct is not None else ""
        lignes.append(f"{tendance} {libelle} : {valeur} {unite}{pct_str}")

    donnees_str = "\n".join(f"- {l}" for l in lignes)

    prompt = f"""Tu analyses la thématique "{thematique_label}" d'une commune française.

Voici les évolutions notables des indicateurs :
{donnees_str}

Rédige exactement 2 ou 3 bullet points synthétisant CE QUI ÉVOLUE (positivement ou négativement).
Règles :
- 1 phrase max par bullet point, en français citoyen (pas de jargon)
- Commence chaque ligne par ↗ si amélioration, ⚠ si dégradation
- Pas de titre, pas d'introduction, UNIQUEMENT les bullet points
- Ne mentionne pas "IA", "modèle", "généré"

Exemple de format attendu :
↗ Le budget d'investissement a progressé de 15% cette année.
⚠ La dette par habitant reste au-dessus de la moyenne régionale."""

    try:
        raw = _appel_mistral(prompt)
        bullets = [line.strip() for line in raw.strip().splitlines() if line.strip()]
        bullets = [b for b in bullets if b.startswith(("↗", "⚠", "↘", "•", "-"))]
        if not bullets:
            # Fallback : découper en phrases si le modèle a répondu autrement
            bullets = [s.strip() for s in raw.strip().split("\n") if s.strip()]
        return bullets[:3] if bullets else None
    except Exception as e:
        print(f"[WARN] generer_synthese_thematique échoué : {e}", flush=True)
        return None
```

- [ ] **Step 2 : Vérifier l'import**

```bash
docker compose exec web python -c "from app.services.ollama_service import generer_synthese_thematique; print('OK')"
```

- [ ] **Step 3 : Commit**

```bash
git add app/services/ollama_service.py
git commit -m "feat: generer_synthese_thematique() via Mistral"
```

---

## Task 5 : Route publique — `grouped` par tendance + synthèse

**Files:**
- Modify: `app/routes/public.py` (fonction `thematique`, lignes ~292–382)

**Context:** La fonction `thematique()` construit `grouped` (actuellement par score) et appelle `render_template`. Il faut : (1) remplacer le `grouped`, (2) charger la synthèse, (3) passer `synthese` au template.

- [ ] **Step 1 : Remplacer le bloc `grouped` (lignes ~303–309)**

Remplacer :
```python
    grouped = {
        "forts":    [e for e in renseignes if e["score"] in ("A", "B")],
        "vigil":    [e for e in renseignes if e["score"] == "C"],
        "preocc":   [e for e in renseignes if e["score"] in ("D", "E")],
        "no_score": [e for e in renseignes if not e["score"]],
        "unset":    [e for e in enrichis   if not e["donnee"]],
    }
```

Par :
```python
    grouped = {
        "amelioration": [e for e in renseignes if e["tendance"] == "↗"],
        "surveiller":   [e for e in renseignes if e["tendance"] == "↘"],
        "stable":       [e for e in renseignes if e["tendance"] == "→"],
        "no_history":   [e for e in renseignes if not e["tendance"]],  # 1 seule année
        "unset":        [e for e in enrichis   if not e["donnee"]],
    }
```

- [ ] **Step 2 : Ajouter le chargement de la synthèse**

Après le bloc `grouped`, ajouter (avant `score_them = ...`) :

```python
    from app.models import synthese_thematique as synthese_model
    derniere_annee = max(e["donnee"]["annee"] for e in renseignes) if renseignes else None
    synthese = synthese_model.get(ville["id"], slug, derniere_annee) if derniere_annee else None
```

- [ ] **Step 3 : Passer `synthese` au template**

Dans l'appel `render_template(...)`, ajouter :
```python
        synthese=synthese,
```

- [ ] **Step 4 : Vérifier (pas de crash)**

```bash
docker compose up -d --build
```

Ouvrir http://localhost:5001/v/sautron/thematique/finances → vérifier que la page charge sans erreur 500.

- [ ] **Step 5 : Commit**

```bash
git add app/routes/public.py
git commit -m "feat: grouped par tendance + chargement synthèse thématique"
```

---

## Task 6 : Carte indicateur — phrase courte + badge conditionnel + suppression exports

**Files:**
- Modify: `app/templates/public/_ind_card.html`

**Context:** Le partial est utilisé par `thematique.html`. Actuellement : (1) `phrase_courte` est dans l'accordéon (ligne ~108), (2) le badge score s'affiche toujours si `ind.score` existe, (3) deux boutons d'export existent (Graphique + Post Facebook) avec beaucoup de JS associé.

- [ ] **Step 1 : Ajouter la phrase courte dans l'en-tête visible**

Dans le bouton `<button onclick="toggleDetail(this)">`, après le bloc `<!-- Nom + valeur + tendance -->` (après la `</div>` qui clôt `flex-1 min-w-0`), ajouter avant `<!-- Score + chevron -->` :

```jinja
  {# Phrase courte visible sans accordéon #}
  {% if ind.interpretation and ind.interpretation.phrase_courte %}
  <div class="w-full px-0 mt-1 text-xs text-gray-500 leading-snug">
    {{ ind.interpretation.phrase_courte }}
  </div>
  {% endif %}
```

Note : la `<div class="flex-1 min-w-0">` contient déjà le libellé + valeur. La phrase courte doit être **dans** cette div, après le bloc `flex items-baseline`.

Voici la zone exacte à modifier dans le bouton. La div `flex-1 min-w-0` doit devenir :

```jinja
  <!-- Nom + valeur + tendance + phrase courte -->
  <div class="flex-1 min-w-0">
    <div class="font-semibold text-gray-900 text-sm leading-snug">{{ ind.libelle_citoyen }}</div>
    <div class="flex items-baseline gap-1.5 mt-1 flex-wrap">
      <span class="text-base font-bold text-gray-800">
        {{ ind.donnee.valeur | format_valeur }}
      </span>
      <span class="text-xs text-gray-400">{{ ind.unite }}</span>
      {% if ind.tendance and ind.valeur_ancienne is not none %}
      <span class="text-xs font-semibold
        {% if tendance_bonne %}text-green-600{% elif tendance_mauvaise %}text-red-500{% else %}text-gray-400{% endif %}">
        {{ ind.tendance }}{% if ind.pct_evolution is not none %}&nbsp;{% if ind.pct_evolution > 0 %}+{% endif %}{{ ind.pct_evolution }}%{% endif %}
        <span class="font-normal italic ml-0.5">
          {%- if tendance_bonne -%}en amélioration
          {%- elif tendance_mauvaise -%}en dégradation
          {%- elif ind.tendance == '→' -%}stable
          {%- endif -%}
        </span>
      </span>
      {% endif %}
    </div>
    {% if ind.interpretation and ind.interpretation.phrase_courte %}
    <div class="mt-1 text-xs text-gray-500 leading-snug">{{ ind.interpretation.phrase_courte }}</div>
    {% endif %}
  </div>
```

- [ ] **Step 2 : Rendre le badge score conditionnel**

Dans `<!-- Score + chevron -->`, remplacer :

```jinja
    {% if ind.score %}
    <div class="score-badge score-badge-lg score-{{ ind.score }}">{{ ind.score }}</div>
    {% endif %}
```

Par :

```jinja
    {% if ind.score and (ind.valeur_reference is not none or (ind.source_type and ind.source_type in ('api_rpls', 'api_cerema'))) %}
    <div class="score-badge score-badge-lg score-{{ ind.score }}">{{ ind.score }}</div>
    {% endif %}
```

- [ ] **Step 3 : Retirer les boutons export (Graphique + Post Facebook)**

Dans `<!-- Source + actions -->`, supprimer les deux blocs `<button>` pour `exportGraphique` et `exportPost`. Conserver uniquement le bouton "En savoir plus ↓".

La section `<div class="flex items-center gap-3">` doit devenir :

```jinja
    <div class="flex items-center gap-3">
      {% if ind.description %}
      <button onclick="openModal('modal-{{ ind.id }}')"
              class="text-xs text-emerald-600 hover:text-emerald-800 hover:underline transition">
        En savoir plus ↓
      </button>
      {% endif %}
    </div>
```

- [ ] **Step 4 : Supprimer aussi la phrase courte de l'accordéon** (elle est maintenant dans l'en-tête)

Supprimer le bloc :
```jinja
  <!-- Interprétation courte -->
  {% if ind.interpretation and ind.interpretation.phrase_courte %}
  <div class="text-sm font-medium text-gray-700 leading-relaxed">{{ ind.interpretation.phrase_courte }}</div>
  {% endif %}
```

- [ ] **Step 5 : Vérifier visuellement**

Ouvrir http://localhost:5001/v/sautron/thematique/finances → les cartes doivent afficher la phrase courte dans l'en-tête (sans clic). Les boutons Graphique/Facebook doivent être absents. Le badge A–E ne doit apparaître que si `valeur_reference` est non-nulle ou `source_type in ('api_rpls', 'api_cerema')`.

- [ ] **Step 6 : Commit**

```bash
git add app/templates/public/_ind_card.html
git commit -m "feat: phrase courte visible + badge score conditionnel + suppression exports"
```

---

## Task 7 : Nouveau template `thematique.html`

**Files:**
- Modify: `app/templates/public/thematique.html`

**Context:** Le template actuel groupe par score (forts/vigil/preocc/no_score/unset). Il faut : (1) max-w-6xl, (2) en-tête en grille lg:grid-cols-3 avec bloc synthèse, (3) 4 sections par tendance.

**Important :** Le template contient aussi les modales description et tout le JS (exportGraphique, exportPost, etc.). Le JS export peut rester pour ne pas casser des usages futurs, mais les boutons qui l'appellent ont été supprimés dans Task 6. Ne pas supprimer les modales description.

- [ ] **Step 1 : Remplacer l'en-tête thématique (lignes ~28–60)**

Remplacer le bloc `<!-- En-tête thématique -->` par :

```jinja
<!-- En-tête thématique -->
<div class="bg-white rounded-xl shadow-sm border border-gray-100 p-5 sm:p-6 mb-6">
  <div class="lg:grid lg:grid-cols-3 lg:gap-6">

    <!-- 2/3 : icône + titre + question + légende -->
    <div class="lg:col-span-2 flex items-start gap-4 mb-4 lg:mb-0">
      <span class="text-4xl sm:text-5xl flex-shrink-0 mt-0.5">{{ icon }}</span>
      <div class="flex-1 min-w-0">
        <div class="flex items-start justify-between gap-3 flex-wrap">
          <div class="min-w-0">
            <h1 class="text-xl sm:text-2xl font-bold text-gray-900 leading-tight">{{ label }}</h1>
            <p class="text-gray-500 italic text-sm mt-1">{{ question }}</p>
          </div>
          <div class="flex-shrink-0">
            {% if score %}
            <div class="score-badge score-badge-lg score-{{ score }}">{{ score }}</div>
            {% else %}
            <span class="text-sm text-gray-400 italic">Score insuffisant</span>
            {% endif %}
          </div>
        </div>
        <!-- Légende A–E -->
        <div class="flex items-center gap-3 flex-wrap mt-3 pt-3 border-t border-gray-100 text-xs text-gray-400">
          <span class="flex-shrink-0">Scores :</span>
          <span class="flex items-center gap-1"><span class="score-badge-xs score-A">A</span> Très satisfaisant</span>
          <span class="flex items-center gap-1"><span class="score-badge-xs score-B">B</span> Bon</span>
          <span class="flex items-center gap-1"><span class="score-badge-xs score-C">C</span> Vigilance</span>
          <span class="flex items-center gap-1"><span class="score-badge-xs score-D">D</span> Préoccupant</span>
          <span class="flex items-center gap-1"><span class="score-badge-xs score-E">E</span> Critique</span>
        </div>
      </div>
    </div>

    <!-- 1/3 : bloc "Ce qu'il faut retenir" -->
    {% if synthese %}
    <div class="bg-emerald-50 border border-emerald-200 rounded-xl p-4 flex flex-col">
      <p class="text-xs font-semibold text-emerald-700 uppercase tracking-wide mb-2">📌 Ce qu'il faut retenir</p>
      <ul class="space-y-2">
        {% for ligne in synthese.texte.split('\n') if ligne.strip() %}
        <li class="text-sm text-gray-700 flex items-start gap-2">
          <span class="shrink-0">{% if '↗' in ligne %}↗{% elif '⚠' in ligne or '↘' in ligne %}⚠{% else %}•{% endif %}</span>
          <span>{{ ligne.lstrip('↗↘⚠•- ') }}</span>
        </li>
        {% endfor %}
      </ul>
    </div>
    {% endif %}

  </div>
</div>
```

- [ ] **Step 2 : Remplacer les sections par tendance (le bloc `{# ─── Triptyque par score ───── #}` jusqu'à `</div>{# end space-y-6 #}`)**

Remplacer de la ligne `{# ─── Triptyque par score ───── #}` jusqu'à `</div>{# end space-y-6 #}` par :

```jinja
{# ─── Sections par tendance ─────────────────────────────────────────────── #}

{% macro section_header(emoji, label_sg, label_pl, items, cls_h2, cls_count) %}
<div class="flex items-center gap-2 mb-3 px-1">
  <span class="text-base leading-none">{{ emoji }}</span>
  <h2 class="text-sm font-semibold {{ cls_h2 }} uppercase tracking-wide leading-tight">
    {{ label_sg if items | length == 1 else label_pl }}
  </h2>
  <span class="ml-auto text-xs {{ cls_count }} font-medium">{{ items | length }} indicateur{{ 's' if items | length > 1 }}</span>
</div>
{% endmacro %}

<div class="space-y-6">

{# ── ↗ En amélioration ─────────────────────────────────────────────────── #}
{% if grouped.amelioration %}
<section>
  {{ section_header('↗', 'En amélioration', 'En amélioration', grouped.amelioration, 'text-emerald-700', 'text-emerald-500') }}
  <div class="space-y-3">
    {% for ind in grouped.amelioration %}
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 border-l-4 border-l-emerald-400 overflow-hidden">
      {% include "public/_ind_card.html" %}
    </div>
    {% endfor %}
  </div>
</section>
{% endif %}

{# ── ↘ À surveiller ────────────────────────────────────────────────────── #}
{% if grouped.surveiller %}
<section>
  {{ section_header('↘', 'À surveiller', 'À surveiller', grouped.surveiller, 'text-red-700', 'text-red-500') }}
  <div class="space-y-3">
    {% for ind in grouped.surveiller %}
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 border-l-4 border-l-red-400 overflow-hidden">
      {% include "public/_ind_card.html" %}
    </div>
    {% endfor %}
  </div>
</section>
{% endif %}

{# ── → Stable ──────────────────────────────────────────────────────────── #}
{% if grouped.stable %}
<section>
  {{ section_header('→', 'Stable', 'Stables', grouped.stable, 'text-gray-500', 'text-gray-400') }}
  <div class="sm:grid sm:grid-cols-2 sm:gap-4 space-y-3 sm:space-y-0">
    {% for ind in grouped.stable %}
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 border-l-4 border-l-gray-300 overflow-hidden">
      {% include "public/_ind_card.html" %}
    </div>
    {% endfor %}
  </div>
</section>
{% endif %}

{# ── 📊 Manque d'historique ────────────────────────────────────────────── #}
{% if grouped.no_history %}
<div class="border border-gray-100 rounded-xl bg-white shadow-sm overflow-hidden">
  <button onclick="this.nextElementSibling.classList.toggle('hidden')"
          class="w-full flex items-center justify-between px-4 sm:px-5 py-3 text-left hover:bg-gray-50 transition">
    <span class="text-sm text-gray-500 font-medium flex items-center gap-2">
      <span>📊</span>
      <span>Manque d'historique</span>
      <span class="ml-1.5 text-xs bg-gray-100 text-gray-500 rounded-full px-2 py-0.5">{{ grouped.no_history | length }}</span>
    </span>
    <svg class="w-4 h-4 text-gray-300 flex-shrink-0 ml-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
      <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/>
    </svg>
  </button>
  <div class="hidden border-t border-gray-100">
    <div class="p-4 sm:grid sm:grid-cols-2 sm:gap-4 space-y-3 sm:space-y-0">
      {% for ind in grouped.no_history %}
      <div class="bg-gray-50 rounded-xl border border-gray-100 overflow-hidden opacity-80">
        {% include "public/_ind_card.html" %}
      </div>
      {% endfor %}
    </div>
  </div>
</div>
{% endif %}

{# ── Non renseignés ────────────────────────────────────────────────────── #}
{% if grouped.unset %}
<div class="border border-gray-100 rounded-xl bg-white shadow-sm overflow-hidden">
  <button onclick="this.nextElementSibling.classList.toggle('hidden')"
          class="w-full flex items-center justify-between px-4 sm:px-5 py-3 text-left hover:bg-gray-50 transition">
    <span class="text-sm text-gray-400 font-medium">
      Données non disponibles
      <span class="ml-1.5 text-xs bg-gray-100 text-gray-500 rounded-full px-2 py-0.5">{{ grouped.unset | length }}</span>
    </span>
    <svg class="w-4 h-4 text-gray-300 flex-shrink-0 ml-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
      <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/>
    </svg>
  </button>
  <div class="hidden divide-y divide-gray-50">
    {% for ind in grouped.unset %}
    <div class="px-4 sm:px-5 py-3 opacity-50">
      <div class="flex items-center justify-between gap-4">
        <div>
          <div class="font-medium text-gray-500 text-sm">{{ ind.libelle_citoyen }}</div>
          {% if ind.libelle_technique %}
          <div class="text-xs text-gray-400 mt-0.5">{{ ind.libelle_technique }}</div>
          {% endif %}
        </div>
        <span class="bg-gray-100 text-gray-400 text-xs font-medium px-2.5 py-1 rounded-full flex-shrink-0">Non renseigné</span>
      </div>
    </div>
    {% endfor %}
  </div>
</div>
{% endif %}

</div>{# end space-y-6 #}
```

- [ ] **Step 3 : Vérifier la page complète**

```bash
docker compose up -d --build
```

Ouvrir plusieurs thématiques :
- http://localhost:5001/v/sautron/thematique/finances → 4 sections tendance, en-tête 2/3 + 1/3 (synthèse absente OK)
- http://localhost:5001/v/sautron/thematique/vivant → vérifier indicateurs ZAN

- [ ] **Step 4 : Commit**

```bash
git add app/templates/public/thematique.html
git commit -m "feat: thematique.html — sections tendance + en-tête synthèse"
```

---

## Task 8 : Routes admin + section synthèses dans le dashboard

**Files:**
- Modify: `app/routes/admin.py`
- Modify: `app/templates/admin/dashboard.html`

**Context:** `admin.py` a 40+ routes. La session stocke `admin_ville_id`. Le décorateur `@login_required` est déjà défini dans le fichier. Le dashboard admin est `app/templates/admin/dashboard.html` et reçoit `stats` (liste par thématique). Il faut : (1) deux nouvelles routes POST, (2) passer les synthèses existantes au dashboard, (3) ajouter une section dans le template.

### Partie A : Nouvelles routes dans `admin.py`

- [ ] **Step 1 : Ajouter les imports en tête de `admin.py`**

Trouver les imports des modèles (bloc `import app.models...`). Ajouter :

```python
import app.models.synthese_thematique as synthese_model
```

Et dans les imports de services, ajouter (si pas déjà présent) :

```python
from app.services.ollama_service import generer_synthese_thematique
```

- [ ] **Step 2 : Ajouter la route `generer`**

Trouver la fin des routes admin (avant ou après la route `/admin/logout`). Ajouter :

```python
@bp.route("/admin/synthese-thematique/generer", methods=["POST"])
@login_required
def synthese_thematique_generer():
    """Génère et sauvegarde une synthèse thématique via Mistral."""
    ville_id = session.get("admin_ville_id")
    if not ville_id:
        flash("Aucune ville sélectionnée.", "error")
        return redirect(url_for("admin.dashboard"))

    thematique = request.form.get("thematique")
    annee = request.form.get("annee", type=int)

    if not thematique or not annee:
        flash("Paramètres manquants.", "error")
        return redirect(url_for("admin.dashboard"))

    # Charger les indicateurs enrichis pour la thématique
    from app.models import indicateur as ind_model
    from app.routes.public import _enrichir_indicateur
    from app.services.ollama_service import MISTRAL_API_KEY

    if not MISTRAL_API_KEY:
        flash("Clé API Mistral non configurée.", "error")
        return redirect(url_for("admin.dashboard"))

    indicateurs = ind_model.get_by_thematique(thematique)
    enrichis = [_enrichir_indicateur(i, ville_id) for i in indicateurs]

    label = ind_model.THEMATIQUE_LABELS.get(thematique, thematique)
    bullets = generer_synthese_thematique(label, enrichis)

    if not bullets:
        flash("La génération a échoué. Vérifiez la clé API Mistral.", "error")
        return redirect(url_for("admin.dashboard"))

    texte = "\n".join(bullets)
    synthese_model.upsert(ville_id, thematique, annee, texte)
    flash(f"Synthèse générée pour « {label} » ({annee}).", "success")
    return redirect(url_for("admin.dashboard"))
```

- [ ] **Step 3 : Ajouter la route `modifier`**

```python
@bp.route("/admin/synthese-thematique/modifier", methods=["POST"])
@login_required
def synthese_thematique_modifier():
    """Enregistre la modification manuelle d'une synthèse thématique."""
    ville_id = session.get("admin_ville_id")
    if not ville_id:
        flash("Aucune ville sélectionnée.", "error")
        return redirect(url_for("admin.dashboard"))

    thematique = request.form.get("thematique")
    annee = request.form.get("annee", type=int)
    texte = request.form.get("texte", "").strip()

    if not thematique or not annee or not texte:
        flash("Paramètres manquants.", "error")
        return redirect(url_for("admin.dashboard"))

    synthese_model.upsert(ville_id, thematique, annee, texte)

    from app.models.indicateur import THEMATIQUE_LABELS
    label = THEMATIQUE_LABELS.get(thematique, thematique)
    flash(f"Synthèse mise à jour pour « {label} » ({annee}).", "success")
    return redirect(url_for("admin.dashboard"))
```

### Partie B : Passer les synthèses au dashboard

- [ ] **Step 4 : Dans la route `dashboard` de admin.py, passer les données synthèse**

Trouver la route `@bp.route("/admin/")` ou `@bp.route("/admin")` qui rend `admin/dashboard.html`. La route appelle `_get_current_ville()` et stocke le résultat dans `ville`. Ajouter avant `render_template` :

```python
    # Synthèses thématiques : charger les existantes + calculer dernière_annee par thématique
    from app.models import synthese_thematique as synthese_model
    from app.models.indicateur import get_thematiques, THEMATIQUE_LABELS, THEMATIQUE_ICONS
    from app.routes.public import _enrichir_indicateur  # import interne OK — public.py n'importe pas admin.py
    import app.models.indicateur as ind_model_admin

    ville_id = ville["id"]  # ville est déjà résolu plus haut dans la route

    syntheses_existantes = {
        s["thematique"]: s
        for s in synthese_model.get_all_for_ville(ville_id)
    }

    syntheses_info = []
    for slug in get_thematiques():
        indicateurs_them = ind_model_admin.get_by_thematique(slug)
        enrichis_them = [_enrichir_indicateur(i, ville_id) for i in indicateurs_them]
        renseignes_them = [e for e in enrichis_them if e["donnee"]]
        derniere_annee = max((e["donnee"]["annee"] for e in renseignes_them), default=None)
        syntheses_info.append({
            "slug": slug,
            "label": THEMATIQUE_LABELS[slug],
            "icon": THEMATIQUE_ICONS[slug],
            "derniere_annee": derniere_annee,
            "synthese": syntheses_existantes.get(slug),
        })
```

Puis passer `syntheses_info=syntheses_info` à `render_template`.

**Note :** Si la route dashboard est complexe et calcule déjà `ville_id` via session, réutiliser la variable existante. Ne pas créer de doublon.

### Partie C : Section dashboard template

- [ ] **Step 5 : Ajouter la section dans `app/templates/admin/dashboard.html`**

Trouver la fin du template (avant `{% endblock %}`). Ajouter :

```jinja
<!-- Synthèses thématiques -->
{% if syntheses_info %}
<div class="bg-white rounded-xl border border-gray-100 shadow-sm p-5 mt-6">
  <h2 class="text-sm font-semibold text-gray-700 mb-4">📌 Synthèses thématiques</h2>
  <div class="space-y-4">
    {% for s in syntheses_info %}
    <div class="border border-gray-100 rounded-lg p-4">
      <div class="flex items-center gap-2 mb-2">
        <span>{{ s.icon }}</span>
        <span class="font-medium text-sm text-gray-800">{{ s.label }}</span>
        {% if s.synthese %}
        <span class="ml-auto text-xs text-gray-400">Mis à jour {{ s.synthese.date_generation.strftime('%d/%m/%Y') if s.synthese.date_generation else '' }}</span>
        {% endif %}
      </div>

      {% if s.derniere_annee %}
      <!-- Texte actuel -->
      {% if s.synthese %}
      <div class="text-xs text-gray-600 bg-gray-50 rounded p-2 mb-3 whitespace-pre-wrap">{{ s.synthese.texte }}</div>
      {% else %}
      <p class="text-xs text-gray-400 italic mb-3">Aucune synthèse générée.</p>
      {% endif %}

      <!-- Formulaire modifier -->
      <form method="POST" action="{{ url_for('admin.synthese_thematique_modifier') }}" class="mb-2">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="hidden" name="thematique" value="{{ s.slug }}">
        <input type="hidden" name="annee" value="{{ s.derniere_annee }}">
        <textarea name="texte" rows="3"
                  class="w-full text-xs border border-gray-200 rounded px-2 py-1.5 mb-1 resize-y"
                  placeholder="Entrez les bullet points (un par ligne, commencer par ↗ ou ⚠)">{{ s.synthese.texte if s.synthese else '' }}</textarea>
        <button type="submit"
                class="px-3 py-1 bg-gray-100 hover:bg-gray-200 text-gray-700 text-xs rounded transition">
          Enregistrer
        </button>
      </form>

      <!-- Bouton générer -->
      <form method="POST" action="{{ url_for('admin.synthese_thematique_generer') }}">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="hidden" name="thematique" value="{{ s.slug }}">
        <input type="hidden" name="annee" value="{{ s.derniere_annee }}">
        <button type="submit"
                class="px-3 py-1 bg-emerald-600 hover:bg-emerald-700 text-white text-xs rounded transition">
          ✨ Générer via IA
        </button>
      </form>

      {% else %}
      <p class="text-xs text-gray-400 italic">Aucune donnée disponible pour cette thématique.</p>
      {% endif %}
    </div>
    {% endfor %}
  </div>
</div>
{% endif %}
```

- [ ] **Step 6 : Rebuild et vérifier le dashboard admin**

```bash
docker compose up -d --build
```

Ouvrir http://localhost:5001/admin/ → la section "Synthèses thématiques" doit apparaître en bas avec les 6 thématiques.

- [ ] **Step 7 : Tester la génération (si MISTRAL_API_KEY configuré)**

Cliquer "Générer via IA" pour une thématique → flash de succès → synthèse apparaît.
Si pas de clé API : flash d'erreur attendu.

- [ ] **Step 8 : Tester la modification manuelle**

Entrer un texte dans le textarea → "Enregistrer" → le texte est sauvegardé → apparaît sur la page publique thématique.

- [ ] **Step 9 : Commit**

```bash
git add app/routes/admin.py app/templates/admin/dashboard.html
git commit -m "feat: routes admin synthèse thématique + section dashboard"
```

---

## Vérification finale

- [ ] Toutes les 6 thématiques affichent le nouveau label
- [ ] La page thématique a bien 4 sections (amélioration / surveiller / stable / manque d'historique)
- [ ] Les accordéons des sections ↗/↘ sont en 1 colonne (pas de décalage)
- [ ] Stable et Manque d'historique sont en 2 colonnes
- [ ] La phrase courte est visible sans clic
- [ ] Les boutons Graphique et Post Facebook sont absents
- [ ] Le bloc "Ce qu'il faut retenir" apparaît si une synthèse existe
- [ ] L'admin peut générer et modifier une synthèse depuis le dashboard

```bash
docker compose up -d --build
# Vérifier manuellement les URLs ci-dessus
```
