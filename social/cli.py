"""
cli.py — command-line entrypoint.

Examples
--------
    # Generate a full content kit (recommended AI-income niche, ~35s)
    python -m social.cli "3 free AI tools that replace a marketing team"

    # Pick a niche and length, ask for 5 value points
    python -m social.cli "delete yourself from data broker sites" \
        --brand privacy --duration 40 --points 5

    # Also render a real MP4 (needs ffmpeg on PATH; uses TTS if available)
    python -m social.cli "the 50/30/20 budget" --brand money --render

    # See what premium features are active in this environment
    python -m social.cli --doctor

    # List available niches / topic ideas
    python -m social.cli --list-brands
    python -m social.cli --ideas --brand ai_income

Premium upgrades are picked up automatically from environment variables:
    OPENAI_API_KEY     -> smart, original scripts (any OpenAI-compatible API)
    ELEVENLABS_API_KEY -> premium voiceover     (or install `edge-tts` for free)
    PEXELS_API_KEY     -> real stock b-roll URLs in the shot list
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from . import __version__
from .brand import DEFAULT_BRAND, get_brand, list_brands
from .engine import generate, write_kit
from .providers import environment_report


def _doctor() -> int:
    env = environment_report()
    print("social doctor — premium feature availability\n" + "-" * 44)
    rows = [
        ("Smart scripts (LLM)", env["openai_key"], "set OPENAI_API_KEY (OpenAI/Groq/Ollama/...)"),
        ("Premium voice (ElevenLabs)", env["elevenlabs_key"], "set ELEVENLABS_API_KEY"),
        ("Free voice (edge-tts)", env["edge_tts"], "pip install edge-tts"),
        ("Local voice (pyttsx3)", env["pyttsx3"], "pip install pyttsx3"),
        ("Stock b-roll (Pexels)", env["pexels_key"], "set PEXELS_API_KEY"),
        ("MP4 rendering (ffmpeg)", env["ffmpeg"], "install ffmpeg"),
    ]
    for label, ok, how in rows:
        mark = "ON " if ok else "off"
        tail = "" if ok else f"   -> {how}"
        print(f"  [{mark}] {label}{tail}")
    print("\nEverything below works WITHOUT any of the above (offline scaffolding).")
    return 0


def _list_brands() -> int:
    print("Available niches / brand presets:\n")
    for key in list_brands():
        b = get_brand(key)
        star = "  (default, recommended)" if key == DEFAULT_BRAND else ""
        print(f"  {key:10s} — {b.display_name}: {b.tagline}{star}")
        print(f"             handle ideas: {', '.join(b.handle_ideas[:3])}")
    return 0


def _ideas(brand_key: str) -> int:
    b = get_brand(brand_key)
    print(f"Topic ideas for {b.display_name} ({b.key}):\n")
    for i, seed in enumerate(b.topic_seeds, 1):
        print(f"  {i}. {seed}")
    return 0


def _run_calendar(args) -> int:
    from .calendar import write_calendar
    try:
        folder = write_calendar(
            brand_key=args.brand,
            days=args.days,
            start=args.start,
            posts_per_day=args.posts_per_day,
            seconds=args.duration,
            points=args.points,
            with_kits=args.with_kits,
            out_root=args.out,
        )
    except (KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    total = args.days * args.posts_per_day
    print(f"\n  {args.days}-day calendar ready: {folder}\n")
    print(f"  Brand : {get_brand(args.brand).display_name} ({args.brand})")
    print(f"  Posts : {total} ({args.posts_per_day}/day)")
    print(f"  Files : calendar.md, calendar.csv, calendar.json")
    if args.with_kits:
        print(f"  Kits  : a full content kit per post under {os.path.join(folder, 'kits')}/")
    else:
        print("  Tip   : add --with-kits to also generate every video kit in one run.")
    print(f"\n  Import calendar.csv into Notion/Sheets/your scheduler to plan the month.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="social",
        description="Turn one prompt into a complete faceless short-form content kit.",
    )
    p.add_argument("topic", nargs="?", help="What the video is about (a prompt).")
    p.add_argument("--brand", "-b", default=DEFAULT_BRAND,
                   help=f"Niche preset (default: {DEFAULT_BRAND}). See --list-brands.")
    p.add_argument("--duration", "-d", type=int, default=0,
                   help="Target length in seconds. 0 = auto (35s for short-form, "
                        "~600s for long-form story brands).")
    p.add_argument("--minutes", type=int, default=0,
                   help="Target length in minutes (long-form convenience; overrides --duration).")
    p.add_argument("--format", choices=["short", "long"], default=None,
                   help="Content format: 'short' (Reels/Shorts) or 'long' (8-12 min "
                        "narrated story). Default: auto from brand (story brands -> long).")
    p.add_argument("--long", action="store_true", help="Shortcut for --format long.")
    p.add_argument("--points", "-p", type=int, default=4,
                   help="Number of value points/tips for short-form (default 4).")
    p.add_argument("--out", "-o", default="content_kits",
                   help="Output root folder (default ./content_kits).")
    p.add_argument("--render", action="store_true",
                   help="Also render an MP4 (requires ffmpeg). Short-form -> vertical "
                        "Reel; long-form Video Pack -> a single upload-ready landscape "
                        "video.mp4 (captions baked in) + a matching thumbnail.jpg.")
    p.add_argument("--no-captions", action="store_true",
                   help="For long-form --render: do NOT bake captions into the video "
                        "(default bakes them in for a self-contained file).")
    p.add_argument("--no-thumbnail", action="store_true",
                   help="For long-form --render: skip generating thumbnail.jpg.")
    p.add_argument("--music", default=None, help="Path to background music for --render.")
    p.add_argument("--no-voiceover", action="store_true",
                   help="Skip TTS voiceover when rendering.")
    p.add_argument("--voiceover", action="store_true",
                   help="For long-form packs: synthesize the narration to MP3 "
                        "(per-beat clips + a combined narration.mp3) using edge-tts "
                        "(free) or ELEVENLABS_API_KEY. Writes into the pack's audio/ folder.")
    p.add_argument("--doctor", action="store_true", help="Report premium feature availability.")
    p.add_argument("--list-brands", action="store_true", help="List niche presets and exit.")
    p.add_argument("--ideas", action="store_true", help="Print topic ideas for the brand and exit.")
    # Long-form YouTube "Video Pack" modes
    p.add_argument("--videopack", action="store_true",
                   help="Generate a complete long-form YouTube Video Pack (script + SEO "
                        "+ thumbnails + promotion). Topic optional; one is proposed if omitted.")
    p.add_argument("--weekly", action="store_true",
                   help="Weekly bundle: opportunity report + a full Video Pack for the "
                        "top topic (used by the weekly workflow).")
    p.add_argument("--report", action="store_true",
                   help="Write only the weekly opportunity report (10 ranked topics).")
    # Calendar mode
    p.add_argument("--calendar", action="store_true",
                   help="Generate a multi-day content calendar instead of a single kit.")
    p.add_argument("--days", type=int, default=30, help="Calendar length in days (default 30).")
    p.add_argument("--start", default=None, help="Calendar start date YYYY-MM-DD (default today).")
    p.add_argument("--posts-per-day", type=int, default=1, help="Posts per day (default 1).")
    p.add_argument("--with-kits", action="store_true",
                   help="With --calendar: also generate a full content kit for every day.")
    # Auto-post / publishing
    p.add_argument("--autopost", action="store_true",
                   help="Generate + render today's post (topic chosen by date) into --out.")
    p.add_argument("--publish", action="store_true",
                   help="Publish a video to Instagram via the Graph API (needs IG_* env).")
    p.add_argument("--verify-instagram", action="store_true",
                   help="Check that IG_USER_ID + IG_ACCESS_TOKEN work, then exit.")
    p.add_argument("--video-url", default=None,
                   help="Public URL of the video to publish (with --publish).")
    p.add_argument("--caption", default=None, help="Caption text (overrides --kit/--caption-file).")
    p.add_argument("--caption-file", default=None, help="Path to a file containing the caption.")
    p.add_argument("--kit", default=None,
                   help="Path to a kit folder; reads caption from its content_package.json.")
    p.add_argument("--dry-run", action="store_true",
                   help="With --publish: show what would post without calling Instagram.")
    p.add_argument("--cover-url", default=None,
                   help="Public URL of a cover image for the Reel (with --publish).")
    p.add_argument("--refresh-token", action="store_true",
                   help="Refresh the long-lived IG token (needs IG_APP_ID, IG_APP_SECRET, IG_ACCESS_TOKEN).")
    p.add_argument("--version", action="version", version=f"social {__version__}")
    return p


def _resolve_fmt(args) -> Optional[str]:
    if getattr(args, "long", False):
        return "long"
    return args.format  # None -> auto by brand


def _resolve_seconds(args) -> int:
    if getattr(args, "minutes", 0) and args.minutes > 0:
        return args.minutes * 60
    return args.duration  # 0 -> auto in engine


def _maybe_voiceover(args, kit, folder) -> None:
    """If --voiceover was requested, synthesize narration audio into the pack
    folder and print a clear status line. Never raises."""
    if not getattr(args, "voiceover", False):
        return
    from .narration import synthesize_narration
    res = synthesize_narration(kit, folder)
    print(f"\n  Voiceover: {res.message}")
    if res.ok and res.combined:
        print(f"    Combined : {res.combined}")
        print(f"    Clips    : {len(res.parts)} in {os.path.join(folder, 'audio')}/")


def _maybe_render_long(args, kit, folder) -> None:
    """If --render was requested for a long-form pack, assemble a single
    self-contained MP4 (visuals + voiceover + baked-in captions) plus a matching
    thumbnail.jpg into the pack folder. Never raises."""
    if not getattr(args, "render", False):
        return
    from .render_long import render_long_video
    mp4 = os.path.join(folder, "video.mp4")
    result = render_long_video(
        kit, mp4, folder=folder, music_path=args.music,
        burn_captions=not getattr(args, "no_captions", False),
        make_thumbnail=not getattr(args, "no_thumbnail", False),
    )
    print("\n  Render:", result.message)
    if result.ok:
        print(f"    Upload-ready video: {result.path}")
        thumb = os.path.join(folder, "thumbnail.jpg")
        if os.path.exists(thumb):
            print(f"    Thumbnail        : {thumb}")
        print("    Give it a lookover, then upload with the title/description from seo.md.")


def _run_videopack(args) -> int:
    topic = args.topic
    if not topic:
        from .videopack import build_opportunities
        opps, _ = build_opportunities(args.brand, 5)
        topic = opps[0].topic if opps else get_brand(args.brand).topic_seeds[0]
        print(f"  No topic given; selected the top proposed topic:\n    \"{topic}\"\n")
    try:
        kit = generate(topic, brand_key=args.brand, seconds=_resolve_seconds(args), fmt="long")
    except (KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    out = args.out if args.out != "content_kits" else "video_packs"
    folder = write_kit(kit, out_root=out)
    yt = kit.youtube or {}
    print(f"\n  Video Pack ready: {folder}\n")
    print(f"  Title    : {yt.get('best_title', kit.title)}")
    print(f"  Brand    : {kit.brand_name} ({kit.brand_key})")
    print(f"  Length   : ~{kit.total_seconds / 60:.0f} min across {len(kit.scenes)} beats")
    print(f"  Script by: {kit.generator}")
    _maybe_voiceover(args, kit, folder)
    _maybe_render_long(args, kit, folder)
    print("\n  Open VIDEO_PACK.md for the full, ready-to-produce package.")
    return 0


def _run_weekly(args) -> int:
    from .videopack import write_weekly
    out = args.out if args.out != "content_kits" else "weekly_out"
    try:
        folder = write_weekly(args.brand, out_root=out, seconds=_resolve_seconds(args),
                              voiceover=getattr(args, "voiceover", False),
                              render=getattr(args, "render", False),
                              burn_captions=not getattr(args, "no_captions", False),
                              make_thumbnail=not getattr(args, "no_thumbnail", False))
    except (KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"\n  Weekly bundle ready: {folder}")
    print(f"  - {os.path.join(folder, 'opportunities.md')}  (10 ranked topics)")
    print(f"  - {os.path.join(folder, 'video-pack')}/        (full pack for the top topic)")
    print(f"  - {os.path.join(folder, 'INDEX.md')}")
    return 0


def _run_report(args) -> int:
    from .videopack import write_opportunities
    out = args.out if args.out != "content_kits" else "weekly_out"
    try:
        write_opportunities(args.brand, 10, out_root=out)
    except (KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"\n  Opportunity report ready: {os.path.join(out, 'opportunities.md')}")
    return 0


def _run_autopost(args) -> int:
    """Generate + render the post whose topic maps to today's date."""
    from .calendar import topic_for_date
    from datetime import date

    when = date.today()
    try:
        topic, fmt = topic_for_date(args.brand, when)
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    kit = generate(topic, brand_key=args.brand, seconds=args.duration,
                   point_count=args.points)
    out_dir = args.out if args.out != "content_kits" else "autopost_out"
    os.makedirs(out_dir, exist_ok=True)
    folder = write_kit(kit, out_root=out_dir)

    mp4 = os.path.join(folder, "reel.mp4")
    from .render import render_video
    result = render_video(kit, mp4, with_voiceover=not args.no_voiceover)
    cover = os.path.join(folder, "cover.jpg")
    has_cover = result.ok and os.path.exists(cover)

    # Write caption + a small machine-readable summary for the workflow to read.
    caption_path = os.path.join(folder, "caption.txt")
    with open(caption_path, "w", encoding="utf-8") as fh:
        fh.write(kit.caption)
    summary = {
        "date": when.isoformat(), "brand": kit.brand_key, "topic": topic,
        "format": fmt, "title": kit.title, "kit_folder": folder,
        "video": mp4 if result.ok else None,
        "cover": cover if has_cover else None,
        "caption_file": caption_path,
        "rendered": result.ok,
    }
    summary_path = os.path.join(out_dir, "autopost.json")
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)

    print(f"\n  Today's post ({when.isoformat()}):")
    print(f"  Topic : {topic}")
    print(f"  Title : {kit.title}")
    print(f"  Kit   : {folder}")
    print(f"  Render: {result.message}")
    print(f"  Summary written: {summary_path}")
    # Expose the rendered file paths to GitHub Actions if running there.
    gh_out = os.getenv("GITHUB_OUTPUT")
    if gh_out and result.ok:
        with open(gh_out, "a", encoding="utf-8") as fh:
            fh.write(f"video={mp4}\n")
            fh.write(f"caption_file={caption_path}\n")
            fh.write(f"kit_folder={folder}\n")
            if has_cover:
                fh.write(f"cover={cover}\n")
    return 0 if result.ok else 1


