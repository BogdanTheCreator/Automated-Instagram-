#!/usr/bin/env bash
# run.sh — one command to generate content. Beginner-friendly.
#
#   ./run.sh                      # 30-day calendar + a kit for every day (recommended)
#   ./run.sh privacy 14           # 14 days for the "privacy" niche
#   ./run.sh ai_income 30 "one off topic"   # a single video kit for one topic
#
# It auto-detects ffmpeg (for MP4s) and edge-tts (for voiceover) and tells you
# how to enable them if they're missing. Nothing is required to get a full kit.

set -euo pipefail
cd "$(dirname "$0")"

BRAND="${1:-ai_income}"
DAYS="${2:-30}"
TOPIC="${3:-}"

# --- pick a python ---------------------------------------------------------
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "Python 3 is not installed. Get it from https://www.python.org/downloads/ and re-run."
  exit 1
fi

echo "================ content studio ================"
echo "python   : $($PY --version 2>&1)"

# --- capability check ------------------------------------------------------
if command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg   : found  (real MP4 videos will be rendered)"
  RENDER=1
else
  echo "ffmpeg   : missing (kits + animated HTML preview only)"
  echo "           install it for MP4s:  macOS 'brew install ffmpeg' | Ubuntu 'sudo apt-get install -y ffmpeg'"
  RENDER=0
fi

if $PY -c "import edge_tts" >/dev/null 2>&1; then
  echo "voiceover: edge-tts found (free neural voice)"
else
  echo "voiceover: none (run 'pip install edge-tts' for a free AI voice)"
fi

if [ -n "${OPENAI_API_KEY:-}" ]; then
  echo "scripts  : OPENAI_API_KEY set (AI-written scripts)"
else
  echo "scripts  : built-in templates (set OPENAI_API_KEY for AI-written scripts)"
fi
echo "================================================"

# --- run -------------------------------------------------------------------
if [ -n "$TOPIC" ]; then
  echo "Generating a single content kit for: \"$TOPIC\" (brand: $BRAND)"
  ARGS=(-m social.cli "$TOPIC" --brand "$BRAND")
  [ "$RENDER" = "1" ] && ARGS+=(--render)
  "$PY" "${ARGS[@]}"
else
  echo "Generating a ${DAYS}-day calendar with a full kit per day (brand: $BRAND)..."
  "$PY" -m social.cli --calendar --days "$DAYS" --brand "$BRAND" --with-kits

  if [ "$RENDER" = "1" ]; then
    MONTH="$(ls -dt content_kits/*calendar*/ 2>/dev/null | head -1 || true)"
    if [ -n "$MONTH" ]; then
      echo ""
      echo "Rendering MP4s for each day in: $MONTH"
      "$PY" - "$MONTH" <<'PYEOF'
import glob, os, sys
from social.render import render_from_package
month = sys.argv[1]
pkgs = sorted(glob.glob(os.path.join(month, "kits", "*", "content_package.json")))
for i, pkg in enumerate(pkgs, 1):
    out = os.path.join(os.path.dirname(pkg), "reel.mp4")
    r = render_from_package(pkg, out)
    print(f"  [{i:>2}/{len(pkgs)}] {'OK  ' if r.ok else 'skip'} {os.path.basename(os.path.dirname(pkg))[:48]}")
print("\nDone. Your videos are the reel.mp4 files inside each kit folder.")
PYEOF
    fi
  fi
fi

echo ""
echo "All set. Open any 'storyboard.html' in a browser to preview, and use"
echo "'post.md' + 'hashtags.txt' for the caption when you post."
