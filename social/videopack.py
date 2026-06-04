"""
videopack.py — weekly opportunity report + full long-form "Video Pack".

This is the YouTube counterpart to the short-form `calendar.py`. It powers the
weekly GitHub Action: every Monday it (1) scans the niche and writes a ranked
"opportunity report" of 10 candidate story topics, and (2) generates a complete,
production-ready Video Pack (title options, full narration script, SEO upload
pack, thumbnail concepts and promotion ideas) for the strongest topic.

Everything runs on the standard library. With OPENAI_API_KEY set, the topic
ideas and the narration are written by the LLM; otherwise a deterministic,
brand-aware scaffold is produced so the report and pack are always generated.
"""
from __future__ import annotations

import json
import os
import random
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import List, Optional, Tuple

from .brand import Brand, get_brand
from .calendar import propose_topics
from .engine import generate, write_kit
from .providers import LLMProvider, auto_llm


# --------------------------------------------------------------------------- #
# Opportunity report
# --------------------------------------------------------------------------- #

@dataclass
class Opportunity:
    rank: int
    topic: str
    category: str
    audience_emotion: str
    competition: str
    retention_angle: str


# Keyword -> (category label, audience emotion). Checked in order, so the more
# specific/contextual categories (workplace, family) come before romantic ones.
_CATEGORY_RULES: List[Tuple[Tuple[str, ...], str, str]] = [
    (("boss", "coworker", "manager", "work", "company", "business", "promotion",
      "employee", "office", "colleague"),
     "workplace betrayal", "righteous, earned payback"),
    (("sister", "brother", "sibling", "inheritance", "will", "mother", "father",
      "parent", "family", "stepparent", "in-law", "wedding"),
     "family / inheritance betrayal", "injustice then catharsis"),
    (("cheat", "affair", "fiance", "husband", "wife", "spouse", "partner", "ex"),
     "cheating / affairs", "betrayal then vindication"),
    (("karma", "scam", "scammer", "landlord", "neighbor"),
     "karma / quiet justice", "tension then satisfying justice"),
]


def _classify(topic: str) -> Tuple[str, str]:
    low = topic.lower()
    for keywords, category, emotion in _CATEGORY_RULES:
        if any(k in low for k in keywords):
            return category, emotion
    return "quiet / delayed revenge", "slow-burn tension then relief"


def _story_topics_offline(brand: Brand, count: int) -> List[str]:
    """Story-aware offline topic pool: use the niche's story premises verbatim
    (themes + seeds) rather than the short-form 'angle x theme' combiner.

    The pool is SHUFFLED per run so repeated weekly runs surface a different
    ranked set (and therefore a different #1 pick) — this is what stops the
    system from producing the same video over and over."""
    pool: List[str] = []
    seen = set()
    for t in (brand.themes or []) + (brand.topic_seeds or []):
        k = t.lower().strip()
        if k and k not in seen:
            seen.add(k)
            pool.append(t)
    if not pool:
        return []
    random.shuffle(pool)
    return pool[:min(count, len(pool))]


def _propose_topics_for_pack(brand: Brand, count: int,
                             llm: Optional[LLMProvider]) -> Tuple[List[str], str]:
    """LLM-proposed topics when available; otherwise story-aware premises for
    story brands, falling back to the short-form combiner for tip brands."""
    llm = llm or auto_llm()
    try:
        proposed = llm.propose_topics(brand.display_name, brand.voice,
                                      brand.content_pillars or [], count)
    except Exception:
        proposed = None
    if proposed:
        return proposed[:count], f"llm:{getattr(llm, 'name', 'unknown')}"
    if brand.niche_kind == "story":
        topics = _story_topics_offline(brand, count)
        if topics:
            return topics, "framework:offline"
    pairs, source = propose_topics(brand, count, llm=llm)  # tip-brand fallback
    return [t for t, _ in pairs], source


def build_opportunities(brand_key: str, count: int = 10,
                        llm: Optional[LLMProvider] = None) -> Tuple[List[Opportunity], str]:
    brand = get_brand(brand_key)
    topics, source = _propose_topics_for_pack(brand, count, llm=llm)
    comp_cycle = ["low", "low-medium", "medium"]
    angles = [
        "Open on the moment of discovery, then rewind; hold the payoff for the final third.",
        "Start calm and ordinary so the betrayal lands harder; escalate every 60-90 seconds.",
        "Tease the ending in the first 10 seconds, then earn it across the story.",
        "Lean into the quiet, methodical plan; let the audience feel the patience pay off.",
    ]
    out: List[Opportunity] = []
    for i, topic in enumerate(topics[:count]):
        category, emotion = _classify(topic)
        out.append(Opportunity(
            rank=i + 1,
            topic=topic,
            category=category,
            audience_emotion=emotion,
            competition=comp_cycle[i % len(comp_cycle)],
            retention_angle=angles[i % len(angles)],
        ))
    return out, source


