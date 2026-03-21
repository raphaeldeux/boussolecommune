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

- `set_statut_resume(conseil_id, statut, resume_citoyen=None, resume_structure=None)` — signature étendue pour sauvegarder optionnellement les deux champs en une seule requête UPDATE

### 3. Service Groq (`app/services/ollama_service.py`)

- Nouveau prompt `PROMPT_STRUCTURE` qui demande à Groq de générer le JSON structuré
- `generer_resume(pdf_path)` retourne un tuple `(resume_texte: str, resume_structure: str | None)` :
  - `resume_texte` : résumé en prose, compatible avec le textarea admin existant
  - `resume_structure` : JSON sérialisé, `None` si la génération JSON échoue
- Stratégie : un seul appel Groq avec instructions pour générer les deux formats dans une réponse délimitée, ou deux appels séparés si un seul échoue à produire du JSON valide. Priorité : fiabilité (le résumé texte ne doit jamais être bloqué par un JSON malformé).

### 4. Route admin (`app/routes/admin.py`)

- Le thread `_run()` dans `conseil_generer_resume` appelle `generer_resume()`, récupère le tuple, sauvegarde les deux champs via `set_statut_resume()`
- L'endpoint JSON `/statut-resume` retourne aussi `resume_structure` pour permettre une mise à jour côté client

### 5. Page publique (`app/templates/public/conseil_detail.html`)

Si `conseil.resume_structure` est présent et valide :
- Affichage par thèmes : une carte par thème avec titre, résumé de synthèse
- Sous chaque carte : liste des délibérations avec titre, description, badge de vote
- Badge vote : `Pour X · Contre Y · Abstentions Z` (couleur verte si majorité pour, rouge si rejet, gris si pas de vote)
- Lien PDF inchangé en haut

Si `resume_structure` est absent/invalide :
- Fallback sur le texte brut `resume_citoyen` (comportement actuel)

### 6. Page admin résumé (`app/templates/admin/conseil_resume.html`)

- Le polling JS existant est étendu : quand `statut === 'termine'`, on reçoit aussi `resume_structure` et on le stocke dans un champ caché pour un usage futur éventuel (pas d'affichage admin du JSON — le textarea texte reste l'outil d'édition)

---

## Comportement en cas d'erreur JSON

Si Groq génère un JSON malformé, `generer_resume()` :
1. Tente de parser le JSON
2. En cas d'échec : log l'erreur, retourne `None` pour `resume_structure`
3. Le résumé texte est toujours sauvegardé — la structure est un enrichissement optionnel

La page publique se rabat sur l'affichage texte si `resume_structure` est `NULL` ou invalide.

---

## Non-inclus (hors scope)

- Édition manuelle du JSON structuré en admin
- Régénération de la structure seule (sans le résumé texte)
- Affichage de la structure dans la liste des conseils (`conseils.html`)
