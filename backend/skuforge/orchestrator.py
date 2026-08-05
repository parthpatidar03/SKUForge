"""Per-SKU pipeline state machine. Emits PipelineEvents for the agent theatre."""
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from . import config, store, taxonomy
from .agents import classifier, composer, extractor, scout, validator
from .llm import QuotaExhausted
from .models import (
    AttributeStatus, PipelineEvent, ProductRecord, RecordStatus, SKUInput,
)

EventSink = Callable[[PipelineEvent], None]


def _fixture_key(sku: SKUInput) -> str:
    return sku.mpn.replace("/", "_").replace(" ", "_").upper()


def run_sku(
    sku: SKUInput,
    emit: Optional[EventSink] = None,
    record_id: Optional[str] = None,
) -> ProductRecord:
    rid = record_id or uuid.uuid4().hex[:12]
    started = time.monotonic()
    record = ProductRecord(id=rid, input=sku)
    fk = _fixture_key(sku) if config.MOCK_MODE else None
    copy_failed = False

    def ev(agent: str, step: str, **detail):
        if emit:
            emit(PipelineEvent(record_id=rid, agent=agent, step=step, detail=detail))

    try:
        ev("scout", f"Hunting sources for {sku.brand} {sku.mpn}")
        sources, c1 = scout.run(sku, fixture_key=fk)
        record.sources = sources
        record.cost_usd += c1
        ev("scout", f"Found {len(sources)} sources",
           sources=[{"url": s.url, "type": s.source_type.value} for s in sources])

        ev("classifier", "Classifying product category")
        category, cat_conf, c2 = classifier.run(sku, fixture_key=fk)
        record.category, record.category_confidence = category, cat_conf
        record.cost_usd += c2
        template = taxonomy.get_template(category)
        ev("classifier", f"Category: {template['label']} ({cat_conf:.0%})",
           category=category)

        # Sources are independent — extract them concurrently. This is the
        # single biggest lever on per-SKU latency (each source is a network
        # fetch plus a model call), and it is what makes catalog-scale runs
        # practical.
        workers = max(1, min(len(sources), config.MAX_PARALLEL_EXTRACTIONS))
        ev("extractor",
           f"Extracting from {len(sources)} sources ({workers} at a time)")
        results: dict[str, tuple] = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(extractor.run, src, sku.mpn, category, fk): src
                for src in sources
            }
            for future in as_completed(futures):
                src = futures[future]
                try:
                    results[src.url] = future.result()
                except Exception as exc:
                    results[src.url] = (None, 0.0, f"error: {type(exc).__name__}")
                    ev("extractor", f"Error on {src.url[:60]}: {exc}", url=src.url)

        per_source = []
        for src in sources:  # replay in trust order for deterministic output
            extraction, c3, skip_reason = results.get(src.url, (None, 0.0, "not run"))
            record.cost_usd += c3
            if extraction:
                per_source.append((src.url, src.source_type, extraction))
                ev("extractor",
                   f"{len(extraction.get('attributes', []))} attributes from "
                   f"{src.source_type.value} source",
                   url=src.url)
            else:
                ev("extractor", f"Skipped — {skip_reason}", url=src.url)
            if src.is_pdf and src.url not in record.datasheet_urls:
                record.datasheet_urls.append(src.url)

        ev("validator", f"Cross-validating {len(per_source)} extractions")
        attrs, images, certs, equivs, c4 = validator.run(per_source, fixture_key=fk)
        record.attributes = attrs
        record.image_urls = images
        record.certifications = certs
        record.equivalent_mpns = equivs
        record.cost_usd += c4
        conflicts = [a for a in attrs if a.status == AttributeStatus.conflict]
        ev("validator",
           f"{len(attrs)} attributes merged, {len(conflicts)} conflicts flagged",
           conflicts=[a.name for a in conflicts])

        # Copywriting is the last and least critical stage: validated
        # attributes are the expensive part, so an API failure here must not
        # discard them.
        ev("composer", "Writing commerce copy")
        try:
            copy, c5 = composer.run(
                sku, template["label"], attrs, certs, fixture_key=fk
            )
            record.seo_title = copy["seo_title"]
            record.short_description = copy["short_description"]
            record.long_description = copy["long_description"]
            record.search_synonyms = copy["search_synonyms"]
            record.cost_usd += c5
        except QuotaExhausted:
            raise  # budget is gone; the caller needs to stop, not just this SKU
        except Exception as exc:
            copy_failed = True
            ev("composer", f"Copy generation failed, keeping attributes: {exc}")

        needs_review = (
            any(a.confidence < config.AUTO_APPROVE_THRESHOLD for a in attrs)
            or bool(conflicts)
            or not attrs
            or copy_failed
        )
        record.status = (
            RecordStatus.needs_review if needs_review else RecordStatus.auto_approved
        )
    except QuotaExhausted:
        # Save whatever was validated, then let this one through: the caller
        # (batch runner, API) must know the budget is gone so it can stop,
        # rather than watching every remaining SKU fail the same way.
        record.status = (
            RecordStatus.needs_review if record.attributes else RecordStatus.failed
        )
        ev("orchestrator", "Provider quota exhausted — stopping")
        record.duration_s = round(time.monotonic() - started, 1)
        store.save(record)
        raise
    except Exception as exc:
        # Keep whatever was validated — a partial record with sourced
        # attributes is far more useful than losing the run entirely.
        record.status = (
            RecordStatus.needs_review if record.attributes else RecordStatus.failed
        )
        ev("orchestrator", f"Pipeline stopped early: {exc}")
    finally:
        record.duration_s = round(time.monotonic() - started, 1)
        store.save(record)

    ev("orchestrator",
       f"Done in {record.duration_s}s, ${record.cost_usd:.4f}, "
       f"status: {record.status.value}")
    return record
