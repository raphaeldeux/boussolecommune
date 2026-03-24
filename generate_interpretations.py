"""
Script de génération en masse des analyses Mistral pour tous les indicateurs
qui n'ont pas encore de phrase_longue.

Usage :
  python generate_interpretations.py              # toutes les communes
  python generate_interpretations.py --ville 1    # une seule ville (id)
  python generate_interpretations.py --dry-run    # affiche sans appeler Mistral
"""
import argparse
import sys
import time

# Bootstrap Flask app context
from app import create_app
app = create_app()

with app.app_context():
    from app.database import get_db
    from app.services.ai_service import generer_interpretation_indicateur, MISTRAL_API_KEY
    import app.models.interpretation as interp_model
    import app.models.donnee as donnee_model
    from app.models.banque_reference import get_ref_for_indicateur_ville

    if not MISTRAL_API_KEY:
        print("❌  MISTRAL_API_KEY non configurée. Abandon.", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser()
    parser.add_argument("--ville", type=int, default=None, help="ID de la ville (toutes si omis)")
    parser.add_argument("--dry-run", action="store_true", help="Affiche sans appeler Mistral")
    args = parser.parse_args()

    with get_db() as conn:
        # Récupérer les couples (ville_id, indicateur_id, annee) avec donnée mais sans analyse
        query = """
            SELECT d.ville_id, d.indicateur_id, d.annee, d.valeur, d.source,
                   i.libelle_citoyen, i.libelle_technique, i.unite, i.sens_positif,
                   v.nom AS ville_nom
            FROM donnees d
            JOIN indicateurs i ON d.indicateur_id = i.id
            JOIN villes v ON d.ville_id = v.id
            LEFT JOIN interpretations interp
                   ON interp.indicateur_id = d.indicateur_id
                  AND interp.ville_id = d.ville_id
                  AND interp.annee = d.annee
            WHERE (interp.phrase_longue IS NULL OR interp.phrase_longue = '')
              AND i.thematique != 'portrait'
        """
        params = []
        if args.ville:
            query += " AND d.ville_id = %s"
            params.append(args.ville)

        # Prendre la dernière année disponible par (ville, indicateur)
        query = f"""
            SELECT DISTINCT ON (sub.ville_id, sub.indicateur_id)
                   sub.*
            FROM ({query}) sub
            ORDER BY sub.ville_id, sub.indicateur_id, sub.annee DESC
        """
        rows = conn.execute(query, params).fetchall()

    todo = [dict(r) for r in rows]
    total = len(todo)
    print(f"📋  {total} analyses à générer{' (dry-run)' if args.dry_run else ''}.")

    ok = 0
    errors = 0

    for i, row in enumerate(todo, 1):
        ville_id     = row["ville_id"]
        ind_id       = row["indicateur_id"]
        annee        = row["annee"]
        ville_nom    = row["ville_nom"]
        libelle      = row["libelle_citoyen"]

        print(f"[{i}/{total}] {ville_nom} — {libelle} ({annee})", end=" ... ", flush=True)

        if args.dry_run:
            print("(skip)")
            continue

        # Récupérer historique pour tendance
        historique = donnee_model.get_by_indicateur(ind_id, ville_id)
        donnee_ancienne = historique[-1] if len(historique) > 1 else None
        valeur_ancienne = donnee_ancienne["valeur"] if donnee_ancienne else None
        annee_ancienne  = donnee_ancienne["annee"]  if donnee_ancienne else None
        pct_evolution   = None
        if valeur_ancienne and valeur_ancienne != 0:
            pct_evolution = round((row["valeur"] - valeur_ancienne) / abs(valeur_ancienne) * 100, 1)

        # Référence communes similaires
        ref_ville = get_ref_for_indicateur_ville(ind_id, ville_id)
        valeur_reference = ref_ville["valeur"] if ref_ville else None

        ind_dict = {
            "id":               ind_id,
            "libelle_citoyen":  row["libelle_citoyen"],
            "libelle_technique": row["libelle_technique"],
            "unite":            row["unite"],
            "sens_positif":     row["sens_positif"],
        }
        donnee_dict = {"valeur": row["valeur"], "annee": annee}

        try:
            result = generer_interpretation_indicateur(
                ind_dict, donnee_dict,
                valeur_ancienne=valeur_ancienne,
                annee_ancienne=annee_ancienne,
                pct_evolution=pct_evolution,
                valeur_reference=valeur_reference,
            )
            if result and result.get("phrase_longue"):
                interp_model.upsert(
                    ind_id, annee,
                    score=None,
                    phrase_courte=None,
                    phrase_longue=result["phrase_longue"],
                    ville_id=ville_id,
                )
                print("✓")
                ok += 1
            else:
                print("⚠ réponse vide")
                errors += 1
        except Exception as e:
            print(f"✗ {e}")
            errors += 1

        # Petite pause pour ne pas saturer l'API
        time.sleep(0.5)

    print(f"\n✅  Terminé : {ok} générées, {errors} erreurs sur {total} total.")
