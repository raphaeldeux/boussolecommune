import json
import os
import tempfile
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app, jsonify, Response, abort
from app.auth import login_required, super_admin_required, is_rate_limited, record_attempt
import app.models.indicateur as ind_model
import app.models.donnee as donnee_model
import app.models.interpretation as interp_model
from app.models.interpretation import LIMITE_PHRASE_COURTE, LIMITE_PHRASE_LONGUE
import app.models.pyramide as pyramide_model
import app.models.subvention as subvention_model
import app.models.ville as ville_model
import app.models.user as user_model
import app.models.banque_reference as banque_ref_model
import app.models.commune as commune_model
import app.models.refs_banque as refs_banque_model
from app.database import get_db
from app.services.scoring import calculer_score, ajuster_score, calculer_score_thematique, SCORE_COULEURS
from app.services.parser_csv import parser_generique
from app.services.parser_ofgl import parser_ofgl
from app.services.fetchers.macantine import fetch_cantine_data

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.context_processor
def inject_admin_context():
    """Injecte la ville courante, les villes accessibles et le nb de propositions en attente."""
    if session.get("user_id"):
        nb_pending = 0
        if session.get("user_role") == "super_admin":
            try:
                nb_pending = refs_banque_model.count_pending()
            except Exception:
                pass
        return {
            "admin_current_ville": _get_current_ville(),
            "admin_user_villes": _get_user_villes(),
            "pending_propositions_count": nb_pending,
        }
    return {"admin_current_ville": None, "admin_user_villes": [], "pending_propositions_count": 0}


def _get_current_ville():
    """Retourne la ville courante pour l'admin depuis la session."""
    ville_id = session.get("admin_ville_id")
    if ville_id:
        v = ville_model.get_by_id(ville_id)
        if v:
            return v
    # Pour gestionnaire, prendre sa première ville assignée
    user_id = session.get("user_id")
    role = session.get("user_role")
    if role == "gestionnaire" and user_id:
        villes = user_model.get_villes(user_id)
        if villes:
            session["admin_ville_id"] = villes[0]["id"]
            return villes[0]
    # Super admin : première ville active
    v = ville_model.get_first_active()
    if v:
        session["admin_ville_id"] = v["id"]
    return v


def _get_user_villes():
    """Retourne les villes accessibles par l'utilisateur courant."""
    role = session.get("user_role")
    if role == "super_admin":
        return ville_model.get_all()
    user_id = session.get("user_id")
    return user_model.get_villes(user_id) if user_id else []


# ── Authentification ─────────────────────────────────────────────────────

@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ip = request.remote_addr
        if is_rate_limited(ip):
            flash("Trop de tentatives. Réessayez dans 15 minutes.", "danger")
            return render_template("admin/login.html")
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = user_model.verify_password(username, password)
        if user:
            session.permanent = True
            session["user_id"] = user["id"]
            session["user_role"] = user["role"]
            session["username"] = user["username"]
            session.pop("admin_ville_id", None)  # reset ville selection
            flash("Connexion réussie.", "success")
            return redirect(url_for("admin.dashboard"))
        else:
            record_attempt(ip)
            flash("Identifiants incorrects.", "danger")
    return render_template("admin/login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Déconnexion réussie.", "info")
    return redirect(url_for("admin.login"))


# ── Changement de ville courante ─────────────────────────────────────────

@bp.route("/set-ville/<int:ville_id>", methods=["POST"])
@login_required
def set_ville(ville_id):
    role = session.get("user_role")
    if role != "super_admin":
        # Vérifier que la ville est bien assignée à l'utilisateur
        user_villes = user_model.get_villes(session["user_id"])
        if not any(v["id"] == ville_id for v in user_villes):
            flash("Accès non autorisé à cette ville.", "danger")
            return redirect(url_for("admin.dashboard"))
    v = ville_model.get_by_id(ville_id)
    if v:
        session["admin_ville_id"] = ville_id
        flash(f"Ville sélectionnée : {v['nom']}", "success")
    return redirect(url_for("admin.dashboard"))


# ── Dashboard ────────────────────────────────────────────────────────────

@bp.route("/")
@login_required
def dashboard():
    ville = _get_current_ville()
    if not ville:
        flash("Aucune ville disponible. Créez une ville d'abord.", "warning")
        if session.get("user_role") == "super_admin":
            return redirect(url_for("admin.villes"))
        return render_template("admin/dashboard.html", stats=[], ville=None, user_villes=[])

    user_villes = _get_user_villes()
    thematiques = ind_model.get_thematiques() + ["portrait"]
    stats = []
    total_donnees = 0
    total_donnees_max = 0
    total_interp_ok = 0
    total_interp_needed = 0
    for them in thematiques:
        indicateurs = ind_model.get_by_thematique(them)
        nb_renseignes = 0
        nb_interp_ok = 0
        scores = []
        rows = []
        for ind in indicateurs:
            donnee = donnee_model.get_latest(ind["id"], ville["id"])
            interp = None
            score = None
            if donnee:
                nb_renseignes += 1
                score = calculer_score(
                    donnee["valeur"], ind.get("seuil_vert"),
                    ind.get("seuil_orange"), ind.get("seuil_rouge"),
                    ind.get("sens_positif", "neutre")
                )
                interp = interp_model.get(ind["id"], donnee["annee"], ville["id"])
                if interp and interp.get("score"):
                    score = interp["score"]
                if score:
                    scores.append(score)
                if interp and interp.get("phrase_courte"):
                    nb_interp_ok += 1
            rows.append({
                **ind,
                "donnee": donnee,
                "score": score,
                "score_couleur": SCORE_COULEURS.get(score),
                "interp_statut": "ok" if (interp and interp.get("phrase_courte")) else (
                    "en_attente" if donnee else "absent"
                ),
            })
        thematic_score = calculer_score_thematique([{"score": s} for s in scores])
        total_donnees += nb_renseignes
        total_donnees_max += len(indicateurs)
        total_interp_ok += nb_interp_ok
        total_interp_needed += nb_renseignes
        stats.append({
            "slug": them,
            "label": ind_model.THEMATIQUE_LABELS[them],
            "icon": ind_model.THEMATIQUE_ICONS.get(them, "📊"),
            "indicateurs": rows,
            "nb_renseignes": nb_renseignes,
            "nb_total": len(indicateurs),
            "nb_interp_ok": nb_interp_ok,
            "thematic_score": thematic_score,
        })
    global_stats = {
        "donnees": total_donnees,
        "donnees_max": total_donnees_max,
        "interp_ok": total_interp_ok,
        "interp_needed": total_interp_needed,
    }
    return render_template(
        "admin/dashboard.html",
        stats=stats,
        ville=ville,
        user_villes=user_villes,
        global_stats=global_stats,
    )


