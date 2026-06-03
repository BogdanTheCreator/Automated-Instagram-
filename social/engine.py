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
    hook = brand.hook_templates[seed % len(brand.hook_templates)].format(topic=topic)
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
        "hook": str(data.get("hook") or brand.hook_templates[0].format(topic=topic)),
        "points": norm_points or _framework_script(topic, brand, 3)["points"],
        "payoff": str(data.get("payoff") or brand.payoff_templates[0]),
        "cta": str(data.get("cta") or brand.cta_templates[0]),
    }


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
    seconds: int = 35,
    point_count: int = 4,
    llm: Optional[LLMProvider] = None,
) -> ContentKit:
    topic = _clean_topic(topic)
    if not topic:
        raise ValueError("topic is empty")
    brand = get_brand(brand_key)
    llm = llm or auto_llm()

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
        brand.hook_templates[(seed + i) % len(brand.hook_templates)].format(topic=topic)
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
    )


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

    # post.md
    post_md = [
        "# Instagram post", "", "## Caption", "", kit.caption, "",
        "## Hook A/B variants", "",
        *[f"{i+1}. {h}" for i, h in enumerate(kit.hook_variants)], "",
        "## Accessibility (alt text)", "", kit.alt_text, "",
        "## Thumbnail / cover text ideas", "",
        *[f"- {textwrap.shorten(t, 80)}" for t in kit.thumbnail_text], "",
        f"## Posting", "",
        f"- Series: **{kit.series_name}**",
        f"- Suggested post times (UTC): {', '.join(kit.best_post_times_utc)}",
    ]
    _write(folder, "post.md", "\n".join(post_md))

    # hashtags.txt
    ht = ["# Hashtag strategy", "",
          "## Recommended set (copy-paste)", " ".join(kit.recommended_hashtags), ""]
    for tier in ("broad", "mid", "niche", "branded"):
        tags = kit.hashtags.get(tier, [])
        if tags:
            ht += [f"## {tier} ({len(tags)})", " ".join(tags), ""]
    _write(folder, "hashtags.txt", "\n".join(ht))

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
