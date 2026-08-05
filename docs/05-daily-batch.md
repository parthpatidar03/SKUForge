# Building the demo catalog on the free tier

The Gemini free tier allows **20 model calls per day** for `gemini-2.5-flash`.
One SKU costs roughly eight calls, so about **2 SKUs land per day**. The batch
runner is resumable, so the catalog is built by running one command daily until
`sample_batch.csv` is complete.

## The daily command

```bash
cd "E:/Web Dev/Hackathons/UniHack/backend" && python -m skuforge.batch sample_batch.csv
```

It prints how many SKUs are already enriched, works through the rest, and stops
cleanly the moment the day's quota is gone:

```
[LIVE via gemini] catalog of 10 SKUs — 3 already enriched, 7 to go, 2 at a time
  [ 1/7] Eaton BR230   circuit_breaker  12 attrs  1 conflict  needs-review
  QUOTA EXHAUSTED — abandoning remaining SKUs.
  ...
  6 SKU(s) left. Quota resets daily — re-run the same command tomorrow.
```

Nothing is lost or repeated: enriched SKUs are skipped next time, and evidence
already fetched is served from the cache rather than re-downloaded.

## Progress

`sample_batch.csv` holds 10 SKUs — 9 electrical plus one Moen plumbing valve as
cross-vertical proof. Expect roughly **5 days** to complete.

| Day | Command run | SKUs added | Catalog total |
|---|---|---|---|
| 5 Aug | initial runs | HOM230CP, 1451-2W | 2 |
| 6 Aug | | | |
| 7 Aug | | | |
| 8 Aug | | | |
| 9 Aug | | | |

(Fill in as it goes — this table is the evidence of a real catalog run for the
demo and the write-up.)

## Checking the catalog

```bash
cd "E:/Web Dev/Hackathons/UniHack/backend" && python -c "from skuforge import store; [print(f'{r.input.brand:12} {r.input.mpn:14} {r.category:16} {len(r.attributes):>2} attrs  {r.status.value}') for r in store.list_all()]"
```

Or open the dashboard at http://localhost:3005 — the catalog table lists every
enriched SKU and any row can be clicked to inspect its evidence.

## Housekeeping

Development runs leave failed attempts and duplicates in the store, which
distorts the catalog view and the aggregate stats. Before recording the demo:

```bash
cd "E:/Web Dev/Hackathons/UniHack/backend" && python -m skuforge.prune
```

Dry-run by default; add `--apply` to keep only the best record per MPN. The
database is copied to `skuforge.db.bak` first, so it is reversible.

## If the batch is needed sooner

A full 10-SKU run on OpenAI costs about **$0.25** — set `SKUFORGE_PROVIDER=openai`
with credits on the key and run the same command once. The free-tier path exists
to avoid that cost, not because the paid path is different.
