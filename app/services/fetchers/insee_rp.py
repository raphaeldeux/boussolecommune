"""
Fetcher INSEE — Recensement de la Population (RP)
Utilise l'API Données locales INSEE (https://api.insee.fr)

Authentification : OAuth2 Bearer Token
Variable d'env : INSEE_API_KEY = "consumer_key:consumer_secret"

Pour obtenir une clé gratuite :
  https://portail-api.insee.fr/ → Créer une application → Abonner à "Données locales"
"""

import os
import base64
import requests
from datetime import datetime

BASE_URL = "https://api.insee.fr"
TOKEN_URL = f"{BASE_URL}/token"
DONNEES_URL = f"{BASE_URL}/donnees-locales/V0.1/donnees"
SOURCE = "INSEE RP"
TIMEOUT = 30

# Millésime RP le plus récent disponible (mettre à jour annuellement)
RP_MILLESIME = "2021"

# Tranches d'âge RP → correspondance tranche INSEE → (indicateur_id, tranche pyramide, ordre)
TRANCHES_AGE = [
    # (code_modalite_insee, indicateur_id, tranche_pyramide, ordre_pyramide)
    # À ajuster selon les modalités réelles de l'API
    ("0-14",  "pop_age_0_14",  "0-14",  0),
    ("15-29", "pop_age_15_29", "15-29", 1),
    ("30-44", "pop_age_30_44", "30-44", 2),
    ("45-59", "pop_age_45_59", "45-59", 3),
    ("60-74", "pop_age_60_74", "60-74", 4),
    ("75-89", "pop_age_75_89", "75-89", 5),
    ("90+",   "pop_age_90_plus", "90+", 6),
]


