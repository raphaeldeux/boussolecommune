"""
Service de génération de résumés citoyens via Mistral AI.
"""
import os
import json as _json
import requests
import pdfplumber

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"

# Les 6 thématiques fixes du cadre "Prendre soin" (ordre d'affichage)
THEMES_ORDRE = ["Soin des personnes", "Soin des finances / RH", "Soin du cadre de vie", "Soin du lien social", "Soin de la démocratie", "Soin du vivant"]

_REGLES_CLASSIFICATION = """RÈGLE CRITIQUE : Le thème est déterminé par le SUJET et le BÉNÉFICIAIRE, jamais par la présence d'argent.
- Subvention à une association sportive/culturelle → Soin du lien social
- Subvention au CCAS ou service d'aide → Soin des personnes
- Subvention projet environnemental → Soin du vivant
- Budget primitif de la commune → Soin des finances / RH
- Emprunt pour travaux → Soin du cadre de vie
- Indemnités des élus → Soin des finances / RH"""

_REGLES_VOTES = """Votes : utiliser UNIQUEMENT les chiffres explicitement écrits dans le document.
- "À l'unanimité" → pour = membres présents, contre = 0, abstentions = 0
- Pas de vote mentionné → "vote": null
- Toujours inclure "abstentions" (même à 0). Total ≤ 29 membres."""

_REGLES_DESCRIPTIONS = """Descriptions : 2-4 phrases avec contexte, décision, montant, impact citoyen.
Bannir : "le conseil a approuvé", "il a été décidé".
Bénéficiaire : nom exact de l'association/organisme (null sinon).
Montant : OBLIGATOIRE si la délibération contient les mots subvention, marché, emprunt, dotation, tarif, ou un signe €.
  - Recopier exactement le chiffre en € trouvé dans le texte (ex: "5 000 €", "1 250 000 €")
  - Si aucun montant explicite mais délibération financière : "montant non précisé dans le PV"
  - Sinon : null"""


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extrait le texte brut d'un PDF. Fallback OCR si le PDF est un scan."""
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
    texte = "\n\n".join(text_parts)
    if texte.strip():
        return texte

    # Fallback OCR pour les PDFs scannés
    print("[INFO] PDF sans texte extractible, tentative OCR…", flush=True)
    try:
        import pytesseract
        from pdf2image import convert_from_path
        images = convert_from_path(pdf_path, dpi=200)
        ocr_parts = []
        for img in images:
            ocr_parts.append(pytesseract.image_to_string(img, lang="fra"))
        return "\n\n".join(ocr_parts)
    except Exception as e:
        print(f"[WARN] OCR échoué : {e}", flush=True)
        return ""


def _parse_json(raw: str) -> dict:
    """Parse JSON depuis une réponse LLM (gère les backticks)."""
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]
        clean = clean.strip()
    return _json.loads(clean)


