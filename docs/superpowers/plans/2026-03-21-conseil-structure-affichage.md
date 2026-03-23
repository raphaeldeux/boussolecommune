# Conseil Structure — Affichage thématique Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Groq génère un JSON structuré (thèmes + délibérations + votes) en plus du résumé texte, et la page publique affiche des cartes visuelles par thème.

**Architecture:** Deux appels Groq séquentiels dans le thread background — un pour la prose, un pour le JSON. Le JSON est stocké dans une nouvelle colonne `resume_structure TEXT`. La route publique pré-parse le JSON en dict Python avant de le passer au template.

**Tech Stack:** Flask 3.0, PostgreSQL 16 (psycopg2), Groq API (requests), Tailwind CSS, Jinja2.

---

## File Map

| File | Action | Responsabilité |
|------|--------|---------------|
| `app/database.py` | Modify | Ajouter colonne `resume_structure` via `_column_exists` |
| `app/models/conseil.py` | Modify | Étendre `set_statut_resume` avec param `resume_structure` |
| `app/services/ollama_service.py` | Modify | Ajouter `PROMPT_STRUCTURE`, second appel Groq, retourner tuple |
| `app/routes/admin.py` | Modify | Thread `_run()` passe le tuple ; endpoint `/statut-resume` retourne `structure` parsé |
| `app/routes/public.py` | Modify | Route `conseil_detail` pré-parse `resume_structure` → dict `structure` |
| `app/templates/public/conseil_detail.html` | Modify | Cartes thématiques avec délibérations et badges de vote |

---

### Task 1: Colonne `resume_structure` en base

**Files:**
- Modify: `app/database.py`

- [ ] **Step 1: Lire les lignes 382–400 de `app/database.py`** pour confirmer l'emplacement exact après le `conn.commit()` de la table `conseils` et après le bloc `statut_resume` ajouté précédemment (qui se termine autour de la ligne 394).

- [ ] **Step 2: Ajouter la migration** immédiatement après la ligne `conn.commit()` qui suit le reset `statut_resume` (vers ligne 394), avant le commentaire `# Table documents publics` :

```python
    if not _column_exists(conn, "conseils", "resume_structure"):
        conn.execute(
            "ALTER TABLE conseils ADD COLUMN resume_structure TEXT DEFAULT NULL"
        )
        conn.commit()
```

- [ ] **Step 3: Déployer et vérifier**

```bash
docker cp app/database.py boussolecommune-web-1:/app/app/database.py
docker restart boussolecommune-web-1
docker logs boussolecommune-web-1 --tail 10
```
Expected: Gunicorn démarre sans erreur.

```bash
docker exec boussolecommune-db-1 psql -U boussole -d boussolecommune -c "\d conseils"
```
Expected: colonne `resume_structure | text` présente.

- [ ] **Step 4: Commit**

```bash
git add app/database.py
git commit -m "feat: add resume_structure column to conseils table"
```

---

### Task 2: Étendre `set_statut_resume` dans le modèle

**Files:**
- Modify: `app/models/conseil.py`

- [ ] **Step 1: Remplacer la fonction `set_statut_resume` existante** par cette version avec clause SET dynamique :

```python
def set_statut_resume(conseil_id, statut, resume_citoyen=None, resume_structure=None):
    """Met à jour statut_resume et optionnellement resume_citoyen et/ou resume_structure."""
    champs = [("statut_resume", statut)]
    if resume_citoyen is not None:
        champs.append(("resume_citoyen", resume_citoyen))
    if resume_structure is not None:
        champs.append(("resume_structure", resume_structure))
    set_clause = ", ".join(f"{col}=%s" for col, _ in champs)
    valeurs = [val for _, val in champs] + [conseil_id]
    with get_db() as conn:
        conn.execute(
            f"UPDATE conseils SET {set_clause} WHERE id=%s",
            valeurs
        )
        conn.commit()
```

- [ ] **Step 2: Vérifier la syntaxe**

```bash
docker cp app/models/conseil.py boussolecommune-web-1:/app/app/models/conseil.py
docker exec boussolecommune-web-1 python -c "import app.models.conseil; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/models/conseil.py
git commit -m "feat: extend set_statut_resume with dynamic SET clause for resume_structure"
```

---

### Task 3: Second appel Groq pour JSON structuré

**Files:**
- Modify: `app/services/ollama_service.py`

- [ ] **Step 1: Ajouter `PROMPT_STRUCTURE`** après `PROMPT_TEMPLATE` (ligne ~30) :

