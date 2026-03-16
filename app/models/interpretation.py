from app.database import get_db


def get(indicateur_id, annee):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM interpretations WHERE indicateur_id = ? AND annee = ?",
        (indicateur_id, annee)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert(indicateur_id, annee, score, phrase_courte, phrase_longue):
    conn = get_db()
    conn.execute("""
        INSERT INTO interpretations (indicateur_id, annee, score, phrase_courte, phrase_longue)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(indicateur_id, annee) DO UPDATE SET
            score = excluded.score,
            phrase_courte = excluded.phrase_courte,
            phrase_longue = excluded.phrase_longue,
            date_generation = CURRENT_TIMESTAMP
    """, (indicateur_id, annee, score, phrase_courte, phrase_longue))
    conn.commit()
    conn.close()


def get_all_for_thematique(thematique, annee):
    conn = get_db()
    rows = conn.execute("""
        SELECT interp.*, i.libelle_citoyen, i.thematique
        FROM interpretations interp
        JOIN indicateurs i ON interp.indicateur_id = i.id
        WHERE i.thematique = ? AND interp.annee = ?
    """, (thematique, annee)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
