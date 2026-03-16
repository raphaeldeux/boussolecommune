from app.database import get_db


def get_all(actif_only=True):
    conn = get_db()
    where = "WHERE actif = 1" if actif_only else ""
    rows = conn.execute(f"SELECT * FROM indicateurs {where} ORDER BY thematique, id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_by_id(indicateur_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM indicateurs WHERE id = ?", (indicateur_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_by_thematique(thematique):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM indicateurs WHERE thematique = ? AND actif = 1 ORDER BY id",
        (thematique,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_thematiques():
    return ["finances", "cadre_vie", "personnes", "lien_social", "democratie", "vivant"]


THEMATIQUE_LABELS = {
    "finances":   "Soin des finances",
    "cadre_vie":  "Soin du cadre de vie",
    "personnes":  "Soin des personnes",
    "lien_social": "Soin du lien social",
    "democratie": "Soin de la démocratie",
    "vivant":     "Soin du vivant",
    "portrait":   "Portrait de la commune",
}

THEMATIQUE_QUESTIONS = {
    "finances":   "La commune gère-t-elle sainement l'argent public ?",
    "cadre_vie":  "La commune entretient-elle son territoire ?",
    "personnes":  "La commune prend-elle soin de ses habitants ?",
    "lien_social": "La commune fait-elle vivre sa communauté ?",
    "democratie": "La commune gouverne-t-elle avec transparence ?",
    "vivant":     "La commune ménage-t-elle son environnement ?",
    "portrait":   "",
}

THEMATIQUE_ICONS = {
    "finances":   "💰",
    "cadre_vie":  "🌳",
    "personnes":  "❤️",
    "lien_social": "🤝",
    "democratie": "🏛️",
    "vivant":     "🌿",
    "portrait":   "🏘️",
}

THEMATIQUE_POIDS = {
    "finances":   0.25,
    "cadre_vie":  0.20,
    "personnes":  0.20,
    "lien_social": 0.15,
    "democratie": 0.12,
    "vivant":     0.08,
}
