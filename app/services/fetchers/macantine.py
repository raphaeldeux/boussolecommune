"""
Fetcher ma-cantine.agriculture.gouv.fr
Récupère les indicateurs EGAlim par commune et par année.

Endpoint public (sans authentification) :
  GET /api/v1/canteenStatistics/?city=<insee>&year=<annee>

Indicateurs retournés :
  eco_part_bio_cantine        → bioPercent       (objectif EGAlim : 20 %)
  eco_egalim_cantine          → egalimPercent     (objectif EGAlim : 50 %)
  eco_viandes_egalim_cantine  → viandesVolaillesEgalimPercent (objectif : 60 %)
  eco_mer_egalim_cantine      → produitsDeLaMerEgalimPercent  (objectif : 60 %)
"""

import requests

BASE_URL = "https://ma-cantine.agriculture.gouv.fr/api/v1"
SOURCE = "ma-cantine.agriculture.gouv.fr"
TIMEOUT = 15

# Correspondance champ API → indicateur_id
CHAMPS = {
    "bioPercent":                    "eco_part_bio_cantine",
    "egalimPercent":                 "eco_egalim_cantine",
    "viandesVolaillesEgalimPercent": "eco_viandes_egalim_cantine",
    "produitsDeLaMerEgalimPercent":  "eco_mer_egalim_cantine",
}


def fetch_all_cantine_data(code_insee: str) -> dict:
    """
    Récupère les données ma-cantine pour toutes les années disponibles (2020 → année en cours).

    Retourne :
    {
        "ok": True,
        "lignes": [{"indicateur_id": str, "annee": int, "valeur": float, "source": str}],
        "annees": [int],
        "erreurs": [str],
    }
    """
    import datetime
    annee_max = datetime.date.today().year
    lignes = []
    erreurs = []
    annees_ok = []

    for annee in range(2020, annee_max + 1):
        result = fetch_cantine_data(code_insee, annee)
        if not result["ok"]:
            erreurs.append(f"{annee} : {result['error']}")
            continue
        if not result["indicateurs"]:
            erreurs.append(f"{annee} : aucun indicateur retourné")
            continue
        annees_ok.append(annee)
        for ind_id, valeur in result["indicateurs"].items():
            lignes.append({
                "indicateur_id": ind_id,
                "annee": annee,
                "valeur": valeur,
                "source": SOURCE,
            })

    if not lignes:
        return {"ok": False, "error": "Aucune donnée disponible pour cette commune"}

    return {
        "ok": True,
        "lignes": lignes,
        "annees": sorted(annees_ok, reverse=True),
        "erreurs": erreurs,
    }


def fetch_cantine_data(code_insee: str, annee: int) -> dict:
    """
    Interroge l'API ma-cantine pour une commune et une année données.

    Retourne un dict :
      {
        "ok": True,
        "source": str,
        "canteen_count": int,
        "teledeclarations_count": int,
        "indicateurs": {
            "eco_part_bio_cantine": 32.0,
            "eco_egalim_cantine": 52.0,
            ...   (champ absent = None → ne pas insérer)
        }
      }
    ou en cas d'erreur :
      {"ok": False, "error": str}
    """
    try:
        resp = requests.get(
            f"{BASE_URL}/canteenStatistics/",
            params={"city": code_insee, "year": annee},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout:
        return {"ok": False, "error": "Délai d'attente dépassé (ma-cantine)"}
    except requests.exceptions.HTTPError as e:
        return {"ok": False, "error": f"Erreur HTTP {resp.status_code} : {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    canteen_count = data.get("canteenCount", 0)
    teledecl_count = data.get("teledeclarationsCount", 0)

    if canteen_count == 0:
        return {"ok": False, "error": "Aucune cantine référencée pour cette commune"}

    if teledecl_count == 0:
        return {"ok": False, "error": f"{canteen_count} cantine(s) référencée(s) mais aucune télédéclaration pour {annee}"}

    indicateurs = {}
    for champ, ind_id in CHAMPS.items():
        val = data.get(champ)
        # On n'insère pas si la valeur est None ou si c'est 0 sans déclaration
        if val is not None:
            indicateurs[ind_id] = float(val)

    return {
        "ok": True,
        "source": SOURCE,
        "canteen_count": canteen_count,
        "teledeclarations_count": teledecl_count,
        "indicateurs": indicateurs,
    }
