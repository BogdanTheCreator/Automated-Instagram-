"""
providers.py — pluggable adapters for the "premium" upgrades.

The core engine never imports a third-party package. Instead it talks to three
small interfaces defined here:

    LLMProvider     -> turns a brief into a smart, original script
    TTSProvider     -> turns narration text into a voiceover audio file
    StockProvider   -> finds b-roll clips for each scene

Each interface ships with an **offline** implementation that needs nothing but
the standard library, plus a **real** implementation that activates when the
relevant API key / dependency / network is available. `auto_*()` factory
functions pick the best provider for the current environment, so the same
pipeline degrades gracefully in a sandbox and shines on a real machine.

Nothing here performs network calls at import time, and every real provider
fails soft (returns None / falls back) so the kit is always produced.
"""
from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol


# --------------------------------------------------------------------------- #
# Capability probing
# --------------------------------------------------------------------------- #

def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _module_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def environment_report() -> Dict[str, object]:
    """A quick snapshot of what premium features are usable right now."""
    return {
        "ffmpeg": has_ffmpeg(),
        "openai_key": bool(os.getenv("OPENAI_API_KEY")),
        "openai_base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "elevenlabs_key": bool(os.getenv("ELEVENLABS_API_KEY")),
        "edge_tts": _module_available("edge_tts"),
        "pyttsx3": _module_available("pyttsx3"),
        "pexels_key": bool(os.getenv("PEXELS_API_KEY")),
        "pixabay_key": bool(os.getenv("PIXABAY_API_KEY")),
    }


# --------------------------------------------------------------------------- #
# LLM provider
# --------------------------------------------------------------------------- #

@dataclass
class ScriptBrief:
    topic: str
    brand_name: str
    voice: str
    scene_count: int
    seconds: int
    point_count: int


class LLMProvider(Protocol):
    name: str
    def write_script(self, brief: ScriptBrief) -> Optional[Dict[str, object]]:
        """Return {'title','hook','points':[...],'payoff','cta'} or None to fall back."""
        ...
    def propose_topics(self, brand_name: str, voice: str, pillars: List[str],
                       count: int) -> Optional[List[str]]:
        """Return a list of distinct video topic ideas, or None to fall back."""
        ...


class OfflineLLM:
    """No model. Returns None so the engine uses its built-in framework writer."""
    name = "offline-template"

    def write_script(self, brief: ScriptBrief) -> Optional[Dict[str, object]]:
        return None

    def propose_topics(self, brand_name: str, voice: str, pillars: List[str],
                       count: int) -> Optional[List[str]]:
        return None


class OpenAICompatibleLLM:
    """
    Works with any OpenAI-compatible chat completions endpoint (OpenAI, Groq,
    Together, OpenRouter, a local Ollama/LM Studio server, ...). Set:
        OPENAI_API_KEY   (required)
        OPENAI_BASE_URL  (optional, default https://api.openai.com/v1)
        OPENAI_MODEL     (optional, default gpt-4o-mini)
    Uses only urllib so there is no dependency to install.
    """
    name = "openai-compatible"

    def __init__(self) -> None:
        self.key = os.getenv("OPENAI_API_KEY", "")
        self.base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def write_script(self, brief: ScriptBrief) -> Optional[Dict[str, object]]:
        if not self.key:
            return None
        sys_prompt = (
            "You are a viral short-form scriptwriter for faceless Reels. "
            "Return STRICT JSON only, no prose."
        )
        user_prompt = (
            f"Brand: {brief.brand_name}\nVoice: {brief.voice}\n"
            f"Topic: {brief.topic}\n"
            f"Write a {brief.seconds}-second vertical video script with exactly "
            f"{brief.point_count} value points.\n"
            "JSON shape: {\"title\": str, \"hook\": str (<=12 words, scroll-stopping), "
            "\"points\": [{\"on_screen\": str (<=6 words), \"narration\": str (1 sentence), "
            "\"broll\": str (2-4 word stock-footage search)}], "
            "\"payoff\": str, \"cta\": str}. "
            "Punchy, specific, no fluff, no emojis inside narration."
        )
        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.8,
            "response_format": {"type": "json_object"},
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
            data = json.loads(content)
            if "points" in data and "hook" in data:
                return data
            return None
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError):
            return None

    def propose_topics(self, brand_name: str, voice: str, pillars: List[str],
                       count: int) -> Optional[List[str]]:
        if not self.key:
            return None
        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content":
                 "You are a short-form content strategist. Return STRICT JSON only."},
                {"role": "user", "content":
                 f"Brand: {brand_name}\nVoice: {voice}\n"
                 f"Content pillars: {', '.join(pillars)}\n"
                 f"Propose {count} distinct, scroll-stopping faceless video topics. "
                 "Specific, varied across the pillars, no duplicates, no numbering. "
                 'JSON shape: {"topics": [str, ...]}.'},
            ],
            "temperature": 0.9,
            "response_format": {"type": "json_object"},
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base}/chat/completions", data=body,
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            data = json.loads(payload["choices"][0]["message"]["content"])
            topics = [str(t).strip() for t in (data.get("topics") or []) if str(t).strip()]
            return topics or None
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError):
            return None


def auto_llm() -> LLMProvider:
    if os.getenv("OPENAI_API_KEY"):
        return OpenAICompatibleLLM()
    return OfflineLLM()


# --------------------------------------------------------------------------- #
# TTS provider
# --------------------------------------------------------------------------- #

class TTSProvider(Protocol):
    name: str
    available: bool
    def synthesize(self, text: str, out_path: str, voice_hint: str = "") -> Optional[str]:
        """Write an audio file and return its path, or None if unavailable."""
        ...


