# Ollama Background Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run Ollama résumé generation in a background thread so users can navigate away and return to see the result.

**Architecture:** Add a `statut_resume` column to `conseils` table tracking state (`idle`/`en_cours`/`termine`/`erreur`). The generation route spawns a daemon thread, updates the DB when done. A new JSON status endpoint allows the frontend to poll every 2 seconds and update the UI without a page reload.

**Tech Stack:** Python `threading.Thread`, PostgreSQL (psycopg2), Flask JSON responses, vanilla JS `setInterval` polling.

---

## Known Limitations

- **`statut_resume` stuck on `en_cours` after restart:** If Gunicorn restarts while a thread is mid-generation, the column stays `en_cours` and the UI spins forever. Mitigated in Task 1 by resetting stuck rows at startup.
- **No polling timeout:** If Ollama hangs indefinitely, the JS will poll forever. Acceptable trade-off for now given the 300s Ollama request timeout — the thread will eventually error out and set `statut_resume = 'erreur'`.

---

## File Map

| File | Action | What changes |
|------|--------|--------------|
| `app/database.py` | Modify | Add `statut_resume` column migration using `_column_exists` helper; reset stuck `en_cours` rows on startup |
| `app/models/conseil.py` | Modify | Add `set_statut_resume()` helper (`get_by_id` already returns all columns including the new one) |
| `app/routes/admin.py` | Modify | Rewrite `conseil_generer_resume` to spawn thread; add `conseil_statut_resume` JSON endpoint |
| `app/templates/admin/conseil_resume.html` | Modify | Add spinner, disable button during generation, JS polling loop |

---

### Task 1: Add `statut_resume` column + startup reset

**Files:**
- Modify: `app/database.py`

- [ ] **Step 1: Add column migration after the `conseils` table block (line 382)**

The codebase uses `_column_exists(conn, table, column)` for all column migrations. Follow the same pattern. Add the following immediately after line 382 (`conn.commit()` that closes the `conseils` CREATE block), and before line 384 (`# Table documents publics`):

```python
    if not _column_exists(conn, "conseils", "statut_resume"):
        conn.execute(
            "ALTER TABLE conseils ADD COLUMN statut_resume TEXT NOT NULL DEFAULT 'idle'"
        )
        conn.commit()

    # Reset any rows stuck in 'en_cours' from a previous interrupted generation
    conn.execute(
        "UPDATE conseils SET statut_resume = 'idle' WHERE statut_resume = 'en_cours'"
    )
    conn.commit()
```

- [ ] **Step 2: Verify the migration runs cleanly**

```bash
docker cp app/database.py boussolecommune-web-1:/app/app/database.py
docker restart boussolecommune-web-1
docker logs boussolecommune-web-1 --tail 20
```
Expected: Gunicorn starts with no errors.

Check the column exists:
```bash
docker exec boussolecommune-db-1 psql -U boussole -d boussolecommune -c "\d conseils"
```
Expected: `statut_resume` column present with default `idle`.

- [ ] **Step 3: Commit**

```bash
git add app/database.py
git commit -m "feat: add statut_resume column to conseils table"
```

---

### Task 2: Add model helper `set_statut_resume`

**Files:**
- Modify: `app/models/conseil.py`

Note: `get_by_id()` already returns all columns via `SELECT *`, so no `get_statut_resume()` helper is needed — the new column will be present automatically.

- [ ] **Step 1: Append `set_statut_resume()` to `app/models/conseil.py`**

```python
def set_statut_resume(conseil_id, statut, resume_citoyen=None):
    """Met à jour statut_resume et optionnellement resume_citoyen."""
    with get_db() as conn:
        if resume_citoyen is not None:
            conn.execute(
                "UPDATE conseils SET statut_resume=%s, resume_citoyen=%s WHERE id=%s",
                (statut, resume_citoyen, conseil_id)
            )
        else:
            conn.execute(
                "UPDATE conseils SET statut_resume=%s WHERE id=%s",
                (statut, conseil_id)
            )
        conn.commit()
```

- [ ] **Step 2: Verify syntax**

```bash
docker cp app/models/conseil.py boussolecommune-web-1:/app/app/models/conseil.py
docker exec boussolecommune-web-1 python -c "import app.models.conseil; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/models/conseil.py
git commit -m "feat: add set_statut_resume model helper"
```

---

### Task 3: Rewrite generation route + add status endpoint

**Files:**
- Modify: `app/routes/admin.py` (around lines 1395–1421)

Note: `jsonify` is already imported at line 5 (`from flask import ..., jsonify, ...`). Do NOT add another import.

- [ ] **Step 1: Add `import threading` near the top of `app/routes/admin.py`**

Add after line 3 (`import tempfile`):
```python
import threading
```

