# Refonte workflow admin — Gestion des conseils

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fusionner les 3 pages admin d'un conseil (Modifier / Préparation / Résumé) en une fiche unique avec pipeline de statut, et simplifier la liste.

**Architecture:** Nouvelle route `conseil_fiche` (`GET/POST /admin/conseils/<id>`) remplace les 3 pages actuelles. La liste est refactorée avec un badge de statut et une colonne "prochaine action". Les routes d'action existantes (upload, IA, publication) conservent leur logique mais redirigent toutes vers la fiche.

**Tech Stack:** Flask 3.0, psycopg2, Jinja2, Tailwind CSS, vanilla JS (pas de framework test)

---

## Fichiers concernés

| Fichier | Action |
|---|---|
| `app/models/conseil.py` | Modifier — `delete()` retourne aussi `note_synthese_pdf` |
| `app/routes/admin.py` | Modifier — nouvelles routes, helpers statut, mise à jour redirects |
| `app/templates/admin/conseils.html` | Modifier — liste refactorée |
| `app/templates/admin/conseil_form.html` | Modifier — supprimer champ PDF |
| `app/templates/admin/conseil_fiche.html` | **Créer** — fiche unique |
| `app/templates/admin/conseil_preparation.html` | Modifier — redirect seulement |
| `app/templates/admin/conseil_resume.html` | Modifier — redirect seulement |

---

## Task 1 : Mettre à jour `conseil_model.delete()` pour retourner les deux fichiers

**Fichiers :**
- Modifier : `app/models/conseil.py:66-73`

- [ ] **Step 1 : Modifier `delete()` pour retourner un dict avec les deux fichiers**

```python
# app/models/conseil.py — remplacer la fonction delete() existante

def delete(conseil_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT fichier_pdf, note_synthese_pdf FROM conseils WHERE id=%s",
            (conseil_id,)
        ).fetchone()
        conn.execute("DELETE FROM conseils WHERE id=%s", (conseil_id,))
        conn.commit()
    if not row:
        return None, None
    return dict(row).get("fichier_pdf"), dict(row).get("note_synthese_pdf")
```

- [ ] **Step 2 : Mettre à jour `conseil_supprimer` dans `admin.py` pour utiliser le tuple**

Remplacer (lignes ~1892-1898 de `app/routes/admin.py`) :

```python
# Avant
fichier_pdf = conseil_model.delete(conseil_id)
if fichier_pdf:
    path = os.path.join(CONSEILS_UPLOAD_DIR, fichier_pdf)
    if os.path.exists(path):
        os.remove(path)

# Après
fichier_pdf, note_synthese_pdf = conseil_model.delete(conseil_id)
if fichier_pdf:
    path = os.path.join(CONSEILS_UPLOAD_DIR, fichier_pdf)
    if os.path.exists(path):
        os.remove(path)
if note_synthese_pdf:
    path = os.path.join(NOTES_SYNTHESE_DIR, note_synthese_pdf)
    if os.path.exists(path):
        os.remove(path)
```

- [ ] **Step 3 : Vérifier manuellement**

Créer un conseil de test, déposer une note de synthèse, supprimer → vérifier que le fichier disparaît de `/app/uploads/notes_synthese/`.

- [ ] **Step 4 : Commit**

```bash
git add app/models/conseil.py app/routes/admin.py
git commit -m "fix: conseil_supprimer supprime aussi la note de synthèse"
```

---

## Task 2 : Ajouter les fonctions helpers de statut dans `admin.py`

**Fichiers :**
- Modifier : `app/routes/admin.py` (après la ligne des imports de conseil_model, vers la ligne ~1790)

- [ ] **Step 1 : Ajouter les deux helpers juste avant la route `conseils()`**

```python
# Ajouter dans app/routes/admin.py juste avant def conseils():

import app.models.conseil as conseil_model  # déjà présent, ne pas dupliquer

def _conseil_statut(conseil):
    """Retourne le statut global d'un conseil : nouveau, odj_publie, pv_depose, publie."""
    if conseil.get("publie"):
        return "publie"
    if conseil.get("fichier_pdf"):
        return "pv_depose"
    if conseil.get("odj_publie"):
        return "odj_publie"
    return "nouveau"


def _conseil_prochaine_action(conseil):
    """Retourne le texte de la prochaine action requise, ou None si publié."""
    if conseil.get("publie"):
        return None
    if conseil.get("fichier_pdf"):
        if not conseil.get("resume_citoyen"):
            return "Générer le résumé citoyen"
        return "Publier le compte-rendu"
    if conseil.get("odj_publie"):
        return "Déposer le PV après séance"
    if not conseil.get("note_synthese_pdf"):
        return "Déposer la note de synthèse"
    return "Publier l'ordre du jour"
```

- [ ] **Step 2 : Commit**

```bash
git add app/routes/admin.py
git commit -m "feat: helpers _conseil_statut et _conseil_prochaine_action"
```

---

## Task 3 : Simplifier le formulaire de création (supprimer le champ PDF)

**Fichiers :**
- Modifier : `app/templates/admin/conseil_form.html:49-62`
- Modifier : `app/routes/admin.py` — route `conseil_nouveau` POST handler

- [ ] **Step 1 : Supprimer le bloc du champ PDF dans `conseil_form.html`**

Supprimer les lignes 49-62 (le `<div>` contenant le champ `fichier_pdf`).

Le template devient (section champs uniquement) :
```html
{# Supprimer entièrement ce bloc de conseil_form.html : #}
    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">
        Procès-verbal (PDF)
        ...
      </label>
      <input type="file" name="fichier_pdf" accept=".pdf" ...>
      ...
    </div>
```

Aussi retirer l'attribut `enctype="multipart/form-data"` de la balise `<form>` (ligne 10) puisqu'il n'y a plus de fichier.

- [ ] **Step 2 : Retirer la logique PDF du POST handler `conseil_nouveau`**

