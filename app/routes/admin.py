import json
import os
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.auth import check_password, login_required
from app.config import UPLOAD_FOLDER
import app.models.indicateur as ind_model
import app.models.donnee as donnee_model
import app.models.interpretation as interp_model
from app.database import get_db
from app.services.scoring import calculer_score, SCORE_COULEURS
from app.services.parser_csv import parser_generique
from app.services.parser_ofgl import parser_ofgl
from app.services.claude import generer_interpretation

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if check_password(password):
            session["admin_logged_in"] = True
            flash("Connexion réussie.", "success")
            return redirect(url_for("admin.dashboard"))
        else:
            flash("Mot de passe incorrect.", "danger")
    return render_template("admin/login.html")


@bp.route("/logout")
def logout():
    session.clear()
    flash("Déconnexion réussie.", "info")
    return redirect(url_for("admin.login"))


@bp.route("/")
@login_required
def dashboard():
    thematiques = ind_model.get_thematiques() + ["portrait"]
    stats = []
    for them in thematiques:
        indicateurs = ind_model.get_by_thematique(them)
        nb_renseignes = 0
        rows = []
        for ind in indicateurs:
            donnee = donnee_model.get_latest(ind["id"])
            interp = None
            score = None
            if donnee:
                nb_renseignes += 1
                score = calculer_score(
                    donnee["valeur"], ind.get("seuil_vert"),
                    ind.get("seuil_orange"), ind.get("seuil_rouge"),
                    ind.get("sens_positif", "neutre")
                )
                interp = interp_model.get(ind["id"], donnee["annee"])
                if interp and interp.get("score"):
                    score = interp["score"]
            rows.append({
                **ind,
                "donnee": donnee,
                "score": score,
                "score_couleur": SCORE_COULEURS.get(score),
                "interp_statut": "ok" if (interp and interp.get("phrase_courte")) else (
                    "en_attente" if donnee else "absent"
                ),
            })
        stats.append({
            "slug": them,
            "label": ind_model.THEMATIQUE_LABELS[them],
            "indicateurs": rows,
            "nb_renseignes": nb_renseignes,
            "nb_total": len(indicateurs),
        })
    return render_template("admin/dashboard.html", stats=stats)


@bp.route("/saisie", methods=["GET", "POST"])
@login_required
def saisie():
    thematiques = ind_model.get_thematiques() + ["portrait"]
    tous_indicateurs = []
    for them in thematiques:
        inds = ind_model.get_by_thematique(them)
        for i in inds:
            tous_indicateurs.append({**i, "them_label": ind_model.THEMATIQUE_LABELS[them]})

    # Pré-remplissage depuis URL (mode modification)
    fv = {"annee": "2024", "valeur": "", "source": "", "commentaire": ""}
    if request.method == "GET":
        ind_arg = request.args.get("ind")
        annee_arg = request.args.get("annee")
        if ind_arg and annee_arg:
            try:
                existing = donnee_model.get_by_indicateur_annee(ind_arg, int(annee_arg))
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
        if not indicateur_id:
            erreurs.append("Veuillez sélectionner un indicateur.")
        if not annee_str:
            erreurs.append("L'année est requise.")
        else:
            try:
                annee = int(annee_str)
            except ValueError:
                erreurs.append("L'année doit être un nombre entier.")
                annee = None
        if not valeur_str:
            erreurs.append("La valeur est requise.")
        else:
            try:
                valeur = float(valeur_str.replace(",", "."))
            except ValueError:
                erreurs.append("La valeur doit être un nombre.")
                valeur = None

        if not erreurs:
            ind = ind_model.get_by_id(indicateur_id)
            if not ind:
                erreurs.append("Indicateur introuvable.")

        if erreurs:
            for e in erreurs:
                flash(e, "danger")
        else:
            donnee_model.upsert(indicateur_id, annee, valeur, source, commentaire, "manuel")
            score = calculer_score(
                valeur, ind.get("seuil_vert"), ind.get("seuil_orange"),
                ind.get("seuil_rouge"), ind.get("sens_positif", "neutre")
            )
            flash(f"Valeur enregistrée pour « {ind['libelle_citoyen']} » ({annee}).", "success")

            # Génération interprétation Claude en arrière-plan (best effort)
            try:
                generer_interpretation(ind, annee, valeur, score)
                flash("Interprétation générée.", "success")
            except Exception:
                flash("Interprétation non générée (erreur API).", "warning")

            return redirect(url_for("admin.saisie"))

    # Après POST (erreur), écraser fv avec les valeurs soumises
    if request.method == "POST":
        fv = {
            "annee": request.form.get("annee", "2024"),
            "valeur": request.form.get("valeur", ""),
            "source": request.form.get("source", ""),
            "commentaire": request.form.get("commentaire", ""),
        }

    recentes = donnee_model.get_recentes(15)
    return render_template(
        "admin/saisie.html",
        indicateurs=tous_indicateurs,
        thematiques=thematiques,
        thematique_labels=ind_model.THEMATIQUE_LABELS,
        recentes=recentes,
        fv=fv,
    )


