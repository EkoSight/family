"""Insights: agriculture news + content-topic suggestions.

Pulls agriculture / agritech news relevant to Ekosight's work (soil health,
Soil Doctor clinics, IoT sensors, precision agriculture), scores each item by
how close it is to what we do, and surfaces prioritised *topics* the CEO can
turn into content.

Network access is best-effort: live RSS when the host can reach the internet
(e.g. on Cloud Run), with a curated offline fallback so the feature always
renders. Results are cached in-process for a short TTL.
"""
from __future__ import annotations

import concurrent.futures
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape

# --- what "relevant to us" means (keyword -> weight) -----------------------
WORK_KEYWORDS = {
    "soil health": 5, "soil testing": 5, "soil": 4, "nutrient": 4,
    "microbe": 3, "microbial": 3, "fertiliser": 3, "fertilizer": 3,
    "iot": 5, "sensor": 4, "precision agriculture": 5, "precision farming": 5,
    "agritech": 5, "agri-tech": 5, "agri tech": 5, "digital agriculture": 4,
    "drone": 3, "satellite": 3, "remote sensing": 3, "ai": 2,
    "farmer": 2, "fpo": 3, "crop": 2, "yield": 2, "harvest": 1,
    "sustainable": 3, "regenerative": 4, "carbon farming": 4, "carbon": 2,
    "climate": 2, "startup": 2, "funding": 2, "gem": 3, "pm-kisan": 3,
    "subsidy": 2, "scheme": 2, "millet": 2, "organic": 2,
}

# Keyless Google News RSS queries (reliable, includes source + date).
_FEEDS = [
    ("India · Agriculture", "IN",
     "https://news.google.com/rss/search?q=agriculture+india+when:10d&hl=en-IN&gl=IN&ceid=IN:en"),
    ("India · Agritech", "IN",
     "https://news.google.com/rss/search?q=agritech+OR+%22agri-tech%22+india+when:14d&hl=en-IN&gl=IN&ceid=IN:en"),
    ("India · Soil health", "IN",
     "https://news.google.com/rss/search?q=%22soil+health%22+OR+%22soil+testing%22+india+when:21d&hl=en-IN&gl=IN&ceid=IN:en"),
    ("Global · Precision agriculture / IoT", "Global",
     "https://news.google.com/rss/search?q=%22precision+agriculture%22+OR+%22agriculture+IoT%22+when:14d&hl=en-US&gl=US&ceid=US:en"),
    ("Global · Agritech", "Global",
     "https://news.google.com/rss/search?q=agritech+farming+technology+when:10d&hl=en-US&gl=US&ceid=US:en"),
]

_CACHE: dict = {"ts": 0, "items": None}
_TTL = 1800  # 30 minutes


def _fetch_one(feed) -> list[dict]:
    label, region, url = feed
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=8).read()
    root = ET.fromstring(raw)
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        # Google News RSS puts the outlet in <source> or after " - " in title.
        src = item.findtext("source") or ""
        if not src and " - " in title:
            src = title.rsplit(" - ", 1)[-1]
        clean = unescape(re.sub(r"\s+-\s+[^-]+$", "", title)) if src else unescape(title)
        if title and link:
            out.append({"title": clean, "url": link, "source": src.strip(),
                        "published": pub, "feed": label, "region": region})
    return out[:15]


def _score(title: str) -> tuple[int, list[str]]:
    low = title.lower()
    score, matched = 0, []
    for kw, w in WORK_KEYWORDS.items():
        if kw in low:
            score += w
            matched.append(kw)
    return score, matched


