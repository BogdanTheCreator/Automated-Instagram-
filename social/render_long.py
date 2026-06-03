"""
render_long.py — assemble a long-form Video Pack into an upload-ready MP4.

This is the "final product" step for YouTube storytelling videos. Unlike
`render.py` (vertical 1080x1920 Reels with one big caption per scene), this
builds a **landscape 1920x1080** narrated video whose visuals are driven by the
**actual voiceover audio**: each story beat is on screen for exactly as long as
its narration clip plays.

Pipeline (all best-effort, fails soft):

    1. Voiceover — reuse social.narration.synthesize_narration() to get one MP3
       per beat (00_hook.mp3, ...) plus a combined narration.mp3.
    2. Per-beat duration — ffprobe each clip for its real length; fall back to
       the scene's scripted duration when probing isn't possible.
    3. Per-beat visual — a background (Pexels photo / AI image if keys are set,
       else an on-brand gradient) with a slow Ken-Burns zoom and a lower-third
       caption showing the section label.
    4. Concatenate the beat clips, mux the combined narration (+ optional music),
       and optionally burn the resynced captions.

Requires the system `ffmpeg`/`ffprobe` binaries (driven via subprocess); no
third-party Python packages. With no ffmpeg, returns a clear, actionable
message and never raises — the text pack and audio are still produced upstream.
"""
from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
import urllib.request
from typing import List, Optional

from .brand import Brand, get_brand
from .engine import ContentKit
from .narration import synthesize_narration
from .providers import auto_image, auto_photos, auto_stock, has_ffmpeg
# Reuse the battle-tested helpers from the short-form renderer.
from .render import (
    RenderResult,
    _escape_drawtext,
    _font_clause,
    _hex_to_ffmpeg,
    _wrap,
)

WIDTH, HEIGHT, FPS = 1920, 1080, 30


def _has_ffprobe() -> bool:
    return shutil.which("ffprobe") is not None


_DRAWTEXT_CACHE: Optional[bool] = None


def _has_drawtext() -> bool:
    """True if this ffmpeg build registers the `drawtext` filter (needs
    libfreetype). Some static builds omit it; we degrade gracefully when so."""
    global _DRAWTEXT_CACHE
    if _DRAWTEXT_CACHE is not None:
        return _DRAWTEXT_CACHE
    _DRAWTEXT_CACHE = False
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"],
                             capture_output=True, timeout=30)
        _DRAWTEXT_CACHE = b" drawtext " in out.stdout
    except Exception:
        _DRAWTEXT_CACHE = False
    return _DRAWTEXT_CACHE


def _probe_duration(path: str) -> Optional[float]:
    """Return the duration of an audio/video file in seconds, or None."""
    if not path or not os.path.exists(path) or not _has_ffprobe():
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            check=True, capture_output=True, timeout=30,
        )
        return float(out.stdout.decode("utf-8", "ignore").strip())
    except Exception:
        return None


def _download(url: str, out_path: str, timeout: int = 60) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(out_path, "wb") as fh:
            shutil.copyfileobj(resp, fh)
        return out_path if os.path.exists(out_path) and os.path.getsize(out_path) > 0 else None
    except Exception:
        return None


def _lower_third(text: str, palette, draw_label: bool = True) -> str:
    """A drawbox lower-third band, optionally with a section-label caption.

    The band serves as a readable backdrop for the burned-in narration
    subtitles. When `draw_label` is False (the default render path, where the
    spoken narration is burned in as captions), we draw ONLY the band — drawing
    the label too would stack a second line of text on top of the captions
    (the "double captions" problem). When True (captions disabled), the label
    becomes the single on-screen text.

    Uses literal pixel coordinates (some ffmpeg builds reject `h*0.78`-style
    expressions inside drawbox).
    """
    band_y = int(HEIGHT * 0.78)          # 842 on 1080
    band_h = HEIGHT - band_y             # 238
    accent = _hex_to_ffmpeg(palette.accent)
    band = (f"drawbox=x=0:y={band_y}:w={WIDTH}:h={band_h}:color=0x000000@0.55:t=fill,"
            f"drawbox=x=0:y={band_y}:w={WIDTH}:h=5:color={accent}:t=fill")
    if not draw_label or not _has_drawtext():
        return band + ",format=yuv420p"
    txt = _escape_drawtext(_wrap(text, 42))
    textcol = _hex_to_ffmpeg(palette.text)
    return (
        band + ","
        f"drawtext=text='{txt}'{_font_clause()}:fontcolor={textcol}:fontsize=52:"
        f"x=(w-text_w)/2:y={int(HEIGHT * 0.83)}:line_spacing=10:"
        f"shadowcolor=0x000000:shadowx=3:shadowy=3,format=yuv420p"
    )


