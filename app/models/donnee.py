from app.database import get_db


def get_by_indicateur(indicateur_id, ville_id=1):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM donnees WHERE indicateur_id = %s AND ville_id = %s ORDER BY annee DESC",
            (indicateur_id, ville_id)
        ).fetchall()
    return [dict(r) for r in rows]


def get_latest(indicateur_id, ville_id=1):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM donnees WHERE indicateur_id = %s AND ville_id = %s ORDER BY annee DESC LIMIT 1",
            (indicateur_id, ville_id)
        ).fetchone()
    return dict(row) if row else None


def get_by_indicateur_annee(indicateur_id, annee, ville_id=1):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM donnees WHERE indicateur_id = %s AND annee = %s AND ville_id = %s",
            (indicateur_id, annee, ville_id)
        ).fetchone()
    return dict(row) if row else None


def upsert(indicateur_id, annee, valeur, source, commentaire, mode_saisie, ville_id=1):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO donnees (indicateur_id, ville_id, annee, valeur, source, commentaire, mode_saisie)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(indicateur_id, annee, ville_id) DO UPDATE SET
                valeur = excluded.valeur,
                source = excluded.source,
                commentaire = excluded.commentaire,
                mode_saisie = excluded.mode_saisie,
                date_saisie = CURRENT_TIMESTAMP
        """, (indicateur_id, ville_id, annee, valeur, source, commentaire, mode_saisie))
        conn.commit()


def get_recentes(limit=20, ville_id=1):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT d.*, i.libelle_citoyen, i.thematique, i.unite
            FROM donnees d
            JOIN indicateurs i ON d.indicateur_id = i.id
            WHERE d.ville_id = %s
            ORDER BY d.date_saisie DESC
            LIMIT %s
        """, (ville_id, limit)).fetchall()
    return [dict(r) for r in rows]


def delete(indicateur_id, annee, ville_id=1):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM donnees WHERE indicateur_id = %s AND annee = %s AND ville_id = %s",
            (indicateur_id, annee, ville_id)
        )
        conn.execute(
            "DELETE FROM interpretations WHERE indicateur_id = %s AND annee = %s AND ville_id = %s",
            (indicateur_id, annee, ville_id)
        )
        conn.commit()


def get_all_for_ville(ville_id):
    """Retourne toutes les données d'une ville, triées par indicateur et année."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT indicateur_id, annee, valeur FROM donnees WHERE ville_id = %s ORDER BY indicateur_id, annee",
            (ville_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_derniere_maj(ville_id=1):
    with get_db() as conn:
        row = conn.execute(
            "SELECT MAX(date_saisie) as maj FROM donnees WHERE ville_id = %s", (ville_id,)
        ).fetchone()
    return row["maj"] if row and row["maj"] else None
