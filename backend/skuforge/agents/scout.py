"""SCOUT: given MPN+brand, find candidate evidence sources via web search."""
import json

from .. import config, llm
from ..models import SKUInput, Source, SourceType

SOURCE_LIST_SCHEMA = {
    "type": "object",
    "properties": {
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "title": {"type": "string"},
                    "source_type": {
                        "type": "string",
                        "enum": ["manufacturer", "distributor", "marketplace", "other"],
                    },
                    "is_pdf": {"type": "boolean"},
                },
                "required": ["url", "title", "source_type", "is_pdf"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["sources"],
    "additionalProperties": False,
}


def run(sku: SKUInput, fixture_key: str | None = None) -> tuple[list[Source], float]:
    """Returns (sources ranked by trust, cost_usd)."""
    search = llm.call_web_search(
        "scout",
        f"Find authoritative product data sources for this industrial part:\n"
        f"MPN: {sku.mpn}\nBrand: {sku.brand}\nDescription: {sku.description}\n\n"
        f"Search for: the official {sku.brand} product page, PDF datasheet/spec sheet, "
        f"and listings on distributor sites (Grainger, Zoro, Platt, etc). "
        f"List every distinct URL you find with its page title.",
        fixture_key=fixture_key,
    )

    classify = llm.call_structured(
        "relevance",
        "From this research output, extract the list of product-data source URLs. "
        "Classify each: 'manufacturer' (brand's own site), 'distributor' "
        "(Grainger/Zoro/Platt/electrical distributors), 'marketplace' (Amazon/eBay), "
        "or 'other'. Mark is_pdf for direct PDF links. Skip forums and videos.\n\n"
        + json.dumps(search.data),
        SOURCE_LIST_SCHEMA,
        "source_list",
        fixture_key=fixture_key,
    )

    sources = [Source(**s) for s in classify.data["sources"]]
    sources.sort(key=lambda s: -config.SOURCE_TRUST.get(s.source_type.value, 0))
    return sources[: config.MAX_SOURCES_PER_SKU], search.cost_usd + classify.cost_usd
