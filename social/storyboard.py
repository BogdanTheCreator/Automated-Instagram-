"""
storyboard.py — render a self-contained, browser-playable preview of the Reel.

This produces a single `.html` file with no external assets or dependencies: a
9:16 phone frame that auto-plays the scenes on a synced virtual clock, with
animated "karaoke" captions, per-scene gradient backgrounds in the brand
palette, a subtle Ken-Burns zoom, a progress bar and scene markers. It loops.

It is the offline stand-in for a rendered MP4 (which `render.py` produces when
ffmpeg is available) and is genuinely useful for previewing pacing and copy
before you commit to a render.
"""
from __future__ import annotations

import json
from typing import List

from .brand import Brand
from .engine import ContentKit


def _scenes_payload(kit: ContentKit) -> List[dict]:
    out = []
    for s in kit.scenes:
        out.append({
            "role": s.role,
            "onScreen": s.on_screen,
            "narration": s.narration,
            "broll": s.broll_query,
            "start": s.start,
            "end": s.end,
        })
    return out


def render_html(kit: ContentKit, brand: Brand) -> str:
    p = brand.palette
    data = {
        "title": kit.title,
        "handle": brand.handle_ideas[0],
        "brandName": kit.brand_name,
        "totalSeconds": kit.total_seconds,
        "scenes": _scenes_payload(kit),
        "palette": {
            "bg": p.bg, "bg2": p.bg2, "text": p.text,
            "accent": p.accent, "accent2": p.accent2, "subtle": p.subtle,
        },
        "font": brand.font_family,
    }
    data_json = json.dumps(data, ensure_ascii=False)

    # NOTE: braces in the CSS/JS below are doubled because this is an f-string.
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{_esc(kit.title)} — Reel preview</title>
<style>
  :root {{
    --bg: {p.bg}; --bg2: {p.bg2}; --text: {p.text};
    --accent: {p.accent}; --accent2: {p.accent2}; --subtle: {p.subtle};
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ height: 100%; }}
  body {{
    background: #05070d;
    color: var(--text);
    font-family: {brand.font_family};
    display: flex; flex-direction: column; align-items: center; gap: 18px;
    padding: 28px 12px 48px; min-height: 100%;
  }}
  .meta {{ text-align: center; opacity: .85; max-width: 420px; }}
  .meta h1 {{ font-size: 17px; font-weight: 700; }}
  .meta p {{ font-size: 12px; opacity: .7; margin-top: 4px; }}
  .phone {{
    position: relative; width: 320px; height: 569px; /* 9:16 */
    border-radius: 38px; padding: 10px; background: #0c0e14;
    box-shadow: 0 30px 80px rgba(0,0,0,.6), inset 0 0 0 2px #1c2030;
  }}
  .notch {{
    position: absolute; top: 16px; left: 50%; transform: translateX(-50%);
    width: 110px; height: 22px; background: #000; border-radius: 14px; z-index: 9;
  }}
  .screen {{
    position: relative; width: 100%; height: 100%; border-radius: 30px;
    overflow: hidden; background: var(--bg);
  }}
  .bg {{
    position: absolute; inset: 0; opacity: 0; transition: opacity .5s ease;
    transform: scale(1.05);
  }}
  .bg.active {{ opacity: 1; animation: kenburns var(--dur,4s) linear forwards; }}
  @keyframes kenburns {{ from {{ transform: scale(1.02) }} to {{ transform: scale(1.14) }} }}
  .grain {{
    position:absolute; inset:0; pointer-events:none; opacity:.06;
    background-image: radial-gradient(#fff 1px, transparent 1px);
    background-size: 3px 3px; mix-blend-mode: overlay;
  }}
  .topbar {{
    position: absolute; top: 46px; left: 16px; right: 16px; z-index: 6;
    display: flex; align-items: center; gap: 8px; font-size: 12px; opacity:.9;
  }}
  .dot {{ width: 26px; height: 26px; border-radius: 50%;
    background: linear-gradient(135deg, var(--accent), var(--accent2)); }}
  .caption-wrap {{
    position: absolute; inset: 0; display: flex; align-items: center;
    justify-content: center; padding: 26px; text-align: center; z-index: 5;
  }}
  .caption {{
    font-weight: 800; line-height: 1.12; letter-spacing: -.01em;
    font-size: 34px; text-shadow: 0 2px 18px rgba(0,0,0,.55);
  }}
  .caption .w {{ opacity: .28; transition: opacity .12s ease, color .12s ease; }}
  .caption .w.on {{ opacity: 1; }}
  .caption .w.hot {{ color: var(--accent); }}
  .rolebadge {{
    position: absolute; top: 84px; left: 50%; transform: translateX(-50%);
    z-index: 6; font-size: 10px; letter-spacing: .18em; text-transform: uppercase;
    padding: 4px 10px; border-radius: 999px; background: rgba(255,255,255,.10);
    border: 1px solid rgba(255,255,255,.18); opacity: .9;
  }}
  .subs {{
    position: absolute; left: 18px; right: 18px; bottom: 92px; z-index: 6;
    text-align: center; font-size: 15px; font-weight: 600; opacity: .92;
    text-shadow: 0 1px 8px rgba(0,0,0,.6);
  }}
  .cta-chip {{
    position: absolute; left: 50%; bottom: 120px; transform: translateX(-50%);
    z-index: 7; padding: 10px 16px; border-radius: 999px; font-weight: 700;
    font-size: 14px; color: #05070d;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    box-shadow: 0 8px 30px rgba(0,0,0,.4); display: none;
  }}
  .progress {{
    position: absolute; left: 14px; right: 14px; bottom: 20px; z-index: 8;
    height: 4px; display: flex; gap: 4px;
  }}
  .seg {{ flex: 1; background: rgba(255,255,255,.22); border-radius: 4px; overflow: hidden; }}
  .seg > i {{ display:block; height:100%; width:0%; background: var(--text); }}
  .handle {{
    position:absolute; bottom: 56px; left: 18px; z-index: 6; font-size: 13px;
    font-weight: 700; opacity:.95; text-shadow: 0 1px 8px rgba(0,0,0,.6);
  }}
  .controls {{ display:flex; gap:10px; align-items:center; }}
  button {{
    background: #11131c; color: var(--text); border: 1px solid #262a3a;
    border-radius: 10px; padding: 9px 14px; font-size: 13px; cursor: pointer;
    font-family: inherit;
  }}
  button:hover {{ border-color: var(--accent); }}
  .hint {{ font-size: 11px; opacity: .5; }}
</style>
</head>
<body>
  <div class="meta">
    <h1>{_esc(kit.title)}</h1>
    <p>{_esc(kit.brand_name)} · ~{kit.total_seconds:.0f}s · animated preview (no audio)</p>
  </div>

  <div class="phone">
    <div class="notch"></div>
    <div class="screen" id="screen">
      <div class="bg" id="bg"></div>
      <div class="grain"></div>
      <div class="topbar"><span class="dot"></span><span>{_esc(brand.handle_ideas[0])}</span></div>
      <div class="rolebadge" id="role">HOOK</div>
      <div class="caption-wrap"><div class="caption" id="caption"></div></div>
      <div class="cta-chip" id="cta">FOLLOW</div>
      <div class="subs" id="subs"></div>
      <div class="handle">{_esc(brand.handle_ideas[0])}</div>
      <div class="progress" id="progress"></div>
    </div>
  </div>

  <div class="controls">
    <button id="play">⏸ Pause</button>
    <button id="restart">⟲ Restart</button>
    <span class="hint">Loops automatically · captions sync to scene timing</span>
  </div>

<script>
const DATA = {data_json};
const scenes = DATA.scenes;
const total = DATA.totalSeconds;
const pal = DATA.palette;

const bg = document.getElementById('bg');
const captionEl = document.getElementById('caption');
const subsEl = document.getElementById('subs');
const roleEl = document.getElementById('role');
const ctaEl = document.getElementById('cta');
const progress = document.getElementById('progress');

// Build progress segments (one per scene, weighted by duration).
scenes.forEach(s => {{
  const seg = document.createElement('div');
  seg.className = 'seg';
  seg.style.flex = Math.max(0.2, (s.end - s.start));
  seg.innerHTML = '<i></i>';
  progress.appendChild(seg);
}});
const segFills = [...progress.querySelectorAll('i')];

const gradients = [
  `linear-gradient(160deg, ${{pal.bg}}, ${{pal.bg2}})`,
  `radial-gradient(120% 80% at 30% 20%, ${{pal.bg2}}, ${{pal.bg}})`,
  `linear-gradient(200deg, ${{pal.bg2}}, ${{pal.bg}} 70%)`,
];

function splitWords(text) {{
  return text.split(/\\s+/).filter(Boolean);
}}

let current = -1;
function showScene(i) {{
  const s = scenes[i];
  current = i;
  bg.style.setProperty('--dur', (s.end - s.start) + 's');
  bg.style.background = gradients[i % gradients.length];
  bg.classList.remove('active'); void bg.offsetWidth; bg.classList.add('active');

  roleEl.textContent = s.role;
  ctaEl.style.display = (s.role === 'cta') ? 'block' : 'none';

  // Big on-screen caption as karaoke words.
  captionEl.innerHTML = '';
  const words = splitWords(s.onScreen);
  // scale font down a touch for long lines
  captionEl.style.fontSize = words.length > 5 ? '28px' : '34px';
  words.forEach(w => {{
    const span = document.createElement('span');
    span.className = 'w'; span.textContent = w + ' ';
    captionEl.appendChild(span);
  }});
}}

function render(t) {{
  // find active scene
  let i = scenes.findIndex(s => t >= s.start && t < s.end);
  if (i === -1) i = scenes.length - 1;
  if (i !== current) showScene(i);

  const s = scenes[i];
  const frac = Math.min(1, Math.max(0, (t - s.start) / Math.max(0.001, (s.end - s.start))));

  // karaoke highlight on the big caption
  const ws = captionEl.querySelectorAll('.w');
  const hot = Math.floor(frac * ws.length);
  ws.forEach((el, k) => {{
    el.classList.toggle('on', k <= hot);
    el.classList.toggle('hot', k === hot);
  }});

  // bottom subtitle: reveal narration progressively
  const nwords = splitWords(s.narration);
  const shown = Math.max(1, Math.ceil(frac * nwords.length));
  subsEl.textContent = nwords.slice(0, shown).join(' ');

  // progress bars
  segFills.forEach((f, k) => {{
    f.style.width = (k < i ? 100 : (k === i ? frac * 100 : 0)) + '%';
  }});
}}

let playing = true;
let t0 = performance.now();
let clock = 0;

function loop(now) {{
  if (playing) {{
    const dt = (now - t0) / 1000;
    t0 = now;
    clock += dt;
    if (clock >= total) clock = 0; // loop
    render(clock);
  }} else {{
    t0 = now;
  }}
  requestAnimationFrame(loop);
}}
requestAnimationFrame(loop);

document.getElementById('play').onclick = (e) => {{
  playing = !playing;
  e.target.textContent = playing ? '⏸ Pause' : '▶ Play';
}};
document.getElementById('restart').onclick = () => {{ clock = 0; }};
</script>
</body>
</html>
"""


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )
