"""
banque_reference.py
Gestion des STRATES (table banque_references) et des assignations
ville↔indicateur (table indicateur_ville_ref).
"""
from app.database import get_db


# ── Strates ───────────────────────────────────────────────────────────────

def get_all():
    conn = get_db()
    rows = conn.execute("SELECT * FROM banque_references ORDER BY nom").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_by_id(strate_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM banque_references WHERE id = ?", (strate_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def create(nom, description=""):
    conn = get_db()
    conn.execute(
        "INSERT INTO banque_references (nom, description) VALUES (?, ?)",
        (nom, description or "")
    )
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return new_id


def update(strate_id, nom, description=""):
    conn = get_db()
    conn.execute(
        "UPDATE banque_references SET nom=?, description=? WHERE id=?",
        (nom, description or "", strate_id)
    )
    conn.commit()
    conn.close()


def delete(strate_id):
    conn = get_db()
    conn.execute("DELETE FROM banque_references WHERE id = ?", (strate_id,))
    conn.commit()
    conn.close()


def count_refs_for_strate(strate_id):
    """Nombre d'entrées banque rattachées à cette strate."""
    conn = get_db()
    n = conn.execute(
        "SELECT COUNT(*) FROM refs_banque WHERE strate_id = ?", (strate_id,)
    ).fetchone()[0]
    conn.close()
    return n


# ── Assignation ville ↔ indicateur ────────────────────────────────────────

def get_ref_for_indicateur_ville(indicateur_id, ville_id):
    """
    Retourne la référence active pour un indicateur dans une ville.
    Priorité : ref_banque_id > valeur_locale > (ancienne colonne valeur).
    Renvoie toujours un dict avec la clé 'valeur' pour compatibilité scoring.
    """
    conn = get_db()
    row = conn.execute("""
        SELECT ivr.*,
               rb.valeur    AS banque_valeur,
               rb.source    AS banque_source,
               rb.annee     AS banque_annee,
               s.nom        AS strate_nom
        FROM indicateur_ville_ref ivr
        LEFT JOIN refs_banque      rb ON ivr.ref_banque_id = rb.id AND rb.statut = 'valide'
        LEFT JOIN banque_references s ON rb.strate_id = s.id
        WHERE ivr.indicateur_id = ? AND ivr.ville_id = ?
    """, (indicateur_id, ville_id)).fetchone()
    conn.close()
    if not row:
        return None
    r = dict(row)
    # Valeur effective : banque si ref validée, sinon valeur_locale
    if r.get('ref_banque_id') and r.get('banque_valeur') is not None:
        r['valeur'] = r['banque_valeur']
        r['is_banque'] = True
    elif r.get('valeur_locale') is not None:
        r['valeur'] = r['valeur_locale']
        r['is_banque'] = False
    else:
        # compat ancien schéma (colonne valeur directe)
        r['is_banque'] = False
    return r


def set_ref_banque(indicateur_id, ville_id, ref_banque_id):
    """Assigne une entrée validée de la banque à cet indicateur pour cette ville."""
    conn = get_db()
    conn.execute("""
        INSERT INTO indicateur_ville_ref
            (indicateur_id, ville_id, ref_banque_id, valeur_locale, justification_locale)
        VALUES (?, ?, ?, NULL, NULL)
        ON CONFLICT(indicateur_id, ville_id) DO UPDATE SET
            ref_banque_id        = excluded.ref_banque_id,
            valeur_locale        = NULL,
            justification_locale = NULL
    """, (indicateur_id, ville_id, ref_banque_id))
    conn.commit()
    conn.close()


def set_ref_locale(indicateur_id, ville_id, valeur_locale, justification=""):
    """Saisit une valeur locale dérogatoire."""
    conn = get_db()
    conn.execute("""
        INSERT INTO indicateur_ville_ref
            (indicateur_id, ville_id, ref_banque_id, valeur_locale, justification_locale)
        VALUES (?, ?, NULL, ?, ?)
        ON CONFLICT(indicateur_id, ville_id) DO UPDATE SET
            ref_banque_id        = NULL,
            valeur_locale        = excluded.valeur_locale,
            justification_locale = excluded.justification_locale
    """, (indicateur_id, ville_id, valeur_locale, justification or ""))
    conn.commit()
    conn.close()


def clear_ref_for_indicateur_ville(indicateur_id, ville_id):
    conn = get_db()
    conn.execute(
        "DELETE FROM indicateur_ville_ref WHERE indicateur_id=? AND ville_id=?",
        (indicateur_id, ville_id)
    )
    conn.commit()
    conn.close()


def get_all_refs_for_ville(ville_id):
    conn = get_db()
    rows = conn.execute("""
        SELECT ivr.*,
               i.libelle_citoyen, i.unite, i.thematique,
               rb.valeur    AS banque_valeur,
               rb.source    AS banque_source,
               s.nom        AS strate_nom
        FROM indicateur_ville_ref ivr
        JOIN indicateurs i ON ivr.indicateur_id = i.id
        LEFT JOIN refs_banque      rb ON ivr.ref_banque_id = rb.id AND rb.statut = 'valide'
        LEFT JOIN banque_references s ON rb.strate_id = s.id
        WHERE ivr.ville_id = ?
        ORDER BY i.thematique, i.id
    """, (ville_id,)).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        if d.get('ref_banque_id') and d.get('banque_valeur') is not None:
            d['valeur'] = d['banque_valeur']
            d['is_banque'] = True
        elif d.get('valeur_locale') is not None:
            d['valeur'] = d['valeur_locale']
            d['is_banque'] = False
        else:
            d['is_banque'] = False
        result.append(d)
    return result


# Alias de compatibilité pour l'ancien code appelant set_ref_for_indicateur_ville
def set_ref_for_indicateur_ville(indicateur_id, ville_id, banque_reference_id, valeur):
    """Compatibilité : utilise valeur_locale."""
    set_ref_locale(indicateur_id, ville_id, valeur)
