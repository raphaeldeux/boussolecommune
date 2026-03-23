# Conseil Detail UX — Design Spec

**Goal:** Refonte de la page détail d'un conseil municipal pour réduire la densité et améliorer la hiérarchie visuelle.

**Design validé:** v6 (mockup `design-v6.html`)

---

## Layout

Page centrée (`max-w-3xl`), colonne unique.

### 1. Header compact
- Icône 🏛️ + titre "Conseil municipal" (sans date dans le titre)
- Métadonnées sous le titre : date, présents/total si disponible, lien PDF
- Ligne de stats : total délibérations / adoptées (vert) / rejetées (rouge) / infos (gris)
- Résumé IA tronqué à 2 lignes + bouton "Lire plus" affiché uniquement si le texte dépasse (détection JS via `scrollHeight > clientHeight`)

### 2. Grille thèmes 3×2
- Toujours 6 cases (les 6 thèmes fixes)
- Thème sans délibérations : grisé + non-cliquable
- Thème actif : fond emerald + bordure emerald
- Chaque case : emoji + nom + compteur en badge

### 3. Contenu du thème actif
- Chapeau IA (italique, gris)
- Table récapitulative subventions si ≥ 2 délibérations avec montant + bénéficiaire
- Délibérations avec bordure gauche colorée :
  - ✅ Adopté (`vote.pour > vote.contre`) : `border-left: 3px solid #16a34a; background: #f0fdf4`
  - ❌ Rejeté (`vote.contre >= vote.pour`) : `border-left: 3px solid #dc2626; background: #fff5f5`
  - ℹ Info (pas de vote) : `border-left: 3px solid #d1d5db; background: #f9fafb`
- Badge vote + détail pour/contre/abstentions

## Thèmes fixes (ordre)
Personnes · Finances / RH · Cadre de vie · Lien social · Démocratie · Vivant
