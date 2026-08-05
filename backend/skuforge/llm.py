"""OpenAI wrapper: structured calls, web-search calls, cost tracking, mock mode.

All agents go through call_structured() / call_web_search() so model routing,
cost accounting, and mock fixtures live in one place.
"""
import json
from pathlib import Path
from typing import Any, Optional

from . import config

# Rough blended $/1M tokens (in, out) for cost display — update before demo.
PRICES = {
    "gpt-5.6": (1.25, 10.0),
    "gpt-5-mini": (0.25, 2.0),
    "gpt-5-nano": (0.05, 0.4),
}

_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


class LLMResult:
    def __init__(self, data: Any, cost_usd: float = 0.0, raw_text: str = ""):
        self.data = data
        self.cost_usd = cost_usd
        self.raw_text = raw_text


def _cost(model: str, usage) -> float:
    pin, pout = PRICES.get(model, (1.0, 4.0))
    try:
        return (usage.input_tokens * pin + usage.output_tokens * pout) / 1_000_000
    except AttributeError:
        return 0.0


def _mock_fixture(stage: str, fixture_key: Optional[str]) -> Any:
    """Load fixtures/<fixture_key>/<stage>.json for offline runs."""
    if not fixture_key:
        raise RuntimeError(f"Mock mode: no fixture_key given for stage '{stage}'")
    path = config.FIXTURES_DIR / fixture_key / f"{stage}.json"
    if not path.exists():
        raise RuntimeError(f"Mock mode: fixture missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def call_structured(
    stage: str,
    prompt: str,
    schema: dict,
    schema_name: str = "result",
    fixture_key: Optional[str] = None,
    input_files: Optional[list[dict]] = None,
) -> LLMResult:
    """Structured-output call routed by stage. input_files: extra content parts
    (e.g. {"type": "input_file", ...} for PDFs or {"type": "input_image", ...})."""
    if config.MOCK_MODE:
        return LLMResult(_mock_fixture(stage, fixture_key))

    route = config.MODELS[stage]
    content: list[dict] = [{"type": "input_text", "text": prompt}]
    if input_files:
        content.extend(input_files)

    resp = _get_client().responses.create(
        model=route["model"],
        reasoning={"effort": route["effort"]},
        input=[{"role": "user", "content": content}],
        text={
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": schema,
            }
        },
    )
    return LLMResult(
        json.loads(resp.output_text),
        cost_usd=_cost(route["model"], resp.usage),
        raw_text=resp.output_text,
    )


def call_web_search(
    stage: str,
    prompt: str,
    fixture_key: Optional[str] = None,
) -> LLMResult:
    """Web-search-enabled call. Returns free text + citations; caller parses."""
    if config.MOCK_MODE:
        return LLMResult(_mock_fixture(stage, fixture_key))

    route = config.MODELS[stage]
    resp = _get_client().responses.create(
        model=route["model"],
        reasoning={"effort": route["effort"]},
        input=prompt,
        tools=[{"type": "web_search"}],
    )
    # Collect url citations from output annotations
    urls: list[dict] = []
    for item in resp.output:
        if getattr(item, "type", "") == "message":
            for part in item.content:
                for ann in getattr(part, "annotations", []) or []:
                    if getattr(ann, "type", "") == "url_citation":
                        urls.append({"url": ann.url, "title": getattr(ann, "title", "")})
    return LLMResult(
        {"text": resp.output_text, "citations": urls},
        cost_usd=_cost(route["model"], resp.usage),
        raw_text=resp.output_text,
    )