@bp.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    apercu = None
    erreurs = []
    format_csv = None
    contenu = None
    nom_fichier = None

    if request.method == "POST":
        action = request.form.get("action", "apercu")
        format_csv = request.form.get("format", "generique")

        if action == "apercu":
            fichier = request.files.get("fichier")
            if not fichier or fichier.filename == "":
                flash("Aucun fichier sélectionné.", "danger")
                return render_template("admin/upload.html")

            contenu = fichier.read().decode("utf-8", errors="replace")
            nom_fichier = fichier.filename
            session["upload_contenu"] = contenu
            session["upload_format"] = format_csv
            session["upload_nom"] = nom_fichier

            if format_csv == "ofgl":
                lignes_valides, erreurs = parser_ofgl(contenu)
            else:
                lignes_valides, erreurs = parser_generique(contenu)

            apercu = lignes_valides

        elif action == "importer":
            contenu = session.get("upload_contenu")
            format_csv = session.get("upload_format", "generique")
            nom_fichier = session.get("upload_nom", "inconnu")

            if not contenu:
                flash("Session expirée. Veuillez re-uploader le fichier.", "danger")
                return redirect(url_for("admin.upload"))

            if format_csv == "ofgl":
                lignes_valides, erreurs = parser_ofgl(contenu)
            else:
                lignes_valides, erreurs = parser_generique(contenu)

            nb_importes = 0
            indicateurs_maj = []
            for ligne in lignes_valides:
                ind = ind_model.get_by_id(ligne["indicateur_id"])
                if ind:
                    donnee_model.upsert(
                        ligne["indicateur_id"], ligne["annee"], ligne["valeur"],
                        ligne.get("source", ""), "", "csv"
                    )
                    nb_importes += 1
                    indicateurs_maj.append((ind, ligne["annee"], ligne["valeur"]))

            # Log import
            conn = get_db()
            conn.execute("""
                INSERT INTO imports (fichier, nb_lignes_traitees, nb_lignes_importees, nb_erreurs, rapport, statut)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                nom_fichier,
                len(lignes_valides) + len(erreurs),
                nb_importes,
                len(erreurs),
                json.dumps([e for e in erreurs], ensure_ascii=False),
                "succes" if not erreurs else ("partiel" if nb_importes > 0 else "echec"),
            ))
            conn.commit()
            conn.close()

            session.pop("upload_contenu", None)
            session.pop("upload_format", None)
            session.pop("upload_nom", None)

            # Génération interprétations
            nb_interp = 0
            for ind, annee, valeur in indicateurs_maj:
                score = calculer_score(
                    valeur, ind.get("seuil_vert"), ind.get("seuil_orange"),
                    ind.get("seuil_rouge"), ind.get("sens_positif", "neutre")
                )
                try:
                    result = generer_interpretation(ind, annee, valeur, score)
                    if result:
                        nb_interp += 1
                except Exception:
                    pass

            flash(
                f"{nb_importes} valeur(s) importée(s), {len(erreurs)} erreur(s), "
                f"{nb_interp} interprétation(s) générée(s).",
                "success" if nb_importes > 0 else "warning"
            )
            return redirect(url_for("admin.dashboard"))

    return render_template(
        "admin/upload.html",
        apercu=apercu,
        erreurs=erreurs,
        format_csv=format_csv or "generique",
    )


@bp.route("/supprimer/<indicateur_id>/<int:annee>", methods=["POST"])
@login_required
def supprimer(indicateur_id, annee):
    ind = ind_model.get_by_id(indicateur_id)
    if not ind:
        flash("Indicateur introuvable.", "danger")
        return redirect(url_for("admin.dashboard"))
    donnee_model.delete(indicateur_id, annee)
    flash(f"Donnée {annee} supprimée pour « {ind['libelle_citoyen']} ».", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/regenerer/<indicateur_id>/<int:annee>", methods=["POST"])
@login_required
def regenerer(indicateur_id, annee):
    ind = ind_model.get_by_id(indicateur_id)
    donnee = donnee_model.get_by_indicateur_annee(indicateur_id, annee)
    if not ind or not donnee:
        flash("Indicateur ou donnée introuvable.", "danger")
        return redirect(url_for("admin.dashboard"))

    score = calculer_score(
        donnee["valeur"], ind.get("seuil_vert"), ind.get("seuil_orange"),
        ind.get("seuil_rouge"), ind.get("sens_positif", "neutre")
    )
    try:
        result = generer_interpretation(ind, annee, donnee["valeur"], score)
        if result:
            flash("Interprétation régénérée.", "success")
        else:
            flash("Erreur lors de la génération.", "warning")
    except Exception as e:
        flash(f"Erreur : {e}", "danger")
    return redirect(url_for("admin.dashboard"))
