# Conseil Municipal — Affichage structuré par thème

**Date:** 2026-03-21
**Statut:** Approuvé

## Problème

La page publique d'un conseil municipal affiche le résumé citoyen en bloc de texte brut (`whitespace-pre-line`). Les délibérations ne sont pas structurées, les thèmes ne sont pas mis en valeur visuellement, et il n'y a aucun affichage des résultats de votes.

## Objectif

Générer automatiquement (via Groq) un résumé structuré par thème incluant les délibérations et résultats de votes, et afficher ces données sur la page publique sous forme de cartes visuelles semi-formelles / semi-citoyennes.

---

## Structure JSON générée par Groq

```json
{
  "themes": [
    {
      "titre": "Finances",
      "resume": "Résumé de synthèse de la thématique en langage citoyen.",
      "deliberations": [
        {
          "titre": "Vote du budget primitif 2025",
          "description": "Le conseil municipal a approuvé le budget primitif pour l'année 2025.",
          "vote": {"pour": 15, "contre": 2, "abstentions": 1}
        }
      ]
    }
  ]
}
```

Règles :
- `vote` est `null` si aucun vote n'est mentionné pour cette délibération
- `deliberations` peut être vide `[]` si le thème ne contient que des informations sans vote
- `resume` est une courte synthèse (2-4 phrases) du thème en langage citoyen
- Seuls les thèmes effectivement présents dans le PV apparaissent

---

## Changements

### 1. Base de données (`app/database.py`)

Nouvelle colonne dans `conseils` :
```sql
ALTER TABLE conseils ADD COLUMN resume_structure TEXT DEFAULT NULL;
```
Utiliser le helper `_column_exists` existant. Type `TEXT` (JSON sérialisé), pas JSONB, pour rester cohérent avec l'utilisation de psycopg2 sans extras.

### 2. Modèle (`app/models/conseil.py`)

Signature étendue de `set_statut_resume` :
```python
def set_statut_resume(conseil_id, statut, resume_citoyen=None, resume_structure=None)
```

Les 4 combinaisons de champs optionnels produisent ces clauses SET :
- `resume_citoyen=None, resume_structure=None` → `SET statut_resume=%s`
- `resume_citoyen=<val>, resume_structure=None` → `SET statut_resume=%s, resume_citoyen=%s`
- `resume_citoyen=None, resume_structure=<val>` → `SET statut_resume=%s, resume_structure=%s`
- `resume_citoyen=<val>, resume_structure=<val>` → `SET statut_resume=%s, resume_citoyen=%s, resume_structure=%s`

Implémentation recommandée : construire la clause SET dynamiquement avec une liste de `(colonne, valeur)` filtrée sur `is not None`.

### 3. Service Groq (`app/services/ollama_service.py`)

**Stratégie : deux appels Groq séquentiels.**

1. **Premier appel** — prompt `PROMPT_TEMPLATE` existant → produit `resume_texte` (prose)
2. **Deuxième appel** — nouveau prompt `PROMPT_STRUCTURE` → produit uniquement le JSON structuré

`PROMPT_STRUCTURE` demande à Groq de répondre **exclusivement** avec du JSON valide, sans texte autour, en utilisant le même contenu PDF tronqué. Exemple de fin de prompt : `"Réponds uniquement avec du JSON valide, sans texte avant ni après."`

`generer_resume(pdf_path)` retourne un tuple `(resume_texte: str, resume_structure: str | None)` :
- `resume_texte` : toujours retourné (exception si échec)
- `resume_structure` : JSON sérialisé si le deuxième appel réussit et produit du JSON valide ; `None` sinon (erreur loguée, pas propagée)

Validation du JSON : `json.loads()` après réception. Si `json.loads` lève une exception, `resume_structure = None`.

### 4. Route admin (`app/routes/admin.py`)

- Le thread `_run()` dans `conseil_generer_resume` appelle `generer_resume()`, récupère le tuple `(texte, structure)`, sauvegarde les deux via `set_statut_resume(conseil_id, "termine", resume_citoyen=texte, resume_structure=structure)`
- L'endpoint GET `/statut-resume` retourne `resume_structure` **comme objet JSON parsé** (pas comme string) dans la réponse :
  ```python
  import json as _json
  structure = conseil.get("resume_structure")
  return jsonify({
      "statut": conseil.get("statut_resume", "idle"),
      "resume": conseil.get("resume_citoyen"),
      "structure": _json.loads(structure) if structure else None,
  })
  ```

### 5. Route publique (`app/routes/public.py`)

La route `conseil_detail` pré-parse `resume_structure` avant de passer les données au template :
```python
import json as _json
structure = None
raw = conseil.get("resume_structure")
if raw:
    try:
        structure = _json.loads(raw)
    except Exception:
        structure = None
return render_template("public/conseil_detail.html", ..., structure=structure)
```
Le template reçoit `structure` (dict Python ou `None`), jamais une string JSON brute.

### 6. Page publique (`app/templates/public/conseil_detail.html`)

Si `structure` est truthy (dict parsé avec une clé `themes`) :
- Pour chaque thème : carte blanche avec titre en gras, résumé de synthèse en texte normal
- Sous chaque carte : liste des délibérations avec titre, description, et badge de vote coloré
- Badge vote : `Pour X · Contre Y · Abstentions Z` — vert si `pour > contre`, rouge si `contre >= pour`, gris si `vote` est null
- Lien PDF inchangé en haut de page

Si `structure` est `None` (absent ou parse échoué) :
- Fallback sur le bloc `conseil.resume_citoyen` avec `whitespace-pre-line` (comportement actuel)

### 7. Page admin résumé (`app/templates/admin/conseil_resume.html`)

Le polling JS est étendu : quand `statut === 'termine'`, le champ `structure` de la réponse JSON est ignoré côté admin (pas d'affichage — le textarea texte reste l'outil d'édition). Aucune modification JS requise au-delà de l'existant.

---

## Comportement en cas d'erreur

| Situation | Comportement |
|-----------|--------------|
| Groq retourne JSON malformé | `resume_structure = None`, `resume_texte` sauvegardé normalement |
| Deuxième appel Groq échoue (timeout, erreur réseau) | Idem — `resume_structure = None` |
| `resume_structure` en DB est NULL | Page publique affiche texte brut |
| `resume_structure` en DB est JSON invalide (corruption) | Route publique catch l'exception, `structure = None`, affichage texte brut |

---

## Non-inclus (hors scope)

- Édition manuelle du JSON structuré en admin
- Régénération de la structure seule (sans le résumé texte)
- Affichage de la structure dans la liste des conseils (`conseils.html`)