def write_opportunities(brand_key: str, count: int = 10, out_root: str = "weekly_out",
                        llm: Optional[LLMProvider] = None) -> str:
    """Write opportunities.md + opportunities.json into out_root. Returns out_root."""
    brand = get_brand(brand_key)
    opps, source = build_opportunities(brand_key, count, llm=llm)
    os.makedirs(out_root, exist_ok=True)

    md = [
        f"# {brand.display_name} — weekly opportunity report",
        "",
        f"*Generated:* {datetime.utcnow().isoformat(timespec='seconds')}Z  ·  "
        f"*Topic source:* {source}",
        "",
        "Pick one topic below and run the Video Pack on it "
        "(`python -m social.cli \"<topic>\" --brand "
        f"{brand.key}`).",
        "",
        "| # | Topic | Category | Audience emotion | Competition |",
        "|---|-------|----------|------------------|-------------|",
    ]
    for o in opps:
        md.append(f"| {o.rank} | {o.topic} | {o.category} | {o.audience_emotion} "
                  f"| {o.competition} |")
    md += ["", "## Retention angles (top 3)", ""]
    for o in opps[:3]:
        md += [f"### {o.rank}. {o.topic}",
               f"- **Why now / angle:** {o.retention_angle}",
               f"- **Emotion to land:** {o.audience_emotion}",
               f"- **Category:** {o.category}", ""]
    _write(out_root, "opportunities.md", "\n".join(md) + "\n")

    payload = {
        "brand": brand.key,
        "brand_name": brand.display_name,
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "topic_source": source,
        "opportunities": [asdict(o) for o in opps],
    }
    _write(out_root, "opportunities.json", json.dumps(payload, indent=2, ensure_ascii=False))
    return out_root


# --------------------------------------------------------------------------- #
# Weekly run: report + full pack for the top topic
# --------------------------------------------------------------------------- #

def write_weekly(brand_key: str, out_root: str = "weekly_out",
                 seconds: int = 0, llm: Optional[LLMProvider] = None,
                 voiceover: bool = False, render: bool = False,
                 burn_captions: bool = True, make_thumbnail: bool = True) -> str:
    """Produce the full weekly bundle:

        weekly_out/
          opportunities.md / .json     ranked 10-topic scan
          video-pack/<...>/             complete Video Pack for the #1 topic
            audio/                      narration MP3s (if voiceover/render and a
                                        TTS engine are available)
            video.mp4                   self-contained upload-ready video with
                                        captions baked in (if render=True + ffmpeg)
            thumbnail.jpg               matching 1280x720 thumbnail (if render=True)
          INDEX.md                      what's inside + next steps
    """
    os.makedirs(out_root, exist_ok=True)
    opps, source = build_opportunities(brand_key, 10, llm=llm)
    write_opportunities(brand_key, 10, out_root=out_root, llm=llm)

    top = opps[0].topic if opps else get_brand(brand_key).topic_seeds[0]
    kit = generate(top, brand_key=brand_key, seconds=seconds, fmt="long", llm=llm)
    pack_root = os.path.join(out_root, "video-pack")
    os.makedirs(pack_root, exist_ok=True)
    pack_folder = write_kit(kit, out_root=pack_root)

    voiceover_line = ("3. Record/generate the voiceover (`voiceover.txt`), assemble visuals "
                      "(`shotlist.md`), then upload using `seo.md`.")

    if render:
        # Rendering assembles the MP4 (captions baked in) + thumbnail and
        # produces the voiceover internally.
        from .render_long import render_long_video
        res = render_long_video(kit, os.path.join(pack_folder, "video.mp4"),
                                folder=pack_folder, burn_captions=burn_captions,
                                make_thumbnail=make_thumbnail)
        if res.ok:
            voiceover_line = ("3. **Everything is rendered:** `video-pack/.../video.mp4` "
                              "(captions baked in) and `thumbnail.jpg`. Give it a "
                              "lookover, then upload with the title/description in `seo.md`.")
        else:
            voiceover_line += (f"\n   _(Auto-render skipped: {res.message.splitlines()[0]})_")
    elif voiceover:
        from .narration import synthesize_narration
        res = synthesize_narration(kit, pack_folder)
        if res.ok:
            voiceover_line = ("3. Voiceover audio is in `video-pack/.../audio/` "
                              "(`narration.mp3` + per-beat clips). Assemble visuals "
                              "(`shotlist.md`) over it, then upload using `seo.md`.")
        else:
            voiceover_line += (f"\n   _(Auto-voiceover skipped: {res.message})_")

    index = [
        f"# Weekly content bundle — {kit.brand_name}",
        "",
        f"*Generated:* {datetime.utcnow().isoformat(timespec='seconds')}Z  ·  "
        f"*Script by:* {kit.generator}",
        "",
        "## This week's pick",
        f"**{kit.youtube.get('best_title', kit.title)}**  \n"
        f"_Topic: {top}_",
        "",
        "## What's inside",
        "- `opportunities.md` — 10 ranked topic ideas for the week.",
        f"- `video-pack/` — a complete Video Pack for the #1 topic "
        f"(open `VIDEO_PACK.md` inside).",
        "",
        "## Next steps",
        "1. Skim `opportunities.md`; swap the pick if another topic fits better.",
        "2. Open `video-pack/.../VIDEO_PACK.md` — review the script, SEO and thumbnails.",
        voiceover_line,
    ]
    _write(out_root, "INDEX.md", "\n".join(index) + "\n")
    return out_root


def _write(folder: str, name: str, content: str) -> None:
    with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
        fh.write(content)
