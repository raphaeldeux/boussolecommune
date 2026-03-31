"""
Fetcher INSEE RP — API Melodi (open, sans authentification)
https://api.insee.fr/melodi

Datasets utilisés :
- DS_RP_POPULATION_PRINC : population par âge et sexe
- DS_RP_LOGEMENT_PRINC   : catégories, tenure, ancienneté du parc
- DS_RP_MENAGES_PRINC    : ménages et taille moyenne
- DS_RP_EMPLOI_LT_PRINC  : emplois sur la commune (lieu de travail)
- DS_RP_ACTIVITE_PRINC   : actifs résidents
"""

import requests

MELODI_URL = "https://api.insee.fr/melodi"
SOURCE = "INSEE RP"
TIMEOUT = 30

# Millésime RP le plus récent disponible dans Melodi (couvre 2011–2022)
RP_MILLESIME = "2022"

# Tranches d'âge Melodi → (code_age, indicateur_id, label_pyramide, ordre)
TRANCHES_AGE = [
    ("Y_LT15", "pop_age_lt15",  "<15 ans", 0),
    ("Y15T24", "pop_age_15_24", "15-24",   1),
    ("Y25T39", "pop_age_25_39", "25-39",   2),
    ("Y40T54", "pop_age_40_54", "40-54",   3),
    ("Y55T64", "pop_age_55_64", "55-64",   4),
    ("Y65T79", "pop_age_65_79", "65-79",   5),
    ("Y_GE80", "pop_age_ge80",  "80+",     6),
]


# ── Helpers Melodi ────────────────────────────────────────────────────────────

