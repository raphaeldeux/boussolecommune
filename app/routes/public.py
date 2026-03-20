from flask import Blueprint, render_template, abort, redirect, url_for, session, request, jsonify
import app.models.indicateur as ind_model
import app.models.donnee as donnee_model
import app.models.interpretation as interp_model
import app.models.pyramide as pyramide_model
import app.models.subvention as subvention_model
import app.models.ville as ville_model
import app.models.commune as commune_model
from app.services.scoring import (
    calculer_score, ajuster_score, calculer_score_thematique, calculer_score_global,
    calculer_tendance, SCORE_COULEURS, SCORE_VALEURS
)

bp = Blueprint("public", __name__)


def _get_ville_or_404(slug=None):
    """Retourne la ville courante depuis le slug ou la session."""
    if slug:
        ville = ville_model.get_by_slug(slug)
        if not ville:
            abort(404)
        session["public_ville_id"] = ville["id"]
        return ville

    # Depuis la session
    ville_id = session.get("public_ville_id")
    if ville_id:
        ville = ville_model.get_by_id(ville_id)
        if ville and ville["actif"]:
            return ville

    # Défaut : première ville active
    ville = ville_model.get_first_active()
    if ville:
        session["public_ville_id"] = ville["id"]
    return ville


def _enrichir_indicateur(ind, ville_id=1, annee=None):
    """Ajoute valeur, score, interprétation, tendance à un indicateur."""
    donnee = donnee_model.get_latest(ind["id"], ville_id)
    if not donnee:
        return {**ind, "donnee": None, "score": None, "interpretation": None, "tendance": None}

    annee_donnee = annee or donnee["annee"]
    donnee_courante = donnee_model.get_by_indicateur_annee(ind["id"], annee_donnee, ville_id)
    if not donnee_courante:
        donnee_courante = donnee

    historique = donnee_model.get_by_indicateur(ind["id"], ville_id)
    donnee_ancienne = historique[-1] if len(historique) > 1 else None
    valeur_ancienne = donnee_ancienne["valeur"] if donnee_ancienne else None
    annee_ancienne = donnee_ancienne["annee"] if donnee_ancienne else None

    donnee_n1 = donnee_model.get_by_indicateur_annee(ind["id"], donnee_courante["annee"] - 1, ville_id)
    valeur_n1 = donnee_n1["valeur"] if donnee_n1 else None

    pct_evolution = None
    if valeur_ancienne is not None and valeur_ancienne != 0:
        pct_evolution = round(
            (donnee_courante["valeur"] - valeur_ancienne) / abs(valeur_ancienne) * 100, 1
        )

    tendance = calculer_tendance(donnee_courante["valeur"], valeur_ancienne)

    # Utiliser la référence ville si disponible, sinon la référence globale de l'indicateur
    from app.models.banque_reference import get_ref_for_indicateur_ville
    ref_ville = get_ref_for_indicateur_ville(ind["id"], ville_id)
    valeur_ref = ref_ville["valeur"] if ref_ville else ind.get("valeur_reference")

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
        valeur_ref,
        ind.get("sens_positif", "neutre"),
    )

    interpretation = interp_model.get(ind["id"], donnee_courante["annee"], ville_id)
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
        "valeur_reference": valeur_ref,
        "ref_ville": ref_ville,
    }


