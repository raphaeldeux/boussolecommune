# OFGL Auto-Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre l'import automatique des données financières OFGL pour une commune via son code INSEE, depuis l'API publique data.ofgl.fr, avec prévisualisation et import incrémental.

**Architecture:** Nouveau fetcher `app/services/fetchers/ofgl.py` qui interroge l'API OFGL et retourne des lignes au même format que `parser_ofgl.py`. Le flux admin suit le même pattern que l'upload CSV existant : fetch → prévisualisation en session → confirmation → import. Les champs `code_insee` et `nb_conseillers` sont déjà en base ; il faut juste les exposer dans le formulaire de modification de ville.

**Tech Stack:** Flask, psycopg2, requests, API OFGL (data.ofgl.fr/api/explore/v2.1), PostgreSQL UPSERT

---

## Contexte codebase

### Fichiers existants clés
- `app/services/parser_ofgl.py` — parse CSV OFGL, contient `MAPPING_OFGL` et `parser_ofgl()`. **Ne pas modifier.** Réutiliser la logique de normalisation.
- `app/services/fetchers/macantine.py` — modèle à suivre pour un fetcher HTTP. Pattern : `fetch_xxx(code_insee, annee) -> dict`.
- `app/routes/admin.py:399` — route `upload()` : gère preview (session tmp) puis import. Même pattern pour OFGL auto.
- `app/models/ville.py:34` — `update(ville_id, nom, slug, population, actif)` → à étendre pour `code_insee`, `nb_conseillers`.
- `app/templates/admin/modifier_ville.html` — formulaire de modification ville → ajouter champs.
- `app/templates/admin/upload.html` — page upload CSV → ajouter section "Import OFGL auto".
- Table `donnees` : UNIQUE(indicateur_id, annee, ville_id) → `ON CONFLICT DO NOTHING` pour incrémental, `DO UPDATE` pour forcer.

### Indicateurs OFGL mappés (indicateur_id dans `indicateurs`)
| Champ API OFGL (à vérifier) | indicateur_id | Unité |
|---|---|---|
| `Eparg_Brute` | `fin_epargne_brute` | € brut |
| `EncDette_Tot` | `fin_dette_habitant` | € → diviser par population |
| `CapDesend` | `fin_capacite_desendettement` | années |
| `Dep_Invest_Tot` | `fin_investissement_habitant` | € → diviser par population |
| `ChgePersonnel_Total` | `fin_masse_salariale_ratio` | € brut |
| `RigChargesStruct` | `fin_rigidite_charges` | % |

> ⚠️ Les noms exacts des champs API OFGL doivent être vérifiés à l'étape 1 du Task 2.

### API OFGL
```
GET https://data.ofgl.fr/api/explore/v2.1/catalog/datasets/ofgl-base-communes-consolidee/records
  ?where=Code_Offic_Commune="44202"
  &limit=100
  &timezone=UTC
```
Réponse : `{"total_count": N, "results": [{...}, ...]}`

---

## File Structure

| Fichier | Action | Rôle |
|---|---|---|
| `app/services/fetchers/ofgl.py` | **Créer** | Fetcher API OFGL, retourne lignes au format parser_ofgl |
| `app/models/ville.py` | **Modifier** | Ajouter `code_insee` et `nb_conseillers` à `update()` |
| `app/routes/admin.py` | **Modifier** | Route `modifier_ville` + nouvelle route `fetch_ofgl` |
| `app/templates/admin/modifier_ville.html` | **Modifier** | Champs code_insee et nb_conseillers |
| `app/templates/admin/upload.html` | **Modifier** | Section "Import OFGL automatique" avec bouton fetch + preview |

---

## Task 1 — US-O1 : Exposer code_insee et nb_conseillers dans l'admin ville

**Files:**
- Modify: `app/models/ville.py:34`
- Modify: `app/routes/admin.py` (route `modifier_ville`, ~ligne 891)
- Modify: `app/templates/admin/modifier_ville.html`

Le but est de permettre à un super_admin de saisir/modifier le code INSEE et le nb de conseillers d'une ville depuis l'interface.

- [ ] **Étape 1 : Mettre à jour `ville_model.update()`**

Dans `app/models/ville.py`, remplacer la fonction `update` :

