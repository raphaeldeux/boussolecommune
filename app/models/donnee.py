from app.database import get_db


def get_by_indicateur(indicateur_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM donnees WHERE indicateur_id = ? ORDER BY annee DESC",
        (indicateur_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest(indicateur_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM donnees WHERE indicateur_id = ? ORDER BY annee DESC LIMIT 1",
        (indicateur_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_by_indicateur_annee(indicateur_id, annee):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM donnees WHERE indicateur_id = ? AND annee = ?",
        (indicateur_id, annee)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert(indicateur_id, annee, valeur, source, commentaire, mode_saisie):
    conn = get_db()
    conn.execute("""
        INSERT INTO donnees (indicateur_id, annee, valeur, source, commentaire, mode_saisie)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(indicateur_id, annee) DO UPDATE SET
            valeur = excluded.valeur,
            source = excluded.source,
            commentaire = excluded.commentaire,
            mode_saisie = excluded.mode_saisie,
            date_saisie = CURRENT_TIMESTAMP
    """, (indicateur_id, annee, valeur, source, commentaire, mode_saisie))
    conn.commit()
    conn.close()


def get_recentes(limit=20):
    conn = get_db()
    rows = conn.execute("""
        SELECT d.*, i.libelle_citoyen, i.thematique, i.unite
        FROM donnees d
        JOIN indicateurs i ON d.indicateur_id = i.id
        ORDER BY d.date_saisie DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete(indicateur_id, annee):
    conn = get_db()
    conn.execute(
        "DELETE FROM donnees WHERE indicateur_id = ? AND annee = ?",
        (indicateur_id, annee)
    )
    conn.execute(
        "DELETE FROM interpretations WHERE indicateur_id = ? AND annee = ?",
        (indicateur_id, annee)
    )
    conn.commit()
    conn.close()


def get_derniere_maj():
    conn = get_db()
    row = conn.execute("SELECT MAX(date_saisie) as maj FROM donnees").fetchone()
    conn.close()
    return row["maj"] if row and row["maj"] else None
