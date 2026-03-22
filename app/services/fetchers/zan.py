"""
Fetcher ZAN — Consommation d'espaces naturels, agricoles et forestiers (ENAF) par commune.

Source : data.gouv.fr — Cerema / Fichiers Fonciers (MAJIC/DGFIP)
  https://www.data.gouv.fr/datasets/consommation-despaces-naturels-agricoles-et-forestiers/

Données disponibles :
  - Consommation ENAF annuelle par commune et par secteur (ha), 2009–2023
  - Secteurs : Habitat, Activité, Route, Mixte, Fer, Inconnu

Calcul du quota ZAN 2021–2031 :
  - baseline = somme des consommations 2011–2020
  - quota = baseline / 2 (objectif : -50 % vs décennie précédente)
  - restant = quota - somme(consommation depuis 2021)
"""

import codecs
import csv

import requests

SOURCE = "Cerema — Fichiers Fonciers / data.gouv.fr"
TIMEOUT = 90

CSV_URL = (
    "https://static.data.gouv.fr/resources/"
    "consommation-despaces-naturels-agricoles-et-forestiers/"
    "20260128-170657/"
    "consommation-d-espaces-naturels-agricoles-et-forestiers-commune.csv"
)

IND_ANNUEL = "zan_conso_enaf_annuelle"
IND_QUOTA = "zan_quota_restant_2031"


def fetch_zan_data(code_insee: str) -> dict:
    """
    Streame le CSV ENAF (~170 Mo, ~15-20 s), filtre la commune,
    calcule la consommation annuelle et le quota ZAN restant.

    Retourne :
    {
        "ok": True,
        "lignes": [{"indicateur_id": str, "annee": int, "valeur": float, "source": str}],
        "annees": [int],
        "quota_total": float,
        "quota_restant": float,
        "erreurs": [str],
    }
    ou {"ok": False, "error": str}
    """
    try:
        resp = requests.get(
            CSV_URL,
            stream=True,
            headers={"Accept-Encoding": "gzip"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        resp.raw.decode_content = True
    except requests.exceptions.Timeout:
        return {"ok": False, "error": "Délai dépassé lors du téléchargement (>90 s)"}
    except Exception as e:
        return {"ok": False, "error": f"Erreur téléchargement : {e}"}

    # Utilise csv.DictReader via un wrapper text pour gérer correctement
    # les champs entre guillemets (libelle_commune peut contenir des virgules)
    reader = csv.DictReader(
        codecs.getreader("utf-8")(resp.raw, errors="replace")
    )

    # Agrégation : {annee_int: {secteur: valeur}}
    by_year: dict[int, dict[str, float]] = {}

    for row in reader:
        if row.get("geocode_commune", "").strip() != code_insee.strip():
            continue
        try:
            annee = int(row["date_mesure"][:4])
            secteur = row["secteur"]
            valeur = float(row["valeur"])
        except (ValueError, KeyError):
            continue
        if annee not in by_year:
            by_year[annee] = {}
        by_year[annee][secteur] = by_year[annee].get(secteur, 0.0) + valeur

    if not by_year:
        return {
            "ok": False,
            "error": f"Commune {code_insee} absente des Fichiers Fonciers Cerema",
        }

    # Construire les lignes pour zan_conso_enaf_annuelle (une par année)
    lignes = []
    for annee in sorted(by_year.keys()):
        secteurs = by_year[annee]
        total = sum(secteurs.values())
        if total == 0.0:
            continue
        detail = ", ".join(
            f"{s}: {v:.2f} ha"
            for s, v in sorted(secteurs.items())
            if v > 0
        )
        source_str = f"{SOURCE} — {detail}" if detail else SOURCE
        lignes.append({
            "indicateur_id": IND_ANNUEL,
            "annee": annee,
            "valeur": round(total, 4),
            "source": source_str,
        })

    # Calcul quota ZAN 2021-2031
    baseline = sum(
        sum(by_year[y].values())
        for y in by_year
        if 2011 <= y <= 2020
    )
    quota_total = round(baseline / 2, 4)
    conso_depuis_2021 = sum(
        sum(by_year[y].values())
        for y in by_year
        if y >= 2021
    )
    quota_restant = round(quota_total - conso_depuis_2021, 4)

    # Dernière année disponible pour stocker le quota restant
    derniere_annee = max(by_year.keys())
    lignes.append({
        "indicateur_id": IND_QUOTA,
        "annee": derniere_annee,
        "valeur": quota_restant,
        "source": (
            f"{SOURCE} — quota 2021-2031 : {quota_total} ha "
            f"(50 % de la baseline 2011-2020 : {round(baseline, 2)} ha), "
            f"consommé depuis 2021 : {round(conso_depuis_2021, 2)} ha"
        ),
    })

    annees = sorted({l["annee"] for l in lignes if l["indicateur_id"] == IND_ANNUEL}, reverse=True)
    return {
        "ok": True,
        "lignes": lignes,
        "annees": annees,
        "quota_total": quota_total,
        "quota_restant": quota_restant,
        "erreurs": [],
    }