def _beat_images(query: str, idx: int, tmp: str, want: int):
    """Fetch up to `want` relevant still images for a beat, in priority order:

      1. Stock photos (Pexels if keyed, else no-key Openverse/Wikimedia) — the
         main path for "show what's being talked about".
      2. A single AI-generated image (OPENAI_API_KEY).
      3. A frame grabbed from a Pexels stock video.

    Returns (paths, source): a list of local image file paths (possibly empty ->
    caller uses the on-brand gradient card) and a short source label for
    diagnostics. All best-effort; never raises.
    """
    want = max(1, want)
    paths: List[str] = []

    # 1) Stock photos. Works with ANY non-offline provider (incl. the tiered
    #    no-key sources), not just Pexels — this is what makes images appear
    #    out of the box.
    photos = auto_photos()
    if getattr(photos, "name", "") != "offline-none":
        tried = [query] + [q for q in _FALLBACK_QUERIES if q != query]
        for attempt in tried:
            try:
                urls = photos.search(attempt, count=want, orientation="landscape")
            except Exception:
                urls = []
            for j, url in enumerate(urls):
                dst = os.path.join(tmp, f"img_{idx:03d}_{j:02d}.jpg")
                if _download(url, dst):
                    paths.append(dst)
            if paths:
                src = getattr(photos, "last_source", getattr(photos, "name", "photos"))
                # Note when we had to use a generic fallback query.
                if attempt != query:
                    src = f"{src}~"
                return paths, src

    # 2) AI background art (single image).
    img = auto_image()
    if getattr(img, "name", "") != "offline-gradient":
        dst = os.path.join(tmp, f"img_{idx:03d}_ai.png")
        made = img.background(query, dst)
        if made:
            return [made], "ai-image"

    # 3) Stock video frame as a still.
    stock = auto_stock()
    if getattr(stock, "name", "") == "pexels":
        clip = stock.find(query, orientation="landscape") if _accepts_orientation(stock) else stock.find(query)
        if clip and clip.url:
            vid = os.path.join(tmp, f"stock_{idx:03d}.mp4")
            if _download(clip.url, vid):
                frame = os.path.join(tmp, f"frame_{idx:03d}.jpg")
                try:
                    subprocess.run(["ffmpeg", "-y", "-i", vid, "-frames:v", "1", frame],
                                   check=True, capture_output=True, timeout=60)
                    if os.path.exists(frame):
                        return [frame], "pexels-video-frame"
                except Exception:
                    pass
    return paths, "gradient"


def _accepts_orientation(stock) -> bool:
    """PexelsStock.find now takes an orientation kwarg; guard for older shims."""
    try:
        import inspect
        return "orientation" in inspect.signature(stock.find).parameters
    except (TypeError, ValueError):
        return False


