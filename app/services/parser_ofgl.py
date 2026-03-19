import csv
import io

# Correspondance libellés OFGL -> indicateur_id
MAPPING_OFGL = {
    "épargne brute": "fin_epargne_brute",
    "epargne brute": "fin_epargne_brute",
    "encours de dette": "fin_dette_habitant",
    "encours dette": "fin_dette_habitant",
    "dette": "fin_dette_habitant",
    "capacité de désendettement": "fin_capacite_desendettement",
    "capacite de desendettement": "fin_capacite_desendettement",
    "dépenses d'investissement": "fin_investissement_habitant",
    "depenses d'investissement": "fin_investissement_habitant",
    "investissements": "fin_investissement_habitant",
    "charges de personnel": "fin_masse_salariale_ratio",
    "masse salariale": "fin_masse_salariale_ratio",
    "rigidité des charges": "fin_rigidite_charges",
    "rigidite des charges": "fin_rigidite_charges",
}

SOURCE_OFGL = "OFGL — Comptes de gestion"

COLONNES_REQUISES = {"code_commune", "annee", "libelle_compte", "montant"}


def parser_ofgl(contenu, population=None):
    """
    Parse un export OFGL (séparateur ;).
    population : nombre d'habitants de la commune (obligatoire pour les indicateurs par habitant).
    Retourne (lignes_valides, erreurs)
    """
    lignes_valides = []
    erreurs = []

    # Détecter le séparateur
    sep = ";" if ";" in contenu[:500] else ","

    try:
        reader = csv.DictReader(io.StringIO(contenu), delimiter=sep)
    except Exception as e:
        return [], [{"ligne": 0, "message": f"Impossible de lire le fichier : {e}"}]

    fieldnames = [f.strip().lower() for f in (reader.fieldnames or [])]
    manquantes = COLONNES_REQUISES - set(fieldnames)
    if manquantes:
        return [], [{"ligne": 0, "message": f"Colonnes manquantes : {', '.join(manquantes)}"}]

    for num, row in enumerate(reader, start=2):
        row_norm = {k.strip().lower(): v.strip() for k, v in row.items()}

        libelle = row_norm.get("libelle_compte", "").lower().strip()
        annee_str = row_norm.get("annee", "").strip()
        montant_str = row_norm.get("montant", "").strip()

        indicateur_id = None
        for cle, ind_id in MAPPING_OFGL.items():
            if cle in libelle:
                indicateur_id = ind_id
                break

        if not indicateur_id:
            erreurs.append({"ligne": num, "message": f"Libellé non reconnu : {libelle}"})
            continue

        try:
            annee = int(annee_str)
        except ValueError:
            erreurs.append({"ligne": num, "message": f"Année invalide : {annee_str}"})
            continue

        try:
            montant = float(montant_str.replace(",", ".").replace(" ", ""))
        except ValueError:
            erreurs.append({"ligne": num, "message": f"Montant invalide : {montant_str}"})
            continue

        # Conversion en valeur par habitant si nécessaire
        if indicateur_id in ("fin_dette_habitant", "fin_investissement_habitant"):
            if not population:
                erreurs.append({"ligne": num, "message": f"Population inconnue, impossible de calculer la valeur par habitant pour {indicateur_id}"})
                continue
            valeur = round(montant / population, 2)
        else:
            valeur = montant

        lignes_valides.append({
            "indicateur_id": indicateur_id,
            "annee": annee,
            "valeur": valeur,
            "source": SOURCE_OFGL,
            "libelle_ofgl": libelle,
        })

    return lignes_valides, erreurs
