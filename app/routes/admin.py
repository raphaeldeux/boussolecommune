import json
import os
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from app.auth import check_password, login_required, is_rate_limited, record_attempt
from app.config import UPLOAD_FOLDER
import app.models.indicateur as ind_model
import app.models.donnee as donnee_model
import app.models.interpretation as interp_model
import app.models.pyramide as pyramide_model
import app.models.subvention as subvention_model
from app.database import get_db
from app.services.scoring import calculer_score, SCORE_COULEURS
from app.services.parser_csv import parser_generique
from app.services.parser_ofgl import parser_ofgl
from app.services.claude import generer_interpretation

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ip = request.remote_addr
        if is_rate_limited(ip):
            flash("Trop de tentatives. Réessayez dans 15 minutes.", "danger")
            return render_template("admin/login.html")
        password = request.form.get("password", "")
        if check_password(password):
            session.permanent = True
            session["admin_logged_in"] = True
            flash("Connexion réussie.", "success")
            return redirect(url_for("admin.dashboard"))
        else:
            record_attempt(ip)
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


@bp.route("/references", methods=["GET", "POST"])
@login_required
def references():
    thematiques = ind_model.get_thematiques() + ["portrait"]
    tous_indicateurs = []
    for them in thematiques:
        inds = ind_model.get_by_thematique(them)
        for i in inds:
            tous_indicateurs.append({**i, "them_label": ind_model.THEMATIQUE_LABELS[them]})

    if request.method == "POST":
        indicateur_id = request.form.get("indicateur_id", "").strip()
        valeur_str = request.form.get("valeur_reference", "").strip()
        libelle = request.form.get("libelle_reference", "").strip()
        annee_str = request.form.get("annee_reference", "").strip()

        erreurs = []
        if not indicateur_id:
            erreurs.append("Veuillez sélectionner un indicateur.")
        if not valeur_str:
            erreurs.append("La valeur de référence est requise.")
        else:
            try:
                valeur = float(valeur_str.replace(",", "."))
            except ValueError:
                erreurs.append("La valeur doit être un nombre.")
                valeur = None
        annee = int(annee_str) if annee_str.isdigit() else None

        if not erreurs:
            ind = ind_model.get_by_id(indicateur_id)
            if not ind:
                erreurs.append("Indicateur introuvable.")

        if erreurs:
            for e in erreurs:
                flash(e, "danger")
        else:
            ind_model.update_reference(indicateur_id, valeur, libelle, annee)
            flash(f"Référence mise à jour pour « {ind['libelle_citoyen']} ».", "success")
            return redirect(url_for("admin.references"))

    return render_template(
        "admin/references.html",
        indicateurs=tous_indicateurs,
        thematiques=thematiques,
        thematique_labels=ind_model.THEMATIQUE_LABELS,
    )


@bp.route("/references/supprimer/<indicateur_id>", methods=["POST"])
@login_required
def supprimer_reference(indicateur_id):
    ind = ind_model.get_by_id(indicateur_id)
    ind_model.clear_reference(indicateur_id)
    label = ind["libelle_citoyen"] if ind else indicateur_id
    flash(f"Référence supprimée pour « {label} ».", "success")
    return redirect(url_for("admin.references"))


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
        current_app.logger.info("[claude] Appel generer_interpretation ind=%s annee=%s", indicateur_id, annee)
        result = generer_interpretation(ind, annee, donnee["valeur"], score)
        current_app.logger.info("[claude] Résultat : %s", result)
        if result:
            flash("Interprétation régénérée.", "success")
        else:
            flash("Erreur lors de la génération.", "warning")
    except Exception as e:
        current_app.logger.error("[claude] Exception : %s", e, exc_info=True)
        flash(f"Erreur : {e}", "danger")
    return redirect(url_for("admin.dashboard"))


# ── Pyramide des âges ────────────────────────────────────────────

@bp.route("/pyramide", methods=["GET", "POST"])
@login_required
def pyramide():
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
        pyramide_model.upsert_year(annee, data)
        flash(f"Pyramide {annee} enregistrée.", "success")
        return redirect(url_for("admin.pyramide"))

    years = pyramide_model.get_years()
    annee_sel = request.args.get("annee", years[0] if years else None)
    rows = pyramide_model.get_by_year(annee_sel) if annee_sel else []
    rows_by_tranche = {r["tranche"]: r for r in rows}
    return render_template(
        "admin/pyramide.html",
        tranches=pyramide_model.TRANCHES,
        years=years,
        annee_sel=annee_sel,
        rows_by_tranche=rows_by_tranche,
    )


@bp.route("/pyramide/supprimer/<int:annee>", methods=["POST"])
@login_required
def supprimer_pyramide(annee):
    pyramide_model.delete_year(annee)
    flash(f"Pyramide {annee} supprimée.", "success")
    return redirect(url_for("admin.pyramide"))


# ── Subventions ──────────────────────────────────────────────────

@bp.route("/subventions", methods=["GET", "POST"])
@login_required
def subventions():
    if request.method == "POST":
        action = request.form.get("action")

        if action == "ajouter":
            annee = request.form.get("annee", "").strip()
            nom = request.form.get("nom_beneficiaire", "").strip()
            domaine = request.form.get("domaine", "autre")
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
            subvention_model.insert(int(annee), nom, domaine, montant, commentaire)
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
                    subvention_model.insert(annee_csv, nom_csv, domaine_csv, montant_csv, commentaire_csv)
                    nb_ok += 1
                except (ValueError, IndexError):
                    nb_err += 1
            flash(f"Import CSV : {nb_ok} lignes importées, {nb_err} ignorées.", "success" if nb_err == 0 else "warning")

        return redirect(url_for("admin.subventions"))

    years = subvention_model.get_years()
    annee_sel = request.args.get("annee", years[0] if years else None)
    lignes = subvention_model.get_by_year(annee_sel) if annee_sel else []
    total = subvention_model.get_total(annee_sel) if annee_sel else 0
    return render_template(
        "admin/subventions.html",
        years=years,
        annee_sel=annee_sel,
        lignes=lignes,
        total=total,
        domaines=subvention_model.DOMAINES,
        annee_courante=2024,
    )


@bp.route("/subventions/supprimer/<int:id_>", methods=["POST"])
@login_required
def supprimer_subvention(id_):
    subvention_model.delete(id_)
    flash("Subvention supprimée.", "success")
    annee = request.form.get("annee", "")
    return redirect(url_for("admin.subventions") + (f"?annee={annee}" if annee else ""))
