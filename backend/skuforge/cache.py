"""Evidence cache: fetched pages/PDFs stored on disk, keyed by URL hash.

Production pattern, not demo trickery: never re-fetch the same datasheet.
Demo SKUs get pre-warmed so recorded runs never depend on live sites.
"""
import hashlib
import json
import time
from pathlib import Path
from typing import Optional

import httpx

from . import config

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
}


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
    """Fetch through cache. Returns meta dict or None on failure."""
    if not force:
        hit = get(url)
        if hit:
            hit["cache_hit"] = True
            return hit

    meta_p, body_p = _paths(url)
    try:
        with httpx.Client(
            headers=HEADERS, timeout=config.FETCH_TIMEOUT_S, follow_redirects=True
        ) as client:
            r = client.get(url)
            r.raise_for_status()
    except Exception:
        return None

    body_p.write_bytes(r.content)
    meta = {
        "url": url,
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