Dans `app/routes/admin.py`, la route `conseil_nouveau` (POST, ~ligne 1827) :

```python
# Supprimer ces lignes :
fichier = request.files.get("fichier_pdf")
# ...
fichier_pdf = None
if fichier and fichier.filename:
    if not fichier.filename.lower().endswith(".pdf") or not _is_valid_pdf(fichier):
        flash("Seuls les fichiers PDF valides sont acceptés.", "danger")
        return render_template("admin/conseil_form.html", ville=ville, conseil=None)
    fichier_pdf = _save_pdf(fichier)
conseil_model.create(ville["id"], titre, date_conseil, fichier_pdf, type_conseil)

# Remplacer par :
conseil_model.create(ville["id"], titre, date_conseil, None, type_conseil)
```

Aussi retirer `enctype="multipart/form-data"` dans `render_template` si présent.

La route `conseil_modifier` devient inutile (elle sera convertie en redirect à la Task 8) — ne pas toucher pour l'instant.

- [ ] **Step 3 : Vérifier manuellement**

Aller sur `/admin/conseils/nouveau` → formulaire sans champ PDF. Créer un conseil → redirige vers la liste.

- [ ] **Step 4 : Commit**

```bash
git add app/templates/admin/conseil_form.html app/routes/admin.py
git commit -m "refactor: formulaire création conseil sans dépôt PDF"
```

---

## Task 4 : Créer la route `conseil_fiche` (GET/POST) et son template

> **Note :** `conseil_upload_pv` (Task 5) référence `admin.conseil_fiche` — créer d'abord la fiche pour que les deux puissent être testées ensemble.

**Fichiers :**
- Modifier : `app/routes/admin.py` (ajouter après `conseil_publier_odj`)
- Créer : `app/templates/admin/conseil_fiche.html`

> **Note :** `get_db` est déjà importé dans `admin.py` (~ligne 20). Pas besoin de l'ajouter.

- [ ] **Step 1 : Ajouter la route `conseil_fiche` dans `admin.py`**

```python
# Ajouter dans app/routes/admin.py après conseil_publier_odj (~ligne 2164)

@bp.route("/conseils/<int:conseil_id>", methods=["GET", "POST"])
@login_required
def conseil_fiche(conseil_id):
    import json as _json
    from datetime import date as _date
    from app.services.ai_service import is_ai_ready

    ville = ville_model.get_by_id(session.get("admin_ville_id"))
    conseil = conseil_model.get_by_id(conseil_id)
    if not conseil or conseil["ville_id"] != ville["id"]:
        abort(404)

    if request.method == "POST":
        bloc = request.form.get("bloc")

        if bloc == "avant_seance":
            titre = request.form.get("titre", "").strip()
            date_conseil = request.form.get("date_conseil", "").strip()
            type_conseil = request.form.get("type_conseil", "municipal")
            if not titre or not date_conseil:
                flash("Titre et date sont obligatoires.", "danger")
                return redirect(url_for("admin.conseil_fiche", conseil_id=conseil_id))
            # Reconstruire ODJ JSON depuis les champs point-by-point
            points = []
            i = 1
            while True:
                titre_point = request.form.get(f"odj_point_titre_{i}", "").strip()
                if not titre_point:
                    break
                desc = request.form.get(f"odj_point_description_{i}", "").strip()
                points.append({"numero": i, "titre": titre_point, "description": desc})
                i += 1
            if points:
                odj_texte = _json.dumps({"points": points}, ensure_ascii=False)
            else:
                # Fallback : textarea libre (uniquement en mode sans points structurés)
                odj_texte = request.form.get("odj_texte", "").strip() or None
            resume_avant = request.form.get("resume_avant_seance", "").strip() or None
            conseil_model.update(conseil_id, titre, date_conseil, None, type_conseil)
            conseil_model.set_statut_odj(
                conseil_id, conseil.get("statut_odj", "idle"),
                odj_texte=odj_texte, resume_avant_seance=resume_avant
            )
            flash("Informations enregistrées.", "success")

        elif bloc == "apres_seance":
            resume_citoyen = request.form.get("resume_citoyen", "").strip() or None
            with get_db() as conn:
                conn.execute(
                    "UPDATE conseils SET resume_citoyen=%s WHERE id=%s",
                    (resume_citoyen, conseil_id)
                )
                conn.commit()
            flash("Résumé citoyen enregistré.", "success")

        return redirect(url_for("admin.conseil_fiche", conseil_id=conseil_id))

    # GET
    conseil = conseil_model.get_by_id(conseil_id)
    odj = None
    odj_raw = conseil.get("odj_texte")
    if odj_raw:
        try:
            odj = _json.loads(odj_raw)
        except Exception:
            odj = None

    today = _date.today()
    date_conseil = conseil.get("date_conseil")
    after_seance_active = (date_conseil is None) or (date_conseil <= today)

    return render_template(
        "admin/conseil_fiche.html",
        ville=ville,
        conseil=conseil,
        odj=odj,
        ai_ready=is_ai_ready(),
        statut=_conseil_statut(conseil),
        prochaine_action=_conseil_prochaine_action(conseil),
        after_seance_active=after_seance_active,
    )
```

- [ ] **Step 2 : Créer `app/templates/admin/conseil_fiche.html`**

