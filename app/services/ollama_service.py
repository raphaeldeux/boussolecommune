"""
Service de génération de résumés citoyens.
Utilise Groq (si GROQ_API_KEY défini) ou Ollama en fallback.
"""
import os
import requests
import pdfplumber

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

PROMPT_TEMPLATE = """Tu es un assistant chargé de résumer des procès-verbaux de conseils municipaux pour les citoyens.

Voici le contenu du procès-verbal :

{contenu}

---

Rédige un résumé clair et accessible pour les citoyens, structuré par thématique (par exemple : Finances, Urbanisme, Vie associative, Environnement, Social, Divers...). Ne retiens que les thématiques présentes dans le document.

Pour chaque thématique :
- Indique les principales délibérations et décisions prises
- Précise les résultats des votes quand ils sont mentionnés (pour / contre / abstentions)
- Utilise un langage simple, sans jargon administratif

Commence directement par le résumé, sans introduction."""

PROMPT_STRUCTURE = """Tu es un assistant qui extrait les délibérations d'un procès-verbal de conseil municipal.

Voici le contenu du procès-verbal :

{contenu}

---

Génère un JSON structuré représentant les thématiques et délibérations. Réponds UNIQUEMENT avec du JSON valide, sans texte avant ni après.

Format attendu :
{{
  "themes": [
    {{
      "titre": "Nom de la thématique",
      "resume": "Résumé de synthèse en 2-4 phrases accessibles aux citoyens.",
      "deliberations": [
        {{
          "titre": "Intitulé de la délibération",
          "description": "Description claire de la décision prise.",
          "vote": {{"pour": 15, "contre": 2, "abstentions": 1}}
        }}
      ]
    }}
  ]
}}

Règles :
- "vote" est null si aucun vote n'est mentionné
- "deliberations" peut être [] si le thème n'a pas de délibération formelle
- N'inclure que les thèmes réellement présents dans le document
- Répondre UNIQUEMENT avec le JSON, sans explication"""


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extrait le texte brut d'un PDF."""
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
    return "\n\n".join(text_parts)


def _generer_via_groq(prompt: str) -> str:
    """Génère un résumé via l'API Groq."""
    response = requests.post(
        GROQ_API_URL,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def _generer_via_ollama(prompt: str) -> str:
    """Génère un résumé via Ollama local."""
    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=300,
    )
    response.raise_for_status()
    return response.json().get("response", "").strip()


def generer_resume(pdf_path: str):
    """
    Extrait le texte du PDF et génère résumé + structure JSON.
    Retourne un tuple (resume_texte: str, resume_structure: str | None).
    """
    import json as _json

    texte = extract_text_from_pdf(pdf_path)
    if not texte.strip():
        raise ValueError("Le PDF ne contient pas de texte extractible.")

    texte_tronque = texte[:12000]

    # Premier appel : résumé en prose
    prompt_prose = PROMPT_TEMPLATE.format(contenu=texte_tronque)
    if GROQ_API_KEY:
        resume_texte = _generer_via_groq(prompt_prose)
    else:
        resume_texte = _generer_via_ollama(prompt_prose)

    # Deuxième appel : JSON structuré (enrichissement optionnel, Groq uniquement)
    resume_structure = None
    if GROQ_API_KEY:
        try:
            prompt_json = PROMPT_STRUCTURE.format(contenu=texte_tronque)
            raw_json = _generer_via_groq(prompt_json)
            parsed = _json.loads(raw_json)
            if "themes" in parsed:
                resume_structure = raw_json
        except Exception as e:
            print(f"[WARN] Génération JSON structuré échouée : {e}", flush=True)

    return resume_texte, resume_structure


def is_ollama_ready() -> bool:
    """Vérifie si un backend de génération est disponible (Groq ou Ollama)."""
    if GROQ_API_KEY:
        return True
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if r.status_code != 200:
            return False
        models = [m["name"] for m in r.json().get("models", [])]
        return any(OLLAMA_MODEL.split(":")[0] in m for m in models)
    except Exception:
        return False
