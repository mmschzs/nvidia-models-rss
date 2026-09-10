#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ModelScope API-Inference Models RSS Generator
Fetches AI foundation models from https://api-inference.modelscope.cn/v1/models
and generates standardized RSS 2.0 and Atom 1.0 feeds.

Timestamp Strategy:
- If the remote endpoint provides a valid model timestamp ('created' > 0), use it.
- If the remote endpoint does not provide a timestamp, track and preserve the
  'first_seen' time when the model was first discovered locally.
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional
import xml.sax.saxutils as saxutils
import urllib.request
import urllib.error

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("modelscope_rss")

API_MODELS_URL = "https://api-inference.modelscope.cn/v1/models"
PORTAL_URL = "https://www.modelscope.cn/models"
DOCS_URL = "https://www.modelscope.cn/docs/model-service/API-Inference/intro"
DEFAULT_FEED_URL = "https://mmschzs.github.io/nvidia-models-rss/modelscope_rss.xml"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Known publisher branding & display names
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
    "MusePublic": {"name": "MusePublic", "color": "#a855f7"}
}


def fetch_models_from_api(url: str = API_MODELS_URL) -> List[Dict[str, Any]]:
    """Fetch model list from ModelScope API-Inference endpoint."""
    logger.info(f"Fetching models from {url} ...")
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Cache-Control": "no-cache",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8")
            data = json.loads(content)
            models = data.get("data", [])
            logger.info(f"Successfully fetched {len(models)} models from API.")
            return models
    except Exception as e:
        logger.error(f"Failed to fetch models from {url}: {e}")
        raise


def load_history(history_file: str) -> Dict[str, Any]:
    """Load model discovery history from JSON file."""
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
                logger.info(f"Loaded {len(history)} models from history file '{history_file}'.")
                return history
        except Exception as e:
            logger.warning(f"Could not read history file '{history_file}': {e}. Starting fresh.")
    return {}


def save_history(history_file: str, history: Dict[str, Any]) -> None:
    """Save model discovery history to JSON file."""
    os.makedirs(os.path.dirname(os.path.abspath(history_file)), exist_ok=True)
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved {len(history)} models history to '{history_file}'.")


def parse_timestamp_or_fallback(
    item: Dict[str, Any],
    history: Dict[str, Any],
    now_dt: datetime
) -> Tuple[datetime, str, bool]:
    """
    Determine the publication timestamp for a model:
    1. If remote endpoint provides a valid positive integer timestamp ('created'), use it.
    2. If remote endpoint lacks timestamp or provides invalid value:
       - Fall back to the persisted 'first_seen' discovery timestamp from history.
       - If not in history (first time seen), use now_dt and mark it to be persisted.

    Returns:
        (pub_datetime, time_source_description, is_newly_discovered)
    """
    model_id = item.get("id", "")
    remote_created = item.get("created")
    now_iso = now_dt.isoformat()

    has_valid_remote = False
    remote_dt: Optional[datetime] = None

    if remote_created is not None:
        try:
            ts = float(remote_created)
            if ts > 0:
                remote_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                has_valid_remote = True
        except (ValueError, TypeError, OverflowError):
            has_valid_remote = False

    is_new = model_id not in history
    model_history = history.setdefault(model_id, {})

    # Record / update first_seen
    if "first_seen" not in model_history:
        model_history["first_seen"] = now_iso
    model_history["last_seen"] = now_iso
    if remote_created is not None:
        model_history["remote_created"] = remote_created

    if has_valid_remote and remote_dt is not None:
        # Remote provided a valid time
        return remote_dt, "Remote API ('created')", is_new
    else:
        # Remote did NOT provide time; use first_seen timestamp
        first_seen_str = model_history.get("first_seen", now_iso)
        try:
            first_seen_dt = datetime.fromisoformat(first_seen_str)
            if first_seen_dt.tzinfo is None:
                first_seen_dt = first_seen_dt.replace(tzinfo=timezone.utc)
        except Exception:
            first_seen_dt = now_dt
        return first_seen_dt, "Local First-Seen (Fallback)", is_new


