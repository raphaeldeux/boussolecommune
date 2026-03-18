from app.database import get_db


def get_all():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM banque_references ORDER BY nom"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_by_id(ref_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM banque_references WHERE id = ?", (ref_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def create(nom, description=""):
    conn = get_db()
    conn.execute(
        "INSERT INTO banque_references (nom, description) VALUES (?, ?)",
        (nom, description or "")
    )
    conn.commit()
    ref_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return ref_id


def update(ref_id, nom, description=""):
    conn = get_db()
    conn.execute(
        "UPDATE banque_references SET nom=?, description=? WHERE id=?",
        (nom, description or "", ref_id)
    )
    conn.commit()
    conn.close()


def delete(ref_id):
    conn = get_db()
    conn.execute("DELETE FROM banque_references WHERE id = ?", (ref_id,))
    conn.commit()
    conn.close()


def get_ref_for_indicateur_ville(indicateur_id, ville_id):
    """Retourne la référence choisie pour un indicateur dans une ville."""
    conn = get_db()
    row = conn.execute("""
        SELECT ivr.*, br.nom as banque_nom, br.description as banque_description
        FROM indicateur_ville_ref ivr
        LEFT JOIN banque_references br ON ivr.banque_reference_id = br.id
        WHERE ivr.indicateur_id = ? AND ivr.ville_id = ?
    """, (indicateur_id, ville_id)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_ref_for_indicateur_ville(indicateur_id, ville_id, banque_reference_id, valeur):
    conn = get_db()
    conn.execute("""
        INSERT INTO indicateur_ville_ref (indicateur_id, ville_id, banque_reference_id, valeur)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(indicateur_id, ville_id) DO UPDATE SET
            banque_reference_id = excluded.banque_reference_id,
            valeur = excluded.valeur
    """, (indicateur_id, ville_id, banque_reference_id, valeur))
    conn.commit()
    conn.close()


def clear_ref_for_indicateur_ville(indicateur_id, ville_id):
    conn = get_db()
    conn.execute(
        "DELETE FROM indicateur_ville_ref WHERE indicateur_id = ? AND ville_id = ?",
        (indicateur_id, ville_id)
    )
    conn.commit()
    conn.close()


def get_all_refs_for_ville(ville_id):
    """Retourne toutes les références configurées pour une ville."""
    conn = get_db()
    rows = conn.execute("""
        SELECT ivr.*, br.nom as banque_nom, i.libelle_citoyen, i.unite
        FROM indicateur_ville_ref ivr
        LEFT JOIN banque_references br ON ivr.banque_reference_id = br.id
        JOIN indicateurs i ON ivr.indicateur_id = i.id
        WHERE ivr.ville_id = ?
        ORDER BY i.thematique, i.id
    """, (ville_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
