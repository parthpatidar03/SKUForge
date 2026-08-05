"""The only module that talks to a model vendor.

Two call shapes cover the whole pipeline:
  call_structured()  — schema-constrained JSON, optionally with PDFs/images
  call_web_search()  — free text grounded in live web results, plus citations

Both dispatch on config.PROVIDER, so the pipeline is vendor-agnostic:
OpenAI (Responses API) and Gemini (Google Gen AI SDK, free tier) are
interchangeable via one env var. Mock mode short-circuits both to fixtures.

Note the two shapes are kept separate deliberately — Gemini cannot combine a
response schema with the google_search tool, and the pipeline never needs to.
"""
import json
import random
import re
import time
from typing import Any, Optional

from . import config

# Blended $/1M tokens (input, output). Gemini entries are the free-tier reality;
# swap in paid rates if the project moves off it.
PRICES = {
    "gpt-5.6": (1.25, 10.0),
    "gpt-5-mini": (0.25, 2.0),
    "gpt-5-nano": (0.05, 0.4),
    "gemini-2.5-flash": (0.0, 0.0),
    "gemini-2.5-flash-lite": (0.0, 0.0),
    "gemini-3.6-flash": (0.0, 0.0),
    "gemini-3.5-flash-lite": (0.0, 0.0),
}

# Gemini thinking budgets (tokens) per effort level.
THINKING_BUDGET = {"minimal": 0, "low": 512, "medium": 2048, "high": 8192}

_clients: dict[str, Any] = {}


class QuotaExhausted(RuntimeError):
    """Daily/plan quota is spent. Unlike a per-minute rate limit, no amount of
    waiting inside this run will fix it, so it fails fast and loudly."""


def _is_rate_limit(exc: Exception) -> bool:
    text = str(exc)
    return "429" in text or "RESOURCE_EXHAUSTED" in text or "rate_limit" in text


def _is_exhausted(exc: Exception) -> bool:
    text = str(exc)
    return (
        "insufficient_quota" in text
        or "credit_balance" in text
        or "PerDay" in text  # e.g. GenerateRequestsPerDayPerProjectPerModel-FreeTier
    )


def _retry_after(exc: Exception) -> float | None:
    """Providers often say exactly how long to wait ("Please retry in 50.8s")."""
    m = re.search(r"retry in ([\d.]+)s", str(exc))
    return float(m.group(1)) if m else None


def _with_retry(fn):
    """Per-minute rate limits are the normal state of a free tier, not an
    error: retry them with backoff, honouring the provider's own retry hint
    when it gives one. Daily/plan exhaustion is raised immediately as
    QuotaExhausted — grinding through four backoffs against a limit that
    resets tomorrow only wastes time and hides the real cause."""
    last: Exception | None = None
    for attempt in range(config.LLM_MAX_RETRIES):
        try:
            return fn()
        except Exception as exc:
            if _is_exhausted(exc):
                raise QuotaExhausted(
                    f"{config.PROVIDER} quota exhausted for this period — "
                    f"add credits, switch SKUFORGE_PROVIDER, or use "
                    f"SKUFORGE_MOCK=1. Original: {exc}"
                ) from exc
            if not _is_rate_limit(exc):
                raise
            last = exc
            if attempt == config.LLM_MAX_RETRIES - 1:
                break
            hinted = _retry_after(exc)
            delay = (
                hinted + random.uniform(0, 2)
                if hinted is not None and hinted <= 90
                else config.LLM_BACKOFF_BASE_S * (2**attempt) + random.uniform(0, 2)
            )
            time.sleep(delay)
    raise last  # type: ignore[misc]


class LLMResult:
    def __init__(self, data: Any, cost_usd: float = 0.0, raw_text: str = ""):
        self.data = data
        self.cost_usd = cost_usd
        self.raw_text = raw_text


def _cost(model: str, tokens_in: int, tokens_out: int) -> float:
    pin, pout = PRICES.get(model, (1.0, 4.0))
    return (tokens_in * pin + tokens_out * pout) / 1_000_000


