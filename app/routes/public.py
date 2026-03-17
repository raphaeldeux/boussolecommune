from flask import Blueprint, render_template, abort
import app.models.indicateur as ind_model
import app.models.donnee as donnee_model
import app.models.interpretation as interp_model
import app.models.pyramide as pyramide_model
import app.models.subvention as subvention_model
from app.services.scoring import (
    calculer_score, ajuster_score, calculer_score_thematique, calculer_score_global,
    calculer_tendance, SCORE_COULEURS, SCORE_VALEURS
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

    tendance = calculer_tendance(donnee_courante["valeur"], valeur_ancienne)

    score = calculer_score(
        donnee_courante["valeur"],
        ind.get("seuil_vert"),
        ind.get("seuil_orange"),
        ind.get("seuil_rouge"),
        ind.get("sens_positif", "neutre"),
    )
    score = ajuster_score(
        score,
        donnee_courante["valeur"],
        valeur_ancienne,
        ind.get("valeur_reference"),
        ind.get("sens_positif", "neutre"),
    )

    interpretation = interp_model.get(ind["id"], donnee_courante["annee"])
    # L'interprétation IA ne remplace le score algorithmique que si celui-ci
    # est None (sens neutre ou seuils absents).
    if score is None and interpretation and interpretation.get("score"):
        score = interpretation["score"]

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


def _build_cartes():
    """Construit la liste des cartes thématiques enrichies (partagée par dashboard et synthese)."""
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

        cartes.append({
            "slug": them,
            "label": ind_model.THEMATIQUE_LABELS[them],
            "question": ind_model.THEMATIQUE_QUESTIONS[them],
            "icon": ind_model.THEMATIQUE_ICONS[them],
            "score": score_them,
            "score_couleur": SCORE_COULEURS.get(score_them) or "#9ca3af",
            "indicateurs_cles": renseignes[:3],
            "nb_renseignes": len(renseignes),
            "nb_total": len(indicateurs),
        })

    score_global = calculer_score_global(scores_thematiques)
    return cartes, score_global


@bp.route("/")
def dashboard():
    cartes, score_global = _build_cartes()
    derniere_maj = donnee_model.get_derniere_maj()
    return render_template(
        "public/dashboard.html",
        cartes=cartes,
        score_global=score_global,
        score_global_couleur=SCORE_COULEURS.get(score_global),
        derniere_maj=derniere_maj,
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

    # Subventions (seulement pour lien_social)
    subventions_years = []
    subventions_lignes = []
    subventions_totaux = []
    subventions_total = 0
    subventions_annee = None
    if slug == "lien_social":
        subventions_years = subvention_model.get_years()
        if subventions_years:
            subventions_annee = subventions_years[0]
            subventions_lignes = subvention_model.get_by_year(subventions_annee)
            subventions_totaux = subvention_model.get_totaux_par_domaine(subventions_annee)
            subventions_total = subvention_model.get_total(subventions_annee)

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
        subventions_years=subventions_years,
        subventions_lignes=subventions_lignes,
        subventions_totaux=subventions_totaux,
        subventions_total=subventions_total,
        subventions_annee=subventions_annee,
    )


@bp.route("/synthese")
def synthese():
    cartes, score_global = _build_cartes()
    radar_labels = [c["label"] for c in cartes]
    radar_values = [SCORE_VALEURS.get(c["score"], 0) for c in cartes]
    radar_colors = [c["score_couleur"] for c in cartes]
    return render_template(
        "public/synthese.html",
        cartes=cartes,
        score_global=score_global,
        score_global_couleur=SCORE_COULEURS.get(score_global) or "#9ca3af",
        radar_labels=radar_labels,
        radar_values=radar_values,
        radar_colors=radar_colors,
    )


@bp.route("/portrait")
def portrait():
    portrait_inds = ind_model.get_by_thematique("portrait")
    stats = []
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
        stats.append({**ind, "donnee": donnee, "pct_evolution": pct_evolution, "annee_ancienne": annee_ancienne})

    from flask import request as _req
    years = pyramide_model.get_years()
    annee_sel = _req.args.get("annee", years[0] if years else None)
    if annee_sel:
        try:
            annee_sel = int(annee_sel)
        except (ValueError, TypeError):
            annee_sel = years[0] if years else None
    pyramide_rows = pyramide_model.get_by_year(annee_sel) if annee_sel else []

    return render_template(
        "public/portrait.html",
        stats=stats,
        pyramide_years=years,
        pyramide_annee=annee_sel,
        pyramide_rows=pyramide_rows,
    )



@bp.route("/api/chat", methods=["POST"])
def chat():
    from flask import request, jsonify
    from app.config import ANTHROPIC_API_KEY

    if not ANTHROPIC_API_KEY:
        return jsonify({"error": "Service non disponible"}), 503

    payload = request.get_json(silent=True)
    if not payload or not payload.get("message"):
        return jsonify({"error": "Message requis"}), 400

    message = payload["message"].strip()[:600]
    history = payload.get("history", [])
    # Garde au plus les 6 derniers messages (3 échanges)
    history = [h for h in history if h.get("role") in ("user", "assistant")][-6:]

    # Contexte : tous les indicateurs avec leur dernière valeur
    lignes_ctx = [
        "Données actuelles de la commune de Sautron (Loire-Atlantique, ~8 600 hab.) :\n"
    ]
    for them in ind_model.get_thematiques():
        lignes_ctx.append(f"### {ind_model.THEMATIQUE_LABELS[them]}")
        for ind in ind_model.get_by_thematique(them):
            d = donnee_model.get_latest(ind["id"])
            if d:
                ligne = f"- {ind['libelle_citoyen']} : {d['valeur']} {ind.get('unite','')} ({d['annee']})"
                interp = interp_model.get(ind["id"], d["annee"])
                if interp and interp.get("phrase_courte"):
                    ligne += f" → {interp['phrase_courte']}"
                lignes_ctx.append(ligne)
            else:
                lignes_ctx.append(f"- {ind['libelle_citoyen']} : donnée non disponible")
        lignes_ctx.append("")

    system = (
        "Tu es un assistant citoyen pour la commune de Sautron (Loire-Atlantique). "
        "Tu réponds aux questions des citoyens sur la gestion et les indicateurs de leur commune. "
        "Ton ton est simple, accessible et bienveillant. Tu es honnête sur les limites des données. "
        "Tu ne portes aucun jugement politique. Tu réponds en français, de façon concise.\n\n"
        + "\n".join(lignes_ctx)
    )

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=system,
            messages=history + [{"role": "user", "content": message}],
        )
        return jsonify({"response": resp.content[0].text})
    except Exception:
        return jsonify({"error": "Erreur lors de la génération de la réponse."}), 500


@bp.route("/methodologie")
def methodologie():
    return render_template("public/methodologie.html")
