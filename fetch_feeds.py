#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multi-source AI model RSS generator.

Runs every scraper registered in ``sources.SOURCES``, merges the results into a
single RSS 2.0 feed (``dist/rss.xml``) and a preview page (``dist/index.html``).
Each entry title is prefixed with the source it came from: ``【源】真实标题``.
"""

import logging
import os
import sys
import xml.sax.saxutils as saxutils
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Dict, List

from sources import SOURCES, SeenStore
from sources.base import Item

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("models_rss")

FEED_TITLE = "AI Models RSS (Multi-Source)"
FEED_DESCRIPTION = (
    "Aggregated model catalog feed built from NVIDIA Build and AMD Radeon TokenFactory."
)
FEED_HOME_URL = "https://build.nvidia.com/models"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")


def collect_items(seen: SeenStore) -> List[Item]:
    """Run every source and merge the results, keeping the newest duplicate."""
    merged: "OrderedDict[str, Item]" = OrderedDict()
    for source_cls in SOURCES:
        name = source_cls.__name__
        try:
            source = source_cls(seen)
            items = source.fetch()
        except Exception as e:
            logger.exception(f"Source {name} failed: {e}")
            continue
        logger.info(f"Source {name} produced {len(items)} items")
        for item in items:
            existing = merged.get(item.guid)
            if existing is None or item.pub_datetime > existing.pub_datetime:
                merged[item.guid] = item
    return list(merged.values())


def rfc822(dt: datetime) -> str:
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")


def build_rss(items: List[Item], output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    now_rfc = rfc822(datetime.now(timezone.utc))

    sorted_items = sorted(items, key=lambda i: i.pub_datetime, reverse=True)

    items_xml = ""
    for it in sorted_items:
        title = f"【{it.source_label}】{it.title}"
        categories_xml = "".join(
            f"    <category>{saxutils.escape(c)}</category>\n" for c in it.categories
        )
        items_xml += f"""  <item>
    <title>{saxutils.escape(title)}</title>
    <link>{saxutils.escape(it.link)}</link>
    <guid isPermaLink="false">{saxutils.escape(it.guid)}</guid>
    <pubDate>{rfc822(it.pub_datetime)}</pubDate>
    <source url="{saxutils.escape(it.link)}">{saxutils.escape(it.source_label)}</source>
    <description>{saxutils.escape(it.summary)}</description>
{categories_xml}  </item>
"""

    rss_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{saxutils.escape(FEED_TITLE)}</title>
    <link>{FEED_HOME_URL}</link>
    <description>{saxutils.escape(FEED_DESCRIPTION)}</description>
    <language>en</language>
    <lastBuildDate>{now_rfc}</lastBuildDate>
{items_xml}  </channel>
</rss>
"""
    path = os.path.join(output_dir, "rss.xml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(rss_xml)
    logger.info(f"Wrote {path} ({os.path.getsize(path)} bytes, {len(sorted_items)} items)")
    return path


def build_landing_page(items: List[Item], output_dir: str) -> str:
    grouped: Dict[str, List[Item]] = {}
    for it in sorted(items, key=lambda i: i.pub_datetime, reverse=True):
        grouped.setdefault(it.source_label, []).append(it)

    sections = ""
    for label, group in grouped.items():
        cards = "".join(
            f'      <article class="card">\n'
            f'        <div class="card-src">{saxutils.escape(label)}</div>\n'
            f'        <h3>{saxutils.escape(it.title)}</h3>\n'
            f'        <div class="card-body">{it.html}</div>\n'
            f'        <div class="card-date">{rfc822(it.pub_datetime)}</div>\n'
            f"      </article>\n"
            for it in group
        )
        sections += (
            f'    <section>\n'
            f'      <h2>【{saxutils.escape(label)}】 · {len(group)} models</h2>\n'
            f'      <div class="cards">{cards}</div>\n'
            f"    </section>\n"
        )

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{saxutils.escape(FEED_TITLE)}</title>
  <link rel="alternate" type="application/rss+xml" title="{saxutils.escape(FEED_TITLE)}" href="rss.xml">
  <style>
    :root {{ --bg:#0b0f19; --card:#131b2e; --border:#232f48; --text:#f1f5f9; --muted:#94a3b8; }}
    * {{ box-sizing:border-box; margin:0; padding:0; }}
    body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
           background:var(--bg); color:var(--text); line-height:1.55; padding:40px 20px; }}
    .container {{ max-width:900px; margin:0 auto; }}
    header {{ text-align:center; margin-bottom:32px; }}
    h1 {{ font-size:2rem; margin-bottom:10px; }}
    p.sub {{ color:var(--muted); margin-bottom:20px; }}
    .btn {{ display:inline-block; background:#f97316; color:#fff; padding:10px 20px;
            border-radius:8px; font-weight:600; text-decoration:none; }}
    .meta {{ display:flex; justify-content:space-between; padding:12px 18px; background:var(--card);
             border:1px solid var(--border); border-radius:8px; color:var(--muted);
             font-size:.85rem; margin-bottom:28px; }}
    section {{ margin-bottom:34px; }}
    section h2 {{ font-size:1.2rem; color:#cbd5e1; margin-bottom:14px; }}
    .cards {{ display:flex; flex-direction:column; gap:14px; }}
    .card {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:16px 18px; }}
    .card-src {{ font-size:.75rem; font-weight:800; letter-spacing:.05em; color:#76b900; text-transform:uppercase; }}
    .card h3 {{ font-size:1.05rem; margin:6px 0 10px; }}
    .card-body {{ font-size:.9rem; color:#e2e8f0; }}
    .card-date {{ margin-top:10px; font-size:.78rem; color:var(--muted); }}
    footer {{ text-align:center; margin-top:40px; padding-top:20px; border-top:1px solid var(--border);
              color:var(--muted); font-size:.85rem; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>{saxutils.escape(FEED_TITLE)}</h1>
      <p class="sub">{saxutils.escape(FEED_DESCRIPTION)}</p>
      <a class="btn" href="rss.xml">Subscribe RSS 2.0</a>
    </header>
    <div class="meta">
      <span>Total entries: <strong>{len(items)}</strong></span>
      <span>Last updated: <strong>{now_str}</strong></span>
    </div>
{sections}
    <footer>Generated by the multi-source models RSS workflow.</footer>
  </div>
</body>
</html>
"""
    path = os.path.join(output_dir, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"Wrote {path}")
    return path


def main() -> None:
    seen = SeenStore()
    try:
        items = collect_items(seen)
    finally:
        seen.save()

    if not items:
        logger.error("No items collected from any source.")
        sys.exit(1)

    build_rss(items, OUTPUT_DIR)
    build_landing_page(items, OUTPUT_DIR)
    logger.info("Done.")


if __name__ == "__main__":
    main()
