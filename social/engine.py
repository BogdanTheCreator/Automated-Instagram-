"""
engine.py — the core generator.

`generate(topic, brand)` returns a fully-populated `ContentKit`; `write_kit`
serialises it into a folder of ready-to-use files:

    script.md             human-readable script + scene breakdown with timings
    voiceover.txt         clean narration for any TTS engine
    voiceover.ssml        SSML version (pauses + emphasis) for premium TTS
    captions.srt          subtitle file, ready to burn into the video
    post.md               Instagram caption, hook A/B variants, alt-text, CTA
    hashtags.txt          tiered hashtag strategy + a copy-paste recommended set
    shotlist.md           per-scene b-roll / visual direction
    content_package.json  machine-readable everything (for the renderer / automation)
    storyboard.html       self-contained animated 9:16 preview of the Reel

The script writer uses the brand's creative frameworks deterministically when no
LLM is configured, and transparently upgrades to LLM output when a key is set
(see providers.auto_llm).
"""
from __future__ import annotations

import json
import os
import re
import textwrap
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .brand import Brand, get_brand
from .providers import LLMProvider, ScriptBrief, auto_llm, environment_report

# Average faceless-VO narration pace (words/sec). Used to sanity-check timing.
WORDS_PER_SECOND = 2.6


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #

@dataclass
class Scene:
    index: int
    role: str               # hook | context | point | payoff | cta
    on_screen: str          # short overlay text (the big animated caption)
    narration: str          # spoken voiceover line
    broll_query: str        # stock-footage / b-roll search phrase
    start: float = 0.0
    end: float = 0.0

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 2)


@dataclass
class ContentKit:
    topic: str
    brand_key: str
    brand_name: str
    title: str
    hook: str
    hook_variants: List[str]
    cta: str
    scenes: List[Scene]
    srt: str
    caption: str
    alt_text: str
    hashtags: Dict[str, List[str]]
    recommended_hashtags: List[str]
    voiceover_text: str
    voiceover_ssml: str
    thumbnail_text: List[str]
    series_name: str
    best_post_times_utc: List[str]
    total_seconds: float
    generator: str
    created_utc: str
    # --- Long-form / YouTube fields (optional; empty for short-form kits) ----
    format: str = "short"                       # "short" | "long"
    titles: List[str] = field(default_factory=list)
    youtube: Dict[str, object] = field(default_factory=dict)
    thumbnail_concepts: List[str] = field(default_factory=list)
    shorts_ideas: List[str] = field(default_factory=list)
    community_posts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, object]) -> "ContentKit":
        """Rebuild a kit from a content_package.json dict (ignores extra keys)."""
        import dataclasses
        scenes = [
            Scene(
                index=int(s["index"]), role=str(s["role"]),
                on_screen=str(s["on_screen"]), narration=str(s["narration"]),
                broll_query=str(s.get("broll_query", "")),
                start=float(s.get("start", 0.0)), end=float(s.get("end", 0.0)),
            )
            for s in d.get("scenes", [])  # type: ignore[union-attr]
        ]
        names = {f.name for f in dataclasses.fields(cls)}
        kw = {k: v for k, v in d.items() if k in names and k != "scenes"}
        return cls(scenes=scenes, **kw)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _clean_topic(topic: str) -> str:
    t = " ".join(topic.strip().split())
    # Drop a leading imperative so hooks read naturally.
    t = re.sub(r"^(make|create|write|generate|do)\s+(me\s+)?(a|an|the)?\s*", "", t, flags=re.I)
    return t


def _cap_first(text: str) -> str:
    """Capitalise only the first character (leaves the rest of the phrase intact)."""
    text = text.strip()
    return text[:1].upper() + text[1:] if text else text


def _fmt_template(template: str, topic: str) -> str:
    """Format a brand template, supporting {topic} (verbatim) and {Topic}
    (first-letter capitalised, for sentence-initial use). Extra keys are
    harmless for templates that only use {topic}."""
    try:
        return template.format(topic=topic, Topic=_cap_first(topic))
    except (KeyError, IndexError, ValueError):
        return template


def _title_case_topic(topic: str) -> str:
    small = {"a", "an", "the", "and", "or", "for", "of", "to", "in", "on", "with", "that"}
    acronyms = {"ai", "diy", "seo", "faq", "api", "ui", "ux", "id", "url", "vpn",
                "iot", "tv", "pdf", "vo2", "roi", "ceo", "llc"}
    words = topic.split()
    out = []
    for i, w in enumerate(words):
        lw = w.lower()
        if lw in acronyms:
            out.append(w.upper())
        elif lw in small and i != 0:
            out.append(lw)
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out)


def _split_caption_lines(text: str, max_words: int = 6) -> List[str]:
    words = text.split()
    lines, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= max_words:
            lines.append(" ".join(cur))
            cur = []
    if cur:
        lines.append(" ".join(cur))
    return lines or [text]


