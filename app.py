"""
CENTRIFUGE CHESS  v2
A retro-arcade puzzle game about balancing centrifuge rotors.
Made by Dylan.

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
    layout="wide",
    initial_sidebar_state="collapsed",
)


# Streamlit renamed the full-width kwarg (use_container_width -> width="stretch").
# Detect it at import so the game runs warning-free on either generation.
def _wide(fn) -> dict:
    params = inspect.signature(fn).parameters
    return {"width": "stretch"} if "width" in params else {"use_container_width": True}


BTN = _wide(st.button)
FIG = _wide(st.plotly_chart)

AMBER = "#ffb627"
CYAN = "#3ff2e0"
GREEN = "#5be36a"
MAGENTA = "#ff3d8b"
STEEL = "#5a6486"
BONE = "#e8e6f0"
DIM = "#5a6486"


# ==========================================================================
# 1. ZONES — the centrifuge hardware itself
# ==========================================================================
@dataclass(frozen=True)
class Zone:
    key: str
    name: str
    accent: str
    plate: str
    plate_edge: str
    housing: str
    shell: str        # box | drum | tower | vault


TEACHING = Zone("teach", "TEACHING LAB", "#57b6ff", "#1a2145", "#3a4780", "#d8dbe8", "box")
CORE = Zone("core", "CORE FACILITY", "#ffb627", "#2a2038", "#6b5330", "#e6dcc8", "drum")
COLD = Zone("cold", "COLD ROOM", "#3ff2e0", "#0f2c38", "#2f6f7a", "#c9e6ec", "tower")
PREP = Zone("prep", "PREP SUITE", "#ff6b3d", "#2e1420", "#7d3b2c", "#d6c2be", "vault")
ULTRA_ZONE = Zone("ultra", "SUITE 3", "#ff3d8b", "#2b0812", "#8f1235", "#b9a6ad", "vault")


# ==========================================================================
# 2. ROOMS — the building you walk through between machines
# Purely cosmetic. The puzzle maths never sees these.
# ==========================================================================
@dataclass(frozen=True)
class Room:
    key: str
    name: str
    sign: str          # flavour line on the door
    wall_top: str
    wall_bot: str
    accent: str
    floor_a: str
    floor_b: str
    critter: str       # monkey|mouse|fish|virus|alien|flake|fly|bubble|roach
    prop: str          # cages|drums|tanks|airlock|pod|dewar|vials|sinks


LOBBY = Room("lobby", "MAIN LAB", "the good bench", "#141a3a", "#0d1128", "#57b6ff",
             "#10142a", "#141935", "roach", "sinks")
VIVARIUM = Room("viv", "VIVARIUM", "do not feed the animals", "#1d2a18", "#0d1509", "#8fd14f",
                "#121b0e", "#172312", "monkey", "cages")
RADIO = Room("radio", "RADIOISOTOPE SUITE", "dosimeter required", "#2b2a0c", "#151405", "#d4ff3d",
             "#1a1907", "#22200b", "flake", "drums")
AQUATICS = Room("aqua", "AQUATICS FACILITY", "3,000 zebrafish", "#062a3a", "#02141d", "#3fd2f2",
                "#04202c", "#062a38", "fish", "tanks")
BSL4 = Room("bsl4", "BSL-4 CONTAINMENT", "positive pressure", "#2a0f2e", "#150618", "#c86bff",
            "#1c0a20", "#240d29", "virus", "airlock")
XENO = Room("xeno", "XENOBIOLOGY", "sample 9 is awake", "#0e2b26", "#041512", "#4fffb0",
            "#082019", "#0b2a21", "alien", "pod")
CRYO = Room("cryo", "CRYOSTORAGE", "-80 and falling", "#0d2733", "#061620", "#a8e6ff",
            "#08202b", "#0c2a36", "flake", "dewar")
FLYROOM = Room("fly", "FLY ROOM", "someone left the vials open", "#33240f", "#1a1207", "#ffc861",
               "#221806", "#2b1f0a", "fly", "vials")
GLASSWASH = Room("glass", "GLASSWASH", "everything is still wet", "#1a2333", "#0b1019", "#9fb8d8",
                 "#0e141f", "#131b28", "bubble", "sinks")
SUITE3 = Room("suite3", "SUITE 3", "unscheduled run", "#3a0a16", "#160208", "#ff3d8b",
              "#180309", "#210610", "roach", "airlock")

# Fixed tour of the building, one room per level.
ROOM_TOUR = [LOBBY, LOBBY, VIVARIUM, FLYROOM, AQUATICS, RADIO,
             GLASSWASH, CRYO, BSL4, XENO, CRYO, RADIO, XENO]


# ==========================================================================
# 3. LEVELS
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
    time_limit: int = 0
    sudden_death: bool = False


LEVELS: List[LevelSpec] = [
    LevelSpec("MICROSPIN 6", "personal microfuge", 6, 2, 1, 0, (1.5,), 0.55, 25, TEACHING, 0),
    LevelSpec("MICROSPIN 12", "12-place fixed rotor", 12, 4, 1, 0, (1.5,), 0.55, 30, TEACHING, 2),
    LevelSpec("MICROSPIN 12-X", "mixed tube sizes", 12, 6, 2, 1, (1.5, 2.0), 0.55, 45, TEACHING, 0),
    LevelSpec("BENCHTOP 16", "one bucket is cracked", 16, 8, 2, 2, (1.5, 2.0), 0.50, 55, CORE, 1),
    LevelSpec("BENCHTOP 18", "thirds, not halves", 18, 9, 2, 2, (1.5, 2.0, 5.0), 0.50, 65, CORE, 2),
    LevelSpec("SWING-24", "swinging bucket rotor", 24, 12, 3, 3, (1.5, 2.0, 5.0), 0.50, 75, CORE, 1),
    LevelSpec("CLINICAL-20", "no thirds on this one", 20, 10, 3, 4, (2.0, 5.0, 15.0), 0.48, 80, CORE, 0),
    LevelSpec("SWING-24 HD", "15 mL conicals", 24, 12, 3, 5, (2.0, 5.0, 15.0), 0.45, 80, COLD, 1),
    LevelSpec("ULTRA-30", "high speed, low patience", 30, 15, 3, 5, (1.5, 2.0, 5.0, 15.0), 0.45, 90, COLD, 0),
    LevelSpec("HEMATO-32", "half the plate is dead", 32, 16, 4, 6, (1.5, 2.0, 5.0, 15.0), 0.42, 95, COLD, 2),
    LevelSpec("ULTRA-36", "seven dead positions", 36, 18, 4, 7, (1.5, 2.0, 5.0, 15.0), 0.40, 100, COLD, 2),
    LevelSpec("PREP-36", "the one with the 50s", 36, 20, 4, 9, (1.5, 2.0, 5.0, 15.0, 50.0), 0.40, 110, PREP, 1),
    LevelSpec("PREP-48", "final rotor of the shift", 48, 24, 5, 12, (1.5, 2.0, 5.0, 15.0, 50.0), 0.38, 130, PREP, 1),
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
ULTRA_CHANCE = 0.35
ULTRA_MAX = 2
ULTRA_EARLIEST = 3


def room_for(level_idx: int) -> Room:
    return ROOM_TOUR[level_idx % len(ROOM_TOUR)]
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
# 5. STYLES
# ==========================================================================
GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&family=IBM+Plex+Mono:wght@400;600&display=swap');

#MainMenu, header[data-testid="stHeader"], footer,
[data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], [data-testid="stAppDeployButton"] {
    display: none !important; visibility: hidden !important; height: 0 !important;
}
[data-testid="stAudio"] { position: fixed; left: -9999px; width: 1px; height: 1px; }

.block-container {
    padding-top: 0.5rem !important; padding-bottom: 1.2rem !important;
    padding-left: 2rem !important; padding-right: 2rem !important;
    max-width: 1600px !important;
}
.stApp { background: #06070d; color: #e8e6f0; }
h1, h2, h3 { font-family: 'Press Start 2P', monospace !important; }
body, p, li, div[data-testid="stMarkdownContainer"] { font-family: 'IBM Plex Mono', monospace; }
[data-testid="stVerticalBlock"] { gap: 0.55rem; }

.cc-strip { font-family:'Press Start 2P',monospace; font-size:0.68rem; color:#ffb627;
            text-align:center; letter-spacing:0.05em; padding:0.3rem 0; margin-bottom:0.35rem; }
.cc-panel { background:rgba(12,16,34,0.88); border:2px solid #2b3358; border-radius:4px;
            padding:0.7rem 0.9rem; margin-bottom:0.55rem; }
.cc-hud { display:flex; justify-content:space-between; gap:0.35rem;
          font-family:'Press Start 2P',monospace; font-size:0.6rem; color:#ffb627; }
.cc-hud span.k { color:#5a6486; display:block; margin-bottom:5px; font-size:0.5rem; }
.cc-readout { font-family:'IBM Plex Mono',monospace; font-size:0.82rem; color:#5a6486;
              text-align:center; letter-spacing:0.04em; }
.cc-ok { color:#5be36a; } .cc-bad { color:#ff3d8b; } .cc-amber { color:#ffb627; }

/* --- tube tray --- */
.tray-banner { font-family:'Press Start 2P',monospace; font-size:0.72rem; text-align:center;
               padding:0.5rem 0.3rem; border-radius:3px; margin-bottom:0.45rem; line-height:1.7; }
.tray-need { background:rgba(255,182,39,0.13); border:2px solid #ffb627; color:#ffb627; }
.tray-done { background:rgba(91,227,106,0.13); border:2px solid #5be36a; color:#5be36a; }
.pips { text-align:center; font-size:1.35rem; letter-spacing:0.32rem; margin:0.1rem 0 0.4rem 0; }
.pip-done { color:#3ff2e0; } .pip-todo { color:#39405f; }

.stButton > button { font-family:'IBM Plex Mono',monospace !important; font-weight:600;
    background:#161c38; color:#e8e6f0; border:1px solid #38416e; border-radius:3px;
    padding:0.3rem 0.1rem; transition:none; }
.stButton > button:hover { background:#ffb627; color:#06070d; border-color:#ffb627; }
.stButton > button:disabled { background:#0f1226; color:#333a58; border-color:#1c2240; }
.stButton > button:focus-visible { outline:2px solid #3ff2e0; outline-offset:2px; }
.stButton > button[kind="primary"] { background:#3ff2e0; color:#06070d; border-color:#3ff2e0;
    box-shadow:0 0 14px rgba(63,242,224,0.45); }
.stButton > button[kind="primary"]:hover { background:#ffb627; border-color:#ffb627; }

table.cc-lb { width:100%; border-collapse:collapse; font-family:'IBM Plex Mono',monospace; font-size:0.84rem; }
table.cc-lb th { text-align:left; color:#5a6486; font-size:0.64rem; text-transform:uppercase;
                 letter-spacing:0.14em; border-bottom:1px solid #2b3358; padding:6px 8px; }
table.cc-lb td { padding:6px 8px; border-bottom:1px solid #191e38; }
table.cc-lb tr.me td { color:#3ff2e0; }
table.cc-lb td.rank { color:#ffb627; }

.streamlit-expanderHeader, details summary { font-family:'IBM Plex Mono',monospace !important;
    font-size:0.78rem !important; color:#5a6486 !important; }

@media (prefers-reduced-motion: reduce) { * { animation:none !important; } }
</style>
"""