```html
{% extends "admin_base.html" %}
{% block title %}{{ conseil.titre }} — Admin{% endblock %}
{% block breadcrumb %} › <a href="{{ url_for('admin.conseils') }}" class="hover:text-gray-600">Conseils</a> › <span class="text-gray-800 font-medium truncate">{{ conseil.titre }}</span>{% endblock %}

{% block content %}

{# ── Stepper statut ── #}
{% set etapes = [
  ('nouveau',    'Créé'),
  ('odj_publie', 'ODJ publié'),
  ('pv_depose',  'PV déposé'),
  ('publie',     'Publié'),
] %}
{% set ordre = ['nouveau', 'odj_publie', 'pv_depose', 'publie'] %}
{% set statut_idx = ordre.index(statut) %}

<div class="flex items-center gap-0 mb-8 bg-white border border-gray-200 rounded-xl px-6 py-4 overflow-x-auto">
  {% for key, label in etapes %}
  {% set idx = loop.index0 %}
  <div class="flex items-center gap-2 flex-shrink-0">
    <div class="flex items-center gap-2">
      {% if idx < statut_idx %}
        <span class="w-6 h-6 rounded-full bg-emerald-500 flex items-center justify-center text-white text-xs">✓</span>
        <span class="text-sm font-medium text-emerald-600">{{ label }}</span>
      {% elif idx == statut_idx %}
        <span class="w-6 h-6 rounded-full bg-emerald-600 flex items-center justify-center text-white text-xs font-bold">{{ idx + 1 }}</span>
        <span class="text-sm font-semibold text-emerald-700">{{ label }}</span>
      {% else %}
        <span class="w-6 h-6 rounded-full bg-gray-200 flex items-center justify-center text-gray-400 text-xs">{{ idx + 1 }}</span>
        <span class="text-sm text-gray-400">{{ label }}</span>
      {% endif %}
    </div>
    {% if not loop.last %}
    <span class="mx-3 text-gray-300">→</span>
    {% endif %}
  </div>
  {% endfor %}
</div>

<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">

{# ══════════════════════════════════════════════ #}
{# Bloc AVANT SÉANCE #}
{# ══════════════════════════════════════════════ #}
<div>
  <h2 class="text-sm font-semibold text-amber-700 uppercase tracking-wide mb-3 flex items-center gap-2">
    <span class="w-2 h-2 rounded-full bg-amber-400 inline-block"></span> Avant séance
  </h2>

  <form method="POST" action="{{ url_for('admin.conseil_fiche', conseil_id=conseil.id) }}"
        class="space-y-4">
    <input type="hidden" name="_csrf" value="{{ csrf_token() }}">
    <input type="hidden" name="bloc" value="avant_seance">

    {# Infos de base #}
    <div class="bg-white border border-amber-200 rounded-xl p-5 space-y-3">
      <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wide">Informations</h3>
      <div>
        <label class="block text-xs font-medium text-gray-600 mb-1">Titre *</label>
        <input type="text" name="titre" value="{{ conseil.titre }}" required
               class="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-400">
      </div>
      <div class="flex gap-3">
        <div class="flex-1">
          <label class="block text-xs font-medium text-gray-600 mb-1">Date *</label>
          <input type="date" name="date_conseil"
                 value="{{ conseil.date_conseil | string | truncate(10, true, '') }}" required
                 class="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-400">
        </div>
        <div class="flex-1">
          <label class="block text-xs font-medium text-gray-600 mb-1">Type</label>
          <select name="type_conseil"
                  class="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-400">
            <option value="municipal" {% if conseil.type_conseil == 'municipal' %}selected{% endif %}>Municipal</option>
            <option value="metropolitain" {% if conseil.type_conseil == 'metropolitain' %}selected{% endif %}>Métropolitain</option>
          </select>
        </div>
      </div>
    </div>

    {# ODJ #}
    <div class="bg-white border border-amber-200 rounded-xl p-5">
      <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Ordre du jour</h3>

      {% if odj and odj.points %}
      {# Mode structuré — PAS de hidden input odj_texte ici, le serveur reconstruit depuis odj_point_titre_N #}
      <div id="odj-points" class="space-y-2 mb-3">
        {% for point in odj.points %}
        <div class="odj-point border border-gray-100 rounded-lg p-3 bg-gray-50" data-index="{{ loop.index }}">
          <div class="flex items-start gap-2">
            <span class="text-xs font-bold text-gray-400 mt-2 w-5 flex-shrink-0 odj-num">{{ loop.index }}</span>
            <div class="flex-1 space-y-1">
              <input type="text" name="odj_point_titre_{{ loop.index }}"
                     value="{{ point.titre }}" placeholder="Titre du point"
                     class="w-full px-2 py-1.5 border border-gray-200 rounded text-sm focus:outline-none focus:ring-1 focus:ring-amber-400">
              <input type="text" name="odj_point_description_{{ loop.index }}"
                     value="{{ point.description or '' }}" placeholder="Description (optionnel)"
                     class="w-full px-2 py-1.5 border border-gray-200 rounded text-xs text-gray-500 focus:outline-none focus:ring-1 focus:ring-amber-400">
            </div>
            <button type="button" onclick="supprimerPoint(this)"
                    class="text-red-400 hover:text-red-600 text-xs mt-2 flex-shrink-0">✕</button>
          </div>
        </div>
        {% endfor %}
      </div>
      {% else %}
      {# Mode fallback — textarea libre avec name=odj_texte #}
      <textarea name="odj_texte" rows="6" id="odj-texte-fallback"
                class="w-full border border-gray-200 rounded-lg px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-amber-400 resize-y"
                placeholder='{"points": [{"numero": 1, "titre": "...", "description": "..."}]}'>{{ conseil.odj_texte or '' }}</textarea>
      {% endif %}

      <button type="button" onclick="ajouterPoint()"
              class="mt-2 text-xs text-amber-600 hover:text-amber-800 font-medium">+ Ajouter un point</button>
    </div>

    {# Résumé avant séance #}
    <div class="bg-white border border-amber-200 rounded-xl p-5">
      <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Résumé citoyen — avant séance</h3>
      <textarea name="resume_avant_seance" rows="4"
                class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 resize-none"
                placeholder="Le prochain conseil municipal portera sur…">{{ conseil.resume_avant_seance or '' }}</textarea>
    </div>

    <button type="submit"
            class="w-full bg-amber-500 hover:bg-amber-600 text-white font-medium py-2.5 rounded-lg text-sm transition">
      Enregistrer (avant séance)
    </button>
  </form>

  {# Note de synthèse — hors du formulaire principal #}
  <div class="bg-white border border-amber-200 rounded-xl p-5 mt-4">
    <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2 flex items-center gap-2">
      <i class="ri-file-lock-line text-gray-400"></i> Note de synthèse (confidentielle)
    </h3>
    {% if conseil.note_synthese_pdf %}
    <p class="text-xs text-emerald-600 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2 mb-3">
      ✓ Déposée — {{ conseil.note_synthese_pdf[-30:] }}
    </p>
    {% endif %}
    <form method="POST" enctype="multipart/form-data"
          action="{{ url_for('admin.conseil_upload_note', conseil_id=conseil.id) }}"
          class="flex items-center gap-2 flex-wrap">
      <input type="hidden" name="_csrf" value="{{ csrf_token() }}">
      <input type="file" name="note_synthese_pdf" accept=".pdf"
             class="text-sm text-gray-600 file:mr-2 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-gray-100 file:text-gray-600 hover:file:bg-gray-200">
      <button type="submit"
              class="bg-gray-700 hover:bg-gray-800 text-white px-3 py-1.5 rounded-lg text-sm font-medium transition whitespace-nowrap">
        {% if conseil.note_synthese_pdf %}Remplacer{% else %}Déposer{% endif %}
      </button>
    </form>
    <p class="text-xs text-gray-400 mt-2">Ce fichier ne sera jamais rendu public.</p>
  </div>

  {# Analyse IA + publication ODJ #}
  {% if conseil.note_synthese_pdf %}
  <div class="bg-white border border-amber-200 rounded-xl p-5 mt-4 space-y-3">
    <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wide flex items-center gap-2">
      <i class="ri-sparkling-line text-emerald-500"></i> Analyse IA
      {% if not ai_ready %}<span class="text-red-400 font-normal">(API non configurée)</span>{% endif %}
    </h3>
    {% if conseil.statut_odj == 'en_cours' %}
    <div id="odj-progress-wrap">
      <div class="flex justify-between text-xs text-gray-500 mb-1">
        <span>Analyse en cours…</span>
        <span id="odj-pct">{{ conseil.progres_odj or 0 }}%</span>
      </div>
      <div class="bg-gray-100 rounded-full h-2">
        <div id="odj-bar" class="bg-emerald-500 h-2 rounded-full transition-all"
             style="width: {{ conseil.progres_odj or 0 }}%"></div>
      </div>
    </div>
    {% elif conseil.statut_odj == 'erreur' %}
    <p class="text-xs text-red-500">Erreur lors de l'analyse. Réessayez.</p>
    {% elif conseil.statut_odj == 'termine' %}
    <p class="text-xs text-emerald-600">✓ Analyse terminée. Vous pouvez relancer.</p>
    {% endif %}
    {% if ai_ready and conseil.statut_odj != 'en_cours' %}
    <form method="POST" action="{{ url_for('admin.conseil_analyser_odj', conseil_id=conseil.id) }}">
      <input type="hidden" name="_csrf" value="{{ csrf_token() }}">
      <button type="submit"
              class="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition">
        <i class="ri-sparkling-line mr-1"></i>
        {% if conseil.statut_odj == 'termine' %}Relancer l'analyse{% else %}Analyser avec l'IA{% endif %}
      </button>
    </form>
    {% endif %}

    {% if conseil.odj_texte or conseil.resume_avant_seance %}
    <form method="POST" action="{{ url_for('admin.conseil_publier_odj', conseil_id=conseil.id) }}">
      <input type="hidden" name="_csrf" value="{{ csrf_token() }}">
      <button type="submit"
              class="px-4 py-2 rounded-lg text-sm font-medium transition
                {% if conseil.odj_publie %}bg-emerald-100 text-emerald-700 hover:bg-emerald-200
                {% else %}bg-gray-100 text-gray-600 hover:bg-gray-200{% endif %}">
        {% if conseil.odj_publie %}✓ ODJ publié{% else %}Publier l'ODJ{% endif %}
      </button>
    </form>
    {% endif %}
  </div>
  {% endif %}
</div>

{# ══════════════════════════════════════════════ #}
{# Bloc APRÈS SÉANCE #}
{# ══════════════════════════════════════════════ #}
<div>
  <h2 class="text-sm font-semibold uppercase tracking-wide mb-3 flex items-center gap-2
      {% if after_seance_active %}text-blue-700{% else %}text-gray-400{% endif %}">
    <span class="w-2 h-2 rounded-full inline-block {% if after_seance_active %}bg-blue-400{% else %}bg-gray-300{% endif %}"></span>
    Après séance
    {% if not after_seance_active %}
    <span class="text-xs font-normal text-gray-400">(disponible après la date du conseil)</span>
    {% endif %}
  </h2>

  <div class="{% if not after_seance_active %}opacity-50 pointer-events-none select-none{% endif %} space-y-4">

    {# Dépôt PV #}
    <div class="bg-white border border-blue-200 rounded-xl p-5">
      <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Procès-verbal (PDF)</h3>
      {% if conseil.fichier_pdf %}
      <p class="text-xs text-emerald-600 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2 mb-3">
        ✓ Déposé — {{ conseil.fichier_pdf[-30:] }}
      </p>
      {% endif %}
      <form method="POST" enctype="multipart/form-data"
            action="{{ url_for('admin.conseil_upload_pv', conseil_id=conseil.id) }}">
        <input type="hidden" name="_csrf" value="{{ csrf_token() }}">
        <div class="flex items-center gap-2">
          <input type="file" name="fichier_pdf" accept=".pdf"
                 class="text-sm text-gray-600 file:mr-2 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-gray-100 file:text-gray-600 hover:file:bg-gray-200">
          <button type="submit"
                  class="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-lg text-sm font-medium transition whitespace-nowrap">
            {% if conseil.fichier_pdf %}Remplacer{% else %}Déposer{% endif %}
          </button>
        </div>
      </form>
    </div>

    {# Génération résumé IA #}
    {% if conseil.fichier_pdf %}
    <div class="bg-white border border-blue-200 rounded-xl p-5">
      <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2 flex items-center gap-2">
        <i class="ri-sparkling-line text-purple-500"></i> Résumé citoyen — IA
        {% if not ai_ready %}<span class="text-red-400 font-normal">(API non configurée)</span>{% endif %}
      </h3>
      {% if conseil.statut_resume == 'en_cours' %}
      <div class="mb-3">
        <div class="flex justify-between text-xs text-gray-500 mb-1">
          <span>Génération en cours…</span>
          <span id="resume-pct">{{ conseil.progres_resume or 0 }}%</span>
        </div>
        <div class="bg-gray-100 rounded-full h-2">
          <div id="resume-bar" class="bg-purple-500 h-2 rounded-full transition-all"
               style="width: {{ conseil.progres_resume or 0 }}%"></div>
        </div>
      </div>
      {% elif conseil.statut_resume == 'erreur' %}
      <p class="text-xs text-red-500 mb-2">Erreur lors de la génération. Réessayez.</p>
      {% elif conseil.statut_resume == 'termine' %}
      <p class="text-xs text-emerald-600 mb-2">✓ Génération terminée.</p>
      {% endif %}
      {% if ai_ready and conseil.statut_resume != 'en_cours' %}
      <form method="POST" action="{{ url_for('admin.conseil_generer_resume', conseil_id=conseil.id) }}">
        <input type="hidden" name="_csrf" value="{{ csrf_token() }}">
        <button type="submit"
                class="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition">
          <i class="ri-sparkling-line mr-1"></i>
          {% if conseil.statut_resume == 'termine' %}Relancer{% else %}Générer le résumé{% endif %}
        </button>
      </form>
      {% endif %}
    </div>
    {% endif %}

    {# Résumé citoyen éditable #}
    <form method="POST" action="{{ url_for('admin.conseil_fiche', conseil_id=conseil.id) }}">
      <input type="hidden" name="_csrf" value="{{ csrf_token() }}">
      <input type="hidden" name="bloc" value="apres_seance">
      <div class="bg-white border border-blue-200 rounded-xl p-5">
        <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Résumé citoyen</h3>
        <textarea name="resume_citoyen" rows="8" id="resume-citoyen"
                  class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 resize-y"
                  placeholder="Synthèse du conseil pour les citoyens…">{{ conseil.resume_citoyen or '' }}</textarea>
      </div>
      <button type="submit"
              class="w-full mt-3 bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 rounded-lg text-sm transition">
        Enregistrer (après séance)
      </button>
    </form>

    {# Publication conseil #}
    <form method="POST" action="{{ url_for('admin.conseil_publier', conseil_id=conseil.id) }}">
      <input type="hidden" name="_csrf" value="{{ csrf_token() }}">
      <button type="submit"
              class="w-full px-4 py-2.5 rounded-lg text-sm font-medium transition
                {% if conseil.publie %}bg-emerald-100 text-emerald-700 hover:bg-emerald-200 border border-emerald-300
                {% else %}bg-gray-100 text-gray-600 hover:bg-gray-200 border border-gray-300{% endif %}">
        {% if conseil.publie %}✓ Conseil publié — Dépublier{% else %}Publier le compte-rendu{% endif %}
      </button>
    </form>

  </div>{# fin opacity wrapper #}
</div>

</div>{# fin grid #}

{% endblock %}

{% block scripts %}
<script>
// ── Compteur de points ODJ ──
var _pointCount = document.querySelectorAll('.odj-point').length;

function ajouterPoint() {
  _pointCount++;
  var idx = _pointCount;
  var container = document.getElementById('odj-points');
  if (!container) {
    // Mode fallback : créer le container et cacher la textarea
    var ta = document.getElementById('odj-texte-fallback');
    if (ta) {
      var div = document.createElement('div');
      div.id = 'odj-points';
      div.className = 'space-y-2 mb-3';
      ta.parentNode.insertBefore(div, ta);
      ta.style.display = 'none';
      ta.name = '';  // désactiver le champ fallback pour éviter conflit
      container = div;
      _pointCount = 1;
      idx = 1;
    }
  }
  if (!container) return;
  var html = '<div class="odj-point border border-gray-100 rounded-lg p-3 bg-gray-50" data-index="' + idx + '">' +
    '<div class="flex items-start gap-2">' +
    '<span class="text-xs font-bold text-gray-400 mt-2 w-5 flex-shrink-0 odj-num">' + idx + '</span>' +
    '<div class="flex-1 space-y-1">' +
    '<input type="text" name="odj_point_titre_' + idx + '" placeholder="Titre du point" class="w-full px-2 py-1.5 border border-gray-200 rounded text-sm focus:outline-none focus:ring-1 focus:ring-amber-400">' +
    '<input type="text" name="odj_point_description_' + idx + '" placeholder="Description (optionnel)" class="w-full px-2 py-1.5 border border-gray-200 rounded text-xs text-gray-500 focus:outline-none focus:ring-1 focus:ring-amber-400">' +
    '</div>' +
    '<button type="button" onclick="supprimerPoint(this)" class="text-red-400 hover:text-red-600 text-xs mt-2 flex-shrink-0">✕</button>' +
    '</div></div>';
  container.insertAdjacentHTML('beforeend', html);
}

function supprimerPoint(btn) {
  btn.closest('.odj-point').remove();
  renumeroterPoints();
}

function renumeroterPoints() {
  var points = document.querySelectorAll('.odj-point');
  points.forEach(function(p, i) {
    var num = i + 1;
    p.setAttribute('data-index', num);
    var numSpan = p.querySelector('.odj-num');
    if (numSpan) numSpan.textContent = num;
    var inputs = p.querySelectorAll('input[type=text]');
    if (inputs[0]) inputs[0].name = 'odj_point_titre_' + num;
    if (inputs[1]) inputs[1].name = 'odj_point_description_' + num;
  });
  _pointCount = points.length;
}

// ── Polling statut IA — ODJ ──
(function() {
  var statut = "{{ conseil.statut_odj }}";
  if (statut !== 'en_cours') return;
  var bar = document.getElementById('odj-bar');
  var pct = document.getElementById('odj-pct');
  var url = "{{ url_for('admin.conseil_statut_odj', conseil_id=conseil.id) }}";
  var timer = setInterval(function() {
    fetch(url).then(function(r) { return r.json(); }).then(function(d) {
      if (bar && d.progres != null) { bar.style.width = d.progres + '%'; if (pct) pct.textContent = d.progres + '%'; }
      if (d.statut === 'termine' || d.statut === 'erreur') { clearInterval(timer); window.location.reload(); }
    });
  }, 2000);
})();

// ── Polling statut IA — Résumé ──
(function() {
  var statut = "{{ conseil.statut_resume }}";
  if (statut !== 'en_cours') return;
  var bar = document.getElementById('resume-bar');
  var pct = document.getElementById('resume-pct');
  var rta = document.getElementById('resume-citoyen');
  var url = "{{ url_for('admin.conseil_statut_resume', conseil_id=conseil.id) }}";
  var timer = setInterval(function() {
    fetch(url).then(function(r) { return r.json(); }).then(function(d) {
      if (bar && d.progres != null) { bar.style.width = d.progres + '%'; if (pct) pct.textContent = d.progres + '%'; }
      if (d.statut === 'termine' || d.statut === 'erreur') {
        clearInterval(timer);
        if (d.statut === 'termine' && rta && d.resume) rta.value = d.resume;
        window.location.reload();
      }
    });
  }, 2000);
})();
</script>
{% endblock %}
```

