# -*- coding: utf-8 -*-
"""AMD Radeon TokenFactory scraper (https://developer.amd.com.cn/radeon/tokenfactory).

The page renders its catalog client side:

    POST /radeon/api/tokenfactory/bootstrap?directory=true   -> card descriptors
    GET  <descriptor.detail_url>                             -> model record

Only models carrying a free tier badge (``Free`` / ``Limited Free``) are kept.
The catalog carries no timestamps, so the first crawl date is used as the entry
date and persisted in ``state/seen.json``.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import Item, Source

logger = logging.getLogger("models_rss")

PAGE_URL = "https://developer.amd.com.cn/radeon/tokenfactory"
ORIGIN = "https://developer.amd.com.cn"
BOOTSTRAP_URL = f"{ORIGIN}/radeon/api/tokenfactory/bootstrap?directory=true"

# Tones rendered as "free to use" on the page. `deploy` / `soon` / `offline`
# are paid or unavailable and are skipped.
FREE_TONES = {"free", "limited"}


class AmdSource(Source):
    key = "amd"
    label = "AMD"
    home_url = PAGE_URL

    def _headers(self) -> Dict[str, str]:
        # The API rejects cross origin callers without these.
        return {
            "Origin": ORIGIN,
            "Referer": PAGE_URL,
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }

    def fetch(self) -> List[Item]:
        payload = self.post_json(BOOTSTRAP_URL, self._headers())
        cards = payload.get("cards") or []
        logger.info(f"[amd] directory returned {len(cards)} cards")

        items: List[Item] = []
        for card in cards:
            detail_url: Optional[str] = card.get("detail_url")
            if not detail_url:
                continue
            if detail_url.startswith("/"):
                detail_url = ORIGIN + detail_url
            try:
                record = self.get_json(detail_url, self._headers())
            except Exception as e:
                logger.warning(f"[amd] failed to load card {card.get('key')}: {e}")
                continue

            model = record.get("model") if isinstance(record, dict) else None
            item = self._to_item(model)
            if item:
                items.append(item)

        logger.info(f"[amd] kept {len(items)} free-tier models")
        return items

    def _to_item(self, model: Optional[Dict[str, Any]]):
        if not model:
            return None
        tf = model.get("token_factory") or {}
        if not tf:
            return None

        badge = tf.get("badge") or {}
        tone = (badge.get("tone") or "").lower()
        if tone not in FREE_TONES:
            logger.debug(f"[amd] skip {tf.get('model')} (badge tone={tone!r})")
            return None

        model_id = model.get("id") or tf.get("model") or tf.get("name") or ""
        name = tf.get("name") or tf.get("model") or model_id
        publisher = (tf.get("publisher") or {}).get("name", "")
        capability = (tf.get("capability") or {}).get("label", "")
        providers = ", ".join(p.get("name", "") for p in tf.get("providers") or [])
        tags = list(tf.get("tags") or [])
        status = (tf.get("status") or {}).get("label", badge.get("label", ""))
        description = tf.get("description") or ""
        context_length = model.get("context_length")

        pricing_lines = [
            f"{i.get('label')}: {i.get('value')}"
            for i in (tf.get("pricing") or {}).get("items", [])
            if i.get("value")
        ]

        pub_dt: datetime = self.seen.first_seen(f"amd:{model_id}")

        facts = [
            ("Publisher", publisher),
            ("Badge", badge.get("label", "")),
            ("Status", status),
            ("Use Case", capability),
            ("Providers", providers),
            ("Context Length", f"{context_length:,}" if context_length else ""),
            ("Model ID", model_id),
            ("Tags", " ".join(f"#{t}" for t in tags) if tags else ""),
            ("Pricing", " • ".join(pricing_lines)),
            ("Source", PAGE_URL),
        ]
        facts = [(k, v) for k, v in facts if v]

        summary = "\n".join(f"{k}: {v}" for k, v in facts if k != "Source")
        if description:
            summary = f"{description}\n{summary}"

        html = "<br/>\n".join(
            f"<b>{k}</b>: {v}" for k, v in facts if k != "Source"
        )
        if description:
            html = f"{description}<br/>\n{html}"
        html += f'<br/>\n<b>Model Page</b>: <a href="{PAGE_URL}" target="_blank">{PAGE_URL}</a>'

        categories = [c for c in [badge.get("label", ""), capability, publisher] if c]
        categories += tags

        return Item(
            source_key=self.key,
            source_label=self.label,
            title=name,
            link=PAGE_URL,
            guid=f"amd:{model_id}",
            pub_datetime=pub_dt,
            summary=summary,
            html=html,
            categories=list(dict.fromkeys(categories)),
        )
