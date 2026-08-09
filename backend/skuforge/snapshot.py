"""Turn a real enriched record into mock fixtures:
    python -m skuforge.snapshot <MPN> [--force]

Hand-written fixtures drift from reality. This reconstructs a fixture set from
a record the pipeline actually produced, so `SKUFORGE_MOCK=1` replays genuine
enrichment — same sources, same extracted values, same conflicts — with no API
calls and no network.

That matters for two reasons: the test suite exercises real data shapes, and a
demo can be recorded without depending on a live provider, a live website, or
today's quota.
"""
import json
import sys
from collections import defaultdict

from . import config, store
from .models import ProductRecord


def build_fixtures(record: ProductRecord) -> dict[str, object]:
    """Rebuild each stage's output from the finished record."""
    citations = [{"url": s.url, "title": s.title} for s in record.sources]

    scout = {
        "text": (
            f"Sources located for {record.input.brand} {record.input.mpn}: "
            + ", ".join(s.url for s in record.sources)
        ),
        "citations": citations,
    }

    relevance = {
        "sources": [
            {
                "url": s.url,
                "title": s.title,
                "source_type": s.source_type.value,
                "is_pdf": s.is_pdf,
            }
            for s in record.sources
        ]
    }

    classifier = {
        "category": record.category,
        "confidence": record.category_confidence,
        "reasoning": f"Recorded from a live run of {record.input.mpn}.",
    }

    # Invert the trust engine: every attribute knows which sources supported it
    # (and which contradicted it), so per-source extractions can be rebuilt.
    per_source: dict[str, list[dict]] = defaultdict(list)
    for attr in record.attributes:
        for ev in list(attr.evidence) + list(attr.conflicting_values):
            per_source[ev.source_url].append(
                {
                    "name": attr.name,
                    "value": ev.raw_value,
                    "unit": attr.unit,
                    "quote": ev.quote,
                }
            )

    extractor: dict[str, object] = {}
    first = True
    for url, attrs in per_source.items():
        extractor[url] = {
            "attributes": attrs,
            # Attach the record-level lists to one source so the merge still
            # produces them, without duplicating across every source.
            "image_urls": record.image_urls if first else [],
            "certifications": record.certifications if first else [],
            "equivalent_mpns": record.equivalent_mpns if first else [],
        }
        first = False
    # Sources that contributed no evidence were unusable in the real run
    # (blocked, timed out, 404). A null default makes the replay skip them too,
    # so source counts — and therefore confidence — match the live record.
    extractor["default"] = None

    # The live validator used a model call to decide which differently-worded
    # values mean the same thing. Record those decisions as value groups so the
    # replay reproduces the same conflicts instead of inventing new ones.
    validator: dict[str, list[list[str]]] = {}
    for attr in record.attributes:
        if not attr.conflicting_values and len({e.raw_value for e in attr.evidence}) < 2:
            continue
        winner = list(dict.fromkeys(e.raw_value for e in attr.evidence))
        groups = [winner] if winner else []
        losers = list(dict.fromkeys(e.raw_value for e in attr.conflicting_values))
        groups.extend([v] for v in losers)
        validator[attr.name] = groups

    composer = {
        "seo_title": record.seo_title,
        "short_description": record.short_description,
        "long_description": record.long_description,
        "search_synonyms": record.search_synonyms,
    }

    return {
        "scout": scout,
        "relevance": relevance,
        "classifier": classifier,
        "extractor": extractor,
        "validator": validator,
        "composer": composer,
    }


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python -m skuforge.snapshot <MPN> [--force]")
        sys.exit(1)
    mpn = sys.argv[1]
    force = "--force" in sys.argv

    # Never snapshot a replayed record — that would regenerate fixtures from
    # fixtures and quietly bake in any drift.
    matches = [
        r for r in store.list_all()
        if r.input.mpn.lower() == mpn.lower()
        and r.attributes
        and r.provider != "mock"
    ]
    if not matches:
        print(
            f"No live-provider record found for MPN '{mpn}'. "
            f"(Records produced in mock mode are ignored — fixtures must come "
            f"from a real run.)"
        )
        sys.exit(1)
    record = max(matches, key=lambda r: (len(r.attributes), r.created_at))

    key = record.input.mpn.replace("/", "_").replace(" ", "_").upper()
    out_dir = config.FIXTURES_DIR / key
    if out_dir.exists() and not force:
        print(f"Fixtures already exist at fixtures/{key}. Use --force to overwrite.")
        sys.exit(1)
    out_dir.mkdir(parents=True, exist_ok=True)

    for stage, payload in build_fixtures(record).items():
        path = out_dir / f"{stage}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"  wrote fixtures/{key}/{stage}.json")

    conflicts = sum(1 for a in record.attributes if a.conflicting_values)
    print(
        f"\nSnapshotted {record.input.brand} {record.input.mpn}: "
        f"{len(record.attributes)} attributes, {len(record.sources)} sources, "
        f"{conflicts} conflict(s).\n"
        f"Replay offline with:  SKUFORGE_MOCK=1 python -m skuforge.cli "
        f'{record.input.mpn} "{record.input.brand}" "{record.input.description}"'
    )


if __name__ == "__main__":
    main()