- [ ] **Step 3 : Vérifier manuellement**

Accéder à `/admin/conseils/<id>` sur un conseil existant → stepper visible, deux blocs, formulaires fonctionnels.

- [ ] **Step 4 : Commit**

```bash
git add app/routes/admin.py app/templates/admin/conseil_fiche.html
git commit -m "feat: fiche conseil unique avec pipeline de statut"
```

---

## Task 5 : Nouveau endpoint `conseil_upload_pv` (POST /pv-pdf)

**Fichiers :**
- Modifier : `app/routes/admin.py` (ajouter après `conseil_publier_odj`)

> **Note :** Cette route référence `admin.conseil_fiche` — créée à la Task 4, donc testable maintenant.

- [ ] **Step 1 : Ajouter la route `conseil_upload_pv`**

```python
# Ajouter dans app/routes/admin.py après conseil_publier_odj (~ligne 2164)

@bp.route("/conseils/<int:conseil_id>/pv-pdf", methods=["POST"])
@login_required
def conseil_upload_pv(conseil_id):
    ville = ville_model.get_by_id(session.get("admin_ville_id"))
    conseil = conseil_model.get_by_id(conseil_id)
    if not conseil or conseil["ville_id"] != ville["id"]:
        abort(404)
    fichier = request.files.get("fichier_pdf")
    if not fichier or not fichier.filename:
        flash("Aucun fichier fourni.", "danger")
        return redirect(url_for("admin.conseil_fiche", conseil_id=conseil_id))
    if not fichier.filename.lower().endswith(".pdf") or not _is_valid_pdf(fichier):
        flash("Seuls les PDFs valides sont acceptés.", "danger")
        return redirect(url_for("admin.conseil_fiche", conseil_id=conseil_id))
    if conseil.get("fichier_pdf"):
        old = os.path.join(CONSEILS_UPLOAD_DIR, conseil["fichier_pdf"])
        if os.path.exists(old):
            os.remove(old)
    filename = _save_pdf(fichier)
    conseil_model.update(conseil_id, conseil["titre"], str(conseil["date_conseil"]), filename, conseil["type_conseil"])
    flash("PV déposé.", "success")
    return redirect(url_for("admin.conseil_fiche", conseil_id=conseil_id))
```