SCENE_BASE = """
<style>
 @import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&family=IBM+Plex+Mono:wght@400;600&display=swap');
 * { box-sizing:border-box; }
 .stage { position:relative; width:100%; height:__H__px; overflow:hidden;
          border:2px solid #2b3358; border-radius:4px; font-family:'IBM Plex Mono',monospace;
          background:linear-gradient(180deg,__WALLTOP__ 0%,__WALLBOT__ 100%); }
 .scan { position:absolute; inset:0; z-index:20; pointer-events:none;
         background:repeating-linear-gradient(180deg,rgba(0,0,0,0.20) 0 1px,transparent 1px 3px); }
 .vig { position:absolute; inset:0; z-index:19; pointer-events:none;
        background:radial-gradient(ellipse at 50% 45%,transparent 42%,rgba(0,0,0,0.7) 100%); }
 .floor { position:absolute; bottom:0; left:0; right:0; height:36px; z-index:2;
          background:repeating-linear-gradient(90deg,__FLOORA__ 0 30px,__FLOORB__ 30px 60px);
          border-top:2px solid rgba(255,255,255,0.07); }
 .lamp { position:absolute; top:0; height:5px; background:__ACCENT__; opacity:0.45; z-index:1;
         animation:flick 6s steps(1) infinite; }
 @keyframes flick { 0%,86%,100%{opacity:.45} 88%{opacity:.10} 91%{opacity:.55} 93%{opacity:.15} }
 .shelf { position:absolute; height:5px; background:rgba(255,255,255,0.10); z-index:1; }
 .sign { position:absolute; z-index:3; font-family:'Press Start 2P',monospace; font-size:7px;
         color:__ACCENT__; border:1px solid __ACCENT__; padding:3px 5px; opacity:.75;
         background:rgba(0,0,0,.45); line-height:1.6; }
 .head { width:20px; height:18px; background:#f0d2b4; border-radius:4px; margin:0 auto; position:relative; }
 .goggles { position:absolute; top:5px; left:-2px; width:24px; height:7px; background:__ACCENT__;
            border:1px solid #10142a; border-radius:3px; }
 .coat { width:34px; height:38px; background:#f4f6ff; border:1px solid #b9bfd8;
         border-radius:4px 4px 2px 2px; margin:0 auto; position:relative; }
 .coat:after { content:''; position:absolute; top:0; left:16px; width:2px; height:38px; background:#d4d9ea; }
 .legs { width:26px; height:16px; background:#2b3358; margin:0 auto; }
 .caption { position:absolute; top:9px; left:0; right:0; text-align:center; z-index:21;
            font-family:'Press Start 2P',monospace; font-size:10px; color:__ACCENT__;
            text-shadow:0 0 10px currentColor; }
 .sub { position:absolute; top:30px; left:0; right:0; text-align:center; z-index:21;
        font-family:'IBM Plex Mono',monospace; font-size:10px; color:#8fa0d8; letter-spacing:.2em; }
 @keyframes bob { 50% { transform:translateY(-5px) } }
 @keyframes lift { to { transform:rotate(-58deg) } }
</style>
"""


def scene_shell(height: int, room: Room, inner: str) -> str:
    css = (SCENE_BASE
           .replace("__H__", str(height))
           .replace("__WALLTOP__", room.wall_top)
           .replace("__WALLBOT__", room.wall_bot)
           .replace("__FLOORA__", room.floor_a)
           .replace("__FLOORB__", room.floor_b)
           .replace("__ACCENT__", room.accent))
    return css + (f'<div class="stage">{inner}<div class="floor"></div>'
                  f'<div class="vig"></div><div class="scan"></div></div>')


# --------------------------------------------------------------------------
# Sprite kit — everything is CSS boxes, no image assets
# --------------------------------------------------------------------------
def beaker(left: str, bottom: int, col: str, w: int = 16, h: int = 20) -> str:
    return (f'<div style="position:absolute;left:{left};bottom:{bottom}px;width:{w}px;height:{h}px;'
            f'border:2px solid #cfe0f5;border-top:none;border-radius:0 0 4px 4px;z-index:4;'
            f'background:linear-gradient(180deg,transparent 0%,transparent 35%,{col} 35%,{col} 100%);'
            f'opacity:.92"></div>')


def flask(left: str, bottom: int, col: str) -> str:
    return (f'<div style="position:absolute;left:{left};bottom:{bottom}px;width:0;height:0;z-index:4;'
            f'border-left:11px solid transparent;border-right:11px solid transparent;'
            f'border-bottom:22px solid {col};opacity:.9"></div>'
            f'<div style="position:absolute;left:calc({left} + 8px);bottom:{bottom+20}px;width:6px;'
            f'height:9px;background:#cfe0f5;z-index:4"></div>')


def microscope(left: str, bottom: int, col: str) -> str:
    return (f'<div style="position:absolute;left:{left};bottom:{bottom}px;width:26px;height:8px;'
            f'background:#2b3358;border-radius:2px;z-index:4"></div>'
            f'<div style="position:absolute;left:calc({left} + 14px);bottom:{bottom+6}px;width:6px;'
            f'height:26px;background:#4a5580;z-index:4"></div>'
            f'<div style="position:absolute;left:calc({left} + 4px);bottom:{bottom+26}px;width:20px;'
            f'height:7px;background:{col};border-radius:3px;z-index:4"></div>')


def bunsen(left: str, bottom: int) -> str:
    return (f'<div style="position:absolute;left:{left};bottom:{bottom}px;width:14px;height:7px;'
            f'background:#39405f;border-radius:2px;z-index:4"></div>'
            f'<div style="position:absolute;left:calc({left} + 5px);bottom:{bottom+5}px;width:5px;'
            f'height:16px;background:#4a5580;z-index:4"></div>'
            f'<div style="position:absolute;left:calc({left} + 3px);bottom:{bottom+20}px;width:9px;'
            f'height:15px;border-radius:50% 50% 30% 30%;z-index:4;'
            f'background:linear-gradient(180deg,#9ad7ff,#3f7fff);'
            f'animation:lick .3s ease-in-out infinite alternate"></div>')


def monitor(left: str, bottom: int, col: str) -> str:
    return (f'<div style="position:absolute;left:{left};bottom:{bottom}px;width:34px;height:24px;'
            f'background:#0a0d18;border:2px solid #4a5580;border-radius:2px;z-index:4;overflow:hidden">'
            f'<div style="position:absolute;top:3px;left:3px;width:60%;height:2px;background:{col};'
            f'animation:trace 1.6s linear infinite"></div>'
            f'<div style="position:absolute;top:9px;left:3px;width:40%;height:2px;background:{col};opacity:.6"></div>'
            f'<div style="position:absolute;top:15px;left:3px;width:75%;height:2px;background:{col};opacity:.4"></div>'
            f'</div>')


def rack(left: str, bottom: int, col: str, n: int = 5) -> str:
    tubes = "".join(
        f'<div style="position:absolute;left:{3+k*7}px;bottom:4px;width:5px;height:{12+(k%3)*3}px;'
        f'background:{col};opacity:.85"></div>' for k in range(n))
    return (f'<div style="position:absolute;left:{left};bottom:{bottom}px;width:{n*7+6}px;height:26px;'
            f'z-index:4"><div style="position:absolute;bottom:0;left:0;right:0;height:5px;'
            f'background:#4a5580;border-radius:2px"></div>{tubes}</div>')


