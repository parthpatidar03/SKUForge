"""Scout must rank sources by whether they can actually be READ.

Regression test for the deployed-only failure: every enrichment returned zero
attributes because scout's top-N were se.com/zoro.com HTML pages, which serve a
403 to datacenter IPs. The identical code worked locally, where scout happened
to surface CDN-hosted PDFs instead. Fetchability now outranks trust tier.
"""
import os

os.environ["SKUFORGE_MOCK"] = "1"

from skuforge.agents.scout import (  # noqa: E402
    BOT_BLOCKED_HOSTS, _is_pdf_url, _likely_blocked,
)
from skuforge.models import Source  # noqa: E402
from skuforge import config  # noqa: E402


def test_pdf_detection_uses_url_not_model_flag():
    assert _is_pdf_url("https://assets.unilogcorp.com/DOC/spec.pdf")
    assert _is_pdf_url("https://download.schneider-electric.com/files?p_Doc_Ref=HOM230CP")
    # A model once flagged every one of these as is_pdf=true.
    assert not _is_pdf_url("https://www.zoro.com/product/i/G8635336/")
    assert not _is_pdf_url("https://www.se.com/us/en/product/HOM230CP/")


def test_known_bot_blocking_hosts_are_recognised():
    assert _likely_blocked("https://www.se.com/us/en/product/HOM230CP/")
    assert _likely_blocked("https://www.zoro.com/foo/i/G1/")
    assert not _likely_blocked("https://assets.unilogcorp.com/x.pdf")
    assert BOT_BLOCKED_HOSTS, "blocklist must not be empty"


def _rank(sources: list[Source]) -> list[Source]:
    """Mirror of scout.run()'s ordering."""
    return sorted(
        sources,
        key=lambda s: (
            not s.is_pdf,
            _likely_blocked(s.url),
            -config.SOURCE_TRUST.get(s.source_type.value, 0),
        ),
    )


def test_fetchable_cdn_pdf_outranks_blocked_manufacturer_page():
    """The exact shape that broke production: a manufacturer HTML page (highest
    trust, unreadable from a datacenter IP) against a distributor CDN PDF."""
    blocked_mfr = Source(
        url="https://www.se.com/us/en/product/HOM230CP/",
        title="Schneider product page",
        source_type="manufacturer",
        is_pdf=False,
    )
    cdn_pdf = Source(
        url="https://assets.unilogcorp.com/267/ITEM/DOC/spec.pdf",
        title="Spec sheet",
        source_type="distributor",
        is_pdf=True,
    )
    ranked = _rank([blocked_mfr, cdn_pdf])
    assert ranked[0].url == cdn_pdf.url, (
        "a readable CDN PDF must outrank a higher-trust page that 403s — "
        "otherwise it is crowded out of the top-N and the run yields nothing"
    )


def test_top_n_keeps_at_least_one_readable_source():
    """With more candidates than MAX_SOURCES_PER_SKU, readable ones survive."""
    blocked = [
        Source(url=f"https://www.zoro.com/p/{i}/", title=f"Zoro {i}",
               source_type="distributor", is_pdf=False)
        for i in range(config.MAX_SOURCES_PER_SKU + 2)
    ]
    pdf = Source(
        url="https://images.thdstatic.com/catalog/pdfImages/spec.pdf",
        title="Spec", source_type="distributor", is_pdf=True,
    )
    top = _rank(blocked + [pdf])[: config.MAX_SOURCES_PER_SKU]
    assert any(s.is_pdf for s in top), "readable PDF was crowded out of the cut"