def _fmt_ts(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    ms = int(round((seconds - int(seconds)) * 1000))
    s = int(seconds) % 60
    m = (int(seconds) // 60) % 60
    h = int(seconds) // 3600
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# --------------------------------------------------------------------------- #
# Script writing (framework-based, LLM-upgradable)
# --------------------------------------------------------------------------- #

def _framework_script(topic: str, brand: Brand, point_count: int) -> Dict[str, object]:
    """Deterministic, brand-aware scaffold used when no LLM is configured."""
    seed = sum(ord(c) for c in topic) or 1
    hook = _fmt_template(brand.hook_templates[seed % len(brand.hook_templates)], topic)
    payoff = brand.payoff_templates[seed % len(brand.payoff_templates)]
    cta = brand.cta_templates[(seed // 3) % len(brand.cta_templates)]

    # Build point scaffolds. These are intentionally structural — the strongest
    # results come from an LLM or your own edits, but the skeleton already has a
    # working hook, value beats, timing and a CTA. The angle templates below
    # rotate so each beat reads distinctly and tells you exactly what to slot in.
    angle_templates = [
        ("The one nobody uses", "Start with the tool/idea most people overlook — name it and the single job it does."),
        ("Where the leverage is", "Show the specific task this removes from your week, with a number."),
        ("The fast win", "Give the quickest result they can copy today in under five minutes."),
        ("The mistake to avoid", "Call out the common error here and the simple fix."),
        ("The compounding move", "Explain how doing this repeatedly stacks into a real advantage."),
        ("Proof it works", "Drop a concrete before/after or a tiny case study."),
    ]
    points: List[Dict[str, str]] = []
    for i in range(point_count):
        lead = brand.point_lead_ins[i % len(brand.point_lead_ins)].format(n=i + 1)
        label, prompt = angle_templates[(seed + i) % len(angle_templates)]
        on_screen = f"{lead} {label}"
        narration = f"{lead} {prompt}"
        points.append({
            "on_screen": on_screen,
            "narration": narration,
            "broll": f"{topic} b-roll",
        })

    return {
        "title": _title_case_topic(topic),
        "hook": hook,
        "points": points,
        "payoff": payoff,
        "cta": cta,
    }


def _normalize_llm(data: Dict[str, object], topic: str, brand: Brand) -> Dict[str, object]:
    points = data.get("points") or []
    norm_points = []
    for i, p in enumerate(points):
        if isinstance(p, dict):
            norm_points.append({
                "on_screen": str(p.get("on_screen") or f"Point {i + 1}"),
                "narration": str(p.get("narration") or ""),
                "broll": str(p.get("broll") or f"{topic} b-roll"),
            })
    return {
        "title": str(data.get("title") or _title_case_topic(topic)),
        "hook": str(data.get("hook") or _fmt_template(brand.hook_templates[0], topic)),
        "points": norm_points or _framework_script(topic, brand, 3)["points"],
        "payoff": str(data.get("payoff") or brand.payoff_templates[0]),
        "cta": str(data.get("cta") or brand.cta_templates[0]),
    }


# --------------------------------------------------------------------------- #
# Long-form story writing (narrated 8-12 min videos, LLM-upgradable)
# --------------------------------------------------------------------------- #

# A believable betrayal/revenge arc. Each beat carries an overlay label, a
# starter narration line (topic-aware, restrained — clearly a draft to edit),
# and a b-roll search phrase. When an LLM key is present the prose is fully
# written instead; offline you still get a complete, well-structured beat sheet.
STORY_ARC = [
    ("setup", "Before it all went wrong",
     "Let me take you back to before any of this happened. Life was ordinary then, "
     "and honestly, I liked it that way. I had no idea what was coming.",
     "quiet everyday life, soft morning light"),
    ("trust", "I trusted them",
     "I trusted them completely. That's the part that still matters, because you "
     "don't get betrayed by strangers. You get betrayed by the people you let all "
     "the way in.",
     "two people laughing, warm candid memories"),
    ("first_crack", "The first small sign",
     "The first sign was small. So small I talked myself out of it. A look that "
     "lasted a second too long, an answer that didn't quite fit. I let it go.",
     "phone face-down on a table, subtle tension"),
    ("suspicion", "It stopped adding up",
     "But small things add up. Soon I was noticing the gaps. The times that didn't "
     "line up. The stories that changed depending on the day. So I started paying "
     "attention.",
     "clock, calendar, a door closing"),
    ("betrayal", "Then I found out",
     "Then it all came out. {Topic}. I'm not going to pretend I was calm. The floor "
     "just moved, and everything I thought I understood rearranged itself in a "
     "single moment.",
     "rain on a dark window, dim room"),
    ("fallout", "The quiet after",
     "For a few days I barely functioned. Part of me wanted to scream. A bigger "
     "part of me went very, very quiet. And looking back, that quiet was the most "
     "dangerous thing in the room.",
     "empty room, single lamp, long shadows"),
    ("decision", "I made a decision",
     "That's when I decided something. I wasn't going to beg, and I wasn't going "
     "to explode. I was going to wait, and I was going to be precise.",
     "close-up of steady, determined eyes"),
    ("plan", "I started preparing",
     "So I started preparing. Nothing dramatic. Just the truth, organized. Dates. "
     "Messages. Receipts. Everything they thought was hidden, quietly gathered in "
     "one place.",
     "documents, folder, screenshots on a screen"),
    ("escalation", "They had no idea",
     "And they had no idea. They kept performing, kept smiling, kept assuming I "
     "was still the person who missed the first sign. I let them keep thinking "
     "that. It made what came next so much cleaner.",
     "dinner table, forced smiles, glances"),
    ("turning_point", "The tables turned",
     "Then came the moment I'd been building toward. One room. The right people. "
     "And the truth laid out plainly, where no one could twist it or talk over it.",
     "meeting room, papers laid on a table"),
    ("payoff", "It was already too late",
     "{payoff}",
     "a stunned, silent realization"),
    ("aftermath", "What was left",
     "There were no fireworks. Just consequences, arriving right on schedule. They "
     "lost the thing they had risked everything to protect, and I got my life back "
     "without ever lowering myself to their level.",
     "an open door, walking into daylight"),
    ("reflection", "What it taught me",
     "Here's what I learned. The loudest reaction is almost never the strongest "
     "one. Sometimes the calmest person in the room is simply the one who already "
     "knows how the story ends.",
     "calm sunrise, a steady horizon"),
]


def _framework_story(topic: str, brand: Brand) -> Dict[str, object]:
    """Deterministic, brand-aware long-form beat sheet (no LLM required)."""
    seed = sum(ord(c) for c in topic) or 1
    hook = _fmt_template(brand.hook_templates[seed % len(brand.hook_templates)], topic)
    payoff = brand.payoff_templates[seed % len(brand.payoff_templates)]
    cta = brand.cta_templates[(seed // 3) % len(brand.cta_templates)]

    beats: List[Dict[str, str]] = []
    for role, on_screen, narration_tmpl, broll in STORY_ARC:
        narration = narration_tmpl.format(topic=topic, Topic=_cap_first(topic), payoff=payoff)
        beats.append({
            "role": role,
            "section": on_screen,
            "on_screen": on_screen,
            "narration": narration,
            "broll": broll,
        })
    return {"title": _title_case_topic(topic), "hook": hook, "beats": beats, "cta": cta}


def _normalize_story(data: Dict[str, object], topic: str, brand: Brand) -> Dict[str, object]:
    raw = data.get("beats") or []
    beats: List[Dict[str, str]] = []
    for i, b in enumerate(raw):
        if not isinstance(b, dict):
            continue
        narration = str(b.get("narration") or "").strip()
        if not narration:
            continue
        section = str(b.get("section") or b.get("on_screen") or f"Part {i + 1}")
        beats.append({
            "role": str(b.get("role") or "beat"),
            "section": section,
            "on_screen": str(b.get("on_screen") or section),
            "narration": narration,
            "broll": str(b.get("broll") or f"{topic} atmospheric b-roll"),
        })
    if not beats:
        return _framework_story(topic, brand)
    return {
        "title": str(data.get("title") or _title_case_topic(topic)),
        "hook": str(data.get("hook") or _fmt_template(brand.hook_templates[0], topic)),
        "beats": beats,
        "cta": str(data.get("cta") or brand.cta_templates[0]),
    }


def _story_script(topic: str, brand: Brand, llm: "LLMProvider", seconds: int) -> Dict[str, object]:
    target_words = int(seconds * WORDS_PER_SECOND)
    brief = ScriptBrief(
        topic=topic, brand_name=brand.display_name, voice=brand.voice,
        scene_count=len(STORY_ARC) + 2, seconds=seconds, point_count=0,
        kind="story", target_words=target_words,
    )
    data = None
    try:
        data = llm.write_script(brief)
    except Exception:
        data = None
    if data and data.get("beats"):
        return _normalize_story(data, topic, brand)
    return _framework_story(topic, brand)


def _build_story_scenes(script: Dict[str, object], seconds: int) -> List[Scene]:
    """Lay out hook + beats + CTA across the target runtime.

    The hook is held to ~10 seconds (the critical retention window); the CTA gets
    a fixed tail; the remaining time is distributed across the body beats weighted
    by narration length so longer beats read at a natural pace.
    """
    hook = str(script["hook"])
    beats = script["beats"]
    cta = str(script["cta"])

    scenes: List[Scene] = []
    idx = 0
    scenes.append(Scene(idx, "hook", _shorten(hook, 7), hook,
                        "cinematic cold-open establishing shot"))
    idx += 1
    for b in beats:
        scenes.append(Scene(idx, str(b.get("role", "beat")), _shorten(b["on_screen"], 6),
                            b["narration"], b.get("broll", "atmospheric b-roll")))
        idx += 1
    scenes.append(Scene(idx, "cta", _shorten(cta, 6), cta, "channel outro / subscribe prompt"))

    hook_dur = min(10.0, max(7.0, seconds * 0.02))
    cta_dur = min(12.0, max(6.0, seconds * 0.025))
    body = scenes[1:-1]
    weights = [max(4, len(s.narration.split())) for s in body]
    total_w = sum(weights) or 1
    remaining = max(1.0, seconds - hook_dur - cta_dur)

    scenes[0].start = 0.0
    scenes[0].end = round(hook_dur, 2)
    t = scenes[0].end
    for s, w in zip(body, weights):
        dur = max(6.0, round(remaining * (w / total_w), 2))
        s.start = round(t, 2)
        s.end = round(t + dur, 2)
        t = s.end
    scenes[-1].start = round(t, 2)
    scenes[-1].end = round(t + cta_dur, 2)
    return scenes


# --------------------------------------------------------------------------- #
# YouTube packaging (titles, SEO, thumbnails, promotion)
# --------------------------------------------------------------------------- #

_DEFAULT_TITLE_FRAMES = [
    "{t}",
    "The Truth About {t}",
    "I Never Saw {t} Coming",
    "How {t} Came Back Around",
]

_STOPWORDS = {"a", "an", "the", "and", "or", "for", "of", "to", "in", "on", "with",
              "that", "my", "our", "his", "her", "their", "was", "were", "is", "i"}


def _build_titles(topic: str, brand: Brand, limit: int = 6) -> List[str]:
    t = _title_case_topic(topic)
    frames = brand.title_templates or _DEFAULT_TITLE_FRAMES
    out: List[str] = []
    seen = set()
    for fr in frames:
        try:
            cand = fr.format(t=t, topic=t)
        except Exception:
            cand = t
        cand = " ".join(cand.split())
        key = cand.lower()
        if key not in seen and cand:
            seen.add(key)
            out.append(cand)
    # Prefer titles that fit YouTube's ~60-char sweet spot, but keep all
    # (stable sort on the original order; don't reference `out` inside the key).
    indexed = sorted(enumerate(out), key=lambda pair: (len(pair[1]) > 60, pair[0]))
    return [c for _, c in indexed][:limit]


def _best_keyword(topic: str) -> str:
    words = [re.sub(r"[^a-z0-9]", "", w.lower()) for w in topic.split()]
    words = [w for w in words if w and w not in _STOPWORDS]
    core = " ".join(words[:4]) if words else topic.lower()
    return f"{core} story".strip()


def _build_tags(topic: str, brand: Brand, limit: int = 15) -> List[str]:
    tags: List[str] = []
    for tier in ("broad", "mid", "niche", "branded"):
        for tag in brand.hashtag_bank.get(tier, []):
            tags.append(tag.lstrip("#"))
    # Topic-derived tags.
    words = [re.sub(r"[^a-z0-9]", "", w.lower()) for w in topic.split()]
    words = [w for w in words if len(w) > 3 and w not in _STOPWORDS]
    if words:
        tags.insert(0, " ".join(words[:3]))
    seen, out = set(), []
    for tag in tags:
        k = tag.lower()
        if tag and k not in seen:
            seen.add(k)
            out.append(tag)
    return out[:limit]


def _fmt_chapter_ts(seconds: float) -> str:
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def _build_chapters(scenes: List[Scene]) -> List[Dict[str, str]]:
    """YouTube chapters: first must be 0:00; pick the major narrative beats."""
    major = {"hook", "setup", "betrayal", "decision", "plan", "turning_point",
             "payoff", "aftermath", "reflection", "cta"}
    labels = {
        "hook": "The hook", "setup": "How it started", "betrayal": "The betrayal",
        "decision": "The decision", "plan": "The plan", "turning_point": "The tables turn",
        "payoff": "The payoff", "aftermath": "The aftermath", "reflection": "What it taught me",
        "cta": "Before you go",
    }
    chapters: List[Dict[str, str]] = []
    for s in scenes:
        if s.role in major:
            chapters.append({
                "time": _fmt_chapter_ts(s.start),
                "label": labels.get(s.role, s.on_screen),
            })
    if chapters:
        chapters[0]["time"] = "0:00"   # YouTube requires the first chapter at 0:00
    return chapters


def _build_youtube_seo(topic: str, brand: Brand, scenes: List[Scene],
                       titles: List[str]) -> Dict[str, object]:
    seed = sum(ord(c) for c in topic)
    opener = brand.caption_openers[seed % len(brand.caption_openers)]
    t = _title_case_topic(topic)
    tags = _build_tags(topic, brand)
    hashtags = " ".join("#" + tag.replace(" ", "") for tag in tags[:3])
    description = (
        f"{opener}\n\n"
        f"In this story: {t}. A slow-burn, true-to-life account of betrayal and the "
        f"quiet justice that followed — no spoilers here, you'll want to watch it unfold.\n\n"
        f"If you enjoy grounded betrayal and revenge stories, subscribe — there's a new "
        f"one every week.\n\n"
        f"Chapters are below. Story is dramatized for storytelling; names and details "
        f"are changed.\n\n"
        f"{hashtags}"
    )
    pinned = (
        "Would you have stayed quiet and waited, or said something the moment you found "
        "out? Tell me below \u2014 and no spoilers for anyone still watching. \U0001F447"
    )
    return {
        "best_title": titles[0] if titles else t,
        "title_variations": titles,
        "description": description,
        "tags": tags,
        "best_keyword": _best_keyword(topic),
        "pinned_comment": pinned,
        "chapters": _build_chapters(scenes),
    }


def _build_thumbnail_concepts(topic: str, brand: Brand) -> List[str]:
    out = []
    for c in (brand.thumbnail_concepts or []):
        out.append(_fmt_template(c, topic))
    return out or _build_thumbnail_text(topic, brand)


def _build_shorts_ideas(scenes: List[Scene]) -> List[str]:
    by_role = {s.role: s for s in scenes}
    ideas: List[str] = []
    hook = by_role.get("hook")
    betrayal = by_role.get("betrayal")
    payoff = by_role.get("payoff")
    if hook:
        ideas.append(f"Cold-open teaser (15-30s): open on \u201c{_shorten(hook.narration, 16)}\u201d "
                     f"then cut to black with \u201cFull story on the channel.\u201d")
    if betrayal:
        ideas.append("The reveal (20-40s): build for 10 seconds, then drop the moment the "
                     "betrayal is discovered. End on a question to drive comments.")
    if payoff:
        ideas.append("The payoff (20-40s): tease the setup in one line, then show the "
                     "satisfying turn. Caption: \u201cWould you have done the same?\u201d")
    return ideas


def _build_community_posts(topic: str, brand: Brand) -> List[str]:
    t = _title_case_topic(topic)
    return [
        f"Poll: When you sense a betrayal coming, do you (A) confront it immediately or "
        f"(B) stay quiet and watch? This week's story is about someone who chose B.",
        f"Teaser: New story dropping \u2014 \u201c{t}.\u201d One small mistake gave the "
        f"whole thing away. Any guesses what it was? \U0001F440",
    ]


# --------------------------------------------------------------------------- #
# Timing
# --------------------------------------------------------------------------- #

def _build_scenes(script: Dict[str, object], seconds: int) -> List[Scene]:
    points = script["points"]
    scenes: List[Scene] = []
    idx = 0

    scenes.append(Scene(idx, "hook", _shorten(script["hook"], 7), script["hook"], "bold opener"))
    idx += 1
    for p in points:
        scenes.append(Scene(idx, "point", _shorten(p["on_screen"], 6), p["narration"], p["broll"]))
        idx += 1
    scenes.append(Scene(idx, "payoff", _shorten(script["payoff"], 6), script["payoff"], "satisfying result"))
    idx += 1
    scenes.append(Scene(idx, "cta", _shorten(script["cta"], 6), script["cta"], "logo / follow prompt"))

    # Weight durations by role, then scale to the requested total length.
    weights = {"hook": 1.0, "context": 1.1, "point": 1.4, "payoff": 1.2, "cta": 1.3}
    raw = [weights.get(s.role, 1.0) for s in scenes]
    total_w = sum(raw)
    t = 0.0
    for s, w in zip(scenes, raw):
        dur = max(1.6, round(seconds * (w / total_w), 2))
        s.start = round(t, 2)
        s.end = round(t + dur, 2)
        t = s.end
    return scenes


def _shorten(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(",.;:") + "…"


# --------------------------------------------------------------------------- #
# Captions / SRT
# --------------------------------------------------------------------------- #

def _build_srt(scenes: List[Scene]) -> str:
    blocks: List[str] = []
    counter = 1
    for s in scenes:
        lines = _split_caption_lines(s.narration, max_words=6)
        span = max(0.6, s.duration)
        per = span / len(lines)
        for j, line in enumerate(lines):
            start = s.start + j * per
            end = start + per
            blocks.append(
                f"{counter}\n{_fmt_ts(start)} --> {_fmt_ts(end)}\n{line}\n"
            )
            counter += 1
    return "\n".join(blocks).strip() + "\n"


# --------------------------------------------------------------------------- #
# Hashtags
# --------------------------------------------------------------------------- #

def _build_hashtags(topic: str, brand: Brand) -> (Dict[str, List[str]], List[str]):
    bank = {k: list(v) for k, v in brand.hashtag_bank.items()}
    # Derive 1-2 topic-specific tags from the prompt keywords.
    words = [re.sub(r"[^a-z0-9]", "", w.lower()) for w in topic.split()]
    words = [w for w in words if len(w) > 3][:2]
    topical = ["#" + "".join(words)] if words else []
    if len(words) >= 2:
        topical.append("#" + words[0] + words[1])
    bank.setdefault("niche", [])
    for t in topical:
        if t not in bank["niche"]:
            bank["niche"].append(t)

    # A focused, copy-paste set (Instagram now favours a tight, relevant set).
    recommended: List[str] = []
    recommended += bank.get("broad", [])[:2]
    recommended += bank.get("mid", [])[:5]
    recommended += bank.get("niche", [])[:5]
    recommended += bank.get("branded", [])[:1]
    # De-dupe, preserve order.
    seen, out = set(), []
    for t in recommended:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return bank, out


# --------------------------------------------------------------------------- #
# Caption / SSML / accessibility
# --------------------------------------------------------------------------- #

def _build_caption(topic: str, brand: Brand, scenes: List[Scene], recommended: List[str]) -> str:
    opener = brand.caption_openers[sum(ord(c) for c in topic) % len(brand.caption_openers)]
    bullets = [f"• {s.on_screen}" for s in scenes if s.role == "point"]
    cta = next((s.narration for s in scenes if s.role == "cta"), brand.cta_templates[0])
    body = "\n".join(bullets)
    tags = " ".join(recommended)
    return (
        f"{opener}\n\n"
        f"{_title_case_topic(topic)} —\n{body}\n\n"
        f"{cta}\n"
        f".\n.\n.\n"
        f"{tags}"
    )


def _build_ssml(scenes: List[Scene], brand: Brand) -> str:
    parts = ["<speak>"]
    for s in scenes:
        emphasis = ' rate="medium"'
        if s.role == "hook":
            emphasis = ' rate="fast" pitch="+2st"'
        if s.role == "cta":
            emphasis = ' rate="medium" pitch="+1st"'
        text = s.narration.replace("&", "and").replace("<", "").replace(">", "")
        parts.append(f'  <prosody{emphasis}>{text}</prosody><break time="350ms"/>')
    parts.append("</speak>")
    return "\n".join(parts)


def _build_thumbnail_text(topic: str, brand: Brand) -> List[str]:
    t = _title_case_topic(topic)
    return [
        t,
        f"{t}\n(most people miss #3)",
        f"DON'T scroll past {t.split()[0].upper()}",
    ]


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def generate(
    topic: str,
    brand_key: str = "ai_income",
    seconds: int = 0,
    point_count: int = 4,
    llm: Optional[LLMProvider] = None,
    fmt: Optional[str] = None,
) -> ContentKit:
    topic = _clean_topic(topic)
    if not topic:
        raise ValueError("topic is empty")
    brand = get_brand(brand_key)
    llm = llm or auto_llm()

    # Resolve format: explicit > brand default ("story" -> long) > short.
    if fmt not in ("short", "long"):
        fmt = "long" if brand.niche_kind == "story" else "short"
    # Resolve duration: 0/None means "auto" based on format.
    if not seconds or seconds <= 0:
        seconds = brand.default_long_seconds if fmt == "long" else 35

    if fmt == "long":
        return _generate_long(topic, brand, seconds, llm)
    return _generate_short(topic, brand, seconds, point_count, llm)


def _generate_short(topic: str, brand: Brand, seconds: int, point_count: int,
                    llm: LLMProvider) -> ContentKit:
    brief = ScriptBrief(
        topic=topic, brand_name=brand.display_name, voice=brand.voice,
        scene_count=point_count + 3, seconds=seconds, point_count=point_count,
    )
    llm_out = None
    try:
        llm_out = llm.write_script(brief)
    except Exception:
        llm_out = None

    if llm_out:
        script = _normalize_llm(llm_out, topic, brand)
        generator = f"llm:{getattr(llm, 'name', 'unknown')}"
    else:
        script = _framework_script(topic, brand, point_count)
        generator = "framework:offline"

    scenes = _build_scenes(script, seconds)
    srt = _build_srt(scenes)
    hashtags, recommended = _build_hashtags(topic, brand)
    caption = _build_caption(topic, brand, scenes, recommended)
    voiceover_text = " ".join(s.narration for s in scenes)
    voiceover_ssml = _build_ssml(scenes, brand)

    seed = sum(ord(c) for c in topic)
    hook_variants = [
        _fmt_template(brand.hook_templates[(seed + i) % len(brand.hook_templates)], topic)
        for i in range(3)
    ]
    alt_text = (
        f"Vertical text-on-screen video about {topic}. "
        f"{len([s for s in scenes if s.role == 'point'])} quick tips with bold captions."
    )

    return ContentKit(
        topic=topic,
        brand_key=brand.key,
        brand_name=brand.display_name,
        title=str(script["title"]),
        hook=str(script["hook"]),
        hook_variants=hook_variants,
        cta=str(script["cta"]),
        scenes=scenes,
        srt=srt,
        caption=caption,
        alt_text=alt_text,
        hashtags=hashtags,
        recommended_hashtags=recommended,
        voiceover_text=voiceover_text,
        voiceover_ssml=voiceover_ssml,
        thumbnail_text=_build_thumbnail_text(topic, brand),
        series_name=brand.series_name,
        best_post_times_utc=brand.best_post_times_utc,
        total_seconds=round(scenes[-1].end, 2) if scenes else float(seconds),
        generator=generator,
        created_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        format="short",
    )


def _generate_long(topic: str, brand: Brand, seconds: int, llm: LLMProvider) -> ContentKit:
    script = _story_script(topic, brand, llm, seconds)
    # Label the generator from whether the LLM actually returned custom beats.
    generator = f"llm:{getattr(llm, 'name', 'unknown')}" if (
        getattr(llm, "name", "") not in ("offline-template", "")
        and not _is_framework_story(script, brand)
    ) else "framework:offline"

    scenes = _build_story_scenes(script, seconds)
    srt = _build_srt(scenes)
    voiceover_text = "\n\n".join(s.narration for s in scenes)
    voiceover_ssml = _build_ssml(scenes, brand)

    titles = _build_titles(topic, brand)
    youtube = _build_youtube_seo(topic, brand, scenes, titles)
    thumbnail_concepts = _build_thumbnail_concepts(topic, brand)
    shorts_ideas = _build_shorts_ideas(scenes)
    community_posts = _build_community_posts(topic, brand)

    seed = sum(ord(c) for c in topic)
    hook_variants = [
        _fmt_template(brand.hook_templates[(seed + i) % len(brand.hook_templates)], topic)
        for i in range(3)
    ]
    word_count = sum(len(s.narration.split()) for s in scenes)
    alt_text = (
        f"Faceless narrated story video about {topic}. ~{seconds // 60} minutes, "
        f"{len(scenes)} narrative beats."
    )

    return ContentKit(
        topic=topic,
        brand_key=brand.key,
        brand_name=brand.display_name,
        title=str(youtube.get("best_title") or script["title"]),
        hook=str(script["hook"]),
        hook_variants=hook_variants,
        cta=str(script["cta"]),
        scenes=scenes,
        srt=srt,
        caption=str(youtube.get("description", "")),
        alt_text=alt_text,
        hashtags={"tags": youtube.get("tags", [])},
        recommended_hashtags=list(youtube.get("tags", [])),
        voiceover_text=voiceover_text,
        voiceover_ssml=voiceover_ssml,
        thumbnail_text=[t for t in titles[:3]],
        series_name=brand.series_name,
        best_post_times_utc=brand.best_post_times_utc,
        total_seconds=round(scenes[-1].end, 2) if scenes else float(seconds),
        generator=generator,
        created_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        format="long",
        titles=titles,
        youtube=youtube,
        thumbnail_concepts=thumbnail_concepts,
        shorts_ideas=shorts_ideas,
        community_posts=community_posts,
    )


def _is_framework_story(script: Dict[str, object], brand: Brand) -> bool:
    """Heuristic: did we fall back to the offline beat sheet? Used for labeling."""
    beats = script.get("beats") or []
    if not beats:
        return True
    roles = [b.get("role") for b in beats]
    arc_roles = [r for r, *_ in STORY_ARC]
    return roles == arc_roles


def _slugify(text: str, maxlen: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:maxlen] or "kit"


def write_kit(kit: ContentKit, out_root: str = "content_kits") -> str:
    """Write all kit files into out_root/<timestamp>-<slug>/ and return the path."""
    from . import storyboard  # local import avoids a circular dependency

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = os.path.join(out_root, f"{stamp}-{kit.brand_key}-{_slugify(kit.topic)}")
    os.makedirs(folder, exist_ok=True)

    # script.md
    script_md = [f"# {kit.title}", "", f"*Brand:* {kit.brand_name}  |  *Length:* "
                 f"~{kit.total_seconds:.0f}s  |  *Generator:* {kit.generator}", "",
                 f"**Hook:** {kit.hook}", "", "## Scenes", ""]
    for s in kit.scenes:
        script_md += [
            f"### {s.index + 1}. [{s.role.upper()}]  {s.start:.1f}s–{s.end:.1f}s "
            f"({s.duration:.1f}s)",
            f"- **On screen:** {s.on_screen}",
            f"- **Voiceover:** {s.narration}",
            f"- **B-roll:** {s.broll_query}",
            "",
        ]
    _write(folder, "script.md", "\n".join(script_md))

    _write(folder, "voiceover.txt", kit.voiceover_text + "\n")
    _write(folder, "voiceover.ssml", kit.voiceover_ssml + "\n")
    _write(folder, "captions.srt", kit.srt)

    if kit.format == "long":
        _write_youtube_files(folder, kit)
    else:
        _write_instagram_files(folder, kit)

    # shotlist.md
    shot = ["# Shot list / b-roll direction", ""]
    for s in kit.scenes:
        shot += [f"- **{s.start:.1f}s** [{s.role}] search: `{s.broll_query}` — "
                 f"overlay: \"{s.on_screen}\""]
    _write(folder, "shotlist.md", "\n".join(shot) + "\n")

    # content_package.json
    payload = kit.to_dict()
    payload["environment"] = environment_report()
    _write(folder, "content_package.json", json.dumps(payload, indent=2, ensure_ascii=False))

    # storyboard.html (animated preview)
    _write(folder, "storyboard.html", storyboard.render_html(kit, get_brand(kit.brand_key)))

    return folder


def _write(folder: str, name: str, content: str) -> None:
    with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
        fh.write(content)


def _write_instagram_files(folder: str, kit: ContentKit) -> None:
    """post.md + hashtags.txt for the short-form Instagram/Reels path."""
    post_md = [
        "# Instagram post", "", "## Caption", "", kit.caption, "",
        "## Hook A/B variants", "",
        *[f"{i+1}. {h}" for i, h in enumerate(kit.hook_variants)], "",
        "## Accessibility (alt text)", "", kit.alt_text, "",
        "## Thumbnail / cover text ideas", "",
        *[f"- {textwrap.shorten(t, 80)}" for t in kit.thumbnail_text], "",
        "## Posting", "",
        f"- Series: **{kit.series_name}**",
        f"- Suggested post times (UTC): {', '.join(kit.best_post_times_utc)}",
    ]
    _write(folder, "post.md", "\n".join(post_md))

    ht = ["# Hashtag strategy", "",
          "## Recommended set (copy-paste)", " ".join(kit.recommended_hashtags), ""]
    for tier in ("broad", "mid", "niche", "branded"):
        tags = kit.hashtags.get(tier, [])
        if tags:
            ht += [f"## {tier} ({len(tags)})", " ".join(tags), ""]
    _write(folder, "hashtags.txt", "\n".join(ht))


def _write_youtube_files(folder: str, kit: ContentKit) -> None:
    """The full YouTube "Video Pack": titles, SEO, thumbnails, promotion + a
    single combined VIDEO_PACK.md the creator can work straight from."""
    yt = kit.youtube or {}

    # titles.md
    titles_md = ["# Title options", "",
                 f"**Recommended:** {yt.get('best_title', kit.title)}", "",
                 "## Variations"]
    titles_md += [f"{i+1}. {t}  _({len(t)} chars)_" for i, t in enumerate(kit.titles)]
    _write(folder, "titles.md", "\n".join(titles_md) + "\n")

    # seo.md
    chapters = yt.get("chapters", [])
    seo_md = [
        "# YouTube upload pack", "",
        f"**Best title:** {yt.get('best_title', kit.title)}", "",
        f"**Primary keyword:** {yt.get('best_keyword', '')}", "",
        "## Description", "", yt.get("description", ""), "",
        "## Tags", "", ", ".join(yt.get("tags", [])), "",
        "## Chapters (paste into the description)", "",
        *[f"{c['time']} {c['label']}" for c in chapters], "",
        "## Pinned comment", "", yt.get("pinned_comment", ""), "",
        "## Upload notes", "",
        f"- Series: **{kit.series_name}**",
        f"- Suggested upload times (UTC): {', '.join(kit.best_post_times_utc)}",
        f"- Target length: ~{kit.total_seconds / 60:.0f} min",
    ]
    _write(folder, "seo.md", "\n".join(seo_md) + "\n")

    # thumbnails.md
    thumb_md = ["# Thumbnail concepts (mobile-first, <=4 words of overlay)", ""]
    for i, c in enumerate(kit.thumbnail_concepts, 1):
        thumb_md.append(f"{i}. {c}")
    _write(folder, "thumbnails.md", "\n".join(thumb_md) + "\n")

    # promotion.md
    promo_md = ["# Promotion", "", "## Shorts ideas", ""]
    promo_md += [f"- {s}" for s in kit.shorts_ideas]
    promo_md += ["", "## Community post ideas", ""]
    promo_md += [f"- {c}" for c in kit.community_posts]
    _write(folder, "promotion.md", "\n".join(promo_md) + "\n")

    # VIDEO_PACK.md — one combined, production-ready document.
    pack = [
        f"# Video Pack — {yt.get('best_title', kit.title)}", "",
        f"*Channel:* {kit.brand_name}  ·  *Series:* {kit.series_name}  ·  "
        f"*Target length:* ~{kit.total_seconds / 60:.0f} min  ·  *Script by:* {kit.generator}",
        "",
        "> Note: when generated offline this is a structured **beat sheet** to edit; "
        "set `OPENAI_API_KEY` for fully-written narration.", "",
        "## 1. Title", "",
        f"**{yt.get('best_title', kit.title)}**", "",
        "Alternatives:",
        *[f"- {t}" for t in kit.titles[1:]],
        "",
        "## 2. Hook (first ~10 seconds)", "", f"> {kit.hook}", "",
        "## 3. Narration script", "",
    ]
    for s in kit.scenes:
        label = s.on_screen if s.role not in ("hook", "cta") else s.role.upper()
        pack += [f"### [{s.role}] {label}  ({s.start:.0f}s–{s.end:.0f}s)", "",
                 s.narration, ""]
    pack += [
        "## 4. SEO", "",
        f"- **Primary keyword:** {yt.get('best_keyword', '')}",
        f"- **Tags:** {', '.join(yt.get('tags', []))}",
        "", "**Description:**", "", yt.get("description", ""), "",
        "**Chapters:**", "",
        *[f"{c['time']} {c['label']}" for c in chapters], "",
        "**Pinned comment:**", "", yt.get("pinned_comment", ""), "",
        "## 5. Thumbnails", "",
        *[f"{i+1}. {c}" for i, c in enumerate(kit.thumbnail_concepts)], "",
        "## 6. Promotion", "",
        "**Shorts:**",
        *[f"- {s}" for s in kit.shorts_ideas],
        "", "**Community posts:**",
        *[f"- {c}" for c in kit.community_posts], "",
        "## 7. Production notes", "",
        "- Voiceover: see `voiceover.txt` (plain) and `voiceover.ssml` (pacing/emphasis).",
        "- Visuals: see `shotlist.md` for per-beat b-roll search terms (Pexels/Pixabay).",
        "- Captions: `captions.srt` is ready to burn in.",
        "- Preview pacing: open `storyboard.html` in a browser.",
    ]
    _write(folder, "VIDEO_PACK.md", "\n".join(pack) + "\n")