def _kenburns_clip(image: str, duration: float, idx: int, sub: int,
                   lower: str, tmp: str) -> str:
    """Render a single image into a `duration`s Ken-Burns landscape clip."""
    out = os.path.join(tmp, f"kb_{idx:03d}_{sub:02d}.mp4")
    frames = max(1, int(round(duration * FPS)))
    # Alternate zoom-in / gentle pan direction for variety across images.
    if sub % 2 == 0:
        zexpr = "min(zoom+0.0009,1.15)"
    else:
        zexpr = "if(lte(zoom,1.0),1.15,max(1.0,zoom-0.0009))"
    vf = (
        f"scale={WIDTH * 2}:-1,"
        f"zoompan=z='{zexpr}':d={frames}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={WIDTH}x{HEIGHT}:fps={FPS},"
        f"drawbox=x=0:y=0:w={WIDTH}:h={HEIGHT}:color=0x000000@0.35:t=fill,"
        + lower
    )
    cmd = ["ffmpeg", "-y", "-loop", "1", "-i", image, "-t", f"{duration:.2f}",
           "-vf", vf, "-r", f"{FPS}", "-c:v", "libx264", "-pix_fmt", "yuv420p", out]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def _scene_clip(idx: int, on_screen: str, duration: float, query: str,
                brand: Brand, tmp: str, draw_label: bool = False):
    """Render one beat to an intermediate landscape mp4.

    If relevant images are available, the beat becomes a short slideshow of
    those images (one Ken-Burns sub-clip each), so viewers see pictures of what
    is being narrated. Otherwise it falls back to an on-brand gradient card.

    Returns (out_path, source_label) for diagnostics.
    """
    p = brand.palette
    out = os.path.join(tmp, f"beat_{idx:03d}.mp4")
    duration = max(1.0, round(duration, 2))
    lower = _lower_third(on_screen, p, draw_label=draw_label)

    # Aim for one fresh image roughly every ~5s of narration (min 1, cap 4).
    want = max(1, min(4, int(math.ceil(duration / 5.0))))
    images, source = _beat_images(query, idx, tmp, want)

    if images:
        # Split the beat duration evenly across the available images and build a
        # Ken-Burns clip for each, then concatenate them into the beat clip.
        n = len(images)
        per = max(1.5, round(duration / n, 2))
        subclips = []
        for j, img in enumerate(images):
            try:
                subclips.append(_kenburns_clip(img, per, idx, j, lower, tmp))
            except subprocess.CalledProcessError:
                continue  # skip a bad image rather than fail the whole beat
        if subclips:
            if len(subclips) == 1:
                shutil.move(subclips[0], out)
            else:
                beat_list = os.path.join(tmp, f"beat_{idx:03d}.txt")
                with open(beat_list, "w", encoding="utf-8") as fh:
                    for c in subclips:
                        fh.write(f"file '{os.path.abspath(c)}'\n")
                subprocess.run(
                    ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", beat_list,
                     "-c", "copy", out],
                    check=True, capture_output=True,
                )
            return out, f"{source}x{len(subclips)}"

    # Fallback: on-brand gradient card (no external assets). Use the `gradients`
    # SOURCE filter (zoompan on a synthetic source errors on some ffmpeg builds).
    base = _hex_to_ffmpeg(p.bg)
    base2 = _hex_to_ffmpeg(p.bg2 if idx % 2 == 0 else
                           p.accent2 if hasattr(p, "accent2") else p.bg2)
    src = (f"gradients=s={WIDTH}x{HEIGHT}:c0={base}:c1={base2}:"
           f"x0=0:y0=0:x1={WIDTH}:y1={HEIGHT}:d={duration}:r={FPS}")
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", src,
           "-vf", lower, "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-t", f"{duration}", out]
    subprocess.run(cmd, check=True, capture_output=True)
    return out, "gradient"


def _concat(clips: List[str], tmp: str) -> str:
    listfile = os.path.join(tmp, "list.txt")
    with open(listfile, "w", encoding="utf-8") as fh:
        for c in clips:
            fh.write(f"file '{os.path.abspath(c)}'\n")
    out = os.path.join(tmp, "video_only.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile,
         "-c", "copy", out],
        check=True, capture_output=True,
    )
    return out


