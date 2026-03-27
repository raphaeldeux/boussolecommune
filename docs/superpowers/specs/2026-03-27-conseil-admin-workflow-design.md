# Refonte workflow admin — Gestion des conseils

## Contexte

Le panel admin de BoussoleCommune permet aux élus et gestionnaires de gérer les conseils municipaux et métropolitains. Chaque conseil a un cycle de vie en deux phases : **avant séance** (préparation de l'ODJ) et **après séance** (dépôt du PV et résumé citoyen).

### Problèmes du workflow actuel

- Le cycle de vie d'un conseil est réparti sur **3 pages séparées** : Modifier, Préparation, Résumé
- La liste affiche **5 boutons par ligne**, sans indication de ce qui reste à faire
- Le PDF du PV se dépose dans "Modifier" (contre-intuitif)
- Aucun statut global visible dans la liste

---

## Design retenu : Fiche conseil unique avec pipeline de statut

### Principe

Fusionner les 3 pages actuelles en une **fiche unique** par conseil, organisée autour d'un stepper de statut à 4 étapes. Les routes d'action (upload, IA, publication) restent des endpoints POST séparés — seule la vue change.

---

## Architecture

### Pages (vues)

| Route actuelle | Route cible | Notes |
|---|---|---|
| `GET /conseils` | `GET /conseils` | Liste refactorée |
| `GET/POST /conseils/nouveau` | `GET/POST /conseils/nouveau` | Formulaire simplifié |
| `GET/POST /conseils/<id>/modifier` | — | Supprimé, intégré dans la fiche |
| `GET/POST /conseils/<id>/preparation` | — | Supprimé, intégré dans la fiche |
| `GET/POST /conseils/<id>/resume` | — | Supprimé, intégré dans la fiche |
| — | `GET/POST /conseils/<id>` | **Nouvelle fiche unique** |

### Endpoints d'action (inchangés)

- `POST /conseils/<id>/publier`
- `POST /conseils/<id>/publier-odj`
- `POST /conseils/<id>/supprimer`
- `POST /conseils/<id>/note-synthese`
- `POST /conseils/<id>/analyser-odj`
- `GET  /conseils/<id>/statut-odj`
- `POST /conseils/<id>/generer-resume`
- `GET  /conseils/<id>/statut-resume`
- `POST /conseils/prochain`

---

## Composants

### 1. Formulaire de création (simplifié)

Le formulaire `conseil_nouveau` se simplifie : **titre, date, type uniquement**. Le PDF et la note de synthèse se déposent depuis la fiche, pas à la création.

Suppression du champ `fichier_pdf` dans le formulaire de création. La route `conseil_nouveau` ne gère plus le fichier.

### 2. Liste des conseils (refactorée)

**Colonnes :**
- Date
- Titre
- Type (badge municipal / métropolitain)
- **Statut** (badge coloré, 4 états) :
  - ⚪ **Nouveau** — conseil créé, rien d'autre
  - 🟡 **ODJ publié** — `odj_publie = true`
  - 🔵 **PV déposé** — `fichier_pdf` présent et `publie = false`
  - 🟢 **Publié** — `publie = true`
- **Prochaine action** (texte gris discret) — calculé selon le statut :
  - Nouveau → "Déposer la note de synthèse"
  - Note déposée, ODJ non publié → "Publier l'ordre du jour"
  - ODJ publié, PV absent → "Déposer le PV après séance"
  - PV présent, résumé absent → "Générer le résumé citoyen"
  - Résumé présent, non publié → "Publier le compte-rendu"
  - Publié → — (rien)
- **Action** : bouton "Gérer →" + lien discret "Supprimer"

Suppression des boutons ODJ, Résumé, Modifier, Publier inline.

### 3. Fiche conseil unique

**URL :** `GET /admin/conseils/<id>` (GET pour affichage, POST pour sauvegarder les champs éditables)

#### Header

- Titre éditable, date, type
- **Stepper horizontal** 4 étapes : *Créé → ODJ publié → PV déposé → Publié*
  - Étape courante mise en évidence (couleur + icône check pour les étapes passées)

#### Bloc "Avant séance" (fond ambre léger)

Toujours visible. Sections :

1. **Infos de base** — titre, date, type (champs éditables, sauvegardés via POST sur la même URL)
2. **Note de synthèse** (confidentielle) — upload PDF, statut "déposée/non déposée", jamais publique
3. **Analyse IA** (affiché seulement si note déposée) — bouton "Analyser avec l'IA" + barre de progression si `statut_odj = en_cours`
4. **Ordre du jour** — affichage lisible des points (numéro + titre + description), édition par point (pas le JSON brut), champ texte libre si pas encore de points IA
5. **Résumé avant séance** — textarea éditable
6. **Publication ODJ** — bouton toggle Publier/Dépublier l'ODJ

#### Bloc "Après séance" (fond ardoise/bleu léger)

Visuellement grisé et non interactif si `date_conseil > today`. Activé dès que la date est passée. Sections :

1. **PV PDF** — upload, statut "déposé/non déposé"
2. **Génération résumé IA** (affiché si PV déposé) — bouton + barre de progression si `statut_resume = en_cours`
3. **Résumé citoyen** — textarea éditable
4. **Publication conseil** — bouton toggle Publier/Dépublier le compte-rendu

#### Enregistrement

Un bouton "Enregistrer" en bas de chaque bloc soumet les champs éditables de ce bloc. Pas un seul bouton global pour toute la page.

---

## Logique de statut

Fonction `_get_conseil_statut(conseil)` à ajouter dans le modèle ou les helpers :

```python
def _get_conseil_statut(conseil):
    if conseil.get("publie"):
        return "publie"
    if conseil.get("fichier_pdf"):
        return "pv_depose"
    if conseil.get("odj_publie"):
        return "odj_publie"
    return "nouveau"

def _get_prochaine_action(conseil):
    statut = _get_conseil_statut(conseil)
    if statut == "publie":
        return None
    if statut == "pv_depose":
        if not conseil.get("resume_citoyen"):
            return "Générer le résumé citoyen"
        return "Publier le compte-rendu"
    if statut == "odj_publie":
        return "Déposer le PV après séance"
    # Nouveau
    if not conseil.get("note_synthese_pdf"):
        return "Déposer la note de synthèse"
    if not conseil.get("odj_texte"):
        return "Publier l'ordre du jour"
    return "Publier l'ordre du jour"
```

---

## Affichage de l'ODJ (non-JSON)

Au lieu d'exposer le JSON brut dans une textarea, l'ODJ est rendu sous forme de liste éditable :

- Si `odj_texte` est parseable : afficher les points avec champs titre/description éditables (ajout/suppression de points)
- Sauvegarder en JSON côté serveur lors du POST
- Si non parseable ou vide : afficher une textarea libre comme fallback

Cette logique se fait côté template Jinja2 + JavaScript léger (ajout/suppression de lignes).

---

## Migrations base de données

Aucune migration nécessaire. Toutes les colonnes requises existent déjà.

---

## Templates à créer/modifier

| Template | Action |
|---|---|
| `admin/conseils.html` | Modifier — nouvelle structure liste |
| `admin/conseil_form.html` | Modifier — supprimer champ PDF |
| `admin/conseil_fiche.html` | **Créer** — fiche unique |
| `admin/conseil_preparation.html` | **Supprimer** (ou garder comme redirect) |
| `admin/conseil_resume.html` | **Supprimer** (ou garder comme redirect) |
| `admin/conseil_form.html` | Modifier |

---

## Routes admin à modifier

| Route | Action |
|---|---|
| `conseil_modifier` | Remplacer par redirect vers la fiche |
| `conseil_nouveau` | Retirer le champ fichier_pdf |
| `conseil_resume` (GET) | Remplacer par redirect vers la fiche |
| `conseil_preparation` (GET) | Remplacer par redirect vers la fiche |
| Nouvelle route `conseil_fiche` | Créer — GET affichage + POST sauvegarde |

---

## Critères de succès

- Un élu peut gérer tout le cycle de vie d'un conseil depuis une seule page
- La liste montre en un coup d'œil l'état de chaque conseil et la prochaine action requise
- Aucune régression fonctionnelle (toutes les actions existantes restent accessibles)
- Les redirects depuis les anciennes URLs évitent les liens brisés
