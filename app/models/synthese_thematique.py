from app.database import get_db


def get(ville_id: int, thematique: str, annee: int) -> dict | None:
    """Retourne la synthèse ou None si absente."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM syntheses_thematiques WHERE ville_id = %s AND thematique = %s AND annee = %s",
            (ville_id, thematique, annee),
        ).fetchone()
    return dict(row) if row else None


def upsert(ville_id: int, thematique: str, annee: int, texte: str) -> None:
    """Insère ou met à jour une synthèse (ON CONFLICT UPDATE)."""
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO syntheses_thematiques (ville_id, thematique, annee, texte, date_generation)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (ville_id, thematique, annee)
            DO UPDATE SET texte = EXCLUDED.texte, date_generation = CURRENT_TIMESTAMP
            """,
            (ville_id, thematique, annee, texte),
        )
        conn.commit()


def delete(ville_id: int, thematique: str, annee: int) -> None:
    """Supprime une synthèse."""
    with get_db() as conn:
        conn.execute(
            "DELETE FROM syntheses_thematiques WHERE ville_id = %s AND thematique = %s AND annee = %s",
            (ville_id, thematique, annee),
        )
        conn.commit()


def get_all_for_ville(ville_id: int) -> list[dict]:
    """Retourne toutes les synthèses d'une ville (pour l'admin dashboard)."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM syntheses_thematiques WHERE ville_id = %s ORDER BY thematique, annee DESC",
            (ville_id,),
        ).fetchall()
    return [dict(r) for r in rows]