def _resynced_srt(scenes_durations: List[tuple], tmp: str) -> str:
    """Build an SRT whose timings match the actual per-beat audio durations."""
    def ts(t: float) -> str:
        h = int(t // 3600); m = int((t % 3600) // 60)
        s = int(t % 60); ms = int(round((t - int(t)) * 1000))
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines, t = [], 0.0
    for i, (text, dur) in enumerate(scenes_durations, start=1):
        start, end = t, t + dur
        lines += [str(i), f"{ts(start)} --> {ts(end)}", text.strip(), ""]
        t = end
    path = os.path.join(tmp, "resynced.srt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return path


def _burn_subtitles(video: str, srt_path: str, tmp: str) -> str:
    """Hard-burn captions using the libass `subtitles` filter (independent of
    drawtext, so this works even on builds without libfreetype). The input
    `video` has no audio yet, so no audio handling is needed here."""
    out = os.path.join(tmp, "video_subs.mp4")
    style = ("FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
             "BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=60")
    # ffmpeg's subtitles filter parses ':' inside the path; escape it.
    srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", video,
             "-vf", f"subtitles='{srt_escaped}':force_style='{style}'",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", out],
            check=True, capture_output=True,
        )
        return out if os.path.exists(out) else video
    except subprocess.CalledProcessError:
        return video  # best-effort: ship the video without burned captions


# --------------------------------------------------------------------------- #
# Thumbnail
# --------------------------------------------------------------------------- #

THUMB_W, THUMB_H = 1280, 720  # YouTube's recommended thumbnail size


def _pick_overlay(kit: ContentKit, brand: Brand) -> str:
    """Choose the short, punchy overlay phrase for the thumbnail."""
    overlays = getattr(brand, "thumbnail_overlays", None) or []
    if overlays:
        seed = sum(ord(c) for c in kit.topic)
        return overlays[seed % len(overlays)]
    # Fallback: first two impactful words of the title, upper-cased.
    words = [w for w in kit.title.split() if len(w) > 2][:2]
    return (" ".join(words) or kit.title[:14]).upper()


def _thumb_background(kit: ContentKit, tmp: str) -> Optional[str]:
    """Landscape background art for the thumbnail (AI if available, else None)."""
    img = auto_image()
    if getattr(img, "name", "") != "offline-gradient":
        out = os.path.join(tmp, "thumb_bg.png")
        # Bias the prompt toward the niche mood for a cohesive cover.
        made = img.background(f"{kit.topic}, dramatic cinematic, dark moody", out)
        if made:
            return made
    return None


def render_thumbnail(kit: ContentKit, out_path: str,
                     brand: Optional[Brand] = None) -> RenderResult:
    """Generate a 1280x720 thumbnail.jpg: bold overlay text over AI art or an
    on-brand gradient. Best-effort; returns ok=False with a message on failure."""
    if not has_ffmpeg():
        return RenderResult(ok=False, path=None,
                            message="ffmpeg not found — thumbnail not generated.")
    brand = brand or get_brand(kit.brand_key)
    p = brand.palette
    overlay = _pick_overlay(kit, brand)
    main = _escape_drawtext(_wrap(overlay, 16))
    series = _escape_drawtext((kit.series_name or brand.display_name).upper())
    accent = _hex_to_ffmpeg(p.accent)
    accent2 = _hex_to_ffmpeg(getattr(p, "accent2", p.accent))
    textcol = _hex_to_ffmpeg(p.text)

    tmp = tempfile.mkdtemp(prefix="vpthumb_")
    try:
        bg = _thumb_background(kit, tmp)
        has_text = _has_drawtext()
        # Big, bold, high-contrast title text with a heavy shadow; a left accent
        # bar and a small series kicker. Reads clearly at small sizes on mobile.
        # When drawtext is unavailable we still emit a styled background with the
        # accent bar so the thumbnail is usable (text can be added in any editor).
        text_layers = ""
        if has_text:
            text_layers = (
                f",drawtext=text='{series}'{_font_clause()}:fontcolor={accent2}:fontsize=44:"
                f"x=70:y=64:shadowcolor=0x000000:shadowx=2:shadowy=2"
                f",drawtext=text='{main}'{_font_clause()}:fontcolor={textcol}:fontsize=150:"
                f"x=70:y=(h-text_h)/2+30:line_spacing=12:"
                f"shadowcolor=0x000000:shadowx=5:shadowy=5"
            )
        draw = (
            # darken for text legibility
            f"drawbox=x=0:y=0:w=iw:h=ih:color=0x000000@0.45:t=fill,"
            # left accent bar
            f"drawbox=x=0:y=0:w=18:h=ih:color={accent}:t=fill"
            + text_layers
        )
        if bg:
            vf = (f"scale={THUMB_W}:{THUMB_H}:force_original_aspect_ratio=increase,"
                  f"crop={THUMB_W}:{THUMB_H}," + draw)
            cmd = ["ffmpeg", "-y", "-i", bg, "-vf", vf, "-frames:v", "1", out_path]
        else:
            base = _hex_to_ffmpeg(p.bg)
            base2 = _hex_to_ffmpeg(p.bg2)
            # `gradients` is a source filter: use it as the lavfi INPUT, then
            # draw text/boxes over it. (Falls back to a flat color below if an
            # older ffmpeg lacks the gradients source.)
            cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i",
                   f"gradients=s={THUMB_W}x{THUMB_H}:c0={base}:c1={base2}:"
                   f"x0=0:y0=0:x1={THUMB_W}:y1={THUMB_H}",
                   "-frames:v", "1", "-vf", draw, out_path]
        subprocess.run(cmd, check=True, capture_output=True)
        if os.path.exists(out_path):
            return RenderResult(ok=True, path=out_path,
                                message=f"Thumbnail: {out_path} (overlay: \"{overlay}\").")
        return RenderResult(ok=False, path=None, message="Thumbnail render produced no file.")
    except subprocess.CalledProcessError:
        # gradients filter may be unavailable on very old ffmpeg — retry flat.
        try:
            base = _hex_to_ffmpeg(p.bg)
            cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i",
                   f"color=c={base}:s={THUMB_W}x{THUMB_H}", "-frames:v", "1",
                   "-vf", draw, out_path]
            subprocess.run(cmd, check=True, capture_output=True)
            return RenderResult(ok=True, path=out_path,
                                message=f"Thumbnail (flat bg): {out_path}.")
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or b"").decode("utf-8", "ignore")[-300:]
            return RenderResult(ok=False, path=None, message=f"Thumbnail failed: {detail}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Per-beat image search queries + diagnostics
# --------------------------------------------------------------------------- #

# Stock libraries respond far better to concrete, cinematic scene descriptions
# than to abstract phrases like "a sibling who stole an inheritance". Map each
# story-arc beat role to a visually-searchable term. (Roles come from
# engine.STORY_ARC.) Falls back to the scene's own b-roll query / topic.
_BEAT_QUERY_BY_ROLE = {
    "hook":          "dark cinematic silhouette",
    "setup":         "quiet home morning light",
    "trust":         "friends laughing together",
    "first_crack":   "smartphone screen night",
    "suspicion":     "rainy window",
    "betrayal":      "rain window night",
    "fallout":       "empty room lamp",
    "decision":      "serious eyes closeup",
    "plan":          "documents desk",
    "escalation":    "dinner table candlelight",
    "turning_point": "empty meeting room",
    "payoff":        "open door daylight",
    "aftermath":     "walking away street sunset",
    "reflection":    "calm sunrise horizon",
    "cta":           "dark moody background",
    # short-form/value roles (harmless if unused here):
    "context":       "cinematic establishing shot",
    "point":         "abstract background",
}

# Generic, high-recall fallbacks tried (in order) when a beat's specific query
# returns nothing — so beats almost always get a relevant-ish image rather than
# a flat gradient.
_FALLBACK_QUERIES = ["cinematic moody", "dark abstract background", "night city lights"]


def _beat_query(scene, topic: str) -> str:
    """Pick a visually-searchable query for a beat: curated by role first, then
    the scene's own b-roll phrase, then the topic."""
    role = getattr(scene, "role", "") or ""
    curated = _BEAT_QUERY_BY_ROLE.get(role)
    if curated:
        return curated
    return getattr(scene, "broll_query", "") or topic


def _write_render_log(out_path: str, kit: ContentKit, sources, img_beats: int,
                      total: int) -> None:
    """Write RENDER_LOG.md next to the video so the user can SEE, per beat,
    which image source was used (or why it fell back to a gradient)."""
    folder = os.path.dirname(os.path.abspath(out_path))
    lines = [
        f"# Render log — {kit.title}",
        "",
        f"**Imagery:** {img_beats} of {total} beats used real stock photos; "
        f"{total - img_beats} fell back to gradient cards.",
        "",
    ]
    if img_beats == 0:
        lines += [
            "> No stock images were fetched for any beat. Likely causes:",
            "> - No network access during the run, or the image sources were rate-limited.",
            "> - `NO_STOCK_IMAGES` is set.",
            "> Set `PEXELS_API_KEY` (free) for the most reliable, highest-quality images.",
            "",
        ]
    lines += ["| # | Beat | Search query | Image source |",
              "|---|------|--------------|--------------|"]
    for i, (role, query, src) in enumerate(sources):
        lines.append(f"| {i} | {role} | {query} | {src} |")
    lines.append("")
    try:
        with open(os.path.join(folder, "RENDER_LOG.md"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
    except OSError:
        pass


def render_long_video(
    kit: ContentKit,
    out_path: str,
    folder: Optional[str] = None,
    music_path: Optional[str] = None,
    burn_captions: bool = True,
    make_thumbnail: bool = True,
) -> RenderResult:
    """Assemble a long-form narrated MP4 from a (long-format) ContentKit.

    `folder` is the Video Pack folder; the voiceover is written into
    `<folder>/audio/`. If omitted, a temp folder is used for audio.
    `burn_captions` defaults to True so the MP4 is a single, self-contained,
    upload-ready file (captions baked in). `make_thumbnail` also writes a
    matching `thumbnail.jpg` next to the video.
    """
    if getattr(kit, "format", "short") != "long":
        return RenderResult(ok=False, path=None,
                            message="render_long_video expects a long-format Video Pack "
                                    "(use render.render_video for short-form Reels).")
    if not has_ffmpeg():
        return RenderResult(
            ok=False, path=None,
            message=(
                "ffmpeg not found on PATH — the MP4 was not assembled. Your full Video "
                "Pack (script, SEO, thumbnails, voiceover text) was still generated. To "
                "build the video, run on a machine with ffmpeg:\n"
                "  macOS:  brew install ffmpeg\n"
                "  Ubuntu: sudo apt-get install -y ffmpeg\n"
                "  Windows: winget install Gyan.FFmpeg\n"
                "Then re-run with --render. (The weekly GitHub Action installs ffmpeg "
                "automatically, so its artifact can include the MP4.)"
            ),
        )

    brand = get_brand(kit.brand_key)
    audio_folder = folder or tempfile.mkdtemp(prefix="vpaudio_")
    # 1) Voiceover — per-beat clips + combined track (reuses the audio module).
    narr = synthesize_narration(kit, audio_folder)
    if not narr.ok or not narr.combined:
        return RenderResult(
            ok=False, path=None,
            message=("No voiceover audio available, so the video can't be timed to "
                     f"narration. {narr.message} "
                     "Enable free voiceover with `pip install edge-tts` and re-run."),
        )

    # Map each produced audio part to its scene (parts are in beat order, and
    # synthesize_narration filters to scenes with narration — same ordering).
    narrated = [s for s in kit.scenes if getattr(s, "narration", "").strip()]
    pairs = list(zip(narrated, narr.parts))

    tmp = tempfile.mkdtemp(prefix="vplong_")
    try:
        clips, srt_rows, sources = [], [], []
        # If we're burning narration captions, don't also draw the per-beat
        # section label (that would stack two text layers = "double captions").
        # When captions are off, the label becomes the single on-screen text.
        draw_label = not burn_captions
        for i, (scene, audio_part) in enumerate(pairs):
            dur = _probe_duration(audio_part) or max(2.0, scene.duration)
            label = scene.on_screen or scene.role.title()
            query = _beat_query(scene, kit.topic)
            clip, src = _scene_clip(i, label, dur, query, brand, tmp,
                                    draw_label=draw_label)
            clips.append(clip)
            sources.append((getattr(scene, "role", f"beat{i}"), query, src))
            srt_rows.append((scene.narration, dur))

        # Diagnostics: write a render log + count how many beats got real images.
        img_beats = sum(1 for _, _, s in sources if s != "gradient")
        _write_render_log(out_path, kit, sources, img_beats, len(sources))

        video = _concat(clips, tmp)

        if burn_captions:
            srt = _resynced_srt(srt_rows, tmp)
            video = _burn_subtitles(video, srt, tmp)

        os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)

        cmd = ["ffmpeg", "-y", "-i", video, "-i", narr.combined]
        if music_path and os.path.exists(music_path):
            cmd += ["-stream_loop", "-1", "-i", music_path,
                    "-filter_complex",
                    "[1:a]volume=1.0[vo];[2:a]volume=0.10[bg];"
                    "[vo][bg]amix=inputs=2:duration=first[a]",
                    "-map", "0:v", "-map", "[a]"]
        else:
            cmd += ["-map", "0:v", "-map", "1:a"]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                "-shortest", out_path]
        subprocess.run(cmd, check=True, capture_output=True)

        # 4) Matching thumbnail next to the video.
        thumb_msg = ""
        if make_thumbnail:
            thumb_path = os.path.join(os.path.dirname(os.path.abspath(out_path)),
                                      "thumbnail.jpg")
            tres = render_thumbnail(kit, thumb_path, brand)
            thumb_msg = f"  {tres.message}" if tres.ok else f"  (thumbnail skipped: {tres.message})"

        mins = (_probe_duration(out_path) or kit.total_seconds) / 60.0
        cap = " + captions baked in" if burn_captions else ""
        imagery = (f"imagery: {img_beats}/{len(sources)} beats from stock photos"
                   if img_beats else
                   "imagery: gradient cards (no stock images found — see RENDER_LOG.md)")
        return RenderResult(
            ok=True, path=out_path,
            message=(f"Rendered {out_path} ({WIDTH}x{HEIGHT} @ {FPS}fps, ~{mins:.1f} min, "
                     f"voice: {narr.engine}{cap}; {imagery}).{thumb_msg}"),
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", "ignore")[-700:]
        return RenderResult(ok=False, path=None, message=f"ffmpeg failed: {detail}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
