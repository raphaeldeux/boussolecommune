"""
Initialise le référentiel des ~40 indicateurs.
Idempotent : n'écrase pas les indicateurs existants.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from app.database import init_db, get_db

INDICATEURS = [
    # ─── Finances publiques ───────────────────────────────────────────────────
    {
        "id": "fin_epargne_brute",
        "thematique": "finances",
        "libelle_citoyen": "La commune met-elle de l'argent de côté ?",
        "libelle_technique": "Taux d'épargne brute",
        "unite": "% recettes",
        "sens_positif": "haut",
        "seuil_vert": 15.0,
        "seuil_orange": 8.0,
        "seuil_rouge": 3.0,
        "valeur_reference": 13.5,
        "libelle_reference": "Médiane communes 5k–10k hab. (OFGL 2023)",
        "description": "L'épargne brute représente la part des recettes de fonctionnement "
                       "qui reste disponible après paiement des dépenses de fonctionnement. "
                       "C'est la « capacité d'autofinancement » de la commune : plus elle est "
                       "élevée, plus la commune peut investir sans s'endetter.",
        "source_type": "csv_ofgl",
    },
    {
        "id": "fin_dette_habitant",
        "thematique": "finances",
        "libelle_citoyen": "Combien la commune doit-elle par habitant ?",
        "libelle_technique": "Encours de dette par habitant",
        "unite": "€/hab",
        "sens_positif": "bas",
        "seuil_vert": 800.0,
        "seuil_orange": 1200.0,
        "seuil_rouge": 1800.0,
        "valeur_reference": 1050.0,
        "libelle_reference": "Médiane communes 5k–10k hab. (OFGL 2023)",
        "description": "Le montant total de la dette divisé par le nombre d'habitants. "
                       "Cet indicateur permet de comparer l'endettement de Sautron avec "
                       "des communes de même taille. Une dette élevée peut limiter la "
                       "capacité d'investissement future.",
        "source_type": "csv_ofgl",
    },
    {
        "id": "fin_capacite_desendettement",
        "thematique": "finances",
        "libelle_citoyen": "En combien d'années pourrait-elle rembourser sa dette ?",
        "libelle_technique": "Capacité de désendettement",
        "unite": "années",
        "sens_positif": "bas",
        "seuil_vert": 5.0,
        "seuil_orange": 8.0,
        "seuil_rouge": 12.0,
        "valeur_reference": 7.0,
        "libelle_reference": "Seuil d'alerte Préfecture (12 ans)",
        "description": "Nombre d'années nécessaires pour rembourser l'intégralité de la "
                       "dette si l'épargne brute y était entièrement consacrée. En dessous "
                       "de 12 ans, la situation est considérée comme saine par les services "
                       "de l'État.",
        "source_type": "csv_ofgl",
    },
    {
        "id": "fin_investissement_habitant",
        "thematique": "finances",
        "libelle_citoyen": "Combien investit-on par habitant chaque année ?",
        "libelle_technique": "Dépenses d'investissement par habitant",
        "unite": "€/hab",
        "sens_positif": "haut",
        "seuil_vert": 350.0,
        "seuil_orange": 200.0,
        "seuil_rouge": 100.0,
        "valeur_reference": 280.0,
        "libelle_reference": "Médiane communes 5k–10k hab. (OFGL 2023)",
        "description": "Les dépenses d'investissement financent les équipements et "
                       "infrastructures de la commune : routes, bâtiments, équipements "
                       "sportifs… Un niveau élevé traduit une politique volontariste "
                       "d'amélioration du cadre de vie.",
        "source_type": "csv_ofgl",
    },
    {
        "id": "fin_rigidite_charges",
        "thematique": "finances",
        "libelle_citoyen": "Quelle part du budget est impossible à réduire rapidement ?",
        "libelle_technique": "Taux de rigidité des charges",
        "unite": "%",
        "sens_positif": "bas",
        "seuil_vert": 55.0,
        "seuil_orange": 65.0,
        "seuil_rouge": 75.0,
        "valeur_reference": 62.0,
        "libelle_reference": "Médiane communes 5k–10k hab. (OFGL 2023)",
        "description": "Somme des charges de personnel et des annuités de dette, rapportée "
                       "aux recettes de fonctionnement. Ces charges sont dites « rigides » "
                       "car elles ne peuvent pas être réduites rapidement. Un ratio élevé "
                       "réduit les marges de manœuvre budgétaires.",
        "source_type": "csv_ofgl",
    },
    {
        "id": "fin_taux_taxe_fonciere",
        "thematique": "finances",
        "libelle_citoyen": "Quel est le taux de la taxe foncière ?",
        "libelle_technique": "Taux de taxe foncière sur les propriétés bâties",
        "unite": "%",
        "sens_positif": "bas",
        "seuil_vert": 20.0,
        "seuil_orange": 28.0,
        "seuil_rouge": 35.0,
        "valeur_reference": 26.5,
        "libelle_reference": "Taux moyen communes 5k–10k hab. (DGFIP 2023)",
        "description": "Le taux voté par le conseil municipal, appliqué à la valeur "
                       "cadastrale de chaque propriété. C'est le principal levier fiscal "
                       "des communes depuis la suppression de la taxe d'habitation.",
        "source_type": "saisie_manuelle",
    },
    {
        "id": "fin_masse_salariale_ratio",
        "thematique": "finances",
        "libelle_citoyen": "Quelle part du budget part aux salaires des agents ?",
        "libelle_technique": "Charges de personnel / dépenses de fonctionnement",
        "unite": "% dép. fonct.",
        "sens_positif": "bas",
        "seuil_vert": 45.0,
        "seuil_orange": 55.0,
        "seuil_rouge": 65.0,
        "valeur_reference": 52.0,
        "libelle_reference": "Médiane communes 5k–10k hab. (OFGL 2023)",
        "description": "Part des dépenses de fonctionnement consacrée aux salaires et "
                       "charges sociales des agents municipaux. Un ratio élevé peut "
                       "signifier une politique de services publics ambitieuse, mais "
                       "aussi des rigidités budgétaires.",
        "source_type": "csv_ofgl",
    },

    # ─── Écologie & environnement ─────────────────────────────────────────────
    {
        "id": "eco_espaces_verts_habitant",
        "thematique": "ecologie",
        "libelle_citoyen": "Quelle surface d'espaces verts par habitant ?",
        "libelle_technique": "Surface d'espaces verts par habitant",
        "unite": "m²/hab",
        "sens_positif": "haut",
        "seuil_vert": 30.0,
        "seuil_orange": 15.0,
        "seuil_rouge": 5.0,
        "valeur_reference": 20.0,
        "libelle_reference": "Recommandation OMS (10 m²/hab minimum)",
        "description": "Surface totale des espaces verts publics gérés par la commune "
                       "(parcs, jardins, squares) divisée par le nombre d'habitants. "
                       "L'OMS recommande un minimum de 10 m² par habitant.",
        "source_type": "saisie_manuelle",
    },
    {
        "id": "eco_fluides_global",
        "thematique": "ecologie",
        "libelle_citoyen": "Combien la commune dépense-t-elle en eau et énergie ?",
        "libelle_technique": "Dépenses eau + énergie des bâtiments communaux",
        "unite": "€/an",
        "sens_positif": "bas",
        "seuil_vert": None,
        "seuil_orange": None,
        "seuil_rouge": None,
        "valeur_reference": None,
        "libelle_reference": None,
        "description": "Total des factures d'eau, électricité et chauffage des bâtiments "
                       "publics communaux. Cet indicateur permet de suivre les économies "
                       "réalisées grâce aux travaux de rénovation énergétique.",
        "source_type": "csv_generique",
    },
    {
        "id": "eco_dpe_batiments",
        "thematique": "ecologie",
        "libelle_citoyen": "Quelle est la performance énergétique des bâtiments communaux ?",
        "libelle_technique": "DPE moyen des bâtiments communaux",
        "unite": "score 1–7",
        "sens_positif": "haut",
        "seuil_vert": 5.0,
        "seuil_orange": 3.0,
        "seuil_rouge": 2.0,
        "valeur_reference": 3.0,
        "libelle_reference": "Score C (5) = objectif décret tertiaire 2030",
        "description": "Score moyen des diagnostics de performance énergétique des "
                       "bâtiments communaux (1=G très énergivore à 7=A très performant). "
                       "Le décret tertiaire impose de réduire la consommation énergétique "
                       "des bâtiments publics de 40% d'ici 2030.",
        "source_type": "csv_generique",
    },
    {
        "id": "eco_dechets_habitant",
        "thematique": "ecologie",
        "libelle_citoyen": "Combien de déchets produit-on par habitant ?",
        "libelle_technique": "Production de déchets ménagers par habitant",
        "unite": "kg/hab/an",
        "sens_positif": "bas",
        "seuil_vert": 380.0,
        "seuil_orange": 450.0,
        "seuil_rouge": 550.0,
        "valeur_reference": 430.0,
        "libelle_reference": "Moyenne nationale (ADEME 2022)",
        "description": "Poids total des déchets ménagers collectés (ordures ménagères + "
                       "recyclables + encombrants) divisé par le nombre d'habitants. "
                       "La moyenne nationale est d'environ 430 kg/hab/an.",
        "source_type": "csv_generique",
    },
    {
        "id": "eco_taux_tri",
        "thematique": "ecologie",
        "libelle_citoyen": "Quelle part des déchets est triée et recyclée ?",
        "libelle_technique": "Taux de tri sélectif",
        "unite": "%",
        "sens_positif": "haut",
        "seuil_vert": 70.0,
        "seuil_orange": 50.0,
        "seuil_rouge": 35.0,
        "valeur_reference": 58.0,
        "libelle_reference": "Moyenne Nantes Métropole (2022)",
        "description": "Part des déchets orientés vers les filières de recyclage ou de "
                       "valorisation, par rapport au total des déchets collectés. Un taux "
                       "élevé traduit à la fois de bonnes pratiques citoyennes et une "
                       "politique de collecte efficace.",
        "source_type": "csv_generique",
    },
    {
        "id": "eco_part_bio_cantine",
        "thematique": "ecologie",
        "libelle_citoyen": "Quelle part du bio et local à la cantine scolaire ?",
        "libelle_technique": "Part des produits bio et locaux en restauration collective",
        "unite": "%",
        "sens_positif": "haut",
        "seuil_vert": 50.0,
        "seuil_orange": 35.0,
        "seuil_rouge": 20.0,
        "valeur_reference": 50.0,
        "libelle_reference": "Objectif loi EGAlim (50% bio+local dès 2022)",
        "description": "Part des achats alimentaires de la restauration collective "
                       "provenant de l'agriculture biologique ou de circuits courts locaux. "
                       "La loi EGAlim de 2018 impose 50% de produits durables dont 20% bio "
                       "depuis le 1er janvier 2022.",
        "source_type": "saisie_manuelle",
    },
    {
        "id": "eco_arbres_plantes",
        "thematique": "ecologie",
        "libelle_citoyen": "Combien d'arbres ont été plantés depuis 2020 ?",
        "libelle_technique": "Nombre d'arbres plantés depuis le début de la mandature",
        "unite": "nb",
        "sens_positif": "haut",
        "seuil_vert": 200.0,
        "seuil_orange": 100.0,
        "seuil_rouge": 30.0,
        "valeur_reference": None,
        "libelle_reference": None,
        "description": "Nombre total d'arbres plantés sur l'espace public depuis le début "
                       "de la mandature municipale (2020). Indicateur de l'engagement "
                       "concret en faveur de la biodiversité et de la lutte contre les "
                       "îlots de chaleur.",
        "source_type": "saisie_manuelle",
    },

    # ─── Social & cohésion ────────────────────────────────────────────────────
    {
        "id": "soc_logements_sociaux_taux",
        "thematique": "social",
        "libelle_citoyen": "Quelle part de logements sociaux dans la commune ?",
        "libelle_technique": "Taux de logements sociaux (SRU)",
        "unite": "%",
        "sens_positif": "haut",
        "seuil_vert": 25.0,
        "seuil_orange": 15.0,
        "seuil_rouge": 10.0,
        "valeur_reference": 25.0,
        "libelle_reference": "Obligation légale loi SRU (25% pour communes > 3 500 hab.)",
        "description": "Part des logements sociaux (HLM) dans le parc total de résidences "
                       "principales. La loi SRU impose aux communes de plus de 3 500 "
                       "habitants d'atteindre 25% de logements sociaux, sous peine de "
                       "pénalités financières.",
        "source_type": "saisie_manuelle",
    },
    {
        "id": "soc_places_creche_attente",
        "thematique": "social",
        "libelle_citoyen": "Combien d'enfants attendent une place en crèche ?",
        "libelle_technique": "Enfants en liste d'attente en structures petite enfance",
        "unite": "nb",
        "sens_positif": "bas",
        "seuil_vert": 10.0,
        "seuil_orange": 30.0,
        "seuil_rouge": 60.0,
        "valeur_reference": None,
        "libelle_reference": None,
        "description": "Nombre d'enfants inscrits sur liste d'attente dans les structures "
                       "d'accueil petite enfance (crèches, haltes-garderies) financées ou "
                       "gérées par la commune. Indicateur de la tension sur l'offre "
                       "d'accueil.",
        "source_type": "saisie_manuelle",
    },
    {
        "id": "soc_tarif_cantine_evolution",
        "thematique": "social",
        "libelle_citoyen": "Combien coûte un repas à la cantine (quotient moyen) ?",
        "libelle_technique": "Tarif cantine au quotient familial médian",
        "unite": "€/repas",
        "sens_positif": "bas",
        "seuil_vert": 3.0,
        "seuil_orange": 4.5,
        "seuil_rouge": 6.0,
        "valeur_reference": None,
        "libelle_reference": None,
        "description": "Prix d'un repas à la cantine scolaire pour une famille au quotient "
                       "familial médian de la commune. La tarification sociale (tarification "
                       "au quotient) est le principal outil d'accessibilité aux services "
                       "publics locaux.",
        "source_type": "saisie_manuelle",
    },
    {
        "id": "soc_associations_nb",
        "thematique": "social",
        "libelle_citoyen": "Combien d'associations sont actives dans la commune ?",
        "libelle_technique": "Nombre d'associations actives domiciliées",
        "unite": "nb",
        "sens_positif": "haut",
        "seuil_vert": 80.0,
        "seuil_orange": 40.0,
        "seuil_rouge": 20.0,
        "valeur_reference": None,
        "libelle_reference": None,
        "description": "Nombre total d'associations déclarées et actives sur le territoire "
                       "communal. La vitalité associative est un indicateur du tissu social "
                       "et de l'engagement citoyen.",
        "source_type": "saisie_manuelle",
    },
    {
        "id": "soc_subventions_associations",
        "thematique": "social",
        "libelle_citoyen": "Combien la commune verse-t-elle aux associations ?",
        "libelle_technique": "Budget des subventions aux associations",
        "unite": "€/an",
        "sens_positif": "haut",
        "seuil_vert": None,
        "seuil_orange": None,
        "seuil_rouge": None,
        "valeur_reference": None,
        "libelle_reference": None,
        "description": "Montant total des subventions versées par la commune aux "
                       "associations locales. Ces financements soutiennent la vie sportive, "
                       "culturelle, sociale et citoyenne.",
        "source_type": "csv_generique",
    },
    {
        "id": "soc_participation_citoyenne",
        "thematique": "social",
        "libelle_citoyen": "Combien de réunions publiques sont organisées chaque année ?",
        "libelle_technique": "Nombre de réunions publiques de participation citoyenne",
        "unite": "nb/an",
        "sens_positif": "haut",
        "seuil_vert": 8.0,
        "seuil_orange": 4.0,
        "seuil_rouge": 1.0,
        "valeur_reference": None,
        "libelle_reference": None,
        "description": "Nombre de réunions publiques ouvertes à tous les citoyens "
                       "organisées par la municipalité hors conseil municipal (réunions de "
                       "quartier, concertations, ateliers participatifs…). Indicateur de "
                       "l'engagement en faveur de la démocratie locale.",
        "source_type": "saisie_manuelle",
    },
    {
        "id": "soc_budget_jeunesse_habitant",
        "thematique": "social",
        "libelle_citoyen": "Combien investit-on dans la jeunesse par habitant ?",
        "libelle_technique": "Budget jeunesse et animation socioculturelle par habitant",
        "unite": "€/hab",
        "sens_positif": "haut",
        "seuil_vert": 80.0,
        "seuil_orange": 50.0,
        "seuil_rouge": 25.0,
        "valeur_reference": None,
        "libelle_reference": None,
        "description": "Budget consacré aux activités jeunesse, périscolaires et à "
                       "l'animation socioculturelle, divisé par le nombre d'habitants.",
        "source_type": "csv_generique",
    },

    # ─── Gouvernance & transparence ───────────────────────────────────────────
    {
        "id": "gouv_taux_presence_conseil",
        "thematique": "gouvernance",
        "libelle_citoyen": "Les élus sont-ils présents aux conseils municipaux ?",
        "libelle_technique": "Taux de présence moyen au conseil municipal",
        "unite": "%",
        "sens_positif": "haut",
        "seuil_vert": 85.0,
        "seuil_orange": 70.0,
        "seuil_rouge": 55.0,
        "valeur_reference": None,
        "libelle_reference": None,
        "description": "Taux moyen de présence des conseillers municipaux aux séances du "
                       "conseil. Un taux élevé traduit l'implication des élus dans la "
                       "gestion de la commune.",
        "source_type": "saisie_manuelle",
    },
    {
        "id": "gouv_delai_publication_pv",
        "thematique": "gouvernance",
        "libelle_citoyen": "Les comptes-rendus du conseil sont-ils publiés rapidement ?",
        "libelle_technique": "Délai moyen de publication des PV (légal : 8 jours ouvrés)",
        "unite": "jours",
        "sens_positif": "bas",
        "seuil_vert": 8.0,
        "seuil_orange": 15.0,
        "seuil_rouge": 30.0,
        "valeur_reference": 8.0,
        "libelle_reference": "Délai légal : 8 jours ouvrés (Code général des collectivités)",
        "description": "Délai moyen entre la tenue du conseil municipal et la publication "
                       "du compte-rendu sur le site de la commune. La loi impose un affichage "
                       "sous 8 jours ouvrés.",
        "source_type": "saisie_manuelle",
    },
    {
        "id": "gouv_deliberations_unanimes",
        "thematique": "gouvernance",
        "libelle_citoyen": "Quelle part des décisions sont prises à l'unanimité ?",
        "libelle_technique": "Part des délibérations votées à l'unanimité",
        "unite": "%",
        "sens_positif": "neutre",
        "seuil_vert": None,
        "seuil_orange": None,
        "seuil_rouge": None,
        "valeur_reference": None,
        "libelle_reference": None,
        "description": "Part des délibérations du conseil municipal adoptées à l'unanimité. "
                       "Cet indicateur est à interpréter avec nuance : une unanimité élevée "
                       "peut refléter le consensus mais aussi l'absence de débat contradictoire.",
        "source_type": "saisie_manuelle",
    },
    {
        "id": "gouv_reponses_questions_ecrites",
        "thematique": "gouvernance",
        "libelle_citoyen": "Les questions de l'opposition reçoivent-elles des réponses ?",
        "libelle_technique": "Taux de réponse aux questions écrites de l'opposition",
        "unite": "%",
        "sens_positif": "haut",
        "seuil_vert": 90.0,
        "seuil_orange": 70.0,
        "seuil_rouge": 50.0,
        "valeur_reference": None,
        "libelle_reference": None,
        "description": "Part des questions écrites posées par les élus d'opposition qui ont "
                       "reçu une réponse écrite de l'exécutif municipal dans le délai d'un "
                       "mois. Indicateur du respect du droit d'information des élus minoritaires.",
        "source_type": "saisie_manuelle",
    },
    {
        "id": "gouv_seances_par_an",
        "thematique": "gouvernance",
        "libelle_citoyen": "Combien de conseils municipaux sont organisés par an ?",
        "libelle_technique": "Nombre de séances du conseil municipal par an",
        "unite": "nb",
        "sens_positif": "haut",
        "seuil_vert": 10.0,
        "seuil_orange": 6.0,
        "seuil_rouge": 4.0,
        "valeur_reference": 4.0,
        "libelle_reference": "Minimum légal : 4 séances par an",
        "description": "Nombre de séances du conseil municipal tenues dans l'année. La loi "
                       "impose un minimum de 4 séances par an. Un nombre élevé traduit une "
                       "gouvernance active et un suivi régulier des affaires communales.",
        "source_type": "saisie_manuelle",
    },
    {
        "id": "gouv_decisions_delegation_maire",
        "thematique": "gouvernance",
        "libelle_citoyen": "Combien de décisions le maire prend-il seul par délégation ?",
        "libelle_technique": "Décisions prises par délégation du conseil au maire",
        "unite": "nb/an",
        "sens_positif": "neutre",
        "seuil_vert": None,
        "seuil_orange": None,
        "seuil_rouge": None,
        "valeur_reference": None,
        "libelle_reference": None,
        "description": "Nombre de décisions prises par le maire en vertu de la délégation "
                       "accordée par le conseil municipal. Cette délégation, prévue par la "
                       "loi, permet une gestion plus souple, mais peut réduire le contrôle "
                       "démocratique si elle est trop étendue.",
        "source_type": "saisie_manuelle",
    },

    # ─── Services publics & patrimoine ───────────────────────────────────────
    {
        "id": "serv_etat_patrimoine_score",
        "thematique": "services",
        "libelle_citoyen": "Dans quel état sont les bâtiments publics communaux ?",
        "libelle_technique": "Score d'état du patrimoine bâti communal",
        "unite": "score 1–5",
        "sens_positif": "haut",
        "seuil_vert": 4.0,
        "seuil_orange": 3.0,
        "seuil_rouge": 2.0,
        "valeur_reference": None,
        "libelle_reference": None,
        "description": "Score moyen de l'état des bâtiments publics (mairie, école, salle "
                       "des fêtes…) évalué de 1 (très dégradé) à 5 (excellent état) lors "
                       "du dernier audit de patrimoine.",
        "source_type": "saisie_manuelle",
    },
    {
        "id": "serv_accessibilite_pmr",
        "thematique": "services",
        "libelle_citoyen": "Les équipements publics sont-ils accessibles aux personnes handicapées ?",
        "libelle_technique": "Taux d'équipements ERP conformes accessibilité PMR",
        "unite": "%",
        "sens_positif": "haut",
        "seuil_vert": 80.0,
        "seuil_orange": 60.0,
        "seuil_rouge": 40.0,
        "valeur_reference": 100.0,
        "libelle_reference": "Obligation légale loi handicap 2005 (100% ERP)",
        "description": "Part des établissements recevant du public (ERP) communaux "
                       "conformes aux normes d'accessibilité pour les personnes en situation "
                       "de handicap. La loi de 2005 impose une accessibilité totale.",
        "source_type": "saisie_manuelle",
    },
    {
        "id": "serv_horaires_mairie",
        "thematique": "services",
        "libelle_citoyen": "Combien d'heures la mairie est-elle ouverte par semaine ?",
        "libelle_technique": "Heures d'ouverture de la mairie par semaine",
        "unite": "h/sem",
        "sens_positif": "haut",
        "seuil_vert": 30.0,
        "seuil_orange": 20.0,
        "seuil_rouge": 12.0,
        "valeur_reference": None,
        "libelle_reference": None,
        "description": "Nombre total d'heures d'ouverture au public de la mairie et de ses "
                       "annexes par semaine. Un horaire étendu facilite l'accès aux services "
                       "pour les actifs et les familles.",
        "source_type": "saisie_manuelle",
    },
    {
        "id": "serv_delai_urbanisme",
        "thematique": "services",
        "libelle_citoyen": "Combien de temps faut-il pour obtenir un permis de construire ?",
        "libelle_technique": "Délai moyen d'instruction des permis de construire",
        "unite": "jours",
        "sens_positif": "bas",
        "seuil_vert": 45.0,
        "seuil_orange": 60.0,
        "seuil_rouge": 90.0,
        "valeur_reference": 60.0,
        "libelle_reference": "Délai légal : 2 mois pour une maison individuelle",
        "description": "Délai moyen constaté entre le dépôt d'un dossier de permis de "
                       "construire complet et la notification de la décision. Le délai légal "
                       "est de 2 mois pour une maison individuelle, 3 mois pour les autres.",
        "source_type": "saisie_manuelle",
    },
    {
        "id": "serv_demarches_en_ligne",
        "thematique": "services",
        "libelle_citoyen": "Quelle part des démarches peut-on faire en ligne ?",
        "libelle_technique": "Part des démarches administratives disponibles en ligne",
        "unite": "%",
        "sens_positif": "haut",
        "seuil_vert": 70.0,
        "seuil_orange": 40.0,
        "seuil_rouge": 20.0,
        "valeur_reference": None,
        "libelle_reference": None,
        "description": "Part des démarches administratives communales accessibles via le "
                       "portail numérique de la mairie ou le site service-public.fr. "
                       "Indicateur de modernisation des services publics locaux.",
        "source_type": "saisie_manuelle",
    },

    # ─── Vitalité économique ──────────────────────────────────────────────────
    {
        "id": "eco2_nb_commerces",
        "thematique": "economie",
        "libelle_citoyen": "Combien de commerces et services de proximité dans la commune ?",
        "libelle_technique": "Nombre de commerces et services de proximité",
        "unite": "nb",
        "sens_positif": "haut",
        "seuil_vert": 60.0,
        "seuil_orange": 35.0,
        "seuil_rouge": 15.0,
        "valeur_reference": None,
        "libelle_reference": None,
        "description": "Nombre total de commerces de détail, services (coiffeur, médecin, "
                       "pharmacie…) et restaurants actifs sur le territoire communal. "
                       "Indicateur du dynamisme commercial et de la qualité de vie.",
        "source_type": "csv_generique",
    },
    {
        "id": "eco2_evolution_entreprises",
        "thematique": "economie",
        "libelle_citoyen": "Le nombre d'entreprises augmente-t-il sur la commune ?",
        "libelle_technique": "Évolution du stock d'entreprises actives",
        "unite": "nb",
        "sens_positif": "haut",
        "seuil_vert": None,
        "seuil_orange": None,
        "seuil_rouge": None,
        "valeur_reference": None,
        "libelle_reference": None,
        "description": "Nombre total d'entreprises et d'établissements actifs domiciliés "
                       "sur la commune (source SIRENE/INSEE). L'évolution d'une année sur "
                       "l'autre reflète l'attractivité économique du territoire.",
        "source_type": "csv_generique",
    },
    {
        "id": "eco2_taux_vacance_commerciale",
        "thematique": "economie",
        "libelle_citoyen": "Quelle part des locaux commerciaux sont vides ?",
        "libelle_technique": "Taux de vacance commerciale",
        "unite": "%",
        "sens_positif": "bas",
        "seuil_vert": 5.0,
        "seuil_orange": 10.0,
        "seuil_rouge": 15.0,
        "valeur_reference": 12.0,
        "libelle_reference": "Taux moyen national 2023 (Procos/CCI)",
        "description": "Part des locaux commerciaux vacants (inoccupés depuis plus de 6 "
                       "mois) dans le total des locaux commerciaux. Un taux élevé traduit "
                       "une fragilisation du tissu commercial local.",
        "source_type": "saisie_manuelle",
    },
    {
        "id": "eco2_marches_evenements",
        "thematique": "economie",
        "libelle_citoyen": "Combien de marchés et événements économiques par an ?",
        "libelle_technique": "Nombre de marchés et événements à dimension économique",
        "unite": "nb/an",
        "sens_positif": "haut",
        "seuil_vert": 20.0,
        "seuil_orange": 10.0,
        "seuil_rouge": 4.0,
        "valeur_reference": None,
        "libelle_reference": None,
        "description": "Nombre total de marchés hebdomadaires, foires, brocantes, forums "
                       "économiques et autres événements à dimension commerciale organisés "
                       "ou soutenus par la commune dans l'année.",
        "source_type": "saisie_manuelle",
    },
    {
        "id": "eco2_emplois_commune",
        "thematique": "economie",
        "libelle_citoyen": "Combien d'emplois sur la commune ?",
        "libelle_technique": "Nombre d'emplois salariés sur le territoire communal",
        "unite": "nb",
        "sens_positif": "haut",
        "seuil_vert": None,
        "seuil_orange": None,
        "seuil_rouge": None,
        "valeur_reference": None,
        "libelle_reference": None,
        "description": "Nombre d'emplois salariés (hors agriculture) déclarés sur le "
                       "territoire de la commune (source INSEE/URSSAF). L'évolution de cet "
                       "indicateur reflète le dynamisme économique local.",
        "source_type": "csv_generique",
    },
]


def seed():
    init_db()
    conn = get_db()
    inserted = 0
    skipped = 0
    for ind in INDICATEURS:
        existing = conn.execute(
            "SELECT id FROM indicateurs WHERE id = ?", (ind["id"],)
        ).fetchone()
        if existing:
            skipped += 1
            continue
        conn.execute("""
            INSERT INTO indicateurs (
                id, thematique, libelle_citoyen, libelle_technique, unite,
                sens_positif, seuil_vert, seuil_orange, seuil_rouge,
                valeur_reference, libelle_reference, description, source_type
            ) VALUES (
                :id, :thematique, :libelle_citoyen, :libelle_technique, :unite,
                :sens_positif, :seuil_vert, :seuil_orange, :seuil_rouge,
                :valeur_reference, :libelle_reference, :description, :source_type
            )
        """, ind)
        inserted += 1
    conn.commit()
    conn.close()
    print(f"Seed terminé : {inserted} indicateurs insérés, {skipped} déjà présents.")


if __name__ == "__main__":
    seed()
