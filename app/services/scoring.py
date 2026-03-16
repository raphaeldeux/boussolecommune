SCORE_VALEURS = {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1}
VALEUR_SCORES = {5: "A", 4: "B", 3: "C", 2: "D", 1: "E"}

SCORE_COULEURS = {
    "A": "#16a34a",
    "B": "#65a30d",
    "C": "#d97706",
    "D": "#dc2626",
    "E": "#7f1d1d",
}

THEMATIQUE_POIDS = {
    "finances":    0.25,
    "cadre_vie":   0.20,
    "personnes":   0.20,
    "lien_social": 0.15,
    "democratie":  0.12,
    "vivant":      0.08,
}


def calculer_score(valeur, seuil_vert, seuil_orange, seuil_rouge, sens):
    """
    sens = 'haut' : plus la valeur est haute, mieux c'est
    sens = 'bas'  : plus la valeur est basse, mieux c'est
    sens = 'neutre' : pas de score calculé automatiquement -> Claude décide
    """
    if valeur is None or sens == "neutre":
        return None
    if seuil_vert is None and seuil_orange is None and seuil_rouge is None:
        return None

    if sens == "haut":
        if seuil_vert is not None and valeur >= seuil_vert:
            return "A"
        elif seuil_orange is not None and valeur >= seuil_orange:
            return "B"
        elif seuil_rouge is not None and valeur >= seuil_rouge:
            return "C"
        elif seuil_rouge is not None and valeur >= seuil_rouge * 0.75:
            return "D"
        else:
            return "E"
    elif sens == "bas":
        if seuil_vert is not None and valeur <= seuil_vert:
            return "A"
        elif seuil_orange is not None and valeur <= seuil_orange:
            return "B"
        elif seuil_rouge is not None and valeur <= seuil_rouge:
            return "C"
        elif seuil_rouge is not None and valeur <= seuil_rouge * 1.25:
            return "D"
        else:
            return "E"
    return None


def score_vers_valeur(score):
    return SCORE_VALEURS.get(score)


def valeur_vers_score(valeur):
    if valeur is None:
        return None
    rounded = round(valeur)
    rounded = max(1, min(5, rounded))
    return VALEUR_SCORES.get(rounded)


def calculer_score_thematique(indicateurs_avec_donnees):
    """
    indicateurs_avec_donnees : liste de dicts avec clé 'score'
    Retourne une lettre ou None si moins de 3 indicateurs renseignés.
    """
    scores = [i["score"] for i in indicateurs_avec_donnees if i.get("score")]
    if len(scores) < 3:
        return None
    valeurs = [SCORE_VALEURS[s] for s in scores if s in SCORE_VALEURS]
    if not valeurs:
        return None
    moyenne = sum(valeurs) / len(valeurs)
    return valeur_vers_score(moyenne)


def calculer_score_global(scores_thematiques):
    """
    scores_thematiques : dict {thematique: score_lettre}
    Retourne une lettre ou None.
    """
    total_poids = 0
    total_pondere = 0
    for thematique, score in scores_thematiques.items():
        if score and thematique in THEMATIQUE_POIDS:
            poids = THEMATIQUE_POIDS[thematique]
            valeur = SCORE_VALEURS.get(score)
            if valeur:
                total_ponde = poids * valeur
                total_pondere += total_ponde
                total_poids += poids
    if total_poids == 0:
        return None
    moyenne = total_pondere / total_poids
    return valeur_vers_score(moyenne)


def calculer_tendance(valeur_actuelle, valeur_precedente):
    """Retourne '↗', '↘' ou '→' selon l'évolution."""
    if valeur_actuelle is None or valeur_precedente is None:
        return None
    if valeur_actuelle > valeur_precedente * 1.02:
        return "↗"
    elif valeur_actuelle < valeur_precedente * 0.98:
        return "↘"
    else:
        return "→"


def ajuster_score(score_base, valeur_actuelle, valeur_ancienne, valeur_reference, sens):
    """
    Ajuste le score issu des seuils en intégrant :
      - la trajectoire (magnitude réelle de l'évolution)
      - l'écart avec les communes similaires

    Barème trajectoire (sens-aware) :
      mauvais sens  2–10%  → −0.5 | 10–25% → −1.0 | >25% → −1.5
      bon sens      2–25%  → +0.5 | >25%   → +1.0

    Barème comparaison (sens-aware) :
      mauvais sens  10–25% → −0.5 | 25–50% → −1.0 | >50% → −1.5
      bon sens      >10%   → +0.5

    Résultat borné entre E (1) et A (5).
    Retourne None si score_base est None ou sens == 'neutre'.
    """
    if score_base is None or sens == "neutre":
        return score_base

    val = SCORE_VALEURS[score_base]
    ajustement = 0.0

    # Trajectoire
    if valeur_actuelle is not None and valeur_ancienne is not None and valeur_ancienne != 0:
        pct = (valeur_actuelle - valeur_ancienne) / abs(valeur_ancienne)
        # delta positif = évolution dans le bon sens selon le sens de l'indicateur
        delta = pct if sens == "haut" else -pct
        if delta > 0.25:
            ajustement += 1.0
        elif delta > 0.02:
            ajustement += 0.5
        elif delta < -0.25:
            ajustement -= 1.5
        elif delta < -0.10:
            ajustement -= 1.0
        elif delta < -0.02:
            ajustement -= 0.5

    # Comparaison avec communes similaires
    if valeur_actuelle is not None and valeur_reference and valeur_reference != 0:
        ecart = (valeur_actuelle - valeur_reference) / abs(valeur_reference)
        delta_ref = ecart if sens == "haut" else -ecart
        if delta_ref > 0.10:
            ajustement += 0.5
        elif delta_ref < -0.50:
            ajustement -= 1.5
        elif delta_ref < -0.25:
            ajustement -= 1.0
        elif delta_ref < -0.10:
            ajustement -= 0.5

    val_ajuste = max(1, min(5, val + ajustement))
    return valeur_vers_score(round(val_ajuste))
