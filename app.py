"""
CENTRIFUGE CHESS  v2
A retro-arcade puzzle game about balancing centrifuge rotors.

Run locally:   streamlit run app.py
Deploy:        push to GitHub -> share.streamlit.io
"""

from __future__ import annotations

import inspect
import io
import json
import math
import os
import random
import time
import wave
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Centrifuge Chess",
    page_icon="🧪",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Streamlit renamed the full-width kwarg (use_container_width -> width="stretch").
# Detect it at import so the game runs warning-free on either generation.
def _wide(fn) -> dict:
    params = inspect.signature(fn).parameters
    return {"width": "stretch"} if "width" in params else {"use_container_width": True}


BTN = _wide(st.button)
FIG = _wide(st.plotly_chart)


# ==========================================================================
# 1. ZONES  — the bench changes character as you walk down it
# ==========================================================================
@dataclass(frozen=True)
class Zone:
    key: str
    name: str
    sky_top: str      # back wall, upper
    sky_bot: str      # back wall, lower
    accent: str       # zone signature colour
    plate: str        # rotor plate
    plate_edge: str   # rotor rim
    housing: str      # centrifuge body on the bench
    floor_a: str
    floor_b: str
    shell: str        # centrifuge silhouette: box | drum | tower | vault


TEACHING = Zone("teach", "TEACHING LAB", "#141a3a", "#0d1128", "#57b6ff",
                "#1a2145", "#3a4780", "#d8dbe8", "#10142a", "#141935", "box")
CORE = Zone("core", "CORE FACILITY", "#2a1c33", "#150e20", "#ffb627",
            "#2a2038", "#6b5330", "#e6dcc8", "#1a1224", "#20172c", "drum")
COLD = Zone("cold", "COLD ROOM", "#0d2733", "#061620", "#3ff2e0",
            "#0f2c38", "#2f6f7a", "#c9e6ec", "#08202b", "#0c2a36", "tower")
PREP = Zone("prep", "PREP SUITE", "#33131f", "#1c0810", "#ff6b3d",
            "#2e1420", "#7d3b2c", "#d6c2be", "#1d0c14", "#26111a", "vault")
ULTRA_ZONE = Zone("ultra", "ULTRACENTRIFUGE SUITE", "#3a0a16", "#160208", "#ff3d8b",
                  "#2b0812", "#8f1235", "#b9a6ad", "#180309", "#210610", "vault")

AMBER = "#ffb627"
CYAN = "#3ff2e0"
GREEN = "#5be36a"
MAGENTA = "#ff3d8b"
STEEL = "#5a6486"
BONE = "#e8e6f0"
DIM = "#5a6486"


# ==========================================================================
# 2. LEVELS
# ==========================================================================
@dataclass(frozen=True)
class LevelSpec:
    name: str
    subtitle: str
    slots: int
    total_tubes: int
    to_place: int
    blocked: int
    masses: Tuple[float, ...]
    tol_frac: float
    par_seconds: int
    zone: Zone
    style: int = 0            # 0 fixed-angle, 1 swinging bucket, 2 drilled plate
    time_limit: int = 0       # 0 = untimed
    sudden_death: bool = False


LEVELS: List[LevelSpec] = [
    LevelSpec("MICROSPIN 6", "personal microfuge", 6, 2, 1, 0, (1.5,), 0.55, 25, TEACHING, 0),
    LevelSpec("MICROSPIN 12", "12-place fixed rotor", 12, 4, 1, 0, (1.5,), 0.55, 30, TEACHING, 2),
    LevelSpec("MICROSPIN 12-X", "mixed tube sizes", 12, 6, 2, 1, (1.5, 2.0), 0.55, 45, TEACHING, 0),
    LevelSpec("BENCHTOP 16", "one bucket is cracked", 16, 8, 2, 2, (1.5, 2.0), 0.50, 55, CORE, 1),
    LevelSpec("BENCHTOP 18", "thirds, not halves", 18, 9, 2, 2, (1.5, 2.0, 5.0), 0.50, 65, CORE, 2),
    LevelSpec("SWING-24", "swinging bucket rotor", 24, 12, 3, 3, (1.5, 2.0, 5.0), 0.50, 75, CORE, 1),
    LevelSpec("SWING-24 HD", "15 mL conicals", 24, 12, 3, 5, (2.0, 5.0, 15.0), 0.45, 80, COLD, 1),
    LevelSpec("ULTRA-30", "high speed, low patience", 30, 15, 3, 5, (1.5, 2.0, 5.0, 15.0), 0.45, 90, COLD, 0),
    LevelSpec("ULTRA-36", "seven dead positions", 36, 18, 4, 7, (1.5, 2.0, 5.0, 15.0), 0.40, 100, COLD, 2),
    LevelSpec("PREP-36", "the one with the 50s", 36, 20, 4, 9, (1.5, 2.0, 5.0, 15.0, 50.0), 0.40, 110, PREP, 1),
]

ULTRA_SPEC = LevelSpec(
    "VTi-24 VACUUM", "one spin. no meter. no second chance.",
    24, 12, 3, 2, (5.0, 15.0), 0.15, 45, ULTRA_ZONE,
    style=1, time_limit=45, sudden_death=True,
)

ACC_POINTS = 600
TIME_POINTS = 400
FAIL_PENALTY = 75
ULTRA_BONUS = 1500
START_LIVES = 3
ULTRA_CHANCE = 0.38          # per eligible bench transition
ULTRA_MAX = 2                # per run
ULTRA_EARLIEST = 3           # after finishing this level index


# ==========================================================================
# 3. PHYSICS
# ==========================================================================
def slot_angle(i: int, n: int) -> float:
    """Angle of slot i measured from 12 o'clock, going clockwise."""
    return -math.pi / 2 + (2 * math.pi * i / n)


def slot_xy(i: int, n: int, r: float = 1.0) -> Tuple[float, float]:
    a = slot_angle(i, n)
    return r * math.cos(a), -r * math.sin(a)   # screen-up is +y in plotly


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


def tolerance_for(spec: LevelSpec) -> float:
    """Smallest mistake physically possible on this rotor is moving the lightest
    tube one slot: 2*m*sin(pi/n). Tolerance sits below that, so any real error
    trips the alarm at any rotor size, while float noise (~1e-16) always passes."""
    m = min(spec.masses)
    smallest_error = 2 * m * math.sin(math.pi / spec.slots)
    return spec.tol_frac * smallest_error


# ==========================================================================
# 4. LEVEL GENERATION
# Build a known-balanced rotor from regular polygons, then lift tubes back
# out into the player's tray. Solvability is guaranteed by construction.
# ==========================================================================
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

        if imbalance(base) < 1e-9:
            continue
        return base, blocked, list(hand)

    raise RuntimeError(f"Could not generate level {spec.name}")


# ==========================================================================
# 5. SOUND  — synthesised in-process, no asset files
# Rendered through st.audio(autoplay=True) in the top-level document, which
# inherits the page's user activation, so it is not blocked after first click.
# ==========================================================================
RATE = 22050