class OfflineTTS:
    """No audio engine. Records intent only; render falls back to silent track."""
    name = "offline-none"
    available = False

    def synthesize(self, text: str, out_path: str, voice_hint: str = "") -> Optional[str]:
        return None


class EdgeTTS:
    """Free, high-quality neural voices via the `edge-tts` package (no API key)."""
    name = "edge-tts"

    def __init__(self) -> None:
        self.available = _module_available("edge_tts") and shutil.which("edge-tts") is not None

    def synthesize(self, text: str, out_path: str, voice_hint: str = "") -> Optional[str]:
        if not self.available:
            return None
        import subprocess
        voice = {
            "male_energetic": "en-US-GuyNeural",
            "female_warm": "en-US-JennyNeural",
            "neutral_calm": "en-US-AriaNeural",
        }.get(voice_hint, "en-US-AriaNeural")
        try:
            subprocess.run(
                ["edge-tts", "--voice", voice, "--text", text, "--write-media", out_path],
                check=True, capture_output=True, timeout=120,
            )
            return out_path if os.path.exists(out_path) else None
        except Exception:
            return None


class ElevenLabsTTS:
    """Premium voices via ElevenLabs. Set ELEVENLABS_API_KEY (+ optional ELEVENLABS_VOICE_ID)."""
    name = "elevenlabs"

    def __init__(self) -> None:
        self.key = os.getenv("ELEVENLABS_API_KEY", "")
        self.voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
        self.available = bool(self.key)

    def synthesize(self, text: str, out_path: str, voice_hint: str = "") -> Optional[str]:
        if not self.available:
            return None
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
        body = json.dumps({
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=body,
            headers={"xi-api-key": self.key, "Content-Type": "application/json",
                     "Accept": "audio/mpeg"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                audio = resp.read()
            with open(out_path, "wb") as fh:
                fh.write(audio)
            return out_path
        except Exception:
            return None


def auto_tts() -> TTSProvider:
    if os.getenv("ELEVENLABS_API_KEY"):
        p = ElevenLabsTTS()
        if p.available:
            return p
    edge = EdgeTTS()
    if edge.available:
        return edge
    return OfflineTTS()


# --------------------------------------------------------------------------- #
# Stock footage provider
# --------------------------------------------------------------------------- #

@dataclass
class StockClip:
    query: str
    url: Optional[str]
    source: str
    note: str = ""


class StockProvider(Protocol):
    name: str
    def find(self, query: str) -> StockClip:
        ...


class OfflineStock:
    """No network. Returns the search query so a human/renderer can fetch later."""
    name = "offline-query-only"

    def find(self, query: str) -> StockClip:
        return StockClip(query=query, url=None, source="manual",
                         note="Search this on Pexels/Pixabay or generate with an AI video tool.")


class PexelsStock:
    """Free stock video via Pexels. Set PEXELS_API_KEY."""
    name = "pexels"

    def __init__(self) -> None:
        self.key = os.getenv("PEXELS_API_KEY", "")

    def find(self, query: str) -> StockClip:
        if not self.key:
            return OfflineStock().find(query)
        url = f"https://api.pexels.com/videos/search?per_page=1&orientation=portrait&query={urllib.request.quote(query)}"
        req = urllib.request.Request(url, headers={"Authorization": self.key})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            videos = data.get("videos") or []
            if not videos:
                return OfflineStock().find(query)
            files = sorted(videos[0].get("video_files", []),
                           key=lambda f: (f.get("height") or 0), reverse=True)
            link = files[0]["link"] if files else None
            return StockClip(query=query, url=link, source="pexels")
        except Exception:
            return OfflineStock().find(query)


def auto_stock() -> StockProvider:
    if os.getenv("PEXELS_API_KEY"):
        return PexelsStock()
    return OfflineStock()



# --------------------------------------------------------------------------- #
# Cover / thumbnail image provider
# --------------------------------------------------------------------------- #

class ImageProvider(Protocol):
    name: str
    def background(self, prompt: str, out_path: str) -> Optional[str]:
        """Generate a background image for a cover and return its path, or None."""
        ...


class OfflineImage:
    """No image model. render.py falls back to a branded gradient cover."""
    name = "offline-gradient"

    def background(self, prompt: str, out_path: str) -> Optional[str]:
        return None


class OpenAIImage:
    """
    AI background art via an OpenAI-compatible images endpoint. Set:
        OPENAI_API_KEY    (required)
        OPENAI_IMAGE_MODEL (optional, default gpt-image-1)
        OPENAI_BASE_URL   (optional)
    The title text is drawn on top by the renderer, so we only ask for art.
    Uses urllib only; fails soft to the gradient cover.
    """
    name = "openai-image"

    def __init__(self) -> None:
        self.key = os.getenv("OPENAI_API_KEY", "")
        self.base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")

    def background(self, prompt: str, out_path: str) -> Optional[str]:
        if not self.key:
            return None
        body = json.dumps({
            "model": self.model,
            "prompt": (
                "Vertical 9:16 social media background art, premium and clean, "
                "no text, strong negative space in the center for a title, "
                f"subject: {prompt}"
            ),
            "size": "1024x1536",
            "n": 1,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base}/images/generations", data=body,
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            item = (payload.get("data") or [{}])[0]
            if item.get("b64_json"):
                import base64
                with open(out_path, "wb") as fh:
                    fh.write(base64.b64decode(item["b64_json"]))
                return out_path
            if item.get("url"):
                with urllib.request.urlopen(item["url"], timeout=90) as img:
                    with open(out_path, "wb") as fh:
                        fh.write(img.read())
                return out_path
            return None
        except Exception:
            return None


def auto_image() -> ImageProvider:
    if os.getenv("OPENAI_API_KEY") and os.getenv("ENABLE_AI_COVERS", "1") != "0":
        return OpenAIImage()
    return OfflineImage()
