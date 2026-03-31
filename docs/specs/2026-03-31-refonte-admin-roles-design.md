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
```

### Administrateur

Identique au gestionnaire, plus :

```
── Administration plateforme ──
🏙️ Villes
👥 Utilisateurs
🏛️ Banque de références
```

---

## Pages — description et changements

### Tableau de bord
**Existant, modifié.** Affiche :
- Scores A–E par thématique (cartes/graphiques)
- Activité récente : dernières données importées, derniers conseils publiés, indicateurs sans donnée

La section interprétations disparaît du dashboard (déplacée dans "Indicateurs").

### Sources automatiques
**Existant, renommé.** Anciennement "Import". Page des fetchers API : INSEE RP, SIRENE, BPE, Ma Cantine, OFGL, SRU, ZAN.

### Sources manuelles
**Existant, renommé.** Anciennement "Saisie manuelle". Saisie ligne par ligne + upload CSV.

### Indicateurs
**Nouveau** (page dédiée extraite du dashboard). Tableau des indicateurs avec scores, et pour chaque indicateur : lien pour rédiger ou générer une interprétation via IA.

### Conseils municipaux
**Existant, inchangé.** Upload de PV, génération de résumé citoyen, publication.

### Documents
**Existant, inchangé.** Upload et publication de documents publics (budgets, rapports, etc.).

### Références
**Existant, restructuré.** Fusion de trois pages actuelles ("Références", "Proposer une référence", "Mes propositions") en une seule :
- Section haute : liste des valeurs de référence validées (lecture)
- Section basse : formulaire de proposition + liste de mes propositions avec statut (en attente / validée / rejetée)

### Ma commune
**Existant, étendu.** Anciennement accessible aux super_admin uniquement via "Villes → modifier". Désormais accessible au gestionnaire pour sa propre ville. Deux sections :
- **Informations générales** : nom, slug, population, code INSEE
- **Intégrations** : clés API SIRENE et Mistral (anciennement page "Intégrations" séparée)

Page "Intégrations" séparée supprimée du menu.

### Villes (admin uniquement)
**Existant, modifié.** Liste de toutes les villes avec :
- Bouton d'édition (→ modifier_ville)
- Étoile ⭐ cliquable pour marquer une ville comme "commune vedette" (inline, sans page dédiée)

Page "Communes vedette" séparée supprimée.

### Utilisateurs (admin uniquement)
**Existant, inchangé.**

### Banque de références (admin uniquement)
**Existant, inchangé.** Gestion des strates, des entrées validées, validation des propositions reçues.

---

## Changements d'accès

| Route | Avant | Après |
|-------|-------|-------|
| `modifier_ville/<id>` | super_admin uniquement | gestionnaire peut modifier sa propre ville ; super_admin peut modifier toutes |
| `communes_vedette` | super_admin, page dédiée | supprimée — remplacée par étoile inline dans `/villes` |
| `integrations` | gestionnaire (page séparée) | absorbée dans `modifier_ville` (section Intégrations) |

---

## Hors scope

- Changement des noms de rôles en base de données
- Gestion multi-ville pour un gestionnaire (un gestionnaire = une ville)
- Nouveau design visuel (UI uniquement fonctionnelle)
- Notifications ou alertes dans le dashboard
