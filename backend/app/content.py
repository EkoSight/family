"""Content assistant: suggest social/post topics from an uploaded photo.

If a vision-capable model is configured (LLM_PROVIDER=gemini or claude) the image
is actually analysed and topics are generated from what's in the picture. With
no vision model it falls back to a transparent heuristic that blends Ekosight's
work areas with the currently-trending agriculture topics — clearly flagged so
the CEO knows the difference.
"""
from __future__ import annotations

import base64

from . import config, insights

_VISION_PROMPT = (
    "You are the content strategist for Ekosight, an agri-tech company working "
    "on soil health, Soil Doctor clinics, IoT sensors and precision agriculture "
    "for Indian farmers. Look at this photo. In 1 short sentence describe what "
    "is in it, then propose 5 specific, post-worthy content topics grounded in "
    "what you see, each with a one-line angle. Return concise plain text: first "
    "a line 'SCENE: ...' then 5 lines each 'TOPIC: <title> — <angle>'."
)


def suggest_from_photo(image_bytes: bytes, mime: str) -> dict:
    provider = config.LLM_PROVIDER
    if provider == "claude" and config.ANTHROPIC_API_KEY:
        try:
            return _claude_vision(image_bytes, mime)
        except Exception:
            pass
    elif provider == "gemini" and config.GEMINI_API_KEY:
        try:
            return _gemini_vision(image_bytes, mime)
        except Exception:
            pass
    return _heuristic()


def _parse_text(text: str) -> dict:
    scene, topics = "", []
    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("SCENE:"):
            scene = line.split(":", 1)[1].strip()
        elif line.upper().startswith("TOPIC:"):
            body = line.split(":", 1)[1].strip()
            if "—" in body:
                title, angle = body.split("—", 1)
            elif "-" in body:
                title, angle = body.split("-", 1)
            else:
                title, angle = body, ""
            topics.append({"title": title.strip(), "angle": angle.strip()})
    return {"scene": scene, "suggestions": topics}


def _claude_vision(image_bytes: bytes, mime: str) -> dict:
    import anthropic  # type: ignore

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    b64 = base64.standard_b64encode(image_bytes).decode()
    resp = client.messages.create(
        model="claude-sonnet-5", max_tokens=700,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64",
             "media_type": mime, "data": b64}},
            {"type": "text", "text": _VISION_PROMPT},
        ]}],
    )
    parsed = _parse_text(resp.content[0].text)
    parsed["analyzed_by"] = "claude vision"
    return parsed


def _gemini_vision(image_bytes: bytes, mime: str) -> dict:
    import google.generativeai as genai  # type: ignore

    genai.configure(api_key=config.GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")
    resp = model.generate_content(
        [{"mime_type": mime, "data": image_bytes}, _VISION_PROMPT])
    parsed = _parse_text(resp.text)
    parsed["analyzed_by"] = "gemini vision"
    return parsed


def _heuristic() -> dict:
    """No vision model: suggest topics from trending agriculture themes +
    Ekosight framing. Honest about not having looked at the image."""
    t = insights.topics()["topics"][:5]
    suggestions = [{
        "title": x["topic"],
        "angle": x["suggested_angle"],
    } for x in t]
    if not suggestions:
        suggestions = [
            {"title": "A day at a Soil Doctor clinic",
             "angle": "Show the process from sample to recommendation."},
            {"title": "What your soil is telling you",
             "angle": "Turn one soil parameter into a simple farmer tip."},
        ]
    return {
        "scene": "",
        "analyzed_by": "heuristic (no vision model configured)",
        "note": "Set LLM_PROVIDER=gemini (or claude) with an API key to get "
                "topics based on the actual contents of your photo.",
        "suggestions": suggestions,
    }
