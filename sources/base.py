# -*- coding: utf-8 -*-
"""Base contracts for model source scrapers."""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("models_rss")

STATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state", "seen.json"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

HTML_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}


@dataclass
class Item:
    """A single feed entry produced by a source scraper."""

    source_key: str
    source_label: str
    title: str
    link: str
    guid: str
    pub_datetime: datetime
    summary: str
    html: str
    categories: List[str] = field(default_factory=list)


class SeenStore:
    """Persists the first time an entry was observed.

    Some sources (e.g. AMD TokenFactory) publish no timestamp at all. For those
    entries the first crawl date becomes the entry date and must stay stable
    across runs, otherwise every refresh reshuffles the whole feed.
    """

    def __init__(self, path: str = STATE_PATH):
        self.path = path
        self.data: Dict[str, str] = {}
        self._dirty = False
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    self.data = loaded
            except Exception as e:  # pragma: no cover - defensive
                logger.warning(f"Could not read state file {path}: {e}")

    def first_seen(self, key: str) -> datetime:
        raw = self.data.get(key)
        if raw:
            try:
                return datetime.fromisoformat(raw)
            except ValueError:
                pass
        now = datetime.now(timezone.utc).replace(microsecond=0)
        self.data[key] = now.isoformat()
        self._dirty = True
        logger.info(f"First sighting of '{key}' -> {now.isoformat()}")
        return now

    def save(self) -> None:
        if not self._dirty:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2, sort_keys=True)
        logger.info(f"State saved: {self.path} ({len(self.data)} entries)")


class Source:
    """Common behaviour for every scraped source."""

    key: str = ""
    label: str = ""
    home_url: str = ""

    def __init__(self, seen: SeenStore):
        self.seen = seen
        self.session = requests.Session()
        self.session.headers.update(HTML_HEADERS)
        self.timeout = 60
        self.retries = 3

    def fetch(self) -> List[Item]:
        raise NotImplementedError

    def _request(self, method: str, url: str, extra_headers=None):
        last_error = None
        for attempt in range(1, self.retries + 1):
            try:
                resp = self.session.request(
                    method, url, headers=extra_headers or {}, timeout=self.timeout
                )
                resp.raise_for_status()
                return resp
            except Exception as e:
                last_error = e
                logger.warning(
                    f"[{self.key}] {method} {url} attempt {attempt}/{self.retries} failed: {e}"
                )
                if attempt < self.retries:
                    time.sleep(2 * attempt)
        raise last_error

    def get_html(self, url: str) -> str:
        logger.info(f"[{self.key}] GET {url}")
        resp = self._request("GET", url)
        logger.info(f"[{self.key}] {len(resp.text)} bytes (HTTP {resp.status_code})")
        return resp.text

    def get_json(self, url: str, extra_headers=None) -> Any:
        logger.info(f"[{self.key}] GET JSON {url}")
        return self._request("GET", url, extra_headers).json()

    def post_json(self, url: str, extra_headers=None) -> Any:
        logger.info(f"[{self.key}] POST JSON {url}")
        return self._request("POST", url, extra_headers).json()
