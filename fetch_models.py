#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NVIDIA Models RSS Generator
Fetches latest AI foundation models and NIMs from https://build.nvidia.com/models
and generates standardized RSS 2.0 (dist/rss.xml) and Atom 1.0 (dist/atom.xml) feeds.
"""

import os
import re
import sys
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from feedgen.feed import FeedGenerator

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("nvidia_models_rss")

BASE_URL = "https://build.nvidia.com"
MODELS_URL = "https://build.nvidia.com/models"
FEED_HOME_URL = "https://build.nvidia.com/models"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Known publishers map for normalization
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
    "z-ai": "Z.ai"
}

# Brand colors for badges
PUBLISHER_COLORS = {
    "NVIDIA": "#76b900",
    "Meta": "#0081fb",
    "Google": "#4285f4",
    "Microsoft": "#00a4ef",
    "Qwen": "#6366f1",
    "DeepSeek": "#0ea5e9",
    "OpenAI": "#10a37f",
    "Anthropic": "#d97706",
    "Mistral AI": "#f97316",
    "Stepfun-ai": "#8b5cf6",
    "Thinking Machines": "#ec4899",
    "Poolside": "#06b6d4",
    "Resemble.AI": "#14b8a6",
    "Z.ai": "#3b82f6"
}


def fetch_page_content(url: str = MODELS_URL) -> str:
    """Fetch HTML content from target URL with proper headers."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    }
    logger.info(f"Fetching models from {url} ...")
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    logger.info(f"Fetched {len(resp.text)} bytes (HTTP {resp.status_code})")
    return resp.text


def parse_next_data(html: str) -> Optional[List[Dict[str, Any]]]:
    """Strategy 1: Try parsing Next.js __NEXT_DATA__ script tag if available."""
    soup = BeautifulSoup(html, 'html.parser')
    script = soup.find('script', id='__NEXT_DATA__')
    if not script or not script.string:
        return None

    try:
        data = json.loads(script.string)
        page_props = data.get('props', {}).get('pageProps', {})
        for key in ['models', 'initialModels', 'cards', 'items', 'data']:
            if key in page_props and isinstance(page_props[key], list) and page_props[key]:
                logger.info(f"Found {len(page_props[key])} models in __NEXT_DATA__['{key}']")
                models = []
                for item in page_props[key]:
                    if isinstance(item, dict):
                        name = item.get("name") or item.get("displayName") or item.get("id")
                        pub = item.get("publisher") or item.get("org") or item.get("author") or "NVIDIA"
                        link = item.get("url") or (f"{BASE_URL}{item.get('link')}" if item.get("link") else None)
                        models.append({
                            "name": name,
                            "publisher": pub,
                            "publisher_url": f"{BASE_URL}/{pub.lower()}",
                            "url": link,
                            "description": item.get("description") or item.get("summary") or "",
                            "tags": item.get("tags") or item.get("labels") or [],
                            "badges": item.get("badges") or [],
                            "updated_str": item.get("updatedAt") or item.get("lastUpdated") or "",
                            "pub_datetime": parse_datetime_safe(item.get("updatedAt") or item.get("date")),
                            "stats": item.get("stats") or [],
                            "image": item.get("image") or item.get("logo") or None
                        })
                if models:
                    return models
    except Exception as e:
        logger.warning(f"Error parsing __NEXT_DATA__: {e}")

    return None


def parse_rsc_stream(html: str) -> Optional[List[Dict[str, Any]]]:
    """Strategy 2: Extract React Query or model objects from Next.js App Router RSC stream."""
    soup = BeautifulSoup(html, 'html.parser')
    scripts = soup.find_all('script')
    
    rsc_lines = []
    for s in scripts:
        if s.string and 'self.__next_f.push' in s.string:
            for match in re.finditer(r'self\.__next_f\.push\(\[\d+,\s*"(.*?)"\]\)', s.string):
                raw = match.group(1)
                try:
                    unescaped = bytes(raw, "utf-8").decode("unicode_escape")
                    rsc_lines.append(unescaped)
                except Exception:
                    rsc_lines.append(raw)

    full_rsc = "\n".join(rsc_lines)
    for line in full_rsc.split('\n'):
        if 'queryKey' in line and 'models' in line:
            try:
                idx = line.find('{')
                if idx != -1:
                    parsed = json.loads(line[idx:])
                    queries = parsed.get('state', {}).get('queries', [])
                    for q in queries:
                        data = q.get('state', {}).get('data')
                        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                            logger.info(f"Extracted {len(data)} models from RSC stream queries")
                            return data
            except Exception:
                pass

    return None


