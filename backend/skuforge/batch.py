"""Catalog runner: python -m skuforge.batch <csv> [limit] [--force]

Processes a CSV of bare SKUs through the pipeline with bounded concurrency and
prints a throughput/cost/quality summary — the scalability story in one command.

Runs are **resumable**: SKUs already enriched are skipped, so on a metered free
tier the same command can be run each day and will pick up where the last one
stopped. `--force` re-enriches everything.
"""
import csv
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import config, store
from .llm import QuotaExhausted
from .models import AttributeStatus, RecordStatus, SKUInput
from .orchestrator import run_sku


def already_enriched() -> set[str]:
    """brand|mpn keys that already have a usable record."""
    return {
        f"{r.input.brand.lower()}|{r.input.mpn.lower()}"
        for r in store.list_all()
        if r.status != RecordStatus.failed and r.attributes
    }


def load(path: Path, limit: int | None) -> list[SKUInput]:
    rows = list(csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines()))
    skus = [
        SKUInput(
            mpn=r["mpn"].strip(),
            brand=r.get("brand", "").strip(),
            description=r.get("description", "").strip(),
        )
        for r in rows
        if r.get("mpn", "").strip()
    ]
    return skus[:limit] if limit else skus


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python -m skuforge.batch <csv> [limit]")
        sys.exit(1)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    path = Path(args[0])
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    limit = int(args[1]) if len(args) > 1 else None

    catalog = load(path, limit)
    if force:
        skus, skipped = catalog, 0
    else:
        done_keys = already_enriched()
        skus = [
            s for s in catalog
            if f"{s.brand.lower()}|{s.mpn.lower()}" not in done_keys
        ]
        skipped = len(catalog) - len(skus)

    mode = "MOCK" if config.MOCK_MODE else f"LIVE via {config.PROVIDER}"
    print(f"[{mode}] catalog of {len(catalog)} SKUs — "
          f"{skipped} already enriched, {len(skus)} to go, "
          f"{config.BATCH_CONCURRENCY} at a time\n")
    if not skus:
        print("Catalog complete. Nothing to do.")
        return

    started = time.monotonic()
    records = []
    quota_hit = False
    with ThreadPoolExecutor(max_workers=config.BATCH_CONCURRENCY) as pool:
        futures = {pool.submit(run_sku, sku): sku for sku in skus}
        for i, future in enumerate(as_completed(futures), 1):
            sku = futures[future]
            try:
                rec = future.result()
                records.append(rec)
                conflicts = sum(
                    1 for a in rec.attributes if a.status == AttributeStatus.conflict
                )
                print(f"  [{i:>2}/{len(skus)}] {sku.brand} {sku.mpn:<14} "
                      f"{rec.category:<16} {len(rec.attributes):>2} attrs  "
                      f"{conflicts} conflict  {rec.status.value}")
            except QuotaExhausted as exc:
                # Every remaining SKU would fail the same way; stop rather than
                # burn minutes proving it.
                if not quota_hit:
                    quota_hit = True
                    print(f"\n  QUOTA EXHAUSTED — abandoning remaining SKUs.\n  {exc}\n")
                for f in futures:
                    f.cancel()
            except Exception as exc:
                print(f"  [{i:>2}/{len(skus)}] {sku.brand} {sku.mpn:<14} FAILED: {exc}")

    elapsed = time.monotonic() - started
    done = [r for r in records if r.status != RecordStatus.failed]
    attrs = sum(len(r.attributes) for r in done)
    flagged = sum(
        1 for r in done for a in r.attributes
        if a.confidence < config.AUTO_APPROVE_THRESHOLD
    )
    auto = sum(1 for r in done if r.status == RecordStatus.auto_approved)
    cost = sum(r.cost_usd for r in done)

    print(f"\n{'='*58}\nBATCH SUMMARY")
    print(f"  SKUs completed        {len(done)}/{len(skus)}")
    print(f"  Wall time             {elapsed:.0f}s "
          f"({elapsed/max(len(done),1):.0f}s per SKU)")
    print(f"  Total cost            ${cost:.4f} "
          f"(${cost/max(len(done),1):.4f} per SKU)")
    print(f"  Attributes generated  {attrs} "
          f"({attrs/max(len(done),1):.1f} per SKU)")
    print(f"  Auto-approved records {auto}/{len(done)}")
    print(f"  Attributes to review  {flagged}/{attrs} "
          f"({100*flagged/max(attrs,1):.0f}%)")
    print(f"  Human effort saved    {100*(1-flagged/max(attrs,1)):.0f}% of fields "
          f"need no human touch")

    remaining = len(skus) - len(done)
    if quota_hit and remaining > 0:
        print(f"\n  {remaining} SKU(s) left. Quota resets daily — re-run the same "
              f"command tomorrow and it will resume from here.")


if __name__ == "__main__":
    main()