def prop_wall(room: Room, seed: int) -> str:
    """Large fixtures specific to the room."""
    rng = random.Random(seed)
    a = room.accent
    out = []
    if room.prop == "cages":
        for k in range(4):
            x = 6 + k * 24
            out.append(
                f'<div style="position:absolute;left:{x}%;bottom:36px;width:74px;height:56px;'
                f'border:2px solid #6b7a5a;background:rgba(255,255,255,0.04);z-index:3">'
                + "".join(f'<div style="position:absolute;left:{6+j*9}px;top:0;bottom:0;width:1px;'
                          f'background:#6b7a5a;opacity:.7"></div>' for j in range(7))
                + f'<div style="position:absolute;bottom:3px;left:8px;width:14px;height:7px;'
                  f'border-radius:50%;background:#c9a37a"></div></div>')
    elif room.prop == "drums":
        for k in range(4):
            x = 8 + k * 23
            out.append(
                f'<div style="position:absolute;left:{x}%;bottom:36px;width:44px;height:58px;'
                f'background:#4a4712;border:2px solid {a};border-radius:4px;z-index:3;'
                f'box-shadow:0 0 26px rgba(212,255,61,.35)">'
                f'<div style="position:absolute;top:14px;left:11px;width:22px;height:22px;'
                f'border-radius:50%;border:3px solid {a};opacity:.9"></div>'
                f'<div style="position:absolute;top:22px;left:20px;width:5px;height:5px;'
                f'border-radius:50%;background:{a}"></div></div>')
    elif room.prop == "tanks":
        for k in range(3):
            x = 7 + k * 31
            out.append(
                f'<div style="position:absolute;left:{x}%;bottom:36px;width:104px;height:66px;'
                f'background:linear-gradient(180deg,rgba(63,210,242,.30),rgba(63,210,242,.13));'
                f'border:2px solid {a};z-index:3;box-shadow:inset 0 0 24px rgba(63,210,242,.35)"></div>')
    elif room.prop == "airlock":
        out.append(
            f'<div style="position:absolute;left:50%;margin-left:-58px;bottom:36px;width:116px;height:96px;'
            f'border:4px solid {a};border-radius:8px;background:rgba(0,0,0,.35);z-index:3;'
            f'box-shadow:0 0 34px {a}44">'
            f'<div style="position:absolute;top:10px;left:50%;margin-left:-26px;width:52px;height:52px;'
            f'border-radius:50%;border:3px solid {a};opacity:.8"></div></div>')
        for k in (12, 78):
            out.append(f'<div style="position:absolute;left:{k}%;bottom:36px;width:30px;height:74px;'
                       f'background:#e8e6f0;opacity:.16;border-radius:14px 14px 3px 3px;z-index:3"></div>')
    elif room.prop == "pod":
        out.append(
            f'<div style="position:absolute;left:50%;margin-left:-46px;bottom:36px;width:92px;height:110px;'
            f'border-radius:46px 46px 8px 8px;background:linear-gradient(180deg,rgba(79,255,176,.28),'
            f'rgba(79,255,176,.08));border:3px solid {a};z-index:3;box-shadow:0 0 40px {a}55"></div>')
    elif room.prop == "dewar":
        for k in range(4):
            x = 9 + k * 22
            out.append(
                f'<div style="position:absolute;left:{x}%;bottom:36px;width:50px;height:62px;'
                f'background:#dfeef7;opacity:.20;border:2px solid {a};border-radius:6px 6px 3px 3px;z-index:3"></div>'
                f'<div style="position:absolute;left:{x}%;bottom:88px;width:50px;height:18px;z-index:3;'
                f'background:radial-gradient(ellipse,rgba(255,255,255,.5),transparent 70%);'
                f'animation:fog 3.4s ease-in-out infinite"></div>')
    elif room.prop == "vials":
        for k in range(9):
            x = 5 + k * 10.5
            out.append(
                f'<div style="position:absolute;left:{x}%;bottom:36px;width:17px;height:44px;'
                f'background:rgba(255,200,97,.18);border:1px solid {a};border-radius:2px 2px 4px 4px;z-index:3">'
                f'<div style="position:absolute;bottom:0;left:0;right:0;height:11px;background:#8a5a1a;opacity:.75"></div></div>')
    else:  # sinks
        out.append(f'<div style="position:absolute;left:4%;right:4%;bottom:74px;height:7px;'
                   f'background:rgba(255,255,255,.13);z-index:2"></div>')
        for k in range(3):
            x = 10 + k * 30
            out.append(
                f'<div style="position:absolute;left:{x}%;bottom:36px;width:86px;height:38px;'
                f'background:#39405f;border:2px solid #5a6486;border-radius:3px;z-index:3"></div>')
    return "".join(out)


def critters(room: Room, seed: int, n: int = 7) -> str:
    """Small animated inhabitants. Randomised per playthrough."""
    rng = random.Random(seed)
    k = room.critter
    a = room.accent
    out = []
    for i in range(n):
        d = rng.uniform(0, 4.2)
        dur = rng.uniform(3.0, 7.5)
        if k == "monkey":
            top = rng.randint(16, 60)
            out.append(
                f'<div style="position:absolute;top:{top}px;left:-40px;z-index:6;'
                f'animation:swing {dur:.1f}s linear {d:.1f}s infinite">'
                f'<div style="width:15px;height:13px;background:#8a6240;border-radius:50% 50% 45% 45%"></div>'
                f'<div style="width:11px;height:9px;background:#d9b18a;border-radius:50%;margin:-9px 0 0 2px"></div>'
                f'<div style="width:19px;height:3px;background:#8a6240;margin:1px 0 0 -3px;border-radius:2px"></div>'
                f'</div>')
        elif k == "mouse":
            out.append(
                f'<div style="position:absolute;bottom:{rng.randint(4,26)}px;left:-30px;z-index:6;'
                f'animation:scurry {dur:.1f}s linear {d:.1f}s infinite">'
                f'<div style="width:13px;height:7px;background:#cfc6bd;border-radius:50% 40% 40% 50%"></div>'
                f'<div style="width:9px;height:1px;background:#cfc6bd;margin-left:-8px"></div></div>')
        elif k == "fish":
            out.append(
                f'<div style="position:absolute;top:{rng.randint(40,100)}px;left:-30px;z-index:6;'
                f'animation:swim {dur:.1f}s linear {d:.1f}s infinite;opacity:.85">'
                f'<div style="width:15px;height:6px;background:{a};border-radius:50% 20% 20% 50%"></div>'
                f'<div style="width:0;height:0;border-top:4px solid transparent;border-bottom:4px solid transparent;'
                f'border-right:7px solid {a};margin:-7px 0 0 -6px"></div></div>')
        elif k == "virus":
            sz = rng.randint(11, 19)
            spikes = "".join(
                f'<div style="position:absolute;left:50%;top:50%;width:2px;height:{sz//2+4}px;'
                f'background:{a};transform-origin:top center;transform:rotate({j*45}deg)"></div>' for j in range(8))
            out.append(
                f'<div style="position:absolute;top:{rng.randint(20,110)}px;left:{rng.randint(4,92)}%;z-index:6;'
                f'animation:float {dur:.1f}s ease-in-out {d:.1f}s infinite;opacity:.8">'
                f'<div style="position:relative;width:{sz}px;height:{sz}px;border-radius:50%;'
                f'background:{a};opacity:.55">{spikes}</div></div>')
        elif k == "alien":
            out.append(
                f'<div style="position:absolute;bottom:{rng.randint(38,80)}px;left:{rng.randint(6,88)}%;z-index:6;'
                f'animation:writhe {dur:.1f}s ease-in-out {d:.1f}s infinite">'
                f'<div style="width:5px;height:{rng.randint(20,40)}px;background:{a};opacity:.6;'
                f'border-radius:3px;transform-origin:bottom center"></div></div>')
        elif k == "flake":
            out.append(
                f'<div style="position:absolute;top:-12px;left:{rng.randint(2,96)}%;width:4px;height:4px;'
                f'border-radius:50%;background:{a};opacity:.75;z-index:6;'
                f'animation:fall {dur:.1f}s linear {d:.1f}s infinite"></div>')
        elif k == "fly":
            out.append(
                f'<div style="position:absolute;top:{rng.randint(24,110)}px;left:{rng.randint(4,92)}%;'
                f'width:4px;height:3px;border-radius:50%;background:#2b2416;z-index:6;'
                f'animation:buzz {rng.uniform(.7,1.6):.1f}s ease-in-out {d:.1f}s infinite"></div>')
        elif k == "bubble":
            out.append(
                f'<div style="position:absolute;bottom:34px;left:{rng.randint(3,95)}%;width:{rng.randint(5,11)}px;'
                f'height:{rng.randint(5,11)}px;border-radius:50%;border:1px solid {a};opacity:.6;z-index:6;'
                f'animation:rise {dur:.1f}s linear {d:.1f}s infinite"></div>')
        else:  # roach
            out.append(
                f'<div style="position:absolute;bottom:{rng.randint(3,16)}px;left:-24px;width:9px;height:5px;'
                f'border-radius:50%;background:#3a2a18;z-index:6;'
                f'animation:scurry {rng.uniform(2.2,4.5):.1f}s linear {d:.1f}s infinite"></div>')
    return "".join(out)


