"""
Fetcher SRU — Inventaire officiel loi SRU (art. 55) par commune.

Source : data.gouv.fr — "Communes et inventaire SRU" (DGALN/Ministère du Logement)
  https://www.data.gouv.fr/datasets/communes-et-inventaire-sru

Données disponibles :
  - Taux SRU au 01/01/2022 (fichier édition 2023)
  - Taux SRU au 01/01/2023 (fichier mise à jour 2024)
  - Taux SRU au 01/01/2024 (fichier édition 2025)
  + Nb logements locatifs sociaux (inventaire SRU) pour chaque année

Note : seules les communes soumises à l'obligation SRU figurent dans ces fichiers.
"""

import csv
import io
import re
import requests

SOURCE = "Inventaire SRU — DGALN / data.gouv.fr"
TIMEOUT = 30

IND_TAUX = "log_taux_logements_sociaux"
IND_NB = "log_nb_logements_sociaux"

# Fichiers CSV disponibles : (url, délimiteur, lignes_à_sauter, année, col_taux, col_nb)
SRU_FILES = [
    (
        "https://static.data.gouv.fr/resources/communes-et-inventaire-sru/"
        "20251219-143258/donnees-sru-data-gouv-2025-v2.csv",
        ";", 0, 2024,
        "Taux_SRU_au_01_01_2024",
        "Nombre_lls_ Inventaire_au_01_01_2024",
    ),
    (
        "https://static.data.gouv.fr/resources/communes-et-inventaire-sru/"
        "20250929-132410/donnees-sru-data-gouv-maj2024-vf.csv",
        ",", 1, 2023,
        "Taux_SRU_au_01_01_2023",
        "Nombre_lls_ Inventaire_au_01_01_2023",
    ),
    (
        "https://static.data.gouv.fr/resources/communes-et-inventaire-sru/"
        "20250922-104633/donnees-sru-data-gouv-maj2023-vf.csv",
        ",", 0, 2022,
        "Taux_SRU_au_01_01_2022",
        "Nombre_lls_ Inventaire_au_01_01_2022",
    ),
]


def _parse_pct(val: str) -> float | None:
    """Convertit '16,78 %' ou '16,77%' en float 16.78."""
    if not val:
        return None
    cleaned = val.strip().rstrip("%").strip().replace(",", ".").replace("\xa0", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_int(val: str) -> float | None:
    """Convertit '625' ou '1 234' en float."""
    if not val:
        return None
    cleaned = re.sub(r"[\s\xa0]", "", val.strip())
    try:
        return float(cleaned)
    except ValueError:
        return None


def _fetch_file(url: str, delimiter: str, skip_rows: int,
                annee: int, col_taux: str, col_nb: str,
                code_insee: str) -> tuple:
    """
    Télécharge un fichier SRU et retourne (lignes, erreur_str | None).
    lignes = liste de dicts {indicateur_id, annee, valeur, source}
    """
    try:
        resp = requests.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        content = resp.content.decode("latin-1")
    except requests.exceptions.Timeout:
        return [], f"{annee}: délai dépassé"
    except Exception as e:
        return [], f"{annee}: erreur téléchargement — {e}"

    lines = content.splitlines()
    data = "\n".join(lines[skip_rows:])
    reader = csv.DictReader(io.StringIO(data), delimiter=delimiter)

    row = None
    for r in reader:
        if r.get("Code_INSEE_commune", "").strip() == code_insee.strip():
            row = r
            break

    if row is None:
        return [], f"{annee}: commune {code_insee} non soumise à la loi SRU (ou absente)"

    lignes = []

    taux = _parse_pct(row.get(col_taux, ""))
    if taux is not None:
        lignes.append({
            "indicateur_id": IND_TAUX,
            "annee": annee,
            "valeur": taux,
            "source": SOURCE,
        })

    nb = _parse_int(row.get(col_nb, ""))
    if nb is not None:
        lignes.append({
            "indicateur_id": IND_NB,
            "annee": annee,
            "valeur": nb,
            "source": SOURCE,
        })

    return lignes, None


def fetch_sru_data(code_insee: str) -> dict:
    """
    Récupère le taux SRU officiel et le nb de logements sociaux (inventaire SRU)
    pour une commune, sur les années disponibles (2022, 2023, 2024).

    Retourne :
    {
        "ok": True,
        "lignes": [{"indicateur_id": str, "annee": int, "valeur": float, "source": str}],
        "annees": [int],
        "erreurs": [str],
    }
    ou {"ok": False, "error": str}
    """
    lignes = []
    erreurs = []

    for url, delimiter, skip_rows, annee, col_taux, col_nb in SRU_FILES:
        file_lignes, err = _fetch_file(
            url, delimiter, skip_rows, annee, col_taux, col_nb, code_insee
        )
        lignes.extend(file_lignes)
        if err:
            erreurs.append(err)

    if not lignes:
        first_err = erreurs[0] if erreurs else "Commune non soumise à la loi SRU"
        return {"ok": False, "error": first_err}

    annees = sorted({l["annee"] for l in lignes}, reverse=True)
    return {
        "ok": True,
        "lignes": lignes,
        "annees": annees,
        "erreurs": erreurs,
    }
