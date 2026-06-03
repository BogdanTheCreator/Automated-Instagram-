"""
calendar.py — generate a month (or any N days) of content in one run.

`generate_calendar(...)` builds a posting schedule: for each day it picks a
distinct topic (LLM-proposed when a key is set, otherwise a deterministic
format x theme combiner), assigns a content pillar, a posting time, a series
episode number and a weekday. `write_calendar(...)` saves it as:

    calendar.md    human-readable table you can glance at
    calendar.csv   import straight into Notion / Google Sheets / a scheduler
    calendar.json  machine-readable, for automation

With `with_kits=True` it also generates the full content kit (script, captions,
hashtags, voiceover, animated storyboard.html, ...) for every day into per-day
subfolders — i.e. a whole month of ready-to-post content from a single command.
"""
from __future__ import annotations

import csv
import json
import math
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional

from .brand import Brand, get_brand
from .engine import generate, write_kit
from .providers import LLMProvider, auto_llm

# Angle templates: each turns a noun-phrase theme into a distinct video prompt.
# Rotating these across days gives the month a varied, intentional rhythm.
FORMATS: List[tuple] = [
    ("list", "{n} things you should know about {theme}"),
    ("myth", "the biggest myth about {theme}"),
    ("howto", "how to actually get started with {theme}"),
    ("mistake", "the mistake almost everyone makes with {theme}"),
    ("quickwin", "do this one thing for {theme} this week"),
    ("explainer", "{theme}, explained in 30 seconds"),
    ("secret", "what nobody tells you about {theme}"),
    ("tool", "the free tool for {theme} that feels like cheating"),
    ("contrarian", "stop overthinking {theme} — do this instead"),
    ("proof", "the before and after of getting {theme} right"),
]


@dataclass
class CalendarDay:
    day: int                 # 1-based index in the plan
    date: str                # YYYY-MM-DD
    weekday: str
    post_time_utc: str
    pillar: str
    fmt: str                 # format/angle key
    topic: str
    series_label: str        # e.g. "AI Money Move #1"
    status: str = "planned"
    kit_folder: Optional[str] = None


def _offline_topics(brand: Brand, count: int) -> List[tuple]:
    """Deterministic, de-duplicated (topic, format) pairs from themes x FORMATS.

    Iterates theme-major and shifts the format each time the theme list wraps, so
    consecutive days differ in both theme and angle, and a theme only recurs with
    a *different* format once all themes are used.
    """
    themes = brand.themes or brand.topic_seeds or ["this niche"]
    seed = sum(ord(c) for c in brand.key)
    pairs: List[tuple] = []
    seen = set()
    nt, nf = len(themes), len(FORMATS)
    idx = 0
    while len(pairs) < count and idx < nt * nf:
        cycle, pos = divmod(idx, nt)
        theme = themes[(seed + pos) % nt]
        fmt_name, tmpl = FORMATS[(seed + pos + cycle) % nf]
        n = (idx % 3) + 3
        topic = tmpl.format(theme=theme, n=n)
        key = topic.lower()
        if key not in seen:
            seen.add(key)
            pairs.append((topic, fmt_name))
        idx += 1
    return pairs[:count]


def propose_topics(brand: Brand, count: int, llm: Optional[LLMProvider] = None) -> (List[tuple], str):
    """Return (pairs, source) where pairs are (topic, format). LLM when available."""
    llm = llm or auto_llm()
    try:
        proposed = llm.propose_topics(brand.display_name, brand.voice,
                                      brand.content_pillars or [], count)
    except Exception:
        proposed = None
    if proposed:
        pairs = [(t, "ai") for t in proposed]
        if len(pairs) < count:  # top up from the offline combiner if short
            pairs += _offline_topics(brand, count - len(pairs))
        return pairs[:count], f"llm:{getattr(llm, 'name', 'unknown')}"
    return _offline_topics(brand, count), "framework:offline"


