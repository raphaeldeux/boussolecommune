from app.database import get_db

TRANCHES = [
    ("0-14",  0),
    ("15-29", 1),
    ("30-44", 2),
    ("45-59", 3),
    ("60-74", 4),
    ("75-89", 5),
    ("90+",   6),
]


def get_years(ville_id=1):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT annee FROM pyramide_ages WHERE ville_id = ? ORDER BY annee DESC",
            (ville_id,)
        ).fetchall()
    return [r["annee"] for r in rows]


def get_by_year(annee, ville_id=1):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT tranche, ordre, hommes, femmes FROM pyramide_ages "
            "WHERE annee = ? AND ville_id = ? ORDER BY ordre",
            (annee, ville_id),
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_year(annee, data, ville_id=1):
    """data : liste de dicts {tranche, ordre, hommes, femmes}."""
    with get_db() as conn:
        for row in data:
            conn.execute(
                "INSERT INTO pyramide_ages (ville_id, annee, tranche, ordre, hommes, femmes) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(ville_id, annee, tranche) DO UPDATE SET "
                "hommes=excluded.hommes, femmes=excluded.femmes",
                (ville_id, annee, row["tranche"], row["ordre"], row["hommes"], row["femmes"]),
            )
        conn.commit()


def delete_year(annee, ville_id=1):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM pyramide_ages WHERE annee = ? AND ville_id = ?",
            (annee, ville_id)
        )
        conn.commit()
