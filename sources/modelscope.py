# -*- coding: utf-8 -*-
"""ModelScope API-Inference models scraper (https://api-inference.modelscope.cn).

Fetches OpenAI-compatible foundation model catalog from ModelScope API-Inference.
If a remote model supplies a valid 'created' timestamp, it is used. Otherwise,
the first-seen discovery timestamp is persisted via SeenStore.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import xml.sax.saxutils as saxutils

from .base import Item, Source

logger = logging.getLogger("models_rss")

API_MODELS_URL = "https://api-inference.modelscope.cn/v1/models"
PORTAL_URL = "https://www.modelscope.cn/models"

PUBLISHER_META = {
    "deepseek-ai": {"name": "DeepSeek (深度求索)", "color": "#0ea5e9"},
    "Qwen": {"name": "Qwen (通义千问)", "color": "#6366f1"},
    "ZhipuAI": {"name": "Zhipu AI (智谱清言)", "color": "#2563eb"},
    "stepfun-ai": {"name": "Stepfun (阶跃星辰)", "color": "#8b5cf6"},
    "MiniMax": {"name": "MiniMax (名之梦)", "color": "#ec4899"},
    "Tencent-Hunyuan": {"name": "Tencent Hunyuan (腾讯混元)", "color": "#0052d9"},
    "Shanghai_AI_Laboratory": {"name": "Shanghai AI Lab (书生)", "color": "#059669"},
    "OpenGVLab": {"name": "OpenGVLab (书生·通用视觉)", "color": "#10b981"},
    "PaddlePaddle": {"name": "PaddlePaddle (百度飞桨·文心)", "color": "#2932e1"},
    "mistralai": {"name": "Mistral AI", "color": "#f97316"},
    "meituan-longcat": {"name": "Meituan LongCat (美团)", "color": "#ffc300"},
    "opencompass": {"name": "OpenCompass (司南)", "color": "#14b8a6"},
    "XGenerationLab": {"name": "XGenerationLab (析言)", "color": "#d97706"},
    "MedAIBase": {"name": "MedAIBase (医疗AI)", "color": "#0284c7"},
    "early-access": {"name": "Early Access (抢先体验)", "color": "#ef4444"},
    "MusePublic": {"name": "MusePublic", "color": "#a855f7"},
}


class ModelScopeSource(Source):
    key = "modelscope"
    label = "ModelScope"
    home_url = PORTAL_URL

    def fetch(self) -> List[Item]:
        logger.info(f"[modelscope] Fetching models from {API_MODELS_URL}")
        data = self.get_json(API_MODELS_URL)
        models = data.get("data", []) if isinstance(data, dict) else []
        logger.info(f"[modelscope] Returned {len(models)} models")

        items: List[Item] = []
        for raw in models:
            item = self._to_item(raw)
            if item:
                items.append(item)
        return items

    def _to_item(self, model: Dict[str, Any]) -> Optional[Item]:
        model_id = model.get("id")
        if not model_id:
            return None

        owned_by = model.get("owned_by", "system")
        if "/" in model_id:
            publisher_slug, model_short_name = model_id.split("/", 1)
        else:
            publisher_slug = owned_by or "ModelScope"
            model_short_name = model_id

        publisher_info = PUBLISHER_META.get(publisher_slug, {
            "name": publisher_slug,
            "color": "#64748b"
        })
        publisher_name = publisher_info["name"]

        # Timestamp Strategy: remote 'created' if valid (>0), else seen.first_seen fallback
        remote_created = model.get("created")
        has_valid_remote = False
        remote_dt = None
        if remote_created is not None:
            try:
                ts = float(remote_created)
                if ts > 0:
                    remote_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    has_valid_remote = True
            except (ValueError, TypeError, OverflowError):
                has_valid_remote = False

        if has_valid_remote and remote_dt is not None:
            pub_dt = remote_dt
            time_source = "Remote API ('created')"
        else:
            pub_dt = self.seen.first_seen(f"modelscope:{model_id}")
            time_source = "Local First-Seen (Fallback)"

        model_url = f"https://www.modelscope.cn/models/{model_id}"
        pub_time_str = pub_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

        facts = [
            ("Model ID", model_id),
            ("Publisher", publisher_name),
            ("Release Time", f"{pub_time_str} ({time_source})"),
            ("Endpoint", "https://api-inference.modelscope.cn/v1"),
            ("Model Page", model_url),
        ]

        summary = "\n".join(f"{k}: {v}" for k, v in facts)
        html = "<br/>\n".join(
            f"<b>{k}</b>: {saxutils.escape(v)}" for k, v in facts if k != "Model Page"
        )
        html += f'<br/>\n<b>Model Page</b>: <a href="{saxutils.escape(model_url)}" target="_blank">{saxutils.escape(model_url)}</a>'

        categories = [publisher_slug, "ModelScope", "API-Inference"]

        return Item(
            source_key=self.key,
            source_label=self.label,
            title=f"[{publisher_slug}] {model_short_name}",
            link=model_url,
            guid=f"modelscope:{model_id}",
            pub_datetime=pub_dt,
            summary=summary,
            html=html,
            categories=categories,
        )
