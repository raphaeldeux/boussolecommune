from app.database import get_db

LIMITE_PHRASE_COURTE = 200
LIMITE_PHRASE_LONGUE = 1000


def get(indicateur_id, annee, ville_id=1):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM interpretations WHERE indicateur_id = ? AND annee = ? AND ville_id = ?",
        (indicateur_id, annee, ville_id)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert(indicateur_id, annee, score, phrase_courte, phrase_longue, ville_id=1):
    # Applique les limites de caractères
    if phrase_courte:
        phrase_courte = phrase_courte[:LIMITE_PHRASE_COURTE]
    if phrase_longue:
        phrase_longue = phrase_longue[:LIMITE_PHRASE_LONGUE]
    conn = get_db()
    conn.execute("""
        INSERT INTO interpretations (indicateur_id, ville_id, annee, score, phrase_courte, phrase_longue)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(indicateur_id, annee, ville_id) DO UPDATE SET
            score = excluded.score,
            phrase_courte = excluded.phrase_courte,
            phrase_longue = excluded.phrase_longue,
            date_generation = CURRENT_TIMESTAMP
    """, (indicateur_id, ville_id, annee, score, phrase_courte, phrase_longue))
    conn.commit()
    conn.close()


def delete(indicateur_id, annee, ville_id=1):
    conn = get_db()
    conn.execute(
        "DELETE FROM interpretations WHERE indicateur_id = ? AND annee = ? AND ville_id = ?",
        (indicateur_id, annee, ville_id)
    )
    conn.commit()
    conn.close()


def get_all_for_thematique(thematique, annee, ville_id=1):
    conn = get_db()
    rows = conn.execute("""
        SELECT interp.*, i.libelle_citoyen, i.thematique
        FROM interpretations interp
        JOIN indicateurs i ON interp.indicateur_id = i.id
        WHERE i.thematique = ? AND interp.annee = ? AND interp.ville_id = ?
    """, (thematique, annee, ville_id)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
