"""
Service de génération de résumés citoyens via Ollama.
"""
import os
import requests
import pdfplumber

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")

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


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extrait le texte brut d'un PDF."""
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
    return "\n\n".join(text_parts)


def generer_resume(pdf_path: str) -> str:
    """
    Extrait le texte du PDF et génère un résumé citoyen via Ollama.
    Retourne le résumé sous forme de texte.
    Lève une exception en cas d'erreur.
    """
    texte = extract_text_from_pdf(pdf_path)
    if not texte.strip():
        raise ValueError("Le PDF ne contient pas de texte extractible.")

    # Tronquer à 12 000 caractères pour rester dans le contexte du modèle
    texte_tronque = texte[:12000]

    prompt = PROMPT_TEMPLATE.format(contenu=texte_tronque)

    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=300,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("response", "").strip()


def is_ollama_ready() -> bool:
    """Vérifie si Ollama est disponible et si le modèle est téléchargé."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if r.status_code != 200:
            return False
        models = [m["name"] for m in r.json().get("models", [])]
        return any(OLLAMA_MODEL.split(":")[0] in m for m in models)
    except Exception:
        return False
