"""
social — a faceless short-form content engine.

Turn a single prompt into a complete, premium Instagram Reels / TikTok / YouTube
Shorts content kit: script, scene-by-scene storyboard, burned-in caption file
(.srt), an Instagram post caption, a tiered hashtag strategy, a TTS-ready
voiceover (plain + SSML), a shot list, machine-readable JSON, and a
browser-playable animated 9:16 preview of the Reel.

Design goals
------------
* **Zero dependencies for the core.** Everything in `engine`, `brand`,
  `storyboard` runs on the Python standard library alone, so it works in a
  locked-down sandbox or on any laptop.
* **Pluggable "premium" upgrades.** `providers` defines clean adapter
  interfaces for an LLM (smart scripts), a TTS engine (real voiceover) and a
  stock-video source. Offline you get strong deterministic scaffolding; add an
  API key + network and the same pipeline produces studio-grade output.
* **Real video on your machine.** `render` assembles an actual vertical MP4
  with ffmpeg (captions burned in, voiceover + music mixed) the moment ffmpeg
  is available.

Usage
-----
    python -m social.cli "3 free AI tools that replace a marketing team" \
        --brand ai_income --duration 35

See `social.cli` for all options.
"""
from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]
