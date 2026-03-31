# Refonte du panel admin — Rôles et navigation

**Goal:** Clarifier les deux rôles de l'espace admin, donner au gestionnaire accès aux paramètres de sa ville, et réorganiser la navigation pour la rendre cohérente.

---

## Rôles

Deux rôles, inchangés en base de données (`gestionnaire`, `super_admin`) :

| Rôle | Périmètre |
|------|-----------|
| **Gestionnaire** | Tout ce qui concerne sa ville assignée : données, indicateurs, conseils, documents, paramètres de la ville |
| **Administrateur** (`super_admin`) | Plateforme multi-tenant : gestion des villes, des utilisateurs, banque de références — + peut agir comme gestionnaire sur n'importe quelle ville |

Le label affiché dans l'UI passe de "Super-admin" à "Administrateur".

---

## Navigation

### Gestionnaire

```
📊 Tableau de bord

── Données ──
🔄 Sources automatiques
✏️ Sources manuelles

── Commune ──
📊 Indicateurs
📋 Conseils municipaux
📁 Documents

── Paramètres ──
📊 Références
⚙️ Ma commune

── (section cachée aux gestionnaires) ──
Démographie & vie asso.  ← section existante, inchangée, visible admin seulement
```

### Administrateur

Identique au gestionnaire, plus :

```
── Administration plateforme ──
🏙️ Villes
👥 Utilisateurs
🏛️ Banque de références
```

L'administrateur voit aussi la section "Démographie & vie asso." (pyramide, subventions, etc. — existante, inchangée).

---

## Pages — description et changements

### Tableau de bord
**Existant, modifié.** Affiche :
- Scores A–E par thématique (cartes/graphiques)
- Activité récente : dernières données importées, derniers conseils publiés, indicateurs sans donnée

La section interprétations disparaît du dashboard (déplacée dans "Indicateurs").

### Sources automatiques
**Existant, renommé.** Anciennement "Import". Route : `/upload`. Page des fetchers API : INSEE RP, SIRENE, BPE, Ma Cantine, OFGL, SRU, ZAN.

### Sources manuelles
**Existant, renommé.** Anciennement "Saisie manuelle". Route : `/saisie`. Saisie ligne par ligne + upload CSV.

### Indicateurs
**Nouveau — page dédiée extraite du dashboard.** Route : `/indicateurs`.
Tableau des indicateurs avec scores, et pour chaque indicateur : lien pour rédiger ou générer une interprétation via IA. Reprend le contenu de l'actuelle section `#interp-section` du dashboard.

### Conseils municipaux
**Existant, inchangé.** Route : `/conseils`. Upload de PV, génération de résumé citoyen, publication.

### Documents
**Existant, inchangé.** Route : `/documents`. Upload et publication de documents publics (budgets, rapports, etc.).

### Références
**Existant, restructuré — page unique.** Route : `/references`.
Fusion de trois pages actuelles en une seule avec deux sections :
- **Section haute** : liste des valeurs de référence validées (consultation, lecture seule)
- **Section basse** : formulaire de proposition d'une nouvelle valeur + liste de mes propositions avec statut (en attente / validée / rejetée)

Les routes `/proposer-reference` et `/mes-propositions` sont supprimées (ou redirigent vers `/references`).

### Ma commune
**Existant, étendu.** Route : `/ma-commune` (alias vers `/villes/modifier/<ville_id>` selon le rôle).

Deux sections sur une seule page :
- **Informations générales** : nom, slug, population, code INSEE
- **Intégrations** : clés API SIRENE et Mistral

Règles d'accès :
- Gestionnaire : accès à sa propre ville uniquement (vérifié via `session['admin_ville_id']` == `ville_id`)
- Administrateur : accès à toutes les villes

La page "Intégrations" (`/integrations`) est supprimée. Son contenu est absorbé dans "Ma commune".

### Villes (admin uniquement)
**Existant, modifié.** Route : `/villes`. Liste de toutes les villes avec :
- Bouton d'édition (→ `modifier_ville`)
- Étoile ⭐ : bouton POST inline par ville pour basculer le statut "commune vedette" (sans page dédiée)

La page `/communes-vedette` est supprimée.

### Utilisateurs (admin uniquement)
**Existant, inchangé.** Route : `/users`.

### Banque de références (admin uniquement)
**Existant, inchangé.** Routes : `/banque-references`, `/banque-references/entrees`, `/banque-references/propositions`. Gestion des strates, des entrées validées, validation des propositions reçues.

---

## Contrôle d'accès

### Nouvelle règle : gestionnaire et modifier_ville

Ajouter une fonction helper `can_modify_ville(ville_id)` dans `auth.py` ou en inline dans la route :

```python
def can_modify_ville(ville_id):
    """Retourne True si l'utilisateur connecté peut modifier la ville donnée."""
    if session.get('user_role') == 'super_admin':
        return True
    return session.get('admin_ville_id') == ville_id
```

La route `modifier_ville` passe de `@super_admin_required` à `@login_required` + vérification `can_modify_ville`.

### Routes supprimées / redirigées

| Route | Action |
|-------|--------|
| `/integrations` | Supprimée — remplacée par section dans `modifier_ville` |
| `/proposer-reference` | Supprimée — contenu absorbé dans `/references` |
| `/mes-propositions` | Supprimée — contenu absorbé dans `/references` |
| `/communes-vedette` | Supprimée — remplacée par toggle inline dans `/villes` |

---

## Changements d'accès récapitulatifs

| Route | Avant | Après |
|-------|-------|-------|
| `modifier_ville/<id>` | super_admin uniquement | gestionnaire (sa ville) + super_admin (toutes) |
| `communes_vedette` | super_admin, page dédiée | supprimée — étoile inline dans `/villes` |
| `integrations` | gestionnaire (page séparée) | supprimée — absorbée dans `modifier_ville` |
| `proposer_reference` | gestionnaire | supprimée — absorbée dans `/references` |
| `mes_propositions` | gestionnaire | supprimée — absorbée dans `/references` |

---

## Hors scope

- Changement des noms de rôles en base de données
- Gestion multi-ville pour un gestionnaire (un gestionnaire = une ville)
- Nouveau design visuel
- Notifications ou alertes dans le dashboard
- Section "Démographie & vie associative" (pyramide, subventions) — existante, inchangée
