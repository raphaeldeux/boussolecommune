from app.database import get_db

DOMAINES = ["sport", "culture", "social", "environnement", "education", "autre"]


def get_years(ville_id=1):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT annee FROM subventions WHERE ville_id = ? ORDER BY annee DESC",
            (ville_id,)
        ).fetchall()
    return [r["annee"] for r in rows]


def get_by_year(annee, ville_id=1):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, nom_beneficiaire, domaine, montant, commentaire "
            "FROM subventions WHERE annee = ? AND ville_id = ? ORDER BY montant DESC",
            (annee, ville_id),
        ).fetchall()
    return [dict(r) for r in rows]


def get_totaux_par_domaine(annee, ville_id=1):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT domaine, SUM(montant) AS total FROM subventions "
            "WHERE annee = ? AND ville_id = ? GROUP BY domaine ORDER BY total DESC",
            (annee, ville_id),
        ).fetchall()
    return [dict(r) for r in rows]


def get_total(annee, ville_id=1):
    with get_db() as conn:
        row = conn.execute(
            "SELECT SUM(montant) AS total FROM subventions WHERE annee = ? AND ville_id = ?",
            (annee, ville_id),
        ).fetchone()
    return row["total"] or 0


def insert(annee, nom_beneficiaire, domaine, montant, commentaire="", ville_id=1):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO subventions (ville_id, annee, nom_beneficiaire, domaine, montant, commentaire) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ville_id, annee, nom_beneficiaire, domaine, montant, commentaire or ""),
        )
        conn.commit()


def delete(id_):
    with get_db() as conn:
        conn.execute("DELETE FROM subventions WHERE id = ?", (id_,))
        conn.commit()