```python
PROMPT_STRUCTURE = """Tu es un assistant qui extrait les délibérations d'un procès-verbal de conseil municipal.

Voici le contenu du procès-verbal :

{contenu}

---

Génère un JSON structuré représentant les thématiques et délibérations. Réponds UNIQUEMENT avec du JSON valide, sans texte avant ni après.

Format attendu :
{{
  "themes": [
    {{
      "titre": "Nom de la thématique",
      "resume": "Résumé de synthèse en 2-4 phrases accessibles aux citoyens.",
      "deliberations": [
        {{
          "titre": "Intitulé de la délibération",
          "description": "Description claire de la décision prise.",
          "vote": {{"pour": 15, "contre": 2, "abstentions": 1}}
        }}
      ]
    }}
  ]
}}

Règles :
- "vote" est null si aucun vote n'est mentionné
- "deliberations" peut être [] si le thème n'a pas de délibération formelle
- N'inclure que les thèmes réellement présents dans le document
- Répondre UNIQUEMENT avec le JSON, sans explication"""
```

- [ ] **Step 2: Modifier `generer_resume`** pour retourner un tuple `(str, str | None)` :

Remplacer la fonction `generer_resume` existante par :

```python
def generer_resume(pdf_path: str):
    """
    Extrait le texte du PDF et génère résumé + structure JSON.
    Retourne un tuple (resume_texte: str, resume_structure: str | None).
    """
    import json as _json

    texte = extract_text_from_pdf(pdf_path)
    if not texte.strip():
        raise ValueError("Le PDF ne contient pas de texte extractible.")

    texte_tronque = texte[:12000]

    # Premier appel : résumé en prose
    prompt_prose = PROMPT_TEMPLATE.format(contenu=texte_tronque)
    if GROQ_API_KEY:
        resume_texte = _generer_via_groq(prompt_prose)
    else:
        resume_texte = _generer_via_ollama(prompt_prose)

    # Deuxième appel : JSON structuré (enrichissement optionnel)
    resume_structure = None
    if GROQ_API_KEY:
        try:
            prompt_json = PROMPT_STRUCTURE.format(contenu=texte_tronque)
            raw_json = _generer_via_groq(prompt_json)
            # Validation
            parsed = _json.loads(raw_json)
            if "themes" in parsed:
                resume_structure = raw_json
        except Exception as e:
            print(f"[WARN] Génération JSON structuré échouée : {e}", flush=True)

    return resume_texte, resume_structure
```

- [ ] **Step 3: Déployer et tester la syntaxe**

```bash
docker cp app/services/ollama_service.py boussolecommune-web-1:/app/app/services/ollama_service.py
docker exec boussolecommune-web-1 python -c "from app.services.ollama_service import generer_resume; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app/services/ollama_service.py
git commit -m "feat: second Groq call generates structured JSON (themes + deliberations + votes)"
```

---

### Task 4: Mettre à jour le thread admin et l'endpoint status

**Files:**
- Modify: `app/routes/admin.py`

- [ ] **Step 1: Mettre à jour la fonction `_run()`** dans `conseil_generer_resume` (autour de la ligne 1419).

Remplacer :
```python
    def _run():
        from app.services.ollama_service import generer_resume
        try:
            resume = generer_resume(pdf_path)
            conseil_model.set_statut_resume(conseil_id, "termine", resume_citoyen=resume)
        except Exception:
            conseil_model.set_statut_resume(conseil_id, "erreur")
```

Par :
```python
    def _run():
        from app.services.ollama_service import generer_resume
        try:
            resume_texte, resume_structure = generer_resume(pdf_path)
            conseil_model.set_statut_resume(
                conseil_id, "termine",
                resume_citoyen=resume_texte,
                resume_structure=resume_structure,
            )
        except Exception:
            conseil_model.set_statut_resume(conseil_id, "erreur")
```

- [ ] **Step 2: Mettre à jour `conseil_statut_resume`** pour retourner `structure` parsé.

Remplacer la fonction existante par :
```python
@bp.route("/conseils/<int:conseil_id>/statut-resume", methods=["GET"])
@login_required
def conseil_statut_resume(conseil_id):
    import json as _json
    ville = ville_model.get_by_id(session.get("admin_ville_id"))
    if not ville:
        abort(403)
    conseil = conseil_model.get_by_id(conseil_id)
    if not conseil or conseil["ville_id"] != ville["id"]:
        abort(404)
    raw_structure = conseil.get("resume_structure")
    structure = None
    if raw_structure:
        try:
            structure = _json.loads(raw_structure)
        except Exception:
            structure = None
    return jsonify({
        "statut": conseil.get("statut_resume", "idle"),
        "resume": conseil.get("resume_citoyen"),
        "structure": structure,
    })
```