def _pcm(sig: np.ndarray) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((np.clip(sig, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def _t(dur: float) -> np.ndarray:
    return np.linspace(0, dur, int(RATE * dur), endpoint=False)


def _square(freq, t, duty=0.5):
    return np.where((freq * t) % 1.0 < duty, 1.0, -1.0)


@st.cache_data(show_spinner=False)
def sfx_library() -> Dict[str, np.ndarray]:
    lib: Dict[str, np.ndarray] = {}

    # blip: tube seated
    t = _t(0.06)
    lib["place"] = (0.25 * _square(880, t) * np.exp(-28 * t))

    # error buzz: illegal slot
    t = _t(0.10)
    lib["nope"] = (0.22 * _square(120, t, 0.3) * np.exp(-14 * t))

    # spin-up: rising whine + air
    t = _t(1.9)
    sweep = 140 + 900 * (t / t[-1]) ** 1.7
    body = 0.30 * np.sin(2 * np.pi * np.cumsum(sweep) / RATE)
    air = 0.10 * np.random.default_rng(7).normal(0, 1, t.size) * (t / t[-1])
    env = np.minimum(1.0, t / 0.25) * np.minimum(1.0, (t[-1] - t) / 0.2 + 0.2)
    lib["spin"] = (body + air) * env

    # clean spin: rising arpeggio
    notes, seg = [523, 659, 784, 1047], _t(0.11)
    lib["good"] = (np.concatenate(
        [0.26 * _square(f, seg, 0.5) * np.exp(-9 * seg) for f in notes]))

    # alarm: harsh two-tone
    a, blk = [], _t(0.16)
    for f in (740, 560) * 3:
        a.append(0.30 * _square(f, blk, 0.35) * np.minimum(1, (blk[-1] - blk) * 14))
    lib["alarm"] = (np.concatenate(a))

    # explosion: filtered noise burst with a low thump
    t = _t(1.5)
    rng = np.random.default_rng(3)
    noise = rng.normal(0, 1, t.size)
    smooth = np.convolve(noise, np.ones(40) / 40, mode="same")
    thump = np.sin(2 * np.pi * np.cumsum(np.linspace(90, 25, t.size)) / RATE)
    lib["boom"] = ((0.55 * smooth + 0.45 * thump) * np.exp(-3.2 * t))

    # ultracentrifuge PA alert
    a, blk = [], _t(0.22)
    for f in (1046, 784, 1046, 784):
        a.append(0.26 * _square(f, blk, 0.5) * np.minimum(1, (blk[-1] - blk) * 10))
    lib["alert"] = (np.concatenate(a))

    # game over: descending
    a, seg = [], _t(0.16)
    for f in (523, 415, 330, 220, 165):
        a.append(0.26 * _square(f, seg, 0.4) * np.exp(-5 * seg))
    lib["over"] = (np.concatenate(a))
    return lib


def play(name: str):
    """Queue an effect for the next rerun (used right before st.rerun())."""
    st.session_state.sfx = name


def play_now(name: str):
    """Render an effect immediately, for screens that then sleep."""
    if st.session_state.get("muted"):
        return
    sig = sfx_library().get(name)
    if sig is None:
        return
    # A random silent tail changes the bytes so the browser sees a new element
    # and replays it, instead of reusing the cached one.
    tail = np.zeros(random.randint(1, 700))
    st.audio(_pcm(np.concatenate([sig, tail])), format="audio/wav", autoplay=True)


def emit_sound():
    name = st.session_state.pop("sfx", None)
    if name:
        play_now(name)


# ==========================================================================
# 6. STYLES
# ==========================================================================
GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&family=IBM+Plex+Mono:wght@400;600&display=swap');

/* --- reclaim the top of the page from Streamlit's chrome --- */
#MainMenu, header[data-testid="stHeader"], footer,
[data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], [data-testid="stAppDeployButton"] {
    display: none !important;
    visibility: hidden !important;
    height: 0 !important;
}
[data-testid="stAudio"] { position: fixed; left: -9999px; width: 1px; height: 1px; }
.block-container { padding-top: 0.6rem !important; padding-bottom: 3rem; max-width: 820px; }

.stApp { background: #07080f; color: #e8e6f0; }
h1, h2, h3 { font-family: 'Press Start 2P', monospace !important; }
body, p, li, div[data-testid="stMarkdownContainer"] { font-family: 'IBM Plex Mono', monospace; }

.cc-strip {
    font-family: 'Press Start 2P', monospace; font-size: 0.62rem;
    color: #ffb627; text-align: center; letter-spacing: 0.05em;
    padding: 0.35rem 0; margin-bottom: 0.5rem;
}
.cc-panel {
    background: rgba(12,16,34,0.86); border: 2px solid #2b3358;
    border-radius: 4px; padding: 0.7rem 0.95rem; margin-bottom: 0.7rem;
}
.cc-hud { display: flex; justify-content: space-between; gap: 0.4rem;
          font-family: 'Press Start 2P', monospace; font-size: 0.58rem; color: #ffb627; }
.cc-hud span.k { color: #5a6486; display: block; margin-bottom: 6px; font-size: 0.5rem; }
.cc-readout { font-family: 'IBM Plex Mono', monospace; font-size: 0.8rem;
              color: #5a6486; text-align: center; letter-spacing: 0.05em; }
.cc-ok { color: #5be36a; } .cc-bad { color: #ff3d8b; } .cc-amber { color: #ffb627; }

.stButton > button {
    font-family: 'IBM Plex Mono', monospace !important; font-weight: 600;
    background: #161c38; color: #e8e6f0; border: 1px solid #38416e;
    border-radius: 3px; padding: 0.3rem 0.1rem; transition: none;
}
.stButton > button:hover { background: #ffb627; color: #07080f; border-color: #ffb627; }
.stButton > button:disabled { background: #0f1226; color: #333a58; border-color: #1c2240; }
.stButton > button:focus-visible { outline: 2px solid #3ff2e0; outline-offset: 2px; }
.stRadio label { font-family: 'IBM Plex Mono', monospace !important; }

table.cc-lb { width: 100%; border-collapse: collapse;
              font-family: 'IBM Plex Mono', monospace; font-size: 0.82rem; }
table.cc-lb th { text-align: left; color: #5a6486; font-size: 0.64rem;
                 text-transform: uppercase; letter-spacing: 0.14em;
                 border-bottom: 1px solid #2b3358; padding: 6px 8px; }
table.cc-lb td { padding: 6px 8px; border-bottom: 1px solid #191e38; }
table.cc-lb tr.me td { color: #3ff2e0; }
table.cc-lb td.rank { color: #ffb627; }

@media (prefers-reduced-motion: reduce) { * { animation: none !important; } }
</style>
"""

# Shared scene chrome: scanlines, vignette, sprite parts.
SCENE_BASE = """
<style>
 @import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&family=IBM+Plex+Mono:wght@400;600&display=swap');
 * { box-sizing: border-box; }
 .stage { position: relative; width: 100%; height: __H__px; overflow: hidden;
          border: 2px solid #2b3358; border-radius: 4px;
          font-family: 'IBM Plex Mono', monospace;
          background: linear-gradient(180deg, __SKYTOP__ 0%, __SKYBOT__ 100%); }
 .scan { position: absolute; inset: 0; z-index: 9; pointer-events: none;
         background: repeating-linear-gradient(180deg, rgba(0,0,0,0.22) 0 1px, transparent 1px 3px); }
 .vig { position: absolute; inset: 0; z-index: 8; pointer-events: none;
        background: radial-gradient(ellipse at 50% 45%, transparent 45%, rgba(0,0,0,0.65) 100%); }
 .floor { position: absolute; bottom: 0; left: 0; right: 0; height: 30px; z-index: 1;
          background: repeating-linear-gradient(90deg, __FLOORA__ 0 26px, __FLOORB__ 26px 52px); }
 .shelf { position: absolute; height: 5px; background: rgba(255,255,255,0.09); z-index: 0; }
 .jar { position: absolute; bottom: 5px; width: 9px; border-radius: 2px 2px 1px 1px; z-index: 0; }
 .lamp { position: absolute; top: 0; height: 4px; background: __ACCENT__; opacity: 0.5; z-index: 0;
         animation: flick 5s steps(1) infinite; }
 @keyframes flick { 0%,88%,100% { opacity: 0.5; } 90% { opacity: 0.12; } 93% { opacity: 0.55; } }
 .head { width: 20px; height: 18px; background: #f0d2b4; border-radius: 4px; margin: 0 auto; position: relative; }
 .goggles { position: absolute; top: 5px; left: -2px; width: 24px; height: 7px;
            background: __ACCENT__; border: 1px solid #10142a; border-radius: 3px; }
 .coat { width: 34px; height: 38px; background: #f4f6ff; border: 1px solid #b9bfd8;
         border-radius: 4px 4px 2px 2px; margin: 0 auto; position: relative; }
 .coat:after { content:''; position:absolute; top:0; left:16px; width:2px; height:38px; background:#d4d9ea; }
 .legs { width: 26px; height: 16px; background: #2b3358; margin: 0 auto; }
 .caption { position: absolute; top: 10px; left: 0; right: 0; text-align: center; z-index: 10;
            font-family: 'Press Start 2P', monospace; font-size: 10px; color: __ACCENT__;
            text-shadow: 0 0 10px currentColor; }
</style>
"""


def scene_shell(height: int, zone: Zone, inner: str) -> str:
    css = (SCENE_BASE
           .replace("__H__", str(height))
           .replace("__SKYTOP__", zone.sky_top)
           .replace("__SKYBOT__", zone.sky_bot)
           .replace("__FLOORA__", zone.floor_a)
           .replace("__FLOORB__", zone.floor_b)
           .replace("__ACCENT__", zone.accent))
    return css + f'<div class="stage">{inner}<div class="floor"></div><div class="vig"></div><div class="scan"></div></div>'


def backdrop(zone: Zone, seed: int = 0) -> str:
    """Shelves, reagent bottles and a strip light — dressing for the back wall."""
    rng = random.Random(seed)
    bits = ['<div class="lamp" style="left:6%;width:38%"></div>',
            '<div class="lamp" style="left:56%;width:32%"></div>']
    for sy, sx, sw in ((34, 4, 30), (34, 62, 33), (74, 20, 26)):
        bits.append(f'<div class="shelf" style="top:{sy}px;left:{sx}%;width:{sw}%"></div>')
        for k in range(6):
            h = rng.randint(10, 20)
            col = rng.choice([zone.accent, "#5be36a", "#ffb627", "#ff3d8b", "#8fa0d8"])
            bits.append(
                f'<div class="jar" style="left:calc({sx}% + {6+k*15}px);bottom:auto;top:{sy-h}px;'
                f'height:{h}px;background:{col};opacity:0.55"></div>')
    return "".join(bits)


def fuge_sprite(zone: Zone, state: str, lid_open: bool, idx: int) -> str:
    """A centrifuge on the bench. Silhouette varies by zone."""
    shell = zone.shell
    body = zone.housing if state != "done" else "#2a3350"
    glow = "box-shadow:0 0 20px rgba(255,182,39,0.4);" if state == "active" else ""
    lid_anim = "animation: lift 0.5s ease-out 1.3s forwards;" if lid_open else ""
    led = GREEN if state == "done" else ("#39405f" if state == "todo" else zone.accent)

    if shell == "box":
        geo, lidgeo = "width:60px;height:42px;border-radius:5px 5px 3px 3px;", "width:66px;height:11px;top:-8px;left:-3px;"
    elif shell == "drum":
        geo, lidgeo = "width:64px;height:48px;border-radius:50% 50% 6px 6px;", "width:70px;height:13px;top:-9px;left:-3px;border-radius:50%;"
    elif shell == "tower":
        geo, lidgeo = "width:52px;height:64px;border-radius:4px;", "width:58px;height:10px;top:-7px;left:-3px;"
    else:
        geo, lidgeo = "width:70px;height:52px;border-radius:3px;", "width:76px;height:14px;top:-10px;left:-3px;"

    stripes = ("background-image:repeating-linear-gradient(45deg,#ff3d8b 0 6px,transparent 6px 12px);"
               if shell == "vault" else "")
    return (
        f'<div class="unit">'
        f'<div class="fuge" style="{geo}background:{body};border:2px solid {zone.plate_edge};'
        f'position:relative;{glow}{stripes}">'
        f'<div style="position:absolute;{lidgeo}background:{zone.housing};border:2px solid {zone.plate_edge};'
        f'border-radius:4px;transform-origin:left bottom;{lid_anim}"></div>'
        f'<div style="position:absolute;bottom:6px;left:11px;width:34px;height:13px;background:#080a16;border-radius:2px"></div>'
        f'<div style="position:absolute;top:6px;right:7px;width:6px;height:6px;border-radius:50%;background:{led}"></div>'
        f'</div>'
        f'<div style="width:100%;height:9px;background:{zone.plate};border-top:2px solid {zone.plate_edge}"></div>'
        f'<div style="font-size:8px;color:#5a6486;margin-top:5px;letter-spacing:0.1em">{idx+1:02d}</div>'
        f"</div>"
    )


# ==========================================================================
# 7. SCENES
# ==========================================================================
def scene_attract() -> str:
    z = TEACHING
    rng = random.Random(11)
    bub = "".join(
        f'<div style="position:absolute;left:{rng.randint(4,92)}%;bottom:{rng.randint(34,52)}px;'
        f'width:5px;height:5px;border-radius:50%;background:{rng.choice([CYAN,GREEN,AMBER])};opacity:0.7;'
        f'animation:rise {rng.uniform(2.4,4.6):.1f}s linear {rng.uniform(0,3):.1f}s infinite"></div>'
        for _ in range(14))
    fuges = "".join(fuge_sprite(z, "active" if i == 1 else "todo", False, i) for i in range(3))
    inner = f"""
    <style>
      @keyframes rise {{ from {{ transform: translateY(0); opacity:.8 }} to {{ transform: translateY(-70px); opacity:0 }} }}
      @keyframes idle {{ 0%,100% {{ transform: translateY(0) }} 50% {{ transform: translateY(-3px) }} }}
      @keyframes spinwin {{ to {{ transform: rotate(360deg) }} }}
      @keyframes glowpulse {{ 0%,100% {{ text-shadow:0 0 12px #ffb627,0 0 30px rgba(255,182,39,.5); }}
                              50% {{ text-shadow:0 0 22px #ffb627,0 0 55px rgba(255,182,39,.85); }} }}
      @keyframes blink {{ 0%,49% {{ opacity:1 }} 50%,100% {{ opacity:0 }} }}
      .unit {{ width:104px; display:flex; flex-direction:column; align-items:center; }}
      .logo {{ position:absolute; top:34px; left:0; right:0; text-align:center; z-index:7;
               font-family:'Press Start 2P',monospace; color:#ffb627; animation:glowpulse 2.6s ease-in-out infinite; }}
      .logo .l1 {{ font-size:26px; display:block; letter-spacing:2px; }}
      .logo .l2 {{ font-size:26px; display:block; letter-spacing:2px; margin-top:10px; color:#3ff2e0;
                   text-shadow:0 0 12px #3ff2e0,0 0 30px rgba(63,242,224,.5); }}
      .tag {{ position:absolute; top:126px; left:0; right:0; text-align:center; z-index:7;
              font-family:'IBM Plex Mono',monospace; font-size:11px; color:#8fa0d8; letter-spacing:.34em; }}
      .ins {{ position:absolute; bottom:44px; left:0; right:0; text-align:center; z-index:7;
              font-family:'Press Start 2P',monospace; font-size:9px; color:#5be36a; animation:blink 1.1s steps(1) infinite; }}
      .row {{ position:absolute; bottom:30px; left:0; right:0; display:flex; justify-content:center; gap:26px; z-index:2; }}
      .sci2 {{ position:absolute; bottom:38px; left:calc(50% + 150px); width:36px; z-index:3; animation:idle 2.2s ease-in-out infinite; }}
    </style>
    {backdrop(z, 5)}
    {bub}
    <div class="row">{fuges}</div>
    <div class="sci2"><div class="head"><div class="goggles"></div></div><div class="coat"></div><div class="legs"></div></div>
    <div class="logo"><span class="l1">CENTRIFUGE</span><span class="l2">CHESS</span></div>
    <div class="tag">BALANCE  OR  BURN</div>
    <div class="ins">&#9654; INSERT SAMPLE TO START</div>
    """
    return scene_shell(330, z, inner)


def scene_walk(current: int, previous: int, zone: Zone, caption: str) -> str:
    unit_w, width = 104, 760
    units = "".join(
        fuge_sprite(LEVELS[i].zone,
                    "done" if i < current else ("active" if i == current else "todo"),
                    i == current, i)
        for i in range(len(LEVELS)))
    cur = width / 2 - (current * unit_w + unit_w / 2)
    prev = width / 2 - (previous * unit_w + unit_w / 2)
    inner = f"""
    <style>
      .unit {{ width:{unit_w}px; display:flex; flex-direction:column; align-items:center; }}
      .bench {{ position:absolute; bottom:32px; left:0; display:flex; align-items:flex-end; z-index:2;
                animation: walkb 1.3s cubic-bezier(.5,0,.2,1) forwards; }}
      @keyframes walkb {{ from {{ transform: translateX({prev:.0f}px) }} to {{ transform: translateX({cur:.0f}px) }} }}
      @keyframes lift {{ to {{ transform: rotate(-58deg) }} }}
      @keyframes bob {{ 50% {{ transform: translateY(-5px) }} }}
      @keyframes fadein {{ to {{ opacity:1 }} }}
      .sci {{ position:absolute; bottom:40px; left:50%; margin-left:-18px; width:36px; z-index:4;
              animation: bob .2s steps(2) 0s 7; }}
      .cap2 {{ opacity:0; animation: fadein .4s ease-out 1.5s forwards; }}
    </style>
    {backdrop(zone, current + 3)}
    <div class="bench">{units}</div>
    <div class="sci"><div class="head"><div class="goggles"></div></div><div class="coat"></div><div class="legs"></div></div>
    <div class="caption cap2">{caption}</div>
    """
    return scene_shell(230, zone, inner)


def scene_spin(zone: Zone, n: int) -> str:
    spokes = "".join(
        f'<div style="position:absolute;left:50%;top:50%;width:2px;height:52px;background:{zone.plate_edge};'
        f'transform-origin:top center;transform:rotate({i*360/n}deg)"></div>' for i in range(n))
    inner = f"""
    <style>
      @keyframes whirl {{ to {{ transform: rotate(360deg) }} }}
      @keyframes shudder {{ 0%,100% {{ transform:translate(0,0) }} 25% {{ transform:translate(-1px,1px) }}
                            75% {{ transform:translate(1px,-1px) }} }}
      .drum {{ position:absolute; left:50%; top:50%; width:150px; height:150px; margin:-75px 0 0 -75px;
               border-radius:50%; background:{zone.plate}; border:4px solid {zone.plate_edge}; z-index:3;
               animation: shudder .09s linear infinite; }}
      .rot {{ position:absolute; inset:0; animation: whirl .32s linear infinite; }}
      .hub {{ position:absolute; left:50%; top:50%; width:24px; height:24px; margin:-12px 0 0 -12px;
              border-radius:50%; background:#080a16; border:2px solid {zone.plate_edge}; z-index:5; }}
    </style>
    {backdrop(zone, 9)}
    <div class="drum"><div class="rot">{spokes}</div><div class="hub"></div></div>
    <div class="caption">ROTOR AT SPEED&hellip;</div>
    """
    return scene_shell(230, zone, inner)


def scene_explode(zone: Zone, lethal: bool) -> str:
    rng = random.Random(4)
    shards = "".join(
        f'<div style="position:absolute;left:50%;top:48%;width:{rng.randint(4,9)}px;height:{rng.randint(4,11)}px;'
        f'background:{rng.choice([CYAN,GREEN,AMBER,"#ffffff"])};z-index:6;'
        f'animation: fly{i%8} {rng.uniform(.7,1.3):.2f}s ease-out .18s forwards"></div>' for i in range(26))
    flies = "".join(
        f'@keyframes fly{k} {{ to {{ transform: translate({math.cos(k*math.pi/4)*260:.0f}px,'
        f'{math.sin(k*math.pi/4)*150-40:.0f}px) rotate({k*140}deg); opacity:0 }} }}' for k in range(8))
    msg = "CATASTROPHIC ROTOR FAILURE" if lethal else "ROTOR FAILURE"
    inner = f"""
    <style>
      {flies}
      @keyframes flash {{ 0% {{opacity:0}} 8% {{opacity:1}} 100% {{opacity:0}} }}
      @keyframes quake {{ 0%,100% {{transform:translate(0,0)}} 20% {{transform:translate(-9px,5px)}}
                          40% {{transform:translate(8px,-6px)}} 60% {{transform:translate(-6px,-4px)}}
                          80% {{transform:translate(5px,6px)}} }}
      @keyframes smoke {{ from {{transform:translateY(0) scale(.5); opacity:.75}}
                          to {{transform:translateY(-90px) scale(2.4); opacity:0}} }}
      .quake {{ position:absolute; inset:0; animation: quake .42s linear .18s 3; }}
      .flash {{ position:absolute; inset:0; background:#fff; z-index:7; animation: flash .5s ease-out .15s forwards; }}
      .core {{ position:absolute; left:50%; top:48%; width:120px; height:120px; margin:-60px 0 0 -60px;
               border-radius:50%; background:radial-gradient(circle,#fff 0%,#ffb627 35%,#ff3d8b 70%,transparent 72%);
               z-index:6; animation: flash .9s ease-out .15s forwards; }}
      .puff {{ position:absolute; left:50%; bottom:70px; width:44px; height:44px; margin-left:-22px;
               border-radius:50%; background:#3a3f55; z-index:5; animation: smoke 1.6s ease-out .4s infinite; }}
    </style>
    <div class="quake">{backdrop(zone, 13)}</div>
    <div class="core"></div>{shards}<div class="puff"></div><div class="flash"></div>
    <div class="caption" style="color:#ff3d8b;font-size:11px">{msg}</div>
    """
    return scene_shell(230, zone, inner)


def scene_fire() -> str:
    rng = random.Random(8)
    flames = "".join(
        f'<div style="position:absolute;left:{rng.randint(2,94)}%;bottom:{rng.randint(24,40)}px;'
        f'width:{rng.randint(16,34)}px;height:{rng.randint(38,88)}px;border-radius:50% 50% 30% 30%;'
        f'background:linear-gradient(180deg,#fff36b 0%,#ff9b1f 45%,#ff3d0f 100%);opacity:.9;z-index:4;'
        f'animation: lick {rng.uniform(.4,.8):.2f}s ease-in-out {rng.uniform(0,.5):.2f}s infinite alternate"></div>'
        for _ in range(16))
    embers = "".join(
        f'<div style="position:absolute;left:{rng.randint(2,96)}%;bottom:30px;width:3px;height:3px;'
        f'border-radius:50%;background:#ffca6b;z-index:5;'
        f'animation: ember {rng.uniform(1.6,3.4):.1f}s linear {rng.uniform(0,2.5):.1f}s infinite"></div>'
        for _ in range(22))
    inner = f"""
    <style>
      @keyframes lick {{ from {{ transform: scaleY(.82) skewX(-4deg) }} to {{ transform: scaleY(1.12) skewX(5deg) }} }}
      @keyframes ember {{ from {{ transform: translateY(0); opacity:1 }} to {{ transform: translateY(-170px); opacity:0 }} }}
      @keyframes sirens {{ 0%,100% {{ background:rgba(255,61,139,.10) }} 50% {{ background:rgba(255,61,139,.30) }} }}
      .siren {{ position:absolute; inset:0; z-index:6; animation: sirens 1s ease-in-out infinite; }}
    </style>
    {backdrop(ULTRA_ZONE, 21)}
    {flames}{embers}<div class="siren"></div>
    <div class="caption" style="color:#ffca6b;font-size:11px">LAB CONDEMNED &mdash; SHIFT OVER</div>
    """
    return scene_shell(230, ULTRA_ZONE, inner)


def scene_ultra_alert() -> str:
    inner = f"""
    <style>
      @keyframes strobe {{ 0%,100% {{ background:rgba(255,61,139,.06) }} 50% {{ background:rgba(255,61,139,.42) }} }}
      @keyframes dash {{ from {{ transform: translateX(-260px) }} to {{ transform: translateX(300px) }} }}
      @keyframes bob2 {{ 50% {{ transform: translateY(-7px) }} }}
      @keyframes typein {{ from {{ opacity:0; letter-spacing:1em }} to {{ opacity:1; letter-spacing:.14em }} }}
      .strobe {{ position:absolute; inset:0; z-index:6; animation: strobe .55s ease-in-out infinite; }}
      .runner {{ position:absolute; bottom:38px; left:50%; width:36px; z-index:4;
                 animation: dash 2.1s linear forwards, bob2 .18s steps(2) infinite; }}
      .pa {{ position:absolute; top:64px; left:0; right:0; text-align:center; z-index:7;
             font-family:'Press Start 2P',monospace; font-size:13px; color:#ff3d8b;
             text-shadow:0 0 16px #ff3d8b; animation: typein .8s ease-out forwards; }}
      .pa2 {{ position:absolute; top:104px; left:0; right:0; text-align:center; z-index:7;
              font-family:'IBM Plex Mono',monospace; font-size:11px; color:#ffb627; letter-spacing:.2em; }}
    </style>
    {backdrop(ULTRA_ZONE, 17)}
    <div class="runner"><div class="head"><div class="goggles"></div></div><div class="coat"></div><div class="legs"></div></div>
    <div class="strobe"></div>
    <div class="pa">&#9888; SAMPLE ALERT</div>
    <div class="pa2">ULTRACENTRIFUGE SUITE 3 &mdash; REPORT IMMEDIATELY</div>
    """
    return scene_shell(230, ULTRA_ZONE, inner)


def countdown_html(seconds_left: float) -> str:
    """Ticking clock for the ultracentrifuge. Display only -- the authoritative
    check happens in Python whenever the player acts."""
    return """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');
      .cd { font-family:'Press Start 2P',monospace; font-size:13px; color:#ff3d8b;
            text-align:center; letter-spacing:.12em; text-shadow:0 0 12px #ff3d8b;
            animation: pulse .9s ease-in-out infinite; }
      .bar { height:6px; background:#2b0812; border:1px solid #8f1235; margin-top:6px; }
      .fill { height:100%; background:#ff3d8b; width:__PCT__%;
              animation: drain __LEFT__s linear forwards; }
      @keyframes drain { to { width:0%; } }
      @keyframes pulse { 50% { opacity:.55; } }
    </style>
    <div class="cd" id="c">T-MINUS __INT__</div>
    <div class="bar"><div class="fill"></div></div>
    <script>
      let t = __LEFT__;
      const el = document.getElementById('c');
      const iv = setInterval(() => {
        t -= 1;
        if (t <= 0) { el.textContent = 'CHAMBER LOCKED'; clearInterval(iv); }
        else { el.textContent = 'T-MINUS ' + String(t).padStart(2,'0'); }
      }, 1000);
    </script>
    """.replace("__LEFT__", "%.0f" % seconds_left) \
       .replace("__INT__", "%02d" % int(seconds_left)) \
       .replace("__PCT__", "%.0f" % (100 * seconds_left / max(1, ULTRA_SPEC.time_limit)))


# ==========================================================================
# 8. ROTOR — interactive (plotly) and static (svg)
# ==========================================================================
def tube_size(mass: float) -> float:
    return 15 + 7.0 * math.sqrt(mass)


def rotor_figure(spec: LevelSpec, base, player, blocked: Set[int], show_needle: bool) -> go.Figure:
    z, n = spec.zone, spec.slots
    loads = combined(base, player)
    fig = go.Figure()
    shapes = []

    shapes.append(dict(type="circle", xref="x", yref="y", x0=-1.44, y0=-1.44, x1=1.44, y1=1.44,
                       line=dict(color=z.plate_edge, width=3), fillcolor=z.sky_bot, layer="below"))
    shapes.append(dict(type="circle", xref="x", yref="y", x0=-1.26, y0=-1.26, x1=1.26, y1=1.26,
                       line=dict(color=z.plate_edge, width=2), fillcolor=z.plate, layer="below"))

    if spec.style == 2:                       # drilled plate
        for k in range(n):
            hx, hy = slot_xy(k, n, 0.55)
            shapes.append(dict(type="circle", x0=hx - .05, y0=hy - .05, x1=hx + .05, y1=hy + .05,
                               line=dict(color=z.sky_bot, width=1), fillcolor=z.sky_bot, layer="below"))
    else:
        for k in range(n):
            sx, sy = slot_xy(k, n, 1.0)
            shapes.append(dict(type="line", x0=0, y0=0, x1=sx, y1=sy,
                               line=dict(color=z.plate_edge, width=1), layer="below"))

    if spec.style == 1:                       # swinging buckets: outer cradle ring
        shapes.append(dict(type="circle", x0=-1.13, y0=-1.13, x1=1.13, y1=1.13,
                           line=dict(color=z.plate_edge, width=8), layer="below"))

    hub = 0.17 if spec.style != 2 else 0.22
    shapes.append(dict(type="circle", x0=-hub, y0=-hub, x1=hub, y1=hub,
                       line=dict(color=z.plate_edge, width=2), fillcolor="#080a16", layer="below"))

    xs, ys, colors, sizes, lines, hover = [], [], [], [], [], []
    for i in range(n):
        x, y = slot_xy(i, n, 1.0)
        xs.append(x); ys.append(y)
        m = loads[i]
        if i in blocked:
            colors.append("rgba(255,61,139,0.10)"); sizes.append(19)
            lines.append(MAGENTA); hover.append(f"{i} · cracked bucket")
        elif m is None:
            colors.append("rgba(8,10,22,0.85)"); sizes.append(19)
            lines.append(STEEL); hover.append(f"{i} · empty")
        elif base[i] is not None:
            colors.append(GREEN); sizes.append(tube_size(m))
            lines.append("#0a2a10"); hover.append(f"{i} · locked {m:g} g")
        else:
            colors.append(CYAN); sizes.append(tube_size(m))
            lines.append("#062a28"); hover.append(f"{i} · yours {m:g} g · click to lift")

    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="markers", customdata=list(range(n)),
        marker=dict(color=colors, size=sizes, line=dict(color=lines, width=2)),
        hovertext=hover, hoverinfo="text",
        selected=dict(marker=dict(opacity=1.0)),
        unselected=dict(marker=dict(opacity=1.0)),
        showlegend=False,
    ))

    ann = []
    for i in range(n):
        lx, ly = slot_xy(i, n, 1.30)
        ann.append(dict(x=lx, y=ly, text=str(i), showarrow=False,
                        font=dict(family="IBM Plex Mono, monospace", size=10, color=DIM)))

    if show_needle:
        vx, vy = imbalance_vector(loads)
        mag = math.hypot(vx, vy)
        if mag > 1e-9:
            scale = min(1.02, 0.20 + mag * 0.075)
            shapes.append(dict(type="line", x0=0, y0=0,
                               x1=scale * vx / mag, y1=-scale * vy / mag,
                               line=dict(color=MAGENTA, width=4), layer="above"))
        else:
            shapes.append(dict(type="circle", x0=-0.09, y0=-0.09, x1=0.09, y1=0.09,
                               fillcolor=GREEN, line=dict(color=GREEN, width=1), layer="above"))
    else:
        ann.append(dict(x=0, y=0, text="?", showarrow=False,
                        font=dict(family="Press Start 2P, monospace", size=13, color=MAGENTA)))

    fig.update_layout(
        shapes=shapes, annotations=ann,
        xaxis=dict(range=[-1.55, 1.55], visible=False, fixedrange=True,
                   scaleanchor="y", scaleratio=1, constrain="domain"),
        yaxis=dict(range=[-1.55, 1.55], visible=False, fixedrange=True, constrain="domain"),
        margin=dict(l=0, r=0, t=0, b=0), height=430,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        clickmode="event+select", showlegend=False,
        hoverlabel=dict(bgcolor="#10142a", font=dict(family="IBM Plex Mono, monospace",
                                                    size=11, color=BONE)),
    )
    return fig


# ==========================================================================
# 9. LEADERBOARD
# ==========================================================================
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
            return df.dropna(how="all").to_dict("records")
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
    rows = sorted(rows, key=lambda r: -int(float(r.get("score", 0))))[:500]
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
    rows = sorted(rows, key=lambda r: -int(float(r.get("score", 0))))[:top]
    if not rows:
        return '<p class="cc-readout">No scores logged yet. Be the first.</p>'
    out = ['<table class="cc-lb"><tr><th>#</th><th>Operator</th><th>Score</th>'
           '<th>Levels</th><th>Time</th></tr>']
    for i, r in enumerate(rows, 1):
        me = ' class="me"' if highlight and str(r.get("name")) == highlight else ""
        s = int(float(r.get("seconds", 0)))
        out.append(f"<tr{me}><td class='rank'>{i:02d}</td><td>{r.get('name','???')}</td>"
                   f"<td>{int(float(r.get('score',0)))}</td>"
                   f"<td>{int(float(r.get('levels',0)))}/{len(LEVELS)}</td>"
                   f"<td>{s//60}:{s%60:02d}</td></tr>")
    out.append("</table>")
    return "".join(out)


# ==========================================================================
# 10. STATE
# ==========================================================================
def init_state():
    ss = st.session_state
    ss.setdefault("phase", "title")
    ss.setdefault("level", 0)
    ss.setdefault("prev_level", 0)
    ss.setdefault("name", "")
    ss.setdefault("scores", [])
    ss.setdefault("fails", 0)
    ss.setdefault("lives", START_LIVES)
    ss.setdefault("ultra_count", 0)
    ss.setdefault("in_ultra", False)
    ss.setdefault("nonce", 0)
    ss.setdefault("submitted", False)
    ss.setdefault("muted", False)
    ss.setdefault("last_result", None)
    ss.setdefault("show_help", False)


def current_spec() -> LevelSpec:
    return ULTRA_SPEC if st.session_state.in_ultra else LEVELS[st.session_state.level]


def load_level(spec: LevelSpec, keep_fails: bool = False):
    ss = st.session_state
    base, blocked, hand = generate_level(spec, random.Random())
    ss.base, ss.blocked, ss.hand = base, blocked, hand
    ss.player = [None] * spec.slots
    if not keep_fails:
        ss.fails = 0
    ss.nonce += 1
    ss.level_start = time.time()


def reset_game():
    for k in ("phase", "level", "prev_level", "scores", "fails", "lives",
              "ultra_count", "in_ultra", "submitted", "last_result", "show_help"):
        st.session_state.pop(k, None)
    init_state()


def finish_run(reason: str, burned: bool):
    st.session_state.gameover_reason = reason
    st.session_state.burned = burned
    st.session_state.phase = "burn"


# ==========================================================================
# 11. SCREENS
# ==========================================================================
def screen_title():
    components.html(scene_attract(), height=344)
    c1, c2, c3 = st.columns([2, 1.4, 1.4])
    with c1:
        name = st.text_input("Operator initials", max_chars=12, placeholder="RSA",
                             label_visibility="collapsed", key="name_in")
    with c2:
        if st.button("START SHIFT", type="primary", **BTN):
            ss = st.session_state
            ss.name = (name or "ANON").strip().upper()[:12] or "ANON"
            ss.level, ss.prev_level = 0, 0
            ss.scores, ss.lives = [], START_LIVES
            ss.ultra_count, ss.in_ultra = 0, False
            ss.submitted = False
            ss.game_start = time.time()
            load_level(LEVELS[0])
            ss.phase = "intro"
            st.rerun()
    with c3:
        if st.button("HOW TO PLAY", **BTN):
            st.session_state.show_help = not st.session_state.show_help
            st.rerun()

    b1, b2 = st.columns(2)
    with b1:
        if st.button("HIGH SCORES", **BTN):
            st.session_state.phase = "scores_only"
            st.rerun()
    with b2:
        if st.button("SOUND: OFF" if st.session_state.muted else "SOUND: ON",
                     **BTN):
            st.session_state.muted = not st.session_state.muted
            st.rerun()

    if st.session_state.show_help:
        st.markdown(
            f"""<div class="cc-panel"><p class="cc-readout" style="text-align:left;line-height:1.95">
            A spinning tube pulls outward. The rotor is safe when every pull cancels:
            <span class="cc-amber">two opposite</span>, <span class="cc-amber">three at 120&deg;</span>,
            <span class="cc-amber">four at 90&deg;</span>, or any mix that sums to zero.<br><br>
            Click a rotor position to seat the selected tube. Click your own tube to lift it out.
            The <span style="color:{MAGENTA}">magenta needle</span> points where the rotor is pulling &mdash;
            shrink it to nothing, close the lid, and walk to the next machine.<br><br>
            <span style="color:{GREEN}">Green</span> = already loaded, locked.
            <span style="color:{CYAN}">Cyan</span> = yours.
            <span style="color:{MAGENTA}">Dashed</span> = cracked bucket, unusable.<br><br>
            You get <span class="cc-amber">3 lives</span>. Spin an unbalanced rotor and one is gone.
            And if the PA calls you to the ultracentrifuge suite &mdash; there are no lives in there.
            </p></div>""", unsafe_allow_html=True)


def screen_intro():
    ss = st.session_state
    spec = LEVELS[ss.level]
    st.markdown(f'<div class="cc-strip">{spec.zone.name} &nbsp;&middot;&nbsp; '
                f'{spec.name} &nbsp;&middot;&nbsp; {spec.subtitle}</div>', unsafe_allow_html=True)
    components.html(scene_walk(ss.level, ss.prev_level, spec.zone,
                               f"LEVEL {ss.level+1} &mdash; LID OPEN"), height=244)
    time.sleep(2.3)
    ss.phase = "play"
    ss.level_start = time.time()
    st.rerun()


def screen_ultra_intro():
    ss = st.session_state
    st.markdown('<div class="cc-strip" style="color:#ff3d8b">&#9888; UNSCHEDULED RUN &#9888;</div>',
                unsafe_allow_html=True)
    components.html(scene_ultra_alert(), height=244)
    time.sleep(2.6)
    ss.phase = "play"
    ss.level_start = time.time()
    st.rerun()


def hud(spec: LevelSpec):
    ss = st.session_state
    hearts = "&#9829;" * ss.lives + '<span style="color:#333a58">&#9829;</span>' * (START_LIVES - ss.lives)
    if spec.time_limit:
        left = max(0, int(spec.time_limit - (time.time() - ss.level_start)))
        clock = f'<div><span class="k">T-MINUS</span><span style="color:{MAGENTA}">{left:02d}s</span></div>'
    else:
        clock = f'<div><span class="k">PAR</span>{spec.par_seconds}s</div>'
    tag = "SUITE 3" if spec.sudden_death else f"{ss.level+1:02d}/{len(LEVELS)}"
    st.markdown(
        f'<div class="cc-panel"><div class="cc-hud">'
        f'<div><span class="k">LEVEL</span>{tag}</div>'
        f'<div><span class="k">SCORE</span>{sum(ss.scores)}</div>'
        f'<div><span class="k">LIVES</span><span style="color:{MAGENTA}">{hearts}</span></div>'
        f'<div><span class="k">TRAY</span>{len(ss.hand)}</div>'
        f"{clock}</div></div>", unsafe_allow_html=True)


def try_place(i: int, pick: Optional[int]):
    """Resolve a click on rotor position i."""
    ss = st.session_state
    if i in ss.blocked or ss.base[i] is not None:
        play("nope")
        return
    if ss.player[i] is not None:
        ss.hand.append(ss.player[i]); ss.hand.sort(reverse=True)
        ss.player[i] = None
        play("place")
        return
    if ss.hand:
        ss.player[i] = ss.hand.pop(pick if pick is not None and pick < len(ss.hand) else 0)
        play("place")
    else:
        play("nope")


def screen_play():
    ss = st.session_state
    spec = current_spec()
    loads = combined(ss.base, ss.player)
    resid = imbalance(loads)
    tol = tolerance_for(spec)
    blind = spec.time_limit > 0          # ultracentrifuge: vacuum chamber, no meter

    # hard timer
    if spec.time_limit and time.time() - ss.level_start > spec.time_limit:
        ss.last_result = ("timeout", resid, tol, 0, 0, 0)
        play("alarm")
        ss.phase = "explode"
        st.rerun()

    if spec.sudden_death:
        st.markdown('<div class="cc-strip" style="color:#ff3d8b">'
                    f'{spec.name} &nbsp;&middot;&nbsp; {spec.subtitle}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="cc-strip">{spec.zone.name} &nbsp;&middot;&nbsp; {spec.name}</div>',
                    unsafe_allow_html=True)
    hud(spec)

    if spec.time_limit:                      # live ticking clock for the vacuum run
        left = max(0, spec.time_limit - (time.time() - ss.level_start))
        components.html(countdown_html(left), height=42)

    # tray first: the selected tube is what a rotor click will seat
    if ss.hand:
        pick = st.radio("Tube tray", options=list(range(len(ss.hand))),
                        format_func=lambda i: f"{ss.hand[i]:g} g",
                        horizontal=True, label_visibility="collapsed",
                        key=f"tray_{ss.nonce}_{len(ss.hand)}")
    else:
        pick = None

    fig = rotor_figure(spec, ss.base, ss.player, ss.blocked, show_needle=not blind)
    event = st.plotly_chart(fig, key=f"rotor_{ss.nonce}",
                            on_select="rerun", selection_mode="points",
                            config={"displayModeBar": False, "staticPlot": False}, **FIG)

    pts = []
    try:
        pts = event.selection["points"] if event and event.selection else []
    except Exception:
        pts = []
    if pts:
        idx = pts[0].get("customdata")
        if isinstance(idx, list):
            idx = idx[0]
        if idx is None:
            idx = pts[0].get("point_index")
        if idx is not None:
            try_place(int(idx), pick)
            ss.nonce += 1
            st.rerun()

    if blind:
        state = ('<span class="cc-bad">CHAMBER SEALED &mdash; no imbalance telemetry</span>'
                 f'<br><span style="color:#5a6486">limit {tol:.3f} &middot; one spin only</span>')
    elif resid < 1e-9:
        state = '<span class="cc-ok">BALANCED &mdash; residual 0.000</span>'
    elif resid <= tol and not ss.hand:
        state = f'<span class="cc-ok">WITHIN TOLERANCE &mdash; {resid:.3f} / {tol:.3f}</span>'
    else:
        state = (f'<span class="cc-bad">IMBALANCE {resid:.3f}</span>'
                 f'<span style="color:#5a6486"> / limit {tol:.3f}</span>')
    st.markdown(f'<p class="cc-readout">{state}</p>', unsafe_allow_html=True)

    st.markdown('<p class="cc-readout" style="text-align:left;font-size:.7rem">'
                'CLICK THE ROTOR, OR USE THE PAD</p>', unsafe_allow_html=True)
    n = spec.slots
    per_row = 10 if n >= 30 else 12
    for row_start in range(0, n, per_row):
        row = list(range(row_start, min(row_start + per_row, n)))
        for c, i in zip(st.columns(len(row)), row):
            with c:
                if i in ss.blocked:
                    st.button("✖", key=f"s{ss.nonce}_{i}", disabled=True, **BTN)
                elif ss.base[i] is not None:
                    st.button("▪", key=f"s{ss.nonce}_{i}", disabled=True, **BTN)
                elif ss.player[i] is not None:
                    if st.button("↩", key=f"s{ss.nonce}_{i}", **BTN):
                        try_place(i, pick); ss.nonce += 1; st.rerun()
                else:
                    if st.button(str(i), key=f"s{ss.nonce}_{i}", disabled=not ss.hand, **BTN):
                        try_place(i, pick); ss.nonce += 1; st.rerun()

    st.write("")
    c1, c2 = st.columns([2, 1])
    with c1:
        label = "SEAL CHAMBER AND SPIN" if spec.sudden_death else "CLOSE LID AND SPIN"
        if st.button(label, type="primary", **BTN, disabled=bool(ss.hand)):
            play("spin")
            ss.phase = "spin"
            st.rerun()
    with c2:
        if st.button("CLEAR TRAY", **BTN):
            for i in range(n):
                if ss.player[i] is not None:
                    ss.hand.append(ss.player[i]); ss.player[i] = None
            ss.hand.sort(reverse=True)
            ss.nonce += 1
            st.rerun()


def screen_spin():
    ss = st.session_state
    spec = current_spec()
    loads = combined(ss.base, ss.player)
    resid = imbalance(loads)
    tol = tolerance_for(spec)

    st.markdown('<div class="cc-strip">SPINNING UP</div>', unsafe_allow_html=True)
    components.html(scene_spin(spec.zone, spec.slots), height=244)
    time.sleep(2.0)

    if resid > tol:
        ss.fails += 1
        ss.last_result = ("fail", resid, tol, 0, 0, 0)
        play("alarm")
        ss.phase = "explode"
    else:
        elapsed = time.time() - ss.level_start
        acc = ACC_POINTS * (1 - min(1.0, resid / tol))
        speed = TIME_POINTS * max(0.0, (spec.par_seconds - elapsed) / spec.par_seconds)
        bonus = ULTRA_BONUS if spec.sudden_death else 0
        pts = max(0, round(acc + speed + bonus - FAIL_PENALTY * ss.fails))
        ss.scores.append(pts)
        ss.last_result = ("pass", resid, tol, round(acc), round(speed + bonus), pts)
        play("good")
        ss.phase = "result"
    st.rerun()


def screen_explode():
    ss = st.session_state
    spec = current_spec()
    kind = ss.last_result[0]
    lethal = spec.sudden_death or ss.lives <= 1

    st.markdown('<div class="cc-strip" style="color:#ff3d8b">'
                f'{"TIMER EXPIRED" if kind == "timeout" else "IMBALANCE ALARM"}</div>',
                unsafe_allow_html=True)
    play_now("boom")
    components.html(scene_explode(spec.zone, lethal), height=244)
    time.sleep(2.4)

    if spec.sudden_death:
        finish_run("The vacuum chamber let go at 60,000 rpm. Suite 3 no longer exists.", True)
    else:
        ss.lives -= 1
        if ss.lives <= 0:
            finish_run("Three rotors in one shift. The safety officer walked you out.", True)
        else:
            ss.phase = "result"
    st.rerun()


def screen_result():
    ss = st.session_state
    spec = current_spec()
    kind, resid, tol, acc, speed, pts = ss.last_result

    if kind in ("fail", "timeout"):
        st.markdown('<div class="cc-strip" style="color:#ff3d8b">ROTOR DESTROYED</div>',
                    unsafe_allow_html=True)
        why = ("The clock ran out with the chamber still open."
               if kind == "timeout" else
               f"Imbalance hit {resid:.3f} against a {tol:.3f} limit.")
        st.markdown(
            f'<div class="cc-panel"><p class="cc-readout" style="text-align:left">'
            f'{why} You lost a life and {FAIL_PENALTY} points.<br><br>'
            f'<span class="cc-amber">{ss.lives}</span> of {START_LIVES} lives left. '
            f'A fresh rotor is being wheeled over.</p></div>', unsafe_allow_html=True)
        if st.button("TAKE THE NEW ROTOR", type="primary", **BTN):
            load_level(spec, keep_fails=True)
            ss.phase = "play"
            st.rerun()
        return

    if spec.sudden_death:
        st.markdown('<div class="cc-strip" style="color:#5be36a">SUITE 3 CLEARED</div>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<div class="cc-strip" style="color:#5be36a">CLEAN SPIN</div>',
                    unsafe_allow_html=True)
    st.markdown(
        f'<div class="cc-panel"><div class="cc-hud">'
        f'<div><span class="k">RESIDUAL</span>{resid:.3f}</div>'
        f'<div><span class="k">ACCURACY</span>{acc}</div>'
        f'<div><span class="k">{"BONUS" if spec.sudden_death else "SPEED"}</span>{speed}</div>'
        f'<div><span class="k">ABORTS</span>-{FAIL_PENALTY*ss.fails}</div>'
        f'<div><span class="k">LEVEL</span>{pts}</div>'
        f"</div></div>", unsafe_allow_html=True)

    if ss.in_ultra:
        if st.button("BACK TO THE BENCH", type="primary", **BTN):
            ss.in_ultra = False
            ss.prev_level = ss.level
            ss.level += 1
            load_level(LEVELS[ss.level])
            ss.phase = "intro"
            st.rerun()
        return

    last = ss.level + 1 >= len(LEVELS)
    if st.button("END SHIFT" if last else "NEXT CENTRIFUGE",
                 type="primary", **BTN):
        if last:
            finish_run("You balanced every rotor on the bench and went home clean.", False)
        else:
            rng = random.Random()
            if (ss.level >= ULTRA_EARLIEST and ss.ultra_count < ULTRA_MAX
                    and rng.random() < ULTRA_CHANCE):
                ss.in_ultra = True
                ss.ultra_count += 1
                load_level(ULTRA_SPEC)
                play("alert")
                ss.phase = "ultra_intro"
            else:
                ss.prev_level = ss.level
                ss.level += 1
                load_level(LEVELS[ss.level])
                ss.phase = "intro"
        st.rerun()


def screen_burn():
    ss = st.session_state
    st.markdown('<div class="cc-strip" style="color:#ffca6b">SHIFT OVER</div>', unsafe_allow_html=True)
    if ss.get("burned"):
        play_now("over")
        components.html(scene_fire(), height=244)
        time.sleep(2.8)
    ss.phase = "gameover"
    st.rerun()


def screen_gameover():
    ss = st.session_state
    total = sum(ss.scores)
    shift = int(time.time() - ss.get("game_start", time.time()))

    st.markdown('<div class="cc-strip">SHIFT REPORT</div>', unsafe_allow_html=True)
    st.markdown(f'<p class="cc-readout">{ss.get("gameover_reason","")}</p>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="cc-panel"><div class="cc-hud">'
        f'<div><span class="k">OPERATOR</span>{ss.name}</div>'
        f'<div><span class="k">FINAL SCORE</span>{total}</div>'
        f'<div><span class="k">LEVELS</span>{len(ss.scores)}/{len(LEVELS)}</div>'
        f'<div><span class="k">LIVES LEFT</span>{ss.lives}</div>'
        f'<div><span class="k">SHIFT TIME</span>{shift//60}:{shift%60:02d}</div>'
        f"</div></div>", unsafe_allow_html=True)

    if not ss.submitted:
        save_score({"name": ss.name, "score": total, "levels": len(ss.scores),
                    "seconds": shift, "when": time.strftime("%Y-%m-%d")})
        ss.submitted = True

    st.markdown('<p class="cc-readout" style="text-align:left">GLOBAL TOP 10</p>', unsafe_allow_html=True)
    st.markdown(leaderboard_table(load_scores(), highlight=ss.name), unsafe_allow_html=True)
    st.markdown(f'<p class="cc-readout" style="font-size:.68rem">scores stored in: {backend_name()}</p>',
                unsafe_allow_html=True)

    if st.button("NEW SHIFT", type="primary", **BTN):
        reset_game()
        st.rerun()


def screen_scores_only():
    st.markdown('<div class="cc-strip">HIGH SCORES</div>', unsafe_allow_html=True)
    st.markdown(leaderboard_table(load_scores()), unsafe_allow_html=True)
    st.markdown(f'<p class="cc-readout" style="font-size:.68rem">scores stored in: {backend_name()}</p>',
                unsafe_allow_html=True)
    if st.button("BACK", **BTN):
        st.session_state.phase = "title"
        st.rerun()


# ==========================================================================
# 12. MAIN
# ==========================================================================
def main():
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
    init_state()
    emit_sound()
    {
        "title": screen_title,
        "intro": screen_intro,
        "ultra_intro": screen_ultra_intro,
        "play": screen_play,
        "spin": screen_spin,
        "explode": screen_explode,
        "result": screen_result,
        "burn": screen_burn,
        "gameover": screen_gameover,
        "scores_only": screen_scores_only,
    }[st.session_state.phase]()


if __name__ == "__main__":
    main()