def extract_model_meta(item: Dict[str, Any]) -> Dict[str, Any]:
    """Extract metadata, publisher info, and links for a model."""
    model_id = item.get("id", "unknown/model")
    owned_by = item.get("owned_by", "system")

    if "/" in model_id:
        publisher_slug, model_short_name = model_id.split("/", 1)
    else:
        publisher_slug = owned_by or "ModelScope"
        model_short_name = model_id

    publisher_info = PUBLISHER_META.get(publisher_slug, {
        "name": publisher_slug,
        "color": "#64748b"
    })

    model_url = f"https://www.modelscope.cn/models/{model_id}"
    publisher_url = f"https://www.modelscope.cn/organization/{publisher_slug}"

    return {
        "model_id": model_id,
        "model_short_name": model_short_name,
        "publisher_slug": publisher_slug,
        "publisher_name": publisher_info["name"],
        "publisher_color": publisher_info["color"],
        "publisher_url": publisher_url,
        "model_url": model_url,
        "owned_by": owned_by,
    }


def generate_item_html(model: Dict[str, Any]) -> str:
    """Generate clean semantic HTML content for RSS readers."""
    model_id = model["model_id"]
    publisher_name = model["publisher_name"]
    publisher_color = model["publisher_color"]
    model_url = model["model_url"]
    pub_dt: datetime = model["pub_datetime"]
    time_source = model["time_source"]
    first_seen_str = model["first_seen_str"]
    pub_time_str = pub_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

    html = f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;line-height:1.6;color:#1e293b;max-width:720px;">
  <div style="margin-bottom:16px;">
    <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;background:{publisher_color};color:#ffffff;margin-right:8px;">
      {saxutils.escape(publisher_name)}
    </span>
    <span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:500;background:#e2e8f0;color:#334155;">
      ModelScope API-Inference
    </span>
  </div>

  <table style="width:100%;border-collapse:collapse;margin-bottom:16px;font-size:14px;">
    <tr style="border-bottom:1px solid #e2e8f0;">
      <td style="padding:6px 0;font-weight:600;color:#475569;width:130px;">Model Identifier</td>
      <td style="padding:6px 0;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;color:#0f172a;font-weight:600;">{saxutils.escape(model_id)}</td>
    </tr>
    <tr style="border-bottom:1px solid #e2e8f0;">
      <td style="padding:6px 0;font-weight:600;color:#475569;">Release Time</td>
      <td style="padding:6px 0;color:#0f172a;">{pub_time_str} <span style="font-size:12px;color:#64748b;">({saxutils.escape(time_source)})</span></td>
    </tr>
    <tr style="border-bottom:1px solid #e2e8f0;">
      <td style="padding:6px 0;font-weight:600;color:#475569;">First Discovered</td>
      <td style="padding:6px 0;color:#0f172a;">{saxutils.escape(first_seen_str)}</td>
    </tr>
    <tr style="border-bottom:1px solid #e2e8f0;">
      <td style="padding:6px 0;font-weight:600;color:#475569;">Model Homepage</td>
      <td style="padding:6px 0;"><a href="{saxutils.escape(model_url)}" target="_blank" style="color:#2563eb;text-decoration:none;font-weight:500;">{saxutils.escape(model_url)}</a></td>
    </tr>
    <tr>
      <td style="padding:6px 0;font-weight:600;color:#475569;">Inference Base URL</td>
      <td style="padding:6px 0;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;color:#0f172a;">https://api-inference.modelscope.cn/v1</td>
    </tr>
  </table>

  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;margin-top:16px;">
    <div style="font-weight:600;font-size:13px;color:#334155;margin-bottom:8px;">🚀 Quick Start (OpenAI Compatible Python SDK):</div>
    <pre style="background:#0f172a;color:#f8fafc;padding:12px;border-radius:6px;font-size:12px;overflow-x:auto;margin:0;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;">from openai import OpenAI

client = OpenAI(
    base_url="https://api-inference.modelscope.cn/v1",
    api_key="YOUR_MODELSCOPE_API_KEY",
)

response = client.chat.completions.create(
    model="{saxutils.escape(model_id)}",
    messages=[{{"role": "user", "content": "Hello!"}}],
)
print(response.choices[0].message.content)</pre>
  </div>
