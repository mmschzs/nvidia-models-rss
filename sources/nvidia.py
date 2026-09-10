# -*- coding: utf-8 -*-
"""NVIDIA Build scraper (https://build.nvidia.com/models).

Three extraction strategies are tried in order so the scraper survives markup
changes:

1. ``__NEXT_DATA__`` (Next.js Pages Router payload)
2. React Query dehydrated state inside the App Router RSC stream
3. Direct DOM parsing of the rendered model cards
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from .base import Item, Source

logger = logging.getLogger("models_rss")

BASE_URL = "https://build.nvidia.com"
MODELS_URL = "https://build.nvidia.com/models"

KNOWN_PUBLISHERS = {
    "nvidia": "NVIDIA",
    "meta": "Meta",
    "google": "Google",
    "mistralai": "Mistral AI",
    "microsoft": "Microsoft",
    "baichuan": "Baichuan",
    "qwen": "Qwen",
    "deepseek": "DeepSeek",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "snowflake": "Snowflake",
    "ibm": "IBM",
    "01-ai": "01.AI",
    "adept": "Adept",
    "black-forest-labs": "Black Forest Labs",
    "resembleai": "Resemble.AI",
    "stepfun-ai": "Stepfun-ai",
    "thinkingmachines": "Thinking Machines",
    "poolside": "Poolside",
    "z-ai": "Z.ai",
}

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def parse_datetime_safe(val: Any) -> datetime:
    if not val:
        return datetime.now(timezone.utc)
    if isinstance(val, (int, float)):
        if val > 1e11:
            val = val / 1000.0
        return datetime.fromtimestamp(val, tz=timezone.utc)
    if isinstance(val, str):
        try:
            return date_parser.parse(val).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc)


class NvidiaSource(Source):
    key = "nvidia"
    label = "NVIDIA"
    home_url = MODELS_URL

    def fetch(self) -> List[Item]:
        html = self.get_html(MODELS_URL)

        models = self._parse_next_data(html) or self._parse_rsc_stream(html)
        if not models:
            models = self._parse_dom_cards(html)

        logger.info(f"[nvidia] extracted {len(models)} models")
        return [self._to_item(m) for m in models if m.get("name")]

    # ------------------------------------------------------------------ #
    # extraction strategies
    # ------------------------------------------------------------------ #
    def _parse_next_data(self, html: str) -> Optional[List[Dict[str, Any]]]:
        soup = BeautifulSoup(html, "html.parser")
        script = soup.find("script", id="__NEXT_DATA__")
        if not script or not script.string:
            return None
        try:
            data = json.loads(script.string)
            page_props = data.get("props", {}).get("pageProps", {})
            for key in ["models", "initialModels", "cards", "items", "data"]:
                bucket = page_props.get(key)
                if isinstance(bucket, list) and bucket:
                    logger.info(f"[nvidia] {len(bucket)} models in __NEXT_DATA__['{key}']")
                    return [self._normalize_api_item(i) for i in bucket if isinstance(i, dict)]
        except Exception as e:
            logger.warning(f"[nvidia] __NEXT_DATA__ parse error: {e}")
        return None

    def _normalize_api_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        pub = item.get("publisher") or item.get("org") or item.get("author") or "NVIDIA"
        link = item.get("url")
        if not link and item.get("link"):
            link = f"{BASE_URL}{item['link']}"
        return {
            "name": item.get("name") or item.get("displayName") or item.get("id"),
            "publisher": pub,
            "url": link,
            "description": item.get("description") or item.get("summary") or "",
            "badges": item.get("badges") or [],
            "tags": item.get("tags") or item.get("labels") or [],
            "updated_str": item.get("updatedAt") or item.get("lastUpdated") or "",
            "pub_datetime": parse_datetime_safe(item.get("updatedAt") or item.get("date")),
        }

    def _parse_rsc_stream(self, html: str) -> Optional[List[Dict[str, Any]]]:
        soup = BeautifulSoup(html, "html.parser")
        chunks: List[str] = []
        for s in soup.find_all("script"):
            if not s.string or "self.__next_f.push" not in s.string:
                continue
            for match in re.finditer(r'self\.__next_f\.push\(\[\d+,\s*"(.*?)"\]\)', s.string):
                raw = match.group(1)
                try:
                    chunks.append(bytes(raw, "utf-8").decode("unicode_escape"))
                except Exception:
                    chunks.append(raw)

        for line in "\n".join(chunks).split("\n"):
            if "queryKey" not in line or "models" not in line:
                continue
            try:
                idx = line.find("{")
                if idx == -1:
                    continue
                queries = json.loads(line[idx:]).get("state", {}).get("queries", [])
                for q in queries:
                    data = q.get("state", {}).get("data")
                    if isinstance(data, list) and data and isinstance(data[0], dict):
                        logger.info(f"[nvidia] {len(data)} models in RSC stream")
                        return [self._normalize_api_item(i) for i in data]
            except Exception:
                continue
        return None

    def _parse_dom_cards(self, html: str) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.find_all(attrs={"data-testid": "nv-card-root"})
        if not cards:
            cards = soup.find_all("div", class_=re.compile(r"nv-card-root"))
        logger.info(f"[nvidia] DOM parser found {len(cards)} cards")

        models: List[Dict[str, Any]] = []
        for i, card in enumerate(cards):
            try:
                publisher = ""
                pub_el = card.find("a", attrs={"data-nvtrack-nav-object": "artifact-card-publisher-link"})
                if pub_el:
                    publisher = pub_el.get_text(strip=True)

                badges = []
                for b in card.find_all(attrs={"data-testid": "nv-badge"}):
                    txt = b.get_text(strip=True)
                    if txt and txt not in badges:
                        badges.append(txt)

                model_name = ""
                model_url = ""
                model_el = card.find("a", attrs={"data-nvtrack-nav-object": "artifact-card"})
                if model_el:
                    span = model_el.find(attrs={"data-testid": "nv-text"})
                    model_name = span.get_text(strip=True) if span else model_el.get_text(strip=True)
                    href = model_el.get("href", "")
                    model_url = f"{BASE_URL}{href}" if href.startswith("/") else href

                if not model_url or not publisher:
                    for a in card.find_all("a"):
                        href = a.get("href", "")
                        text = a.get_text(strip=True)
                        parts = [p for p in href.strip("/").split("/") if p]
                        if len(parts) == 1 and not parts[0].startswith("models") and not publisher:
                            publisher = text or parts[0]
                        elif len(parts) == 2 and parts[0] not in ["models", "api", "docs"] and not model_url:
                            model_name = model_name or text or parts[1]
                            model_url = f"{BASE_URL}{href}"

                if not publisher and model_url:
                    path_parts = model_url.replace(BASE_URL, "").strip("/").split("/")
                    if len(path_parts) >= 2:
                        raw = path_parts[0]
                        publisher = KNOWN_PUBLISHERS.get(raw.lower(), raw.capitalize())
                publisher = publisher or "NVIDIA"

                desc = ""
                desc_el = card.find("span", class_=re.compile(r"line-clamp-\d+|label-regular-md"))
                if desc_el:
                    desc = desc_el.get_text(strip=True)
                if not desc:
                    for s in card.find_all(["span", "p"]):
                        txt = s.get_text(strip=True)
                        if len(txt) > 25 and txt != model_name and not txt.startswith("Last updated"):
                            desc = txt
                            break

                tags: List[str] = []
                for t in card.find_all(attrs={"data-testid": "nv-tag-root"}):
                    txt = t.get_text(strip=True)
                    if txt and txt != "+" and txt not in tags:
                        tags.append(txt)
                for a in card.find_all("a", href=re.compile(r"/models\?")):
                    txt = a.get_text(strip=True)
                    if txt and txt != "+" and txt not in tags:
                        tags.append(txt)

                updated_str = ""
                pub_dt = None
                for el in card.find_all(attrs={"aria-label": True}):
                    label = el.get("aria-label", "")
                    if any(m in label for m in MONTHS):
                        updated_str = label
                        break
                if not updated_str:
                    for s in card.stripped_strings:
                        m = re.search(r"Last updated on\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})", s, re.I)
                        if m:
                            updated_str = m.group(1)
                            break
                if updated_str:
                    try:
                        pub_dt = date_parser.parse(updated_str).replace(tzinfo=timezone.utc)
                    except Exception:
                        pub_dt = None

                models.append({
                    "name": model_name,
                    "publisher": publisher,
                    "url": model_url,
                    "description": desc,
                    "badges": badges,
                    "tags": tags,
                    "updated_str": updated_str,
                    "pub_datetime": pub_dt or datetime.now(timezone.utc),
                })
            except Exception as e:
                logger.warning(f"[nvidia] error parsing card {i}: {e}")

        return models

    # ------------------------------------------------------------------ #
    def _to_item(self, m: Dict[str, Any]) -> Item:
        name = m.get("name") or "Unknown Model"
        publisher = m.get("publisher") or "NVIDIA"
        url = m.get("url") or MODELS_URL
        badges = m.get("badges") or []
        tags = m.get("tags") or []
        updated_str = m.get("updated_str") or ""
        desc = m.get("description") or f"Model card for {name} by {publisher}"

        parts = [desc]
        if badges:
            parts.append(f"Features: {' | '.join(badges)}")
        if tags:
            parts.append(f"Tags: {' '.join('#' + t for t in tags)}")
        if updated_str:
            parts.append(f"Last Updated: {updated_str}")
        summary = "\n".join(parts)

        lines = [
            f"<b>Publisher</b>: {publisher}",
            f"<b>Features</b>: {' | '.join(badges) if badges else 'Standard'}",
            f"<b>Description</b>:<br/>{desc}",
        ]
        if tags:
            lines.append(f"<b>Tags</b>: {' '.join('#' + t for t in tags)}")
        if updated_str:
            lines.append(f"<b>Last Updated</b>: {updated_str}")
        lines.append(f"<b>Model Card</b>: <a href=\"{url}\" target=\"_blank\">{url}</a>")
        html = "<br/>\n".join(lines)

        return Item(
            source_key=self.key,
            source_label=self.label,
            title=name,
            link=url,
            guid=url or f"nvidia:{name}",
            pub_datetime=m.get("pub_datetime") or datetime.now(timezone.utc),
            summary=summary,
            html=html,
            categories=list(dict.fromkeys(badges + tags + [publisher])),
        )
