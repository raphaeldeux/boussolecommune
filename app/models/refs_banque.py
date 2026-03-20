from app.database import get_db


# ── Lecture ───────────────────────────────────────────────────────────────

def get_all(statut=None, indicateur_id=None, strate_id=None):
    """Retourne les entrées de la banque avec jointures indicateur + strate + auteurs."""
    where = []
    params = []
    if statut:
        where.append("rb.statut = %s")
        params.append(statut)
    if indicateur_id:
        where.append("rb.indicateur_id = %s")
        params.append(indicateur_id)
    if strate_id:
        where.append("rb.strate_id = %s")
        params.append(strate_id)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    conn = get_db()
    rows = conn.execute(f"""
        SELECT rb.*,
               i.libelle_citoyen, i.unite, i.thematique,
               s.nom            AS strate_nom,
               up.username      AS propose_par_nom,
               uv.username      AS valide_par_nom
        FROM refs_banque rb
        JOIN indicateurs i  ON rb.indicateur_id = i.id
        JOIN banque_references s ON rb.strate_id = s.id
        LEFT JOIN users up ON rb.propose_par = up.id
        LEFT JOIN users uv ON rb.valide_par  = uv.id
        {clause}
        ORDER BY i.thematique, i.libelle_citoyen, s.nom
    """, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_by_id(ref_id):
    conn = get_db()
    row = conn.execute("""
        SELECT rb.*,
               i.libelle_citoyen, i.unite, i.thematique,
               s.nom            AS strate_nom,
               up.username      AS propose_par_nom,
               uv.username      AS valide_par_nom
        FROM refs_banque rb
        JOIN indicateurs i  ON rb.indicateur_id = i.id
        JOIN banque_references s ON rb.strate_id = s.id
        LEFT JOIN users up ON rb.propose_par = up.id
        LEFT JOIN users uv ON rb.valide_par  = uv.id
        WHERE rb.id = %s
    """, (ref_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_valide_for_indicateur_strate(indicateur_id, strate_id):
    """Entrée validée pour un couple indicateur × strate (unicité)."""
    conn = get_db()
    row = conn.execute("""
        SELECT rb.*, s.nom AS strate_nom
        FROM refs_banque rb
        JOIN banque_references s ON rb.strate_id = s.id
        WHERE rb.indicateur_id = %s AND rb.strate_id = %s AND rb.statut = 'valide'
    """, (indicateur_id, strate_id)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_valides_for_indicateur(indicateur_id):
    """Toutes les entrées validées pour un indicateur (toutes strates)."""
    conn = get_db()
    rows = conn.execute("""
        SELECT rb.*, s.nom AS strate_nom
        FROM refs_banque rb
        JOIN banque_references s ON rb.strate_id = s.id
        WHERE rb.indicateur_id = %s AND rb.statut = 'valide'
        ORDER BY s.nom
    """, (indicateur_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_by_user(user_id):
    """Propositions d'un gestionnaire (toutes strates / statuts)."""
    conn = get_db()
    rows = conn.execute("""
        SELECT rb.*,
               i.libelle_citoyen, i.unite, i.thematique,
               s.nom AS strate_nom,
               uv.username AS valide_par_nom
        FROM refs_banque rb
        JOIN indicateurs i  ON rb.indicateur_id = i.id
        JOIN banque_references s ON rb.strate_id = s.id
        LEFT JOIN users uv ON rb.valide_par = uv.id
        WHERE rb.propose_par = %s
        ORDER BY rb.date_proposition DESC
    """, (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_pending():
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) AS nb FROM refs_banque WHERE statut = 'en_attente'"
    ).fetchone()
    conn.close()
    return row["nb"]


# ── Création ──────────────────────────────────────────────────────────────

def create(indicateur_id, strate_id, valeur, source, annee=None,
           statut='en_attente', propose_par=None, valide_par=None):
    conn = get_db()
    try:
        cur = conn.execute("""
            INSERT INTO refs_banque
                (indicateur_id, strate_id, valeur, source, annee,
                 statut, propose_par, valide_par,
                 date_validation)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                    CASE WHEN %s = 'valide' THEN CURRENT_TIMESTAMP ELSE NULL END)
            RETURNING id
        """, (indicateur_id, strate_id, valeur, source, annee,
              statut, propose_par, valide_par, statut))
        new_id = cur.fetchone()["id"]
        conn.commit()
        conn.close()
        return new_id
    except Exception as e:
        conn.close()
        raise e


# ── Modification ──────────────────────────────────────────────────────────

def update_statut(ref_id, statut, valide_par=None, commentaire_rejet=None):
    conn = get_db()
    conn.execute("""
        UPDATE refs_banque SET
            statut            = %s,
            valide_par        = %s,
            commentaire_rejet = %s,
            date_validation   = CASE WHEN %s IN ('valide','rejete') THEN CURRENT_TIMESTAMP ELSE NULL END
        WHERE id = %s
    """, (statut, valide_par, commentaire_rejet, statut, ref_id))
    conn.commit()
    conn.close()


def update_valeur(ref_id, valeur, source, annee=None):
    """Mise à jour des données d'une entrée par le super-admin."""
    conn = get_db()
    conn.execute(
        "UPDATE refs_banque SET valeur=%s, source=%s, annee=%s WHERE id=%s",
        (valeur, source, annee, ref_id)
    )
    conn.commit()
    conn.close()


def delete(ref_id):
    conn = get_db()
    conn.execute("DELETE FROM refs_banque WHERE id = %s", (ref_id,))
    conn.commit()
    conn.close()