</div>"""
    return html


def build_rss_xml(
    models: List[Dict[str, Any]],
    feed_title: str = "ModelScope API-Inference Models",
    feed_link: str = PORTAL_URL,
    feed_desc: str = "Real-time updates of AI foundation models available on ModelScope API-Inference",
    self_url: str = DEFAULT_FEED_URL,
) -> str:
    """Build standard RSS 2.0 feed with clean description and content:encoded."""
    now_utc = datetime.now(timezone.utc)
    now_rfc = now_utc.strftime("%a, %d %b %Y %H:%M:%S +0000")

    sorted_models = sorted(models, key=lambda m: m["pub_datetime"], reverse=True)

    items_xml = ""
    for m in sorted_models:
        model_id = m["model_id"]
        publisher_name = m["publisher_name"]
        model_url = m["model_url"]
        pub_dt: datetime = m["pub_datetime"]
        pub_rfc = pub_dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
        time_source = m["time_source"]

        title = f"[{m['publisher_slug']}] {m['model_short_name']}"

        # Plain text summary for <description>
        plain_summary = (
            f"Model: {model_id}\n"
            f"Publisher: {publisher_name}\n"
            f"Release Time: {pub_dt.strftime('%Y-%m-%d %H:%M:%S UTC')} ({time_source})\n"
            f"Endpoint: https://api-inference.modelscope.cn/v1\n"
            f"URL: {model_url}"
        )

        html_content = generate_item_html(m)

        categories = [m["publisher_slug"], "ModelScope", "API-Inference"]
        categories_xml = "".join(
            f"    <category>{saxutils.escape(c)}</category>\n"
            for c in categories
        )

        items_xml += f"""  <item>
    <title>{saxutils.escape(title)}</title>
    <link>{saxutils.escape(model_url)}</link>
    <guid isPermaLink="false">modelscope:model:{saxutils.escape(model_id)}</guid>
    <pubDate>{pub_rfc}</pubDate>
    <description>{saxutils.escape(plain_summary)}</description>
    <content:encoded><![CDATA[{html_content}]]></content:encoded>
{categories_xml}  </item>
"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>{saxutils.escape(feed_title)}</title>
    <link>{saxutils.escape(feed_link)}</link>
    <description>{saxutils.escape(feed_desc)}</description>
    <atom:link href="{saxutils.escape(self_url)}" rel="self" type="application/rss+xml"/>
    <language>zh-cn</language>
    <lastBuildDate>{now_rfc}</lastBuildDate>
{items_xml}  </channel>
</rss>
"""


def build_atom_xml(
    models: List[Dict[str, Any]],
    feed_title: str = "ModelScope API-Inference Models",
    feed_link: str = PORTAL_URL,
    feed_desc: str = "Real-time updates of AI foundation models available on ModelScope API-Inference",
    self_url: str = DEFAULT_FEED_URL.replace("rss.xml", "atom.xml"),
) -> str:
    """Build standard Atom 1.0 feed."""
    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()

    sorted_models = sorted(models, key=lambda m: m["pub_datetime"], reverse=True)

    entries_xml = ""
    for m in sorted_models:
        model_id = m["model_id"]
        publisher_name = m["publisher_name"]
        model_url = m["model_url"]
        pub_dt: datetime = m["pub_datetime"]
        pub_iso = pub_dt.isoformat()
        time_source = m["time_source"]

        title = f"[{m['publisher_slug']}] {m['model_short_name']}"
        summary = f"Model: {model_id} by {publisher_name} ({time_source})"
        html_content = generate_item_html(m)

        entries_xml += f"""  <entry>
    <title>{saxutils.escape(title)}</title>
    <link href="{saxutils.escape(model_url)}" rel="alternate"/>
    <id>urn:modelscope:model:{saxutils.escape(model_id)}</id>
    <updated>{pub_iso}</updated>
    <published>{pub_iso}</published>
    <summary>{saxutils.escape(summary)}</summary>
    <author>
      <name>{saxutils.escape(publisher_name)}</name>
    </author>
    <content type="html">{saxutils.escape(html_content)}</content>
  </entry>
"""

    return f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>{saxutils.escape(feed_title)}</title>
  <subtitle>{saxutils.escape(feed_desc)}</subtitle>
  <link href="{saxutils.escape(feed_link)}" rel="alternate"/>
  <link href="{saxutils.escape(self_url)}" rel="self" type="application/atom+xml"/>
  <id>{saxutils.escape(feed_link)}</id>
  <updated>{now_iso}</updated>
{entries_xml}</feed>
"""