def parse_datetime_safe(val: Any) -> datetime:
    """Safely convert string or timestamp to UTC datetime."""
    if not val:
        return datetime.now(timezone.utc)
    if isinstance(val, (int, float)):
        # Check if milliseconds timestamp
        if val > 1e11:
            val = val / 1000.0
        return datetime.fromtimestamp(val, tz=timezone.utc)
    if isinstance(val, str):
        try:
            return date_parser.parse(val).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc)


def parse_dom_cards(html: str) -> List[Dict[str, Any]]:
    """Strategy 3 (Primary & robust): Parse HTML DOM card elements directly."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Locate model cards: either data-testid="nv-card-root" or class nv-card-root
    cards = soup.find_all(attrs={'data-testid': 'nv-card-root'})
    if not cards:
        cards = soup.find_all('div', class_=re.compile(r'nv-card-root'))
    
    logger.info(f"DOM parser found {len(cards)} model card elements.")
    models = []
    
    for i, card in enumerate(cards):
        try:
            # 1. Extract Publisher
            pub_el = card.find('a', attrs={'data-nvtrack-nav-object': 'artifact-card-publisher-link'})
            publisher = ""
            publisher_url = ""
            if pub_el:
                publisher = pub_el.get_text(strip=True)
                pub_href = pub_el.get('href', '')
                publisher_url = f"{BASE_URL}{pub_href}" if pub_href.startswith('/') else pub_href
            
            # 2. Extract Badges (e.g. Downloadable, Free Endpoint)
            badges = []
            badge_els = card.find_all(attrs={'data-testid': 'nv-badge'})
            for b in badge_els:
                btxt = b.get_text(strip=True)
                if btxt and btxt not in badges:
                    badges.append(btxt)

            # 3. Extract Model Name & URL
            model_el = card.find('a', attrs={'data-nvtrack-nav-object': 'artifact-card'})
            model_name = ""
            model_url = ""
            if model_el:
                name_span = model_el.find(attrs={'data-testid': 'nv-text'})
                model_name = name_span.get_text(strip=True) if name_span else model_el.get_text(strip=True)
                href = model_el.get('href', '')
                model_url = f"{BASE_URL}{href}" if href.startswith('/') else href
            
            # Fallback for publisher/model links if needed
            if not model_url or not publisher:
                all_links = card.find_all('a')
                for a in all_links:
                    href = a.get('href', '')
                    text = a.get_text(strip=True)
                    parts = [p for p in href.strip('/').split('/') if p]
                    if len(parts) == 1 and not parts[0].startswith('models') and not publisher:
                        publisher = text or parts[0]
                        publisher_url = f"{BASE_URL}{href}"
                    elif len(parts) == 2 and parts[0] not in ['models', 'api', 'docs'] and not model_url:
                        model_name = text or parts[1]
                        model_url = f"{BASE_URL}{href}"

            if not model_name:
                continue

            if not publisher:
                if model_url:
                    path_parts = model_url.replace(BASE_URL, '').strip('/').split('/')
                    if len(path_parts) >= 2:
                        raw_pub = path_parts[0]
                        publisher = KNOWN_PUBLISHERS.get(raw_pub.lower(), raw_pub.capitalize())
                if not publisher:
                    publisher = "NVIDIA"

            # 4. Extract Description
            desc_el = card.find('span', class_=re.compile(r'line-clamp-\d+|label-regular-md'))
            desc = ""
            if desc_el:
                desc = desc_el.get_text(strip=True)
            
            if not desc:
                for s in card.find_all(['span', 'p']):
                    stxt = s.get_text(strip=True)
                    if len(stxt) > 25 and stxt != model_name and not stxt.startswith('Last updated'):
                        desc = stxt
                        break

            # 5. Extract Tags
            tags = []
            tag_els = card.find_all(attrs={'data-testid': 'nv-tag-root'})
            for t in tag_els:
                ttxt = t.get_text(strip=True)
                if ttxt and ttxt != '+' and ttxt not in tags:
                    tags.append(ttxt)
            
            for a in card.find_all('a', href=re.compile(r'/models\?')):
                ttxt = a.get_text(strip=True)
                if ttxt and ttxt != '+' and ttxt not in tags:
                    tags.append(ttxt)

            # 6. Extract Last Updated Date & Stats
            updated_date_str = ""
            pub_datetime = None
            
            for el in card.find_all(attrs={'aria-label': True}):
                label = el.get('aria-label', '')
                if any(m in label for m in ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']):
                    updated_date_str = label
                    break
            
            if not updated_date_str:
                for s in card.stripped_strings:
                    match = re.search(r'Last updated on\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})', s, re.I)
                    if match:
                        updated_date_str = match.group(1)
                        break
            
            if updated_date_str:
                try:
                    pub_datetime = date_parser.parse(updated_date_str).replace(tzinfo=timezone.utc)
                except Exception as e:
                    logger.debug(f"Date parse error for '{updated_date_str}': {e}")

            if not pub_datetime:
                pub_datetime = datetime.now(timezone.utc)

            # 7. Extract Stats (API calls, downloads)
            stats = []
            for s in card.stripped_strings:
                if 'API calls' in s or 'downloads' in s.lower():
                    if s not in stats:
                        stats.append(s)

            # 8. Extract Image
            img_url = None
            img_el = card.find('img')
            if img_el and img_el.get('src'):
                img_src = img_el.get('src')
                img_url = f"{BASE_URL}{img_src}" if img_src.startswith('/') else img_src

            models.append({
                "name": model_name,
                "publisher": publisher,
                "publisher_url": publisher_url or f"{BASE_URL}/{publisher.lower()}",
                "url": model_url,
                "description": desc,
                "badges": badges,
                "tags": tags,
                "updated_str": updated_date_str,
                "pub_datetime": pub_datetime,
                "stats": stats,
                "image": img_url
            })
        except Exception as e:
            logger.warning(f"Error parsing card {i}: {e}")

    return models


def generate_item_html(model: Dict[str, Any]) -> str:
    """Generate beautiful, modern HTML formatted content for RSS item."""
    name = model.get("name", "Unknown Model")
    publisher = model.get("publisher", "NVIDIA")
    url = model.get("url", MODELS_URL)
    desc = model.get("description", "No description available.")
    badges = model.get("badges", [])
    tags = model.get("tags", [])
    updated_str = model.get("updated_str", "")
    stats = model.get("stats", [])

    # Badges HTML
    badges_html = ""
    for badge in badges:
        bg_color = "#76b900" if "downloadable" in badge.lower() else "#7c3aed"
        badges_html += (
            f'<span style="display:inline-block;background-color:{bg_color};color:#ffffff;'
            f'font-size:11px;font-weight:600;padding:3px 8px;border-radius:12px;margin-right:6px;'
            f'text-transform:uppercase;letter-spacing:0.5px;">{badge}</span>'
        )

    # Publisher pill color
    pub_color = PUBLISHER_COLORS.get(publisher, "#334155")
    pub_badge_html = (
        f'<span style="display:inline-block;font-size:12px;font-weight:700;color:{pub_color};'
        f'background:#f8fafc;padding:3px 8px;border-radius:4px;border:1px solid #e2e8f0;'
        f'text-transform:uppercase;letter-spacing:0.5px;">'
        f'{publisher}'
        f'</span>'
    )

    # Tags HTML
    tags_html = ""
    for tag in tags:
        tags_html += (
            f'<span style="display:inline-block;background-color:#f1f5f9;color:#334155;'
            f'font-size:12px;padding:3px 10px;border-radius:6px;margin:3px 4px 3px 0;'
            f'border:1px solid #e2e8f0;">#{tag}</span>'
        )

    # Stats HTML
    stats_html = ""
    if stats:
        stats_text = " &bull; ".join(stats)
        stats_html = f'<div style="color:#64748b;font-size:12px;margin-top:8px;">📊 {stats_text}</div>'

    # Updated Date HTML
    date_html = ""
    if updated_str:
        date_html = f'<div style="color:#64748b;font-size:12px;margin-top:4px;">🕒 Last updated: <strong>{updated_str}</strong></div>'

    html = f"""
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;max-width:680px;border:1px solid #e2e8f0;border-radius:12px;padding:20px;background:#ffffff;box-shadow:0 1px 3px rgba(0,0,0,0.05);margin-bottom:16px;">
  <!-- Header -->
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;flex-wrap:wrap;gap:8px;">
    <div>
      {pub_badge_html}
    </div>
    <div>
      {badges_html}
    </div>
  </div>

  <!-- Title -->
  <h2 style="margin:0 0 10px 0;font-size:20px;font-weight:700;line-height:1.3;">
    <a href="{url}" target="_blank" rel="noopener noreferrer" style="color:#0f172a;text-decoration:none;">
      {name}
    </a>
  </h2>

  <!-- Description -->
  <p style="margin:0 0 16px 0;color:#334155;font-size:14px;line-height:1.6;">
    {desc}
  </p>

  <!-- Tags Container -->
  {f'<div style="margin-bottom:16px;">{tags_html}</div>' if tags_html else ''}

  <!-- Metadata -->
  <div style="border-top:1px solid #f1f5f9;padding-top:12px;margin-top:12px;">
    {date_html}
    {stats_html}
  </div>

  <!-- CTA Button -->
  <div style="margin-top:16px;">
    <a href="{url}" target="_blank" rel="noopener noreferrer" style="display:inline-block;background-color:#76b900;color:#ffffff;font-size:13px;font-weight:600;padding:8px 16px;border-radius:6px;text-decoration:none;">
      View Model Card on NVIDIA Build &rarr;
    </a>
  </div>
