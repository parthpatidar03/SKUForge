"""Central config: env, model routing, thresholds."""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MOCK_MODE = os.getenv("SKUFORGE_MOCK", "0") == "1" or not OPENAI_API_KEY

CACHE_DIR = BACKEND_DIR / "cache"
DB_PATH = BACKEND_DIR / "skuforge.db"
FIXTURES_DIR = BACKEND_DIR / "fixtures"

# Model routing (see PLAN.md §4). Verified against OpenAI docs Aug 2026:
# flagship gpt-5.6, volume tiers gpt-5-mini / gpt-5-nano.
MODELS = {
    "scout": {"model": "gpt-5-mini", "effort": "low"},
    "relevance": {"model": "gpt-5-nano", "effort": "minimal"},
    "classifier": {"model": "gpt-5-mini", "effort": "low"},
    "extractor": {"model": "gpt-5-mini", "effort": "low"},
    "validator": {"model": "gpt-5.6", "effort": "medium"},
    "composer": {"model": "gpt-5.6", "effort": "low"},
}

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
