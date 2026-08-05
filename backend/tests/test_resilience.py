"""Degradation tests: a late API failure must not discard validated work."""
import os

os.environ["SKUFORGE_MOCK"] = "1"

import pytest  # noqa: E402

from skuforge import orchestrator  # noqa: E402
from skuforge.agents import composer  # noqa: E402
from skuforge.models import RecordStatus, SKUInput  # noqa: E402

SKU = SKUInput(mpn="HOM230CP", brand="Square D", description="30A 2 pole breaker")


@pytest.fixture
def failing_composer(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("credit_balance_exhausted")

    monkeypatch.setattr(composer, "run", boom)


def test_composer_failure_keeps_attributes(failing_composer):
    record = orchestrator.run_sku(SKU)
    assert record.attributes, "validated attributes must survive a copy failure"
    assert record.status == RecordStatus.needs_review
    assert record.seo_title == ""


def test_scout_failure_marks_record_failed(monkeypatch):
    from skuforge.agents import scout

    def boom(*args, **kwargs):
        raise RuntimeError("credit_balance_exhausted")

    monkeypatch.setattr(scout, "run", boom)
    record = orchestrator.run_sku(SKU)
    assert record.status == RecordStatus.failed
    assert not record.attributes
