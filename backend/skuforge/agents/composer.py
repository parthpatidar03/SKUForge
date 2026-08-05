"""COMPOSER: commerce copy — SEO title, descriptions, search synonyms.

Only writes from validated attributes; instructed never to introduce specs
that aren't in the record.
"""
import json

from .. import llm
from ..models import Attribute, SKUInput

SCHEMA = {
    "type": "object",
    "properties": {
        "seo_title": {"type": "string", "maxLength": 150},
        "short_description": {"type": "string", "maxLength": 300},
        "long_description": {"type": "string"},
        "search_synonyms": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["seo_title", "short_description", "long_description", "search_synonyms"],
    "additionalProperties": False,
}


def run(
    sku: SKUInput,
    category_label: str,
    attributes: list[Attribute],
    certifications: list[str],
    fixture_key: str | None = None,
) -> tuple[dict, float]:
    facts = {
        a.name: f"{a.value} {a.unit}".strip()
        for a in attributes
        if a.confidence >= 0.5 and a.status.value != "conflict"
    }
    result = llm.call_structured(
        "composer",
        f"Write commerce-ready product copy for a B2B distributor catalog.\n"
        f"Product: {sku.brand} {sku.mpn} — {category_label}\n"
        f"Original description: {sku.description}\n"
        f"Verified attributes: {json.dumps(facts)}\n"
        f"Certifications: {', '.join(certifications) or 'none listed'}\n\n"
        f"Rules: use ONLY the facts above — never invent specs. "
        f"SEO title format: Brand MPN key-specs category. "
        f"Long description: 2 short paragraphs, professional B2B tone, no fluff. "
        f"Search synonyms: 5-10 terms an electrician or contractor would type.",
        SCHEMA,
        "copy",
        fixture_key=fixture_key,
    )
    return result.data, result.cost_usd
