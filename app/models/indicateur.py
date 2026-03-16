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
    return ["finances", "ecologie", "social", "gouvernance", "services", "economie"]


THEMATIQUE_LABELS = {
    "finances": "Finances publiques",
    "ecologie": "Écologie & environnement",
    "social": "Social & cohésion",
    "gouvernance": "Gouvernance & transparence",
    "services": "Services publics & patrimoine",
    "economie": "Vitalité économique",
}

THEMATIQUE_ICONS = {
    "finances": "💰",
    "ecologie": "🌿",
    "social": "🤝",
    "gouvernance": "🏛️",
    "services": "🏗️",
    "economie": "📈",
}

THEMATIQUE_POIDS = {
    "finances": 0.25,
    "ecologie": 0.20,
    "social": 0.20,
    "gouvernance": 0.15,
    "services": 0.10,
    "economie": 0.10,
}