- [ ] **Step 2 : Vérifier manuellement**

Depuis la fiche `/admin/conseils/<id>`, déposer un PDF dans le bloc "Après séance" → flash "PV déposé", badge apparaît.

- [ ] **Step 3 : Commit**

```bash
git add app/routes/admin.py
git commit -m "feat: endpoint conseil_upload_pv POST /pv-pdf"
```

---

## Task 6 : Refactorer la liste `conseils.html`

**Fichiers :**
- Modifier : `app/templates/admin/conseils.html`

La liste passe les données de statut via le template, calculées dans la route. Il faut d'abord enrichir la route `conseils()`.

- [ ] **Step 1 : Enrichir la route `conseils()` avec statut et prochaine action**

```python
# Dans app/routes/admin.py, modifier la route conseils() :

@bp.route("/conseils")
@login_required
def conseils():
    ville = ville_model.get_by_id(session.get("admin_ville_id"))
    if not ville:
        flash("Aucune ville sélectionnée.", "danger")
        return redirect(url_for("admin.dashboard"))
    items = conseil_model.get_all(ville["id"])
    # Enrichir chaque conseil avec statut et prochaine action
    for c in items:
        c["_statut"] = _conseil_statut(c)
        c["_prochaine_action"] = _conseil_prochaine_action(c)
    return render_template("admin/conseils.html", ville=ville, conseils=items)
```

