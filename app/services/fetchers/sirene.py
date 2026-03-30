"""
Fetcher SIRENE v3 — Entreprises et associations
https://api.insee.fr/entreprises/sirene/V3/

Authentification : même OAuth2 que l'API Données locales INSEE (INSEE_API_KEY)
"""

import os
import base64
import requests
from datetime import datetime

BASE_URL = "https://api.insee.fr/entreprises/sirene/V3"
TOKEN_URL = "https://api.insee.fr/token"
SOURCE = "SIRENE INSEE"
TIMEOUT = 30
MAX_RESULTS = 10000  # limite par requête SIRENE


def _get_bearer_token(api_key: str):
    if not api_key or ":" not in api_key:
        raise ValueError(
            "INSEE_API_KEY non configurée. Format : 'consumer_key:consumer_secret'. "
            "Inscription gratuite sur https://api.insee.fr/catalogue/"
        )
    credentials = base64.b64encode(api_key.encode()).decode()
    resp = requests.post(
        TOKEN_URL,
        headers={"Authorization": f"Basic {credentials}",
                 "Content-Type": "application/x-www-form-urlencoded"},
        data="grant_type=client_credentials",
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _count_sirets(token, query):
    """Compte le nombre d'établissements correspondant à une requête SIRENE."""
    resp = requests.get(
        f"{BASE_URL}/siret",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": query, "nombre": 1, "champs": "siret"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("header", {}).get("total", 0)


def fetch_sirene_data(code_insee: str, api_key: str = None) -> dict:
    """
    Récupère les données SIRENE pour une commune.

    Retourne :
    {
        "ok": bool,
        "lignes": [{"indicateur_id", "annee", "valeur", "source"}],
        "annees": [int],
        "erreurs": [str],
        "error": str,
    }
    """
    lignes = []
    erreurs = []
    annee = datetime.now().year

    resolved_key = (api_key or "").strip() or os.environ.get("INSEE_API_KEY", "")

    try:
        token = _get_bearer_token(resolved_key)
    except (ValueError, requests.RequestException) as e:
        return {"ok": False, "error": str(e), "lignes": [], "annees": [], "erreurs": []}

    # Base commune SIRENE : le champ est codePostalEtablissement ou communeImplantationEtablissement
    # selon la version. Utiliser codeCommune (5 chiffres) avec le siège social actif.
    base_query = (
        f"etablissementSiege:true "
        f"AND etatAdministratifEtablissement:A "
        f"AND codeCommuneEtablissement:{code_insee}"
    )

    # ── Entreprises actives (hors associations) ────────────────────────────────
    try:
        query_entreprises = base_query + " AND -categorieJuridiqueUniteLegale:92*"
        nb_entreprises = _count_sirets(token, query_entreprises)
        lignes.append({
            "indicateur_id": "eco2_evolution_entreprises",
            "annee": annee,
            "valeur": nb_entreprises,
            "source": SOURCE,
        })
    except requests.RequestException as e:
        erreurs.append(f"entreprises : {e}")

    # ── Associations actives (catégorie juridique 92xx) ────────────────────────
    try:
        query_associations = base_query + " AND categorieJuridiqueUniteLegale:92*"
        nb_associations = _count_sirets(token, query_associations)
        lignes.append({
            "indicateur_id": "soc_associations_nb",
            "annee": annee,
            "valeur": nb_associations,
            "source": SOURCE,
        })
    except requests.RequestException as e:
        erreurs.append(f"associations : {e}")

    annees = [annee] if lignes else []

    return {
        "ok": bool(lignes),
        "lignes": lignes,
        "annees": annees,
        "erreurs": erreurs,
    }