```python
def update(ville_id, nom, slug, population=None, actif=1, code_insee=None, nb_conseillers=None):
    with get_db() as conn:
        conn.execute(
            "UPDATE villes SET nom=%s, slug=%s, population=%s, actif=%s, "
            "code_insee=%s, nb_conseillers=%s WHERE id=%s",
            (nom, slug, population, actif, code_insee or None, nb_conseillers, ville_id)
        )
        conn.commit()
```

- [ ] **Étape 2 : Mettre à jour la route `modifier_ville`**

Dans `app/routes/admin.py` (~ligne 898), ajouter la lecture des nouveaux champs dans le POST :

```python
code_insee = request.form.get("code_insee", "").strip() or None
nb_conseillers_str = request.form.get("nb_conseillers", "").strip()
nb_conseillers = int(nb_conseillers_str) if nb_conseillers_str.isdigit() else None

ville_model.update(ville_id, nom, slug, population, actif, code_insee, nb_conseillers)
```

- [ ] **Étape 3 : Mettre à jour le template `modifier_ville.html`**

Lire d'abord le template existant. Ajouter après le champ population :

```html
<div>
  <label class="block text-sm font-medium text-gray-700 mb-1">Code INSEE</label>
  <input type="text" name="code_insee" value="{{ ville.code_insee or '' }}"
         placeholder="Ex : 44202"
         class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400">
  <p class="text-xs text-gray-400 mt-1">Requis pour l'import OFGL automatique et ma-cantine.</p>
</div>

<div>
  <label class="block text-sm font-medium text-gray-700 mb-1">Nombre d'élus au conseil</label>
  <input type="number" name="nb_conseillers" value="{{ ville.nb_conseillers or '' }}"
         placeholder="Ex : 29"
         class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400">
</div>
```

- [ ] **Étape 4 : Vérifier manuellement**

```bash
docker compose up -d --build
# Aller sur /admin/villes/modifier/1
# Saisir code_insee=44202, nb_conseillers=29, sauvegarder
# Vérifier en base :
docker compose exec web python3 -c "
from app.database import get_db
with get_db() as conn:
    r = conn.execute('SELECT id, nom, code_insee, nb_conseillers FROM villes WHERE id=1').fetchone()
    print(dict(r))
"
```
Attendu : `{'id': 1, 'nom': 'Sautron', 'code_insee': '44202', 'nb_conseillers': 29}`

- [ ] **Étape 5 : Commit**

```bash
git add app/models/ville.py app/routes/admin.py app/templates/admin/modifier_ville.html
git commit -m "feat(US-O1): code_insee et nb_conseillers éditables dans l'admin ville"
```

---

## Task 2 — US-O2 : Fetcher OFGL automatique

**Files:**
- Create: `app/services/fetchers/ofgl.py`
- Modify: `app/routes/admin.py` (ajouter route `fetch_ofgl`)
- Modify: `app/templates/admin/upload.html` (ajouter bouton)

- [ ] **Étape 1 : Inspecter l'API OFGL et identifier les champs**

```bash
docker compose exec web python3 -c "
import requests, json
r = requests.get(
    'https://data.ofgl.fr/api/explore/v2.1/catalog/datasets/ofgl-base-communes-consolidee/records',
    params={'where': 'Code_Offic_Commune=\"44202\"', 'limit': 3},
    timeout=15
)
print(json.dumps(r.json()['results'][0], indent=2, ensure_ascii=False))
"
```

Lire attentivement les noms de champs retournés. Mettre à jour le mapping dans `ofgl.py` en conséquence.

- [ ] **Étape 2 : Créer `app/services/fetchers/ofgl.py`**