def _get_melodi(dataset: str, code_insee: str, extra_params: dict = None) -> list[dict]:
    """Appelle Melodi et retourne la liste d'observations."""
    params = {"GEO": f"COM-{code_insee}", "maxResult": 1000}
    if extra_params:
        params.update(extra_params)
    resp = requests.get(f"{MELODI_URL}/data/{dataset}", params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json().get("observations", [])


def _obs_value(obs: dict) -> float | None:
    """Extrait OBS_VALUE_NIVEAU.value d'une observation."""
    try:
        return obs["measures"]["OBS_VALUE_NIVEAU"]["value"]
    except (KeyError, TypeError):
        return None


def _filter_obs(obs_list: list[dict], **dims) -> list[dict]:
    """Filtre les observations selon les dimensions données.

    Note : Ne jamais filtrer sur GEO — la réponse Melodi préfixe GEO avec l'année
    ("2025-COM-44202") tandis que la requête envoie "COM-44202".
    Utiliser SEX, AGE, OCS, TSH, BUILD_END, COUPLE, etc.
    """
    result = []
    for obs in obs_list:
        if all(obs["dimensions"].get(k, {}).get("id") == v for k, v in dims.items()):
            result.append(obs)
    return result


# ── Fetcher principal ─────────────────────────────────────────────────────────

def fetch_insee_rp_data(code_insee: str) -> dict:
    """
    Récupère les données RP pour une commune via l'API Melodi (open).

    Retourne :
    {
        "ok": bool,
        "lignes": [{"indicateur_id": str, "annee": int, "valeur": float, "source": str}],
        "annees": [int],
        "pyramide": [{"annee": int, "tranches": [{"tranche": str, "ordre": int,
                                                   "hommes": int, "femmes": int}]}],
        "erreurs": [str],
        "error": str,  # présent seulement si ok=False
    }
    """
    lignes = []
    erreurs = []
    pyramide = []
    annee = int(RP_MILLESIME)
    pop_total = None

    # ── Population totale + structure par âge + pyramide ─────────────────────
    try:
        obs_pop = _get_melodi("DS_RP_POPULATION_PRINC", code_insee,
                              {"TIME_PERIOD": RP_MILLESIME})

        pop_obs = _filter_obs(obs_pop, SEX="_T", AGE="_T")
        if pop_obs:
            pop_total = _obs_value(pop_obs[0])
            if pop_total is not None:
                lignes.append({"indicateur_id": "pop_total", "annee": annee,
                                "valeur": pop_total, "source": SOURCE})

        if pop_total and pop_total > 0:
            tranches_pyramide = []
            for code_age, ind_id, label, ordre in TRANCHES_AGE:
                age_obs = _filter_obs(obs_pop, SEX="_T", AGE=code_age)
                if age_obs:
                    val = _obs_value(age_obs[0])
                    if val is not None:
                        pct = round(val / pop_total * 100, 1)
                        lignes.append({"indicateur_id": ind_id, "annee": annee,
                                        "valeur": pct, "source": SOURCE})
                h_obs = _filter_obs(obs_pop, SEX="M", AGE=code_age)
                f_obs = _filter_obs(obs_pop, SEX="F", AGE=code_age)
                hommes = int(_obs_value(h_obs[0]) or 0) if h_obs else 0
                femmes = int(_obs_value(f_obs[0]) or 0) if f_obs else 0
                tranches_pyramide.append({"tranche": label, "ordre": ordre,
                                          "hommes": hommes, "femmes": femmes})
            if tranches_pyramide:
                pyramide.append({"annee": annee, "tranches": tranches_pyramide})

    except requests.RequestException as e:
        return {"ok": False, "error": f"Erreur Melodi (population) : {e}",
                "lignes": [], "annees": [], "pyramide": [], "erreurs": []}
    except Exception as e:
        erreurs.append(f"population : {e}")

    # ── Évolution population (N vs N−10) ──────────────────────────────────────
    try:
        annee_prec = annee - 10
        obs_prec = _get_melodi("DS_RP_POPULATION_PRINC", code_insee,
                               {"TIME_PERIOD": str(annee_prec)})
        pop_prec_obs = _filter_obs(obs_prec, SEX="_T", AGE="_T")
        if pop_prec_obs and pop_total:
            pop_prec = _obs_value(pop_prec_obs[0])
            if pop_prec and pop_prec > 0:
                evolution = round((pop_total - pop_prec) / pop_prec * 100, 1)
                lignes.append({"indicateur_id": "pop_evolution_10ans", "annee": annee,
                                "valeur": evolution, "source": SOURCE})
    except Exception as e:
        erreurs.append(f"évolution population : {e}")

    # ── Logements ─────────────────────────────────────────────────────────────
    try:
        obs_log = _get_melodi("DS_RP_LOGEMENT_PRINC", code_insee,
                              {"TIME_PERIOD": RP_MILLESIME})

        # Catégories (OCS)
        total_log_obs = _filter_obs(obs_log, OCS="_T")
        total_log = _obs_value(total_log_obs[0]) if total_log_obs else None

        if total_log and total_log > 0:
            vac_obs = _filter_obs(obs_log, OCS="DW_VAC")
            if vac_obs:
                nb_vac = _obs_value(vac_obs[0])
                if nb_vac is not None:
                    lignes.append({"indicateur_id": "log_vacants_taux", "annee": annee,
                                    "valeur": round(nb_vac / total_log * 100, 1), "source": SOURCE})

            # Résidences secondaires — essayer les deux codes possibles
            for sec_code in ("DW_SEC_DW_OCC", "DW_SEC"):
                sec_obs = _filter_obs(obs_log, OCS=sec_code)
                if sec_obs:
                    nb_sec = _obs_value(sec_obs[0])
                    if nb_sec is not None:
                        lignes.append({"indicateur_id": "log_residences_secondaires_taux",
                                        "annee": annee,
                                        "valeur": round(nb_sec / total_log * 100, 1),
                                        "source": SOURCE})
                    break

        # Propriétaires (dimension TSH — codes à découvrir à l'exécution)
        tsh_codes = {o["dimensions"]["TSH"]["id"]
                     for o in obs_log if "TSH" in o["dimensions"]}
        total_tsh_obs = _filter_obs(obs_log, TSH="_T")
        total_tsh = _obs_value(total_tsh_obs[0]) if total_tsh_obs else None
        if total_tsh and total_tsh > 0:
            for owner_code in ("OWNER", "10", "OWN", "OWNER_OCC"):
                prop_obs = _filter_obs(obs_log, TSH=owner_code)
                if prop_obs:
                    nb_prop = _obs_value(prop_obs[0])
                    if nb_prop is not None:
                        lignes.append({"indicateur_id": "log_proprietaires_taux", "annee": annee,
                                        "valeur": round(nb_prop / total_tsh * 100, 1),
                                        "source": SOURCE})
                    break
            else:
                erreurs.append(f"propriétaires : codes TSH disponibles = {tsh_codes}")

        # Ancienneté du parc (dimension BUILD_END)
        build_codes = {o["dimensions"]["BUILD_END"]["id"]
                       for o in obs_log
                       if "BUILD_END" in o["dimensions"]
                       and o["dimensions"]["BUILD_END"]["id"] != "_T"}
        total_build_obs = _filter_obs(obs_log, BUILD_END="_T")
        total_build = _obs_value(total_build_obs[0]) if total_build_obs else None

        if total_build and total_build > 0 and build_codes:
            av1946 = [c for c in build_codes
                      if any(x in c for x in ("LT1919", "LT1946", "1919T1945", "Y1919", "Y1945"))]
            codes_1946_1990 = [c for c in build_codes
                                if any(x in c for x in ("1946", "1970", "1971", "1990"))
                                and c not in av1946]
            post1990 = [c for c in build_codes
                        if any(x in c for x in ("1991", "2005", "2006", "GT1990", "GE1991"))
                        and c not in av1946 and c not in codes_1946_1990]

            def _sum_build(codes):
                total = 0
                for c in codes:
                    obs = _filter_obs(obs_log, BUILD_END=c)
                    if obs:
                        total += _obs_value(obs[0]) or 0
                return total

            nb_av = _sum_build(av1946)
            nb_mid = _sum_build(codes_1946_1990)
            nb_post = _sum_build(post1990)
            total_connu = nb_av + nb_mid + nb_post

            if total_connu > 0:
                lignes.append({"indicateur_id": "log_anciennete_avant1946", "annee": annee,
                                "valeur": round(nb_av / total_connu * 100, 1), "source": SOURCE})
                lignes.append({"indicateur_id": "log_anciennete_1946_1990", "annee": annee,
                                "valeur": round(nb_mid / total_connu * 100, 1), "source": SOURCE})
                lignes.append({"indicateur_id": "log_anciennete_post1990", "annee": annee,
                                "valeur": round(nb_post / total_connu * 100, 1), "source": SOURCE})
            else:
                erreurs.append(f"ancienneté : codes BUILD_END disponibles = {build_codes}")

    except Exception as e:
        erreurs.append(f"logements : {e}")

    # ── Ménages ────────────────────────────────────────────────────────────────
    try:
        obs_men = _get_melodi("DS_RP_MENAGES_PRINC", code_insee,
                              {"TIME_PERIOD": RP_MILLESIME})

        # Total ménages : observation avec toutes les dimensions à _T
        total_men_obs = [
            o for o in obs_men
            if all(o["dimensions"].get(d, {}).get("id") == "_T"
                   for d in o["dimensions"] if d != "GEO" and d != "TIME_PERIOD" and d != "FREQ")
        ]
        nb_men_total = _obs_value(total_men_obs[0]) if total_men_obs else None

        if nb_men_total and nb_men_total > 0:
            if pop_total:
                lignes.append({"indicateur_id": "pop_taille_menages", "annee": annee,
                                "valeur": round(pop_total / nb_men_total, 2), "source": SOURCE})

            # Ménages d'une seule personne (COUPLE=0, AGE=_T)
            solo_obs = _filter_obs(obs_men, COUPLE="0", AGE="_T")
            if not solo_obs:
                # Fallback : tous COUPLE=0 à tous âges
                solo_all = _filter_obs(obs_men, COUPLE="0")
                nb_solo = sum(_obs_value(o) or 0 for o in solo_all
                              if o["dimensions"].get("AGE", {}).get("id") == "_T")
            else:
                nb_solo = sum(_obs_value(o) or 0 for o in solo_obs)

            if nb_solo > 0:
                lignes.append({"indicateur_id": "pop_menages_solo", "annee": annee,
                                "valeur": round(nb_solo / nb_men_total * 100, 1), "source": SOURCE})
            else:
                erreurs.append("ménages solo : dimension COUPLE non résolue")

    except Exception as e:
        erreurs.append(f"ménages : {e}")

    # ── Emplois ────────────────────────────────────────────────────────────────
    try:
        obs_emp = _get_melodi("DS_RP_EMPLOI_LT_PRINC", code_insee,
                              {"TIME_PERIOD": RP_MILLESIME})
        # Chercher le total : SEX=_T ou première observation si pas de dimension SEX
        emp_total_obs = _filter_obs(obs_emp, SEX="_T") or obs_emp
        nb_emplois = _obs_value(emp_total_obs[0]) if emp_total_obs else None

        if nb_emplois is not None:
            lignes.append({"indicateur_id": "eco2_emplois_commune", "annee": annee,
                            "valeur": nb_emplois, "source": SOURCE})

        obs_act = _get_melodi("DS_RP_ACTIVITE_PRINC", code_insee,
                              {"TIME_PERIOD": RP_MILLESIME})
        act_total_obs = _filter_obs(obs_act, SEX="_T") or obs_act
        nb_actifs = _obs_value(act_total_obs[0]) if act_total_obs else None

        if nb_emplois and nb_actifs and nb_actifs > 0:
            lignes.append({"indicateur_id": "eco_emplois_actifs_ratio", "annee": annee,
                            "valeur": round(nb_emplois / nb_actifs, 2), "source": SOURCE})

    except Exception as e:
        erreurs.append(f"emplois : {e}")

    annees = list({l["annee"] for l in lignes}) if lignes else []

    return {
        "ok": True,
        "lignes": lignes,
        "annees": sorted(annees, reverse=True),
        "pyramide": pyramide,
        "erreurs": erreurs,
    }
