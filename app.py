"""
CENTRIFUGE CHESS
A retro-arcade puzzle game about balancing centrifuge rotors.

Run locally:   streamlit run app.py
Deploy:        push to GitHub -> share.streamlit.io
"""

from __future__ import annotations

import json
import math
import os
import random
import time
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

import streamlit as st
import streamlit.components.v1 as components

# --------------------------------------------------------------------------
# Page config must be the first Streamlit call
# --------------------------------------------------------------------------
st.set_page_config(
    page_title="Centrifuge Chess",
    page_icon="🧪",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# --------------------------------------------------------------------------
# Design tokens
# --------------------------------------------------------------------------
BENCH_DEEP = "#0b0d1a"   # bench at night
BENCH_MID = "#151a30"    # panel
AMBER = "#ffb627"        # CRT amber, primary UI
CYAN = "#3ff2e0"         # tubes the player places
GREEN = "#5be36a"        # tubes already in the rotor
MAGENTA = "#ff3d8b"      # imbalance needle / danger
STEEL = "#5a6486"        # inert chrome, slot outlines
BONE = "#e8e6f0"         # body text

GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&family=IBM+Plex+Mono:wght@400;600&display=swap');

.stApp {
    background:
        radial-gradient(ellipse at 50% -10%, #1d2547 0%, #0b0d1a 60%),
        #0b0d1a;
    color: #e8e6f0;
}
.block-container { padding-top: 2.2rem; max-width: 780px; }

h1, h2, h3, .arcade {
    font-family: 'Press Start 2P', monospace !important;
    letter-spacing: 0.04em;
    line-height: 1.7;
}
body, p, li, div[data-testid="stMarkdownContainer"] {
    font-family: 'IBM Plex Mono', monospace;
}

.cc-title {
    font-family: 'Press Start 2P', monospace;
    font-size: 1.55rem;
    color: #ffb627;
    text-align: center;
    text-shadow: 0 0 14px rgba(255,182,39,0.55), 0 3px 0 #7a4a00;
    margin-bottom: 0.2rem;
}
.cc-sub {
    font-family: 'IBM Plex Mono', monospace;
    text-align: center;
    color: #5a6486;
    letter-spacing: 0.22em;
    font-size: 0.72rem;
    text-transform: uppercase;
    margin-bottom: 1.4rem;
}

.cc-panel {
    background: linear-gradient(180deg, #151a30 0%, #10142a 100%);
    border: 2px solid #2b3358;
    border-radius: 4px;
    padding: 0.85rem 1.05rem;
    margin-bottom: 0.9rem;
}
.cc-hud {
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
    font-family: 'Press Start 2P', monospace;
    font-size: 0.6rem;
    color: #ffb627;
}
.cc-hud span.k { color: #5a6486; display: block; margin-bottom: 6px; font-size: 0.52rem; }

.cc-readout {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.8rem;
    color: #5a6486;
    text-align: center;
    letter-spacing: 0.06em;
}
.cc-ok { color: #5be36a; }
.cc-bad { color: #ff3d8b; }
.cc-amber { color: #ffb627; }

/* Buttons: slot pads on a control panel */
.stButton > button {
    font-family: 'IBM Plex Mono', monospace !important;
    font-weight: 600;
    background: #1b2140;
    color: #e8e6f0;
    border: 1px solid #38416e;
    border-radius: 3px;
    padding: 0.32rem 0.1rem;
    transition: none;
}
.stButton > button:hover {
    background: #ffb627;
    color: #0b0d1a;
    border-color: #ffb627;
}
.stButton > button:disabled {
    background: #111428;
    color: #39405f;
    border-color: #1e2440;
}
.stButton > button:focus-visible {
    outline: 2px solid #3ff2e0;
    outline-offset: 2px;
}

table.cc-lb {
    width: 100%;
    border-collapse: collapse;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.82rem;
}
table.cc-lb th {
    text-align: left;
    color: #5a6486;
    font-weight: 600;
    text-transform: uppercase;
    font-size: 0.66rem;
    letter-spacing: 0.14em;
    border-bottom: 1px solid #2b3358;
    padding: 6px 8px;
}
table.cc-lb td { padding: 6px 8px; border-bottom: 1px solid #191e38; }
table.cc-lb tr.me td { color: #3ff2e0; }
table.cc-lb td.rank { color: #ffb627; }

@media (prefers-reduced-motion: reduce) {
    * { animation: none !important; transition: none !important; }
}
</style>
"""


# --------------------------------------------------------------------------
# Level design
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class LevelSpec:
    name: str
    subtitle: str
    slots: int          # rotor positions
    total_tubes: int    # tubes in the final balanced solution
    to_place: int       # how many of those the player must place
    blocked: int        # cracked / missing buckets
    masses: Tuple[float, ...]
    tol_frac: float     # tolerance as a fraction of total loaded mass
    par_seconds: int


LEVELS: List[LevelSpec] = [
    LevelSpec("MICROSPIN 6", "personal microfuge", 6, 2, 1, 0, (1.5,), 0.055, 25),
    LevelSpec("MICROSPIN 12", "12-place fixed rotor", 12, 4, 1, 0, (1.5,), 0.050, 30),
    LevelSpec("MICROSPIN 12-X", "mixed tube sizes", 12, 6, 2, 1, (1.5, 2.0), 0.050, 45),
    LevelSpec("BENCHTOP 16", "one bucket is cracked", 16, 8, 2, 2, (1.5, 2.0), 0.045, 55),
    LevelSpec("BENCHTOP 18", "thirds, not halves", 18, 9, 2, 2, (1.5, 2.0, 5.0), 0.045, 65),
    LevelSpec("SWING-24", "swinging bucket rotor", 24, 12, 3, 3, (1.5, 2.0, 5.0), 0.040, 75),
    LevelSpec("SWING-24 HD", "15 mL conicals", 24, 12, 3, 5, (2.0, 5.0, 15.0), 0.040, 80),
    LevelSpec("ULTRA-30", "high speed, low patience", 30, 15, 3, 5, (1.5, 2.0, 5.0, 15.0), 0.035, 90),
    LevelSpec("ULTRA-36", "seven dead positions", 36, 18, 4, 7, (1.5, 2.0, 5.0, 15.0), 0.030, 100),
    LevelSpec("PREP-36", "the one with the 50s", 36, 20, 4, 9, (1.5, 2.0, 5.0, 15.0, 50.0), 0.025, 110),
]

ACC_POINTS = 600     # max points for a clean balance
TIME_POINTS = 400    # max points for beating par
FAIL_PENALTY = 75    # per aborted spin


# --------------------------------------------------------------------------
# Physics
# --------------------------------------------------------------------------
def slot_angle(i: int, n: int) -> float:
    """Angle of slot i, measured from 12 o'clock, clockwise."""
    return -math.pi / 2 + (2 * math.pi * i / n)


def imbalance_vector(loads: List[Optional[float]]) -> Tuple[float, float]:
    n = len(loads)
    x = y = 0.0
    for i, m in enumerate(loads):
        if m:
            a = slot_angle(i, n)
            x += m * math.cos(a)
            y += m * math.sin(a)
    return x, y


def imbalance(loads: List[Optional[float]]) -> float:
    x, y = imbalance_vector(loads)
    return math.hypot(x, y)


def combined(base: List[Optional[float]], player: List[Optional[float]]) -> List[Optional[float]]:
    return [b if b is not None else p for b, p in zip(base, player)]


def tolerance_for(spec: LevelSpec, loads: List[Optional[float]]) -> float:
    total = sum(m for m in loads if m) or 1.0
    return max(0.12, spec.tol_frac * total)


# --------------------------------------------------------------------------
# Level generation
#
# Strategy: build a *known balanced* rotor out of regular polygons of equal
# tubes (a pair 180 deg apart, a triple 120 deg apart, a quad 90 deg apart),
# then lift some tubes back out and hand them to the player. Solvability is
# guaranteed by construction, and the player is free to find a different
# balanced arrangement -- scoring only cares about residual imbalance.
# --------------------------------------------------------------------------
def generate_level(spec: LevelSpec, rng: random.Random):
    n = spec.slots
    group_sizes = [g for g in (2, 3, 4) if n % g == 0]

    for _ in range(600):
        blocked: Set[int] = set(rng.sample(range(n), spec.blocked))
        loads: List[Optional[float]] = [None] * n
        placed = 0

        for _ in range(900):
            if placed == spec.total_tubes:
                break
            g = rng.choice(group_sizes)
            if placed + g > spec.total_tubes:
                continue
            step = n // g
            start = rng.randrange(n)
            idxs = [(start + k * step) % n for k in range(g)]
            if any(i in blocked or loads[i] is not None for i in idxs):
                continue
            m = rng.choice(spec.masses)
            for i in idxs:
                loads[i] = m
            placed += g

        if placed != spec.total_tubes:
            continue

        filled = [i for i in range(n) if loads[i] is not None]
        if len(filled) <= spec.to_place:
            continue

        hand_slots = rng.sample(filled, spec.to_place)
        hand = sorted((loads[i] for i in hand_slots), reverse=True)
        base = list(loads)
        for i in hand_slots:
            base[i] = None

        # A pre-balanced rotor makes the puzzle meaningless.
        if imbalance(base) < 1e-9:
            continue

        return base, blocked, list(hand)

    raise RuntimeError(f"Could not generate level {spec.name}")


# --------------------------------------------------------------------------
# Rotor rendering (the signature element)
# --------------------------------------------------------------------------
def tube_radius(mass: float) -> float:
    return 4.2 + 2.6 * math.sqrt(mass)


def rotor_svg(
    base: List[Optional[float]],
    player: List[Optional[float]],
    blocked: Set[int],
    spinning: bool = False,
    show_needle: bool = True,
    size: int = 380,
) -> str:
    n = len(base)
    cx = cy = size / 2
    ring = size * 0.335
    loads = combined(base, player)

    parts = [
        f'<svg viewBox="0 0 {size} {size}" width="100%" height="{size}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="Centrifuge rotor with {n} positions">'
    ]

    # housing
    parts.append(
        f'<circle cx="{cx}" cy="{cy}" r="{size*0.465}" fill="#10142a" stroke="{STEEL}" stroke-width="2"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{size*0.425}" fill="none" stroke="#22294a" stroke-width="10"/>'
    )

    spin_group = ""
    if spinning:
        spin_group = (
            f'<animateTransform attributeName="transform" attributeType="XML" type="rotate" '
            f'from="0 {cx} {cy}" to="360 {cx} {cy}" dur="0.45s" repeatCount="indefinite"/>'
        )
    parts.append("<g>" + spin_group)

    # rotor plate + spokes
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{ring + 22}" fill="#171c33" stroke="#2b3358" stroke-width="2"/>')
    for i in range(n):
        a = slot_angle(i, n)
        parts.append(
            f'<line x1="{cx}" y1="{cy}" x2="{cx + (ring)*math.cos(a):.1f}" '
            f'y2="{cy + (ring)*math.sin(a):.1f}" stroke="#20263f" stroke-width="1"/>'
        )

    label_r = ring + 30
    for i in range(n):
        a = slot_angle(i, n)
        sx = cx + ring * math.cos(a)
        sy = cy + ring * math.sin(a)
        m = loads[i]

        if i in blocked:
            parts.append(
                f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="11" fill="#1a0f18" stroke="{MAGENTA}" '
                f'stroke-width="1.6" stroke-dasharray="3 2"/>'
                f'<path d="M{sx-4.5:.1f} {sy-4.5:.1f} L{sx+4.5:.1f} {sy+4.5:.1f} '
                f'M{sx+4.5:.1f} {sy-4.5:.1f} L{sx-4.5:.1f} {sy+4.5:.1f}" '
                f'stroke="{MAGENTA}" stroke-width="1.8"/>'
            )
        elif m is None:
            parts.append(
                f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="11" fill="#0e1226" stroke="{STEEL}" stroke-width="1.4"/>'
            )
        else:
            colour = CYAN if player[i] is not None else GREEN
            r = tube_radius(m)
            parts.append(
                f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="{r+3.2:.1f}" fill="#0e1226" stroke="{colour}" stroke-width="1.4"/>'
                f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="{r:.1f}" fill="{colour}" opacity="0.85"/>'
            )

        lx = cx + label_r * math.cos(a)
        ly = cy + label_r * math.sin(a) + 3.5
        parts.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" font-family="IBM Plex Mono, monospace" font-size="10" '
            f'fill="#5a6486" text-anchor="middle">{i}</text>'
        )

    parts.append("</g>")

    # hub
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="16" fill="#0e1226" stroke="{STEEL}" stroke-width="2"/>')

    # imbalance needle
    if show_needle:
        vx, vy = imbalance_vector(loads)
        mag = math.hypot(vx, vy)
        if mag > 1e-9:
            scale = min(ring - 26, 14 + mag * 5.5)
            ex = cx + scale * vx / mag
            ey = cy + scale * vy / mag
            parts.append(
                f'<line x1="{cx}" y1="{cy}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="{MAGENTA}" '
                f'stroke-width="3" stroke-linecap="round"/>'
                f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="4" fill="{MAGENTA}"/>'
            )
        else:
            parts.append(f'<circle cx="{cx}" cy="{cy}" r="7" fill="{GREEN}"/>')

    parts.append("</svg>")
    return "".join(parts)


# --------------------------------------------------------------------------
# Bench scene / cutscene
# --------------------------------------------------------------------------
SCENE_TEMPLATE = """
<style>
  .bench-wrap {
    position: relative; width: 100%; height: 210px; overflow: hidden;
    background: linear-gradient(180deg, #0b0d1a 0%, #131734 78%, #0b0d1a 100%);
    border: 2px solid #2b3358; border-radius: 4px;
    font-family: 'IBM Plex Mono', monospace;
  }
  .bench {
    position: absolute; bottom: 34px; left: 0; height: 130px; display: flex;
    align-items: flex-end;
    animation: walkbench 1.25s cubic-bezier(.5,0,.2,1) forwards;
  }
  @keyframes walkbench {
    from { transform: translateX(__PREV__px); }
    to   { transform: translateX(__CUR__px); }
  }
  .unit { width: 120px; display: flex; flex-direction: column; align-items: center; }
  .fuge { width: 62px; height: 46px; background: #d8dbe8; border: 2px solid #8f96b5;
          border-radius: 6px 6px 3px 3px; position: relative; }
  .fuge.done { background: #2a3350; border-color: #3c456d; }
  .fuge.active { background: #e9ecf7; box-shadow: 0 0 18px rgba(255,182,39,0.35); }
  .lid { position: absolute; top: -8px; left: -3px; width: 68px; height: 12px;
         background: #aeb4d0; border: 2px solid #7b83a6; border-radius: 4px;
         transform-origin: left bottom; }
  .lid.opening { animation: lift 0.55s ease-out 1.35s forwards; }
  @keyframes lift { to { transform: rotate(-58deg); } }
  .win { position: absolute; bottom: 6px; left: 12px; width: 38px; height: 14px;
         background: #0e1226; border-radius: 2px; }
  .led { position: absolute; top: 6px; right: 7px; width: 6px; height: 6px; border-radius: 50%;
         background: #5be36a; }
  .led.off { background: #39405f; }
  .plinth { width: 100%; height: 10px; background: #1b2140; border-top: 2px solid #2b3358; }
  .tag { font-size: 8px; color: #5a6486; margin-top: 6px; letter-spacing: 0.1em; }

  .sci { position: absolute; bottom: 44px; left: 50%; margin-left: -18px; width: 36px; height: 78px; z-index: 3; }
  .sci.walking { animation: bob 0.22s steps(2) 0s 6; }
  @keyframes bob { 50% { transform: translateY(-4px); } }
  .head { width: 20px; height: 18px; background: #f0d2b4; border-radius: 4px; margin: 0 auto; position: relative; }
  .goggles { position: absolute; top: 5px; left: -2px; width: 24px; height: 7px;
             background: #3ff2e0; border: 1px solid #1b2140; border-radius: 3px; }
  .coat { width: 34px; height: 40px; background: #f4f6ff; border: 1px solid #b9bfd8;
          border-radius: 4px 4px 2px 2px; margin: 0 auto; position: relative; }
  .coat:after { content: ''; position: absolute; top: 0; left: 16px; width: 2px; height: 40px; background: #d4d9ea; }
  .legs { width: 26px; height: 18px; background: #2b3358; margin: 0 auto; }

  .floor { position: absolute; bottom: 0; left: 0; right: 0; height: 34px;
           background: repeating-linear-gradient(90deg, #10142a 0 28px, #141935 28px 56px); }
  .caption { position: absolute; top: 8px; left: 0; right: 0; text-align: center;
             font-family: 'Press Start 2P', monospace; font-size: 9px; color: #ffb627;
             opacity: 0; animation: fadein 0.4s ease-out 1.5s forwards; }
  @keyframes fadein { to { opacity: 1; } }
  @media (prefers-reduced-motion: reduce) {
    .bench, .sci, .lid, .caption { animation: none !important; }
    .bench { transform: translateX(__CUR__px); }
    .caption { opacity: 1; }
    .lid.opening { transform: rotate(-58deg); }
  }
</style>
<div class="bench-wrap">
  <div class="bench">__UNITS__</div>
  <div class="sci walking">
    <div class="head"><div class="goggles"></div></div>
    <div class="coat"></div>
    <div class="legs"></div>
  </div>
  <div class="floor"></div>
  <div class="caption">__CAPTION__</div>
</div>
"""


def bench_scene(current: int, previous: int, caption: str, opening: bool) -> str:
    unit_w, width = 120, 700
    units = []
    for i, spec in enumerate(LEVELS):
        state = "done" if i < current else ("active" if i == current else "")
        lid = "lid opening" if (i == current and opening) else "lid"
        led = "led" if i < current else "led off"
        units.append(
            f'<div class="unit">'
            f'<div class="fuge {state}"><div class="{lid}"></div>'
            f'<div class="win"></div><div class="{led}"></div></div>'
            f'<div class="plinth"></div>'
            f'<div class="tag">{i+1:02d}</div>'
            f"</div>"
        )
    cur_off = width / 2 - (current * unit_w + unit_w / 2)
    prev_off = width / 2 - (previous * unit_w + unit_w / 2)
    return (
        SCENE_TEMPLATE.replace("__UNITS__", "".join(units))
        .replace("__PREV__", f"{prev_off:.0f}")
        .replace("__CUR__", f"{cur_off:.0f}")
        .replace("__CAPTION__", caption)
    )


# --------------------------------------------------------------------------
# Leaderboard
#
# Backend order: Google Sheets (persists on Streamlit Cloud) -> local JSON
# (fine for local play, wiped whenever Cloud restarts the container).
# --------------------------------------------------------------------------
LOCAL_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leaderboard.json")
WORKSHEET = "scores"
COLUMNS = ["name", "score", "levels", "seconds", "when"]


@st.cache_resource(show_spinner=False)
def _sheets():
    try:
        from streamlit_gsheets import GSheetsConnection
    except Exception:
        return None
    try:
        if "connections" not in st.secrets or "gsheets" not in st.secrets["connections"]:
            return None
        return st.connection("gsheets", type=GSheetsConnection)
    except Exception:
        return None


def backend_name() -> str:
    return "google sheets" if _sheets() is not None else "local file"


def load_scores() -> List[dict]:
    conn = _sheets()
    if conn is not None:
        try:
            df = conn.read(worksheet=WORKSHEET, ttl=5, usecols=list(range(len(COLUMNS))))
            df = df.dropna(how="all")
            return df.to_dict("records")
        except Exception:
            pass
    try:
        with open(LOCAL_DB, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return []


def save_score(row: dict) -> bool:
    rows = load_scores()
    rows.append(row)
    rows = sorted(rows, key=lambda r: -int(r.get("score", 0)))[:500]

    conn = _sheets()
    if conn is not None:
        try:
            import pandas as pd

            conn.update(worksheet=WORKSHEET, data=pd.DataFrame(rows, columns=COLUMNS))
            return True
        except Exception:
            pass
    try:
        with open(LOCAL_DB, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=1)
        return True
    except Exception:
        return False


def leaderboard_table(rows: List[dict], highlight: Optional[str] = None, top: int = 10) -> str:
    rows = sorted(rows, key=lambda r: -int(r.get("score", 0)))[:top]
    if not rows:
        return '<p class="cc-readout">No scores logged yet. Be the first.</p>'
    out = ['<table class="cc-lb"><tr><th>#</th><th>Operator</th><th>Score</th><th>Levels</th><th>Time</th></tr>']
    for i, r in enumerate(rows, 1):
        me = ' class="me"' if highlight and str(r.get("name")) == highlight else ""
        secs = int(float(r.get("seconds", 0)))
        out.append(
            f"<tr{me}><td class='rank'>{i:02d}</td><td>{r.get('name','???')}</td>"
            f"<td>{int(float(r.get('score',0)))}</td><td>{int(float(r.get('levels',0)))}/{len(LEVELS)}</td>"
            f"<td>{secs//60}:{secs%60:02d}</td></tr>"
        )
    out.append("</table>")
    return "".join(out)


# --------------------------------------------------------------------------
# Game state
# --------------------------------------------------------------------------
def init_state():
    ss = st.session_state
    ss.setdefault("phase", "title")     # title | intro | play | spin | result | gameover
    ss.setdefault("level", 0)
    ss.setdefault("prev_level", 0)
    ss.setdefault("name", "")
    ss.setdefault("scores", [])
    ss.setdefault("fails", 0)
    ss.setdefault("submitted", False)
    ss.setdefault("last_result", None)


def load_level(idx: int):
    ss = st.session_state
    spec = LEVELS[idx]
    rng = random.Random()
    base, blocked, hand = generate_level(spec, rng)
    ss.base = base
    ss.blocked = blocked
    ss.hand = hand
    ss.player = [None] * spec.slots
    ss.fails = 0
    ss.level_start = time.time()


def reset_game():
    for k in ("phase", "level", "prev_level", "scores", "fails", "submitted", "last_result"):
        st.session_state.pop(k, None)
    init_state()


# --------------------------------------------------------------------------
# Screens
# --------------------------------------------------------------------------
def screen_title():
    st.markdown('<div class="cc-title">CENTRIFUGE CHESS</div>', unsafe_allow_html=True)
    st.markdown('<div class="cc-sub">balance the rotor · or clean the ceiling</div>', unsafe_allow_html=True)

    st.markdown(
        f"""<div class="cc-panel">
        <p class="cc-readout" style="text-align:left;line-height:1.9">
        Every tube you drop into a rotor pulls outward when it spins. Balance means the pulls
        cancel: <span class="cc-amber">two tubes opposite</span>, <span class="cc-amber">three at 120&deg;</span>,
        <span class="cc-amber">four at 90&deg;</span> &mdash; or any combination whose forces sum to zero.<br><br>
        The <span style="color:{MAGENTA}">magenta needle</span> shows which way the rotor is currently pulling.
        Shorten it to nothing, close the lid, and move down the bench.<br><br>
        <span style="color:{GREEN}">Green</span> tubes are already loaded and locked.
        <span style="color:{CYAN}">Cyan</span> tubes are yours. Dashed magenta positions are cracked buckets &mdash; unusable.
        </p></div>""",
        unsafe_allow_html=True,
    )

    name = st.text_input("Operator initials", max_chars=12, placeholder="e.g. RSA", key="name_in")
    c1, c2 = st.columns([2, 1])
    with c1:
        if st.button("START SHIFT", use_container_width=True, type="primary"):
            st.session_state.name = (name or "ANON").strip().upper()[:12]
            st.session_state.level = 0
            st.session_state.prev_level = 0
            st.session_state.scores = []
            st.session_state.submitted = False
            st.session_state.game_start = time.time()
            load_level(0)
            st.session_state.phase = "intro"
            st.rerun()
    with c2:
        if st.button("HIGH SCORES", use_container_width=True):
            st.session_state.phase = "scores_only"
            st.rerun()


def screen_intro():
    ss = st.session_state
    spec = LEVELS[ss.level]
    st.markdown(f'<div class="cc-title" style="font-size:1.05rem">{spec.name}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="cc-sub">{spec.subtitle}</div>', unsafe_allow_html=True)
    components.html(
        bench_scene(ss.level, ss.prev_level, f"LEVEL {ss.level+1} &mdash; LID OPEN", opening=True),
        height=222,
    )
    time.sleep(2.3)
    ss.phase = "play"
    ss.level_start = time.time()
    st.rerun()


def hud(spec: LevelSpec, resid: float, tol: float):
    total = sum(st.session_state.scores)
    elapsed = int(time.time() - st.session_state.level_start)
    st.markdown(
        f"""<div class="cc-panel"><div class="cc-hud">
        <div><span class="k">LEVEL</span>{st.session_state.level+1:02d}/{len(LEVELS)}</div>
        <div><span class="k">SCORE</span>{total}</div>
        <div><span class="k">TUBES LEFT</span>{len(st.session_state.hand)}</div>
        <div><span class="k">ABORTS</span>{st.session_state.fails}</div>
        <div><span class="k">PAR</span>{spec.par_seconds}s</div>
        </div></div>""",
        unsafe_allow_html=True,
    )


def screen_play():
    ss = st.session_state
    spec = LEVELS[ss.level]
    loads = combined(ss.base, ss.player)
    resid = imbalance(loads)
    tol = tolerance_for(spec, loads)

    st.markdown(f'<div class="cc-title" style="font-size:1.05rem">{spec.name}</div>', unsafe_allow_html=True)
    hud(spec, resid, tol)

    st.markdown(rotor_svg(ss.base, ss.player, ss.blocked), unsafe_allow_html=True)

    if resid < 1e-9:
        state = f'<span class="cc-ok">BALANCED &mdash; residual 0.000</span>'
    elif resid <= tol and not ss.hand:
        state = f'<span class="cc-ok">WITHIN TOLERANCE &mdash; residual {resid:.3f} / {tol:.3f}</span>'
    else:
        state = f'<span class="cc-bad">IMBALANCE {resid:.3f}</span> <span style="color:#5a6486">/ limit {tol:.3f}</span>'
    st.markdown(f'<p class="cc-readout">{state}</p>', unsafe_allow_html=True)

    # --- tube tray -------------------------------------------------------
    if ss.hand:
        st.markdown('<p class="cc-readout" style="text-align:left">TUBE TRAY</p>', unsafe_allow_html=True)
        pick = st.radio(
            "Select a tube",
            options=list(range(len(ss.hand))),
            format_func=lambda i: f"{ss.hand[i]:g} g",
            horizontal=True,
            label_visibility="collapsed",
            key=f"tray_{ss.level}_{len(ss.hand)}",
        )
    else:
        pick = None
        st.markdown(
            '<p class="cc-readout" style="text-align:left">TUBE TRAY &mdash; empty. Close the lid.</p>',
            unsafe_allow_html=True,
        )

    # --- slot pad --------------------------------------------------------
    st.markdown('<p class="cc-readout" style="text-align:left">ROTOR POSITIONS</p>', unsafe_allow_html=True)
    per_row = 12
    n = spec.slots
    for row_start in range(0, n, per_row):
        row = list(range(row_start, min(row_start + per_row, n)))
        cols = st.columns(len(row))
        for c, i in zip(cols, row):
            with c:
                if i in ss.blocked:
                    st.button("✖", key=f"s{ss.level}_{i}", disabled=True, use_container_width=True,
                              help="Cracked bucket")
                elif ss.base[i] is not None:
                    st.button("▪", key=f"s{ss.level}_{i}", disabled=True, use_container_width=True,
                              help=f"Locked: {ss.base[i]:g} g")
                elif ss.player[i] is not None:
                    if st.button("↩", key=f"s{ss.level}_{i}", use_container_width=True,
                                 help=f"Remove {ss.player[i]:g} g from position {i}"):
                        ss.hand.append(ss.player[i])
                        ss.hand.sort(reverse=True)
                        ss.player[i] = None
                        st.rerun()
                else:
                    if st.button(str(i), key=f"s{ss.level}_{i}", disabled=not ss.hand,
                                 use_container_width=True, help=f"Position {i}"):
                        ss.player[i] = ss.hand.pop(pick if pick is not None else 0)
                        st.rerun()

    st.write("")
    c1, c2 = st.columns([2, 1])
    with c1:
        if st.button("CLOSE LID AND SPIN", use_container_width=True, type="primary",
                     disabled=bool(ss.hand)):
            ss.phase = "spin"
            st.rerun()
    with c2:
        if st.button("CLEAR TRAY", use_container_width=True):
            for i in range(n):
                if ss.player[i] is not None:
                    ss.hand.append(ss.player[i])
                    ss.player[i] = None
            ss.hand.sort(reverse=True)
            st.rerun()


def screen_spin():
    ss = st.session_state
    spec = LEVELS[ss.level]
    loads = combined(ss.base, ss.player)
    resid = imbalance(loads)
    tol = tolerance_for(spec, loads)

    st.markdown('<div class="cc-title" style="font-size:1.05rem">SPINNING UP</div>', unsafe_allow_html=True)
    st.markdown(
        rotor_svg(ss.base, ss.player, ss.blocked, spinning=True, show_needle=False),
        unsafe_allow_html=True,
    )
    st.markdown('<p class="cc-readout">rotor at speed…</p>', unsafe_allow_html=True)
    time.sleep(2.0)

    if resid > tol:
        ss.fails += 1
        ss.last_result = ("fail", resid, tol, 0, 0, 0)
    else:
        elapsed = time.time() - ss.level_start
        acc = ACC_POINTS * (1 - min(1.0, resid / tol))
        speed = TIME_POINTS * max(0.0, (spec.par_seconds - elapsed) / spec.par_seconds)
        pts = max(0, round(acc + speed - FAIL_PENALTY * ss.fails))
        ss.scores.append(pts)
        ss.last_result = ("pass", resid, tol, round(acc), round(speed), pts)

    ss.phase = "result"
    st.rerun()


def screen_result():
    ss = st.session_state
    spec = LEVELS[ss.level]
    kind, resid, tol, acc, speed, pts = ss.last_result

    if kind == "fail":
        st.markdown('<div class="cc-title" style="font-size:1.05rem;color:#ff3d8b">ROTOR ALARM</div>',
                    unsafe_allow_html=True)
        st.markdown(
            f'<div class="cc-panel"><p class="cc-readout" style="text-align:left">'
            f'The rotor tripped its imbalance sensor at <span class="cc-bad">{resid:.3f}</span>, '
            f'over the <span class="cc-amber">{tol:.3f}</span> limit. Spin aborted, lid released, '
            f'{FAIL_PENALTY} points docked.<br><br>Pull the tubes out and try a different arrangement.'
            f'</p></div>',
            unsafe_allow_html=True,
        )
        st.markdown(rotor_svg(ss.base, ss.player, ss.blocked), unsafe_allow_html=True)
        if st.button("REOPEN LID", use_container_width=True, type="primary"):
            ss.phase = "play"
            st.rerun()
        return

    st.markdown('<div class="cc-title" style="font-size:1.05rem;color:#5be36a">CLEAN SPIN</div>',
                unsafe_allow_html=True)
    st.markdown(
        f"""<div class="cc-panel"><div class="cc-hud">
        <div><span class="k">RESIDUAL</span>{resid:.3f}</div>
        <div><span class="k">ACCURACY</span>{acc}</div>
        <div><span class="k">SPEED</span>{speed}</div>
        <div><span class="k">ABORTS</span>-{FAIL_PENALTY*ss.fails}</div>
        <div><span class="k">LEVEL</span>{pts}</div>
        </div></div>""",
        unsafe_allow_html=True,
    )
    st.markdown(rotor_svg(ss.base, ss.player, ss.blocked), unsafe_allow_html=True)

    last = ss.level + 1 >= len(LEVELS)
    label = "END SHIFT" if last else "NEXT CENTRIFUGE"
    if st.button(label, use_container_width=True, type="primary"):
        if last:
            ss.phase = "gameover"
        else:
            ss.prev_level = ss.level
            ss.level += 1
            load_level(ss.level)
            ss.phase = "intro"
        st.rerun()


def screen_gameover():
    ss = st.session_state
    total = sum(ss.scores)
    shift = int(time.time() - ss.get("game_start", time.time()))

    st.markdown('<div class="cc-title">SHIFT COMPLETE</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="cc-sub">operator {ss.name}</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="cc-panel"><div class="cc-hud">'
        f'<div><span class="k">FINAL SCORE</span>{total}</div>'
        f'<div><span class="k">LEVELS</span>{len(ss.scores)}/{len(LEVELS)}</div>'
        f'<div><span class="k">BEST LEVEL</span>{max(ss.scores) if ss.scores else 0}</div>'
        f'<div><span class="k">SHIFT TIME</span>{shift//60}:{shift%60:02d}</div>'
        f"</div></div>",
        unsafe_allow_html=True,
    )

    if not ss.submitted:
        row = {
            "name": ss.name,
            "score": total,
            "levels": len(ss.scores),
            "seconds": shift,
            "when": time.strftime("%Y-%m-%d"),
        }
        save_score(row)
        ss.submitted = True

    st.markdown('<p class="cc-readout" style="text-align:left">GLOBAL TOP 10</p>', unsafe_allow_html=True)
    st.markdown(leaderboard_table(load_scores(), highlight=ss.name), unsafe_allow_html=True)
    st.markdown(f'<p class="cc-readout">scores stored in: {backend_name()}</p>', unsafe_allow_html=True)

    if st.button("NEW SHIFT", use_container_width=True, type="primary"):
        reset_game()
        st.rerun()


def screen_scores_only():
    st.markdown('<div class="cc-title">HIGH SCORES</div>', unsafe_allow_html=True)
    st.markdown(leaderboard_table(load_scores()), unsafe_allow_html=True)
    st.markdown(f'<p class="cc-readout">scores stored in: {backend_name()}</p>', unsafe_allow_html=True)
    if st.button("BACK", use_container_width=True):
        st.session_state.phase = "title"
        st.rerun()


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
    init_state()
    phase = st.session_state.phase
    {
        "title": screen_title,
        "intro": screen_intro,
        "play": screen_play,
        "spin": screen_spin,
        "result": screen_result,
        "gameover": screen_gameover,
        "scores_only": screen_scores_only,
    }[phase]()


if __name__ == "__main__":
    main()
