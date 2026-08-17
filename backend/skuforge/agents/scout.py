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


# Hosts that serve automated clients a 403 from datacenter IPs. Verified
# against the deployed container: se.com and zoro.com both 403 there while the
# same URLs fetch fine from a residential connection — which is exactly why a
# run can succeed locally and return nothing once deployed. Their CDN-hosted
# spec sheets are unaffected, so these are demoted, never dropped: if a run
# finds nothing better, a possible 403 still beats no candidate at all.
BOT_BLOCKED_HOSTS = (
    "se.com", "schneider-electric.com/us", "zoro.com", "grainger.com",
    "homedepot.com", "lowes.com", "amazon.", "walmart.com", "ebay.",
)


def _is_pdf_url(url: str) -> bool:
    """Trust the URL over the model's flag — it hallucinated is_pdf=true for
    every plain HTML listing on one deployed run."""
    path = url.split("?", 1)[0].split("#", 1)[0].lower()
    return path.endswith(".pdf") or "/pdf/" in path or "p_doc_ref=" in url.lower()


def _likely_blocked(url: str) -> bool:
    host = url.split("//", 1)[-1].split("/", 1)[0].lower()
    return any(b in host for b in BOT_BLOCKED_HOSTS)


def run(sku: SKUInput, fixture_key: str | None = None) -> tuple[list[Source], float]:
    """Returns (sources ranked by fetchability then trust, cost_usd)."""
    search = llm.call_web_search(
        "scout",
        f"Find authoritative product data sources for this industrial part:\n"
        f"MPN: {sku.mpn}\nBrand: {sku.brand}\nDescription: {sku.description}\n\n"
        f"Search for: PDF datasheets and specification sheets, the official "
        f"{sku.brand} product page, and distributor listings.\n\n"
        f"IMPORTANT — prioritise **direct links to PDF files** (URLs ending in "
        f".pdf), especially spec sheets hosted on content-delivery domains such "
        f"as assets.*, images.*, cdn.*, download.*, or documents.*. These carry "
        f"the densest attribute data and remain reachable to automated clients, "
        f"whereas retailer and manufacturer HTML pages frequently block them. "
        f"Include at least three direct PDF links if they exist. "
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
    for s in sources:
        s.is_pdf = _is_pdf_url(s.url)

    # Rank by whether we can actually READ the source before ranking by how
    # much we'd trust it — a highly-trusted page that 403s contributes nothing,
    # and previously crowded fetchable CDN PDFs out of the top-N cut entirely.
    sources.sort(
        key=lambda s: (
            not s.is_pdf,                                    # real PDFs first
            _likely_blocked(s.url),                          # then unblocked hosts
            -config.SOURCE_TRUST.get(s.source_type.value, 0),  # then trust tier
        )
    )
    return (
        sources[: config.MAX_SOURCE_CANDIDATES],
        search.cost_usd + classify.cost_usd,
    )
