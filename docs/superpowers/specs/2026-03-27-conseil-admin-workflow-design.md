# Refonte workflow admin — Gestion des conseils

## Contexte

Le panel admin de BoussoleCommune permet aux élus et gestionnaires de gérer les conseils municipaux et métropolitains. Chaque conseil a un cycle de vie en deux phases : **avant séance** (préparation de l'ODJ) et **après séance** (dépôt du PV et résumé citoyen).

### Problèmes du workflow actuel

- Le cycle de vie d'un conseil est réparti sur **3 pages séparées** : Modifier, Préparation, Résumé
- La liste affiche **5 boutons par ligne**, sans indication de ce qui reste à faire
- Le PDF du PV se dépose dans "Modifier" (contre-intuitif)
- Aucun statut global visible dans la liste
- La suppression d'un conseil ne supprime pas le fichier `note_synthese_pdf` du disque (fuite de données confidentielles)

---

## Design retenu : Fiche conseil unique avec pipeline de statut

### Principe

Fusionner les 3 pages actuelles en une **fiche unique** par conseil, organisée autour d'un stepper de statut. Les routes d'action (upload, IA, publication) restent des endpoints POST séparés — seule la vue change.

---

## Architecture

### Pages (vues)

| Route actuelle | Route cible | Notes |
|---|---|---|
| `GET /conseils` | `GET /conseils` | Liste refactorée |
| `GET/POST /conseils/nouveau` | `GET/POST /conseils/nouveau` | Formulaire simplifié |
| `GET/POST /conseils/<id>/modifier` | `GET /conseils/<id>` (redirect) | Supprimé, remplacé par redirect vers la fiche |
| `GET/POST /conseils/<id>/preparation` | `GET /conseils/<id>` (redirect) | Supprimé, remplacé par redirect vers la fiche |
| `GET/POST /conseils/<id>/resume` | `GET /conseils/<id>` (redirect) | Supprimé, remplacé par redirect vers la fiche |
| — | `GET/POST /conseils/<id>` | **Nouvelle fiche unique** |

### Endpoints d'action (cibles de redirect mises à jour)

Ces endpoints restent fonctionnellement inchangés, mais leurs redirects en cas de succès **et d'erreur** pointent désormais vers `admin.conseil_fiche` (et non plus vers `admin.conseil_preparation` ou `admin.conseil_resume`) :

- `POST /conseils/<id>/publier` → redirige vers `admin.conseil_fiche`
- `POST /conseils/<id>/publier-odj` → redirige vers `admin.conseil_fiche`
- `POST /conseils/<id>/supprimer` → redirige vers `admin.conseils` (liste)
- `POST /conseils/<id>/note-synthese` → redirige vers `admin.conseil_fiche` **dans tous les cas** (succès, fichier absent, PDF invalide) — mettre à jour les 3 branches de `conseil_upload_note`
- `POST /conseils/<id>/analyser-odj` → redirige vers `admin.conseil_fiche` (erreur et succès)
- `GET  /conseils/<id>/statut-odj` — inchangé
- `POST /conseils/<id>/pv-pdf` → **nouveau** (voir ci-dessous)
- `POST /conseils/<id>/generer-resume` → redirige vers `admin.conseil_fiche`
- `GET  /conseils/<id>/statut-resume` — inchangé
- `POST /conseils/prochain` — inchangé

---

## Composants

### 1. Formulaire de création (simplifié)

Le formulaire `conseil_nouveau` se simplifie : **titre, date, type uniquement**. Le PDF et la note de synthèse se déposent depuis la fiche, pas à la création.

Suppression du champ `fichier_pdf` dans le formulaire de création et dans le POST handler `conseil_nouveau`.

### 2. Nouveau endpoint : dépôt du PV PDF

**`POST /conseils/<id>/pv-pdf`** — route `conseil_upload_pv`

Reprend la logique de `conseil_modifier` pour le PV PDF uniquement :
- Validation extension + signature PDF (réutiliser `_is_valid_pdf` + `_save_pdf`)
- Appel `conseil_model.update_pdf(conseil_id, filename)` (ou `conseil_model.update` avec le champ fichier)
- Redirige vers `admin.conseil_fiche`

### 3. Suppression — nettoyage complet des fichiers

`conseil_supprimer` doit supprimer **les deux fichiers**.

Le modèle `conseil_model.delete()` retourne actuellement uniquement `fichier_pdf`. Il faut le modifier pour retourner un tuple `(fichier_pdf, note_synthese_pdf)` (ou un dict). La route récupère le conseil avant la suppression pour avoir les deux valeurs, puis supprime :
- `fichier_pdf` depuis `CONSEILS_UPLOAD_DIR`
- `note_synthese_pdf` depuis `NOTES_SYNTHESE_DIR`

### 4. Liste des conseils (refactorée)

**Colonnes :**
- Date
- Titre
- Type (badge municipal / métropolitain)
- **Statut** (badge coloré, 4 états intentionnellement coarse — la colonne "Prochaine action" assure la granularité) :
  - ⚪ **Nouveau** — conseil créé, rien d'autre
  - 🟡 **ODJ publié** — `odj_publie = true`
  - 🔵 **PV déposé** — `fichier_pdf` présent et `publie = false`
  - 🟢 **Publié** — `publie = true`
- **Prochaine action** (texte gris discret) — calculé par `_get_prochaine_action()` :
  - Nouveau, pas de note → "Déposer la note de synthèse"
  - Note déposée, ODJ non publié → "Publier l'ordre du jour"
  - ODJ publié, PV absent → "Déposer le PV après séance"
  - PV présent, résumé absent → "Générer le résumé citoyen"
  - Résumé présent, non publié → "Publier le compte-rendu"
  - Publié → — (rien)
- **Action** : bouton "Gérer →" + lien discret "Supprimer"

Suppression des boutons ODJ, Résumé, Modifier, Publier inline.

### 5. Fiche conseil unique

**URL :** `GET /admin/conseils/<id>` (GET pour affichage, POST pour sauvegarder les champs éditables)

#### Formulaires POST dans la fiche

La fiche contient **deux formulaires indépendants** avec un champ caché `bloc` pour discriminer côté serveur :

- `bloc=avant_seance` — sauvegarde titre, date, type, odj_texte, resume_avant_seance
- `bloc=apres_seance` — sauvegarde resume_citoyen

Le POST handler `conseil_fiche` lit `request.form.get("bloc")` et n'enregistre que les champs du bloc concerné.

#### Header

- **Stepper horizontal** 4 étapes : *Créé → ODJ publié → PV déposé → Publié*
  - Étape courante mise en évidence, étapes passées avec icône check

#### Bloc "Avant séance" (fond ambre léger)

Toujours visible et interactif. Sections :

1. **Infos de base** — titre, date, type (champs éditables dans le formulaire `bloc=avant_seance`)
2. **Note de synthèse** (confidentielle) — upload via `POST /note-synthese`, statut "déposée/non déposée", jamais publique
3. **Analyse IA** (affiché seulement si note déposée) — bouton `POST /analyser-odj` + barre de progression si `statut_odj = en_cours`
4. **Ordre du jour** — voir section "Affichage de l'ODJ"
5. **Résumé avant séance** — textarea dans le formulaire `bloc=avant_seance`
6. **Publication ODJ** — bouton `POST /publier-odj`

#### Bloc "Après séance" (fond ardoise/bleu léger)

Sections affichées mais inputs désactivés (`disabled`) si `date_conseil > today`. Un message contextuel explique pourquoi ("Le conseil n'a pas encore eu lieu"). Les champs restent accessibles visuellement. Un élu peut forcer l'accès manuellement en modifiant la date du conseil dans le bloc "Avant séance".

Sections :

1. **PV PDF** — upload via `POST /pv-pdf`, statut "déposé/non déposé"
2. **Génération résumé IA** (affiché si PV déposé) — bouton `POST /generer-resume` + barre de progression si `statut_resume = en_cours`
3. **Résumé citoyen** — textarea dans le formulaire `bloc=apres_seance`
4. **Publication conseil** — bouton `POST /publier`

---

## Logique de statut

Fonctions helpers à ajouter dans `app/routes/admin.py` (ou extraites dans un module partagé) :

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
    if conseil.get("publie"):
        return None
    if conseil.get("fichier_pdf"):
        if not conseil.get("resume_citoyen"):
            return "Générer le résumé citoyen"
        return "Publier le compte-rendu"
    if conseil.get("odj_publie"):
        return "Déposer le PV après séance"
    # Nouveau
    if not conseil.get("note_synthese_pdf"):
        return "Déposer la note de synthèse"
    return "Publier l'ordre du jour"
```

---

## Affichage de l'ODJ (non-JSON)

Au lieu d'exposer le JSON brut dans une textarea, l'ODJ est rendu sous forme de liste éditable :

- Si `odj_texte` est parseable JSON (`{"points": [...]}`) : afficher les points avec champs `titre` et `description` éditables, boutons "Ajouter un point" / "Supprimer"
- Sauvegarder en reconstruisant le JSON côté serveur lors du POST `bloc=avant_seance`
- Si non parseable ou vide : afficher une textarea libre comme fallback, sauvegarder tel quel

JavaScript léger (vanilla) gère l'ajout/suppression de points dans le DOM. Lors du submit, les champs sont sérialisés côté serveur en JSON.

**Contrat de sérialisation :**
- Nommage des champs : `odj_point_titre_1`, `odj_point_description_1`, `odj_point_titre_2`, etc. (index 1-based, continus)
- Le serveur itère de 1 à N jusqu'à ce qu'il ne trouve plus de `odj_point_titre_N` dans le form
- Les suppressions de points intermédiaires sont gérées côté JS en renumérotant les champs avant submit (pas de trous dans la séquence)
- Résultat JSON : `{"points": [{"numero": 1, "titre": "...", "description": "..."}, ...]}`
- Si aucun champ `odj_point_titre_1` n'est présent mais qu'un champ `odj_texte` (fallback) est présent, sauvegarder tel quel

`conseil_resume.html` sera conservé comme redirect simple vers la fiche. Son contenu (y compris le lien vers `conseil_modifier`) n'a pas besoin d'être mis à jour avant d'être retiré — un redirect 302 est suffisant.

---

## Migrations base de données

Aucune migration nécessaire. Toutes les colonnes requises existent déjà.

---

## Templates à créer/modifier

| Template | Action |
|---|---|
| `admin/conseils.html` | Modifier — nouvelle structure liste (statut + prochaine action + un seul bouton) |
| `admin/conseil_form.html` | Modifier — supprimer le champ `fichier_pdf` |
| `admin/conseil_fiche.html` | **Créer** — fiche unique (remplace modifier + preparation + resume) |
| `admin/conseil_preparation.html` | Conserver uniquement comme redirect vers la fiche |
| `admin/conseil_resume.html` | Conserver uniquement comme redirect vers la fiche |

---

## Routes admin à modifier

| Route | Action |
|---|---|
| `conseil_modifier` (GET) | Redirect vers `admin.conseil_fiche` |
| `conseil_modifier` (POST) | Supprimer — remplacé par `conseil_upload_pv` pour le PDF et `conseil_fiche` POST pour les métadonnées |
| `conseil_nouveau` | Retirer le champ et la logique `fichier_pdf` |
| `conseil_resume` (GET) | Redirect vers `admin.conseil_fiche` |
| `conseil_preparation` (GET) | Redirect vers `admin.conseil_fiche` |
| `conseil_publier` | Mettre à jour redirect cible → `admin.conseil_fiche` |
| `conseil_publier_odj` | Mettre à jour redirect cible → `admin.conseil_fiche` |
| `conseil_analyser_odj` | Mettre à jour redirects (succès + erreur) → `admin.conseil_fiche` |
| `conseil_generer_resume` | Mettre à jour redirects (succès + erreur) → `admin.conseil_fiche` |
| `conseil_supprimer` | Ajouter suppression de `note_synthese_pdf` depuis `NOTES_SYNTHESE_DIR` ; mettre à jour `conseil_model.delete()` pour retourner aussi `note_synthese_pdf` |
| `conseil_upload_pv` | **Créer** — `POST /conseils/<id>/pv-pdf` |
| `conseil_fiche` | **Créer** — `GET/POST /conseils/<id>` |

---

## Critères de succès

- Un élu peut gérer tout le cycle de vie d'un conseil depuis une seule page
- La liste montre en un coup d'œil l'état de chaque conseil et la prochaine action requise
- Aucune régression fonctionnelle (toutes les actions existantes restent accessibles)
- Les anciens URLs (`/modifier`, `/preparation`, `/resume`) redirigent vers la fiche
- La suppression d'un conseil nettoie tous les fichiers associés (PV + note de synthèse)