# ── Saisie manuelle ───────────────────────────────────────────────────────

@bp.route("/saisie", methods=["GET", "POST"])
@login_required
def saisie():
    ville = _get_current_ville()
    if not ville:
        flash("Aucune ville sélectionnée.", "warning")
        return redirect(url_for("admin.dashboard"))

    thematiques = ind_model.get_thematiques() + ["portrait"]
    tous_indicateurs = []
    for them in thematiques:
        inds = ind_model.get_by_thematique(them)
        for i in inds:
            tous_indicateurs.append({**i, "them_label": ind_model.THEMATIQUE_LABELS[them]})

    fv = {"annee": str(datetime.now().year), "valeur": "", "source": "", "commentaire": ""}
    if request.method == "GET":
        ind_arg = request.args.get("ind")
        annee_arg = request.args.get("annee")
        if ind_arg and annee_arg:
            try:
                existing = donnee_model.get_by_indicateur_annee(ind_arg, int(annee_arg), ville["id"])
                if existing:
                    fv = {
                        "annee": str(existing["annee"]),
                        "valeur": str(existing["valeur"]),
                        "source": existing.get("source") or "",
                        "commentaire": existing.get("commentaire") or "",
                    }
            except (ValueError, TypeError):
                pass

    if request.method == "POST":
        indicateur_id = request.form.get("indicateur_id", "").strip()
        annee_str = request.form.get("annee", "").strip()
        valeur_str = request.form.get("valeur", "").strip()
        source = request.form.get("source", "").strip()
        commentaire = request.form.get("commentaire", "").strip()

        erreurs = []
        annee = None
        valeur = None
        if not indicateur_id:
            erreurs.append("Veuillez sélectionner un indicateur.")
        if not annee_str:
            erreurs.append("L'année est requise.")
        else:
            try:
                annee = int(annee_str)
            except ValueError:
                erreurs.append("L'année doit être un nombre entier.")
        if not valeur_str:
            erreurs.append("La valeur est requise.")
        else:
            try:
                valeur = float(valeur_str.replace(",", "."))
            except ValueError:
                erreurs.append("La valeur doit être un nombre.")

        if not erreurs:
            ind = ind_model.get_by_id(indicateur_id)
            if not ind:
                erreurs.append("Indicateur introuvable.")

        if erreurs:
            for e in erreurs:
                flash(e, "danger")
        else:
            donnee_model.upsert(indicateur_id, annee, valeur, source, commentaire, "manuel", ville["id"])
            flash(f"Valeur enregistrée pour « {ind['libelle_citoyen']} » ({annee}).", "success")
            return redirect(url_for("admin.saisie", saved_ind=indicateur_id, saved_annee=annee))

    if request.method == "POST":
        fv = {
            "annee": request.form.get("annee", str(datetime.now().year)),
            "valeur": request.form.get("valeur", ""),
            "source": request.form.get("source", ""),
            "commentaire": request.form.get("commentaire", ""),
        }

    recentes = donnee_model.get_recentes(15, ville["id"])
    # Historique pour mini-graphiques (US9)
    historique_raw = donnee_model.get_all_for_ville(ville["id"])
    historique_by_ind = {}
    for d in historique_raw:
        ind_id = d["indicateur_id"]
        if ind_id not in historique_by_ind:
            historique_by_ind[ind_id] = []
        historique_by_ind[ind_id].append({"annee": d["annee"], "valeur": d["valeur"]})
    return render_template(
        "admin/saisie.html",
        indicateurs=tous_indicateurs,
        thematiques=thematiques,
        thematique_labels=ind_model.THEMATIQUE_LABELS,
        recentes=recentes,
        fv=fv,
        ville=ville,
        historique_by_ind=historique_by_ind,
    )


# ── API : vérification donnée existante (US9) ─────────────────────────────

@bp.route("/api/check-donnee")
@login_required
def api_check_donnee():
    ville = _get_current_ville()
    ind_id = request.args.get("ind", "").strip()
    annee_str = request.args.get("annee", "").strip()
    if not ind_id or not annee_str or not ville:
        return jsonify({"exists": False})
    try:
        annee = int(annee_str)
    except ValueError:
        return jsonify({"exists": False})
    donnee = donnee_model.get_by_indicateur_annee(ind_id, annee, ville["id"])
    if donnee:
        ind = ind_model.get_by_id(ind_id)
        return jsonify({
            "exists": True,
            "valeur": donnee["valeur"],
            "unite": ind["unite"] if ind else "",
            "annee": annee,
        })
    return jsonify({"exists": False})


# ── Interprétation manuelle ───────────────────────────────────────────────

@bp.route("/interpretation/<indicateur_id>/<int:annee>", methods=["GET", "POST"])
@login_required
def interpretation(indicateur_id, annee):
    ville = _get_current_ville()
    ind = ind_model.get_by_id(indicateur_id)
    donnee = donnee_model.get_by_indicateur_annee(indicateur_id, annee, ville["id"]) if ville else None
    if not ind or not donnee:
        flash("Indicateur ou donnée introuvable.", "danger")
        return redirect(url_for("admin.dashboard"))

    interp = interp_model.get(indicateur_id, annee, ville["id"])

    if request.method == "POST":
        score = request.form.get("score", "").strip()
        phrase_courte = request.form.get("phrase_courte", "").strip()
        phrase_longue = request.form.get("phrase_longue", "").strip()

        erreurs = []
        if score and score not in ("A", "B", "C", "D", "E"):
            erreurs.append("Le score doit être A, B, C, D ou E.")
        if len(phrase_courte) > LIMITE_PHRASE_COURTE:
            erreurs.append(f"La phrase courte dépasse {LIMITE_PHRASE_COURTE} caractères.")
        if len(phrase_longue) > LIMITE_PHRASE_LONGUE:
            erreurs.append(f"L'interprétation dépasse {LIMITE_PHRASE_LONGUE} caractères.")

        if erreurs:
            for e in erreurs:
                flash(e, "danger")
        else:
            if phrase_courte or phrase_longue or score:
                interp_model.upsert(
                    indicateur_id, annee,
                    score or None,
                    phrase_courte or None,
                    phrase_longue or None,
                    ville["id"]
                )
                flash("Interprétation enregistrée.", "success")
            else:
                interp_model.delete(indicateur_id, annee, ville["id"])
                flash("Interprétation supprimée.", "info")
            return redirect(url_for("admin.dashboard"))

    return render_template(
        "admin/interpretation.html",
        ind=ind,
        annee=annee,
        donnee=donnee,
        interp=interp,
        ville=ville,
        limit_courte=LIMITE_PHRASE_COURTE,
        limit_longue=LIMITE_PHRASE_LONGUE,
    )


