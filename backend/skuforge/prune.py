"""Tidy the record store for a demo: python -m skuforge.prune [--apply]

Development leaves the database full of repeated runs of the same SKU and
failed attempts, which makes the catalog view and the aggregate stats
meaningless. This keeps the best record per MPN — richest attribute set, newest
as the tiebreak — and drops the rest.

Dry-run by default. `--apply` copies the database to skuforge.db.bak first, so
the operation is always reversible.
"""
import shutil
import sqlite3
import sys

from . import config, store
from .models import RecordStatus


def choose_keepers() -> tuple[list, list]:
    records = store.list_all()
    best: dict[str, object] = {}
    for r in records:
        if r.status == RecordStatus.failed or not r.attributes:
            continue
        key = f"{r.input.brand.lower()}|{r.input.mpn.lower()}"
        current = best.get(key)
        # A live-provider record must never lose to a mock replay, however
        # recent — test runs re-save mock records with a fresh timestamp, and
        # ranking on (attrs, created_at) alone let a fake record win the slot
        # a real enrichment had earned. Provider authenticity outranks both.
        rank = (r.provider != "mock", len(r.attributes), r.created_at)
        current_rank = (
            (current.provider != "mock", len(current.attributes), current.created_at)  # type: ignore[union-attr]
            if current is not None
            else None
        )
        if current_rank is None or rank > current_rank:
            best[key] = r
    keep_ids = {r.id for r in best.values()}  # type: ignore[attr-defined]
    return list(best.values()), [r for r in records if r.id not in keep_ids]


def main() -> None:
    apply = "--apply" in sys.argv
    keepers, dropping = choose_keepers()

    print(f"Keeping {len(keepers)} record(s) — best per MPN:")
    for r in sorted(keepers, key=lambda x: x.input.mpn):
        print(f"  {r.input.brand:<12} {r.input.mpn:<14} {r.category:<16} "
              f"{len(r.attributes):>2} attrs  {r.status.value}")
    print(f"\nDropping {len(dropping)} record(s) "
          f"(failed runs and superseded duplicates).")

    if not apply:
        print("\nDry run. Re-run with --apply to make the change "
              "(the database is backed up first).")
        return

    backup = config.DB_PATH.with_suffix(".db.bak")
    shutil.copy2(config.DB_PATH, backup)
    with sqlite3.connect(config.DB_PATH) as conn:
        conn.executemany(
            "DELETE FROM records WHERE id = ?", [(r.id,) for r in dropping]
        )
    print(f"\nDone. Backup written to {backup.name}.")


if __name__ == "__main__":
    main()
