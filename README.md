# social — faceless short-form content engine

Turn **one prompt** into a complete, premium Instagram Reels / TikTok / YouTube
Shorts content kit: script, scene-by-scene storyboard with timings, a burned-in
caption file (`.srt`), an Instagram post caption with A/B hook variants, a tiered
hashtag strategy, a TTS-ready voiceover (plain + SSML), a shot list, a
machine-readable JSON package, and a **browser-playable animated 9:16 preview**
of the Reel.

The core runs on the Python standard library alone — no dependencies, no API
keys, no internet required. Add keys/tools and the *same* pipeline upgrades to
AI-written scripts, real voiceover, stock b-roll, and a rendered MP4.

## Easiest way to run it (pick one)

**A. One click in your browser (recommended, zero install).**
Open [`notebooks/content_studio.ipynb`](notebooks/content_studio.ipynb) in
free Google Colab and choose **Runtime → Run all**. It installs everything,
generates a whole **month** of content *with rendered MP4 videos*, and
auto-downloads a `.zip`. Nothing to install on your computer.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/BogdanTheCreator/Automated-Instagram-/blob/main/notebooks/content_studio.ipynb)

**B. One command on your computer.**
```bash
./run.sh                 # 30-day calendar + a full kit for every day
./run.sh privacy 14      # 14 days of the "privacy" niche
```
It auto-detects `ffmpeg`/`edge-tts` and tells you how to enable MP4s + voiceover.

**C. Direct CLI** — see Quick start below for fine-grained control.

## The niche

The default brand is **`ai_income`** ("AI Income Lab"): faceless-friendly, fully
automatable, evergreen *and* news-fed, with the strongest beginner monetisation
surface (affiliate links to AI tools, your own digital products, sponsorships).
`privacy` is the more differentiated, less-saturated alternative. `money` and
`longevity` are also included. The engine works for any topic.

## Quick start

```bash
# from the repo root (the folder containing this README)
python3 -m social.cli "3 free AI tools that replace a marketing team"

# choose a niche, length, and number of tips
python3 -m social.cli "delete yourself from data broker sites" \
    --brand privacy --duration 40 --points 5

# render a real vertical MP4 (needs ffmpeg; uses TTS if available)
python3 -m social.cli "the 50/30/20 budget" --brand money --render

# helpers
python3 -m social.cli --doctor        # what premium features are active
python3 -m social.cli --list-brands   # niche presets
python3 -m social.cli --ideas -b ai_income
```

Each run writes a timestamped folder under `content_kits/` (a curated example
lives in [`samples/`](samples)). Open `storyboard.html` in any browser to watch
the animated preview.

## 30-day content calendar

Plan and (optionally) produce a whole month in one command:

```bash
# a 30-day plan: distinct topic, pillar, format and post time per day
python3 -m social.cli --calendar --days 30 --brand ai_income

# also generate a full content kit for every single day
python3 -m social.cli --calendar --days 30 --brand ai_income --with-kits

# start on a specific date / post twice a day
python3 -m social.cli --calendar --days 30 --start 2026-07-01 --posts-per-day 2
```

This writes `calendar.md` (a glanceable table), `calendar.csv` (import into
Notion / Google Sheets / a scheduler), and `calendar.json`. Topics are drawn
from per-brand pillars + themes crossed with proven formats (listicle, myth,
how-to, quick win, ...), so a month reads as varied and intentional. With an
`OPENAI_API_KEY` set, the topics are proposed by the LLM instead. A lightweight
example lives in [`samples/sample-30-day-calendar/`](samples/sample-30-day-calendar).

## Auto-posting to Instagram (hands-off, no PC install)

The account can post **by itself on a schedule, running on GitHub's servers** —
nothing installed on your computer. The included workflow
[`.github/workflows/autopost.yml`](.github/workflows/autopost.yml) each day:

1. picks today's topic, writes the script/captions/hashtags, renders a Reel MP4,
2. uploads it to a public GitHub Release URL,
3. publishes it to your Instagram via the official Graph API.

