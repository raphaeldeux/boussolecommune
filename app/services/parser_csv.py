import csv
import io
from app.models.indicateur import get_by_id


COLONNES_REQUISES = {"annee", "indicateur_id", "valeur", "source"}


def parser_generique(contenu):
    """
    Parse un CSV générique.
    Retourne (lignes_valides, erreurs)
    lignes_valides : liste de dicts {indicateur_id, annee, valeur, source}
    erreurs : liste de dicts {ligne, message}
    """
    lignes_valides = []
    erreurs = []

    try:
        reader = csv.DictReader(io.StringIO(contenu))
    except Exception as e:
        return [], [{"ligne": 0, "message": f"Impossible de lire le fichier CSV : {e}"}]

    colonnes = set(reader.fieldnames or [])
    manquantes = COLONNES_REQUISES - colonnes
    if manquantes:
        return [], [{"ligne": 0, "message": f"Colonnes manquantes : {', '.join(manquantes)}"}]

    for num, row in enumerate(reader, start=2):
        indicateur_id = row.get("indicateur_id", "").strip()
        annee_str = row.get("annee", "").strip()
        valeur_str = row.get("valeur", "").strip()
        source = row.get("source", "").strip()

        if not indicateur_id:
            erreurs.append({"ligne": num, "message": "indicateur_id vide"})
            continue

        indicateur = get_by_id(indicateur_id)
        if not indicateur:
            erreurs.append({"ligne": num, "message": f"Indicateur inconnu : {indicateur_id}"})
            continue

        try:
            annee = int(annee_str)
        except ValueError:
            erreurs.append({"ligne": num, "message": f"Année invalide : {annee_str}"})
            continue

        try:
            valeur = float(valeur_str.replace(",", "."))
        except ValueError:
            erreurs.append({"ligne": num, "message": f"Valeur invalide : {valeur_str}"})
            continue

        lignes_valides.append({
            "indicateur_id": indicateur_id,
            "annee": annee,
            "valeur": valeur,
            "source": source,
            "libelle_citoyen": indicateur["libelle_citoyen"],
            "thematique": indicateur["thematique"],
        })

    return lignes_valides, erreurs