def _appel_mistral(prompt: str) -> str:
    """Appel Mistral AI. Contexte 128k tokens."""
    response = requests.post(
        MISTRAL_API_URL,
        headers={
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MISTRAL_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        },
        timeout=180,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def generer_resume(pdf_path: str, progress_callback=None):
    """
    Extrait le texte du PDF et génère résumé + structure JSON via Mistral.
    Retourne un tuple (resume_texte: str, resume_structure: str | None).
    progress_callback(pct: int, message: str = None) est appelé à chaque étape.
    """
    def _progress(pct, message=None):
        if progress_callback:
            try:
                progress_callback(pct, message)
            except Exception:
                pass

    _progress(5, "Lecture du document…")
    texte = extract_text_from_pdf(pdf_path)
    if not texte.strip():
        raise ValueError("Le PDF ne contient pas de texte extractible.")

    _progress(10, "Lecture du document…")
    prompt = f"""Tu es un assistant chargé d'analyser des procès-verbaux de conseils municipaux.

Voici le contenu intégral du procès-verbal :

{texte}

---

IMPÉRATIF : Tu dois être EXHAUSTIF. Chaque point inscrit à l'ordre du jour doit figurer dans le JSON.

Génère une réponse JSON avec ces champs :
1. "resume_texte" : synthèse en 2-3 phrases max en langage citoyen pour l'aperçu de la liste des conseils
2. "nb_points_odj" : nombre de points à l'ordre du jour identifiés dans le document
3. "nb_presents" : nombre de conseillers présents à la séance (entier, null si non mentionné)
4. "themes" : liste exhaustive et structurée de toutes les délibérations

Thématiques (classer par sujet, pas par présence d'argent) :
- Soin des personnes : santé, école, éducation, enfance, seniors, CCAS, aide sociale
- Soin des finances / RH : budget communal, fiscalité, emprunt de la commune, personnel, RH, indemnités élus
- Soin du cadre de vie : urbanisme, voirie, logement, travaux, équipements publics
- Soin du lien social : associations sportives/culturelles/solidarité, événements, vie associative
- Soin de la démocratie : gouvernance, délégations, conventions, intercommunalité, élus
- Soin du vivant : environnement, biodiversité, eau, énergie, agriculture, alimentation

{_REGLES_CLASSIFICATION}
{_REGLES_VOTES}
{_REGLES_DESCRIPTIONS}

Réponds UNIQUEMENT avec du JSON valide :
{{
  "resume_texte": "2-3 phrases max, grandes tendances du conseil.",
  "nb_points_odj": 18,
  "nb_presents": 23,
  "themes": [
    {{
      "titre": "<thème exact parmi : Soin des personnes, Soin des finances / RH, Soin du cadre de vie, Soin du lien social, Soin de la démocratie, Soin du vivant>",
      "resume": "Chapeau introductif 1-2 phrases sans répéter les délibérations.",
      "total_subventions": "Somme si plusieurs subventions dans ce thème, sinon null",
      "deliberations": [
        {{
          "titre": "Intitulé exact",
          "description": "2-4 phrases: contexte, décision, impact citoyen.",
          "beneficiaire": "Nom exact ou null",
          "montant": "X € (obligatoire si subvention/marché/€ mentionné) ou null",
          "vote": {{"pour": N, "contre": N, "abstentions": N}}
        }}
      ]
    }}
  ]
}}"""

    _progress(20, "Envoi au modèle IA…")
    raw = _appel_mistral(prompt)
    _progress(85, "Extraction des délibérations…")

    try:
        parsed = _parse_json(raw)
        resume_texte = parsed.get("resume_texte", "").strip()
        themes = parsed.get("themes", [])
        nb_points_odj = parsed.get("nb_points_odj", 0)
        nb_presents = parsed.get("nb_presents", None)

        themes_ordonnes = []
        for titre in THEMES_ORDRE:
            for t in themes:
                if t.get("titre") == titre:
                    themes_ordonnes.append(t)
                    break

        if not resume_texte:
            raise ValueError("resume_texte vide")

        resume_structure = _json.dumps({
            "themes": themes_ordonnes,
            "nb_points_odj": nb_points_odj,
            "nb_presents": nb_presents,
        }, ensure_ascii=False)
        _progress(95, "Finalisation…")
        return resume_texte, resume_structure

    except Exception as e:
        print(f"[WARN] Parse JSON échoué : {e} — fallback prose", flush=True)
        return raw[:500], None


def generer_synthese_thematique(thematique_label: str, indicateurs_enrichis: list) -> list[str] | None:
    """
    Génère 2-3 bullet points de synthèse pour une thématique à partir des indicateurs enrichis.

    Args:
        thematique_label: Label d'affichage, ex. "Soin de la maison" (pas le slug).
        indicateurs_enrichis: Liste de dicts enrichis (tendance, libelle_citoyen, donnee, pct_evolution).

    Returns:
        list[str] avec 2-3 éléments, ou None si échec.
    """
    if not MISTRAL_API_KEY:
        return None

    # Sélection des évolutions les plus notables
    renseignes = [e for e in indicateurs_enrichis if e.get("donnee")]
    amelioration = sorted(
        [e for e in renseignes if e.get("tendance") == "↗"],
        key=lambda e: abs(e.get("pct_evolution") or 0),
        reverse=True,
    )[:3]
    surveiller = sorted(
        [e for e in renseignes if e.get("tendance") == "↘"],
        key=lambda e: abs(e.get("pct_evolution") or 0),
        reverse=True,
    )[:3]
    notables = amelioration + surveiller

    if not notables:
        return None

    lignes = []
    for e in notables:
        tendance = e.get("tendance", "")
        libelle = e.get("libelle_citoyen", "")
        valeur = e.get("donnee", {}).get("valeur", "")
        unite = e.get("unite", "")
        pct = e.get("pct_evolution")
        pct_str = f" ({'+' if pct and pct > 0 else ''}{pct}%)" if pct is not None else ""
        lignes.append(f"{tendance} {libelle} : {valeur} {unite}{pct_str}")

    donnees_str = "\n".join(f"- {l}" for l in lignes)

    prompt = f"""Tu analyses la thématique "{thematique_label}" d'une commune française.

Voici les évolutions notables des indicateurs :
{donnees_str}

Rédige exactement 2 ou 3 bullet points synthétisant CE QUI ÉVOLUE (positivement ou négativement).
Règles :
- 1 phrase max par bullet point, en français citoyen (pas de jargon)
- Commence chaque ligne par ↗ si amélioration, ⚠ si dégradation
- Pas de titre, pas d'introduction, UNIQUEMENT les bullet points
- Ne mentionne pas "IA", "modèle", "généré"

Exemple de format attendu :
↗ Le budget d'investissement a progressé de 15% cette année.
⚠ La dette par habitant reste au-dessus de la moyenne régionale."""

    try:
        raw = _appel_mistral(prompt)
        bullets = [line.strip() for line in raw.strip().splitlines() if line.strip()]
        bullets = [b for b in bullets if b.startswith(("↗", "⚠", "↘", "•", "-"))]
        if not bullets:
            # Fallback : découper en phrases si le modèle a répondu autrement
            bullets = [s.strip() for s in raw.strip().split("\n") if s.strip()]
        return bullets[:3] if bullets else None
    except Exception as e:
        print(f"[WARN] generer_synthese_thematique échoué : {e}", flush=True)
        return None


def generer_interpretation_indicateur(
    ind: dict,
    donnee: dict,
    valeur_ancienne=None,
    annee_ancienne=None,
    pct_evolution=None,
    valeur_reference=None,
) -> dict | None:
    """
    Génère une analyse (phrase_longue) pour un indicateur via Mistral.
    Retourne {"phrase_longue": str} ou None si échec.
    """
    if not MISTRAL_API_KEY:
        return None

    libelle = ind.get("libelle_citoyen", ind.get("id", ""))
    libelle_tech = ind.get("libelle_technique") or libelle
    unite = ind.get("unite", "")
    valeur = donnee.get("valeur")
    annee = donnee.get("annee")
    sens = ind.get("sens_positif", "neutre")

    sens_explication = {
        "haut": "une valeur élevée est favorable",
        "bas":  "une valeur basse est favorable",
        "neutre": "la valeur est neutre (ni bonne ni mauvaise en soi)",
    }.get(sens, "")

    contexte_tendance = ""
    if valeur_ancienne is not None and annee_ancienne:
        signe = "+" if pct_evolution and pct_evolution > 0 else ""
        contexte_tendance = (
            f"\n- Évolution depuis {annee_ancienne} : "
            f"{'hausse' if valeur > valeur_ancienne else 'baisse'} "
            f"({signe}{pct_evolution}%) — était {valeur_ancienne} {unite}"
        )

    contexte_ref = ""
    if valeur_reference is not None:
        try:
            ecart = round((valeur - valeur_reference) / abs(valeur_reference) * 100, 1)
            signe = "+" if ecart > 0 else ""
            contexte_ref = (
                f"\n- Référence communes similaires : {valeur_reference} {unite} "
                f"(écart : {signe}{ecart}%)"
            )
        except Exception:
            pass

    prompt = f"""Tu es un assistant spécialisé dans l'analyse des données d'une commune française à destination des citoyen·nes.

Indicateur : {libelle}
Libellé technique : {libelle_tech}
Valeur actuelle ({annee}) : {valeur} {unite}
Sens de l'indicateur : {sens_explication}{contexte_tendance}{contexte_ref}

Génère une analyse de cet indicateur pour un public citoyen non expert.
Réponds UNIQUEMENT avec du JSON valide :
{{
  "phrase_longue": "3-5 phrases : situation actuelle, tendance si connue, comparaison si disponible, lecture citoyenne. Langage accessible, sans jargon."
}}"""

    try:
        raw = _appel_mistral(prompt)
        parsed = _parse_json(raw)
        return {
            "phrase_longue": parsed.get("phrase_longue", "").strip(),
        }
    except Exception as e:
        print(f"[WARN] generer_interpretation_indicateur : {e}", flush=True)
        return None


def is_ai_ready() -> bool:
    """Vérifie si Mistral AI est configuré."""
    return bool(MISTRAL_API_KEY)
