from app.database import get_db

DOMAINES = ["sport", "culture", "social", "environnement", "education", "autre"]


def get_years():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT annee FROM subventions ORDER BY annee DESC"
        ).fetchall()
    return [r["annee"] for r in rows]


def get_by_year(annee):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, nom_beneficiaire, domaine, montant, commentaire "
            "FROM subventions WHERE annee = ? ORDER BY montant DESC",
            (annee,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_totaux_par_domaine(annee):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT domaine, SUM(montant) AS total FROM subventions "
            "WHERE annee = ? GROUP BY domaine ORDER BY total DESC",
            (annee,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_total(annee):
    with get_db() as conn:
        row = conn.execute(
            "SELECT SUM(montant) AS total FROM subventions WHERE annee = ?",
            (annee,),
        ).fetchone()
    return row["total"] or 0


def insert(annee, nom_beneficiaire, domaine, montant, commentaire=""):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO subventions (annee, nom_beneficiaire, domaine, montant, commentaire) "
            "VALUES (?, ?, ?, ?, ?)",
            (annee, nom_beneficiaire, domaine, montant, commentaire or ""),
        )
        conn.commit()


def delete(id_):
    with get_db() as conn:
        conn.execute("DELETE FROM subventions WHERE id = ?", (id_,))
        conn.commit()
