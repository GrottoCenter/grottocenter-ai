import json
import re
from typing import List, Optional

import ollama as ollama_client

from worker.src.ollamaconfig import OllamaConfig
from backendV2.model.Document import DocumentMetadata


SYSTEM_PROMPT = """
Tu extrais des métadonnées de documents scientifiques.
Réponds uniquement en JSON valide, sans markdown.
Si l'information est absente: null ou [].
N'invente jamais.
S'il n'y a pas de résumé explicite, rédige un bref résumé.
Le résumé doit être dans la langue du document.

"""


JSON_SCHEMA = {
    "title": "string|null",
    "authors": ["string"],
    "iso3166": ["string"],
    "editor": "string|null",
    "issue": "string|null",
    "issn": "string|null",
    "isbn": "string|null",
}


def _extract_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass

    return {}


def extract_metadata_with_llm(ocr_text: str, known_metadata: Optional[DocumentMetadata] = None,) -> DocumentMetadata:
    text = (ocr_text or "").strip()
    if not text:
        return DocumentMetadata()

    if OllamaConfig.max_input_chars is not None and len(text) > OllamaConfig.max_input_chars:
        print(f"Texte trop long")
        text = text[:OllamaConfig.max_input_chars] + "\n\n[texte tronque]"

    known = known_metadata.model_dump(mode="json", exclude_none=True) if known_metadata else {}

    prompt = (
        "Texte OCR:\n"
        + text
        + "\n\nMetadonnees deja connues (ne pas les contredire):\n"
        + json.dumps(known, ensure_ascii=False)
        + "\n\nSchema attendu:\n"
        + json.dumps(JSON_SCHEMA, ensure_ascii=False)
    )

    client = ollama_client.Client(host=OllamaConfig.base_url)
    resp = client.chat(
        model=OllamaConfig.model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        options={
            "temperature": OllamaConfig.temperature,
            "num_ctx": OllamaConfig.ctx,
            "num_predict": OllamaConfig.num_predict,
        },
        format="json",
    )

    data = _extract_json(resp["message"]["content"])
    if not data:
        return DocumentMetadata()

    safe = {k: v for k, v in data.items() if k in DocumentMetadata.model_fields}
    try:
        return DocumentMetadata(**safe)
    except Exception:
        return DocumentMetadata()
    
def generate_global_summary(chunks: List[str], language: str = "français") -> Optional[str]:
    client = ollama_client.Client(host=OllamaConfig.base_url)
    partial_summaries = []
    
    # Étape 1 : Map (Résumé de chaque bloc)
    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
        print(f"Génération du résumé intermédiaire pour le bloc {i+1}/{len(chunks)}")
        prompt = f"Texte (Partie {i+1}/{len(chunks)}) :\n{chunk}\n\nFais un résumé synthétique très concis et factuel de cette partie uniquement. Ne rajoute pas d'introduction."
        
        resp = client.chat(
            model=OllamaConfig.model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.2, "num_ctx": OllamaConfig.ctx, "num_predict": 512}
        )
        partial_summaries.append(resp["message"]["content"].strip())
        
    if not partial_summaries:
        return None
        
    # Étape 2 : Reduce (Fusion des résumés)
    if len(partial_summaries) == 1:
        return partial_summaries[0]
        
    print("Fusion des résumés intermédiaires...")
    combined = "\n\n".join([f"--- Résumé de la Partie {i+1} ---\n{s}" for i, s in enumerate(partial_summaries)])
    
    final_prompt = (
        f"Voici les résumés chronologiques des {len(chunks)} parties d'un document :\n\n{combined}\n\n"
        f"Rédige un résumé global fluide, détaillé et cohérent de l'ensemble du document. "
        f"Le résumé final doit impérativement être structuré et rédigé en langue : {language}. "
        f"Ne fais pas référence aux 'parties', rédige directement le résumé global."
    )
    
    resp_final = client.chat(
        model=OllamaConfig.model,
        messages=[{"role": "user", "content": final_prompt}],
        options={"temperature": 0.3, "num_ctx": OllamaConfig.ctx, "num_predict": 1024}
    )
    
    return resp_final["message"]["content"].strip()