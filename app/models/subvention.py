from app.database import get_db

DOMAINES = ["sport", "culture", "social", "environnement", "education", "sante", "autre"]


def get_years(ville_id=1, thematique=None):
    with get_db() as conn:
        if thematique:
            rows = conn.execute(
                "SELECT DISTINCT annee FROM subventions WHERE ville_id = %s AND thematique = %s ORDER BY annee DESC",
                (ville_id, thematique),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT DISTINCT annee FROM subventions WHERE ville_id = %s ORDER BY annee DESC",
                (ville_id,),
            ).fetchall()
    return [r["annee"] for r in rows]


def get_previous_year(annee, ville_id=1, thematique=None):
    """Retourne l'année précédente disponible (strictement < annee), ou None."""
    with get_db() as conn:
        if thematique:
            row = conn.execute(
                "SELECT MAX(annee) AS prev FROM subventions WHERE ville_id = %s AND thematique = %s AND annee < %s",
                (ville_id, thematique, annee),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT MAX(annee) AS prev FROM subventions WHERE ville_id = %s AND annee < %s",
                (ville_id, annee),
            ).fetchone()
    return row["prev"] if row and row["prev"] else None


def get_by_year(annee, ville_id=1, thematique=None):
    with get_db() as conn:
        if thematique:
            rows = conn.execute(
                "SELECT id, nom_beneficiaire, domaine, thematique, montant, commentaire "
                "FROM subventions WHERE annee = %s AND ville_id = %s AND thematique = %s ORDER BY montant DESC",
                (annee, ville_id, thematique),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, nom_beneficiaire, domaine, thematique, montant, commentaire "
                "FROM subventions WHERE annee = %s AND ville_id = %s ORDER BY montant DESC",
                (annee, ville_id),
            ).fetchall()
    return [dict(r) for r in rows]


def get_totaux_par_domaine(annee, ville_id=1, thematique=None):
    with get_db() as conn:
        if thematique:
            rows = conn.execute(
                "SELECT domaine, SUM(montant) AS total FROM subventions "
                "WHERE annee = %s AND ville_id = %s AND thematique = %s GROUP BY domaine ORDER BY total DESC",
                (annee, ville_id, thematique),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT domaine, SUM(montant) AS total FROM subventions "
                "WHERE annee = %s AND ville_id = %s GROUP BY domaine ORDER BY total DESC",
                (annee, ville_id),
            ).fetchall()
    return [dict(r) for r in rows]


def get_total(annee, ville_id=1, thematique=None):
    with get_db() as conn:
        if thematique:
            row = conn.execute(
                "SELECT SUM(montant) AS total FROM subventions WHERE annee = %s AND ville_id = %s AND thematique = %s",
                (annee, ville_id, thematique),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT SUM(montant) AS total FROM subventions WHERE annee = %s AND ville_id = %s",
                (annee, ville_id),
            ).fetchone()
    return row["total"] or 0


def get_by_id(id_):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM subventions WHERE id = %s", (id_,)).fetchone()
    return dict(row) if row else None


def insert(annee, nom_beneficiaire, domaine, montant, commentaire="", ville_id=1, thematique="lien_social"):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO subventions (ville_id, annee, nom_beneficiaire, domaine, thematique, montant, commentaire) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (ville_id, annee, nom_beneficiaire, domaine, thematique, montant, commentaire or ""),
        )
        conn.commit()


def update(id_, annee, nom_beneficiaire, domaine, montant, commentaire="", thematique="lien_social"):
    with get_db() as conn:
        conn.execute(
            "UPDATE subventions SET annee=%s, nom_beneficiaire=%s, domaine=%s, thematique=%s, montant=%s, commentaire=%s "
            "WHERE id=%s",
            (annee, nom_beneficiaire, domaine, thematique, montant, commentaire or "", id_),
        )
        conn.commit()


def delete(id_):
    with get_db() as conn:
        conn.execute("DELETE FROM subventions WHERE id = %s", (id_,))
        conn.commit()