- [ ] **Step 2: Rewrite `conseil_generer_resume` (lines ~1395–1421)**

Replace the entire existing `conseil_generer_resume` route with:

```python
@bp.route("/conseils/<int:conseil_id>/generer-resume", methods=["POST"])
@login_required
def conseil_generer_resume(conseil_id):
    ville = ville_model.get_by_id(session.get("admin_ville_id"))
    if not ville:
        abort(403)
    conseil = conseil_model.get_by_id(conseil_id)
    if not conseil or conseil["ville_id"] != ville["id"]:
        abort(404)
    if not conseil.get("fichier_pdf"):
        flash("Aucun PDF associé à ce conseil.", "danger")
        return redirect(url_for("admin.conseil_resume", conseil_id=conseil_id))
    if conseil.get("statut_resume") == "en_cours":
        flash("Une génération est déjà en cours.", "warning")
        return redirect(url_for("admin.conseil_resume", conseil_id=conseil_id))

    pdf_path = os.path.join(CONSEILS_UPLOAD_DIR, conseil["fichier_pdf"])
    if not os.path.exists(pdf_path):
        flash("Fichier PDF introuvable.", "danger")
        return redirect(url_for("admin.conseil_resume", conseil_id=conseil_id))

    conseil_model.set_statut_resume(conseil_id, "en_cours")

    def _run():
        from app.services.ollama_service import generer_resume
        try:
            resume = generer_resume(pdf_path)
            conseil_model.set_statut_resume(conseil_id, "termine", resume_citoyen=resume)
        except Exception:
            conseil_model.set_statut_resume(conseil_id, "erreur")

    threading.Thread(target=_run, daemon=True).start()
    return redirect(url_for("admin.conseil_resume", conseil_id=conseil_id))
```

- [ ] **Step 3: Add the JSON status endpoint** immediately after the route above:

```python
@bp.route("/conseils/<int:conseil_id>/statut-resume", methods=["GET"])
@login_required
def conseil_statut_resume(conseil_id):
    ville = ville_model.get_by_id(session.get("admin_ville_id"))
    if not ville:
        abort(403)
    conseil = conseil_model.get_by_id(conseil_id)
    if not conseil or conseil["ville_id"] != ville["id"]:
        abort(404)
    return jsonify({
        "statut": conseil.get("statut_resume", "idle"),
        "resume": conseil.get("resume_citoyen"),
    })
```

- [ ] **Step 4: Deploy and verify**

```bash
docker cp app/routes/admin.py boussolecommune-web-1:/app/app/routes/admin.py
docker restart boussolecommune-web-1
docker logs boussolecommune-web-1 --tail 20
```
Expected: Gunicorn starts with no import errors.

- [ ] **Step 5: Commit**

```bash
git add app/routes/admin.py
git commit -m "feat: run Ollama resume generation in background thread"
```

---

### Task 4: Update frontend to poll and reflect status

**Files:**
- Modify: `app/templates/admin/conseil_resume.html`

- [ ] **Step 1: Check current state of the template**

```bash
git diff app/templates/admin/conseil_resume.html
```
Expected: no unexpected local changes (the only changes should be the two CSRF tokens added earlier).

- [ ] **Step 2: Replace the entire content of `conseil_resume.html`**

