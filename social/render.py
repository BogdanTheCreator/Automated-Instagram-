"""
render.py — turn a generated ContentKit into a real vertical MP4 with ffmpeg.

This is the "on your machine" path. In a locked-down sandbox there is no ffmpeg,
so `render_video` detects that and returns a clear, actionable message instead of
failing. On any machine with ffmpeg on PATH it produces a 1080x1920 video:

    * one gradient background segment per scene, in the brand palette
    * the on-screen caption drawn large and centered (drawtext)
    * a subtle zoom (zoompan) for motion
    * optional voiceover (synthesized via providers.auto_tts) mixed under
    * optional background music if you pass --music

If you also have stock b-roll (e.g. Pexels via PEXELS_API_KEY), you can extend
`_scene_clip` to use downloaded clips instead of generated gradients — the shot
list and JSON already carry the search queries.

No third-party Python packages are required; this drives the system ffmpeg
binary through subprocess.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import List, Optional

from .brand import Brand, get_brand
from .engine import ContentKit
from .providers import auto_image, auto_tts, has_ffmpeg

WIDTH, HEIGHT, FPS = 1080, 1920, 30

# Fonts: drawtext is most reliable with an explicit font file. We probe common
# locations across CI / mac / Linux and fall back to ffmpeg's default if none.
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def _find_font() -> Optional[str]:
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def _font_clause() -> str:
    f = _find_font()
    return f":fontfile='{f}'" if f else ""


class RenderResult:
    def __init__(self, ok: bool, path: Optional[str], message: str) -> None:
        self.ok = ok
        self.path = path
        self.message = message

    def __repr__(self) -> str:
        return f"RenderResult(ok={self.ok}, path={self.path!r}, message={self.message!r})"


def _hex_to_ffmpeg(color: str) -> str:
    """'#0B0F1A' -> '0x0B0F1A' for ffmpeg color/lavfi sources."""
    return "0x" + color.lstrip("#")


def _escape_drawtext(text: str) -> str:
    # ffmpeg drawtext needs these escaped.
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\u2019")  # curly apostrophe avoids quoting hell
        .replace("%", "\\%")
    )


def _wrap(text: str, width: int = 18) -> str:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def _scene_clip(idx: int, on_screen: str, duration: float, brand: Brand,
                tmp: str) -> str:
    """Render one scene to an intermediate mp4 and return its path."""
    p = brand.palette
    bg = _hex_to_ffmpeg(p.bg if idx % 2 == 0 else p.bg2)
    txt = _escape_drawtext(_wrap(on_screen))
    out = os.path.join(tmp, f"scene_{idx:03d}.mp4")

    # A gradient-ish background via two blended color sources + zoompan motion.
    vf = (
        f"zoompan=z='min(zoom+0.0015,1.15)':d={int(duration * FPS)}:"
        f"s={WIDTH}x{HEIGHT}:fps={FPS},"
        f"drawtext=text='{txt}'{_font_clause()}:fontcolor={_hex_to_ffmpeg(p.text)}:fontsize=92:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:line_spacing=14:"
        f"box=0:shadowcolor=0x000000:shadowx=4:shadowy=4"
    )
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c={bg}:s={WIDTH}x{HEIGHT}:d={duration}:r={FPS}",
        "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", f"{duration}",
        out,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def _concat(clips: List[str], tmp: str) -> str:
    listfile = os.path.join(tmp, "list.txt")
    with open(listfile, "w", encoding="utf-8") as fh:
        for c in clips:
            fh.write(f"file '{c}'\n")
    out = os.path.join(tmp, "video_only.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile,
         "-c", "copy", out],
        check=True, capture_output=True,
    )
    return out


def _burn_subtitles(video: str, srt_path: str, tmp: str) -> str:
    out = os.path.join(tmp, "video_subs.mp4")
    style = "FontSize=16,PrimaryColour=&H00FFFFFF,Outline=2,Shadow=1,Alignment=2,MarginV=120"
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
        return video  # subtitle burn-in is best-effort


def render_from_package(package_json_path: str, out_path: str,
                        music_path: Optional[str] = None,
                        with_voiceover: bool = True,
                        burn_captions: bool = True) -> RenderResult:
    """Render an MP4 from a previously-written content_package.json file.

    Lets you batch-render a whole month of saved kits without regenerating them
    (used by the Colab notebook and any automation).
    """
    import json
    from .engine import ContentKit
    with open(package_json_path, encoding="utf-8") as fh:
        data = json.load(fh)
    kit = ContentKit.from_dict(data)
    return render_video(kit, out_path, music_path=music_path,
                        with_voiceover=with_voiceover, burn_captions=burn_captions)


def render_cover(kit: ContentKit, out_path: str) -> Optional[str]:
    """Render a premium 1080x1920 cover/thumbnail JPG for the grid.

    Uses AI background art when an image provider is configured (see
    providers.auto_image), otherwise a clean branded gradient. The title is
    drawn on top either way. Best-effort: returns the path or None.
    """
    if not has_ffmpeg():
        return None
    brand = get_brand(kit.brand_key)
    p = brand.palette
    title = _escape_drawtext(_wrap(kit.title, 14))
    handle = _escape_drawtext(brand.handle_ideas[0] if brand.handle_ideas else "")
    badge = _escape_drawtext("SAVE THIS")
    fc = _font_clause()
    tmp = tempfile.mkdtemp(prefix="cover_")
    try:
        bg_img = auto_image().background(kit.title, os.path.join(tmp, "bg.png"))
        common = (
            f"drawtext=text='{badge}'{fc}:fontcolor={_hex_to_ffmpeg(p.accent)}:fontsize=46:"
            f"x=(w-text_w)/2:y=h-300,"
            f"drawtext=text='{title}'{fc}:fontcolor={_hex_to_ffmpeg(p.text)}:fontsize=110:"
            f"x=(w-text_w)/2:y=(h-text_h)/2:line_spacing=18:"
            f"shadowcolor=0x000000:shadowx=4:shadowy=4,"
            f"drawtext=text='{handle}'{fc}:fontcolor={_hex_to_ffmpeg(p.text)}@0.85:fontsize=40:"
            f"x=(w-text_w)/2:y=h-180"
        )
        if bg_img:
            vf = (
                f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={WIDTH}:{HEIGHT},"
                f"drawbox=x=0:y=0:w=iw:h=ih:color=0x000000@0.40:t=fill,"
                + common
            )
            cmd = ["ffmpeg", "-y", "-i", bg_img, "-vf", vf, "-frames:v", "1", out_path]
        else:
            vf = (
                f"drawbox=x=0:y=ih*0.62:w=iw:h=ih*0.38:color={_hex_to_ffmpeg(p.bg2)}@0.85:t=fill,"
                f"drawbox=x=0:y=ih*0.60:w=iw:h=6:color={_hex_to_ffmpeg(p.accent)}:t=fill,"
                + common
            )
            cmd = ["ffmpeg", "-y", "-f", "lavfi",
                   "-i", f"color=c={_hex_to_ffmpeg(p.bg)}:s={WIDTH}x{HEIGHT}",
                   "-vf", vf, "-frames:v", "1", out_path]
        subprocess.run(cmd, check=True, capture_output=True)
        return out_path if os.path.exists(out_path) else None
    except subprocess.CalledProcessError:
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def render_video(
    kit: ContentKit,
    out_path: str,
    music_path: Optional[str] = None,
    with_voiceover: bool = True,
    burn_captions: bool = True,
) -> RenderResult:
    if not has_ffmpeg():
        return RenderResult(
            ok=False, path=None,
            message=(
                "ffmpeg not found on PATH. The full content kit (script, captions, "
                "hashtags, voiceover text, animated storyboard.html preview) was "
                "still generated. To render a real MP4, run this on a machine with "
                "ffmpeg installed:\n"
                "  macOS:  brew install ffmpeg\n"
                "  Ubuntu: sudo apt-get install -y ffmpeg\n"
                "  Windows: winget install Gyan.FFmpeg\n"
                "Then re-run with --render. Meanwhile, open storyboard.html in a "
                "browser to preview the Reel."
            ),
        )

    brand = get_brand(kit.brand_key)
    tmp = tempfile.mkdtemp(prefix="reel_")
    try:
        clips = [
            _scene_clip(s.index, s.on_screen, max(1.0, s.duration), brand, tmp)
            for s in kit.scenes
        ]
        video = _concat(clips, tmp)

        if burn_captions:
            srt = os.path.join(tmp, "captions.srt")
            with open(srt, "w", encoding="utf-8") as fh:
                fh.write(kit.srt)
            video = _burn_subtitles(video, srt, tmp)

        audio = None
        if with_voiceover:
            tts = auto_tts()
            vo = os.path.join(tmp, "vo.mp3")
            audio = tts.synthesize(kit.voiceover_text, vo, brand.tts_voice)

        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

        if audio or music_path:
            cmd = ["ffmpeg", "-y", "-i", video]
            inputs = 1
            if audio:
                cmd += ["-i", audio]; inputs += 1
            if music_path:
                cmd += ["-i", music_path]; inputs += 1
            if audio and music_path:
                cmd += ["-filter_complex",
                        "[1:a]volume=1.0[vo];[2:a]volume=0.18[bg];"
                        "[vo][bg]amix=inputs=2:duration=longest[a]",
                        "-map", "0:v", "-map", "[a]"]
            else:
                cmd += ["-map", "0:v", "-map", "1:a"]
            cmd += ["-c:v", "copy", "-c:a", "aac", "-shortest", out_path]
            subprocess.run(cmd, check=True, capture_output=True)
        else:
            shutil.copy(video, out_path)

        # Best-effort: also produce a branded cover/thumbnail next to the video.
        cover_msg = ""
        try:
            cover = render_cover(kit, os.path.join(os.path.dirname(os.path.abspath(out_path)), "cover.jpg"))
            if cover:
                cover_msg = " + cover.jpg"
        except Exception:
            pass

        return RenderResult(ok=True, path=out_path,
                            message=f"Rendered {out_path} ({WIDTH}x{HEIGHT} @ {FPS}fps){cover_msg}.")
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", "ignore")[-600:]
        return RenderResult(ok=False, path=None, message=f"ffmpeg failed: {detail}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
