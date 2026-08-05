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


def _norm(value: str, unit: str) -> str:
    return f"{value.strip().lower()} {unit.strip().lower()}".strip()


def _group_values(name: str, evidence: list[Evidence], units: list[str],
                  fixture_key: str | None) -> tuple[list[list[int]], float]:
    """Group evidence indexes by equivalent value. Fast path: exact normalized match."""
    buckets: dict[str, list[int]] = {}
    for i, ev in enumerate(evidence):
        buckets.setdefault(_norm(ev.raw_value, units[i]), []).append(i)
    if len(buckets) == 1 or config.MOCK_MODE:
        return list(buckets.values()), 0.0

    # Textual mismatch — ask the model if values are equivalent (e.g. 0.5in vs 1/2").
    listing = "\n".join(
        f"{i}: '{ev.raw_value}' {units[i]}" for i, ev in enumerate(evidence)
    )
    result = llm.call_structured(
        "validator",
        f"Attribute '{name}' has these values from different sources:\n{listing}\n\n"
        f"Group the indexes: values that are the SAME fact expressed differently "
        f"(unit conversion, formatting, abbreviation) go in one group. "
        f"Genuinely different facts go in separate groups.",
        EQUIV_SCHEMA, "equivalence", fixture_key=fixture_key,
    )
    return result.data["groups"], result.cost_usd


def _confidence(group: list[Evidence], total_sources: int) -> float:
    """Blend of source trust, corroboration count, and coverage."""
    if not group:
        return 0.1
    best_trust = max(config.SOURCE_TRUST.get(e.source_type.value, 0.4) for e in group)
    corroboration = min(len(group) / 2, 1.0)          # 2+ agreeing sources = full marks
    coverage = len(group) / max(total_sources, 1)      # how many sources agree vs all seen
    return round(0.5 * best_trust + 0.35 * corroboration + 0.15 * coverage, 2)


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
        images.extend(u for u in ex.get("image_urls", []) if u not in images)
        certs.extend(c for c in ex.get("certifications", []) if c not in certs)
        equivs.extend(m for m in ex.get("equivalent_mpns", []) if m not in equivs)

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