```html
{% extends "admin_base.html" %}
{% block title %}Résumé citoyen — {{ conseil.titre }}{% endblock %}

{% block content %}
<div class="max-w-3xl">
  <div class="flex items-center gap-3 mb-6">
    <a href="{{ url_for('admin.conseils') }}" class="text-gray-400 hover:text-gray-600 text-sm">← Conseils</a>
    <span class="text-gray-300">/</span>
    <h1 class="text-xl font-bold text-gray-900 truncate">{{ conseil.titre }}</h1>
  </div>

  {% if not conseil.fichier_pdf %}
  <div class="bg-amber-50 border border-amber-200 rounded-xl p-4 mb-5 text-sm text-amber-800">
    ⚠️ Aucun PDF associé à ce conseil. <a href="{{ url_for('admin.conseil_modifier', conseil_id=conseil.id) }}" class="underline">Ajouter un PDF →</a>
  </div>
  {% elif not ollama_ok %}
  <div class="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-5 text-sm text-blue-800">
    ℹ️ Ollama est en cours de démarrage ou le modèle n'est pas encore téléchargé.
    La génération automatique sera disponible dès qu'il sera prêt.
    En attendant, vous pouvez saisir le résumé manuellement ci-dessous.
  </div>
  {% endif %}

  <!-- Bouton de génération -->
  {% if conseil.fichier_pdf and ollama_ok %}
  <form method="POST" action="{{ url_for('admin.conseil_generer_resume', conseil_id=conseil.id) }}" class="mb-5">
    <input type="hidden" name="_csrf" value="{{ csrf_token() }}">
    <button id="btn-generer" type="submit"
            {% if conseil.statut_resume == 'en_cours' %}disabled{% endif %}
            class="bg-purple-600 hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-4 py-2 rounded-lg text-sm font-medium transition flex items-center gap-2">
      <span id="btn-label">
        {% if conseil.statut_resume == 'en_cours' %}
          <svg class="animate-spin h-4 w-4 inline mr-1" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"></path>
          </svg>
          Génération en cours…
        {% else %}
          ✨ Générer le résumé via Ollama
        {% endif %}
      </span>
    </button>
  </form>

  <div id="status-erreur" class="hidden bg-red-50 border border-red-200 rounded-xl p-4 mb-5 text-sm text-red-800">
    ❌ Une erreur est survenue lors de la génération. Veuillez réessayer.
  </div>
  {% endif %}

  <!-- Formulaire d'édition -->
  <form method="POST" class="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
    <input type="hidden" name="_csrf" value="{{ csrf_token() }}">
    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">
        Résumé citoyen
        <span class="text-xs text-gray-400 font-normal ml-1">— modifiable avant publication</span>
      </label>
      <textarea id="textarea-resume" name="resume_citoyen" rows="16"
                placeholder="Le résumé généré par l'IA apparaîtra ici. Vous pouvez aussi le saisir manuellement."
                class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400 font-mono leading-relaxed">{{ conseil.resume_citoyen or '' }}</textarea>
    </div>
    <div class="flex items-center gap-3">
      <button type="submit"
              class="bg-emerald-600 hover:bg-emerald-700 text-white px-5 py-2 rounded-lg text-sm font-medium transition">
        Enregistrer
      </button>
      <a href="{{ url_for('admin.conseils') }}" class="text-gray-500 hover:text-gray-700 text-sm">Annuler</a>
    </div>
  </form>
</div>

<script>
(function () {
  var statut = {{ conseil.statut_resume | tojson }};
  var statusUrl = {{ url_for('admin.conseil_statut_resume', conseil_id=conseil.id) | tojson }};
  var pollInterval = null;

  function setIdle() {
    var btn = document.getElementById('btn-generer');
    var label = document.getElementById('btn-label');
    if (btn) btn.disabled = false;
    if (label) label.textContent = '✨ Générer le résumé via Ollama';
  }

  function stopPolling() {
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
  }

  function poll() {
    fetch(statusUrl, { credentials: 'same-origin' })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.statut === 'termine') {
          stopPolling();
          var textarea = document.getElementById('textarea-resume');
          if (textarea && data.resume) textarea.value = data.resume;
          setIdle();
        } else if (data.statut === 'erreur') {
          stopPolling();
          var err = document.getElementById('status-erreur');
          if (err) err.classList.remove('hidden');
          setIdle();
        }
      })
      .catch(function() { /* réseau instable, on réessaie */ });
  }

  if (statut === 'en_cours') {
    pollInterval = setInterval(poll, 2000);
  }
})();
</script>
{% endblock %}
```

- [ ] **Step 3: Deploy template to container**

```bash
docker cp app/templates/admin/conseil_resume.html boussolecommune-web-1:/app/app/templates/admin/conseil_resume.html
docker restart boussolecommune-web-1
```

- [ ] **Step 4: Manual test**
  1. Navigate to a conseil that has a PDF and Ollama is ready
  2. Click "Générer le résumé via Ollama"
  3. Verify button becomes a spinner and is disabled immediately
  4. Navigate to another admin page (e.g., dashboard)
  5. Come back to the conseil résumé page — verify spinner is shown while `statut_resume = 'en_cours'`
  6. Wait for Ollama to finish — verify textarea fills automatically, button re-enables, no page reload needed

- [ ] **Step 5: Commit**

```bash
git add app/templates/admin/conseil_resume.html
git commit -m "feat: poll Ollama generation status, update UI without page reload"
```

---

### Task 5: Rebuild Docker image for persistence

All `docker cp` changes are lost on the next `docker compose up --build`. This task bakes everything into the image.

- [ ] **Step 1: Check `.env` exists** (required by docker compose `env_file`)

```bash
ls .env || echo "MISSING — copy from .env.example and fill in values"
```

- [ ] **Step 2: Rebuild**

```bash
docker compose up -d --build
```

- [ ] **Step 3: Verify all services are healthy**

```bash
docker compose ps
docker compose logs web --tail 20
```
Expected: all services `Up`, Gunicorn logs show workers ready, no errors.

- [ ] **Step 4: Final commit**

```bash
git add app/database.py app/models/conseil.py app/routes/admin.py app/templates/admin/conseil_resume.html
git commit -m "chore: rebuild-ready — background Ollama generation complete"
```