```python
"""
Fetcher OFGL — data.ofgl.fr
Récupère les données financières d'une commune via l'API publique.
"""
import requests

BASE_URL = "https://data.ofgl.fr/api/explore/v2.1/catalog/datasets/ofgl-base-communes-consolidee/records"
SOURCE = "OFGL — data.ofgl.fr"
TIMEOUT = 20

# Champs API → (indicateur_id, diviseur_par_population)
# diviseur_par_population=True : valeur brute € à diviser par la population
# Noms de champs à vérifier avec l'étape 1
CHAMPS_OFGL = {
    "Eparg_Brute":           ("fin_epargne_brute",             False),
    "EncDette_Tot":          ("fin_dette_habitant",             True),
    "CapDesend":             ("fin_capacite_desendettement",    False),
    "Dep_Invest_Tot":        ("fin_investissement_habitant",    True),
    "ChgePersonnel_Total":   ("fin_masse_salariale_ratio",      False),
    "RigChargesStruct":      ("fin_rigidite_charges",           False),
}


def fetch_ofgl_data(code_insee: str, population: int = None) -> dict:
    """
    Récupère toutes les années disponibles pour une commune.

    Retourne :
    {
        "ok": True,
        "lignes": [{"indicateur_id": str, "annee": int, "valeur": float, "source": str}],
        "erreurs": [str],
        "annees": [int],   # années récupérées
    }
    """
    try:
        resp = requests.get(
            BASE_URL,
            params={
                "where": f'Code_Offic_Commune="{code_insee}"',
                "limit": 200,
                "timezone": "UTC",
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

    results = data.get("results", [])
    if not results:
        return {"ok": False, "error": f"Aucune donnée OFGL pour le code INSEE {code_insee}"}

    lignes = []
    erreurs = []
    annees = set()

    for record in results:
        annee = record.get("Annee") or record.get("annee")
        if not annee:
            continue
        try:
            annee = int(annee)
        except (ValueError, TypeError):
            continue
        annees.add(annee)

        for champ, (indicateur_id, par_habitant) in CHAMPS_OFGL.items():
            val = record.get(champ)
            if val is None:
                continue
            try:
                valeur = float(val)
            except (ValueError, TypeError):
                erreurs.append(f"Valeur non numérique pour {champ} (année {annee})")
                continue

            if par_habitant:
                if not population:
                    erreurs.append(f"Population inconnue, {champ} ignoré (année {annee})")
                    continue
                valeur = round(valeur / population, 2)

            lignes.append({
                "indicateur_id": indicateur_id,
                "annee": annee,
                "valeur": valeur,
                "source": SOURCE,
                "libelle_ofgl": champ,
            })

    return {
        "ok": True,
        "lignes": lignes,
        "erreurs": erreurs,
        "annees": sorted(annees, reverse=True),
    }
```

- [ ] **Étape 3 : Ajouter la route `fetch_ofgl` dans `admin.py`**

En haut du fichier, ajouter l'import du fetcher (avec les autres imports fetchers, ~ligne 23) :
```python
from app.services.fetchers.ofgl import fetch_ofgl_data
```

Ajouter la route après la route `fetch_macantine` (~ligne 549) :

```python
@bp.route("/upload/fetch-ofgl", methods=["POST"])
@login_required
def fetch_ofgl():
    """Fetch les données OFGL depuis l'API et stocke le preview en session."""
    ville = _get_current_ville()
    if not ville:
        flash("Aucune commune sélectionnée.", "danger")
        return redirect(url_for("admin.upload"))

    code_insee = ville.get("code_insee")
    if not code_insee:
        flash("Code INSEE non renseigné. Modifiez la fiche de la commune.", "danger")
        return redirect(url_for("admin.upload"))

    result = fetch_ofgl_data(code_insee, population=ville.get("population"))

    if not result["ok"]:
        flash(f"OFGL : {result['error']}", "danger")
        return redirect(url_for("admin.upload"))

    import json as _json
    session["ofgl_preview"] = _json.dumps({
        "lignes": result["lignes"],
        "annees": result["annees"],
        "code_insee": code_insee,
    })

    if result["erreurs"]:
        flash(f"{len(result['erreurs'])} avertissement(s) : {result['erreurs'][0]}", "warning")

    flash(
        f"{len(result['lignes'])} valeur(s) récupérée(s) depuis OFGL "
        f"({len(result['annees'])} année(s) : {', '.join(str(a) for a in result['annees'])}). "
        "Vérifiez et confirmez ci-dessous.",
        "info"
    )
    return redirect(url_for("admin.upload"))
```

- [ ] **Étape 4 : Ajouter la route `confirm_ofgl` dans `admin.py`**

