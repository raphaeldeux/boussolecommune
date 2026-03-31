# Refonte admin — Plan 1 : Accès + Ma commune + Navigation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ouvrir la page de modification de ville aux gestionnaires (accès à leur seule ville), absorber la page Intégrations dans Ma commune, et reorganiser la navigation selon le nouveau design.

**Architecture:** Ajout d'un helper `can_modify_ville` dans `auth.py`, modification du decorator sur `modifier_ville`, ajout d'une route `/ma-commune`, redirect de `/integrations`, et réécriture du template de navigation `admin_base.html`.

**Tech Stack:** Flask 3.0, Jinja2, Tailwind CSS (CDN), psycopg2, session Flask

**Spec de référence:** `docs/specs/2026-03-31-refonte-admin-roles-design.md`

---

## Fichiers touchés

| Fichier | Action |
|---------|--------|
| `app/auth.py` | Ajouter `can_modify_ville(ville_id)` |
| `app/routes/admin.py` | Modifier `modifier_ville`, ajouter `/ma-commune`, rediriger `/integrations` |
| `app/templates/admin/modifier_ville.html` | Ajouter bandeaux env, corriger breadcrumb, restructurer 2 sections |
| `app/templates/admin_base.html` | Réécrire la navigation complète |

Pas de suppression de route `/integrations` (juste redirect). Pas de nouveau modèle. Pas de migration DB.

> **Note :** Aucun framework de test n'est configuré dans ce projet (cf. CLAUDE.md). Les étapes de vérification sont manuelles.

---

## Task 1 : Ajouter `can_modify_ville` dans `app/auth.py`

**Fichiers :**
- Modifier : `app/auth.py`

- [ ] **Step 1 : Ajouter la fonction helper**

À la fin de `app/auth.py` (après `super_admin_required`, ligne 42), ajouter :

```python
def can_modify_ville(ville_id):
    """Retourne True si l'utilisateur connecté peut modifier la ville donnée."""
    if session.get('user_role') == 'super_admin':
        return True
    return session.get('admin_ville_id') == ville_id
```

- [ ] **Step 2 : Ajouter `can_modify_ville` à l'import dans admin.py**

Dans `app/routes/admin.py` ligne 7, l'import existant est :

```python
from app.auth import login_required, super_admin_required, is_rate_limited, record_attempt
```

Le mettre à jour pour ajouter `can_modify_ville` :

```python
from app.auth import login_required, super_admin_required, can_modify_ville, is_rate_limited, record_attempt
```

