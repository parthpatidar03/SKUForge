"""CLASSIFIER: pick the category template for a SKU."""
from .. import llm, taxonomy
from ..models import SKUInput

SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": taxonomy.category_ids()},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reasoning": {"type": "string"},
    },
    "required": ["category", "confidence", "reasoning"],
    "additionalProperties": False,
}


def run(sku: SKUInput, fixture_key: str | None = None) -> tuple[str, float, float]:
    """Returns (category_id, confidence, cost_usd)."""
    result = llm.call_structured(
        "classifier",
        f"Classify this industrial product into exactly one category.\n"
        f"MPN: {sku.mpn}\nBrand: {sku.brand}\nDescription: {sku.description}\n\n"
        f"Categories: {', '.join(taxonomy.category_ids())}\n"
        f"Use 'generic' only if nothing else fits.",
        SCHEMA,
        "classification",
        fixture_key=fixture_key,
    )
    return result.data["category"], result.data["confidence"], result.cost_usd