CRITTER_KEYFRAMES = """
<style>
 @keyframes swing { from{transform:translateX(-40px) rotate(-8deg)} to{transform:translateX(105vw) rotate(8deg)} }
 @keyframes scurry { from{transform:translateX(0)} to{transform:translateX(105vw)} }
 @keyframes swim { from{transform:translateX(0)} to{transform:translateX(105vw)} }
 @keyframes float { 0%,100%{transform:translate(0,0)} 50%{transform:translate(14px,-16px)} }
 @keyframes writhe { 0%,100%{transform:rotate(-16deg)} 50%{transform:rotate(16deg)} }
 @keyframes fall { to{transform:translateY(230px)} }
 @keyframes buzz { 0%,100%{transform:translate(0,0)} 25%{transform:translate(16px,-11px)}
                   50%{transform:translate(-9px,7px)} 75%{transform:translate(11px,9px)} }
 @keyframes rise { from{transform:translateY(0);opacity:.6} to{transform:translateY(-150px);opacity:0} }
 @keyframes lick { from{transform:scaleY(.85)} to{transform:scaleY(1.15)} }
 @keyframes fog { 0%,100%{opacity:.25;transform:translateY(0)} 50%{opacity:.6;transform:translateY(-8px)} }
 @keyframes trace { from{transform:translateX(-100%)} to{transform:translateX(220%)} }
</style>
"""


# ==========================================================================
# 6. SCENES
# ==========================================================================
def fuge_sprite(zone: Zone, state: str, lid_open: bool, idx: int, width: int = 112) -> str:
    body = zone.housing if state != "done" else "#2a3350"
    glow = "box-shadow:0 0 22px rgba(255,182,39,0.45);" if state == "active" else ""
    lid_anim = "animation:lift .5s ease-out 1.35s forwards;" if lid_open else ""
    led = GREEN if state == "done" else ("#39405f" if state == "todo" else zone.accent)
    shell = zone.shell
    if shell == "box":
        geo = "width:62px;height:44px;border-radius:5px 5px 3px 3px;"
        lg = "width:68px;height:11px;top:-8px;left:-3px;"
    elif shell == "drum":
        geo = "width:66px;height:50px;border-radius:50% 50% 6px 6px;"
        lg = "width:72px;height:13px;top:-9px;left:-3px;border-radius:50%;"
    elif shell == "tower":
        geo = "width:54px;height:66px;border-radius:4px;"
        lg = "width:60px;height:10px;top:-7px;left:-3px;"
    else:
        geo = "width:72px;height:54px;border-radius:3px;"
        lg = "width:78px;height:14px;top:-10px;left:-3px;"
    stripes = ("background-image:repeating-linear-gradient(45deg,#ff3d8b 0 6px,transparent 6px 12px);"
               if shell == "vault" else "")
    return (
        f'<div style="width:{width}px;display:flex;flex-direction:column;align-items:center">'
        f'<div style="{geo}background:{body};border:2px solid {zone.plate_edge};position:relative;{glow}{stripes}">'
        f'<div style="position:absolute;{lg}background:{zone.housing};border:2px solid {zone.plate_edge};'
        f'border-radius:4px;transform-origin:left bottom;{lid_anim}"></div>'
        f'<div style="position:absolute;bottom:6px;left:12px;width:34px;height:13px;background:#06070d;border-radius:2px"></div>'
        f'<div style="position:absolute;top:6px;right:7px;width:6px;height:6px;border-radius:50%;background:{led}"></div>'
        f'</div>'
        f'<div style="width:100%;height:9px;background:{zone.plate};border-top:2px solid {zone.plate_edge}"></div>'
        f'<div style="font-size:8px;color:#5a6486;margin-top:5px;letter-spacing:.1em">{idx+1:02d}</div>'
        f"</div>")


def scene_attract(seed: int) -> str:
    r = LOBBY
    rng = random.Random(seed)
    bench = "".join([
        beaker("4%", 74, "#5be36a"), beaker("7%", 74, "#3ff2e0", 13, 16),
        flask("11%", 74, "#ff3d8b"), microscope("16%", 74, "#ffb627"),
        rack("22%", 74, "#3ff2e0", 6), bunsen("29%", 74),
        beaker("33%", 74, "#ffb627", 18, 23), flask("37%", 74, "#8fd14f"),
        monitor("42%", 74, "#5be36a"), rack("49%", 74, "#ff3d8b", 5),
        beaker("56%", 74, "#c86bff", 15, 19), microscope("60%", 74, "#3ff2e0"),
        flask("66%", 74, "#ffb627"), bunsen("71%", 74),
        rack("75%", 74, "#8fd14f", 6), beaker("82%", 74, "#57b6ff", 17, 21),
        monitor("86%", 74, "#3ff2e0"), flask("92%", 74, "#5be36a"),
    ])
    fuges = "".join(
        f'<div style="position:absolute;left:{x}%;bottom:36px;z-index:5">'
        f'{fuge_sprite(z, "active" if i == 2 else "todo", False, i, 96)}</div>'
        for i, (x, z) in enumerate([(3, TEACHING), (18, CORE), (34, TEACHING),
                                    (52, COLD), (68, PREP), (84, CORE)]))
    monkeys = critters(VIVARIUM, seed + 1, 4)
    roaches = critters(LOBBY, seed + 2, 3)
    inner = f"""
    {CRITTER_KEYFRAMES}
    <style>
      @keyframes glowpulse {{ 0%,100%{{text-shadow:0 0 12px #ffb627,0 0 34px rgba(255,182,39,.5)}}
                              50%{{text-shadow:0 0 24px #ffb627,0 0 62px rgba(255,182,39,.9)}} }}
      @keyframes blink {{ 0%,49%{{opacity:1}} 50%,100%{{opacity:0}} }}
      @keyframes idle {{ 50%{{transform:translateY(-4px)}} }}
      @keyframes sway {{ 0%,100%{{transform:rotate(-3deg)}} 50%{{transform:rotate(3deg)}} }}
      .logo {{ position:absolute; top:24px; left:0; right:0; text-align:center; z-index:15;
               font-family:'Press Start 2P',monospace; color:#ffb627; animation:glowpulse 2.6s ease-in-out infinite; }}
      .logo .l1 {{ font-size:38px; display:block; letter-spacing:3px; }}
      .logo .l2 {{ font-size:38px; display:block; letter-spacing:3px; margin-top:12px; color:#3ff2e0;
                   text-shadow:0 0 14px #3ff2e0,0 0 36px rgba(63,242,224,.55); }}
      .tag {{ position:absolute; top:130px; left:0; right:0; text-align:center; z-index:15;
              font-family:'IBM Plex Mono',monospace; font-size:13px; color:#8fa0d8; letter-spacing:.44em; }}
      .ins {{ position:absolute; bottom:96px; left:0; right:0; text-align:center; z-index:15;
              font-family:'Press Start 2P',monospace; font-size:11px; color:#5be36a;
              animation:blink 1.1s steps(1) infinite; }}
      .by {{ position:absolute; bottom:8px; right:12px; z-index:22; font-family:'Press Start 2P',monospace;
             font-size:8px; color:#5a6486; letter-spacing:.14em; }}
      .by b {{ color:#ffb627; }}
      .sci {{ position:absolute; bottom:44px; left:44%; width:36px; z-index:8; animation:idle 2.3s ease-in-out infinite; }}
      .banner {{ position:absolute; top:150px; left:50%; margin-left:-92px; width:184px; z-index:6;
                 border:2px dashed rgba(255,255,255,.16); padding:5px; text-align:center;
                 font-size:9px; color:#5a6486; letter-spacing:.16em; animation:sway 5s ease-in-out infinite; }}
    </style>
    <div class="lamp" style="left:4%;width:26%"></div>
    <div class="lamp" style="left:36%;width:26%"></div>
    <div class="lamp" style="left:68%;width:26%"></div>
    <div class="shelf" style="top:58px;left:3%;width:30%"></div>
    <div class="shelf" style="top:58px;left:66%;width:31%"></div>
    <div style="position:absolute;left:3%;right:3%;bottom:66px;height:8px;background:#2b3358;
                border-top:2px solid #4a5580;z-index:3"></div>
    {bench}{fuges}{monkeys}{roaches}
    <div class="sci"><div class="head"><div class="goggles"></div></div><div class="coat"></div><div class="legs"></div></div>
    <div class="banner">SAFETY RECORD:<br>0 DAYS</div>
    <div class="logo"><span class="l1">CENTRIFUGE</span><span class="l2">CHESS</span></div>
    <div class="tag">BALANCE OR BURN</div>
    <div class="ins">&#9654; INSERT SAMPLE TO START</div>
    <div class="by">MADE BY <b>DYLAN</b></div>
    """
    return scene_shell(430, r, inner)


def scene_transit(room: Room, zone: Zone, level_idx: int, seed: int) -> str:
    """Scientist crosses a themed room and arrives at the next machine."""
    inner = f"""
    {CRITTER_KEYFRAMES}
    <style>
      @keyframes cross {{ from{{left:-6%}} to{{left:74%}} }}
      @keyframes arrive {{ 0%,72%{{opacity:0;transform:translateX(28px)}} 100%{{opacity:1;transform:translateX(0)}} }}
      @keyframes fadein {{ to{{opacity:1}} }}
      .sci {{ position:absolute; bottom:40px; width:36px; z-index:9;
              animation:cross 2.0s cubic-bezier(.45,0,.3,1) forwards, bob .2s steps(2) infinite; }}
      .target {{ position:absolute; right:5%; bottom:36px; z-index:8; animation:arrive 2.4s ease-out forwards; }}
      .cap3 {{ opacity:0; animation:fadein .45s ease-out 1.3s forwards; }}
      .door {{ position:absolute; left:2%; bottom:36px; width:52px; height:96px; z-index:3;
               border:3px solid {room.accent}; border-bottom:none; border-radius:4px 4px 0 0;
               background:rgba(0,0,0,.4); }}
    </style>
    {prop_wall(room, seed)}
    <div class="lamp" style="left:5%;width:40%"></div>
    <div class="lamp" style="left:52%;width:40%"></div>
    <div class="door"></div>
    <div class="sign" style="left:2%;top:14px">{room.name}<br><span style="opacity:.6">{room.sign}</span></div>
    {critters(room, seed, 8)}
    <div class="sci"><div class="head"><div class="goggles"></div></div><div class="coat"></div><div class="legs"></div></div>
    <div class="target">{fuge_sprite(zone, "active", True, level_idx, 120)}</div>
    <div class="caption cap3">LEVEL {level_idx+1} &mdash; {zone.name}</div>
    """
    return scene_shell(280, room, inner)


