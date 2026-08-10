"""Evidence cache: fetched pages/PDFs stored on disk, keyed by URL hash.

Production pattern, not demo trickery: never re-fetch the same datasheet.
Demo SKUs get pre-warmed so recorded runs never depend on live sites.
"""
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Optional

import httpx

from . import config

logger = logging.getLogger("skuforge")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
}


# url -> human-readable reason the last fetch failed (surfaced in pipeline events)
_FAILURES: dict[str, str] = {}


def last_failure(url: str) -> str:
    return _FAILURES.get(url, "unreachable")


def _key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:24]


def _paths(url: str) -> tuple[Path, Path]:
    k = _key(url)
    config.CACHE_DIR.mkdir(exist_ok=True)
    return config.CACHE_DIR / f"{k}.meta.json", config.CACHE_DIR / f"{k}.body"


def get(url: str) -> Optional[dict]:
    """Return {url, content_type, body_path, fetched_at} or None."""
    meta_p, body_p = _paths(url)
    if meta_p.exists() and body_p.exists():
        return json.loads(meta_p.read_text(encoding="utf-8"))
    return None


def fetch(url: str, force: bool = False) -> Optional[dict]:
    """Fetch through cache. Returns meta dict, or None with the reason recorded
    in last_failure() — distinguishes bot-blocking (403) from transient errors."""
    if not force:
        hit = get(url)
        if hit:
            hit["cache_hit"] = True
            return hit

    meta_p, body_p = _paths(url)
    r = None
    for attempt in range(2):  # datasheet PDFs are large; one retry on timeout
        try:
            with httpx.Client(
                headers=HEADERS,
                timeout=config.FETCH_TIMEOUT_S * (attempt + 1),
                follow_redirects=True,
            ) as client:
                r = client.get(url)
                r.raise_for_status()
            break
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            _FAILURES[url] = "blocked (403)" if code in (401, 403, 429) else f"HTTP {code}"
            logger.warning("fetch blocked (%s): %s", _FAILURES[url], url)
            return None  # server answered; retrying won't help
        except Exception as exc:
            # Logged with the message, not just the exception class name — an
            # SSL/CA failure and a DNS failure both raise generically enough
            # that the class name alone hides which one actually happened.
            _FAILURES[url] = f"{type(exc).__name__}"
            logger.warning("fetch failed (attempt %d): %s: %s", attempt + 1, url, exc)
            r = None
    if r is None:
        logger.warning("fetch exhausted retries, giving up: %s", url)
        return None
    _FAILURES.pop(url, None)

    body_p.write_bytes(r.content)
    meta = {
        "url": url,
        # Search grounding hands back redirector links (Google's
        # vertexaisearch grounding-api-redirect, for example). Provenance must
        # cite the page a human can actually open, so record where we landed.
        "final_url": str(r.url),
        "content_type": r.headers.get("content-type", ""),
        "body_path": str(body_p),
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cache_hit": False,
    }
    meta_p.write_text(json.dumps(meta), encoding="utf-8")
    return meta


def read_text(meta: dict, max_chars: int = 40_000) -> str:
    """Extract readable text from a cached HTML body."""
    from bs4 import BeautifulSoup

    body = Path(meta["body_path"]).read_bytes()
    if "pdf" in meta.get("content_type", ""):
        return ""  # PDFs go to the model as input_file, not text
    soup = BeautifulSoup(body, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ").split())
    return text[:max_chars]
