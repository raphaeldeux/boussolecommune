"""
Fetcher BPE — Base Permanente des Équipements (INSEE via data.gouv.fr)
https://www.data.gouv.fr/fr/datasets/base-permanente-des-equipements/

Pas d'authentification requise.
Téléchargement du fichier CSV annuel et filtrage par commune.
"""

import io
import csv
import gzip
import requests
from datetime import datetime

DATASET_URL = "https://www.data.gouv.fr/api/1/datasets/base-permanente-des-equipements/"
SOURCE = "BPE INSEE"
TIMEOUT = 60

# Codes BPE à comptabiliser pour eco2_nb_commerces
# Nomenclature : https://www.insee.fr/fr/information/2410988
TYPES_COMMERCE_SERVICES = {
    # Commerce alimentaire
    "A101", "A104", "A105", "A106", "A107", "A108",
    # Grande distribution
    "A201", "A203", "A208",
    # Services aux particuliers
    "A301", "A302", "A303", "A304", "A401", "A402", "A404",
    # Santé
    "D101", "D106",  # médecin, pharmacie
    # Restauration
    "A501",
}


def _get_bpe_resource_url():
    """Récupère l'URL du dernier fichier BPE ensemble depuis l'API data.gouv.fr."""
    resp = requests.get(DATASET_URL, timeout=30)
    resp.raise_for_status()
    resources = resp.json().get("resources", [])
    # Chercher le fichier 'ensemble' le plus récent (CSV ou CSV.GZ)
    for r in sorted(resources, key=lambda x: x.get("created_at", ""), reverse=True):
        url = r.get("url", "")
        title = r.get("title", "").lower()
        if "ensemble" in title and (".csv" in url.lower() or "csv" in title):
            return url, r.get("created_at", "")[:4]  # URL + année
    raise ValueError("Fichier BPE 'ensemble' non trouvé dans le dataset data.gouv.fr")


def fetch_bpe_data(code_insee: str) -> dict:
    """
    Récupère le nombre de commerces et services de proximité pour une commune.

    Retourne :
    {
        "ok": bool,
        "lignes": [{"indicateur_id", "annee", "valeur", "source"}],
        "annees": [int],
        "erreurs": [str],
        "error": str,
    }
    """
    erreurs = []

    try:
        resource_url, annee_str = _get_bpe_resource_url()
        annee = int(annee_str) if annee_str.isdigit() else datetime.now().year
    except Exception as e:
        return {"ok": False, "error": f"BPE : impossible de récupérer l'URL du fichier : {e}",
                "lignes": [], "annees": [], "erreurs": []}

    try:
        resp = requests.get(resource_url, timeout=TIMEOUT, stream=True)
        resp.raise_for_status()
        content = resp.content

        # Décompresser si gzip
        if resource_url.endswith(".gz") or content[:2] == b"\x1f\x8b":
            content = gzip.decompress(content)

        # Lire le CSV et compter les équipements par commune
        reader = csv.DictReader(io.StringIO(content.decode("utf-8", errors="replace")), delimiter=";")
        nb_equip = 0
        for row in reader:
            depcom = row.get("DEPCOM", row.get("depcom", ""))
            typequ = row.get("TYPEQU", row.get("typequ", ""))
            if depcom == code_insee and typequ in TYPES_COMMERCE_SERVICES:
                # Certaines versions ont NB_EQUIP, d'autres une ligne par équipement
                nb = row.get("NB_EQUIP", row.get("nb_equip", "1"))
                try:
                    nb_equip += int(float(nb))
                except (ValueError, TypeError):
                    nb_equip += 1

    except requests.RequestException as e:
        return {"ok": False, "error": f"BPE : erreur de téléchargement : {e}",
                "lignes": [], "annees": [], "erreurs": []}
    except Exception as e:
        return {"ok": False, "error": f"BPE : erreur de traitement : {e}",
                "lignes": [], "annees": [], "erreurs": []}

    lignes = [{
        "indicateur_id": "eco2_nb_commerces",
        "annee": annee,
        "valeur": nb_equip,
        "source": SOURCE,
    }]

    return {
        "ok": True,
        "lignes": lignes,
        "annees": [annee],
        "erreurs": erreurs,
    }