def scene_spin(zone: Zone, room: Room, n: int) -> str:
    spokes = "".join(
        f'<div style="position:absolute;left:50%;top:50%;width:2px;height:66px;background:{zone.plate_edge};'
        f'transform-origin:top center;transform:rotate({i*360/n}deg)"></div>' for i in range(n))
    inner = f"""
    {CRITTER_KEYFRAMES}
    <style>
      @keyframes whirl {{ to{{transform:rotate(360deg)}} }}
      @keyframes shudder {{ 0%,100%{{transform:translate(0,0)}} 25%{{transform:translate(-2px,1px)}}
                            75%{{transform:translate(2px,-1px)}} }}
      .drum {{ position:absolute; left:50%; top:48%; width:190px; height:190px; margin:-95px 0 0 -95px;
               border-radius:50%; background:{zone.plate}; border:5px solid {zone.plate_edge}; z-index:6;
               animation:shudder .08s linear infinite; box-shadow:0 0 44px rgba(0,0,0,.6); }}
      .rot {{ position:absolute; inset:0; animation:whirl .3s linear infinite; }}
      .hub {{ position:absolute; left:50%; top:50%; width:30px; height:30px; margin:-15px 0 0 -15px;
              border-radius:50%; background:#06070d; border:3px solid {zone.plate_edge}; z-index:8; }}
    </style>
    {prop_wall(room, 9)}
    {critters(room, 4, 4)}
    <div class="drum"><div class="rot">{spokes}</div><div class="hub"></div></div>
    <div class="caption">ROTOR AT SPEED&hellip;</div>
    """
    return scene_shell(280, room, inner)


def scene_explode(room: Room, lethal: bool) -> str:
    rng = random.Random(4)
    shards = "".join(
        f'<div style="position:absolute;left:50%;top:46%;width:{rng.randint(5,12)}px;'
        f'height:{rng.randint(5,15)}px;background:{rng.choice([CYAN,GREEN,AMBER,"#ffffff","#ff9b1f"])};'
        f'border-radius:{rng.choice([0,50])}%;z-index:12;'
        f'animation:fly{i%12} {rng.uniform(.7,1.5):.2f}s cubic-bezier(.15,.7,.5,1) .16s forwards"></div>'
        for i in range(44))
    flies = "".join(
        f'@keyframes fly{k} {{ to {{ transform:translate({math.cos(k*math.pi/6)*rng.randint(280,460)}px,'
        f'{math.sin(k*math.pi/6)*rng.randint(160,260)-40}px) rotate({rng.randint(200,900)}deg); opacity:0 }} }}'
        for k in range(12))
    debris = "".join(
        f'<div style="position:absolute;left:{rng.randint(2,96)}%;top:-20px;width:{rng.randint(3,7)}px;'
        f'height:{rng.randint(3,9)}px;background:#5a4a38;z-index:11;'
        f'animation:rain {rng.uniform(.9,1.8):.2f}s linear {rng.uniform(.5,1.4):.2f}s forwards"></div>'
        for _ in range(26))
    cracks = "".join(
        f'<div style="position:absolute;left:50%;top:46%;width:{rng.randint(90,230)}px;height:2px;'
        f'background:rgba(255,255,255,.5);transform-origin:left center;'
        f'transform:rotate({rng.randint(0,359)}deg);z-index:17;opacity:0;'
        f'animation:crack .1s steps(1) {0.34+i*0.03:.2f}s forwards"></div>' for i in range(14))
    msg = "CATASTROPHIC ROTOR FAILURE" if lethal else "ROTOR FAILURE"
    inner = f"""
    <style>
      {flies}
      @keyframes flash {{ 0%{{opacity:0}} 6%{{opacity:1}} 100%{{opacity:0}} }}
      @keyframes shock {{ from{{width:0;height:0;opacity:.95}} to{{width:760px;height:760px;opacity:0}} }}
      @keyframes ball {{ 0%{{transform:scale(.15);opacity:1}} 55%{{transform:scale(1.25);opacity:.96}}
                         100%{{transform:scale(1.9);opacity:0}} }}
      @keyframes quake {{ 0%,100%{{transform:translate(0,0)}} 12%{{transform:translate(-15px,9px)}}
                          28%{{transform:translate(13px,-11px)}} 44%{{transform:translate(-11px,-7px)}}
                          62%{{transform:translate(9px,11px)}} 80%{{transform:translate(-6px,4px)}} }}
      @keyframes smoke {{ from{{transform:translateY(0) scale(.4);opacity:.8}}
                          to{{transform:translateY(-140px) scale(3.2);opacity:0}} }}
      @keyframes rain {{ to{{transform:translateY(300px) rotate(180deg);opacity:.2}} }}
      @keyframes crack {{ to{{opacity:1}} }}
      .quake {{ position:absolute; inset:0; animation:quake .4s linear .16s 4; }}
      .flash {{ position:absolute; inset:0; background:#fff; z-index:16; animation:flash .55s ease-out .14s forwards; }}
      .shock {{ position:absolute; left:50%; top:46%; border:5px solid #fff; border-radius:50%;
                transform:translate(-50%,-50%); z-index:13; animation:shock .75s ease-out .16s forwards; }}
      .shock2 {{ position:absolute; left:50%; top:46%; border:3px solid {AMBER}; border-radius:50%;
                 transform:translate(-50%,-50%); z-index:13; animation:shock 1.05s ease-out .3s forwards; }}
      .ball {{ position:absolute; left:50%; top:46%; width:230px; height:230px; margin:-115px 0 0 -115px;
               border-radius:50%; z-index:12; animation:ball 1.15s ease-out .15s forwards;
               background:radial-gradient(circle,#fff 0%,#fff36b 22%,#ff9b1f 48%,#ff3d0f 72%,transparent 78%); }}
      .puff {{ position:absolute; left:50%; bottom:52px; width:64px; height:64px; margin-left:-32px;
               border-radius:50%; background:#3a3f55; z-index:10; animation:smoke 2s ease-out .35s infinite; }}
      .puff2 {{ left:38%; animation-delay:.75s; }} .puff3 {{ left:60%; animation-delay:1.1s; }}
    </style>
    <div class="quake">{prop_wall(room, 13)}</div>
    <div class="ball"></div><div class="shock"></div><div class="shock2"></div>
    {shards}{debris}
    <div class="puff"></div><div class="puff puff2"></div><div class="puff puff3"></div>
    {cracks}<div class="flash"></div>
    <div class="caption" style="color:#ff3d8b;font-size:12px">{msg}</div>
    """
    return scene_shell(280, room, inner)


def scene_fire(seed: int) -> str:
    rng = random.Random(seed)
    flames = "".join(
        f'<div style="position:absolute;left:{rng.randint(0,97)}%;bottom:{rng.randint(18,46)}px;'
        f'width:{rng.randint(22,52)}px;height:{rng.randint(54,150)}px;border-radius:50% 50% 28% 28%;'
        f'background:linear-gradient(180deg,#fff8b0 0%,#ffd34a 28%,#ff8a1f 62%,#ff2f0a 100%);'
        f'opacity:.92;z-index:8;filter:blur(.4px);'
        f'animation:lick2 {rng.uniform(.32,.72):.2f}s ease-in-out {rng.uniform(0,.6):.2f}s infinite alternate"></div>'
        for _ in range(30))
    embers = "".join(
        f'<div style="position:absolute;left:{rng.randint(0,99)}%;bottom:26px;width:{rng.randint(2,5)}px;'
        f'height:{rng.randint(2,5)}px;border-radius:50%;background:{rng.choice(["#ffca6b","#ff8a1f","#fff2b0"])};'
        f'z-index:10;animation:ember {rng.uniform(1.4,3.6):.1f}s linear {rng.uniform(0,3):.1f}s infinite"></div>'
        for _ in range(46))
    smoke = "".join(
        f'<div style="position:absolute;left:{rng.randint(0,92)}%;bottom:60px;width:{rng.randint(40,90)}px;'
        f'height:{rng.randint(40,90)}px;border-radius:50%;background:rgba(30,26,30,.55);z-index:9;'
        f'animation:billow {rng.uniform(2.4,4.6):.1f}s ease-out {rng.uniform(0,2):.1f}s infinite"></div>'
        for _ in range(12))
    sprink = "".join(
        f'<div style="position:absolute;left:{8+k*12}%;top:0;width:7px;height:11px;background:#6b7a8a;'
        f'z-index:7"></div>' for k in range(8))
    inner = f"""
    <style>
      @keyframes lick2 {{ from{{transform:scaleY(.78) skewX(-6deg)}} to{{transform:scaleY(1.24) skewX(7deg)}} }}
      @keyframes ember {{ from{{transform:translate(0,0);opacity:1}}
                          to{{transform:translate({rng.randint(-40,40)}px,-260px);opacity:0}} }}
      @keyframes billow {{ from{{transform:translateY(0) scale(.5);opacity:.6}}
                           to{{transform:translateY(-190px) scale(2.2);opacity:0}} }}
      @keyframes sirens {{ 0%,100%{{background:rgba(255,61,139,.06)}} 50%{{background:rgba(255,61,139,.34)}} }}
      @keyframes hotshake {{ 0%,100%{{transform:translate(0,0)}} 33%{{transform:translate(-3px,2px)}}
                             66%{{transform:translate(3px,-2px)}} }}
      @keyframes flee {{ from{{left:62%}} to{{left:-8%}} }}
      @keyframes drip {{ to{{transform:translateY(240px);opacity:0}} }}
      .hot {{ position:absolute; inset:0; animation:hotshake .16s linear infinite; }}
      .siren {{ position:absolute; inset:0; z-index:15; animation:sirens .85s ease-in-out infinite; }}
      .runner {{ position:absolute; bottom:34px; width:36px; z-index:12;
                 animation:flee 2.6s linear forwards, bob .13s steps(2) infinite; }}
      .glow {{ position:absolute; inset:0; z-index:6;
               background:radial-gradient(ellipse at 50% 100%,rgba(255,140,30,.55),transparent 68%); }}
    </style>
    <div class="hot">{prop_wall(SUITE3, seed)}</div>
    {sprink}
    <div class="glow"></div>{smoke}{flames}{embers}
    <div class="runner"><div class="head"><div class="goggles"></div></div><div class="coat"></div><div class="legs"></div></div>
    <div class="siren"></div>
    <div class="caption" style="color:#ffca6b;font-size:13px">LAB CONDEMNED</div>
    <div class="sub">EVACUATE &middot; EVACUATE &middot; EVACUATE</div>
    """
    return scene_shell(300, SUITE3, inner)