def _build_cartes(ville_id=1):
    """Construit la liste des cartes thématiques enrichies."""
    thematiques = ind_model.get_thematiques()
    cartes = []
    scores_thematiques = {}
    tous_enrichis = []

    for them in thematiques:
        indicateurs = ind_model.get_by_thematique(them)
        enrichis = [_enrichir_indicateur(i, ville_id) for i in indicateurs]
        renseignes = [e for e in enrichis if e["donnee"]]

        score_them = calculer_score_thematique([
            {"score": e["score"]} for e in renseignes
        ])
        scores_thematiques[them] = score_them

        annee_max = max((e["donnee"]["annee"] for e in renseignes), default=None)
        for e in renseignes:
            tous_enrichis.append({**e, "_them_label": ind_model.THEMATIQUE_LABELS[them]})

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
            "nb_forts": sum(1 for e in renseignes if e.get("score") in ("A", "B")),
            "nb_defis": sum(1 for e in renseignes if e.get("score") in ("D", "E")),
            "annee_max": annee_max,
        })

    score_global = calculer_score_global(scores_thematiques)

    ORDRE = {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1}
    scored = [e for e in tous_enrichis if e.get("score") in ORDRE]
    scored_desc = sorted(scored, key=lambda e: ORDRE[e["score"]], reverse=True)
    top_inds = scored_desc[:3]
    top_ids = {e["id"] for e in top_inds}
    flop_inds = [e for e in reversed(scored_desc) if e["id"] not in top_ids][:3]

    return cartes, score_global, top_inds, flop_inds


# ── Page de sélection des villes ────────────────────────────────────────

@bp.route("/villes")
def villes():
    villes_list = ville_model.get_all()
    # Enrichir avec score global
    villes_enrichies = []
    for v in villes_list:
        _, score_global, _, _ = _build_cartes(v["id"])
        villes_enrichies.append({
            **v,
            "score_global": score_global,
            "score_couleur": SCORE_COULEURS.get(score_global) or "#9ca3af",
            "has_data": ville_model.has_data(v["id"]),
        })
    return render_template("public/villes.html", villes=villes_enrichies)


# ── Dashboard principal ──────────────────────────────────────────────────

@bp.route("/")
def index():
    """Page d'accueil avec recherche de communes."""
    vedettes = commune_model.get_vedettes()
    nb_communes = commune_model.count_dans_base()
    nb_indicateurs = commune_model.count_indicateurs()
    return render_template(
        "public/index.html",
        vedettes=vedettes,
        nb_communes=nb_communes,
        nb_indicateurs=nb_indicateurs,
        score_couleurs=SCORE_COULEURS,
    )


@bp.route("/recherche")
def recherche():
    """Recherche de communes sans JS (fallback GET form)."""
    q = request.args.get("q", "").strip()
    resultats = []
    if len(q) >= 2:
        if commune_model.is_empty():
            resultats = commune_model.search_fallback(q, limit=20)
        else:
            resultats = commune_model.search(q, limit=20)
    return render_template(
        "public/recherche.html",
        q=q,
        resultats=resultats,
        score_couleurs=SCORE_COULEURS,
    )


@bp.route("/api/recherche")
def api_recherche():
    """API JSON pour l'autocomplétion."""
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    if commune_model.is_empty():
        resultats = commune_model.search_fallback(q)
    else:
        resultats = commune_model.search(q)
    return jsonify(resultats)


def _sync_ville_code_insee(ville_id: int, code_insee: str) -> None:
    """Met à jour villes.code_insee depuis le référentiel communes (une seule fois)."""
    try:
        from app.database import get_db
        conn = get_db()
        conn.execute("UPDATE villes SET code_insee = %s WHERE id = %s AND code_insee IS NULL",
                     (code_insee, ville_id))
        conn.commit()
        conn.close()
    except Exception:
        pass