def _get_bearer_token(api_key: str):
    """Obtient un Bearer token OAuth2 depuis l'API INSEE."""
    if not api_key or ":" not in api_key:
        raise ValueError(
            "INSEE_API_KEY non configurée. Format attendu : 'consumer_key:consumer_secret'. "
            "Inscription gratuite sur https://portail-api.insee.fr/"
        )
    credentials = base64.b64encode(api_key.encode()).decode()
    resp = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data="grant_type=client_credentials",
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _get_cube(token, cube_ref, code_insee):
    """Appelle l'API Données locales pour un cube donné."""
    url = f"{DONNEES_URL}/{cube_ref}/COM/{code_insee}"
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_insee_rp_data(code_insee: str, api_key: str = None) -> dict:
    """
    Récupère les données RP pour une commune.

    Retourne :
    {
        "ok": bool,
        "lignes": [{"indicateur_id": str, "annee": int, "valeur": float, "source": str}],
        "annees": [int],
        "pyramide": [{"annee": int, "tranches": [{"tranche": str, "ordre": int, "hommes": int, "femmes": int}]}],
        "erreurs": [str],
        "error": str,  # présent seulement si ok=False
    }
    """
    lignes = []
    erreurs = []
    pyramide = []
    annee = int(RP_MILLESIME)
    pop_total = None

    resolved_key = (api_key or "").strip() or os.environ.get("INSEE_API_KEY", "")

    try:
        token = _get_bearer_token(resolved_key)
    except ValueError as e:
        return {"ok": False, "error": str(e), "lignes": [], "annees": [], "pyramide": [], "erreurs": []}
    except requests.RequestException as e:
        return {"ok": False, "error": f"Erreur d'authentification INSEE : {e}", "lignes": [], "annees": [], "pyramide": [], "erreurs": []}

    # ── Population totale ──────────────────────────────────────────────────────
    try:
        data = _get_cube(token, f"geo-SEXE-AGE10@RP_POP_{RP_MILLESIME}", code_insee)
        pop_total = _extraire_total(data)
        if pop_total is not None:
            lignes.append({"indicateur_id": "pop_total", "annee": annee, "valeur": pop_total, "source": SOURCE})
    except Exception as e:
        erreurs.append(f"population : {e}")

    # ── Structure par âge + pyramide ───────────────────────────────────────────
    try:
        data_age = _get_cube(token, f"geo-SEXE-AGE10@RP_POP_{RP_MILLESIME}", code_insee)
        tranches_pyramide = []
        for code_tranche, ind_id, tranche_label, ordre in TRANCHES_AGE:
            hommes, femmes = _extraire_tranche(data_age, code_tranche)
            total_tranche = hommes + femmes
            if pop_total and pop_total > 0:
                pct = round(total_tranche / pop_total * 100, 1)
                lignes.append({"indicateur_id": ind_id, "annee": annee, "valeur": pct, "source": SOURCE})
            tranches_pyramide.append({"tranche": tranche_label, "ordre": ordre, "hommes": hommes, "femmes": femmes})
        if tranches_pyramide:
            pyramide.append({"annee": annee, "tranches": tranches_pyramide})
    except Exception as e:
        erreurs.append(f"structure par âge : {e}")

    # ── Logements ─────────────────────────────────────────────────────────────
    try:
        data_log = _get_cube(token, f"geo-CATL@RP_LOGEMENT_{RP_MILLESIME}", code_insee)
        # CATL : 1=RP, 2=RS, 3=logement vacant, 4=autre résidence
        nb_rp = _extraire_modalite(data_log, "1")
        nb_rs = _extraire_modalite(data_log, "2")
        nb_vac = _extraire_modalite(data_log, "3")
        nb_total = (nb_rp or 0) + (nb_rs or 0) + (nb_vac or 0)
        if nb_total > 0:
            if nb_vac is not None:
                lignes.append({"indicateur_id": "log_vacants_taux", "annee": annee,
                                "valeur": round(nb_vac / nb_total * 100, 1), "source": SOURCE})
            if nb_rs is not None:
                lignes.append({"indicateur_id": "log_residences_secondaires_taux", "annee": annee,
                                "valeur": round(nb_rs / nb_total * 100, 1), "source": SOURCE})
    except Exception as e:
        erreurs.append(f"logements (catégorie) : {e}")

    # ── Tenure (propriétaires/locataires) ─────────────────────────────────────
    try:
        data_stocd = _get_cube(token, f"geo-STOCD@RP_LOGEMENT_{RP_MILLESIME}", code_insee)
        # STOCD : 10=proprio, 20=locataire privé, 21=locataire HLM, 30=logé gratuitement
        nb_proprio = _extraire_modalite(data_stocd, "10")
        nb_rp_total = _extraire_total(data_stocd)
        if nb_proprio and nb_rp_total:
            lignes.append({"indicateur_id": "log_proprietaires_taux", "annee": annee,
                            "valeur": round(nb_proprio / nb_rp_total * 100, 1), "source": SOURCE})
    except Exception as e:
        erreurs.append(f"tenure : {e}")

    # ── Ancienneté du parc ─────────────────────────────────────────────────────
    try:
        data_ancons = _get_cube(token, f"geo-ANCONS@RP_LOGEMENT_{RP_MILLESIME}", code_insee)
        # ANCONS : 1=avant 1919, 2=1919-1945, 3=1946-1970, 4=1971-1990, 5=1991-2005, 6=2006-2011, 7=après 2011
        nb_av1946 = (_extraire_modalite(data_ancons, "1") or 0) + (_extraire_modalite(data_ancons, "2") or 0)
        nb_1946_1990 = (_extraire_modalite(data_ancons, "3") or 0) + (_extraire_modalite(data_ancons, "4") or 0)
        nb_post1990 = sum(_extraire_modalite(data_ancons, str(i)) or 0 for i in range(5, 8))
        nb_total_ancons = nb_av1946 + nb_1946_1990 + nb_post1990
        if nb_total_ancons > 0:
            lignes.append({"indicateur_id": "log_anciennete_avant1946", "annee": annee,
                            "valeur": round(nb_av1946 / nb_total_ancons * 100, 1), "source": SOURCE})
            lignes.append({"indicateur_id": "log_anciennete_1946_1990", "annee": annee,
                            "valeur": round(nb_1946_1990 / nb_total_ancons * 100, 1), "source": SOURCE})
            lignes.append({"indicateur_id": "log_anciennete_post1990", "annee": annee,
                            "valeur": round(nb_post1990 / nb_total_ancons * 100, 1), "source": SOURCE})
    except Exception as e:
        erreurs.append(f"ancienneté parc : {e}")

    # ── Ménages ────────────────────────────────────────────────────────────────
    try:
        data_men = _get_cube(token, f"geo-TYPMR@RP_MENAGES_{RP_MILLESIME}", code_insee)
        # TYPMR : 11=personne seule, ... (voir catalogue)
        nb_solo = _extraire_modalite(data_men, "11")
        nb_men_total = _extraire_total(data_men)
        if nb_solo and nb_men_total:
            lignes.append({"indicateur_id": "pop_menages_solo", "annee": annee,
                            "valeur": round(nb_solo / nb_men_total * 100, 1), "source": SOURCE})
        # Taille moyenne : pop / nb ménages (approximation)
        if pop_total and nb_men_total:
            lignes.append({"indicateur_id": "pop_taille_menages", "annee": annee,
                            "valeur": round(pop_total / nb_men_total, 2), "source": SOURCE})
    except Exception as e:
        erreurs.append(f"ménages : {e}")

    # ── Emplois ────────────────────────────────────────────────────────────────
    try:
        data_emp = _get_cube(token, f"geo-TACT@RP_ACT_{RP_MILLESIME}", code_insee)
        # TACT : 11=actif occupé résident, ... (emplois sur commune via cube emplois)
        nb_actifs = _extraire_modalite(data_emp, "11")
        # Note : emplois SUR la commune nécessite un cube différent (RP_EMP)
        data_emplois = _get_cube(token, f"geo-TACT@RP_EMP_{RP_MILLESIME}", code_insee)
        nb_emplois = _extraire_total(data_emplois)
        if nb_actifs and nb_emplois and nb_actifs > 0:
            lignes.append({"indicateur_id": "eco_emplois_actifs_ratio", "annee": annee,
                            "valeur": round(nb_emplois / nb_actifs, 2), "source": SOURCE})
        if nb_emplois:
            lignes.append({"indicateur_id": "eco2_emplois_commune", "annee": annee,
                            "valeur": nb_emplois, "source": SOURCE})
    except Exception as e:
        erreurs.append(f"emplois : {e}")

    # ── Évolution population ───────────────────────────────────────────────────
    try:
        # Millésime précédent (N-10 ans)
        annee_prec = annee - 10
        millesime_prec = str(annee_prec)
        data_prec = _get_cube(token, f"geo-SEXE-AGE10@RP_POP_{millesime_prec}", code_insee)
        pop_prec = _extraire_total(data_prec)
        if pop_prec and pop_total and pop_prec > 0:
            evolution = round((pop_total - pop_prec) / pop_prec * 100, 1)
            lignes.append({"indicateur_id": "pop_evolution_10ans", "annee": annee,
                            "valeur": evolution, "source": SOURCE})
    except Exception as e:
        erreurs.append(f"évolution population : {e}")

    annees = list({l["annee"] for l in lignes}) if lignes else []

    return {
        "ok": True,
        "lignes": lignes,
        "annees": sorted(annees, reverse=True),
        "pyramide": pyramide,
        "erreurs": erreurs,
    }


