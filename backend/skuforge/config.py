"""Central config: env, model routing, thresholds."""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Which vendor backs the pipeline. Every stage runs through llm.py, so this is
# the only switch needed: "openai" or "gemini" (Gemini has a free tier).
PROVIDER = os.getenv("SKUFORGE_PROVIDER", "openai").lower()

API_KEYS = {"openai": OPENAI_API_KEY, "gemini": GEMINI_API_KEY}
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
        "validator": {"model": "gpt-5.6", "effort": "medium"},
        "composer": {"model": "gpt-5.6", "effort": "low"},
    },
    "gemini": {
        "scout": {"model": "gemini-2.5-flash", "effort": "low"},
        "relevance": {"model": "gemini-2.5-flash-lite", "effort": "minimal"},
        "classifier": {"model": "gemini-2.5-flash-lite", "effort": "minimal"},
        "extractor": {"model": "gemini-2.5-flash", "effort": "low"},
        "validator": {"model": "gemini-2.5-flash", "effort": "medium"},
        "composer": {"model": "gemini-2.5-flash", "effort": "low"},
    },
}

MODELS = MODEL_ROUTING.get(PROVIDER, MODEL_ROUTING["openai"])

# Trust engine
AUTO_APPROVE_THRESHOLD = 0.8
SOURCE_TRUST = {
    "manufacturer": 1.0,
    "distributor": 0.75,
    "marketplace": 0.5,
    "other": 0.4,
}

MAX_SOURCES_PER_SKU = 5
FETCH_TIMEOUT_S = 20
