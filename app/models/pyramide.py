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


def get_years():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT annee FROM pyramide_ages ORDER BY annee DESC"
        ).fetchall()
    return [r["annee"] for r in rows]


def get_by_year(annee):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT tranche, ordre, hommes, femmes FROM pyramide_ages "
            "WHERE annee = ? ORDER BY ordre",
            (annee,),
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_year(annee, data):
    """data : liste de dicts {tranche, ordre, hommes, femmes}."""
    with get_db() as conn:
        for row in data:
            conn.execute(
                "INSERT INTO pyramide_ages (annee, tranche, ordre, hommes, femmes) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(annee, tranche) DO UPDATE SET "
                "hommes=excluded.hommes, femmes=excluded.femmes",
                (annee, row["tranche"], row["ordre"], row["hommes"], row["femmes"]),
            )
        conn.commit()


def delete_year(annee):
    with get_db() as conn:
        conn.execute("DELETE FROM pyramide_ages WHERE annee = ?", (annee,))
        conn.commit()
