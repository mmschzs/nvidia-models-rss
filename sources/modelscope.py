# -*- coding: utf-8 -*-
"""ModelScope API-Inference scraper (https://api-inference.modelscope.cn).

Uses the OpenAI compatible ``GET /v1/models`` endpoint. Each entry exposes a
``created`` unix timestamp, which is used directly as the entry date. Models
without one fall back to the first-crawl date.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import Item, Source

logger = logging.getLogger("models_rss")

API_HOME = "https://api-inference.modelscope.cn"
MODELS_URL = "https://api-inference.modelscope.cn/v1/models"
MODEL_PAGE = "https://www.modelscope.cn/models/{model_id}"


class ModelScopeSource(Source):
    key = "modelscope"
    label = "ModelScope"
    home_url = API_HOME

    def fetch(self) -> List[Item]:
        payload = self.get_json(MODELS_URL, {"Accept": "application/json"})
        entries = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            logger.warning(f"[modelscope] unexpected payload: {type(payload)}")
            return []

        logger.info(f"[modelscope] {len(entries)} models returned")
        items = [self._to_item(m) for m in entries if isinstance(m, dict)]
        return [i for i in items if i]

    def _to_item(self, m: Dict[str, Any]) -> Optional[Item]:
        model_id = (m.get("id") or "").strip()
        if not model_id:
            return None

        namespace = model_id.split("/", 1)[0] if "/" in model_id else ""
        created = m.get("created")

        pub_dt: Optional[datetime] = None
        if isinstance(created, (int, float)) and created > 0:
            pub_dt = datetime.fromtimestamp(created, tz=timezone.utc)
        if pub_dt is None:
            pub_dt = self.seen.first_seen(f"modelscope:{model_id}")

        link = MODEL_PAGE.format(model_id=model_id)
        created_str = pub_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

        facts = [
            ("Model", model_id),
            ("Namespace", namespace),
            ("Owner", m.get("owned_by") or ""),
            ("Created", created_str),
            ("Endpoint", MODELS_URL),
        ]
        facts = [(k, v) for k, v in facts if v]

        summary = "\n".join(f"{k}: {v}" for k, v in facts)
        html = "<br/>\n".join(
            f"<b>{k}</b>: {v}" if k != "Model" else f"<b>{k}</b>: <a href=\"{link}\" target=\"_blank\">{v}</a>"
            for k, v in facts
        )

        return Item(
            source_key=self.key,
            source_label=self.label,
            title=model_id,
            link=link,
            guid=f"modelscope:{model_id}",
            pub_datetime=pub_dt,
            summary=summary,
            html=html,
            categories=[c for c in [namespace] if c],
        )