def _resolve_caption(args) -> str:
    if args.caption:
        return args.caption
    if args.caption_file and os.path.exists(args.caption_file):
        with open(args.caption_file, encoding="utf-8") as fh:
            return fh.read().strip()
    if args.kit:
        pkg = os.path.join(args.kit, "content_package.json")
        if os.path.exists(pkg):
            with open(pkg, encoding="utf-8") as fh:
                return str(json.load(fh).get("caption", "")).strip()
    return ""


def _run_publish(args) -> int:
    from .publisher import InstagramPublisher

    ig_user = os.getenv("IG_USER_ID", "").strip()
    token = os.getenv("IG_ACCESS_TOKEN", "").strip()
    caption = _resolve_caption(args)
    video_url = args.video_url

    if args.dry_run or not (ig_user and token and video_url):
        reason = "dry-run requested" if args.dry_run else "missing IG creds or --video-url"
        print(f"  [dry run] not posting ({reason}).")
        print(f"  Would publish Reel:")
        print(f"    video_url : {video_url or '(none provided)'}")
        print(f"    cover_url : {args.cover_url or '(none, IG will auto-pick a frame)'}")
        print(f"    ig_user   : {ig_user or '(IG_USER_ID not set)'}")
        print(f"    token set : {bool(token)}")
        print(f"    caption   :\n{caption[:300]}{'...' if len(caption) > 300 else ''}")
        # Not an error in dry-run mode; lets first-time users see the flow safely.
        return 0 if args.dry_run else 1

    pub = InstagramPublisher(ig_user, token)
    check = pub.verify()
    print(f"  {check.message or check.steps}")
    if not check.ok:
        return 1

    result = pub.publish_reel(video_url, caption, cover_url=args.cover_url)
    for line in result.steps:
        print(f"    - {line}")
    if result.ok:
        print(f"\n  Posted to Instagram. Media id: {result.media_id}")
        return 0
    print(f"\n  Publish failed: {result.message or 'see steps above'}", file=sys.stderr)
    return 1


