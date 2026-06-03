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

## Long-form faceless YouTube videos (Video Packs)

The same engine also produces **long-form, narrated YouTube videos** (8–12 min)
for storytelling channels — not just short-form Reels. The included
**`betrayal_revenge`** brand ("Betrayal & Revenge Stories") is a complete,
ready-to-run storytelling niche: dramatic-but-grounded voice, story-arc scripts,
high-CTR (non-misleading) titles, mobile-first thumbnail concepts, and a full
SEO upload pack.

```bash
# one full Video Pack from a topic
python3 -m social.cli "my sister forged our mother's will" --brand betrayal_revenge

# let it pick the week's strongest topic for you
python3 -m social.cli --videopack --brand betrayal_revenge

# just this week's ranked topic ideas (no script)
python3 -m social.cli --report --brand betrayal_revenge

# the full weekly bundle: opportunity report + a complete pack for the top topic
python3 -m social.cli --weekly --brand betrayal_revenge
```

A long-form pack (format auto-selected for story brands; force with `--long`)
adds these files to the kit:

| File | Purpose |
|------|---------|
| `VIDEO_PACK.md` | One combined, production-ready doc: title, hook, full script, SEO, thumbnails, promotion, production notes |
| `titles.md` | Recommended title + variations with character counts |
| `seo.md` | Description, 15 tags, primary keyword, 0:00-anchored chapters, pinned comment |
| `thumbnails.md` | Mobile-first thumbnail concepts (≤4 words of overlay) |
| `promotion.md` | Shorts ideas + community post ideas to promote the video |
| `script.md` / `voiceover.txt` / `voiceover.ssml` / `captions.srt` | The narration, ready for any TTS |

Without an `OPENAI_API_KEY`, the script is a complete, brand-aware **beat sheet**
(structure + per-beat guidance) you can edit; **set the key and the same command
writes the full ~1,500-word narration**. Everything else (titles, SEO,
thumbnails, promotion) is generated either way.

### Automatic voiceover (free, no API key)

Add `--voiceover` to a long-form command and the narration is synthesized to MP3
right inside the pack — no separate tool, no recording:

```bash
python3 -m social.cli "my husband's affair with my best friend" \
    --brand betrayal_revenge --voiceover
```

This writes an `audio/` folder containing **one MP3 per story beat**
(`00_hook.mp3`, `01_setup.mp3`, …) so you can drop each clip onto its matching
b-roll, plus a single combined **`narration.mp3`** for the whole video, and an
`INDEX.md` mapping each beat to its file. It uses
[`edge-tts`](https://pypi.org/project/edge-tts/) (free neural voices, just
`pip install edge-tts`) or, if `ELEVENLABS_API_KEY` is set, premium ElevenLabs
voices — picked automatically. The combined track needs `ffmpeg`; without it you
still get the per-beat clips. If no engine is available, `audio/INDEX.md`
explains how to enable it and nothing else is affected.

The free voices use Microsoft's newer **Multilingual** neural models
(`AndrewMultilingual` — warm, confident male narrator — by default for the
betrayal/revenge brand, `AvaMultilingual` for the warm-female brands), delivered
at a slightly slower storytelling pace so the narration sounds human and
emotional rather than flat. Override per run without code changes:

- `EDGE_TTS_VOICE` — any edge-tts voice id (run `edge-tts --list-voices`).
- ElevenLabs expressiveness: `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL`,
  `ELEVENLABS_STABILITY` (lower = more emotional), `ELEVENLABS_STYLE`,
  `ELEVENLABS_SIMILARITY`.

### Upload-ready MP4 (the final video)

Add `--render` to a long-form command to assemble a finished **landscape
1920x1080 narrated video** — the visuals are timed to the actual voiceover, with
a lower-third label per beat, slow Ken-Burns motion, and **captions baked in**:

```bash
python3 -m social.cli "my husband's affair with my best friend" \
    --brand betrayal_revenge --render            # voiceover is generated automatically
```

This writes two files into the pack folder, ready to publish after a quick
lookover:

- **`video.mp4`** — a single self-contained video with captions baked in, and
- **`thumbnail.jpg`** — a matching 1280x720 thumbnail with a bold overlay.

Just pair them with the title/description/tags in `seo.md` and upload.
Backgrounds use:

- real **stock footage/photos** if `PEXELS_API_KEY` is set,
- **AI background art** if `OPENAI_API_KEY` is set, otherwise
- clean **on-brand gradient cards** (no keys, always works).

Requires `ffmpeg` on PATH (`brew install ffmpeg` / `apt-get install -y ffmpeg` /
`winget install Gyan.FFmpeg`). Without it, the full pack + voiceover text are
still produced and you get a clear message. Captions are **burned in by default**
so the MP4 is fully self-contained; pass `--no-captions` for a clean frame
(YouTube can still auto-caption from the audio), or `--no-thumbnail` to skip the
image. The complete flow from a topic to upload-ready files is:

```bash
# topic -> script + SEO + voiceover + video.mp4 (captions in) + thumbnail.jpg
python3 -m social.cli "a sibling who stole an inheritance" \
    --brand betrayal_revenge --render
```

### Weekly Video Pack on autopilot (free, on GitHub's servers)

[`.github/workflows/weekly-videopack.yml`](.github/workflows/weekly-videopack.yml)
runs **every Monday at 08:00 UTC** (and on-demand from the **Actions** tab). It
writes the opportunity report + a full Video Pack for the week's top topic,
**synthesizes the narration to MP3** and **assembles the upload-ready
`video.mp4` (captions baked in) + `thumbnail.jpg`** (free edge-tts + ffmpeg are
installed in the run), then uploads everything as a **downloadable artifact**. It
publishes nothing, so you keep human control of the final lookover and upload.
Set `OPENAI_API_KEY` for full written narration and `PEXELS_API_KEY` for real
stock-footage backgrounds. The
MP4 render is the heaviest step — untick the **render** input on a manual run for
a fast text+audio-only bundle.

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
  engine.py       prompt -> ContentKit; writes all kit files (short + long-form)
  calendar.py     N-day content calendar (topics x formats); batch kit generation
  videopack.py    long-form YouTube Video Pack + weekly opportunity report
  narration.py    long-form voiceover: per-beat MP3s + combined narration.mp3
  render_long.py  long-form landscape MP4: visuals + voiceover (+ captions)
  storyboard.py   animated, dependency-free HTML Reel preview
  render.py       ffmpeg MP4 assembly + voiceover mixing
  publisher.py    Instagram Graph API publishing (Reels + image), stdlib only
  cli.py          command-line entrypoint
notebooks/
  content_studio.ipynb   one-click Google Colab: month of content + MP4s -> zip
.github/workflows/
  autopost.yml          scheduled cloud auto-poster (no local install needed)
  weekly-videopack.yml  weekly long-form YouTube Video Pack (artifact, no keys)
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