def _mock_fixture(stage: str, fixture_key: Optional[str]) -> Any:
    """Load fixtures/<fixture_key>/<stage>.json for offline runs."""
    if not fixture_key:
        raise RuntimeError(f"Mock mode: no fixture_key given for stage '{stage}'")
    path = config.FIXTURES_DIR / fixture_key / f"{stage}.json"
    if not path.exists():
        raise RuntimeError(f"Mock mode: fixture missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# OpenAI
# --------------------------------------------------------------------------

def _openai_client():
    if "openai" not in _clients:
        from openai import OpenAI
        _clients["openai"] = OpenAI(api_key=config.OPENAI_API_KEY)
    return _clients["openai"]


def _openai_structured(route, prompt, schema, schema_name, input_files) -> LLMResult:
    content: list[dict] = [{"type": "input_text", "text": prompt}]
    if input_files:
        content.extend(input_files)
    resp = _openai_client().responses.create(
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
    u = resp.usage
    return LLMResult(
        json.loads(resp.output_text),
        _cost(route["model"], u.input_tokens, u.output_tokens),
        resp.output_text,
    )


def _openai_web_search(route, prompt) -> LLMResult:
    resp = _openai_client().responses.create(
        model=route["model"],
        reasoning={"effort": route["effort"]},
        input=prompt,
        tools=[{"type": "web_search"}],
    )
    urls: list[dict] = []
    for item in resp.output:
        if getattr(item, "type", "") == "message":
            for part in item.content:
                for ann in getattr(part, "annotations", []) or []:
                    if getattr(ann, "type", "") == "url_citation":
                        urls.append({"url": ann.url, "title": getattr(ann, "title", "")})
    u = resp.usage
    return LLMResult(
        {"text": resp.output_text, "citations": urls},
        _cost(route["model"], u.input_tokens, u.output_tokens),
        resp.output_text,
    )


# --------------------------------------------------------------------------
# Gemini
# --------------------------------------------------------------------------

def _gemini_client():
    if "gemini" not in _clients:
        from google import genai
        _clients["gemini"] = genai.Client(api_key=config.GEMINI_API_KEY)
    return _clients["gemini"]


def _gemini_config(route, **extra):
    from google.genai import types
    budget = THINKING_BUDGET.get(route["effort"], 512)
    return types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_budget=budget), **extra
    )


def _gemini_usage(resp) -> tuple[int, int]:
    u = getattr(resp, "usage_metadata", None)
    if not u:
        return 0, 0
    return (
        getattr(u, "prompt_token_count", 0) or 0,
        getattr(u, "candidates_token_count", 0) or 0,
    )


# Gemini's response_schema accepts an OpenAPI 3.0 subset, not full JSON Schema.
# Agents author one schema in OpenAI's strict dialect; this strips what Gemini
# rejects so a single definition serves both vendors.
_GEMINI_UNSUPPORTED = {
    "additionalProperties", "strict", "minLength", "maxLength",
    "minimum", "maximum", "$schema", "default",
}


def _sanitize_schema(node: Any) -> Any:
    if isinstance(node, dict):
        return {
            k: _sanitize_schema(v)
            for k, v in node.items()
            if k not in _GEMINI_UNSUPPORTED
        }
    if isinstance(node, list):
        return [_sanitize_schema(v) for v in node]
    return node


def _gemini_structured(route, prompt, schema, input_files) -> LLMResult:
    contents: list[Any] = [prompt]
    for part in input_files or []:
        # Translate the OpenAI-shaped file part into Gemini inline_data.
        data_uri = part.get("file_data", "")
        if "base64," in data_uri:
            header, b64 = data_uri.split("base64,", 1)
            mime = header.removeprefix("data:").rstrip(";")
            contents.append({"inline_data": {"data": b64, "mimeType": mime}})

    resp = _gemini_client().models.generate_content(
        model=route["model"],
        contents=contents,
        config=_gemini_config(
            route,
            response_mime_type="application/json",
            response_schema=_sanitize_schema(schema),
        ),
    )
    tin, tout = _gemini_usage(resp)
    return LLMResult(
        json.loads(resp.text), _cost(route["model"], tin, tout), resp.text
    )


def _gemini_web_search(route, prompt) -> LLMResult:
    from google.genai import types

    resp = _gemini_client().models.generate_content(
        model=route["model"],
        contents=prompt,
        config=_gemini_config(
            route, tools=[types.Tool(google_search=types.GoogleSearch())]
        ),
    )
    urls: list[dict] = []
    for cand in resp.candidates or []:
        meta = getattr(cand, "grounding_metadata", None)
        for chunk in (getattr(meta, "grounding_chunks", None) or []) if meta else []:
            web = getattr(chunk, "web", None)
            if web and getattr(web, "uri", None):
                urls.append({"url": web.uri, "title": getattr(web, "title", "") or ""})
    tin, tout = _gemini_usage(resp)
    return LLMResult(
        {"text": resp.text or "", "citations": urls},
        _cost(route["model"], tin, tout),
        resp.text or "",
    )


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def call_structured(
    stage: str,
    prompt: str,
    schema: dict,
    schema_name: str = "result",
    fixture_key: Optional[str] = None,
    input_files: Optional[list[dict]] = None,
) -> LLMResult:
    """Schema-constrained JSON. input_files carries PDFs/images as OpenAI-shaped
    content parts; the Gemini path translates them to inline_data."""
    if config.MOCK_MODE:
        return LLMResult(_mock_fixture(stage, fixture_key))
    route = config.MODELS[stage]
    if config.PROVIDER == "gemini":
        return _with_retry(lambda: _gemini_structured(route, prompt, schema, input_files))
    return _with_retry(
        lambda: _openai_structured(route, prompt, schema, schema_name, input_files)
    )


def call_web_search(
    stage: str,
    prompt: str,
    fixture_key: Optional[str] = None,
) -> LLMResult:
    """Live web-grounded call. Returns {"text", "citations": [{url, title}]}."""
    if config.MOCK_MODE:
        return LLMResult(_mock_fixture(stage, fixture_key))
    route = config.MODELS[stage]
    if config.PROVIDER == "gemini":
        return _with_retry(lambda: _gemini_web_search(route, prompt))
    return _with_retry(lambda: _openai_web_search(route, prompt))
