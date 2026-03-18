import unicodedata
import re
from app.database import get_db


def normaliser(s: str) -> str:
    """Supprime les accents et met en minuscule."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9\s-]", "", s.lower())
    return s.strip()


def slugify(nom: str, dep_code: str) -> str:
    return normaliser(nom).replace(" ", "-") + "-" + dep_code.lower()


def search(q: str, limit: int = 8) -> list:
    """Recherche des communes par nom (préfixe, insensible aux accents)."""
    q_norm = normaliser(q)
    if len(q_norm) < 2:
        return []
    conn = get_db()
    rows = conn.execute("""
        SELECT c.code_insee, c.nom, c.departement_code, c.departement_nom, c.slug,
               sg.score,
               CASE WHEN v.id IS NOT NULL THEN 1 ELSE 0 END AS dans_la_base
        FROM communes c
        LEFT JOIN scores_globaux sg ON sg.code_insee = c.code_insee
        LEFT JOIN villes v ON v.code_insee = c.code_insee
        WHERE c.nom_normalise LIKE ?
        ORDER BY dans_la_base DESC, c.nom
        LIMIT ?
    """, (q_norm + "%", limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_fallback(q: str, limit: int = 8) -> list:
    """Recherche dans la table villes si communes est vide (avant seed_communes)."""
    q_lower = "%" + q.lower() + "%"
    conn = get_db()
    rows = conn.execute("""
        SELECT v.id, v.nom, v.slug, v.code_insee
        FROM villes v
        WHERE lower(v.nom) LIKE ? AND v.actif = 1
        LIMIT ?
    """, (q_lower, limit)).fetchall()
    conn.close()
    results = []
    for r in rows:
        results.append({
            "code_insee": r["code_insee"] or "",
            "nom": r["nom"],
            "departement_code": "",
            "departement_nom": "",
            "slug": r["slug"],
            "score": None,
            "dans_la_base": 1,
        })
    return results


def is_empty() -> bool:
    """Retourne True si la table communes n'a pas encore été peuplée."""
    conn = get_db()
    row = conn.execute("SELECT COUNT(*) AS nb FROM communes").fetchone()
    conn.close()
    return row["nb"] == 0


def get_by_slug(slug: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM communes WHERE slug = ?", (slug,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_by_code_insee(code_insee: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM communes WHERE code_insee = ?", (code_insee,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_vedettes() -> list:
    """Retourne les communes en vedette avec leur score et indicateur clé."""
    conn = get_db()
    rows = conn.execute("""
        SELECT cv.id AS vedette_id, cv.ordre, cv.code_insee,
               c.nom, c.departement_code, c.departement_nom, c.slug,
               sg.score,
               v.id AS ville_id, v.slug AS ville_slug
        FROM communes_vedette cv
        JOIN communes c ON c.code_insee = cv.code_insee
        LEFT JOIN scores_globaux sg ON sg.code_insee = cv.code_insee
        LEFT JOIN villes v ON v.code_insee = cv.code_insee
        WHERE cv.actif = 1
        ORDER BY cv.ordre
        LIMIT 3
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_score_global(code_insee: str, score: str) -> None:
    """Met à jour le cache du score global pour l'autocomplétion."""
    if not code_insee or not score:
        return
    conn = get_db()
    conn.execute("""
        INSERT INTO scores_globaux (code_insee, score)
        VALUES (?, ?)
        ON CONFLICT(code_insee) DO UPDATE SET
            score = excluded.score,
            date_calcul = CURRENT_TIMESTAMP
    """, (code_insee, score))
    conn.commit()
    conn.close()


def count_dans_base() -> int:
    conn = get_db()
    row = conn.execute("SELECT COUNT(*) AS nb FROM villes WHERE actif = 1").fetchone()
    conn.close()
    return row["nb"] if row else 0


def count_indicateurs() -> int:
    conn = get_db()
    row = conn.execute("SELECT COUNT(*) AS nb FROM indicateurs WHERE actif = 1").fetchone()
    conn.close()
    return row["nb"] if row else 0


# ── Gestion des vedettes (admin) ─────────────────────────────────────────

def get_all_vedettes() -> list:
    conn = get_db()
    rows = conn.execute("""
        SELECT cv.*, c.nom, c.departement_code, c.departement_nom, c.slug
        FROM communes_vedette cv
        JOIN communes c ON c.code_insee = cv.code_insee
        ORDER BY cv.ordre
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_vedettes(code_insees: list) -> None:
    """Remplace la liste des vedettes (max 3)."""
    conn = get_db()
    conn.execute("DELETE FROM communes_vedette")
    for i, code in enumerate(code_insees[:3], start=1):
        if code:
            conn.execute(
                "INSERT OR IGNORE INTO communes_vedette (code_insee, ordre, actif) VALUES (?, ?, 1)",
                (code, i)
            )
    conn.commit()
    conn.close()