Until you add credentials, every run is a safe **dry run** (renders but does not
post), and you can trigger it manually with a button from the **Actions** tab.
Full step-by-step setup (and a no-API alternative using Meta Business Suite) is in
[`SETUP_AUTOPOST.md`](SETUP_AUTOPOST.md).

The same publishing works locally too:

```bash
python3 -m social.cli --verify-instagram             # check IG_USER_ID + IG_ACCESS_TOKEN
python3 -m social.cli --autopost --brand ai_income   # build today's post
python3 -m social.cli --publish --video-url <PUBLIC_MP4_URL> --kit <kit_folder> --dry-run
```

> This posts *your* original content to *your* own Business/Creator account via
> the official API — the same mechanism Buffer/Later/Hootsuite use. It does not
> touch followers or engagement.

## What's in a kit

| File | Purpose |
|------|---------|
| `storyboard.html` | Self-contained animated 9:16 preview (karaoke captions, brand colours, loops) |
| `script.md` | Hook + scene breakdown with on-screen text, voiceover, b-roll, and timings |
| `captions.srt` | Subtitle file, ready to burn into the video |
| `voiceover.txt` / `voiceover.ssml` | Narration for any TTS engine (SSML adds pacing/emphasis) |
| `post.md` | IG caption, 3 hook A/B variants, alt-text, cover-text ideas, posting times |
| `hashtags.txt` | Broad / mid / niche / branded tiers + a copy-paste recommended set |
| `shotlist.md` | Per-scene b-roll search queries and overlay text |
| `content_package.json` | Everything, machine-readable, for automation/rendering |

## Premium upgrades (auto-detected)

Set any of these and the pipeline uses them automatically — no code changes:

| Capability | How to enable |
|------------|---------------|
| AI-written scripts | `OPENAI_API_KEY` (+ optional `OPENAI_BASE_URL`, `OPENAI_MODEL`) — works with OpenAI, Groq, Together, OpenRouter, or a local Ollama/LM Studio server |
| Premium voiceover | `ELEVENLABS_API_KEY` (+ optional `ELEVENLABS_VOICE_ID`) |
| Free voiceover | `pip install edge-tts` |
| Stock b-roll URLs | `PEXELS_API_KEY` |
| AI cover art | `OPENAI_API_KEY` (else a clean branded gradient cover is used) |
| MP4 rendering | install `ffmpeg` (`brew install ffmpeg` / `apt-get install ffmpeg`) |
| Token never expires | `IG_APP_ID` + `IG_APP_SECRET` + `GH_PAT` (auto-refreshes daily — see SETUP_AUTOPOST.md) |

Run `python3 -m social.cli --doctor` to see what's active in your environment.

## Architecture

```
social/
  brand.py        niche/brand presets: voice, palette, hooks, CTAs, hashtags, themes
  providers.py    pluggable LLM / TTS / stock adapters (offline stubs + real impls)
  engine.py       prompt -> ContentKit; writes all kit files
  calendar.py     N-day content calendar (topics x formats); batch kit generation
  storyboard.py   animated, dependency-free HTML Reel preview
  render.py       ffmpeg MP4 assembly + voiceover mixing
  publisher.py    Instagram Graph API publishing (Reels + image), stdlib only
  cli.py          command-line entrypoint
notebooks/
  content_studio.ipynb   one-click Google Colab: month of content + MP4s -> zip
.github/workflows/
  autopost.yml    scheduled cloud auto-poster (no local install needed)
run.sh            one-command local runner with capability detection
SETUP_AUTOPOST.md guided Instagram auto-posting setup
```

The core (`brand`, `engine`, `storyboard`) imports no third-party packages, so it
runs anywhere. `providers` and `render` fail soft: if a key/tool is missing they
fall back, and the kit is always produced.

> Note: in a network-locked sandbox there is no `ffmpeg`/TTS/internet, so the MP4
> and AI-written script steps are skipped — but the full kit and the animated
> `storyboard.html` preview are still generated. Run locally with the upgrades
> above for the studio-grade output.