def scene_ultra_alert() -> str:
    inner = f"""
    <style>
      @keyframes strobe {{ 0%,100%{{background:rgba(255,61,139,.05)}} 50%{{background:rgba(255,61,139,.44)}} }}
      @keyframes dash {{ from{{left:-8%}} to{{left:104%}} }}
      @keyframes typein {{ from{{opacity:0;letter-spacing:1.1em}} to{{opacity:1;letter-spacing:.14em}} }}
      .strobe {{ position:absolute; inset:0; z-index:15; animation:strobe .5s ease-in-out infinite; }}
      .runner {{ position:absolute; bottom:38px; width:36px; z-index:9;
                 animation:dash 2.3s linear forwards, bob .15s steps(2) infinite; }}
      .pa {{ position:absolute; top:70px; left:0; right:0; text-align:center; z-index:16;
             font-family:'Press Start 2P',monospace; font-size:17px; color:#ff3d8b;
             text-shadow:0 0 18px #ff3d8b; animation:typein .85s ease-out forwards; }}
      .pa2 {{ position:absolute; top:114px; left:0; right:0; text-align:center; z-index:16;
              font-family:'IBM Plex Mono',monospace; font-size:12px; color:#ffb627; letter-spacing:.22em; }}
    </style>
    {prop_wall(SUITE3, 17)}
    <div class="runner"><div class="head"><div class="goggles"></div></div><div class="coat"></div><div class="legs"></div></div>
    <div class="strobe"></div>
    <div class="pa">&#9888; SAMPLE ALERT</div>
    <div class="pa2">ULTRACENTRIFUGE SUITE 3 &mdash; REPORT IMMEDIATELY</div>
    """
    return scene_shell(280, SUITE3, inner)


