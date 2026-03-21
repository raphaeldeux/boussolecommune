from app.database import get_db

CATEGORIES = ['budget', 'rapport', 'urbanisme', 'environnement', 'social', 'autre']


def get_all(ville_id):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM documents WHERE ville_id = %s ORDER BY date_creation DESC",
            (ville_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_publies(ville_id, limit=3):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM documents WHERE ville_id = %s AND publie = TRUE "
            "ORDER BY date_creation DESC LIMIT %s",
            (ville_id, limit)
        ).fetchall()
    return [dict(r) for r in rows]


def get_by_id(doc_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE id = %s", (doc_id,)
        ).fetchone()
    return dict(row) if row else None


def create(ville_id, titre, categorie, fichier=None):
    with get_db() as conn:
        row = conn.execute(
            "INSERT INTO documents (ville_id, titre, categorie, fichier) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (ville_id, titre, categorie, fichier)
        ).fetchone()
        conn.commit()
    return row["id"]


def set_publie(doc_id, publie):
    with get_db() as conn:
        conn.execute(
            "UPDATE documents SET publie=%s WHERE id=%s", (publie, doc_id)
        )
        conn.commit()


def delete(doc_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT fichier FROM documents WHERE id=%s", (doc_id,)
        ).fetchone()
        conn.execute("DELETE FROM documents WHERE id=%s", (doc_id,))
        conn.commit()
    return dict(row)["fichier"] if row else None