def generate_preview_page(models: List[Dict[str, Any]], output_path: str) -> None:
    """Generate a responsive static preview page for ModelScope feeds."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    sorted_models = sorted(models, key=lambda m: m["pub_datetime"], reverse=True)

    cards_html = []
    for m in sorted_models:
        model_id = m["model_id"]
        publisher_name = m["publisher_name"]
        publisher_color = m["publisher_color"]
        pub_dt: datetime = m["pub_datetime"]
        pub_str = pub_dt.strftime("%Y-%m-%d %H:%M UTC")
        time_source = m["time_source"]
        model_url = m["model_url"]

        card = f"""
        <div class="card">
          <div class="card-header">
            <span class="badge" style="background:{publisher_color};">{saxutils.escape(publisher_name)}</span>
            <span class="date-badge" title="Source: {saxutils.escape(time_source)}">{pub_str}</span>
          </div>
          <h3 class="card-title">
            <a href="{saxutils.escape(model_url)}" target="_blank" rel="noopener noreferrer">{saxutils.escape(model_id)}</a>
          </h3>
          <div class="card-meta">
            <span>🕒 时间来源: <strong>{saxutils.escape(time_source)}</strong></span>
            <span>⚡ API ID: <code>{saxutils.escape(model_id)}</code></span>
          </div>
          <div class="card-actions">
            <a href="{saxutils.escape(model_url)}" target="_blank" rel="noopener noreferrer" class="btn-card">查看模型主页 &rarr;</a>
          </div>
        </div>
        """
        cards_html.append(card)

    cards_content = "\n".join(cards_html)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ModelScope API-Inference Models RSS Feed</title>
  <link rel="icon" href="https://www.modelscope.cn/favicon.ico" type="image/x-icon">
  <style>
    :root {{
      --bg: #0f172a;
      --card-bg: #1e293b;
      --card-hover: #273549;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --border: #334155;
      --accent: #3b82f6;
      --accent-hover: #2563eb;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.6;
      padding: 40px 20px;
    }}
    .container {{
      max-width: 1080px;
      margin: 0 auto;
    }}
    header {{
      text-align: center;
      margin-bottom: 40px;
    }}
    h1 {{
      font-size: 2.2rem;
      font-weight: 800;
      margin-bottom: 12px;
      background: linear-gradient(135deg, #60a5fa, #a855f7);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    p.subtitle {{
      color: var(--text-muted);
      font-size: 1.05rem;
      margin-bottom: 24px;
    }}
    .feed-buttons {{
      display: flex;
      justify-content: center;
      gap: 16px;
      flex-wrap: wrap;
      margin-bottom: 24px;
    }}
    .btn {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 10px 20px;
      border-radius: 8px;
      font-weight: 600;
      font-size: 0.95rem;
      text-decoration: none;
      transition: all 0.2s ease;
    }}
    .btn-rss {{ background: #f97316; color: #ffffff; }}
    .btn-rss:hover {{ background: #ea580c; transform: translateY(-1px); }}
    .btn-atom {{ background: #3b82f6; color: #ffffff; }}
    .btn-atom:hover {{ background: #2563eb; transform: translateY(-1px); }}
    .btn-portal {{ background: #475569; color: #ffffff; }}
    .btn-portal:hover {{ background: #64748b; transform: translateY(-1px); }}
    .meta-bar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px 20px;
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      font-size: 0.85rem;
      color: var(--text-muted);
      margin-bottom: 32px;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 20px;
    }}
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 20px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: transform 0.2s ease, border-color 0.2s ease;
    }}
    .card:hover {{
      transform: translateY(-2px);
      border-color: #475569;
      background: var(--card-hover);
    }}
    .card-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
    }}
    .badge {{
      color: #ffffff;
      font-size: 0.75rem;
      font-weight: 600;
      padding: 4px 10px;
      border-radius: 9999px;
    }}
    .date-badge {{
      font-size: 0.8rem;
      color: var(--text-muted);
    }}
    .card-title {{
      font-size: 1.1rem;
      font-weight: 700;
      margin-bottom: 12px;
      word-break: break-all;
    }}
    .card-title a {{
      color: #f1f5f9;
      text-decoration: none;
    }}
    .card-title a:hover {{
      color: var(--accent);
    }}
    .card-meta {{
      display: flex;
      flex-direction: column;
      gap: 6px;
      font-size: 0.82rem;
      color: var(--text-muted);
      margin-bottom: 16px;
    }}
    .card-meta code {{
      background: #0f172a;
      padding: 2px 6px;
      border-radius: 4px;
      color: #cbd5e1;
    }}
    .card-actions {{
      margin-top: auto;
      border-top: 1px solid var(--border);
      padding-top: 12px;
    }}
    .btn-card {{
      color: var(--accent);
      text-decoration: none;
      font-size: 0.85rem;
      font-weight: 600;
    }}
    .btn-card:hover {{
      text-decoration: underline;
    }}
    footer {{
      text-align: center;
      margin-top: 50px;
      color: var(--text-muted);
      font-size: 0.85rem;
      border-top: 1px solid var(--border);
      padding-top: 24px;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>ModelScope API-Inference Models RSS</h1>
      <p class="subtitle">跟踪魔搭平台 API-Inference 开放服务上的最新大模型上线动态</p>
      <div class="feed-buttons">
        <a href="modelscope_rss.xml" class="btn btn-rss">📡 订阅 RSS 2.0</a>
        <a href="modelscope_atom.xml" class="btn btn-atom">⚛️ 订阅 Atom 1.0</a>
        <a href="index.html" class="btn btn-portal" style="background:#76b900;">🟢 NVIDIA Models 源</a>
        <a href="https://www.modelscope.cn/docs/model-service/API-Inference/intro" target="_blank" rel="noopener noreferrer" class="btn btn-portal">📖 官方接入文档</a>
      </div>
    </header>

    <div class="meta-bar">
      <span>📦 当前在线模型数: <strong>{len(models)}</strong></span>
      <span>🕒 最近更新时间: <strong>{now_str}</strong></span>
      <span>⏱️ 时间规则: <strong>远端提供优先 / 首次收录保底</strong></span>
    </div>

    <div class="grid">
      {cards_content}
    </div>

    <footer>
      <p>Data sourced from <a href="https://api-inference.modelscope.cn/v1/models" target="_blank" style="color:var(--text-muted)">ModelScope API-Inference</a> &bull; Automated RSS Generator</p>
    </footer>
  </div>
</body>
</html>
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"Generated preview page at '{output_path}'.")


def main():
    parser = argparse.ArgumentParser(description="Generate RSS feed for ModelScope API-Inference models.")
    parser.add_argument("--output-dir", default="dist", help="Directory to save generated RSS and HTML files.")
    parser.add_argument("--history-file", default=os.path.join("data", "modelscope_history.json"),
                        help="Path to JSON file tracking model discovery history.")
    parser.add_argument("--rss-name", default="modelscope_rss.xml", help="RSS filename.")
    parser.add_argument("--atom-name", default="modelscope_atom.xml", help="Atom filename.")
    parser.add_argument("--preview-name", default="modelscope.html", help="HTML preview filename.")
    parser.add_argument("--feed-url", default=DEFAULT_FEED_URL, help="Self link URL for RSS XML.")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    history = load_history(args.history_file)
    now_dt = datetime.now(timezone.utc)

    # 1. Fetch raw models from API
    raw_models = fetch_models_from_api()

    # 2. Process models and timestamps
    processed_models = []
    new_models_count = 0

    for item in raw_models:
        meta = extract_model_meta(item)
        pub_dt, time_source, is_new = parse_timestamp_or_fallback(item, history, now_dt)
        if is_new:
            new_models_count += 1
            logger.info(f"🆕 Discovered new model: {meta['model_id']} (time: {pub_dt.isoformat()}, source: {time_source})")

        model_info = {
            **meta,
            "raw": item,
            "pub_datetime": pub_dt,
            "time_source": time_source,
            "first_seen_str": history.get(meta["model_id"], {}).get("first_seen", now_dt.isoformat())
        }
        processed_models.append(model_info)

    # 3. Save updated history
    save_history(args.history_file, history)
    if new_models_count > 0:
        logger.info(f"Recorded {new_models_count} new models into history.")
    else:
        logger.info("No new models discovered in this run.")

    # 4. Generate RSS 2.0
    rss_path = os.path.join(args.output_dir, args.rss_name)
    rss_xml = build_rss_xml(processed_models, self_url=args.feed_url)
    with open(rss_path, "w", encoding="utf-8") as f:
        f.write(rss_xml)
    logger.info(f"Generated RSS 2.0 feed at '{rss_path}' ({os.path.getsize(rss_path)} bytes).")

    # 5. Generate Atom 1.0
    atom_path = os.path.join(args.output_dir, args.atom_name)
    atom_xml = build_atom_xml(processed_models, self_url=args.feed_url.replace("rss.xml", "atom.xml"))
    with open(atom_path, "w", encoding="utf-8") as f:
        f.write(atom_xml)
    logger.info(f"Generated Atom 1.0 feed at '{atom_path}' ({os.path.getsize(atom_path)} bytes).")

    # 6. Generate Preview Page
    preview_path = os.path.join(args.output_dir, args.preview_name)
    generate_preview_page(processed_models, preview_path)

    logger.info("ModelScope RSS generation completed successfully.")


if __name__ == "__main__":
    main()
