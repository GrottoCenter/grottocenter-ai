import json
import logging
import re
import ollama as ollama_client

from pipeline_ia.config import settings
from pipeline_ia.models import DocumentMetadata, DocumentAnalysis

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es un assistant spécialisé dans l'analyse de documents scientifiques, 
en particulier dans le domaine de la spéléologie et des sciences karstiques.

Tu dois analyser le texte fourni et en extraire des informations structurées.
Tu dois répondre UNIQUEMENT avec un JSON valide. Pas de texte avant ou après le JSON.
Pas de markdown, pas de ```json```, juste le JSON brut.

Règles :
- Si une information n'est pas trouvable, utilise une valeur par défaut ("unknown", [], etc.).
- Le champ "iso_code" doit être au format ISO 639-1 (2 lettres : fr, en, es, de, it, etc.).
- Si le document contient plusieurs articles (comme dans une revue), liste-les tous dans "articles".
- Le "confidence_score" reflète ta confiance globale dans l'extraction (0.0 à 1.0).
- Pour "caves_mentioned" et "regions_mentioned", ne liste que celles explicitement citées.
- "document_type" peut être : article, rapport, revue, thèse, livre, bulletin, guide, autre."""

JSON_SCHEMA = {
    "title": "string",
    "authors": ["string"],
    "summary": "string (résumé en 3-5 phrases)",
    "language": "string (nom complet de la langue)",
    "iso_code": "string (code ISO 639-1, 2 lettres)",
    "year": "integer ou null",
    "keywords": ["string"],
    "document_type": "string",
    "articles": [
        {
            "title": "string",
            "authors": ["string"],
            "summary": "string",
            "page_start": "integer ou null",
            "page_end": "integer ou null",
        }
    ],
    "caves_mentioned": ["string"],
    "regions_mentioned": ["string"],
    "confidence_score": "float entre 0.0 et 1.0",
}


def build_prompt(
    ocr_text: str,
    metadata: DocumentMetadata | None = None,
    max_chars: int = None,
) -> str:
    """Construit le prompt pour le LLM."""
    max_chars = max_chars or settings.llm_max_text_chars
    parts = []

    # Métadonnées connues
    if metadata:
        known = metadata.model_dump(exclude_none=True)
        if known:
            parts.append(
                f"Métadonnées déjà connues du document :\n{json.dumps(known, ensure_ascii=False)}"
            )

    # Texte OCR (tronqué si nécessaire)
    text = ocr_text
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[... texte tronqué ...]"

    parts.append(f"Contenu extrait du document :\n\n{text}")

    # Schéma attendu
    parts.append(
        f"Analyse ce document et retourne UN JSON valide avec cette structure :\n"
        f"{json.dumps(JSON_SCHEMA, ensure_ascii=False, indent=2)}"
    )

    return "\n\n---\n\n".join(parts)


def extract_json_from_response(response: str) -> dict:
    """Extrait le JSON d'une réponse LLM potentiellement bruitée."""
    # Essai direct
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # Chercher un bloc JSON entre accolades
    match = re.search(r"\{.*\}", response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Chercher un bloc ```json ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    logger.error(f"Impossible d'extraire le JSON de la réponse LLM")
    logger.debug(f"Réponse brute: {response[:500]}")
    return {}


def analyze_with_ollama(
    ocr_text: str,
    metadata: DocumentMetadata | None = None,
    model: str = None,
    base_url: str = None,
) -> DocumentAnalysis:
    """
    Analyse le texte OCR via un LLM local Ollama.

    Args:
        ocr_text: Texte extrait par OCR.
        metadata: Métadonnées connues du document.
        model: Nom du modèle Ollama.
        base_url: URL du serveur Ollama.

    Returns:
        DocumentAnalysis structuré.
    """
    model = model or settings.ollama_model
    base_url = base_url or settings.ollama_base_url

    prompt = build_prompt(ocr_text, metadata)

    logger.info(f"Envoi au LLM local ({model}), {len(prompt)} caractères")

    client = ollama_client.Client(host=base_url)

    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        options={
            "temperature": 0.1,
            "num_ctx": 8192,  # Fenêtre de contexte
            "num_predict": 4096,  # Tokens max en sortie
        },
    )

    raw_response = response["message"]["content"]
    logger.debug(f"Réponse LLM brute ({len(raw_response)} chars)")

    data = extract_json_from_response(raw_response)

    if not data:
        logger.warning("Aucun JSON valide extrait, retour d'une analyse vide")
        return DocumentAnalysis()

    # Nettoyage et validation
    try:
        analysis = DocumentAnalysis(**data)
    except Exception as e:
        logger.warning(f"Erreur de validation Pydantic: {e}")
        # Essayer de sauver ce qui est sauvable
        safe_data = {}
        for key in DocumentAnalysis.model_fields:
            if key in data:
                safe_data[key] = data[key]
        try:
            analysis = DocumentAnalysis(**safe_data)
        except Exception:
            analysis = DocumentAnalysis()

    logger.info(f"Analyse terminée: '{analysis.title}' (confiance: {analysis.confidence_score:.2f})")
    return analysis