def fetch_news(force: bool = False) -> list[dict]:
    now = time.time()
    if not force and _CACHE["items"] is not None and now - _CACHE["ts"] < _TTL:
        return _CACHE["items"]

    items: list[dict] = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            futures = [ex.submit(_fetch_one, f) for f in _FEEDS]
            for fut in concurrent.futures.as_completed(futures, timeout=12):
                try:
                    items.extend(fut.result())
                except Exception:
                    continue
    except Exception:
        items = []

    # dedupe by title, score, sort
    seen, deduped = set(), []
    for it in items:
        key = it["title"].lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        s, matched = _score(it["title"])
        it["relevance"] = s
        it["matched"] = matched
        deduped.append(it)
    deduped.sort(key=lambda x: x["relevance"], reverse=True)

    result = {"online": bool(deduped), "items": deduped[:40]}
    if not deduped:
        result = {"online": False, "items": _FALLBACK_NEWS}
    _CACHE.update(ts=now, items=result)
    return result


# --- prioritised topic suggestions -----------------------------------------
_TOPIC_THEMES = [
    ("Soil health & testing", ["soil health", "soil testing", "soil", "nutrient", "microbe"],
     "Show a real before/after from a Soil Doctor clinic and explain what a soil test actually reveals."),
    ("IoT & precision agriculture", ["iot", "sensor", "precision agriculture", "precision farming", "drone", "satellite"],
     "Explain, in plain language, how affordable sensors help a small farmer decide when to irrigate or fertilise."),
    ("Agritech & innovation", ["agritech", "agri-tech", "agri tech", "digital agriculture", "startup", "ai"],
     "Position Ekosight in the India agritech story — what problem we solve that generic apps do not."),
    ("Sustainability & regenerative farming", ["sustainable", "regenerative", "carbon farming", "carbon", "organic", "climate"],
     "Tie a trending climate/soil-carbon headline to what farmers can do this season."),
    ("Policy, schemes & FPOs", ["gem", "pm-kisan", "subsidy", "scheme", "fpo", "millet"],
     "Break down a new scheme/policy and how an FPO or clinic partner can benefit."),
]


def topics() -> list[dict]:
    news = fetch_news()
    items = news["items"]
    out = []
    for name, kws, angle in _TOPIC_THEMES:
        related = [it for it in items
                   if any(k in it["title"].lower() for k in kws)]
        weight = sum(it.get("relevance", 1) for it in related) or 0
        out.append({
            "topic": name,
            "priority_score": weight + len(related),
            "story_count": len(related),
            "suggested_angle": angle,
            "headlines": [{"title": it["title"], "url": it["url"],
                           "source": it.get("source", ""), "region": it.get("region", "")}
                          for it in related[:4]],
        })
    out.sort(key=lambda x: x["priority_score"], reverse=True)
    return {"online": news["online"], "topics": out}


# --- offline fallback so the UI always has content -------------------------
_FALLBACK_NEWS = [
    {"title": "Soil health cards and low-cost soil testing gain ground with Indian farmers",
     "url": "#", "source": "Sample", "region": "IN", "feed": "India · Soil health",
     "relevance": 13, "matched": ["soil health", "soil testing", "farmer"], "published": ""},
    {"title": "IoT sensors and precision agriculture cut input costs for smallholders",
     "url": "#", "source": "Sample", "region": "Global", "feed": "Global · IoT",
     "relevance": 14, "matched": ["iot", "sensor", "precision agriculture"], "published": ""},
    {"title": "Indian agritech startups raise fresh funding to digitise the farm",
     "url": "#", "source": "Sample", "region": "IN", "feed": "India · Agritech",
     "relevance": 9, "matched": ["agritech", "startup", "funding"], "published": ""},
    {"title": "Regenerative and carbon farming move from pilot to policy",
     "url": "#", "source": "Sample", "region": "Global", "feed": "Global · Agritech",
     "relevance": 10, "matched": ["regenerative", "carbon farming"], "published": ""},
    {"title": "New government scheme expands support for FPOs and millet growers",
     "url": "#", "source": "Sample", "region": "IN", "feed": "India · Agriculture",
     "relevance": 8, "matched": ["scheme", "fpo", "millet"], "published": ""},
]