(`os` est déjà importé ligne 2 — pas besoin d'ajouter.)

- [ ] **Step 3 : Commit**

```bash
git add app/auth.py app/routes/admin.py
git commit -m "feat: add can_modify_ville access helper"
```

---

## Task 2 : Ouvrir `modifier_ville` aux gestionnaires + `/ma-commune` + redirect `/integrations`

**Fichiers :**
- Modifier : `app/routes/admin.py` (lignes 1624–1672 pour `modifier_ville`, ~2616 pour `integrations`)

- [ ] **Step 1 : Modifier le decorator de `modifier_ville`**

Remplacer dans `admin.py` :

```python
@bp.route("/villes/modifier/<int:ville_id>", methods=["GET", "POST"])
@super_admin_required
def modifier_ville(ville_id):
    ville = ville_model.get_by_id(ville_id)
    if not ville:
        abort(404)
```

Par :

```python
@bp.route("/villes/modifier/<int:ville_id>", methods=["GET", "POST"])
@login_required
def modifier_ville(ville_id):
    if not can_modify_ville(ville_id):
        flash("Accès refusé.", "danger")
        return redirect(url_for("admin.dashboard"))
    ville = ville_model.get_by_id(ville_id)
    if not ville:
        abort(404)
```

- [ ] **Step 2 : Passer `has_env_*` au template et corriger le redirect après sauvegarde**

Dans `modifier_ville`, remplacer la section après la mise à jour des clés API :

```python
            flash(f"Ville « {nom} » mise à jour.", "success")
            return redirect(url_for("admin.villes"))
```

Par :

```python
            flash(f"Ville « {nom} » mise à jour.", "success")
            if session.get("user_role") == "super_admin":
                return redirect(url_for("admin.villes"))
            return redirect(url_for("admin.modifier_ville", ville_id=ville_id))
```

Et remplacer le `return render_template` final :

```python
    tous_indicateurs = ind_model.get_all(actif_only=True)
    vedettes_actuelles = (ville.get("indicateurs_vedettes") or "").split(",")
    vedettes_actuelles += ["", "", ""]  # ensure at least 3 slots
    return render_template("admin/modifier_ville.html", ville=ville,
                           tous_indicateurs=tous_indicateurs,
                           vedettes_actuelles=vedettes_actuelles)
```

Par :

```python
    from app.services.ai_service import MISTRAL_API_KEY as ENV_MISTRAL
    has_env_insee = bool(os.environ.get("INSEE_API_KEY"))
    has_env_mistral = bool(ENV_MISTRAL)
    tous_indicateurs = ind_model.get_all(actif_only=True)
    vedettes_actuelles = (ville.get("indicateurs_vedettes") or "").split(",")
    vedettes_actuelles += ["", "", ""]  # ensure at least 3 slots
    return render_template("admin/modifier_ville.html", ville=ville,
                           tous_indicateurs=tous_indicateurs,
                           vedettes_actuelles=vedettes_actuelles,
                           has_env_insee=has_env_insee,
                           has_env_mistral=has_env_mistral)
```

- [ ] **Step 3 : Ajouter la route `/ma-commune`**

Juste avant la route `modifier_ville` (avant la ligne `@bp.route("/villes/modifier/<int:ville_id>")`), ajouter :

```python
@bp.route("/ma-commune")
@login_required
def ma_commune():
    """Redirige vers modifier_ville de la ville courante."""
    ville_id = session.get("admin_ville_id")
    if not ville_id:
        flash("Aucune commune assignée.", "danger")
        return redirect(url_for("admin.dashboard"))
    return redirect(url_for("admin.modifier_ville", ville_id=ville_id))
```

- [ ] **Step 4 : Rediriger `/integrations` vers `/ma-commune`**

Remplacer la route `integrations` entière (`app/routes/admin.py` ~ligne 2616) par :

```python
@bp.route("/integrations", methods=["GET", "POST"])
@login_required
def integrations():
    """Redirigé vers Ma commune — fonctionnalité absorbée dans modifier_ville."""
    return redirect(url_for("admin.ma_commune"))
```

> Le POST est aussi redirigé intentionnellement : les formulaires de l'ancienne page `/integrations` sont remplacés par le formulaire unifié de `modifier_ville`. Comme le lien est retiré de la nav, personne ne devrait arriver sur cette URL — le redirect est un filet de sécurité.

- [ ] **Step 5 : Commit**

```bash
git add app/routes/admin.py
git commit -m "feat: open modifier_ville to gestionnaire, add /ma-commune route, redirect /integrations"
```

---

## Task 3 : Mettre à jour `modifier_ville.html`

**Fichiers :**
- Modifier : `app/templates/admin/modifier_ville.html`

- [ ] **Step 1 : Corriger le breadcrumb pour les gestionnaires**

Remplacer :

```html
{% block breadcrumb %} › <a href="{{ url_for('admin.villes') }}" class="hover:text-gray-600">Villes</a> › <span class="text-gray-800 font-medium">Modifier</span>{% endblock %}
```

Par :

```html
{% block breadcrumb %}
  {% if session.get('user_role') == 'super_admin' %}
   › <a href="{{ url_for('admin.villes') }}" class="hover:text-gray-600">Villes</a> › <span class="text-gray-800 font-medium">Modifier</span>
  {% else %}
   › <span class="text-gray-800 font-medium">Ma commune</span>
  {% endif %}
{% endblock %}
```

- [ ] **Step 2 : Mettre à jour le titre**

Remplacer :

```html
<h1 class="text-2xl font-bold text-gray-900 mb-6">Modifier « {{ ville.nom }} »</h1>
```

Par :

```html
<h1 class="text-2xl font-bold text-gray-900 mb-6">
  {% if session.get('user_role') == 'super_admin' %}Modifier « {{ ville.nom }} »{% else %}Ma commune — {{ ville.nom }}{% endif %}
</h1>
```

- [ ] **Step 3 : Ajouter les bandeaux ENV dans la section Intégrations**

Dans la section `<!-- API Keys (super_admin) -->` (ligne 80), remplacer l'en-tête :

```html
      <!-- API Keys (super_admin) -->
      <div class="mt-6 pt-6 border-t border-gray-100">
        <h3 class="text-sm font-semibold text-gray-700 mb-3">Intégrations API</h3>

        <div class="mb-4">
          <label class="block text-sm font-medium text-gray-700 mb-1">Clé API SIRENE</label>
```

Par :

```html
      <!-- Intégrations -->
      <div class="mt-6 pt-6 border-t border-gray-100">
        <h3 class="text-sm font-semibold text-gray-700 mb-3">Intégrations</h3>
        <p class="text-xs text-gray-500 mb-4">Clés API spécifiques à cette commune. Elles prennent le dessus sur la configuration globale du serveur si renseignées.</p>

        {% if has_env_insee %}
        <div class="mb-3 flex items-start gap-2 bg-blue-50 border border-blue-200 text-blue-700 text-sm rounded-lg px-3 py-2">
          <span class="mt-0.5">ℹ️</span>
          <span>Clé SIRENE héritée de la configuration serveur — la valeur ci-dessous la remplace si renseignée.</span>
        </div>
        {% endif %}

        <div class="mb-4">
          <label class="block text-sm font-medium text-gray-700 mb-1">Clé API SIRENE</label>
```

Et avant le champ Mistral, ajouter le bandeau Mistral. Remplacer :

```html
        <div class="mb-4">
          <label class="block text-sm font-medium text-gray-700 mb-1">Clé API Mistral</label>
```

Par :

```html
        {% if has_env_mistral %}
        <div class="mb-3 flex items-start gap-2 bg-blue-50 border border-blue-200 text-blue-700 text-sm rounded-lg px-3 py-2">
          <span class="mt-0.5">ℹ️</span>
          <span>Clé Mistral héritée de la configuration serveur — la valeur ci-dessous la remplace si renseignée.</span>
        </div>
        {% endif %}

        <div class="mb-4">
          <label class="block text-sm font-medium text-gray-700 mb-1">Clé API Mistral</label>
```

- [ ] **Step 4 : Commit**

```bash
git add app/templates/admin/modifier_ville.html
git commit -m "feat: update modifier_ville template — role-aware breadcrumb, env banners in integrations"
```

---

## Task 4 : Réécrire la navigation dans `admin_base.html`

**Fichiers :**
- Modifier : `app/templates/admin_base.html` (lignes 100–213, section `<nav>`)

La navigation cible, selon la spec :

**Tous les rôles :**
- Tableau de bord (standalone)
- **Données** : Sources automatiques (`/upload`), Sources manuelles (`/saisie`)
- **Commune** : Conseils municipaux (`/conseils`), Documents (`/documents`)
- **Paramètres** : Références (`/references`), Ma commune (`/ma-commune`)

**Administrateur uniquement :**
- **Démographie & vie asso.** (existant, inchangé) : Pyramide des âges, Subventions
- **Administration plateforme** : Villes, Utilisateurs, Banque de références

- [ ] **Step 1 : Remplacer le contenu de `<nav>` (lignes 100–213)**

Remplacer tout le bloc `<nav class="flex-1 overflow-y-auto py-4 px-2 space-y-5">` jusqu'à `</nav>` par :

```html
      <nav class="flex-1 overflow-y-auto py-4 px-2 space-y-5">

        <!-- Tableau de bord -->
        <div>
          <a href="{{ url_for('admin.dashboard') }}"
             class="flex items-center gap-2 px-3 py-2 rounded-lg transition text-sm
               {% if request.endpoint == 'admin.dashboard' %}bg-emerald-700 text-white font-medium{% else %}hover:bg-gray-700 hover:text-white{% endif %}">
            🗂️ Tableau de bord
          </a>
        </div>

        <!-- Données -->
        <div>
          <div class="text-xs uppercase tracking-wider text-gray-500 font-semibold px-3 mb-1">Données</div>
          <a href="{{ url_for('admin.upload') }}"
             class="flex items-center gap-2 px-3 py-2 rounded-lg transition text-sm
               {% if request.endpoint == 'admin.upload' %}bg-emerald-700 text-white font-medium{% else %}hover:bg-gray-700 hover:text-white{% endif %}">
            🔄 Sources automatiques
          </a>
          <a href="{{ url_for('admin.saisie') }}"
             class="flex items-center gap-2 px-3 py-2 rounded-lg transition text-sm
               {% if request.endpoint == 'admin.saisie' %}bg-emerald-700 text-white font-medium{% else %}hover:bg-gray-700 hover:text-white{% endif %}">
            ✏️ Sources manuelles
          </a>
        </div>

        <!-- Commune -->
        <!-- NOTE : le lien "Indicateurs" (/indicateurs) sera ajouté ici en Plan 2 -->
        <div>
          <div class="text-xs uppercase tracking-wider text-gray-500 font-semibold px-3 mb-1">Commune</div>
          <a href="{{ url_for('admin.conseils') }}"
             class="flex items-center gap-2 px-3 py-2 rounded-lg transition text-sm
               {% if request.endpoint in ('admin.conseils', 'admin.conseil_nouveau', 'admin.conseil_modifier', 'admin.conseil_resume') %}bg-emerald-700 text-white font-medium{% else %}hover:bg-gray-700 hover:text-white{% endif %}">
            📋 Conseils municipaux
          </a>
          <a href="{{ url_for('admin.documents') }}"
             class="flex items-center gap-2 px-3 py-2 rounded-lg transition text-sm
               {% if request.endpoint in ('admin.documents', 'admin.document_nouveau') %}bg-emerald-700 text-white font-medium{% else %}hover:bg-gray-700 hover:text-white{% endif %}">
            📁 Documents
          </a>
        </div>

        <!-- Paramètres -->
        <div>
          <div class="text-xs uppercase tracking-wider text-gray-500 font-semibold px-3 mb-1">Paramètres</div>
          <a href="{{ url_for('admin.references') }}"
             class="flex items-center gap-2 px-3 py-2 rounded-lg transition text-sm
               {% if request.endpoint == 'admin.references' %}bg-emerald-700 text-white font-medium{% else %}hover:bg-gray-700 hover:text-white{% endif %}">
            📊 Références
          </a>
          <a href="{{ url_for('admin.ma_commune') }}"
             class="flex items-center gap-2 px-3 py-2 rounded-lg transition text-sm
               {% if request.endpoint == 'admin.modifier_ville' %}bg-emerald-700 text-white font-medium{% else %}hover:bg-gray-700 hover:text-white{% endif %}">
            ⚙️ Ma commune
          </a>
        </div>

        <!-- Admin uniquement : Démographie & vie asso. -->
        {% if session.get('user_role') == 'super_admin' %}
        <div>
          <div class="text-xs uppercase tracking-wider text-gray-500 font-semibold px-3 mb-1">Démographie & vie asso.</div>
          <a href="{{ url_for('admin.pyramide') }}"
             class="flex items-center gap-2 px-3 py-2 rounded-lg transition text-sm
               {% if request.endpoint in ('admin.pyramide', 'admin.supprimer_pyramide') %}bg-emerald-700 text-white font-medium{% else %}hover:bg-gray-700 hover:text-white{% endif %}">
            👥 Pyramide des âges
          </a>
          <a href="{{ url_for('admin.subventions') }}"
             class="flex items-center gap-2 px-3 py-2 rounded-lg transition text-sm
               {% if request.endpoint in ('admin.subventions', 'admin.supprimer_subvention') %}bg-emerald-700 text-white font-medium{% else %}hover:bg-gray-700 hover:text-white{% endif %}">
            🤝 Subventions
          </a>
        </div>

        <!-- Admin uniquement : Administration plateforme -->
        <div>
          <div class="text-xs uppercase tracking-wider text-gray-500 font-semibold px-3 mb-1">Administration</div>
          <a href="{{ url_for('admin.villes') }}"
             class="flex items-center gap-2 px-3 py-2 rounded-lg transition text-sm
               {% if request.endpoint in ('admin.villes', 'admin.nouvelle_ville') %}bg-emerald-700 text-white font-medium{% else %}hover:bg-gray-700 hover:text-white{% endif %}">
            🏙️ Villes
          </a>
          <a href="{{ url_for('admin.users') }}"
             class="flex items-center gap-2 px-3 py-2 rounded-lg transition text-sm
               {% if request.endpoint in ('admin.users', 'admin.nouveau_user', 'admin.modifier_user') %}bg-emerald-700 text-white font-medium{% else %}hover:bg-gray-700 hover:text-white{% endif %}">
            👥 Utilisateurs
          </a>
          <a href="{{ url_for('admin.banque_references') }}"
             class="relative flex items-center gap-2 px-3 py-2 rounded-lg transition text-sm
               {% if request.endpoint in ('admin.banque_references','admin.banque_entrees','admin.banque_propositions') %}bg-emerald-700 text-white font-medium{% else %}hover:bg-gray-700 hover:text-white{% endif %}">
            🏛️ Banque de références
            {%- set nb_p = pending_propositions_count | default(0) -%}
            {% if nb_p > 0 %}
            <span class="ml-auto bg-red-500 text-white text-xs font-bold rounded-full w-4 h-4 flex items-center justify-center flex-shrink-0">
              {{ nb_p }}
            </span>
            {% endif %}
          </a>
        </div>
        {% endif %}

      </nav>
```

- [ ] **Step 2 : Vérification manuelle**

Démarrer l'application et vérifier :
- Gestionnaire : voit les 4 sections (Tableau de bord, Données, Commune, Paramètres), pas la section Administration
- Admin : voit toutes les sections dont Démographie & vie asso. et Administration
- Lien "Ma commune" mène bien à la page de modification de la ville
- Lien "Sources automatiques" → `/upload`, "Sources manuelles" → `/saisie`

```bash
docker compose up -d --build
# Ouvrir http://localhost:5001/admin
```

- [ ] **Step 3 : Commit**

```bash
git add app/templates/admin_base.html
git commit -m "feat: rewrite admin navigation — new sections per role, Ma commune, Sources auto/manuelles"
```

---

## Vérification finale

- [ ] Connexion en tant que gestionnaire :
  - La nav ne montre pas la section Administration
  - Clic sur "Ma commune" → redirigé vers sa propre ville
  - Clic sur `/integrations` (URL directe) → redirigé vers Ma commune
  - Impossible d'accéder à `/villes/modifier/<autre_id>` → flash "Accès refusé"
- [ ] Connexion en tant qu'admin :
  - La nav montre toutes les sections
  - Peut modifier n'importe quelle ville
  - Le breadcrumb "Villes › Modifier" s'affiche correctement

