from app.database import get_db


def get_all(actif_only=True):
    conn = get_db()
    where = "WHERE actif = 1" if actif_only else ""
    rows = conn.execute(f"SELECT * FROM villes {where} ORDER BY nom").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_by_id(ville_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM villes WHERE id = ?", (ville_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_by_slug(slug):
    conn = get_db()
    row = conn.execute("SELECT * FROM villes WHERE slug = ? AND actif = 1", (slug,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create(nom, slug, population=None):
    conn = get_db()
    conn.execute(
        "INSERT INTO villes (nom, slug, population) VALUES (?, ?, ?)",
        (nom, slug, population)
    )
    conn.commit()
    ville_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return ville_id


def update(ville_id, nom, slug, population=None, actif=1):
    conn = get_db()
    conn.execute(
        "UPDATE villes SET nom=?, slug=?, population=?, actif=? WHERE id=?",
        (nom, slug, population, actif, ville_id)
    )
    conn.commit()
    conn.close()


def get_first_active():
    """Retourne la première ville active (défaut)."""
    conn = get_db()
    row = conn.execute("SELECT * FROM villes WHERE actif = 1 ORDER BY id LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else None


def has_data(ville_id):
    """Vérifie si une ville a des données publiées."""
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) as nb FROM donnees WHERE ville_id = ?", (ville_id,)
    ).fetchone()
    conn.close()
    return row["nb"] > 0