def _pillar_for_index(brand: Brand, theme_index: int, total: int) -> str:
    pillars = brand.content_pillars or ["general"]
    chunk = max(1, math.ceil(max(total, len(pillars)) / len(pillars)))
    return pillars[min(theme_index // chunk, len(pillars) - 1)]


def _parse_start(start: Optional[str]) -> date:
    if not start:
        return date.today()
    return datetime.strptime(start, "%Y-%m-%d").date()


def topic_for_date(brand_key: str, when: Optional[date] = None,
                   llm: Optional[LLMProvider] = None) -> tuple:
    """Deterministic (topic, format) for a given calendar date.

    Used by the auto-poster so each day maps to a stable, non-repeating topic
    without needing to store state. Walks the full theme x format space and
    indexes it by the date's ordinal, so the same date always yields the same
    topic but consecutive days differ.
    """
    brand = get_brand(brand_key)
    when = when or date.today()
    # Build a large distinct pool (offline). LLM topics aren't used here because
    # we want determinism per-date without an API call on every scheduled run.
    pool = _offline_topics(brand, 366)
    if not pool:
        return (brand.topic_seeds[0] if brand.topic_seeds else "this niche", "explainer")
    return pool[when.toordinal() % len(pool)]


def generate_calendar(
    brand_key: str = "ai_income",
    days: int = 30,
    start: Optional[str] = None,
    posts_per_day: int = 1,
    llm: Optional[LLMProvider] = None,
) -> (List[CalendarDay], str):
    """Build the plan (no files written). Returns (entries, topic_source)."""
    brand = get_brand(brand_key)
    start_date = _parse_start(start)
    total_posts = days * posts_per_day
    pairs, source = propose_topics(brand, total_posts, llm=llm)
    times = brand.best_post_times_utc or ["17:00"]

    entries: List[CalendarDay] = []
    post_index = 0
    for d in range(days):
        the_date = start_date + timedelta(days=d)
        for slot in range(posts_per_day):
            topic, fmt_name = pairs[post_index % len(pairs)]
            entries.append(CalendarDay(
                day=d + 1,
                date=the_date.isoformat(),
                weekday=the_date.strftime("%a"),
                post_time_utc=times[slot % len(times)],
                pillar=_pillar_for_index(brand, post_index, total_posts),
                fmt=fmt_name,
                topic=topic,
                series_label=f"{brand.series_name} #{post_index + 1}",
            ))
            post_index += 1
    return entries, source


def write_calendar(
    brand_key: str = "ai_income",
    days: int = 30,
    start: Optional[str] = None,
    posts_per_day: int = 1,
    seconds: int = 35,
    points: int = 4,
    with_kits: bool = False,
    out_root: str = "content_kits",
) -> str:
    """Generate the calendar (and optionally every kit) into a month folder."""
    brand = get_brand(brand_key)
    entries, source = generate_calendar(brand_key, days, start, posts_per_day)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = os.path.join(out_root, f"{stamp}-{brand.key}-calendar-{days}d")
    os.makedirs(folder, exist_ok=True)

    if with_kits:
        kits_dir = os.path.join(folder, "kits")
        os.makedirs(kits_dir, exist_ok=True)
        for e in entries:
            kit = generate(e.topic, brand_key=brand.key, seconds=seconds, point_count=points)
            kit_folder = write_kit(kit, out_root=kits_dir)
            e.kit_folder = os.path.relpath(kit_folder, folder)

    _write_md(folder, brand, entries, source, with_kits)
    _write_csv(folder, entries)
    _write_json(folder, brand, entries, source, days, posts_per_day, with_kits)
    return folder


def _write_md(folder: str, brand: Brand, entries: List[CalendarDay],
              source: str, with_kits: bool) -> None:
    lines = [
        f"# {brand.display_name} — {len(entries)}-post content calendar",
        "",
        f"*Series:* {brand.series_name}  |  *Topic source:* {source}  |  "
        f"*Pillars:* {', '.join(brand.content_pillars)}",
        "",
        "| # | Date | Day | Time (UTC) | Pillar | Format | Topic |",
        "|---|------|-----|-----------|--------|--------|-------|",
    ]
    for e in entries:
        lines.append(
            f"| {e.day} | {e.date} | {e.weekday} | {e.post_time_utc} | "
            f"{e.pillar} | {e.fmt} | {e.topic} |"
        )
    if with_kits:
        lines += ["", "## Kits", "",
                  "Each topic has a full content kit (open the `storyboard.html` "
                  "inside each folder to preview):", ""]
        for e in entries:
            lines.append(f"- Day {e.day}: `{e.kit_folder}`")
    lines += ["", "## How to use this", "",
              "1. Each row is one post. Batch-record/generate, then schedule.",
              "2. Import `calendar.csv` into Notion, Google Sheets, or a scheduler.",
              "3. Post at the suggested times; keep the series label in the caption "
              "so the account feels consistent.", ""]
    with open(os.path.join(folder, "calendar.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def _write_csv(folder: str, entries: List[CalendarDay]) -> None:
    with open(os.path.join(folder, "calendar.csv"), "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["day", "date", "weekday", "post_time_utc", "pillar",
                         "format", "topic", "series_label", "status", "kit_folder"])
        for e in entries:
            writer.writerow([e.day, e.date, e.weekday, e.post_time_utc, e.pillar,
                             e.fmt, e.topic, e.series_label, e.status, e.kit_folder or ""])


def _write_json(folder: str, brand: Brand, entries: List[CalendarDay],
                source: str, days: int, posts_per_day: int, with_kits: bool) -> None:
    payload = {
        "brand": brand.key,
        "brand_name": brand.display_name,
        "series_name": brand.series_name,
        "pillars": brand.content_pillars,
        "topic_source": source,
        "days": days,
        "posts_per_day": posts_per_day,
        "with_kits": with_kits,
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "entries": [asdict(e) for e in entries],
    }
    with open(os.path.join(folder, "calendar.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
