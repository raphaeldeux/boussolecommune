"""
Fetcher OFGL — data.ofgl.fr
Récupère les données financières d'une commune via l'API publique.

Endpoint :
  GET https://data.ofgl.fr/api/explore/v2.1/catalog/datasets/ofgl-base-communes-consolidee/records
    ?where=com_code="44194"&limit=100&order_by=exer desc

Structure : chaque enregistrement a un champ `agregat` (catégorie) et `montant` (€ brut),
`euros_par_habitant` (€/hab) et `exer` (année). On calcule les ratios depuis ces valeurs.
"""
import requests

BASE_URL = "https://data.ofgl.fr/api/explore/v2.1/catalog/datasets/ofgl-base-communes-consolidee/records"
SOURCE = "OFGL — data.ofgl.fr"
TIMEOUT = 20
MAX_RECORDS_PER_PAGE = 100

# Agrégats à récupérer
AGREGAT_EPARGNE_BRUTE = "Epargne brute"
AGREGAT_RECETTES_FONCT = "Recettes de fonctionnement"
AGREGAT_DEP_FONCT = "Dépenses de fonctionnement"
AGREGAT_ENCOURS_DETTE = "Encours de dette"
AGREGAT_FRAIS_PERSONNEL = "Frais de personnel"
AGREGAT_ANNUITE = "Annuité de la dette"
AGREGAT_DEP_INVEST = "Dépenses d'investissement"

AGREGATS_NECESSAIRES = {
    AGREGAT_EPARGNE_BRUTE, AGREGAT_RECETTES_FONCT, AGREGAT_DEP_FONCT,
    AGREGAT_ENCOURS_DETTE, AGREGAT_FRAIS_PERSONNEL, AGREGAT_ANNUITE,
    AGREGAT_DEP_INVEST,
}


def _fetch_all_records(com_code: str) -> list:
    """Récupère tous les enregistrements OFGL pour une commune (pagination)."""
    records = []
    offset = 0
    while True:
        try:
            resp = requests.get(
                BASE_URL,
                params={
                    "where": f'com_code="{com_code}"',
                    "limit": MAX_RECORDS_PER_PAGE,
                    "offset": offset,
                },
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"Erreur API OFGL : {e}")

        batch = data.get("results", [])
        if not batch:
            break
        records.extend(batch)
        if len(batch) < MAX_RECORDS_PER_PAGE:
            break
        offset += MAX_RECORDS_PER_PAGE
    return records


def fetch_ofgl_data(com_code: str) -> dict:
    """
    Récupère toutes les années disponibles pour une commune.

    Retourne :
    {
        "ok": True,
        "lignes": [{"indicateur_id": str, "annee": int, "valeur": float, "source": str}],
        "erreurs": [str],
        "annees": [int],
    }
    """
    try:
        records = _fetch_all_records(com_code)
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}

    if not records:
        return {"ok": False, "error": f"Aucune donnée OFGL pour le code commune {com_code}"}

    # Grouper par année
    by_year = {}
    for rec in records:
        year_str = rec.get("exer")
        agregat = rec.get("agregat", "")
        if not year_str or agregat not in AGREGATS_NECESSAIRES:
            continue
        try:
            year = int(year_str)
        except (ValueError, TypeError):
            continue
        if year not in by_year:
            by_year[year] = {}
        by_year[year][agregat] = rec

    lignes = []
    erreurs = []

    for year in sorted(by_year.keys()):
        data_year = by_year[year]

        def get_montant(agregat):
            rec = data_year.get(agregat)
            if rec is None:
                return None
            try:
                return float(rec["montant"])
            except (KeyError, TypeError, ValueError):
                return None

        def get_eur_hab(agregat):
            rec = data_year.get(agregat)
            if rec is None:
                return None
            try:
                return float(rec["euros_par_habitant"])
            except (KeyError, TypeError, ValueError):
                return None

        epargne = get_montant(AGREGAT_EPARGNE_BRUTE)
        recettes = get_montant(AGREGAT_RECETTES_FONCT)
        dep_fonct = get_montant(AGREGAT_DEP_FONCT)
        encours = get_montant(AGREGAT_ENCOURS_DETTE)
        personnel = get_montant(AGREGAT_FRAIS_PERSONNEL)
        annuite = get_montant(AGREGAT_ANNUITE)
        invest_hab = get_eur_hab(AGREGAT_DEP_INVEST)
        dette_hab = get_eur_hab(AGREGAT_ENCOURS_DETTE)

        # fin_epargne_brute : % recettes de fonctionnement
        if epargne is not None and recettes and recettes > 0:
            lignes.append({
                "indicateur_id": "fin_epargne_brute",
                "annee": year,
                "valeur": round(epargne / recettes * 100, 2),
                "source": SOURCE,
            })
        else:
            erreurs.append(f"{year}: impossible de calculer fin_epargne_brute")

        # fin_dette_habitant : €/hab
        if dette_hab is not None:
            lignes.append({
                "indicateur_id": "fin_dette_habitant",
                "annee": year,
                "valeur": round(dette_hab, 2),
                "source": SOURCE,
            })
        else:
            erreurs.append(f"{year}: données manquantes pour fin_dette_habitant")

        # fin_capacite_desendettement : années
        if encours is not None and epargne and epargne > 0:
            lignes.append({
                "indicateur_id": "fin_capacite_desendettement",
                "annee": year,
                "valeur": round(encours / epargne, 2),
                "source": SOURCE,
            })
        else:
            erreurs.append(f"{year}: impossible de calculer fin_capacite_desendettement")

        # fin_investissement_habitant : €/hab
        if invest_hab is not None:
            lignes.append({
                "indicateur_id": "fin_investissement_habitant",
                "annee": year,
                "valeur": round(invest_hab, 2),
                "source": SOURCE,
            })
        else:
            erreurs.append(f"{year}: données manquantes pour fin_investissement_habitant")

        # fin_masse_salariale_ratio : % dépenses de fonctionnement
        if personnel is not None and dep_fonct and dep_fonct > 0:
            lignes.append({
                "indicateur_id": "fin_masse_salariale_ratio",
                "annee": year,
                "valeur": round(personnel / dep_fonct * 100, 2),
                "source": SOURCE,
            })
        else:
            erreurs.append(f"{year}: impossible de calculer fin_masse_salariale_ratio")

        # fin_rigidite_charges : % dépenses de fonctionnement
        if personnel is not None and annuite is not None and dep_fonct and dep_fonct > 0:
            lignes.append({
                "indicateur_id": "fin_rigidite_charges",
                "annee": year,
                "valeur": round((personnel + annuite) / dep_fonct * 100, 2),
                "source": SOURCE,
            })
        else:
            erreurs.append(f"{year}: impossible de calculer fin_rigidite_charges")

    return {
        "ok": True,
        "lignes": lignes,
        "erreurs": erreurs,
        "annees": sorted(by_year.keys(), reverse=True),
    }