- [ ] **Step 3: Déployer et vérifier**

```bash
docker cp app/routes/admin.py boussolecommune-web-1:/app/app/routes/admin.py
docker restart boussolecommune-web-1
docker logs boussolecommune-web-1 --tail 10
```
Expected: Gunicorn démarre sans erreur.

- [ ] **Step 4: Commit**

```bash
git add app/routes/admin.py
git commit -m "feat: thread saves resume_structure, status endpoint returns parsed structure"
```

---

### Task 5: Pré-parser `resume_structure` dans la route publique

**Files:**
- Modify: `app/routes/public.py` (autour de la ligne 532–542)

- [ ] **Step 1: Mettre à jour `conseil_detail`** pour pré-parser `resume_structure` :

Remplacer :
```python
@bp.route("/v/<ville_slug>/conseils/<int:conseil_id>")
def conseil_detail(ville_slug, conseil_id):
    """Détail d'un conseil municipal."""
    import app.models.conseil as conseil_model
    ville = ville_model.get_by_slug(ville_slug)
    if not ville:
        abort(404)
    conseil = conseil_model.get_by_id(conseil_id)
    if not conseil or conseil["ville_id"] != ville["id"] or not conseil["publie"]:
        abort(404)
    return render_template("public/conseil_detail.html", ville=ville, conseil=conseil)
```

Par :
```python
@bp.route("/v/<ville_slug>/conseils/<int:conseil_id>")
def conseil_detail(ville_slug, conseil_id):
    """Détail d'un conseil municipal."""
    import json as _json
    import app.models.conseil as conseil_model
    ville = ville_model.get_by_slug(ville_slug)
    if not ville:
        abort(404)
    conseil = conseil_model.get_by_id(conseil_id)
    if not conseil or conseil["ville_id"] != ville["id"] or not conseil["publie"]:
        abort(404)
    structure = None
    raw = conseil.get("resume_structure")
    if raw:
        try:
            parsed = _json.loads(raw)
            if isinstance(parsed, dict) and "themes" in parsed:
                structure = parsed
        except Exception:
            structure = None
    return render_template("public/conseil_detail.html", ville=ville, conseil=conseil, structure=structure)
```

- [ ] **Step 2: Déployer et vérifier la syntaxe**

```bash
docker cp app/routes/public.py boussolecommune-web-1:/app/app/routes/public.py
docker exec boussolecommune-web-1 python -c "from app.routes.public import bp; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/routes/public.py
git commit -m "feat: pre-parse resume_structure in conseil_detail route"
```

---

### Task 6: Template public — cartes thématiques

**Files:**
- Modify: `app/templates/public/conseil_detail.html`

- [ ] **Step 1: Remplacer entièrement `conseil_detail.html`** par :