```python
@bp.route("/upload/confirm-ofgl", methods=["POST"])
@login_required
def confirm_ofgl():
    """Confirme et importe les données OFGL prévisualisées."""
    import json as _json
    ville = _get_current_ville()
    if not ville:
        abort(403)

    preview_json = session.pop("ofgl_preview", None)
    if not preview_json:
        flash("Session expirée. Relancez le fetch OFGL.", "danger")
        return redirect(url_for("admin.upload"))

    preview = _json.loads(preview_json)
    lignes = preview["lignes"]
    force = bool(request.form.get("force"))

    nb_importes = 0
    nb_ignores = 0
    with get_db() as conn:
        for ligne in lignes:
            if force:
                conn.execute(
                    """INSERT INTO donnees (indicateur_id, ville_id, annee, valeur, source, mode_saisie)
                       VALUES (%s, %s, %s, %s, %s, 'csv')
                       ON CONFLICT (indicateur_id, annee, ville_id) DO UPDATE
                         SET valeur=EXCLUDED.valeur, source=EXCLUDED.source""",
                    (ligne["indicateur_id"], ville["id"], ligne["annee"],
                     ligne["valeur"], ligne["source"])
                )
                nb_importes += 1
            else:
                cur = conn.execute(
                    """INSERT INTO donnees (indicateur_id, ville_id, annee, valeur, source, mode_saisie)
                       VALUES (%s, %s, %s, %s, %s, 'csv')
                       ON CONFLICT (indicateur_id, annee, ville_id) DO NOTHING""",
                    (ligne["indicateur_id"], ville["id"], ligne["annee"],
                     ligne["valeur"], ligne["source"])
                )
                if cur.rowcount:
                    nb_importes += 1
                else:
                    nb_ignores += 1
        conn.commit()

    msg = f"{nb_importes} valeur(s) importée(s) depuis OFGL."
    if nb_ignores:
        msg += f" {nb_ignores} ignorée(s) (déjà présentes — cochez 'Forcer la mise à jour' pour écraser)."
    flash(msg, "success" if nb_importes > 0 else "warning")
    return redirect(url_for("admin.upload"))
```

- [ ] **Étape 5 : Vérifier le fetcher manuellement**

```bash
docker compose exec web python3 -c "
from app.services.fetchers.ofgl import fetch_ofgl_data
r = fetch_ofgl_data('44202', population=8600)
print('OK:', r['ok'])
print('Années:', r.get('annees'))
print('Nb lignes:', len(r.get('lignes', [])))
print('Erreurs:', r.get('erreurs'))
if r.get('lignes'):
    print('Exemple:', r['lignes'][0])
"
```

Si les champs ne matchent pas (0 lignes), relancer l'étape 1 pour inspecter les vrais noms de champs et mettre à jour `CHAMPS_OFGL`.

- [ ] **Étape 6 : Commit**

```bash
git add app/services/fetchers/ofgl.py app/routes/admin.py
git commit -m "feat(US-O2): fetcher OFGL auto + routes fetch/confirm"
```

---

## Task 3 — US-O3 : Prévisualisation + bouton dans upload.html

**Files:**
- Modify: `app/templates/admin/upload.html`

Lire d'abord le fichier entier pour comprendre sa structure avant de modifier.

- [ ] **Étape 1 : Lire `app/templates/admin/upload.html`**

```bash
# Dans l'éditeur
```

- [ ] **Étape 2 : Ajouter la section OFGL automatique dans le template**