def _run_refresh_token() -> int:
    from .publisher import refresh_long_lived_token
    app_id = os.getenv("IG_APP_ID", "").strip()
    app_secret = os.getenv("IG_APP_SECRET", "").strip()
    token = os.getenv("IG_ACCESS_TOKEN", "").strip()
    if not (app_id and app_secret and token):
        print("Token refresh skipped: set IG_APP_ID, IG_APP_SECRET and IG_ACCESS_TOKEN.",
              file=sys.stderr)
        return 0  # not an error; refresh is optional
    res = refresh_long_lived_token(app_id, app_secret, token)
    if not res.ok:
        print(f"  {res.message}", file=sys.stderr)
        return 1
    days = f" (~{res.expires_in // 86400} days)" if res.expires_in else ""
    # stdout = ONLY the token (so CI can capture + mask it); humans read stderr.
    print(res.token)
    print(f"Token refreshed{days}.", file=sys.stderr)
    return 0


def _run_verify_instagram() -> int:
    from .publisher import InstagramPublisher
    ig_user = os.getenv("IG_USER_ID", "").strip()
    token = os.getenv("IG_ACCESS_TOKEN", "").strip()
    if not (ig_user and token):
        print("  IG_USER_ID and/or IG_ACCESS_TOKEN are not set.", file=sys.stderr)
        return 1
    res = InstagramPublisher(ig_user, token).verify()
    print(f"  {res.message}" if res.ok else f"  {'; '.join(res.steps)}")
    return 0 if res.ok else 1


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.doctor:
        return _doctor()
    if args.list_brands:
        return _list_brands()
    if args.ideas:
        return _ideas(args.brand)
    if args.verify_instagram:
        return _run_verify_instagram()
    if args.refresh_token:
        return _run_refresh_token()
    if args.autopost:
        return _run_autopost(args)
    if args.publish:
        return _run_publish(args)

    if args.calendar:
        return _run_calendar(args)
    if args.weekly:
        return _run_weekly(args)
    if args.report:
        return _run_report(args)
    if args.videopack:
        return _run_videopack(args)

    if not args.topic:
        build_parser().print_help()
        return 2

    try:
        kit = generate(
            topic=args.topic,
            brand_key=args.brand,
            seconds=_resolve_seconds(args),
            point_count=args.points,
            fmt=_resolve_fmt(args),
        )
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    folder = write_kit(kit, out_root=args.out)

    if kit.format == "long":
        yt = kit.youtube or {}
        print(f"\n  Video Pack ready: {folder}\n")
        print(f"  Title    : {yt.get('best_title', kit.title)}")
        print(f"  Brand    : {kit.brand_name} ({kit.brand_key})")
        print(f"  Length   : ~{kit.total_seconds / 60:.0f} min across {len(kit.scenes)} beats")
        print(f"  Script by: {kit.generator}")
        print(f"  Hook     : {kit.hook}")
        print("\n  Files:")
        for name in ("VIDEO_PACK.md", "titles.md", "script.md", "seo.md", "thumbnails.md",
                     "promotion.md", "captions.srt", "voiceover.txt", "voiceover.ssml",
                     "shotlist.md", "storyboard.html", "content_package.json"):
            print(f"    - {os.path.join(folder, name)}")
        _maybe_voiceover(args, kit, folder)
        _maybe_render_long(args, kit, folder)
        print("\n  Tip: open VIDEO_PACK.md for the full package; storyboard.html previews pacing.")
        return 0

    print(f"\n  Content kit ready: {folder}\n")
    print(f"  Title    : {kit.title}")
    print(f"  Brand    : {kit.brand_name} ({kit.brand_key})")
    print(f"  Length   : ~{kit.total_seconds:.0f}s across {len(kit.scenes)} scenes")
    print(f"  Script by: {kit.generator}")
    print(f"  Hook     : {kit.hook}")
    print("\n  Files:")
    for name in ("storyboard.html", "script.md", "captions.srt", "voiceover.txt",
                 "voiceover.ssml", "post.md", "hashtags.txt", "shotlist.md",
                 "content_package.json"):
        print(f"    - {os.path.join(folder, name)}")
    print("\n  Tip: open storyboard.html in a browser to watch the animated preview.")

    if args.render:
        from .render import render_video
        mp4 = os.path.join(folder, "reel.mp4")
        result = render_video(
            kit, mp4, music_path=args.music,
            with_voiceover=not args.no_voiceover,
        )
        print("\n  Render:", result.message)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
