import json
import logging
import os
import re
import time
import app.models.interpretation as interp_model
import app.models.donnee as donnee_model

# Utilise le logger Flask (capturé par gunicorn) avec fallback sur le logger module
try:
    from flask import current_app
    def _log(level, msg, *args):
        getattr(current_app.logger, level)(msg, *args)
except Exception:
    _logger = logging.getLogger(__name__)
    def _log(level, msg, *args):
        getattr(_logger, level)(msg, *args)

SYSTEM_PROMPT = """Tu es un expert en politiques publiques locales françaises, spécialisé dans \
l'analyse des communes de taille moyenne (5 000 à 20 000 habitants).
Tu génères des interprétations factuelles et pédagogiques d'indicateurs \
municipaux pour des citoyens non experts. Ton ton est neutre, honnête et \
bienveillant. Tu ne portes aucun jugement politique. Tu contextualises \
systématiquement avec des références nationales ou légales quand elles existent.
Tu réponds UNIQUEMENT en JSON valide, sans markdown, sans texte avant ou après, \
avec exactement ces trois clés : "score", "phrase_courte", "phrase_longue".
- score : une lettre parmi A, B, C, D, E
- phrase_courte : une seule phrase, maximum 120 caractères
- phrase_longue : 2 à 3 phrases, maximum 400 caractères au total"""


def _build_prompt(indicateur, annee, valeur, valeur_n1=None):
    sens_label = {"haut": "haute", "bas": "basse", "neutre": "haute ou basse"}.get(
        indicateur.get("sens_positif", "neutre"), "haute"
    )
    lignes = [
        "Commune : Sautron (Loire-Atlantique, ~8 600 habitants, périurbain Nantes)",
        f"Indicateur : {indicateur['libelle_citoyen']}",
        f"Identifiant technique : {indicateur['id']}",
        f"Unité : {indicateur.get('unite', '')}",
        f"Sens de lecture : une valeur {sens_label} est meilleure",
        f"Valeur {annee} : {valeur} {indicateur.get('unite', '')}",
    ]
    if valeur_n1 is not None:
        lignes.append(f"Valeur {annee - 1} : {valeur_n1} {indicateur.get('unite', '')}")
    if indicateur.get("valeur_reference") and indicateur.get("libelle_reference"):
        lignes.append(
            f"Référence nationale / seuil légal : {indicateur['valeur_reference']} "
            f"{indicateur.get('unite', '')} ({indicateur['libelle_reference']})"
        )
    if indicateur.get("description"):
        lignes.append(f"Description de l'indicateur : {indicateur['description']}")
    lignes.append("Génère l'interprétation citoyenne.")
    return "\n".join(lignes)


def _get_client():
    """Retourne un client OpenAI-compatible selon la clé disponible (lu depuis os.environ)."""
    from openai import OpenAI
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if openrouter_key:
        return OpenAI(
            api_key=openrouter_key,
            base_url="https://openrouter.ai/api/v1",
        ), "mistralai/mistral-7b-instruct:free"
    if anthropic_key:
        return OpenAI(
            api_key=anthropic_key,
            base_url="https://api.anthropic.com/v1/",
        ), "claude-sonnet-4-5"
    return None, None


def _parse_json(texte):
    """Extrait le JSON même si le modèle l'a entouré de blocs markdown."""
    texte = texte.strip()
    # Retire les blocs ```json ... ``` ou ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", texte)
    if match:
        texte = match.group(1)
    return json.loads(texte)


def generer_interpretation(indicateur, annee, valeur, score_calcule=None):
    """Génère et met en cache l'interprétation via OpenRouter ou Anthropic."""
    client, model = _get_client()
    if not client:
        _log("error", "[claude] Aucune clé API configurée (OPENROUTER_API_KEY manquante).")
        return None

    donnee_n1 = donnee_model.get_by_indicateur_annee(indicateur["id"], annee - 1)
    valeur_n1 = donnee_n1["valeur"] if donnee_n1 else None

    prompt = _build_prompt(indicateur, annee, valeur, valeur_n1)

    for tentative in range(2):
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=512,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            texte = response.choices[0].message.content.strip()
            data = _parse_json(texte)
            score = data.get("score") or score_calcule
            phrase_courte = data.get("phrase_courte", "")
            phrase_longue = data.get("phrase_longue", "")
            interp_model.upsert(indicateur["id"], annee, score, phrase_courte, phrase_longue)
            return {"score": score, "phrase_courte": phrase_courte, "phrase_longue": phrase_longue}
        except Exception as e:
            _log("error", "[claude] Tentative %d échouée : %s", tentative + 1, e)
            if tentative == 0:
                time.sleep(5)
            else:
                return None
    return None