@bp.route("/commune/<slug>")
def commune(slug):
    """Page d'une commune : redirige vers dashboard si gérée, sinon page 'bientôt'."""
    commune_data = commune_model.get_by_slug(slug)
    if not commune_data:
        # Fallback : slug provenant de villes (avant seed_communes)
        ville = ville_model.get_by_slug(slug)
        if ville:
            return redirect(url_for("public.dashboard", ville_slug=ville["slug"]))
        abort(404)
    # Vérifier si la commune a une ville gérée associée
    ville = None
    if commune_data.get("code_insee"):
        ville = ville_model.get_by_code_insee(commune_data["code_insee"])
    if not ville:
        # Fallback : chercher par slug dérivé du nom (villes créées avant seed_communes)
        from app.models.commune import normaliser as _norm
        nom_slug = _norm(commune_data["nom"]).replace(" ", "-")
        ville = ville_model.get_by_slug(nom_slug)
        if ville and commune_data.get("code_insee"):
            # Mettre à jour code_insee pour les prochaines requêtes
            _sync_ville_code_insee(ville["id"], commune_data["code_insee"])
    if ville:
        return redirect(url_for("public.dashboard", ville_slug=ville["slug"]))
    # Commune présente dans le référentiel mais pas encore gérée
    # Suggestions : villes gérées du même département (max 3)
    suggestions = []
    dep_code = commune_data.get("departement_code") or (
        commune_data["code_insee"][:2] if commune_data.get("code_insee") else None
    )
    if dep_code:
        all_villes = ville_model.get_all()
        for v in all_villes:
            v_dep = (v.get("code_insee") or "")[:2]
            if v_dep == dep_code and ville_model.has_data(v["id"]):
                _, sg, _, _ = _build_cartes(v["id"])
                suggestions.append({**v, "score_global": sg,
                                    "score_couleur": SCORE_COULEURS.get(sg) or "#9ca3af"})
                if len(suggestions) >= 3:
                    break
    return render_template("public/commune_bientot.html", commune=commune_data,
                           suggestions=suggestions)


@bp.route("/v/<ville_slug>/")
def dashboard(ville_slug):
    ville = _get_ville_or_404(ville_slug)
    cartes, score_global, top_inds, flop_inds = _build_cartes(ville["id"])
    derniere_maj = donnee_model.get_derniere_maj(ville["id"])
    return render_template(
        "public/dashboard.html",
        ville=ville,
        cartes=cartes,
        score_global=score_global,
        score_global_couleur=SCORE_COULEURS.get(score_global) or "#9ca3af",
        derniere_maj=derniere_maj,
        top_inds=top_inds,
        flop_inds=flop_inds,
        radar_labels=[c["label"] for c in cartes],
        radar_values=[SCORE_VALEURS.get(c["score"], 0) for c in cartes],
        radar_colors=[c["score_couleur"] for c in cartes],
    )


