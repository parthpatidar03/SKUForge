"""Central config: env, model routing, thresholds."""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Which profile backs the pipeline: "openai", "gemini", "openrouter", or
# "hybrid". Every stage runs through llm.py, so this is the only switch needed.
PROVIDER = os.getenv("SKUFORGE_PROVIDER", "openai").lower()

API_KEYS = {
    "openai": OPENAI_API_KEY,
    "gemini": GEMINI_API_KEY,
    "openrouter": OPENROUTER_API_KEY,
}
# A hybrid profile needs every vendor it routes to.
if PROVIDER == "hybrid":
    ACTIVE_KEY = GEMINI_API_KEY and OPENROUTER_API_KEY
else:
    ACTIVE_KEY = API_KEYS.get(PROVIDER, "")
MOCK_MODE = os.getenv("SKUFORGE_MOCK", "0") == "1" or not ACTIVE_KEY

CACHE_DIR = BACKEND_DIR / "cache"
DB_PATH = BACKEND_DIR / "skuforge.db"
FIXTURES_DIR = BACKEND_DIR / "fixtures"

# Model routing per stage, per provider (see PLAN.md §4).
# OpenAI verified Aug 2026: flagship gpt-5.6, volume tiers gpt-5-mini/nano.
# Gemini free tier: 2.5-flash carries grounding + PDF vision; flash-lite for
# the cheap high-volume steps. "effort" maps to reasoning effort (OpenAI) or
# thinking budget (Gemini).
MODEL_ROUTING = {
    "openai": {
        "scout": {"model": "gpt-5-mini", "effort": "low"},
        "relevance": {"model": "gpt-5-nano", "effort": "minimal"},
        "classifier": {"model": "gpt-5-mini", "effort": "low"},
        "extractor": {"model": "gpt-5-mini", "effort": "low"},
        "extractor_pdf": {"model": "gpt-5-mini", "effort": "low"},
        "validator": {"model": "gpt-5.6", "effort": "medium"},
        "composer": {"model": "gpt-5.6", "effort": "low"},
    },
    # Probed against this key on 5 Aug 2026: gemini-2.5-flash is the only model
    # with free-tier quota. 2.5-flash-lite is retired for new accounts (404),
    # and 2.0-flash / 2.5-pro / the 3.x tiers all return 429 RESOURCE_EXHAUSTED.
    # So the free path routes every stage to one model and leans on `effort`
    # (thinking budget) to separate cheap steps from expensive judgment.
    "gemini": {
        "scout": {"model": "gemini-2.5-flash", "effort": "low"},
        "relevance": {"model": "gemini-2.5-flash", "effort": "minimal"},
        "classifier": {"model": "gemini-2.5-flash", "effort": "minimal"},
        "extractor": {"model": "gemini-2.5-flash", "effort": "low"},
        "extractor_pdf": {"model": "gemini-2.5-flash", "effort": "low"},
        "validator": {"model": "gemini-2.5-flash", "effort": "medium"},
        "composer": {"model": "gemini-2.5-flash", "effort": "low"},
    },
    # Free OpenRouter models. Verified against the live catalogue: these are the
    # ones advertising structured outputs. None accept PDFs, so this profile
    # cannot do datasheet vision — use "hybrid" for that.
    "openrouter": {
        "scout": {"model": "nvidia/nemotron-3-super-120b-a12b:free", "effort": "low"},
        "relevance": {"model": "nvidia/nemotron-nano-9b-v2:free", "effort": "minimal"},
        "classifier": {"model": "nvidia/nemotron-nano-9b-v2:free", "effort": "minimal"},
        "extractor": {"model": "nvidia/nemotron-3-super-120b-a12b:free", "effort": "low"},
        "extractor_pdf": {"model": "google/gemma-4-31b-it:free", "effort": "low"},
        "validator": {"model": "nvidia/nemotron-3-super-120b-a12b:free", "effort": "medium"},
        "composer": {"model": "nvidia/nemotron-3-super-120b-a12b:free", "effort": "low"},
    },
    # The zero-cost production profile. Gemini's free tier is metered at 20
    # calls/day, so it is spent only where nothing else is free: grounded web
    # search and PDF datasheet vision. Every text-only stage runs on free
    # OpenRouter models, cutting Gemini usage from ~8 calls per SKU to ~2-3.
    "hybrid": {
        "scout": {
            "provider": "gemini", "model": "gemini-2.5-flash", "effort": "low",
        },
        "relevance": {
            "provider": "openrouter",
            "model": "nvidia/nemotron-nano-9b-v2:free", "effort": "minimal",
        },
        "classifier": {
            "provider": "openrouter",
            "model": "nvidia/nemotron-nano-9b-v2:free", "effort": "minimal",
        },
        "extractor": {
            "provider": "openrouter",
            "model": "nvidia/nemotron-3-super-120b-a12b:free", "effort": "low",
        },
        "extractor_pdf": {
            "provider": "gemini", "model": "gemini-2.5-flash", "effort": "low",
        },
        "validator": {
            "provider": "openrouter",
            "model": "nvidia/nemotron-3-super-120b-a12b:free", "effort": "medium",
        },
        "composer": {
            "provider": "openrouter",
            "model": "nvidia/nemotron-3-super-120b-a12b:free", "effort": "low",
        },
    },
}

MODELS = MODEL_ROUTING.get(PROVIDER, MODEL_ROUTING["openai"])

# Trust engine
AUTO_APPROVE_THRESHOLD = 0.8
# A value found in exactly one source can never auto-approve, no matter how
# authoritative that source is — corroboration is the point of the system.
SINGLE_SOURCE_CEILING = 0.75
SOURCE_TRUST = {
    "manufacturer": 1.0,
    "distributor": 0.75,
    "marketplace": 0.5,
    "other": 0.4,
}

MAX_SOURCES_PER_SKU = 5
FETCH_TIMEOUT_S = 20

# Free tiers cap requests per minute, so fanning out extraction too wide just
# trades parallelism for 429s. Retries use exponential backoff on top of this.
MAX_PARALLEL_EXTRACTIONS = 3 if PROVIDER in ("gemini", "hybrid", "openrouter") else 5
# How many SKUs a catalog run processes at once. Multiplied by the per-SKU
# extraction fan-out, this is the real concurrency the provider sees.
BATCH_CONCURRENCY = 2 if PROVIDER in ("gemini", "hybrid", "openrouter") else 4
LLM_MAX_RETRIES = 4
LLM_BACKOFF_BASE_S = 8
