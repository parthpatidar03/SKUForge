"""VALIDATOR: the Trust Engine.

Merges per-source extractions into final attributes with confidence,
provenance, and explicit conflict detection. Deterministic scoring;
the LLM is only used to judge whether two values are equivalent
(unit conversions, formatting) when they don't match textually.
"""
from .. import config, llm
from ..models import Attribute, AttributeStatus, Evidence, SourceType

EQUIV_SCHEMA = {
    "type": "object",
    "properties": {
        "groups": {
            "type": "array",
            "description": "Groups of value indexes that mean the same thing",
            "items": {"type": "array", "items": {"type": "integer"}},
        }
    },
    "required": ["groups"],
    "additionalProperties": False,
}


IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".bmp")


def _norm(value: str, unit: str) -> str:
    return f"{value.strip().lower()} {unit.strip().lower()}".strip()


def _is_image(url: str) -> bool:
    """Models sometimes hand back the source document URL as an 'image'."""
    return url.lower().split("?")[0].endswith(IMAGE_EXTS)


def _dedupe_labels(labels: list[str]) -> list[str]:
    """Collapse case/whitespace duplicates ('UL listed' vs 'UL Listed'),
    keeping the first spelling seen."""
    seen: dict[str, str] = {}
    for label in labels:
        key = " ".join(label.split()).lower()
        if key and key not in seen:
            seen[key] = label.strip()
    return list(seen.values())


def _subsumes(a: str, b: str) -> bool:
    """True when one value is the other plus extra qualifiers — e.g.
    'AWG 14...AWG 8' vs 'AWG 14...AWG 8 aluminium/copper; AWG 14...AWG 10 copper'.
    Same fact at different detail levels, not a contradiction."""
    x, y = a.strip().lower(), b.strip().lower()
    if not x or not y or x == y:
        return False
    short, long = (x, y) if len(x) <= len(y) else (y, x)
    return len(short) >= 4 and short in long


def _group_values(name: str, evidence: list[Evidence], units: list[str],
                  fixture_key: str | None) -> tuple[list[list[int]], float]:
    """Group evidence indexes by equivalent value. Fast path: exact normalized match."""
    buckets: dict[str, list[int]] = {}
    for i, ev in enumerate(evidence):
        buckets.setdefault(_norm(ev.raw_value, units[i]), []).append(i)

    # Merge buckets where one value is the other plus qualifiers.
    keys = list(buckets)
    for i, ki in enumerate(keys):
        for kj in keys[i + 1:]:
            if ki in buckets and kj in buckets and _subsumes(ki, kj):
                keep, drop = (ki, kj) if len(ki) >= len(kj) else (kj, ki)
                buckets[keep] = sorted(buckets[keep] + buckets[drop])
                del buckets[drop]

    if len(buckets) == 1 or config.MOCK_MODE:
        return list(buckets.values()), 0.0

    # Textual mismatch — ask the model if values are equivalent (e.g. 0.5in vs 1/2").
    listing = "\n".join(
        f"{i}: '{ev.raw_value}' {units[i]}" for i, ev in enumerate(evidence)
    )
    try:
        result = llm.call_structured(
            "validator",
            f"Attribute '{name}' has these values from different sources:\n{listing}\n\n"
            f"Group the indexes: values that are the SAME fact expressed differently "
            f"(unit conversion, formatting, abbreviation) go in one group. "
            f"Genuinely different facts go in separate groups.",
            EQUIV_SCHEMA, "equivalence", fixture_key=fixture_key,
        )
    except Exception:
        # Fall back to the deterministic buckets. Values stay separate, so the
        # attribute is reported as a conflict for a human rather than lost.
        return list(buckets.values()), 0.0
    return result.data["groups"], result.cost_usd


def _confidence(group: list[Evidence], total_sources: int) -> float:
    """Blend of source trust, corroboration count, and coverage.

    Hard rule: a value seen in only one source is capped below the
    auto-approve threshold, however authoritative that source is. "One website
    said so" is exactly the failure mode this system exists to prevent — an
    uncorroborated spec always goes to a human.
    """
    if not group:
        return 0.1
    best_trust = max(config.SOURCE_TRUST.get(e.source_type.value, 0.4) for e in group)
    corroboration = min(len(group) / 2, 1.0)          # 2+ agreeing sources = full marks
    coverage = len(group) / max(total_sources, 1)      # how many sources agree vs all seen
    score = 0.5 * best_trust + 0.35 * corroboration + 0.15 * coverage
    if len(group) < 2:
        score = min(score, config.SINGLE_SOURCE_CEILING)
    return round(score, 2)


def run(
    per_source: list[tuple[str, SourceType, dict]],
    fixture_key: str | None = None,
) -> tuple[list[Attribute], list[str], list[str], list[str], float]:
    """per_source: [(url, source_type, extraction_dict)].
    Returns (attributes, image_urls, certifications, equivalent_mpns, cost)."""
    cost = 0.0
    by_name: dict[str, tuple[list[Evidence], list[str]]] = {}
    images: list[str] = []
    certs: list[str] = []
    equivs: list[str] = []

    for url, stype, ex in per_source:
        for a in ex.get("attributes", []):
            evs, units = by_name.setdefault(a["name"], ([], []))
            evs.append(Evidence(
                source_url=url, source_type=stype,
                raw_value=a["value"], quote=a.get("quote", ""),
            ))
            units.append(a.get("unit", ""))
        images.extend(
            u for u in ex.get("image_urls", []) if _is_image(u) and u not in images
        )
        certs.extend(ex.get("certifications", []))
        equivs.extend(ex.get("equivalent_mpns", []))

    certs = _dedupe_labels(certs)
    equivs = _dedupe_labels(equivs)

    total_sources = len(per_source)
    attributes: list[Attribute] = []

    for name, (evidence, units) in by_name.items():
        groups, group_cost = _group_values(name, evidence, units, fixture_key)
        cost += group_cost
        groups.sort(key=lambda g: -len(g))
        winner_idx, winner = 0, groups[0]

        # Prefer the group with the most trusted source when sizes tie
        for gi, g in enumerate(groups):
            if len(g) == len(winner) and gi != winner_idx:
                gt = max(config.SOURCE_TRUST.get(evidence[i].source_type.value, 0) for i in g)
                wt = max(config.SOURCE_TRUST.get(evidence[i].source_type.value, 0) for i in winner)
                if gt > wt:
                    winner_idx, winner = gi, g

        winner_ev = [evidence[i] for i in winner]
        loser_ev = [evidence[i] for gi, g in enumerate(groups) if gi != winner_idx for i in g]

        if loser_ev:
            status = AttributeStatus.conflict
        elif len(winner_ev) >= 2:
            status = AttributeStatus.verified
        else:
            status = AttributeStatus.single_source

        conf = _confidence(winner_ev, total_sources)
        if status == AttributeStatus.conflict:
            conf = round(min(conf, 0.5), 2)  # conflicts never auto-approve

        attributes.append(Attribute(
            name=name,
            value=evidence[winner[0]].raw_value,
            unit=units[winner[0]],
            confidence=conf,
            status=status,
            evidence=winner_ev,
            conflicting_values=loser_ev,
        ))

    attributes.sort(key=lambda a: (-a.confidence, a.name))
    return attributes, images, certs, equivs, cost