@bp.route("/v/<ville_slug>/thematique/<slug>")
def thematique(ville_slug, slug):
    ville = _get_ville_or_404(ville_slug)
    thematiques_valides = ind_model.get_thematiques()
    if slug not in thematiques_valides:
        abort(404)

    indicateurs = ind_model.get_by_thematique(slug)
    enrichis = [_enrichir_indicateur(i, ville["id"]) for i in indicateurs]
    renseignes = [e for e in enrichis if e["donnee"]]

    grouped = {
        "forts":    [e for e in renseignes if e["score"] in ("A", "B")],
        "vigil":    [e for e in renseignes if e["score"] == "C"],
        "preocc":   [e for e in renseignes if e["score"] in ("D", "E")],
        "no_score": [e for e in renseignes if not e["score"]],
        "unset":    [e for e in enrichis   if not e["donnee"]],
    }

    score_them = calculer_score_thematique([{"score": e["score"]} for e in renseignes])

    interpretation_them = None
    if renseignes:
        derniere_annee = max(e["donnee"]["annee"] for e in renseignes)
        interps = interp_model.get_all_for_thematique(slug, derniere_annee, ville["id"])
        if interps:
            phrases = [i["phrase_courte"] for i in interps if i.get("phrase_courte")]
            interpretation_them = phrases[0] if phrases else None

    subventions_years = []
    subventions_lignes = []
    subventions_totaux = []
    subventions_total = 0
    subventions_annee = None
    subventions_prev_total = 0
    subventions_evol_globale = None   # float ou None
    subventions_prev_by_nom = {}      # {nom: montant_annee_precedente}

    subventions_years = subvention_model.get_years(ville["id"], thematique=slug)
    if subventions_years:
        # US-SUB-03 : lire le paramètre d'année dans l'URL
        annee_param = request.args.get("annee_subv")
        if annee_param and annee_param.isdigit() and int(annee_param) in subventions_years:
            subventions_annee = int(annee_param)
        else:
            subventions_annee = subventions_years[0]

        subventions_lignes = subvention_model.get_by_year(subventions_annee, ville["id"], thematique=slug)
        subventions_totaux = subvention_model.get_totaux_par_domaine(subventions_annee, ville["id"], thematique=slug)
        subventions_total = subvention_model.get_total(subventions_annee, ville["id"], thematique=slug)

        # US-SUB-04 : évolution vs année précédente disponible
        prev_annee = subvention_model.get_previous_year(subventions_annee, ville["id"], thematique=slug)
        if prev_annee:
            subventions_prev_total = subvention_model.get_total(prev_annee, ville["id"], thematique=slug)
            if subventions_prev_total:
                subventions_evol_globale = (subventions_total - subventions_prev_total) / subventions_prev_total * 100
            for l in subvention_model.get_by_year(prev_annee, ville["id"], thematique=slug):
                subventions_prev_by_nom[l["nom_beneficiaire"]] = l["montant"]

    nav_thematiques = [
        {
            "slug": s,
            "label": ind_model.THEMATIQUE_LABELS[s],
            "icon": ind_model.THEMATIQUE_ICONS[s],
        }
        for s in ind_model.get_thematiques()
    ]

    return render_template(
        "public/thematique.html",
        ville=ville,
        slug=slug,
        label=ind_model.THEMATIQUE_LABELS[slug],
        question=ind_model.THEMATIQUE_QUESTIONS[slug],
        icon=ind_model.THEMATIQUE_ICONS[slug],
        indicateurs=enrichis,
        grouped=grouped,
        score=score_them,
        score_couleur=SCORE_COULEURS.get(score_them),
        interpretation=interpretation_them,
        score_couleurs=SCORE_COULEURS,
        nav_thematiques=nav_thematiques,
        subventions_years=subventions_years,
        subventions_lignes=subventions_lignes,
        subventions_totaux=subventions_totaux,
        subventions_total=subventions_total,
        subventions_annee=subventions_annee,
        subventions_evol_globale=subventions_evol_globale,
        subventions_prev_by_nom=subventions_prev_by_nom,
    )


@bp.route("/v/<ville_slug>/subventions-fragment")
def subventions_fragment(ville_slug):
    """Renvoie le fragment HTML barre+tableau pour un changement d'année sans rechargement."""
    ville = _get_ville_or_404(ville_slug)
    slug = request.args.get("slug", "lien_social")
    thematiques_valides = ind_model.get_thematiques()
    if slug not in thematiques_valides:
        abort(404)

    years = subvention_model.get_years(ville["id"], thematique=slug)
    annee_param = request.args.get("annee")
    if annee_param and annee_param.isdigit() and int(annee_param) in years:
        annee = int(annee_param)
    else:
        annee = years[0] if years else None
    if not annee:
        return "", 204

    lignes  = subvention_model.get_by_year(annee, ville["id"], thematique=slug)
    totaux  = subvention_model.get_totaux_par_domaine(annee, ville["id"], thematique=slug)
    total   = subvention_model.get_total(annee, ville["id"], thematique=slug)

    prev_annee = subvention_model.get_previous_year(annee, ville["id"], thematique=slug)
    evol_globale = None
    prev_by_nom  = {}
    if prev_annee:
        prev_total = subvention_model.get_total(prev_annee, ville["id"], thematique=slug)
        if prev_total:
            evol_globale = (total - prev_total) / prev_total * 100
        for l in subvention_model.get_by_year(prev_annee, ville["id"], thematique=slug):
            prev_by_nom[l["nom_beneficiaire"]] = l["montant"]

    return render_template(
        "public/_subventions_content.html",
        subventions_lignes=lignes,
        subventions_totaux=totaux,
        subventions_total=total,
        subventions_annee=annee,
        subventions_evol_globale=evol_globale,
        subventions_prev_by_nom=prev_by_nom,
    )


