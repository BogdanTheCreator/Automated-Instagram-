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

import os
import shutil
import subprocess
import tempfile
import urllib.request
from typing import List, Optional

from .brand import Brand, get_brand
from .engine import ContentKit
from .narration import synthesize_narration
from .providers import auto_image, auto_stock, has_ffmpeg
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


def _lower_third(text: str, palette) -> str:
    """A drawtext + drawbox filter chain for a clean lower-third caption."""
    txt = _escape_drawtext(_wrap(text, 42))
    accent = _hex_to_ffmpeg(palette.accent)
    textcol = _hex_to_ffmpeg(palette.text)
    return (
        # translucent band along the bottom third
        f"drawbox=x=0:y=h*0.78:w=iw:h=h*0.22:color=0x000000@0.55:t=fill,"
        f"drawbox=x=0:y=h*0.78:w=iw:h=5:color={accent}:t=fill,"
        f"drawtext=text='{txt}'{_font_clause()}:fontcolor={textcol}:fontsize=52:"
        f"x=(w-text_w)/2:y=h*0.83:line_spacing=10:"
        f"shadowcolor=0x000000:shadowx=3:shadowy=3"
    )


def _beat_background(query: str, idx: int, tmp: str) -> Optional[str]:
    """Best-effort still image for a beat: stock photo / AI art, else None."""
    # 1) Try a stock provider (Pexels). It returns video URLs; we also accept
    #    a photo via the image provider below. Pexels video is heavier, so we
    #    prefer an AI/stock still for a stable Ken-Burns base.
    img = auto_image()
    if getattr(img, "name", "") != "offline-gradient":
        out = os.path.join(tmp, f"bg_{idx:03d}.png")
        made = img.background(query, out)
        if made:
            return made
    # 2) Stock video frame (Pexels) — download and let ffmpeg grab a still.
    stock = auto_stock()
    if getattr(stock, "name", "") == "pexels":
        clip = stock.find(query)
        if clip and clip.url:
            vid = os.path.join(tmp, f"stock_{idx:03d}.mp4")
            if _download(clip.url, vid):
                return vid  # a video; _scene_clip handles both
    return None


def _scene_clip(idx: int, on_screen: str, duration: float, query: str,
                brand: Brand, tmp: str) -> str:
    """Render one beat to an intermediate landscape mp4 and return its path."""
    p = brand.palette
    out = os.path.join(tmp, f"beat_{idx:03d}.mp4")
    duration = max(1.0, round(duration, 2))
    frames = int(duration * FPS)
    bg = _beat_background(query, idx, tmp)
    lower = _lower_third(on_screen, p)

    if bg and bg.endswith(".mp4"):
        # Use the stock video as the base: scale/crop to 16:9, loop/trim to dur.
        vf = (
            f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},"
            f"drawbox=x=0:y=0:w=iw:h=ih:color=0x000000@0.30:t=fill,"
            + lower
        )
        cmd = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", bg, "-t", f"{duration}",
               "-vf", vf, "-r", f"{FPS}", "-an",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", out]
    elif bg:
        # Still image with a slow Ken-Burns zoom.
        vf = (
            f"scale={WIDTH*2}:-1,"
            f"zoompan=z='min(zoom+0.0008,1.12)':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={WIDTH}x{HEIGHT}:fps={FPS},"
            f"drawbox=x=0:y=0:w=iw:h=ih:color=0x000000@0.35:t=fill,"
            + lower
        )
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", bg, "-t", f"{duration}",
               "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", out]
    else:
        # On-brand gradient card with a subtle zoom — no external assets needed.
        base = _hex_to_ffmpeg(p.bg if idx % 2 == 0 else p.bg2)
        vf = (
            f"zoompan=z='min(zoom+0.0006,1.10)':d={frames}:"
            f"s={WIDTH}x{HEIGHT}:fps={FPS},"
            + lower
        )
        cmd = ["ffmpeg", "-y", "-f", "lavfi",
               "-i", f"color=c={base}:s={WIDTH}x{HEIGHT}:d={duration}:r={FPS}",
               "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", f"{duration}", out]

    subprocess.run(cmd, check=True, capture_output=True)
    return out


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
    out = os.path.join(tmp, "video_subs.mp4")
    style = ("FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
             "BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=60")
    srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", video,
             "-vf", f"subtitles='{srt_escaped}':force_style='{style}'",
             "-c:a", "copy", out],
            check=True, capture_output=True,
        )
        return out
    except subprocess.CalledProcessError:
        return video  # best-effort


def render_long_video(
    kit: ContentKit,
    out_path: str,
    folder: Optional[str] = None,
    music_path: Optional[str] = None,
    burn_captions: bool = False,
) -> RenderResult:
    """Assemble a long-form narrated MP4 from a (long-format) ContentKit.

    `folder` is the Video Pack folder; the voiceover is written into
    `<folder>/audio/`. If omitted, a temp folder is used for audio.
    `burn_captions` is off by default — YouTube auto-captions from the audio and
    most storytelling channels prefer a clean frame; pass True to hard-burn.
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
        clips, srt_rows = [], []
        for i, (scene, audio_part) in enumerate(pairs):
            dur = _probe_duration(audio_part) or max(2.0, scene.duration)
            label = scene.on_screen or scene.role.title()
            query = getattr(scene, "broll_query", "") or kit.topic
            clips.append(_scene_clip(i, label, dur, query, brand, tmp))
            srt_rows.append((scene.narration, dur))

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

        mins = (_probe_duration(out_path) or kit.total_seconds) / 60.0
        cap = " + burned captions" if burn_captions else ""
        return RenderResult(
            ok=True, path=out_path,
            message=(f"Rendered {out_path} ({WIDTH}x{HEIGHT} @ {FPS}fps, ~{mins:.1f} min, "
                     f"voice: {narr.engine}{cap})."),
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", "ignore")[-700:]
        return RenderResult(ok=False, path=None, message=f"ffmpeg failed: {detail}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