</div>
""".strip()
    return html


def build_feeds(models: List[Dict[str, Any]], output_dir: str = "dist") -> None:
    """Generate rss.xml, atom.xml, and static index.html in output_dir."""
    os.makedirs(output_dir, exist_ok=True)
    
    fg = FeedGenerator()
    fg.id(MODELS_URL)
    fg.title("NVIDIA NIM & AI Foundation Models")
    fg.author({'name': 'NVIDIA Build', 'email': 'support@build.nvidia.com'})
    fg.link(href=MODELS_URL, rel='alternate')
    fg.link(href=f"{BASE_URL}/rss.xml", rel='self')
    fg.subtitle("Latest AI foundation models, NVIDIA NIM microservices, and preview endpoints from build.nvidia.com")
    fg.description("Latest AI foundation models, NVIDIA NIM microservices, and preview endpoints from build.nvidia.com")
    fg.language("en")
    fg.logo("https://www.nvidia.com/favicon.ico")
    fg.icon("https://www.nvidia.com/favicon.ico")
    
    now_utc = datetime.now(timezone.utc)
    fg.lastBuildDate(now_utc)
    fg.updated(now_utc)

    # Sort models by pub_datetime descending (newest first)
    sorted_models = sorted(models, key=lambda m: m.get("pub_datetime") or now_utc, reverse=True)

    for m in sorted_models:
        # Using order='append' so that the first (newest) item remains at the top of the feed
        fe = fg.add_entry(order='append')
        item_id = m.get("url") or f"urn:nvidia:model:{m.get('name')}"
        fe.id(item_id)
        
        publisher = m.get("publisher", "NVIDIA")
        name = m.get("name", "Unknown Model")
        fe.title(f"[{publisher}] {name}")
        
        fe.link(href=m.get("url", MODELS_URL))
        fe.author({'name': publisher, 'uri': m.get("publisher_url", MODELS_URL)})
        
        item_date = m.get("pub_datetime") or now_utc
        fe.pubDate(item_date)
        fe.updated(item_date)

        # Tags as categories
        for tag in m.get("tags", []):
            fe.category(term=tag)

        # Rich HTML Content
        content_html = generate_item_html(m)
        fe.description(m.get("description") or f"Model card for {name} by {publisher}")
        fe.content(content_html, type='CDATA')

    # Save RSS 2.0
    rss_path = os.path.join(output_dir, "rss.xml")
    fg.rss_file(rss_path, pretty=True)
    logger.info(f"Successfully generated RSS feed: {rss_path} ({os.path.getsize(rss_path)} bytes)")

    # Save Atom 1.0
    atom_path = os.path.join(output_dir, "atom.xml")
    fg.atom_file(atom_path, pretty=True)
    logger.info(f"Successfully generated Atom feed: {atom_path} ({os.path.getsize(atom_path)} bytes)")

    # Generate an elegant index.html landing page for GitHub Pages
    generate_landing_page(sorted_models, output_dir)


def generate_landing_page(models: List[Dict[str, Any]], output_dir: str) -> None:
    """Generate a high quality index.html preview page for GitHub Pages hosting."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    models_cards_html = ""
    for m in models:
        models_cards_html += generate_item_html(m)

    index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NVIDIA Models RSS Feed</title>
  <meta name="description" content="Automated RSS and Atom feed generator for NVIDIA AI Foundation Models and NIMs.">
  <link rel="alternate" type="application/rss+xml" title="NVIDIA Models RSS Feed" href="rss.xml">
  <link rel="alternate" type="application/atom+xml" title="NVIDIA Models Atom Feed" href="atom.xml">
  <style>
    :root {{
      --primary: #76b900;
      --primary-hover: #68a500;
      --bg: #0b0f19;
      --card-bg: #131b2e;
      --border: #232f48;
      --text: #f1f5f9;
      --text-muted: #94a3b8;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 40px 20px;
    }}
    .container {{
      max-width: 800px;
      margin: 0 auto;
    }}
    header {{
      text-align: center;
      margin-bottom: 40px;
    }}
    h1 {{
      font-size: 2.2rem;
      font-weight: 800;
      color: #ffffff;
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
    }}
    .badge-nvidia {{
      background: var(--primary);
      color: #000000;
      font-size: 0.8rem;
      font-weight: 700;
      padding: 4px 10px;
      border-radius: 9999px;
      text-transform: uppercase;
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
    .btn-rss {{
      background: #f97316;
      color: #ffffff;
    }}
    .btn-rss:hover {{ background: #ea580c; transform: translateY(-1px); }}
    .btn-atom {{
      background: #3b82f6;
      color: #ffffff;
    }}
    .btn-atom:hover {{ background: #2563eb; transform: translateY(-1px); }}
    .btn-gh {{
      background: #334155;
      color: #ffffff;
    }}
    .btn-gh:hover {{ background: #475569; transform: translateY(-1px); }}
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
    }}
    .models-list {{
      display: flex;
      flex-direction: column;
      gap: 16px;
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
      <h1>NVIDIA Models RSS <span class="badge-nvidia">Live Feed</span></h1>
      <p class="subtitle">Real-time RSS & Atom feed tracking newly released AI models and NIM microservices from build.nvidia.com.</p>
      <div class="feed-buttons">
        <a href="rss.xml" class="btn btn-rss">📡 Subscribe RSS 2.0</a>
        <a href="atom.xml" class="btn btn-atom">⚛️ Subscribe Atom 1.0</a>
        <a href="https://build.nvidia.com/models" target="_blank" rel="noopener noreferrer" class="btn btn-gh">🌐 Official Portal</a>
      </div>
    </header>

    <div class="meta-bar">
      <span>📦 Total Models Indexed: <strong>{len(models)}</strong></span>
      <span>🕒 Last Updated: <strong>{now_str}</strong></span>
    </div>

    <div class="models-list">
      <h2 style="font-size:1.3rem;margin-bottom:8px;color:#cbd5e1;">Latest Model Cards Preview</h2>
      {models_cards_html}
    </div>

    <footer>
      <p>Generated by NVIDIA Models RSS Workflow &bull; Data sourced directly from NVIDIA Build</p>
    </footer>
  </div>
</body>
</html>
"""
    index_path = os.path.join(output_dir, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)
    logger.info(f"Successfully generated landing page: {index_path}")


def main():
    """Main execution entry point."""
    try:
        html = fetch_page_content()
        
        # 1. Try Next.js __NEXT_DATA__
        models = parse_next_data(html)
        
        # 2. Try RSC stream if not found
        if not models:
            models = parse_rsc_stream(html)
            
        # 3. Fallback to DOM card parsing
        if not models:
            models = parse_dom_cards(html)

        if not models:
            logger.error("Failed to extract any models from page!")
            sys.exit(1)

        logger.info(f"Successfully extracted {len(models)} models. Generating feeds...")
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")
        build_feeds(models, output_dir=output_dir)
        logger.info("Feed generation completed successfully.")

    except Exception as e:
        logger.exception(f"Fatal error during RSS generation: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