- [ ] **Step 2 : Réécrire `conseils.html`**

```html
{% extends "admin_base.html" %}
{% block title %}Conseils — Admin{% endblock %}

{% block content %}
<div class="flex items-center justify-between mb-6">
  <h1 class="text-2xl font-bold text-gray-900">Conseils</h1>
  <a href="{{ url_for('admin.conseil_nouveau') }}"
     class="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition">
    + Ajouter un conseil
  </a>
</div>

{# ── Prochain conseil ── #}
<div class="bg-white rounded-xl border border-gray-200 p-4 mb-6 flex items-center gap-4">
  <div class="flex-1">
    <p class="text-sm font-medium text-gray-700 mb-1">Prochain conseil municipal</p>
    <p class="text-xs text-gray-400">Affiché en encart sur la page d'accueil jusqu'à la date passée.</p>
  </div>
  <form method="POST" action="{{ url_for('admin.conseil_prochain_update') }}" class="flex items-center gap-2 flex-wrap">
    <input type="hidden" name="_csrf" value="{{ csrf_token() }}">
    <input type="date" name="prochain_conseil"
           value="{{ ville.prochain_conseil | string | truncate(10, true, '') if ville.prochain_conseil else '' }}"
           class="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500">
    <input type="time" name="prochain_conseil_heure"
           value="{{ ville.prochain_conseil_heure | heure_fr if ville.prochain_conseil_heure else '' }}"
           placeholder="HH:MM"
           class="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 w-28">
    <button type="submit"
            class="bg-emerald-600 hover:bg-emerald-700 text-white px-3 py-1.5 rounded-lg text-sm font-medium transition">
      Enregistrer
    </button>
  </form>
</div>

{% set municipaux = conseils | selectattr('type_conseil', 'equalto', 'municipal') | list %}
{% set metropolitains = conseils | selectattr('type_conseil', 'equalto', 'metropolitain') | list %}

{% macro statut_badge(c) %}
{% if c._statut == 'publie' %}
  <span class="px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700">Publié</span>
{% elif c._statut == 'pv_depose' %}
  <span class="px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700">PV déposé</span>
{% elif c._statut == 'odj_publie' %}
  <span class="px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700">ODJ publié</span>
{% else %}
  <span class="px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500">Nouveau</span>
{% endif %}
{% endmacro %}

{% macro conseil_table(items) %}
{% if items %}
<div class="bg-white rounded-xl border border-gray-200 overflow-hidden">
  <table class="w-full text-sm">
    <thead class="bg-gray-50 text-gray-500 text-xs uppercase tracking-wide">
      <tr>
        <th class="px-4 py-3 text-left">Date</th>
        <th class="px-4 py-3 text-left">Titre</th>
        <th class="px-4 py-3 text-left">Statut</th>
        <th class="px-4 py-3 text-left text-gray-400 font-normal">Prochaine action</th>
        <th class="px-4 py-3 text-right">Actions</th>
      </tr>
    </thead>
    <tbody class="divide-y divide-gray-100">
      {% for c in items %}
      <tr class="hover:bg-gray-50">
        <td class="px-4 py-3 text-gray-600 whitespace-nowrap">{{ c.date_conseil | date_fr }}</td>
        <td class="px-4 py-3 font-medium text-gray-900">{{ c.titre }}</td>
        <td class="px-4 py-3">{{ statut_badge(c) }}</td>
        <td class="px-4 py-3 text-xs text-gray-400 italic">{{ c._prochaine_action or '—' }}</td>
        <td class="px-4 py-3 text-right">
          <div class="flex items-center justify-end gap-3">
            <a href="{{ url_for('admin.conseil_fiche', conseil_id=c.id) }}"
               class="bg-gray-800 hover:bg-gray-900 text-white px-3 py-1.5 rounded-lg text-xs font-medium transition">
              Gérer →
            </a>
            <form method="POST" action="{{ url_for('admin.conseil_supprimer', conseil_id=c.id) }}"
                  onsubmit="return confirm('Supprimer ce conseil ?')">
              <input type="hidden" name="_csrf" value="{{ csrf_token() }}">
              <button type="submit" class="text-red-400 hover:text-red-600 text-xs">Supprimer</button>
            </form>
          </div>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% else %}
<p class="text-sm text-gray-400 italic px-1">Aucun conseil ajouté.</p>
{% endif %}
{% endmacro %}

{# ── Municipaux ── #}
<div class="mb-8">
  <h2 class="text-base font-semibold text-gray-700 mb-3 flex items-center gap-2">
    🏛️ Conseils municipaux
    {% if municipaux %}<span class="text-xs font-normal text-gray-400">({{ municipaux | length }})</span>{% endif %}
  </h2>
  {{ conseil_table(municipaux) }}
</div>

{# ── Métropolitains ── #}
<div>
  <h2 class="text-base font-semibold text-gray-700 mb-3 flex items-center gap-2">
    🏙️ Conseils métropolitains
    {% if metropolitains %}<span class="text-xs font-normal text-gray-400">({{ metropolitains | length }})</span>{% endif %}
  </h2>
  {{ conseil_table(metropolitains) }}
</div>

{% if not conseils %}
<div class="bg-white rounded-xl border border-gray-200 p-12 text-center text-gray-400">
  <div class="text-4xl mb-3">🏛️</div>
  <p class="text-sm">Aucun conseil ajouté pour l'instant.</p>
  <a href="{{ url_for('admin.conseil_nouveau') }}"
     class="mt-4 inline-block text-emerald-600 hover:text-emerald-800 text-sm font-medium">
    Ajouter le premier →
  </a>
</div>
{% endif %}
{% endblock %}
```