# ── Upload CSV ────────────────────────────────────────────────────────────

@bp.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    ville = _get_current_ville()
    apercu = None
    erreurs = []
    format_csv = None

    if request.method == "POST":
        action = request.form.get("action", "apercu")
        format_csv = request.form.get("format", "generique")

        if action == "apercu":
            fichier = request.files.get("fichier")
            if not fichier or fichier.filename == "":
                flash("Aucun fichier sélectionné.", "danger")
                return render_template("admin/upload.html", ville=ville)

            contenu = fichier.read().decode("utf-8", errors="replace")

            # Stocker le contenu côté serveur (pas dans le cookie de session)
            old_tmp = session.pop("upload_tmp", None)
            if old_tmp and os.path.exists(old_tmp):
                os.unlink(old_tmp)
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".csv", delete=False, encoding="utf-8"
            )
            tmp.write(contenu)
            tmp.close()
            session["upload_tmp"] = tmp.name
            session["upload_format"] = format_csv
            session["upload_nom"] = fichier.filename

            if format_csv == "ofgl":
                lignes_valides, erreurs = parser_ofgl(contenu, population=ville.get("population") if ville else None)
            else:
                lignes_valides, erreurs = parser_generique(contenu)

            apercu = lignes_valides

        elif action == "importer":
            tmp_path = session.get("upload_tmp")
            format_csv = session.get("upload_format", "generique")
            nom_fichier = session.get("upload_nom", "inconnu")

            if not tmp_path or not os.path.exists(tmp_path):
                flash("Session expirée. Veuillez re-uploader le fichier.", "danger")
                return redirect(url_for("admin.upload"))

            with open(tmp_path, encoding="utf-8") as f:
                contenu = f.read()
            os.unlink(tmp_path)
            session.pop("upload_tmp", None)

            if format_csv == "ofgl":
                lignes_valides, erreurs = parser_ofgl(contenu, population=ville.get("population") if ville else None)
            else:
                lignes_valides, erreurs = parser_generique(contenu)

            nb_importes = 0
            for ligne in lignes_valides:
                ind = ind_model.get_by_id(ligne["indicateur_id"])
                if ind:
                    donnee_model.upsert(
                        ligne["indicateur_id"], ligne["annee"], ligne["valeur"],
                        ligne.get("source", ""), "", "csv", ville["id"]
                    )
                    nb_importes += 1

            conn = get_db()
            conn.execute("""
                INSERT INTO imports (fichier, format_csv, nb_lignes_traitees, nb_lignes_importees, nb_erreurs, rapport, statut)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                nom_fichier,
                format_csv,
                len(lignes_valides) + len(erreurs),
                nb_importes,
                len(erreurs),
                json.dumps([e for e in erreurs], ensure_ascii=False),
                "succes" if not erreurs else ("partiel" if nb_importes > 0 else "echec"),
            ))
            conn.commit()
            conn.close()

            session.pop("upload_format", None)
            session.pop("upload_nom", None)

            flash(
                f"{nb_importes} valeur(s) importée(s), {len(erreurs)} erreur(s).",
                "success" if nb_importes > 0 else "warning"
            )
            return redirect(url_for("admin.upload"))

    # Historique des imports (US10)
    conn = get_db()
    imports_hist = conn.execute(
        "SELECT * FROM imports ORDER BY date_import DESC LIMIT 30"
    ).fetchall()
    conn.close()
    return render_template(
        "admin/upload.html",
        apercu=apercu,
        erreurs=erreurs,
        format_csv=format_csv or "generique",
        ville=ville,
        imports_hist=[dict(r) for r in imports_hist],
        current_year=datetime.now().year - 1,
    )


# ── Fetch automatique : ma-cantine ────────────────────────────────────────

@bp.route("/fetch/macantine", methods=["POST"])
@login_required
def fetch_macantine():
    ville = _get_current_ville()
    if not ville:
        flash("Aucune commune sélectionnée.", "danger")
        return redirect(url_for("admin.upload"))

    code_insee = ville.get("code_insee")
    if not code_insee:
        flash("Cette commune n'a pas de code INSEE renseigné.", "danger")
        return redirect(url_for("admin.upload"))

    annee = request.form.get("annee", type=int)
    if not annee:
        flash("Année invalide.", "danger")
        return redirect(url_for("admin.upload"))

    result = fetch_cantine_data(code_insee, annee)
    if not result["ok"]:
        flash(f"ma-cantine : {result['error']}", "danger")
        return redirect(url_for("admin.upload"))

    commentaire = (
        f"{result['canteen_count']} cantine(s), "
        f"{result['teledeclarations_count']} télédéclaration(s)"
    )
    nb = 0
    for ind_id, valeur in result["indicateurs"].items():
        donnee_model.upsert(ind_id, annee, valeur, result["source"], commentaire, "api", ville["id"])
        nb += 1

    flash(
        f"ma-cantine {annee} : {nb} indicateur(s) importé(s) pour {ville['nom']} "
        f"({result['teledeclarations_count']} télédéclaration(s) sur {result['canteen_count']} cantine(s)).",
        "success"
    )
    return redirect(url_for("admin.upload"))


# ── Modèles CSV téléchargeables (US10) ────────────────────────────────────

@bp.route("/upload/modele/<format_csv>")
@login_required
def modele_csv(format_csv):
    if format_csv == "ofgl":
        contenu = (
            "code_commune;libelle_commune;annee;libelle_compte;montant\n"
            "# Exemple : remplacez les valeurs ci-dessous par vos données\n"
            "44202;Sautron;2023;Épargne brute;1250000\n"
            "44202;Sautron;2023;Encours de dette;8400000\n"
            "44202;Sautron;2023;Dépenses de fonctionnement;12500000\n"
        )
        filename = "modele_ofgl.csv"
    else:
        contenu = (
            "annee,indicateur_id,valeur,source\n"
            "# Exemple : remplacez les valeurs ci-dessous par vos données\n"
            "2024,fin_epargne_brute_par_hab,142.5,\"Rapport financier commune 2024\"\n"
            "2024,eco_part_bio_cantine,42,\"Rapport DRAAF Pays de la Loire 2024\"\n"
            "2024,soc_logements_sociaux_taux,18.3,\"Bilan SRU préfecture 2024\"\n"
        )
        filename = "modele_generique.csv"
    return Response(
        contenu,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Références (banque) ───────────────────────────────────────────────────

@bp.route("/references", methods=["GET", "POST"])
@login_required
def references():
    ville = _get_current_ville()
    if not ville:
        flash("Aucune ville sélectionnée.", "warning")
        return redirect(url_for("admin.dashboard"))

    thematiques = ind_model.get_thematiques() + ["portrait"]
    tous_indicateurs = []
    for them in thematiques:
        for i in ind_model.get_by_thematique(them):
            ref = banque_ref_model.get_ref_for_indicateur_ville(i["id"], ville["id"])
            # Entrées banque validées disponibles pour cet indicateur
            entrees_valides = refs_banque_model.get_valides_for_indicateur(i["id"])
            tous_indicateurs.append({
                **i,
                "them_label": ind_model.THEMATIQUE_LABELS.get(them, them),
                "ref_ville": ref,
                "entrees_valides": entrees_valides,
            })

    if request.method == "POST":
        action = request.form.get("action", "set")
        indicateur_id = request.form.get("indicateur_id", "").strip()

        if action == "clear":
            banque_ref_model.clear_ref_for_indicateur_ville(indicateur_id, ville["id"])
            flash("Référence supprimée.", "info")
            return redirect(url_for("admin.references"))

        mode = request.form.get("mode", "banque")  # 'banque' ou 'locale'

        if not indicateur_id:
            flash("Indicateur requis.", "danger")
            return redirect(url_for("admin.references"))

        ind = ind_model.get_by_id(indicateur_id)
        if not ind:
            flash("Indicateur introuvable.", "danger")
            return redirect(url_for("admin.references"))

        if mode == "banque":
            ref_banque_id_str = request.form.get("ref_banque_id", "").strip()
            if not ref_banque_id_str:
                flash("Sélectionnez une entrée de la banque.", "danger")
                return redirect(url_for("admin.references"))
            banque_ref_model.set_ref_banque(indicateur_id, ville["id"], int(ref_banque_id_str))
            flash(f"Référence banque assignée pour « {ind['libelle_citoyen']} ».", "success")
        else:
            valeur_str = request.form.get("valeur_locale", "").strip()
            justification = request.form.get("justification", "").strip()
            if not valeur_str:
                flash("Valeur locale requise.", "danger")
                return redirect(url_for("admin.references"))
            try:
                valeur = float(valeur_str.replace(",", "."))
            except ValueError:
                flash("Valeur invalide.", "danger")
                return redirect(url_for("admin.references"))
            banque_ref_model.set_ref_locale(indicateur_id, ville["id"], valeur, justification)
            flash(f"Valeur locale enregistrée pour « {ind['libelle_citoyen']} ».", "success")

        return redirect(url_for("admin.references"))

    return render_template(
        "admin/references.html",
        indicateurs=tous_indicateurs,
        thematiques=thematiques,
        thematique_labels=ind_model.THEMATIQUE_LABELS,
        ville=ville,
    )


# ── Suppression donnée ────────────────────────────────────────────────────

@bp.route("/supprimer/<indicateur_id>/<int:annee>", methods=["POST"])
@login_required
def supprimer(indicateur_id, annee):
    ville = _get_current_ville()
    ind = ind_model.get_by_id(indicateur_id)
    if not ind:
        flash("Indicateur introuvable.", "danger")
        return redirect(url_for("admin.dashboard"))
    donnee_model.delete(indicateur_id, annee, ville["id"])
    flash(f"Donnée {annee} supprimée pour « {ind['libelle_citoyen']} ».", "success")
    return redirect(url_for("admin.dashboard"))


# ── Pyramide des âges ────────────────────────────────────────────────────

@bp.route("/pyramide", methods=["GET", "POST"])
@login_required
def pyramide():
    ville = _get_current_ville()
    if not ville:
        flash("Aucune ville sélectionnée.", "warning")
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        annee = request.form.get("annee", "").strip()
        if not annee or not annee.isdigit():
            flash("Année invalide.", "danger")
            return redirect(url_for("admin.pyramide"))
        annee = int(annee)
        data = []
        for tranche, ordre in pyramide_model.TRANCHES:
            try:
                h = int(request.form.get(f"hommes_{tranche}", 0) or 0)
                f = int(request.form.get(f"femmes_{tranche}", 0) or 0)
            except ValueError:
                h, f = 0, 0
            data.append({"tranche": tranche, "ordre": ordre, "hommes": h, "femmes": f})
        pyramide_model.upsert_year(annee, data, ville["id"])
        flash(f"Pyramide {annee} enregistrée.", "success")
        return redirect(url_for("admin.pyramide"))

    years = pyramide_model.get_years(ville["id"])
    annee_sel = request.args.get("annee", years[0] if years else None)
    rows = pyramide_model.get_by_year(annee_sel, ville["id"]) if annee_sel else []
    rows_by_tranche = {r["tranche"]: r for r in rows}
    return render_template(
        "admin/pyramide.html",
        tranches=pyramide_model.TRANCHES,
        years=years,
        annee_sel=annee_sel,
        rows_by_tranche=rows_by_tranche,
        ville=ville,
    )


@bp.route("/pyramide/supprimer/<int:annee>", methods=["POST"])
@login_required
def supprimer_pyramide(annee):
    ville = _get_current_ville()
    pyramide_model.delete_year(annee, ville["id"])
    flash(f"Pyramide {annee} supprimée.", "success")
    return redirect(url_for("admin.pyramide"))


# ── Subventions ───────────────────────────────────────────────────────────

@bp.route("/subventions", methods=["GET", "POST"])
@login_required
def subventions():
    ville = _get_current_ville()
    if not ville:
        flash("Aucune ville sélectionnée.", "warning")
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        action = request.form.get("action")

        if action == "ajouter":
            annee = request.form.get("annee", "").strip()
            nom = request.form.get("nom_beneficiaire", "").strip()
            domaine = request.form.get("domaine", "autre")
            thematique = request.form.get("thematique", "lien_social")
            montant_raw = request.form.get("montant", "").replace(",", ".").strip()
            commentaire = request.form.get("commentaire", "").strip()
            if not annee or not annee.isdigit() or not nom or not montant_raw:
                flash("Tous les champs obligatoires doivent être remplis.", "danger")
                return redirect(url_for("admin.subventions"))
            try:
                montant = float(montant_raw)
            except ValueError:
                flash("Montant invalide.", "danger")
                return redirect(url_for("admin.subventions"))
            subvention_model.insert(int(annee), nom, domaine, montant, commentaire, ville["id"], thematique)
            flash(f"Subvention ajoutée pour « {nom} ».", "success")

        elif action == "importer_csv":
            fichier = request.files.get("fichier_csv")
            if not fichier:
                flash("Aucun fichier sélectionné.", "danger")
                return redirect(url_for("admin.subventions"))
            contenu = fichier.read().decode("utf-8", errors="replace")
            lignes = contenu.splitlines()
            nb_ok, nb_err = 0, 0
            for i, ligne in enumerate(lignes[1:], start=2):
                cols = [c.strip().strip('"') for c in ligne.split(",")]
                if len(cols) < 4:
                    nb_err += 1
                    continue
                try:
                    annee_csv = int(cols[0])
                    nom_csv = cols[1]
                    domaine_csv = cols[2] if cols[2] in subvention_model.DOMAINES else "autre"
                    montant_csv = float(cols[3].replace(",", "."))
                    commentaire_csv = cols[4] if len(cols) > 4 else ""
                    thematique_csv = cols[5].strip() if len(cols) > 5 else "lien_social"
                    subvention_model.insert(annee_csv, nom_csv, domaine_csv, montant_csv, commentaire_csv, ville["id"], thematique_csv)
                    nb_ok += 1
                except (ValueError, IndexError):
                    nb_err += 1
            flash(f"Import CSV : {nb_ok} lignes importées, {nb_err} ignorées.", "success" if nb_err == 0 else "warning")

        return redirect(url_for("admin.subventions"))

    years = subvention_model.get_years(ville["id"])
    annee_sel = request.args.get("annee", years[0] if years else None)
    lignes = subvention_model.get_by_year(annee_sel, ville["id"]) if annee_sel else []
    total = subvention_model.get_total(annee_sel, ville["id"]) if annee_sel else 0
    return render_template(
        "admin/subventions.html",
        years=years,
        annee_sel=annee_sel,
        lignes=lignes,
        total=total,
        domaines=subvention_model.DOMAINES,
        thematiques=ind_model.THEMATIQUE_LABELS,
        annee_courante=datetime.now().year,
        ville=ville,
    )


@bp.route("/subventions/modifier/<int:id_>", methods=["GET", "POST"])
@login_required
def modifier_subvention(id_):
    ville = _get_current_ville()
    if not ville:
        flash("Aucune ville sélectionnée.", "warning")
        return redirect(url_for("admin.subventions"))
    sub = subvention_model.get_by_id(id_)
    if not sub or sub["ville_id"] != ville["id"]:
        flash("Subvention introuvable.", "danger")
        return redirect(url_for("admin.subventions"))

    if request.method == "POST":
        annee = request.form.get("annee", "").strip()
        nom = request.form.get("nom_beneficiaire", "").strip()
        domaine = request.form.get("domaine", "autre")
        thematique = request.form.get("thematique", "lien_social")
        montant_raw = request.form.get("montant", "").replace(",", ".").strip()
        commentaire = request.form.get("commentaire", "").strip()
        if not annee or not annee.isdigit() or not nom or not montant_raw:
            flash("Tous les champs obligatoires doivent être remplis.", "danger")
            return redirect(url_for("admin.modifier_subvention", id_=id_))
        try:
            montant = float(montant_raw)
        except ValueError:
            flash("Montant invalide.", "danger")
            return redirect(url_for("admin.modifier_subvention", id_=id_))
        subvention_model.update(id_, int(annee), nom, domaine, montant, commentaire, thematique)
        flash(f"Subvention modifiée pour « {nom} ».", "success")
        return redirect(url_for("admin.subventions") + f"?annee={annee}")

    return render_template(
        "admin/subvention_modifier.html",
        sub=sub,
        domaines=subvention_model.DOMAINES,
        thematiques=ind_model.THEMATIQUE_LABELS,
        ville=ville,
    )


@bp.route("/subventions/supprimer/<int:id_>", methods=["POST"])
@login_required
def supprimer_subvention(id_):
    ville = _get_current_ville()
    if not ville:
        flash("Aucune ville sélectionnée.", "warning")
        return redirect(url_for("admin.subventions"))
    # Vérifier que la subvention appartient à la ville courante (IDOR)
    conn = get_db()
    row = conn.execute("SELECT ville_id FROM subventions WHERE id = %s", (id_,)).fetchone()
    conn.close()
    if not row or row["ville_id"] != ville["id"]:
        flash("Subvention introuvable.", "danger")
        return redirect(url_for("admin.subventions"))
    subvention_model.delete(id_)
    flash("Subvention supprimée.", "success")
    annee = request.form.get("annee", "")
    return redirect(url_for("admin.subventions") + (f"?annee={annee}" if annee else ""))


# ── Gestion des villes (super_admin) ──────────────────────────────────────

@bp.route("/villes")
@super_admin_required
def villes():
    villes_list = ville_model.get_all(actif_only=False)
    return render_template("admin/villes.html", villes=villes_list)


@bp.route("/villes/nouvelle", methods=["GET", "POST"])
@super_admin_required
def nouvelle_ville():
    if request.method == "POST":
        nom = request.form.get("nom", "").strip()
        slug = request.form.get("slug", "").strip().lower().replace(" ", "-")
        population_str = request.form.get("population", "").strip()
        population = int(population_str) if population_str.isdigit() else None

        if not nom or not slug:
            flash("Le nom et le slug sont requis.", "danger")
        else:
            try:
                ville_model.create(nom, slug, population)
                flash(f"Ville « {nom} » créée.", "success")
                return redirect(url_for("admin.villes"))
            except Exception:
                flash("Le slug existe déjà. Choisissez un autre.", "danger")

    return render_template("admin/nouvelle_ville.html")


@bp.route("/villes/modifier/<int:ville_id>", methods=["GET", "POST"])
@super_admin_required
def modifier_ville(ville_id):
    ville = ville_model.get_by_id(ville_id)
    if not ville:
        abort(404)

    if request.method == "POST":
        nom = request.form.get("nom", "").strip()
        slug = request.form.get("slug", "").strip().lower()
        population_str = request.form.get("population", "").strip()
        population = int(population_str) if population_str.isdigit() else None
        actif = 1 if request.form.get("actif") else 0

        if not nom or not slug:
            flash("Le nom et le slug sont requis.", "danger")
        else:
            ville_model.update(ville_id, nom, slug, population, actif)
            flash(f"Ville « {nom} » mise à jour.", "success")
            return redirect(url_for("admin.villes"))

    return render_template("admin/modifier_ville.html", ville=ville)


# ── Gestion des utilisateurs (super_admin) ────────────────────────────────

@bp.route("/users")
@super_admin_required
def users():
    users_list = user_model.get_all()
    users_enrichis = []
    for u in users_list:
        villes = user_model.get_villes(u["id"])
        users_enrichis.append({**u, "villes": villes})
    return render_template("admin/users.html", users=users_enrichis)


@bp.route("/users/nouveau", methods=["GET", "POST"])
@super_admin_required
def nouveau_user():
    villes_list = ville_model.get_all()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "gestionnaire")
        ville_ids = [int(v) for v in request.form.getlist("ville_ids") if v.isdigit()]

        if not username or not password:
            flash("Le nom d'utilisateur et le mot de passe sont requis.", "danger")
        elif role not in ("super_admin", "gestionnaire"):
            flash("Rôle invalide.", "danger")
        else:
            try:
                user_id = user_model.create(username, password, role)
                if role == "gestionnaire" and ville_ids:
                    user_model.set_villes(user_id, ville_ids)
                flash(f"Utilisateur « {username} » créé.", "success")
                return redirect(url_for("admin.users"))
            except Exception:
                flash("Ce nom d'utilisateur existe déjà.", "danger")

    return render_template("admin/nouveau_user.html", villes=villes_list)


@bp.route("/users/modifier/<int:user_id>", methods=["GET", "POST"])
@super_admin_required
def modifier_user(user_id):
    user = user_model.get_by_id(user_id)
    if not user:
        abort(404)
    villes_list = ville_model.get_all()
    user_villes = user_model.get_villes(user_id)
    user_ville_ids = [v["id"] for v in user_villes]

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        role = request.form.get("role", "gestionnaire")
        actif = 1 if request.form.get("actif") else 0
        password = request.form.get("password", "").strip()
        ville_ids = [int(v) for v in request.form.getlist("ville_ids") if v.isdigit()]

        # Ne pas désactiver le dernier super-admin
        if role != "super_admin" and user["role"] == "super_admin":
            if user_model.count_super_admins() <= 1:
                flash("Impossible : il doit rester au moins un super-administrateur actif.", "danger")
                return redirect(url_for("admin.modifier_user", user_id=user_id))

        user_model.update(user_id, username, role, actif, password or None)
        if role == "gestionnaire":
            user_model.set_villes(user_id, ville_ids)
        flash(f"Utilisateur « {username} » mis à jour.", "success")
        return redirect(url_for("admin.users"))

    return render_template(
        "admin/modifier_user.html",
        user=user,
        villes=villes_list,
        user_ville_ids=user_ville_ids,
    )


@bp.route("/users/supprimer/<int:user_id>", methods=["POST"])
@super_admin_required
def supprimer_user(user_id):
    user = user_model.get_by_id(user_id)
    if not user:
        flash("Utilisateur introuvable.", "danger")
        return redirect(url_for("admin.users"))
    if user["role"] == "super_admin" and user_model.count_super_admins() <= 1:
        flash("Impossible de supprimer le dernier super-administrateur.", "danger")
        return redirect(url_for("admin.users"))
    # Empêcher l'auto-suppression
    if user_id == session.get("user_id"):
        flash("Vous ne pouvez pas supprimer votre propre compte.", "danger")
        return redirect(url_for("admin.users"))
    user_model.delete(user_id)
    flash(f"Utilisateur « {user['username']} » supprimé.", "success")
    return redirect(url_for("admin.users"))


# ── Banque de références : strates (super_admin) ──────────────────────────

@bp.route("/banque-references")
@super_admin_required
def banque_references():
    strates = banque_ref_model.get_all()
    nb_pending = refs_banque_model.count_pending()
    return render_template("admin/banque_references.html",
                           strates=strates, nb_pending=nb_pending)


@bp.route("/banque-references/nouvelle-strate", methods=["POST"])
@super_admin_required
def nouvelle_strate():
    nom = request.form.get("nom", "").strip()
    description = request.form.get("description", "").strip()
    if not nom:
        flash("Le nom est requis.", "danger")
    else:
        banque_ref_model.create(nom, description)
        flash(f"Strate « {nom} » créée.", "success")
    return redirect(url_for("admin.banque_references"))


@bp.route("/banque-references/modifier-strate/<int:strate_id>", methods=["POST"])
@super_admin_required
def modifier_strate(strate_id):
    nom = request.form.get("nom", "").strip()
    description = request.form.get("description", "").strip()
    if not nom:
        flash("Le nom est requis.", "danger")
    else:
        banque_ref_model.update(strate_id, nom, description)
        flash("Strate mise à jour.", "success")
    return redirect(url_for("admin.banque_references"))


@bp.route("/banque-references/supprimer-strate/<int:strate_id>", methods=["POST"])
@super_admin_required
def supprimer_strate(strate_id):
    strate = banque_ref_model.get_by_id(strate_id)
    if not strate:
        flash("Strate introuvable.", "danger")
        return redirect(url_for("admin.banque_references"))
    nb = banque_ref_model.count_refs_for_strate(strate_id)
    if nb > 0:
        flash(f"Impossible : {nb} entrée(s) de banque rattachée(s) à cette strate.", "danger")
    else:
        banque_ref_model.delete(strate_id)
        flash(f"Strate « {strate['nom']} » supprimée.", "success")
    return redirect(url_for("admin.banque_references"))


# ── Banque de références : entrées validées (super_admin) ─────────────────

@bp.route("/banque-references/entrees", methods=["GET", "POST"])
@super_admin_required
def banque_entrees():
    strates = banque_ref_model.get_all()
    thematiques = ind_model.get_thematiques() + ["portrait"]
    tous_indicateurs = []
    for them in thematiques:
        for i in ind_model.get_by_thematique(them):
            tous_indicateurs.append({**i, "them_label": ind_model.THEMATIQUE_LABELS.get(them, them)})

    filtre_them = request.args.get("them", "")
    filtre_strate = request.args.get("strate", "")
    entrees = refs_banque_model.get_all(
        statut="valide",
        strate_id=int(filtre_strate) if filtre_strate else None,
    )
    if filtre_them:
        entrees = [e for e in entrees if e["thematique"] == filtre_them]

    if request.method == "POST":
        action = request.form.get("action", "add")

        if action == "delete":
            ref_id = int(request.form.get("ref_id", 0))
            refs_banque_model.delete(ref_id)
            flash("Entrée supprimée.", "info")
            return redirect(url_for("admin.banque_entrees"))

        indicateur_id = request.form.get("indicateur_id", "").strip()
        strate_id_str = request.form.get("strate_id", "").strip()
        valeur_str = request.form.get("valeur", "").strip()
        source = request.form.get("source", "").strip()
        annee_str = request.form.get("annee", "").strip()

        erreurs = []
        if not indicateur_id:
            erreurs.append("Indicateur requis.")
        if not strate_id_str:
            erreurs.append("Strate requise.")
        if not source:
            erreurs.append("Source requise.")
        valeur = None
        if not valeur_str:
            erreurs.append("Valeur requise.")
        else:
            try:
                valeur = float(valeur_str.replace(",", "."))
            except ValueError:
                erreurs.append("Valeur invalide.")
        annee = int(annee_str) if annee_str.isdigit() else None

        if erreurs:
            for e in erreurs:
                flash(e, "danger")
        else:
            user_id = session.get("user_id")
            try:
                refs_banque_model.create(
                    indicateur_id, int(strate_id_str), valeur, source, annee,
                    statut="valide", propose_par=user_id, valide_par=user_id
                )
                flash("Entrée ajoutée à la banque.", "success")
            except Exception:
                flash("Cette combinaison indicateur × strate existe déjà.", "danger")
        return redirect(url_for("admin.banque_entrees"))

    return render_template(
        "admin/banque_entrees.html",
        entrees=entrees,
        strates=strates,
        indicateurs=tous_indicateurs,
        thematiques=thematiques,
        thematique_labels=ind_model.THEMATIQUE_LABELS,
        filtre_them=filtre_them,
        filtre_strate=filtre_strate,
    )


# ── Banque de références : propositions (super_admin) ─────────────────────

@bp.route("/banque-references/propositions")
@super_admin_required
def banque_propositions():
    propositions = refs_banque_model.get_all(statut="en_attente")
    return render_template("admin/banque_propositions.html", propositions=propositions)


@bp.route("/banque-references/propositions/<int:ref_id>/valider", methods=["POST"])
@super_admin_required
def valider_proposition(ref_id):
    valeur_str = request.form.get("valeur", "").strip()
    source = request.form.get("source", "").strip()
    annee_str = request.form.get("annee", "").strip()
    user_id = session.get("user_id")
    ref = refs_banque_model.get_by_id(ref_id)
    if not ref:
        flash("Proposition introuvable.", "danger")
        return redirect(url_for("admin.banque_propositions"))
    # Le super-admin peut corriger valeur/source avant validation
    if valeur_str:
        try:
            refs_banque_model.update_valeur(
                ref_id,
                float(valeur_str.replace(",", ".")),
                source or ref["source"],
                int(annee_str) if annee_str.isdigit() else ref.get("annee"),
            )
        except ValueError:
            flash("Valeur invalide.", "danger")
            return redirect(url_for("admin.banque_propositions"))
    refs_banque_model.update_statut(ref_id, "valide", valide_par=user_id)
    flash("Proposition validée et ajoutée à la banque.", "success")
    return redirect(url_for("admin.banque_propositions"))


@bp.route("/banque-references/propositions/<int:ref_id>/rejeter", methods=["POST"])
@super_admin_required
def rejeter_proposition(ref_id):
    commentaire = request.form.get("commentaire", "").strip()
    user_id = session.get("user_id")
    refs_banque_model.update_statut(ref_id, "rejete",
                                    valide_par=user_id,
                                    commentaire_rejet=commentaire or None)
    flash("Proposition rejetée.", "info")
    return redirect(url_for("admin.banque_propositions"))


# ── Banque de références : proposition gestionnaire ───────────────────────

@bp.route("/proposer-reference", methods=["GET", "POST"])
@login_required
def proposer_reference():
    strates = banque_ref_model.get_all()
    thematiques = ind_model.get_thematiques() + ["portrait"]
    tous_indicateurs = []
    for them in thematiques:
        for i in ind_model.get_by_thematique(them):
            tous_indicateurs.append({**i, "them_label": ind_model.THEMATIQUE_LABELS.get(them, them)})

    if request.method == "POST":
        indicateur_id = request.form.get("indicateur_id", "").strip()
        strate_id_str = request.form.get("strate_id", "").strip()
        valeur_str = request.form.get("valeur", "").strip()
        source = request.form.get("source", "").strip()
        annee_str = request.form.get("annee", "").strip()

        erreurs = []
        if not indicateur_id:
            erreurs.append("Indicateur requis.")
        if not strate_id_str:
            erreurs.append("Strate requise.")
        if not source:
            erreurs.append("Source requise (URL ou référence documentaire).")
        valeur = None
        if not valeur_str:
            erreurs.append("Valeur requise.")
        else:
            try:
                valeur = float(valeur_str.replace(",", "."))
            except ValueError:
                erreurs.append("Valeur invalide.")
        annee = int(annee_str) if annee_str.isdigit() else None

        if erreurs:
            for e in erreurs:
                flash(e, "danger")
        else:
            user_id = session.get("user_id")
            try:
                refs_banque_model.create(
                    indicateur_id, int(strate_id_str), valeur, source, annee,
                    statut="en_attente", propose_par=user_id
                )
                flash("Proposition soumise, en attente de validation.", "success")
                return redirect(url_for("admin.mes_propositions"))
            except Exception:
                flash("Une proposition existe déjà pour cette combinaison indicateur × strate.", "danger")

    return render_template(
        "admin/proposer_reference.html",
        strates=strates,
        indicateurs=tous_indicateurs,
        thematiques=thematiques,
        thematique_labels=ind_model.THEMATIQUE_LABELS,
    )


@bp.route("/mes-propositions")
@login_required
def mes_propositions():
    user_id = session.get("user_id")
    propositions = refs_banque_model.get_by_user(user_id)
    return render_template("admin/mes_propositions.html", propositions=propositions)


# ── Références ville (assignation) ────────────────────────────────────────


# ── Communes en vedette (super_admin) ─────────────────────────────────────


@bp.route("/communes-vedette", methods=["GET", "POST"])
@super_admin_required
def communes_vedette():
    if request.method == "POST":
        codes = [
            request.form.get("code_1", "").strip(),
            request.form.get("code_2", "").strip(),
            request.form.get("code_3", "").strip(),
        ]
        commune_model.set_vedettes([c for c in codes if c])
        flash("Communes en vedette mises à jour.", "success")
        return redirect(url_for("admin.communes_vedette"))

    vedettes = commune_model.get_all_vedettes()
    # Pré-remplir les 3 emplacements
    slots = [None, None, None]
    for i, v in enumerate(vedettes[:3]):
        slots[i] = v
    return render_template("admin/communes_vedette.html", slots=slots)


# ── Conseils municipaux ───────────────────────────────────────────────────

import app.models.conseil as conseil_model
import werkzeug.utils


CONSEILS_UPLOAD_DIR = "/app/uploads/conseils"


def _save_pdf(fichier):
    """Sauvegarde le PDF uploadé et retourne son nom de fichier."""
    os.makedirs(CONSEILS_UPLOAD_DIR, exist_ok=True)
    filename = werkzeug.utils.secure_filename(fichier.filename)
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    filename = f"{ts}_{filename}"
    fichier.save(os.path.join(CONSEILS_UPLOAD_DIR, filename))
    return filename


@bp.route("/conseils")
@login_required
def conseils():
    ville = ville_model.get_by_id(session.get("ville_id"))
    if not ville:
        flash("Aucune ville sélectionnée.", "danger")
        return redirect(url_for("admin.dashboard"))
    items = conseil_model.get_all(ville["id"])
    return render_template("admin/conseils.html", ville=ville, conseils=items)


@bp.route("/conseils/nouveau", methods=["GET", "POST"])
@login_required
def conseil_nouveau():
    ville = ville_model.get_by_id(session.get("ville_id"))
    if not ville:
        abort(403)
    if request.method == "POST":
        titre = request.form.get("titre", "").strip()
        date_conseil = request.form.get("date_conseil", "").strip()
        fichier = request.files.get("fichier_pdf")
        if not titre or not date_conseil:
            flash("Titre et date sont obligatoires.", "danger")
            return render_template("admin/conseil_form.html", ville=ville, conseil=None)
        fichier_pdf = None
        if fichier and fichier.filename:
            if not fichier.filename.lower().endswith(".pdf"):
                flash("Seuls les fichiers PDF sont acceptés.", "danger")
                return render_template("admin/conseil_form.html", ville=ville, conseil=None)
            fichier_pdf = _save_pdf(fichier)
        conseil_model.create(ville["id"], titre, date_conseil, fichier_pdf)
        flash("Conseil ajouté avec succès.", "success")
        return redirect(url_for("admin.conseils"))
    return render_template("admin/conseil_form.html", ville=ville, conseil=None)


@bp.route("/conseils/<int:conseil_id>/modifier", methods=["GET", "POST"])
@login_required
def conseil_modifier(conseil_id):
    ville = ville_model.get_by_id(session.get("ville_id"))
    conseil = conseil_model.get_by_id(conseil_id)
    if not conseil or conseil["ville_id"] != ville["id"]:
        abort(404)
    if request.method == "POST":
        titre = request.form.get("titre", "").strip()
        date_conseil = request.form.get("date_conseil", "").strip()
        fichier = request.files.get("fichier_pdf")
        if not titre or not date_conseil:
            flash("Titre et date sont obligatoires.", "danger")
            return render_template("admin/conseil_form.html", ville=ville, conseil=conseil)
        fichier_pdf = None
        if fichier and fichier.filename:
            if not fichier.filename.lower().endswith(".pdf"):
                flash("Seuls les fichiers PDF sont acceptés.", "danger")
                return render_template("admin/conseil_form.html", ville=ville, conseil=conseil)
            fichier_pdf = _save_pdf(fichier)
        conseil_model.update(conseil_id, titre, date_conseil, fichier_pdf)
        flash("Conseil mis à jour.", "success")
        return redirect(url_for("admin.conseils"))
    return render_template("admin/conseil_form.html", ville=ville, conseil=conseil)


@bp.route("/conseils/<int:conseil_id>/publier", methods=["POST"])
@login_required
def conseil_publier(conseil_id):
    ville = ville_model.get_by_id(session.get("ville_id"))
    conseil = conseil_model.get_by_id(conseil_id)
    if not conseil or conseil["ville_id"] != ville["id"]:
        abort(404)
    conseil_model.set_publie(conseil_id, not conseil["publie"])
    return redirect(url_for("admin.conseils"))


@bp.route("/conseils/<int:conseil_id>/supprimer", methods=["POST"])
@login_required
def conseil_supprimer(conseil_id):
    ville = ville_model.get_by_id(session.get("ville_id"))
    conseil = conseil_model.get_by_id(conseil_id)
    if not conseil or conseil["ville_id"] != ville["id"]:
        abort(404)
    fichier_pdf = conseil_model.delete(conseil_id)
    if fichier_pdf:
        path = os.path.join(CONSEILS_UPLOAD_DIR, fichier_pdf)
        if os.path.exists(path):
            os.remove(path)
    flash("Conseil supprimé.", "success")
    return redirect(url_for("admin.conseils"))
