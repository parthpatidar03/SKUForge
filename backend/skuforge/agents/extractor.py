"""EXTRACTOR: pull template attributes out of one evidence source.

HTML sources: cached text -> structured extraction.
PDF sources: file passed to the model directly (multimodal input).
"""
import base64
from pathlib import Path

from .. import cache, config, llm, taxonomy
from ..models import Source


def _schema(attribute_names: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "attributes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "enum": attribute_names},
                        "value": {"type": "string"},
                        "unit": {"type": "string"},
                        "quote": {
                            "type": "string",
                            "description": "Exact text from the source supporting this value",
                        },
                    },
                    "required": ["name", "value", "unit", "quote"],
                    "additionalProperties": False,
                },
            },
            "image_urls": {"type": "array", "items": {"type": "string"}},
            "certifications": {"type": "array", "items": {"type": "string"}},
            "equivalent_mpns": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["attributes", "image_urls", "certifications", "equivalent_mpns"],
        "additionalProperties": False,
    }


def run(
    source: Source, mpn: str, category: str, fixture_key: str | None = None
) -> tuple[dict | None, float, str]:
    """Returns (extraction dict or None if source unusable, cost_usd, skip_reason)."""
    template = taxonomy.get_template(category)
    attr_names = template["attributes"] + taxonomy.UNIVERSAL_ATTRIBUTES

    if config.MOCK_MODE:
        result = llm.call_structured("extractor", "", {}, fixture_key=fixture_key)
        per_url = result.data  # fixture: {url: extraction, "default": extraction}
        return per_url.get(source.url, per_url.get("default")), 0.0, ""

    meta = cache.fetch(source.url)
    if meta is None:
        return None, 0.0, cache.last_failure(source.url)
    source.fetched_at = meta["fetched_at"]
    # Cite where we actually landed, not the search engine's redirector.
    source.url = meta.get("final_url") or source.url

    prompt = (
        f"Extract product attributes for part MPN '{mpn}' "
        f"(category: {template['label']}) from this source.\n"
        f"Source URL: {source.url}\n\n"
        f"Only report attributes explicitly present in the source — never guess. "
        f"For each, include the exact supporting quote. Normalize units into the "
        f"'unit' field (e.g. value='30', unit='A'). Also collect image URLs, "
        f"certifications (UL, CE, CSA...), and any equivalent/replacement MPNs mentioned."
    )

    input_files = None
    # Trust the served content type over the classifier's guess: a URL that
    # merely looks like a PDF is often an HTML redirect, and handing that to
    # the model as a PDF fails with "the document has no pages".
    content_type = meta.get("content_type", "").lower()
    is_pdf = "pdf" in content_type or (
        source.is_pdf and not content_type.startswith("text/html")
    )
    if is_pdf:
        b64 = base64.b64encode(Path(meta["body_path"]).read_bytes()).decode()
        input_files = [{
            "type": "input_file",
            "filename": "datasheet.pdf",
            "file_data": f"data:application/pdf;base64,{b64}",
        }]
    else:
        text = cache.read_text(meta)
        if len(text) < 200:  # JS-only shell or interstitial
            return None, 0.0, "no readable text"
        prompt += f"\n\nSOURCE CONTENT:\n{text}"

    result = llm.call_structured(
        "extractor", prompt, _schema(attr_names), "extraction",
        fixture_key=fixture_key, input_files=input_files,
    )
    return result.data, result.cost_usd, ""
