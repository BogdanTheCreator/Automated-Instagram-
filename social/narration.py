"""
narration.py — turn a long-form Video Pack's script into voiceover audio.

This is the "(A) automatic voiceover" step. Given a generated ContentKit (or a
saved content_package.json), it synthesizes the narration to MP3 using whatever
TTS engine is available, picked by `providers.auto_tts()`:

    ELEVENLABS_API_KEY set      -> premium ElevenLabs voice
    `edge-tts` installed        -> free, high-quality neural voice (no key)
    neither                     -> OfflineTTS: no audio engine

It writes, under `<kit_folder>/audio/`:
    * one MP3 per narration beat   (e.g. 00_hook.mp3, 01_setup.mp3, ...) so a
      faceless editor can drop each section onto its matching b-roll, and
    * narration.mp3                a single combined track of the whole video
      (concatenated with ffmpeg when present; otherwise the per-beat files are
      still produced and can be combined in any editor),
    * INDEX.md                     a human-readable map of beat -> file -> text.

Everything fails soft: with no engine or no internet it writes INDEX.md
explaining exactly how to enable audio, and never raises. No third-party Python
package is required by this module itself (edge-tts, if used, is invoked as a
CLI through the existing provider).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional

from .brand import get_brand
from .engine import ContentKit
from .providers import auto_tts, has_ffmpeg


@dataclass
class NarrationResult:
    ok: bool                       # at least one audio file was produced
    engine: str                    # which TTS engine was used (or "offline-none")
    parts: List[str]               # per-beat audio file paths (in order)
    combined: Optional[str]        # path to narration.mp3 if it was built
    message: str                   # human-readable summary / guidance


def _slug(text: str, n: int = 24) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:n].rstrip("-")) or "beat"


def _concat_audio(parts: List[str], out_path: str) -> Optional[str]:
    """Concatenate MP3 parts into one file using ffmpeg's concat demuxer.

    edge-tts / ElevenLabs both emit MPEG audio, so a stream copy is safe and
    fast. Returns the combined path, or None if ffmpeg is unavailable/fails.
    """
    if not has_ffmpeg() or not parts:
        return None
    listfile = out_path + ".list.txt"
    try:
        with open(listfile, "w", encoding="utf-8") as fh:
            for p in parts:
                # concat demuxer needs absolute paths, single-quoted.
                ap = os.path.abspath(p).replace("'", "'\\''")
                fh.write(f"file '{ap}'\n")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile,
             "-c", "copy", out_path],
            check=True, capture_output=True, timeout=180,
        )
        return out_path if os.path.exists(out_path) else None
    except Exception:
        # Fallback: try a re-encode (handles odd headers between parts).
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile,
                 "-c:a", "libmp3lame", "-q:a", "2", out_path],
                check=True, capture_output=True, timeout=300,
            )
            return out_path if os.path.exists(out_path) else None
        except Exception:
            return None
    finally:
        if os.path.exists(listfile):
            os.remove(listfile)


def synthesize_narration(kit: ContentKit, folder: str,
                         combine: bool = True) -> NarrationResult:
    """Synthesize per-beat MP3s (+ a combined narration.mp3) into folder/audio.

    Never raises. If no TTS engine is available, writes guidance to INDEX.md and
    returns ok=False so callers can report it cleanly.
    """
    audio_dir = os.path.join(folder, "audio")
    os.makedirs(audio_dir, exist_ok=True)
    brand = get_brand(kit.brand_key)
    voice_hint = getattr(brand, "tts_voice", "") or ""
    tts = auto_tts()

    beats = [s for s in kit.scenes if getattr(s, "narration", "").strip()]
    parts: List[str] = []
    index_rows: List[str] = []

    if getattr(tts, "available", False):
        for i, scene in enumerate(beats):
            name = f"{i:02d}_{_slug(getattr(scene, 'role', '') or getattr(scene, 'on_screen', ''))}.mp3"
            out = os.path.join(audio_dir, name)
            made = tts.synthesize(scene.narration, out, voice_hint)
            if made:
                parts.append(made)
                index_rows.append(f"| {i:02d} | `{name}` | {getattr(scene, 'role', '')} | "
                                  f"{_first_sentence(scene.narration)} |")
            else:
                index_rows.append(f"| {i:02d} | _(failed)_ | {getattr(scene, 'role', '')} | "
                                  f"{_first_sentence(scene.narration)} |")

    combined = None
    if combine and len(parts) > 1:
        combined = _concat_audio(parts, os.path.join(audio_dir, "narration.mp3"))
    elif len(parts) == 1:
        # Single part: just copy it to the canonical name.
        combined = os.path.join(audio_dir, "narration.mp3")
        shutil.copyfile(parts[0], combined)

    _write_index(audio_dir, kit, tts, parts, combined, index_rows)

    if not getattr(tts, "available", False):
        return NarrationResult(
            ok=False, engine=tts.name, parts=[], combined=None,
            message=("No TTS engine available — wrote audio/INDEX.md with setup steps. "
                     "Enable free voiceover with `pip install edge-tts`, or set "
                     "ELEVENLABS_API_KEY for premium voices."),
        )
    if not parts:
        return NarrationResult(
            ok=False, engine=tts.name, parts=[], combined=None,
            message=(f"TTS engine '{tts.name}' was available but produced no audio "
                     "(often no internet access for the voice service). See audio/INDEX.md."),
        )
    where = combined or parts[0]
    note = "" if combined else " (per-beat files only; install ffmpeg to merge into one)"
    return NarrationResult(
        ok=True, engine=tts.name, parts=parts, combined=combined,
        message=f"Voiceover ready via {tts.name}: {len(parts)} beats -> {where}{note}",
    )


def _first_sentence(text: str, limit: int = 80) -> str:
    t = " ".join(text.split())
    m = re.split(r"(?<=[.!?])\s", t, maxsplit=1)
    s = m[0] if m else t
    return (s[:limit].rstrip() + "…") if len(s) > limit else s


def _write_index(audio_dir: str, kit: ContentKit, tts, parts, combined, rows) -> None:
    lines = [
        f"# Voiceover — {kit.title}",
        "",
        f"*TTS engine:* `{tts.name}`  ·  *Voice hint:* "
        f"`{getattr(get_brand(kit.brand_key), 'tts_voice', '')}`",
        "",
    ]
    if getattr(tts, "available", False) and parts:
        lines += [
            f"Generated **{len(parts)}** narration clips"
            + (f" and a combined **`narration.mp3`**." if combined else
               " (install `ffmpeg` to auto-merge them into one `narration.mp3`)."),
            "",
            "Drop each clip onto its matching b-roll (see `../shotlist.md`), or use the "
            "single combined track and cut visuals over it.",
            "",
            "| # | File | Beat | Narration (start) |",
            "|---|------|------|-------------------|",
            *rows,
        ]
    else:
        lines += [
            "## No audio was generated",
            "",
            "The voiceover step ran but no TTS engine was active (or it had no network "
            "access). The full text is in `../voiceover.txt` and `../voiceover.ssml`.",
            "",
            "### Enable automatic voiceover",
            "- **Free (recommended):** `pip install edge-tts` — high-quality neural "
            "voices, no API key. Re-run with `--voiceover`.",
            "- **Premium:** set `ELEVENLABS_API_KEY` (and optionally `ELEVENLABS_VOICE_ID`).",
            "",
            "Then re-run, e.g.:",
            "",
            "```bash",
            f'python -m social.cli "{kit.topic}" --brand {kit.brand_key} --voiceover',
            "```",
        ]
    with open(os.path.join(audio_dir, "INDEX.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
