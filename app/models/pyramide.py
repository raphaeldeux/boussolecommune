from app.database import get_db

TRANCHES = [
    ("0-4",   0), ("5-9",   1), ("10-14", 2), ("15-19", 3),
    ("20-24", 4), ("25-29", 5), ("30-34", 6), ("35-39", 7),
    ("40-44", 8), ("45-49", 9), ("50-54", 10), ("55-59", 11),
    ("60-64", 12), ("65-69", 13), ("70-74", 14), ("75-79", 15),
    ("80-84", 16), ("85-89", 17), ("90+",   18),
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
