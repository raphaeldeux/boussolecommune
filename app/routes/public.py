from flask import Blueprint, render_template, abort
import app.models.indicateur as ind_model
import app.models.donnee as donnee_model
import app.models.interpretation as interp_model
from app.services.scoring import (
    calculer_score, calculer_score_thematique, calculer_score_global,
    calculer_tendance, SCORE_COULEURS
)

bp = Blueprint("public", __name__)


def _enrichir_indicateur(ind, annee=None):
    """Ajoute valeur, score, interprétation, tendance à un indicateur."""
    donnee = donnee_model.get_latest(ind["id"])
    if not donnee:
        return {**ind, "donnee": None, "score": None, "interpretation": None, "tendance": None}

    annee_donnee = annee or donnee["annee"]
    donnee_courante = donnee_model.get_by_indicateur_annee(ind["id"], annee_donnee)
    if not donnee_courante:
        donnee_courante = donnee

    # Pour la tendance, on compare la donnée la plus récente avec la plus ancienne disponible
    historique = donnee_model.get_by_indicateur(ind["id"])  # trié DESC
    donnee_ancienne = historique[-1] if len(historique) > 1 else None
    valeur_ancienne = donnee_ancienne["valeur"] if donnee_ancienne else None
    annee_ancienne = donnee_ancienne["annee"] if donnee_ancienne else None

    # Conserver valeur_n1 pour le service Claude (contexte IA)
    donnee_n1 = donnee_model.get_by_indicateur_annee(ind["id"], donnee_courante["annee"] - 1)
    valeur_n1 = donnee_n1["valeur"] if donnee_n1 else None

    # % d'évolution entre la plus ancienne et la plus récente
    pct_evolution = None
    if valeur_ancienne is not None and valeur_ancienne != 0:
        pct_evolution = round(
            (donnee_courante["valeur"] - valeur_ancienne) / abs(valeur_ancienne) * 100, 1
        )

    score = calculer_score(
        donnee_courante["valeur"],
        ind.get("seuil_vert"),
        ind.get("seuil_orange"),
        ind.get("seuil_rouge"),
        ind.get("sens_positif", "neutre"),
    )

    interpretation = interp_model.get(ind["id"], donnee_courante["annee"])
    if interpretation and interpretation.get("score"):
        score = interpretation["score"]

    tendance = calculer_tendance(donnee_courante["valeur"], valeur_ancienne)

    return {
        **ind,
        "donnee": donnee_courante,
        "score": score,
        "score_couleur": SCORE_COULEURS.get(score),
        "interpretation": interpretation,
        "tendance": tendance,
        "valeur_n1": valeur_n1,
        "valeur_ancienne": valeur_ancienne,
        "annee_ancienne": annee_ancienne,
        "pct_evolution": pct_evolution,
        "historique": historique,
    }


@bp.route("/")
def dashboard():
    thematiques = ind_model.get_thematiques()
    cartes = []
    scores_thematiques = {}

    for them in thematiques:
        indicateurs = ind_model.get_by_thematique(them)
        enrichis = [_enrichir_indicateur(i) for i in indicateurs]
        renseignes = [e for e in enrichis if e["donnee"]]

        score_them = calculer_score_thematique([
            {"score": e["score"]} for e in renseignes
        ])
        scores_thematiques[them] = score_them

        # 3 indicateurs clés = les 3 premiers renseignés
        cles = renseignes[:3]

        cartes.append({
            "slug": them,
            "label": ind_model.THEMATIQUE_LABELS[them],
            "question": ind_model.THEMATIQUE_QUESTIONS[them],
            "icon": ind_model.THEMATIQUE_ICONS[them],
            "score": score_them,
            "score_couleur": SCORE_COULEURS.get(score_them),
            "indicateurs_cles": cles,
            "nb_renseignes": len(renseignes),
            "nb_total": len(indicateurs),
        })

    score_global = calculer_score_global(scores_thematiques)
    derniere_maj = donnee_model.get_derniere_maj()

    # Stats portrait de la commune
    portrait_inds = ind_model.get_by_thematique("portrait")
    stats_portrait = []
    for ind in portrait_inds:
        donnee = donnee_model.get_latest(ind["id"])
        pct_evolution = None
        annee_ancienne = None
        if donnee:
            hist = donnee_model.get_by_indicateur(ind["id"])
            if len(hist) > 1:
                ancienne = hist[-1]
                annee_ancienne = ancienne["annee"]
                if ancienne["valeur"] and ancienne["valeur"] != 0:
                    pct_evolution = round(
                        (donnee["valeur"] - ancienne["valeur"]) / abs(ancienne["valeur"]) * 100, 1
                    )
        stats_portrait.append({
            **ind,
            "donnee": donnee,
            "pct_evolution": pct_evolution,
            "annee_ancienne": annee_ancienne,
        })

    return render_template(
        "public/dashboard.html",
        cartes=cartes,
        score_global=score_global,
        score_global_couleur=SCORE_COULEURS.get(score_global),
        derniere_maj=derniere_maj,
        stats_portrait=stats_portrait,
    )


@bp.route("/thematique/<slug>")
def thematique(slug):
    thematiques_valides = ind_model.get_thematiques()
    if slug not in thematiques_valides:
        abort(404)

    indicateurs = ind_model.get_by_thematique(slug)
    enrichis = [_enrichir_indicateur(i) for i in indicateurs]
    renseignes = [e for e in enrichis if e["donnee"]]

    score_them = calculer_score_thematique([{"score": e["score"]} for e in renseignes])

    interpretation_them = None
    if renseignes:
        derniere_annee = max(e["donnee"]["annee"] for e in renseignes)
        interps = interp_model.get_all_for_thematique(slug, derniere_annee)
        if interps:
            phrases = [i["phrase_courte"] for i in interps if i.get("phrase_courte")]
            interpretation_them = phrases[0] if phrases else None

    return render_template(
        "public/thematique.html",
        slug=slug,
        label=ind_model.THEMATIQUE_LABELS[slug],
        question=ind_model.THEMATIQUE_QUESTIONS[slug],
        icon=ind_model.THEMATIQUE_ICONS[slug],
        indicateurs=enrichis,
        score=score_them,
        score_couleur=SCORE_COULEURS.get(score_them),
        interpretation=interpretation_them,
        score_couleurs=SCORE_COULEURS,
    )