# ── Helpers pour parser les réponses JSON de l'API Données locales ────────────

def _extraire_total(data):
    """Extrait la valeur totale d'une réponse cube INSEE."""
    # La structure de réponse JSON de l'API Données locales INSEE est :
    # {"Cellule": [{"Modalite": [{"@variable": "VAR", "@code": "code"}], "Valeur": "123"}]}
    try:
        total = 0
        for cellule in data.get("Cellule", []):
            val = cellule.get("Valeur", "0")
            total += int(float(val.replace(" ", "")))
        return total if total > 0 else None
    except Exception:
        return None


def _extraire_modalite(data, code):
    """Extrait la valeur pour une modalité spécifique."""
    try:
        for cellule in data.get("Cellule", []):
            for mod in cellule.get("Modalite", []):
                if mod.get("@code") == code:
                    val = cellule.get("Valeur", "0")
                    return int(float(val.replace(" ", "")))
        return None
    except Exception:
        return None


def _extraire_tranche(data, tranche):
    """Extrait hommes et femmes pour une tranche d'âge."""
    hommes = 0
    femmes = 0
    try:
        for cellule in data.get("Cellule", []):
            modalites = {m.get("@variable"): m.get("@code") for m in cellule.get("Modalite", [])}
            # Adapter les noms de variables selon la réponse réelle de l'API
            if modalites.get("AGE10") == tranche or modalites.get("AGEPYR5") == tranche:
                val = int(float(cellule.get("Valeur", "0").replace(" ", "")))
                sexe = modalites.get("SEXE", "")
                if sexe == "1":  # 1 = Hommes
                    hommes += val
                elif sexe == "2":  # 2 = Femmes
                    femmes += val
    except Exception:
        pass
    return hommes, femmes