```html
{% extends "base.html" %}
{% block title %}{{ conseil.titre }} · {{ ville.nom }}{% endblock %}

{% block content %}
<div class="max-w-3xl mx-auto">

  <!-- Fil d'Ariane -->
  <div class="flex items-center gap-2 text-sm text-gray-400 mb-5">
    <a href="{{ url_for('public.conseils', ville_slug=ville.slug) }}" class="hover:text-emerald-600 transition">Conseils municipaux</a>
    <span>›</span>
    <span class="text-gray-600 truncate">{{ conseil.titre }}</span>
  </div>

  <!-- Header -->
  <div class="bg-white rounded-xl border border-gray-200 p-6 mb-5">
    <div class="flex items-start gap-4">
      <div class="flex-shrink-0 w-12 h-12 bg-emerald-50 rounded-lg flex items-center justify-center text-2xl">🏛️</div>
      <div class="flex-1 min-w-0">
        <h1 class="text-xl font-bold text-gray-900">{{ conseil.titre }}</h1>
        <div class="text-sm text-gray-400 mt-1">{{ conseil.date_conseil }}</div>
      </div>
    </div>
    {% if conseil.fichier_pdf %}
    <div class="mt-4 pt-4 border-t border-gray-100">
      <a href="{{ url_for('static', filename='conseils/' + conseil.fichier_pdf) }}"
         target="_blank"
         class="inline-flex items-center gap-2 text-sm text-emerald-600 hover:text-emerald-800 font-medium transition">
        📄 Télécharger le procès-verbal (PDF)
      </a>
    </div>
    {% endif %}
  </div>

  {% if structure and structure.themes %}
  <!-- Affichage structuré par thème -->
  <div class="space-y-4">
    {% for theme in structure.themes %}
    <div class="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <!-- En-tête du thème -->
      <div class="px-6 py-4 border-b border-gray-100 bg-gray-50">
        <h2 class="text-base font-semibold text-gray-900">{{ theme.titre }}</h2>
        {% if theme.resume %}
        <p class="text-sm text-gray-600 mt-1 leading-relaxed">{{ theme.resume }}</p>
        {% endif %}
      </div>

      {% if theme.deliberations %}
      <!-- Liste des délibérations -->
      <div class="divide-y divide-gray-50">
        {% for delib in theme.deliberations %}
        <div class="px-6 py-4">
          <div class="flex items-start justify-between gap-4">
            <div class="flex-1 min-w-0">
              <p class="text-sm font-medium text-gray-900">{{ delib.titre }}</p>
              {% if delib.description %}
              <p class="text-sm text-gray-500 mt-1 leading-relaxed">{{ delib.description }}</p>
              {% endif %}
            </div>
            {% if delib.vote %}
            {% set vote = delib.vote %}
            {% set majority = vote.pour > vote.contre %}
            <div class="flex-shrink-0">
              <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium
                {% if majority %}bg-emerald-50 text-emerald-700 border border-emerald-200
                {% else %}bg-red-50 text-red-700 border border-red-200{% endif %}">
                ✓ {{ vote.pour }} · ✗ {{ vote.contre }}{% if vote.abstentions %} · ~ {{ vote.abstentions }}{% endif %}
              </span>
            </div>
            {% endif %}
          </div>
        </div>
        {% endfor %}
      </div>
      {% endif %}
    </div>
    {% endfor %}
  </div>

  {% elif conseil.resume_citoyen %}
  <!-- Fallback : résumé texte brut -->
  <div class="bg-white rounded-xl border border-gray-200 p-6">
    <h2 class="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4">Résumé en langage citoyen</h2>
    <div class="prose prose-sm max-w-none text-gray-700 leading-relaxed whitespace-pre-line">{{ conseil.resume_citoyen }}</div>
  </div>

  {% else %}
  <div class="bg-gray-50 rounded-xl border border-gray-200 p-8 text-center text-gray-400">
    <p class="text-sm">Le résumé citoyen est en cours de rédaction.</p>
  </div>
  {% endif %}

</div>
{% endblock %}
```

- [ ] **Step 2: Déployer et tester visuellement**

```bash
docker cp app/templates/public/conseil_detail.html boussolecommune-web-1:/app/app/templates/public/conseil_detail.html
docker restart boussolecommune-web-1
```

Ouvrir un conseil publié dans le navigateur :
- Si `resume_structure` est NULL : vérifier que le résumé texte s'affiche normalement (fallback)
- Après une génération avec Groq : vérifier les cartes thématiques, délibérations, et badges de vote

- [ ] **Step 3: Commit**

```bash
git add app/templates/public/conseil_detail.html
git commit -m "feat: affichage structuré par thème avec délibérations et badges de vote"
```

---

### Task 7: Rebuild Docker image

- [ ] **Step 1: Vérifier que `.env` est présent**

```bash
ls /home/ubuntu/boussolecommune/.env
```

- [ ] **Step 2: Rebuild**

```bash
cd /home/ubuntu/boussolecommune && docker compose up -d --build
```

- [ ] **Step 3: Vérifier**

```bash
docker compose ps
docker compose logs web --tail 10
```
Expected: tous les services `Up`, Gunicorn démarre sans erreur.

- [ ] **Step 4: Test end-to-end**
  1. Se connecter en admin
  2. Aller sur un conseil avec PDF
  3. Cliquer "Générer le résumé via IA" — attendre ~30s
  4. Aller sur la page publique du conseil
  5. Vérifier les cartes thématiques avec délibérations et votes

- [ ] **Step 5: Commit final**

```bash
git add app/database.py app/models/conseil.py app/services/ollama_service.py app/routes/admin.py app/routes/public.py app/templates/public/conseil_detail.html
git commit -m "chore: rebuild Docker image — affichage structuré conseils municipaux"
```
