from app.database import get_db


def get_all(actif_only=True):
    with get_db() as conn:
        where = "WHERE actif = 1" if actif_only else ""
        rows = conn.execute(f"SELECT * FROM indicateurs {where} ORDER BY thematique, id").fetchall()
    return [dict(r) for r in rows]


def get_by_id(indicateur_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM indicateurs WHERE id = %s", (indicateur_id,)).fetchone()
    return dict(row) if row else None


def get_by_thematique(thematique):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM indicateurs WHERE thematique = %s AND actif = 1 ORDER BY id",
            (thematique,)
        ).fetchall()
    return [dict(r) for r in rows]


def update_reference(indicateur_id, valeur, libelle, annee):
    with get_db() as conn:
        conn.execute(
            """UPDATE indicateurs
               SET valeur_reference = %s, libelle_reference = %s, annee_reference = %s
               WHERE id = %s""",
            (valeur, libelle, annee, indicateur_id)
        )
        conn.commit()


def clear_reference(indicateur_id):
    with get_db() as conn:
        conn.execute(
            "UPDATE indicateurs SET valeur_reference=NULL, libelle_reference=NULL, annee_reference=NULL WHERE id=%s",
            (indicateur_id,)
        )
        conn.commit()


def get_thematiques():
    return ["finances", "cadre_vie", "personnes", "lien_social", "democratie", "vivant"]


THEMATIQUE_LABELS = {
    "finances":    "Soin de la maison",
    "cadre_vie":   "Soin du territoire",
    "personnes":   "Soin des habitant·es",
    "lien_social": "Soin du lien",
    "democratie":  "Soin de la parole",
    "vivant":      "Soin du vivant",
    "portrait":    "Portrait de la commune",
}

THEMATIQUE_QUESTIONS = {
    "finances":    "La commune se donne-t-elle les moyens d'agir ?",
    "cadre_vie":   "La commune entretient-elle son territoire ?",
    "personnes":   "La commune prend-elle soin de ses habitant·es ?",
    "lien_social": "La commune fait-elle vivre sa communauté ?",
    "democratie":  "La commune gouverne-t-elle avec transparence ?",
    "vivant":      "La commune ménage-t-elle son environnement ?",
    "portrait":    "",
}

THEMATIQUE_ICONS = {
    "finances":   "ri-home-4-line",
    "cadre_vie":  "ri-landscape-line",
    "personnes":  "ri-heart-line",
    "lien_social": "ri-group-line",
    "democratie": "ri-government-line",
    "vivant":     "ri-leaf-line",
    "portrait":   "ri-community-line",
}

THEMATIQUE_POIDS = {
    "finances":   0.25,
    "cadre_vie":  0.20,
    "personnes":  0.20,
    "lien_social": 0.15,
    "democratie": 0.12,
    "vivant":     0.08,
}
