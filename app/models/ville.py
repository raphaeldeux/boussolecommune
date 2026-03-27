from app.database import get_db


def get_all(actif_only=True):
    with get_db() as conn:
        if actif_only:
            rows = conn.execute("SELECT * FROM villes WHERE actif = 1 ORDER BY nom").fetchall()
        else:
            rows = conn.execute("SELECT * FROM villes ORDER BY nom").fetchall()
    return [dict(r) for r in rows]


def get_by_id(ville_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM villes WHERE id = %s", (ville_id,)).fetchone()
    return dict(row) if row else None


def get_by_slug(slug):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM villes WHERE slug = %s AND actif = 1", (slug,)).fetchone()
    return dict(row) if row else None


def create(nom, slug, population=None):
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO villes (nom, slug, population) VALUES (%s, %s, %s) RETURNING id",
            (nom, slug, population)
        )
        ville_id = cur.fetchone()["id"]
        conn.commit()
    return ville_id


def update(ville_id, nom, slug, population=None, actif=1, code_insee=None, nb_conseillers=None,
           whatsapp_url=None, indicateurs_vedettes=None, prochain_conseil=None,
           prochain_conseil_heure=None):
    with get_db() as conn:
        conn.execute(
            "UPDATE villes SET nom=%s, slug=%s, population=%s, actif=%s, "
            "code_insee=%s, nb_conseillers=%s, whatsapp_url=%s, indicateurs_vedettes=%s, "
            "prochain_conseil=%s, prochain_conseil_heure=%s WHERE id=%s",
            (nom, slug, population, actif, code_insee or None, nb_conseillers,
             whatsapp_url or None, indicateurs_vedettes or None, prochain_conseil or None,
             prochain_conseil_heure or None, ville_id)
        )
        conn.commit()


def get_first_active():
    """Retourne la première ville active (défaut)."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM villes WHERE actif = 1 ORDER BY id LIMIT 1").fetchone()
    return dict(row) if row else None


def get_by_code_insee(code_insee: str):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM villes WHERE code_insee = %s AND actif = 1", (code_insee,)).fetchone()
    return dict(row) if row else None


def has_data(ville_id):
    """Vérifie si une ville a des données publiées."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as nb FROM donnees WHERE ville_id = %s", (ville_id,)
        ).fetchone()
    return row["nb"] > 0