Ajouter une nouvelle section (après l'historique ou en haut, selon ce qui est logique dans le template existant) :

```html
{# ── Import OFGL automatique ──────────────────────────────────────────── #}
<div class="bg-white rounded-xl border border-gray-200 p-6 mb-6">
  <h2 class="text-lg font-semibold text-gray-800 mb-1">Import OFGL automatique</h2>
  <p class="text-sm text-gray-500 mb-4">
    Récupère les données financières depuis
    <a href="https://data.ofgl.fr" target="_blank" class="text-emerald-600 hover:underline">data.ofgl.fr</a>
    pour toutes les années disponibles.
    {% if not ville or not ville.code_insee %}
    <span class="text-amber-600 font-medium">⚠ Code INSEE non renseigné —
      <a href="{{ url_for('admin.modifier_ville', ville_id=ville.id) if ville else '#' }}"
         class="underline">configurer la commune</a>.</span>
    {% endif %}
  </p>

  {# Bouton fetch #}
  <form method="POST" action="{{ url_for('admin.fetch_ofgl') }}">
    <input type="hidden" name="_csrf" value="{{ csrf_token() }}">
    <button type="submit"
            {% if not ville or not ville.code_insee %}disabled{% endif %}
            class="bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed
                   text-white px-4 py-2 rounded-lg text-sm font-medium transition">
      🔄 Récupérer les données OFGL
    </button>
  </form>

  {# Preview OFGL #}
  {% if session.get('ofgl_preview') %}
  {% set preview = session['ofgl_preview'] | fromjson %}
  <div class="mt-5">
    <p class="text-sm font-medium text-gray-700 mb-2">
      {{ preview.lignes | length }} valeur(s) prêtes à importer
      (années : {{ preview.annees | join(', ') }})
    </p>
    <div class="overflow-x-auto rounded-lg border border-gray-200 mb-4">
      <table class="w-full text-xs">
        <thead class="bg-gray-50 text-gray-500 uppercase tracking-wide">
          <tr>
            <th class="px-3 py-2 text-left">Indicateur</th>
            <th class="px-3 py-2 text-center">Année</th>
            <th class="px-3 py-2 text-right">Valeur</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
          {% for l in preview.lignes | sort(attribute='annee', reverse=True) %}
          <tr class="hover:bg-gray-50">
            <td class="px-3 py-1.5 text-gray-700">{{ l.indicateur_id }}</td>
            <td class="px-3 py-1.5 text-center text-gray-500">{{ l.annee }}</td>
            <td class="px-3 py-1.5 text-right font-mono text-gray-800">{{ l.valeur }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    <form method="POST" action="{{ url_for('admin.confirm_ofgl') }}" class="flex items-center gap-4">
      <input type="hidden" name="_csrf" value="{{ csrf_token() }}">
      <label class="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
        <input type="checkbox" name="force" class="rounded">
        Forcer la mise à jour (écraser les données existantes)
      </label>
      <button type="submit"
              class="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition">
        ✅ Confirmer l'import
      </button>
      <a href="{{ url_for('admin.upload') }}"
         class="text-gray-500 hover:text-gray-700 text-sm">Annuler</a>
    </form>
  </div>
  {% endif %}
</div>
```

> Note : `session.get('ofgl_preview')` et le filtre `| fromjson` nécessitent d'ajouter `fromjson` comme filtre Jinja2 dans `app/__init__.py` (voir étape 3).

- [ ] **Étape 3 : Ajouter le filtre `fromjson` dans `app/__init__.py`**

Dans `create_app()`, après les autres filtres :

```python
import json as _json_module

@app.template_filter("fromjson")
def fromjson(value):
    try:
        return _json_module.loads(value)
    except Exception:
        return {}
```

- [ ] **Étape 4 : Vérifier le flux complet**

```bash
docker compose up -d --build
# 1. Aller sur /admin/upload
# 2. Vérifier que le bouton OFGL apparaît
# 3. Cliquer "Récupérer les données OFGL"
# 4. Vérifier le tableau de prévisualisation
# 5. Confirmer l'import
# 6. Vérifier en base :
docker compose exec web python3 -c "
from app.database import get_db
with get_db() as conn:
    rows = conn.execute(
        'SELECT indicateur_id, annee, valeur, source FROM donnees WHERE ville_id=1 AND source LIKE %s ORDER BY annee DESC LIMIT 10',
        ('%OFGL%',)
    ).fetchall()
    for r in rows: print(dict(r))
"
```

- [ ] **Étape 5 : Commit**

```bash
git add app/templates/admin/upload.html app/__init__.py
git commit -m "feat(US-O3): preview OFGL dans la page upload + filtre fromjson"
```

---

## Task 4 — US-O4 : Import incrémental (validation finale)

L'import incrémental est déjà implémenté dans la route `confirm_ofgl` (Task 2) via `ON CONFLICT DO NOTHING` + checkbox `force`. Ce task vérifie et documente le comportement.

**Files:**
- Aucun nouveau fichier

- [ ] **Étape 1 : Tester le comportement incrémental**

```bash
# Lancer un 2ème import OFGL sans cocher "Forcer"
# → Vérifier le message flash indique les lignes ignorées
# Lancer un 3ème import avec "Forcer" coché
# → Vérifier que les valeurs sont mises à jour
docker compose exec web python3 -c "
from app.database import get_db
with get_db() as conn:
    # Vérifier qu'il n'y a pas de doublons
    rows = conn.execute(
        'SELECT indicateur_id, annee, COUNT(*) as nb FROM donnees WHERE ville_id=1 GROUP BY indicateur_id, annee HAVING COUNT(*) > 1'
    ).fetchall()
    print('Doublons (doit être vide):', [dict(r) for r in rows])
"
```

- [ ] **Étape 2 : Commit final**

```bash
git add -A
git commit -m "feat(US-O1/O2/O3/O4): intégration OFGL automatique complète"
```
