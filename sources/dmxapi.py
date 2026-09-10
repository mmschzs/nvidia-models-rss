# -*- coding: utf-8 -*-
"""DMXAPI free-model scraper (https://www.dmxapi.cn).

``GET /v1/models`` needs a bearer token (``DMX_API_KEY`` env var / CI secret).
Free models are the ones whose id ends with ``free``.

The API's ``created`` field is a placeholder (every model reports 2021-07-20),
so the entry date is the first time we saw the model, persisted in
``state/seen.json``.
"""

import logging
import os
from typing import Any, Dict, List

from .base import Item, Source

logger = logging.getLogger("models_rss")

SITE_URL = "https://www.dmxapi.cn"
API_URL = "https://www.dmxapi.cn/v1/models"
API_BASE = "https://www.dmxapi.cn/v1"


class DmxapiSource(Source):
    key = "dmxapi"
    label = "DMXAPI"
    home_url = SITE_URL

    def fetch(self) -> List[Item]:
        api_key = os.environ.get("DMX_API_KEY", "").strip()
        if not api_key:
            logger.warning(
                "[dmxapi] DMX_API_KEY is not set - skipping source. "
                "Add it as a repository secret to enable this feed."
            )
            return []

        payload = self.get_json(
            API_URL,
            {
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )
        entries = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            logger.warning(f"[dmxapi] unexpected payload: {type(payload)}")
            return []

        free_models = [
            m for m in entries
            if isinstance(m, dict) and str(m.get("id", "")).strip().lower().endswith("free")
        ]
        logger.info(f"[dmxapi] {len(entries)} models, {len(free_models)} free")

        items = [self._to_item(m) for m in free_models]
        return [i for i in items if i]

    def _to_item(self, m: Dict[str, Any]) -> Item:
        model_id = str(m.get("id", "")).strip()
        owned_by = m.get("owned_by") or "unknown"
        endpoints = [str(e) for e in (m.get("supported_endpoint_types") or [])]
        endpoints_str = ", ".join(endpoints) if endpoints else "openai"

        pub_dt = self.seen.first_seen(f"dmxapi:{model_id}")

        facts = [
            ("Model", model_id),
            ("Vendor", owned_by),
            ("Endpoints", endpoints_str),
            ("Base URL", API_BASE),
            ("First seen", pub_dt.strftime("%Y-%m-%d %H:%M:%S UTC")),
        ]
        summary = "\n".join(f"{k}: {v}" for k, v in facts)

        is_rerank = any("rerank" in e.lower() for e in endpoints) or "rerank" in model_id.lower()
        curl = _curl_example(model_id, is_rerank)

        html = "<br/>\n".join(f"<b>{k}</b>: {v}" for k, v in facts)
        html += f'<br/>\n<b>Quick test</b>:<br/><pre>{_escape(curl)}</pre>'
        html += f'<br/>\n<b>Site</b>: <a href="{SITE_URL}" target="_blank">{SITE_URL}</a>'

        return Item(
            source_key=self.key,
            source_label=self.label,
            title=model_id,
            link=SITE_URL,
            guid=f"dmxapi:{model_id}",
            pub_datetime=pub_dt,
            summary=summary,
            html=html,
            categories=list(dict.fromkeys([owned_by] + endpoints)),
        )


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _curl_example(model_id: str, is_rerank: bool) -> str:
    if is_rerank:
        return (
            f"curl {API_BASE}/rerank \\\n"
            f'  -H "Content-Type: application/json" \\\n'
            f'  -H "Authorization: Bearer $DMX_API_KEY" \\\n'
            f"  -d '{{\"model\": \"{model_id}\", \"query\": \"hello\", "
            f"\"documents\": [\"doc a\", \"doc b\"]}}'"
        )
    return (
        f"curl {API_BASE}/chat/completions \\\n"
        f'  -H "Content-Type: application/json" \\\n'
        f'  -H "Authorization: Bearer $DMX_API_KEY" \\\n'
        f"  -d '{{\"model\": \"{model_id}\", "
        f"\"messages\": [{{\"role\": \"user\", \"content\": \"Hello!\"}}]}}'"
    )