@bp.route("/v/<ville_slug>/portrait")
def portrait(ville_slug):
    ville = _get_ville_or_404(ville_slug)
    portrait_inds = ind_model.get_by_thematique("portrait")
    stats = []
    for ind in portrait_inds:
        donnee = donnee_model.get_latest(ind["id"], ville["id"])
        pct_evolution = None
        annee_ancienne = None
        if donnee:
            hist = donnee_model.get_by_indicateur(ind["id"], ville["id"])
            if len(hist) > 1:
                ancienne = hist[-1]
                annee_ancienne = ancienne["annee"]
                if ancienne["valeur"] and ancienne["valeur"] != 0:
                    pct_evolution = round(
                        (donnee["valeur"] - ancienne["valeur"]) / abs(ancienne["valeur"]) * 100, 1
                    )
        stats.append({**ind, "donnee": donnee, "pct_evolution": pct_evolution, "annee_ancienne": annee_ancienne})

    years = pyramide_model.get_years(ville["id"])
    annee_sel = request.args.get("annee", years[0] if years else None)
    if annee_sel:
        try:
            annee_sel = int(annee_sel)
        except (ValueError, TypeError):
            annee_sel = years[0] if years else None
    pyramide_rows = pyramide_model.get_by_year(annee_sel, ville["id"]) if annee_sel else []

    return render_template(
        "public/portrait.html",
        ville=ville,
        stats=stats,
        pyramide_years=years,
        pyramide_annee=annee_sel,
        pyramide_rows=pyramide_rows,
    )


# ── Comparaison entre villes ────────────────────────────────────────────

@bp.route("/comparer")
def comparer():
    villes_list = ville_model.get_all()
    villes_avec_data = [v for v in villes_list if ville_model.has_data(v["id"])]

    slugs_sel = request.args.getlist("v")
    villes_sel = []
    comparaison = []

    if slugs_sel:
        for slug in slugs_sel[:4]:
            v = ville_model.get_by_slug(slug)
            if v and ville_model.has_data(v["id"]):
                villes_sel.append(v)

    if len(villes_sel) >= 2:
        thematiques = ind_model.get_thematiques()
        for v in villes_sel:
            cartes, score_global, _, _ = _build_cartes(v["id"])
            scores_them = {c["slug"]: {"score": c["score"], "couleur": c["score_couleur"],
                                       "nb_forts": c["nb_forts"], "nb_defis": c["nb_defis"]} for c in cartes}
            comparaison.append({
                "ville": v,
                "score_global": score_global,
                "score_global_couleur": SCORE_COULEURS.get(score_global) or "#9ca3af",
                "scores_thematiques": scores_them,
            })

    # Contexte de retour : si on vient d'une page ville, on passe la ville
    # pour que base.html affiche le header ville + les tabs de navigation
    retour_slug = request.args.get("retour")
    ville_retour = ville_model.get_by_slug(retour_slug) if retour_slug else None

    return render_template(
        "public/comparer.html",
        villes=villes_avec_data,
        villes_sel=villes_sel,
        comparaison=comparaison,
        thematiques=ind_model.get_thematiques(),
        thematique_labels=ind_model.THEMATIQUE_LABELS,
        thematique_icons=ind_model.THEMATIQUE_ICONS,
        ville=ville_retour,
    )


@bp.route("/methodologie")
def methodologie():
    retour_slug = request.args.get("retour")
    ville_retour = ville_model.get_by_slug(retour_slug) if retour_slug else None
    return render_template("public/methodologie.html", ville=ville_retour)