- [ ] **Step 3 : Vérifier manuellement**

Aller sur `/admin/conseils` → liste avec badges statut et colonne "prochaine action".

- [ ] **Step 4 : Commit**

```bash
git add app/templates/admin/conseils.html app/routes/admin.py
git commit -m "refactor: liste conseils avec statut et prochaine action"
```

---

## Task 7 : Rediriger les anciennes routes vers la fiche

> **Important :** Les Steps 1 à 4 doivent être réalisés dans le même commit (Step 6). Ne pas committer entre les steps — un commit partiel laisserait des redirects en double ou des routes pointant vers des cibles supprimées.

**Fichiers :**
- Modifier : `app/routes/admin.py`

- [ ] **Step 1 : Remplacer `conseil_modifier` par un redirect**

> **Note :** La conversion de `conseil_modifier` GET+POST en redirect est sûre **à ce stade** car : (a) le template `conseil_form.html` n'est plus rendu via `conseil_modifier` (Task 3 a supprimé le champ PDF et Task 7 a retiré le bouton "Modifier" de la liste), et (b) la fiche `conseil_fiche` est maintenant l'unique point d'entrée pour l'édition. L'ancien POST handler qui sauvegardait `fichier_pdf` est remplacé par `conseil_upload_pv` (Task 5). Si une URL `/modifier` bookmarkée soumet un ancien formulaire POST, elle sera redirigée silencieusement vers la fiche — acceptable.

