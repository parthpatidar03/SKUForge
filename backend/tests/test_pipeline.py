"""Smoke tests — run with SKUFORGE_MOCK=1: pytest -q"""
import os

os.environ["SKUFORGE_MOCK"] = "1"

from skuforge.models import AttributeStatus, SKUInput  # noqa: E402
from skuforge.orchestrator import run_sku  # noqa: E402

SKU = SKUInput(mpn="HOM230CP", brand="Square D", description="30A 2 pole breaker")


def test_pipeline_end_to_end():
    record = run_sku(SKU)
    assert record.category == "circuit_breaker"
    assert len(record.attributes) >= 8
    assert record.seo_title.startswith("Square D HOM230CP")
    assert record.sources, "scout found no sources"


def test_trust_engine_flags_conflict():
    record = run_sku(SKU)
    conflicts = [a for a in record.attributes if a.status == AttributeStatus.conflict]
    assert any(a.name == "weight_lbs" for a in conflicts), "weight conflict not flagged"
    weight = next(a for a in record.attributes if a.name == "weight_lbs")
    assert weight.confidence <= 0.5, "conflicted attribute must not auto-approve"
    assert weight.conflicting_values, "losing values must stay visible"


def test_verified_needs_two_sources():
    record = run_sku(SKU)
    amp = next(a for a in record.attributes if a.name == "amperage_rating")
    assert amp.status == AttributeStatus.verified
    assert len(amp.evidence) >= 2
    assert amp.confidence >= 0.9


def test_single_source_never_auto_approves():
    """One authoritative source is still one source — it must reach a human."""
    from skuforge import config

    record = run_sku(SKU)
    singles = [a for a in record.attributes if len(a.evidence) < 2]
    assert singles, "fixture should contain single-source attributes"
    for attr in singles:
        assert attr.confidence < config.AUTO_APPROVE_THRESHOLD, (
            f"{attr.name} auto-approved on a single source"
        )
