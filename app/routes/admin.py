import json
import os
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from app.auth import login_required, super_admin_required, is_rate_limited, record_attempt
from app.config import UPLOAD_FOLDER
import app.models.indicateur as ind_model
import app.models.donnee as donnee_model
import app.models.interpretation as interp_model
import app.models.pyramide as pyramide_model
import app.models.subvention as subvention_model
import app.models.ville as ville_model
import app.models.user as user_model
import app.models.banque_reference as banque_ref_model
from app.database import get_db
from app.services.scoring import calculer_score, SCORE_COULEURS
from app.services.parser_csv import parser_generique
from app.services.parser_ofgl import parser_ofgl

bp = Blueprint("admin", __name__, url_prefix="/admin")

INTERP_LIMIT_COURTE = 200
INTERP_LIMIT_LONGUE = 1000


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


@bp.route("/logout")
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
    for them in thematiques:
        indicateurs = ind_model.get_by_thematique(them)
        nb_renseignes = 0
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
    return render_template(
        "admin/dashboard.html",
        stats=stats,
        ville=ville,
        user_villes=user_villes,
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

    fv = {"annee": "2024", "valeur": "", "source": "", "commentaire": ""}
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
            return redirect(url_for("admin.saisie"))

    if request.method == "POST":
        fv = {
            "annee": request.form.get("annee", "2024"),
            "valeur": request.form.get("valeur", ""),
            "source": request.form.get("source", ""),
            "commentaire": request.form.get("commentaire", ""),
        }

    recentes = donnee_model.get_recentes(15, ville["id"])
    return render_template(
        "admin/saisie.html",
        indicateurs=tous_indicateurs,
        thematiques=thematiques,
        thematique_labels=ind_model.THEMATIQUE_LABELS,
        recentes=recentes,
        fv=fv,
        ville=ville,
    )


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
        if len(phrase_courte) > INTERP_LIMIT_COURTE:
            erreurs.append(f"La phrase courte dépasse {INTERP_LIMIT_COURTE} caractères.")
        if len(phrase_longue) > INTERP_LIMIT_LONGUE:
            erreurs.append(f"L'interprétation dépasse {INTERP_LIMIT_LONGUE} caractères.")

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
        limit_courte=INTERP_LIMIT_COURTE,
        limit_longue=INTERP_LIMIT_LONGUE,
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
            session["upload_contenu"] = contenu
            session["upload_format"] = format_csv
            session["upload_nom"] = fichier.filename

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

            flash(
                f"{nb_importes} valeur(s) importée(s), {len(erreurs)} erreur(s).",
                "success" if nb_importes > 0 else "warning"
            )
            return redirect(url_for("admin.dashboard"))

    return render_template(
        "admin/upload.html",
        apercu=apercu,
        erreurs=erreurs,
        format_csv=format_csv or "generique",
        ville=ville,
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
        inds = ind_model.get_by_thematique(them)
        for i in inds:
            ref = banque_ref_model.get_ref_for_indicateur_ville(i["id"], ville["id"])
            tous_indicateurs.append({**i, "them_label": ind_model.THEMATIQUE_LABELS[them], "ref_ville": ref})

    banque = banque_ref_model.get_all()

    if request.method == "POST":
        action = request.form.get("action", "set")
        indicateur_id = request.form.get("indicateur_id", "").strip()

        if action == "clear":
            banque_ref_model.clear_ref_for_indicateur_ville(indicateur_id, ville["id"])
            flash("Référence supprimée.", "info")
            return redirect(url_for("admin.references"))

        banque_reference_id = request.form.get("banque_reference_id", "").strip()
        valeur_str = request.form.get("valeur", "").strip()

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

        if not erreurs:
            ind = ind_model.get_by_id(indicateur_id)
            if not ind:
                erreurs.append("Indicateur introuvable.")

        if erreurs:
            for e in erreurs:
                flash(e, "danger")
        else:
            banque_ref_model.set_ref_for_indicateur_ville(
                indicateur_id, ville["id"],
                int(banque_reference_id) if banque_reference_id else None,
                valeur
            )
            flash(f"Référence mise à jour pour « {ind['libelle_citoyen']} ».", "success")
            return redirect(url_for("admin.references"))

    return render_template(
        "admin/references.html",
        indicateurs=tous_indicateurs,
        thematiques=thematiques,
        thematique_labels=ind_model.THEMATIQUE_LABELS,
        banque=banque,
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
            subvention_model.insert(int(annee), nom, domaine, montant, commentaire, ville["id"])
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
                    subvention_model.insert(annee_csv, nom_csv, domaine_csv, montant_csv, commentaire_csv, ville["id"])
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
        annee_courante=2024,
        ville=ville,
    )


@bp.route("/subventions/supprimer/<int:id_>", methods=["POST"])
@login_required
def supprimer_subvention(id_):
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
    from flask import abort
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


# ── Banque de références (super_admin) ────────────────────────────────────

@bp.route("/banque-references")
@super_admin_required
def banque_references():
    refs = banque_ref_model.get_all()
    return render_template("admin/banque_references.html", refs=refs)


@bp.route("/banque-references/nouvelle", methods=["POST"])
@super_admin_required
def nouvelle_banque_reference():
    nom = request.form.get("nom", "").strip()
    description = request.form.get("description", "").strip()
    if not nom:
        flash("Le nom est requis.", "danger")
    else:
        banque_ref_model.create(nom, description)
        flash(f"Référence « {nom} » créée.", "success")
    return redirect(url_for("admin.banque_references"))


@bp.route("/banque-references/supprimer/<int:ref_id>", methods=["POST"])
@super_admin_required
def supprimer_banque_reference(ref_id):
    ref = banque_ref_model.get_by_id(ref_id)
    if ref:
        banque_ref_model.delete(ref_id)
        flash(f"Référence « {ref['nom']} » supprimée.", "success")
    return redirect(url_for("admin.banque_references"))