def countdown_html(seconds_left: float) -> str:
    """Ticking clock for the ultracentrifuge. Display only -- the authoritative
    check happens in Python whenever the player acts."""
    return """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');
      .cd { font-family:'Press Start 2P',monospace; font-size:15px; color:#ff3d8b;
            text-align:center; letter-spacing:.12em; text-shadow:0 0 14px #ff3d8b;
            animation:pulse .9s ease-in-out infinite; }
      .bar { height:8px; background:#2b0812; border:1px solid #8f1235; margin-top:7px; }
      .fill { height:100%; background:#ff3d8b; width:__PCT__%; animation:drain __LEFT__s linear forwards; }
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
# 7. ROTOR
# ==========================================================================
def tube_size(mass: float) -> float:
    return 16 + 7.4 * math.sqrt(mass)


def _hex_rgba(hex_col: str, alpha: float) -> str:
    h = hex_col.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def room_decor(room: Room) -> List[dict]:
    """Faint room-themed dressing behind the rotor. Low opacity by design --
    it should read as atmosphere, never compete with the tubes."""
    a = room.accent
    faint = _hex_rgba(a, 0.13)
    fainter = _hex_rgba(a, 0.07)
    d: List[dict] = []
    k = room.critter
    rng = random.Random(len(room.key))

    if k == "bubble" or k == "fish":
        for _ in range(9):
            x, y = rng.uniform(-1.5, 1.5), rng.uniform(-1.5, 1.5)
            s = rng.uniform(0.05, 0.13)
            d.append(dict(type="circle", x0=x - s, y0=y - s, x1=x + s, y1=y + s,
                          line=dict(color=faint, width=2), layer="below"))
    elif k == "flake":
        for _ in range(14):
            x, y = rng.uniform(-1.5, 1.5), rng.uniform(-1.5, 1.5)
            s = rng.uniform(0.02, 0.05)
            d.append(dict(type="circle", x0=x - s, y0=y - s, x1=x + s, y1=y + s,
                          fillcolor=faint, line=dict(width=0), layer="below"))
    elif k == "virus":
        for _ in range(7):
            x, y = rng.uniform(-1.45, 1.45), rng.uniform(-1.45, 1.45)
            s = rng.uniform(0.07, 0.14)
            d.append(dict(type="circle", x0=x - s, y0=y - s, x1=x + s, y1=y + s,
                          fillcolor=fainter, line=dict(color=faint, width=1), layer="below"))
    elif k == "alien":
        for i in range(6):
            x = -1.45 + i * 0.58
            d.append(dict(type="line", x0=x, y0=-1.55, x1=x + rng.uniform(-0.2, 0.2), y1=-0.7,
                          line=dict(color=faint, width=5), layer="below"))
    else:
        for i in range(7):                       # hazard chevrons in the corners
            o = -1.5 + i * 0.16
            d.append(dict(type="line", x0=-1.55, y0=o, x1=o + 1.55, y1=-1.55,
                          line=dict(color=fainter, width=6), layer="below"))
    return d


def rotor_figure(spec: LevelSpec, room: Room, base, player, blocked: Set[int],
                 show_needle: bool, height: int = 600) -> go.Figure:
    z, n = spec.zone, spec.slots
    loads = combined(base, player)
    fig = go.Figure()
    shapes: List[dict] = room_decor(room)

    shapes.append(dict(type="circle", x0=-1.46, y0=-1.46, x1=1.46, y1=1.46,
                       line=dict(color=z.plate_edge, width=3),
                       fillcolor=_hex_rgba(room.wall_bot, 0.80), layer="below"))
    shapes.append(dict(type="circle", x0=-1.27, y0=-1.27, x1=1.27, y1=1.27,
                       line=dict(color=z.plate_edge, width=2), fillcolor=z.plate, layer="below"))
    shapes.append(dict(type="circle", x0=-1.20, y0=-1.20, x1=1.20, y1=1.20,
                       line=dict(color=_hex_rgba(z.accent, 0.30), width=1), layer="below"))

    if spec.style == 2:
        for k in range(n):
            hx, hy = slot_xy(k, n, 0.56)
            shapes.append(dict(type="circle", x0=hx - .05, y0=hy - .05, x1=hx + .05, y1=hy + .05,
                               fillcolor=_hex_rgba(room.wall_bot, 0.9),
                               line=dict(width=0), layer="below"))
    else:
        for k in range(n):
            sx, sy = slot_xy(k, n, 1.0)
            shapes.append(dict(type="line", x0=0, y0=0, x1=sx, y1=sy,
                               line=dict(color=z.plate_edge, width=1), layer="below"))

    if spec.style == 1:
        shapes.append(dict(type="circle", x0=-1.13, y0=-1.13, x1=1.13, y1=1.13,
                           line=dict(color=z.plate_edge, width=9), layer="below"))

    hub = 0.17 if spec.style != 2 else 0.23
    shapes.append(dict(type="circle", x0=-hub, y0=-hub, x1=hub, y1=hub,
                       line=dict(color=z.plate_edge, width=2), fillcolor="#06070d", layer="below"))

    xs, ys, colors, sizes, lines, hover = [], [], [], [], [], []
    for i in range(n):
        x, y = slot_xy(i, n, 1.0)
        xs.append(x); ys.append(y)
        m = loads[i]
        if i in blocked:
            colors.append("rgba(255,61,139,0.10)"); sizes.append(20)
            lines.append(MAGENTA); hover.append(f"{i} · cracked bucket")
        elif m is None:
            colors.append("rgba(6,7,13,0.85)"); sizes.append(20)
            lines.append(STEEL); hover.append(f"{i} · empty — click to load")
        elif base[i] is not None:
            colors.append(GREEN); sizes.append(tube_size(m))
            lines.append("#0a2a10"); hover.append(f"{i} · locked {m:g} g")
        else:
            colors.append(CYAN); sizes.append(tube_size(m))
            lines.append("#062a28"); hover.append(f"{i} · yours {m:g} g — click to lift")

    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="markers", customdata=list(range(n)),
        marker=dict(color=colors, size=sizes, line=dict(color=lines, width=2)),
        hovertext=hover, hoverinfo="text",
        selected=dict(marker=dict(opacity=1.0)), unselected=dict(marker=dict(opacity=1.0)),
        showlegend=False))

    ann = []
    lab_size = 11 if n <= 24 else (9 if n <= 36 else 8)
    for i in range(n):
        lx, ly = slot_xy(i, n, 1.345)
        ann.append(dict(x=lx, y=ly, text=str(i), showarrow=False,
                        font=dict(family="IBM Plex Mono, monospace", size=lab_size, color=DIM)))

    if show_needle:
        vx, vy = imbalance_vector(loads)
        mag = math.hypot(vx, vy)
        if mag > 1e-9:
            scale = min(1.02, 0.20 + mag * 0.075)
            shapes.append(dict(type="line", x0=0, y0=0, x1=scale * vx / mag, y1=-scale * vy / mag,
                               line=dict(color=MAGENTA, width=5), layer="above"))
        else:
            shapes.append(dict(type="circle", x0=-0.10, y0=-0.10, x1=0.10, y1=0.10,
                               fillcolor=GREEN, line=dict(color=GREEN, width=1), layer="above"))
    else:
        ann.append(dict(x=0, y=0, text="?", showarrow=False,
                        font=dict(family="Press Start 2P, monospace", size=15, color=MAGENTA)))

    fig.update_layout(
        shapes=shapes, annotations=ann,
        xaxis=dict(range=[-1.58, 1.58], visible=False, fixedrange=True,
                   scaleanchor="y", scaleratio=1, constrain="domain"),
        yaxis=dict(range=[-1.58, 1.58], visible=False, fixedrange=True, constrain="domain"),
        margin=dict(l=0, r=0, t=0, b=0), height=height,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        clickmode="event+select", showlegend=False,
        hoverlabel=dict(bgcolor="#10142a",
                        font=dict(family="IBM Plex Mono, monospace", size=11, color=BONE)))
    return fig


# ==========================================================================
# 8. LEADERBOARD
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
# 9. STATE
# ==========================================================================
def init_state():
    ss = st.session_state
    ss.setdefault("phase", "title")
    ss.setdefault("level", 0)
    ss.setdefault("name", "")
    ss.setdefault("scores", [])
    ss.setdefault("fails", 0)
    ss.setdefault("lives", START_LIVES)
    ss.setdefault("ultra_count", 0)
    ss.setdefault("in_ultra", False)
    ss.setdefault("nonce", 0)
    ss.setdefault("pick", 0)
    ss.setdefault("total_to_place", 1)
    ss.setdefault("seed", random.randint(0, 9999))
    ss.setdefault("submitted", False)
    ss.setdefault("muted", False)
    ss.setdefault("burned", False)
    ss.setdefault("last_result", None)
    ss.setdefault("show_help", False)


def current_spec() -> LevelSpec:
    return ULTRA_SPEC if st.session_state.in_ultra else LEVELS[st.session_state.level]


def current_room() -> Room:
    return SUITE3 if st.session_state.in_ultra else room_for(st.session_state.level)


def load_level(spec: LevelSpec, keep_fails: bool = False):
    ss = st.session_state
    base, blocked, hand = generate_level(spec, random.Random())
    ss.base, ss.blocked, ss.hand = base, blocked, hand
    ss.total_to_place = spec.to_place
    ss.player = [None] * spec.slots
    ss.pick = 0
    if not keep_fails:
        ss.fails = 0
    ss.nonce += 1
    ss.level_start = time.time()


def reset_game():
    for k in ("phase", "level", "scores", "fails", "lives", "ultra_count", "in_ultra",
              "submitted", "last_result", "show_help", "burned", "seed"):
        st.session_state.pop(k, None)
    init_state()


def finish_run(reason: str, burned: bool):
    st.session_state.gameover_reason = reason
    st.session_state.burned = burned
    st.session_state.phase = "burn"


# ==========================================================================
# 10. SCREENS
# ==========================================================================
def screen_title():
    ss = st.session_state
    components.html(scene_attract(ss.seed), height=444)

    c1, c2, c3, c4 = st.columns([2, 1.3, 1.3, 1.3])
    with c1:
        name = st.text_input("Operator initials", max_chars=12, placeholder="OPERATOR INITIALS",
                             label_visibility="collapsed", key="name_in")
    with c2:
        if st.button("START SHIFT", type="primary", **BTN):
            ss.name = (name or "ANON").strip().upper()[:12] or "ANON"
            ss.level = 0
            ss.scores, ss.lives = [], START_LIVES
            ss.ultra_count, ss.in_ultra = 0, False
            ss.submitted, ss.burned = False, False
            ss.seed = random.randint(0, 9999)
            ss.game_start = time.time()
            load_level(LEVELS[0])
            ss.phase = "intro"
            st.rerun()
    with c3:
        if st.button("HOW TO PLAY", **BTN):
            ss.show_help = not ss.show_help
            st.rerun()
    with c4:
        if st.button("SOUND: OFF" if ss.muted else "SOUND: ON", **BTN):
            ss.muted = not ss.muted
            st.rerun()

    d1, d2 = st.columns([2, 4.9])
    with d1:
        if st.button("HIGH SCORES", **BTN):
            ss.phase = "scores_only"
            st.rerun()

    if ss.show_help:
        st.markdown(
            f"""<div class="cc-panel"><p class="cc-readout" style="text-align:left;line-height:2">
            A spinning tube pulls outward. The rotor is safe only when every pull cancels:
            <span class="cc-amber">two opposite</span>, <span class="cc-amber">three at 120&deg;</span>,
            <span class="cc-amber">four at 90&deg;</span>, or any mix summing to zero.<br>
            Click a rotor position to seat the selected tube. Click your own tube to lift it out.
            The <span style="color:{MAGENTA}">magenta needle</span> shows where the rotor is pulling &mdash;
            shrink it to nothing, close the lid, walk to the next machine.<br>
            <span style="color:{GREEN}">Green</span> = locked in already &nbsp;&middot;&nbsp;
            <span style="color:{CYAN}">Cyan</span> = yours &nbsp;&middot;&nbsp;
            <span style="color:{MAGENTA}">Dashed</span> = cracked bucket, unusable<br>
            <span class="cc-amber">3 lives.</span> Spin unbalanced and one is gone.
            If the PA calls you to Suite 3, there are no lives in there.
            </p></div>""", unsafe_allow_html=True)


def screen_intro():
    ss = st.session_state
    spec = LEVELS[ss.level]
    room = room_for(ss.level)
    st.markdown(f'<div class="cc-strip">{room.name} &nbsp;&middot;&nbsp; {spec.name} '
                f'&nbsp;&middot;&nbsp; {spec.subtitle}</div>', unsafe_allow_html=True)
    components.html(scene_transit(room, spec.zone, ss.level, ss.seed + ss.level), height=294)
    time.sleep(2.5)
    ss.phase = "play"
    ss.level_start = time.time()
    st.rerun()


def screen_ultra_intro():
    ss = st.session_state
    st.markdown('<div class="cc-strip" style="color:#ff3d8b">&#9888; UNSCHEDULED RUN &#9888;</div>',
                unsafe_allow_html=True)
    components.html(scene_ultra_alert(), height=294)
    time.sleep(2.7)
    ss.phase = "play"
    ss.level_start = time.time()
    st.rerun()


def try_place(i: int):
    ss = st.session_state
    if i in ss.blocked or ss.base[i] is not None:
        play("nope"); return
    if ss.player[i] is not None:
        ss.hand.append(ss.player[i]); ss.hand.sort(reverse=True)
        ss.player[i] = None
        ss.pick = min(ss.pick, max(0, len(ss.hand) - 1))
        play("place"); return
    if ss.hand:
        idx = ss.pick if ss.pick < len(ss.hand) else 0
        ss.player[i] = ss.hand.pop(idx)
        ss.pick = min(idx, max(0, len(ss.hand) - 1))
        play("place")
    else:
        play("nope")


def screen_play():
    ss = st.session_state
    spec = current_spec()
    room = current_room()
    loads = combined(ss.base, ss.player)
    resid = imbalance(loads)
    tol = tolerance_for(spec)
    blind = spec.time_limit > 0
    total = ss.total_to_place
    seated = total - len(ss.hand)

    if spec.time_limit and time.time() - ss.level_start > spec.time_limit:
        ss.last_result = ("timeout", resid, tol, 0, 0, 0)
        play("alarm"); ss.phase = "explode"; st.rerun()

    header = (f'<div class="cc-strip" style="color:#ff3d8b">{spec.name} &nbsp;&middot;&nbsp; {spec.subtitle}</div>'
              if spec.sudden_death else
              f'<div class="cc-strip">{room.name} &nbsp;&middot;&nbsp; {spec.name} '
              f'&nbsp;&middot;&nbsp; {spec.subtitle}</div>')
    st.markdown(header, unsafe_allow_html=True)

    left, right = st.columns([1.35, 1], gap="medium")

    with left:
        fig = rotor_figure(spec, room, ss.base, ss.player, ss.blocked,
                           show_needle=not blind, height=620)
        event = st.plotly_chart(fig, key=f"rotor_{ss.nonce}", on_select="rerun",
                                selection_mode="points",
                                config={"displayModeBar": False}, **FIG)
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
                try_place(int(idx))
                ss.nonce += 1
                st.rerun()

    with right:
        hearts = ("&#9829;" * ss.lives +
                  '<span style="color:#333a58">&#9829;</span>' * (START_LIVES - ss.lives))
        tag = "SUITE 3" if spec.sudden_death else f"{ss.level+1:02d}/{len(LEVELS)}"
        clock = (f'<div><span class="k">LIMIT</span><span style="color:{MAGENTA}">'
                 f'{spec.time_limit}s</span></div>' if spec.time_limit
                 else f'<div><span class="k">PAR</span>{spec.par_seconds}s</div>')
        st.markdown(
            f'<div class="cc-panel"><div class="cc-hud">'
            f'<div><span class="k">LEVEL</span>{tag}</div>'
            f'<div><span class="k">SCORE</span>{sum(ss.scores)}</div>'
            f'<div><span class="k">LIVES</span><span style="color:{MAGENTA}">{hearts}</span></div>'
            f'{clock}</div></div>', unsafe_allow_html=True)

        if spec.time_limit:
            left_s = max(0, spec.time_limit - (time.time() - ss.level_start))
            components.html(countdown_html(left_s), height=52)

        # ---- tube tray: make multi-tube levels unmistakable ----
        if ss.hand:
            word = "TUBE" if total == 1 else "TUBES"
            banner = (f'<div class="tray-banner tray-need">PLACE {total} {word}<br>'
                      f'<span style="font-size:.62rem">{seated} SEATED &middot; '
                      f'{len(ss.hand)} STILL IN TRAY</span></div>')
        else:
            banner = ('<div class="tray-banner tray-done">TRAY EMPTY<br>'
                      '<span style="font-size:.62rem">READY TO SPIN</span></div>')
        pips = "".join(f'<span class="pip-done">&#9679;</span>' for _ in range(seated))
        pips += "".join(f'<span class="pip-todo">&#9675;</span>' for _ in range(len(ss.hand)))
        st.markdown(banner + f'<div class="pips">{pips}</div>', unsafe_allow_html=True)

        if ss.hand:
            if ss.pick >= len(ss.hand):
                ss.pick = 0
            cols = st.columns(len(ss.hand))
            for j, c in enumerate(cols):
                with c:
                    if st.button(f"{ss.hand[j]:g} g", key=f"tube_{ss.nonce}_{j}",
                                 type="primary" if j == ss.pick else "secondary", **BTN):
                        ss.pick = j
                        st.rerun()
            st.markdown('<p class="cc-readout" style="font-size:.66rem">'
                        'SELECTED TUBE IS HIGHLIGHTED &middot; CLICK A ROTOR POSITION TO SEAT IT</p>',
                        unsafe_allow_html=True)

        if blind:
            state = ('<span class="cc-bad">CHAMBER SEALED &mdash; no telemetry</span><br>'
                     f'<span style="color:#5a6486;font-size:.7rem">limit {tol:.3f} &middot; one spin only</span>')
        elif resid < 1e-9:
            state = '<span class="cc-ok">BALANCED &mdash; residual 0.000</span>'
        elif resid <= tol and not ss.hand:
            state = f'<span class="cc-ok">WITHIN TOLERANCE &mdash; {resid:.3f} / {tol:.3f}</span>'
        else:
            state = (f'<span class="cc-bad">IMBALANCE {resid:.3f}</span>'
                     f'<span style="color:#5a6486"> / limit {tol:.3f}</span>')
        st.markdown(f'<div class="cc-panel"><p class="cc-readout">{state}</p></div>',
                    unsafe_allow_html=True)

        if ss.hand:
            spin_label = f"{len(ss.hand)} TUBE{'' if len(ss.hand)==1 else 'S'} STILL IN TRAY"
        else:
            spin_label = "SEAL CHAMBER AND SPIN" if spec.sudden_death else "CLOSE LID AND SPIN"
        s1, s2 = st.columns([2, 1])
        with s1:
            if st.button(spin_label, type="primary", disabled=bool(ss.hand), **BTN):
                play("spin"); ss.phase = "spin"; st.rerun()
        with s2:
            if st.button("CLEAR", **BTN):
                for i in range(spec.slots):
                    if ss.player[i] is not None:
                        ss.hand.append(ss.player[i]); ss.player[i] = None
                ss.hand.sort(reverse=True)
                ss.pick = 0
                ss.nonce += 1
                st.rerun()

        with st.expander("Keyboard-friendly slot pad"):
            per_row = 10 if spec.slots >= 30 else 8
            for row_start in range(0, spec.slots, per_row):
                row = list(range(row_start, min(row_start + per_row, spec.slots)))
                for c, i in zip(st.columns(len(row)), row):
                    with c:
                        if i in ss.blocked:
                            st.button("✖", key=f"s{ss.nonce}_{i}", disabled=True, **BTN)
                        elif ss.base[i] is not None:
                            st.button("▪", key=f"s{ss.nonce}_{i}", disabled=True, **BTN)
                        elif ss.player[i] is not None:
                            if st.button("↩", key=f"s{ss.nonce}_{i}", **BTN):
                                try_place(i); ss.nonce += 1; st.rerun()
                        else:
                            if st.button(str(i), key=f"s{ss.nonce}_{i}",
                                         disabled=not ss.hand, **BTN):
                                try_place(i); ss.nonce += 1; st.rerun()


def screen_spin():
    ss = st.session_state
    spec = current_spec()
    loads = combined(ss.base, ss.player)
    resid = imbalance(loads)
    tol = tolerance_for(spec)

    st.markdown('<div class="cc-strip">SPINNING UP</div>', unsafe_allow_html=True)
    components.html(scene_spin(spec.zone, current_room(), spec.slots), height=294)
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
    components.html(scene_explode(current_room(), lethal), height=294)
    time.sleep(2.7)

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
        why = ("The clock ran out with the chamber still open." if kind == "timeout"
               else f"Imbalance hit {resid:.3f} against a {tol:.3f} limit.")
        st.markdown(
            f'<div class="cc-panel"><p class="cc-readout">{why} '
            f'You lost a life and {FAIL_PENALTY} points.<br><br>'
            f'<span class="cc-amber">{ss.lives}</span> of {START_LIVES} lives left. '
            f'A fresh rotor is being wheeled over.</p></div>', unsafe_allow_html=True)
        c = st.columns([1, 2, 1])[1]
        with c:
            if st.button("TAKE THE NEW ROTOR", type="primary", **BTN):
                load_level(spec, keep_fails=True)
                ss.phase = "play"
                st.rerun()
        return

    title = "SUITE 3 CLEARED" if spec.sudden_death else "CLEAN SPIN"
    st.markdown(f'<div class="cc-strip" style="color:#5be36a">{title}</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="cc-panel"><div class="cc-hud">'
        f'<div><span class="k">RESIDUAL</span>{resid:.3f}</div>'
        f'<div><span class="k">ACCURACY</span>{acc}</div>'
        f'<div><span class="k">{"BONUS" if spec.sudden_death else "SPEED"}</span>{speed}</div>'
        f'<div><span class="k">ABORTS</span>-{FAIL_PENALTY*ss.fails}</div>'
        f'<div><span class="k">LEVEL</span>{pts}</div>'
        f'<div><span class="k">TOTAL</span>{sum(ss.scores)}</div>'
        f'</div></div>', unsafe_allow_html=True)

    c = st.columns([1, 2, 1])[1]
    if ss.in_ultra:
        with c:
            if st.button("BACK TO THE BENCH", type="primary", **BTN):
                ss.in_ultra = False
                ss.level += 1
                load_level(LEVELS[ss.level])
                ss.phase = "intro"
                st.rerun()
        return

    last = ss.level + 1 >= len(LEVELS)
    with c:
        if st.button("END SHIFT" if last else "NEXT CENTRIFUGE", type="primary", **BTN):
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
                    ss.level += 1
                    load_level(LEVELS[ss.level])
                    ss.phase = "intro"
            st.rerun()


def screen_burn():
    ss = st.session_state
    st.markdown('<div class="cc-strip" style="color:#ffca6b">SHIFT OVER</div>', unsafe_allow_html=True)
    if ss.burned:
        play_now("over")
        components.html(scene_fire(ss.seed), height=314)
        time.sleep(3.0)
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
        f'</div></div>', unsafe_allow_html=True)

    if not ss.submitted:
        save_score({"name": ss.name, "score": total, "levels": len(ss.scores),
                    "seconds": shift, "when": time.strftime("%Y-%m-%d")})
        ss.submitted = True

    a, b = st.columns([1, 1], gap="medium")
    with a:
        st.markdown('<p class="cc-readout" style="text-align:left">GLOBAL TOP 10</p>',
                    unsafe_allow_html=True)
        st.markdown(leaderboard_table(load_scores(), highlight=ss.name), unsafe_allow_html=True)
        st.markdown(f'<p class="cc-readout" style="font-size:.66rem;text-align:left">'
                    f'stored in: {backend_name()}</p>', unsafe_allow_html=True)
    with b:
        st.markdown('<p class="cc-readout" style="text-align:left">PER LEVEL</p>',
                    unsafe_allow_html=True)
        rows = "".join(f"<tr><td class='rank'>{i+1:02d}</td><td>{v}</td></tr>"
                       for i, v in enumerate(ss.scores)) or "<tr><td>-</td><td>0</td></tr>"
        st.markdown(f'<table class="cc-lb"><tr><th>#</th><th>Points</th></tr>{rows}</table>',
                    unsafe_allow_html=True)
        st.write("")
        if st.button("NEW SHIFT", type="primary", **BTN):
            reset_game()
            st.rerun()


def screen_scores_only():
    st.markdown('<div class="cc-strip">HIGH SCORES</div>', unsafe_allow_html=True)
    c = st.columns([1, 2, 1])[1]
    with c:
        st.markdown(leaderboard_table(load_scores()), unsafe_allow_html=True)
        st.markdown(f'<p class="cc-readout" style="font-size:.66rem">stored in: {backend_name()}</p>',
                    unsafe_allow_html=True)
        if st.button("BACK", **BTN):
            st.session_state.phase = "title"
            st.rerun()


# ==========================================================================
# 11. MAIN
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
