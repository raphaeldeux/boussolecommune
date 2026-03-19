"""
Fetcher ma-cantine.agriculture.gouv.fr
Récupère le taux de produits bio (%) par commune et par année.

Endpoint public (sans authentification) :
  GET /api/v1/canteenStatistics/?city=<insee>&year=<annee>
Champ utilisé : bioPercent (entier 0-100)
"""

import requests

BASE_URL = "https://ma-cantine.agriculture.gouv.fr/api/v1"
INDICATEUR_ID = "eco_part_bio_cantine"
SOURCE = "ma-cantine.agriculture.gouv.fr"
TIMEOUT = 15


def fetch_bio_percent(code_insee: str, annee: int) -> dict:
    """
    Interroge l'API ma-cantine pour une commune et une année données.

    Retourne un dict :
      {
        "valeur": float,          # bioPercent (0-100)
        "source": str,
        "canteen_count": int,     # nb de cantines déclarantes
        "egalim_percent": float,  # % EGAlim global (informatif)
        "ok": True
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

    bio = data.get("bioPercent")
    if bio is None:
        return {"ok": False, "error": "Champ bioPercent absent de la réponse"}

    canteen_count = data.get("canteenCount", 0)
    if canteen_count == 0:
        return {"ok": False, "error": "Aucune cantine déclarante pour cette commune et cette année"}

    return {
        "ok": True,
        "valeur": float(bio),
        "source": SOURCE,
        "canteen_count": canteen_count,
        "egalim_percent": data.get("egalimPercent"),
    }
