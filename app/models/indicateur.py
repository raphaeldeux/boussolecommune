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
    return ["humain", "lien_social", "cadre_vie", "avenir", "democratie", "cooperation"]


THEMATIQUE_LABELS = {
    "humain":      "Prendre soin de l'humain",
    "lien_social": "Prendre soin du lien social",
    "cadre_vie":   "Prendre soin du cadre de vie",
    "avenir":      "Prendre soin de l'avenir",
    "democratie":  "Prendre soin de la démocratie",
    "cooperation": "Prendre soin de la coopération métropolitaine",
}

THEMATIQUE_ICONS = {
    "humain":      "❤️",
    "lien_social": "🤝",
    "cadre_vie":   "🌳",
    "avenir":      "🔮",
    "democratie":  "🏛️",
    "cooperation": "🌐",
}

THEMATIQUE_POIDS = {
    "humain":      0.20,
    "lien_social": 0.15,
    "cadre_vie":   0.20,
    "avenir":      0.25,
    "democratie":  0.10,
    "cooperation": 0.10,
}