```python
# Remplacer la fonction conseil_modifier entière par :

@bp.route("/conseils/<int:conseil_id>/modifier", methods=["GET", "POST"])
@login_required
def conseil_modifier(conseil_id):
    return redirect(url_for("admin.conseil_fiche", conseil_id=conseil_id))
```

- [ ] **Step 2 : Remplacer `conseil_preparation` par un redirect**

```python
# Remplacer la route conseil_preparation GET par un redirect simple.
# Garder les sous-routes (note-synthese, analyser-odj, statut-odj, publier-odj) intactes.

@bp.route("/conseils/<int:conseil_id>/preparation", methods=["GET", "POST"])
@login_required
def conseil_preparation(conseil_id):
    return redirect(url_for("admin.conseil_fiche", conseil_id=conseil_id))
```

- [ ] **Step 3 : Remplacer le GET de `conseil_resume` par un redirect**

```python
# Remplacer la route conseil_resume entière (GET + POST) par un redirect :

@bp.route("/conseils/<int:conseil_id>/resume", methods=["GET", "POST"])
@login_required
def conseil_resume(conseil_id):
    return redirect(url_for("admin.conseil_fiche", conseil_id=conseil_id))
```

- [ ] **Step 4 : Mettre à jour les redirects des endpoints d'action**

Dans `app/routes/admin.py`, mettre à jour les redirections des endpoints suivants pour pointer vers `admin.conseil_fiche` :

**`conseil_publier`** (~ligne 1881) :
```python
# Avant
return redirect(url_for("admin.conseils"))
# Après
return redirect(url_for("admin.conseil_fiche", conseil_id=conseil_id))
```

**`conseil_analyser_odj`** (~ligne 2099, et les flashs d'erreur ~2065-2075) :
```python
# Toutes les branches return redirect(...) → remplacer par :
return redirect(url_for("admin.conseil_fiche", conseil_id=conseil_id))
```

**`conseil_generer_resume`** (~ligne 1945, et les flashs d'erreur ~1910-1921) :
```python
# Toutes les branches return redirect(...) → remplacer par :
return redirect(url_for("admin.conseil_fiche", conseil_id=conseil_id))
```

**`conseil_upload_note`** (~lignes 2042, 2045, 2054) — toutes les branches (les 3 `return redirect(...)`) :
```python
return redirect(url_for("admin.conseil_fiche", conseil_id=conseil_id))
```

**`conseil_publier_odj`** (~ligne 2163) :
```python
return redirect(url_for("admin.conseil_fiche", conseil_id=conseil_id))
```

- [ ] **Step 5 : Vérifier manuellement**

Accéder aux anciennes URLs `/modifier`, `/preparation`, `/resume` → doit rediriger vers `/admin/conseils/<id>`.
Tester le bouton "Publier" depuis la fiche → doit rester sur la fiche.

- [ ] **Step 6 : Commit**

```bash
git add app/routes/admin.py
git commit -m "refactor: anciennes routes conseil redirigent vers la fiche unique"
```

---

## Task 8 : Build et déploiement dev + validation finale

- [ ] **Step 1 : Rebuild le container dev**

```bash
docker stop boussole-dev-test 2>/dev/null; docker rm boussole-dev-test 2>/dev/null
docker compose -f docker-compose.dev.yml build
docker run -d --name boussole-dev-test \
  --network boussolecommune_default \
  -p 127.0.0.1:5002:5000 \
  -v /home/ubuntu/boussolecommune/uploads:/app/uploads \
  --env-file /home/ubuntu/boussolecommune/.env \
  -e FLASK_ENV=development \
  boussolecommune-web-dev
```

- [ ] **Step 2 : Vérification fonctionnelle complète**

Checklist manuelle sur http://localhost:5002 :
- [ ] Créer un nouveau conseil → pas de champ PDF → redirige vers la liste
- [ ] Cliquer "Gérer →" → ouvre la fiche avec stepper "Créé"
- [ ] Enregistrer "avant séance" → flash succès, reste sur la fiche
- [ ] Déposer une note de synthèse → badge "Déposée"
- [ ] Lancer analyse IA (si API configurée) → barre de progression
- [ ] Publier ODJ → stepper passe à "ODJ publié"
- [ ] Modifier la date vers une date passée → bloc "Après séance" s'active
- [ ] Déposer un PV → statut "PV déposé" dans la liste
- [ ] Générer résumé → barre de progression dans le bloc après séance
- [ ] Publier conseil → statut "Publié" dans la liste
- [ ] Supprimer un conseil avec note de synthèse → vérifier que le fichier est supprimé
- [ ] Accéder à `/conseils/<id>/modifier` → redirige vers la fiche

- [ ] **Step 3 : Push sur la branche dev**

```bash
git push origin dev
```

- [ ] **Step 4 : Notifier l'utilisateur pour validation sur dev.sautronautrement.fr**
