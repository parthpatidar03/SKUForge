"""Quota exhaustion must reach the caller so a batch can stop early."""
import os

os.environ["SKUFORGE_MOCK"] = "1"

import pytest  # noqa: E402

from skuforge import llm, orchestrator  # noqa: E402
from skuforge.agents import composer  # noqa: E402
from skuforge.llm import QuotaExhausted  # noqa: E402
from skuforge.models import RecordStatus, SKUInput  # noqa: E402

SKU = SKUInput(mpn="HOM230CP", brand="Square D", description="30A 2 pole breaker")

DAILY = "429 RESOURCE_EXHAUSTED 'GenerateRequestsPerDayPerProjectPerModel-FreeTier'"
PER_MINUTE = "429 RESOURCE_EXHAUSTED rate limit exceeded"


def test_daily_quota_is_not_retried():
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise RuntimeError(DAILY)

    with pytest.raises(QuotaExhausted):
        llm._with_retry(boom)
    assert calls["n"] == 1, "daily quota must fail fast, not retry"


def test_per_minute_limit_is_retried(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda _: None)
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise RuntimeError(PER_MINUTE)

    with pytest.raises(RuntimeError):
        llm._with_retry(boom)
    assert calls["n"] > 1, "per-minute limits should be retried"


def test_quota_exhaustion_propagates_but_saves_partial(monkeypatch):
    """Partial work is persisted, and the caller still learns to stop."""
    def boom(*args, **kwargs):
        raise QuotaExhausted("out of daily quota")

    monkeypatch.setattr(composer, "run", boom)
    with pytest.raises(QuotaExhausted):
        orchestrator.run_sku(SKU)

    from skuforge import store
    saved = store.list_all()[0]
    assert saved.attributes, "validated attributes must still be persisted"
    assert saved.status == RecordStatus.needs_review
