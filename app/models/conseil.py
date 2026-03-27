from app.database import get_db


def get_all(ville_id):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM conseils WHERE ville_id = %s ORDER BY date_conseil DESC",
            (ville_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_publies(ville_id, limit=3):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM conseils WHERE ville_id = %s AND publie = TRUE "
            "ORDER BY date_conseil DESC LIMIT %s",
            (ville_id, limit)
        ).fetchall()
    return [dict(r) for r in rows]


def get_by_id(conseil_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM conseils WHERE id = %s", (conseil_id,)
        ).fetchone()
    return dict(row) if row else None


def create(ville_id, titre, date_conseil, fichier_pdf=None, type_conseil="municipal"):
    with get_db() as conn:
        row = conn.execute(
            "INSERT INTO conseils (ville_id, titre, date_conseil, fichier_pdf, type_conseil) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (ville_id, titre, date_conseil, fichier_pdf, type_conseil)
        ).fetchone()
        conn.commit()
    return row["id"]


def update(conseil_id, titre, date_conseil, fichier_pdf=None, type_conseil="municipal"):
    with get_db() as conn:
        if fichier_pdf is not None:
            conn.execute(
                "UPDATE conseils SET titre=%s, date_conseil=%s, fichier_pdf=%s, type_conseil=%s WHERE id=%s",
                (titre, date_conseil, fichier_pdf, type_conseil, conseil_id)
            )
        else:
            conn.execute(
                "UPDATE conseils SET titre=%s, date_conseil=%s, type_conseil=%s WHERE id=%s",
                (titre, date_conseil, type_conseil, conseil_id)
            )
        conn.commit()


def set_publie(conseil_id, publie):
    with get_db() as conn:
        conn.execute(
            "UPDATE conseils SET publie=%s WHERE id=%s",
            (publie, conseil_id)
        )
        conn.commit()


def delete(conseil_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT fichier_pdf, note_synthese_pdf FROM conseils WHERE id=%s",
            (conseil_id,)
        ).fetchone()
        conn.execute("DELETE FROM conseils WHERE id=%s", (conseil_id,))
        conn.commit()
    if not row:
        return None, None
    return dict(row).get("fichier_pdf"), dict(row).get("note_synthese_pdf")


def set_note_synthese(conseil_id, filename):
    with get_db() as conn:
        conn.execute("UPDATE conseils SET note_synthese_pdf=%s WHERE id=%s", (filename, conseil_id))
        conn.commit()


def set_statut_odj(conseil_id, statut, odj_texte=None, resume_avant_seance=None, progres=None):
    champs = [("statut_odj", statut)]
    if odj_texte is not None:
        champs.append(("odj_texte", odj_texte))
    if resume_avant_seance is not None:
        champs.append(("resume_avant_seance", resume_avant_seance))
    if progres is not None:
        champs.append(("progres_odj", progres))
    set_clause = ", ".join(f"{col}=%s" for col, _ in champs)
    valeurs = [val for _, val in champs] + [conseil_id]
    with get_db() as conn:
        conn.execute(f"UPDATE conseils SET {set_clause} WHERE id=%s", valeurs)
        conn.commit()


def set_odj_publie(conseil_id, publie):
    with get_db() as conn:
        conn.execute("UPDATE conseils SET odj_publie=%s WHERE id=%s", (publie, conseil_id))
        conn.commit()


def set_statut_resume(conseil_id, statut, resume_citoyen=None, resume_structure=None, progres=None, message=None):
    """Met à jour statut_resume et optionnellement resume_citoyen, resume_structure, progres_resume, message_resume."""
    champs = [("statut_resume", statut)]
    if resume_citoyen is not None:
        champs.append(("resume_citoyen", resume_citoyen))
    if resume_structure is not None:
        champs.append(("resume_structure", resume_structure))
    if progres is not None:
        champs.append(("progres_resume", progres))
    if message is not None:
        champs.append(("message_resume", message))
    set_clause = ", ".join(f"{col}=%s" for col, _ in champs)
    valeurs = [val for _, val in champs] + [conseil_id]
    with get_db() as conn:
        conn.execute(
            f"UPDATE conseils SET {set_clause} WHERE id=%s",
            valeurs
        )
        conn.commit()
