"""
CENTRIFUGE CHESS  v2
A retro-arcade puzzle game about balancing centrifuge rotors.
Made by Dylan.

Run locally:   streamlit run app.py
Deploy:        push to GitHub -> share.streamlit.io
"""

from __future__ import annotations

import base64
import inspect
import io
import uuid
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


def html_block(markup: str, height: int):
    """st.components.v1.html is deprecated. Keep using it while it exists, and fall
    back to an iframe with a data URI if a future Streamlit release removes it, so
    the game does not go blank on an upgrade."""
    fn = getattr(components, "html", None)
    if fn is not None:
        fn(markup, height=height)
        return
    b64 = base64.b64encode(markup.encode("utf-8")).decode("ascii")
    st.iframe("data:text/html;charset=utf-8;base64," + b64, height=height)

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
                "#121b0e", "#172312", "monkey,rabbit,mouse,rat", "cages")
RADIO = Room("radio", "RADIOISOTOPE SUITE", "dosimeter required", "#2b2a0c", "#151405", "#d4ff3d",
             "#1a1907", "#22200b", "flake", "drums")
AQUATICS = Room("aqua", "AQUATICS FACILITY", "3,140 tanks of zebrafish", "#062a3a", "#02141d", "#3fd2f2",
                "#04202c", "#062a38", "fish,bubble", "tanks")
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
TISSUE = Room("tissue", "TISSUE CULTURE", "plate 4 is contaminated again", "#2a1030", "#140618", "#ff8fd1",
              "#1b0a20", "#230d29", "spore", "hoods")
EM = Room("em", "ELECTRON MICROSCOPY", "do not breathe near the column", "#101426", "#06080f", "#9fd8ff",
          "#0a0d18", "#0e1220", "flake", "column")
ANALYTIC = Room("mass", "ANALYTICAL SUITE", "the mass spec is down", "#12242a", "#060f13", "#5be3c8",
                "#0a181d", "#0e2027", "bubble", "instruments")
GREENHOUSE = Room("green", "PLANT GROWTH ROOM", "18 hour days, no exceptions", "#16300f", "#081a06", "#a8ff5c",
                  "#0d2109", "#12290d", "butterfly,aphid", "trays")
SUITE3 = Room("suite3", "SUITE 3", "unscheduled run", "#3a0a16", "#160208", "#ff3d8b",
              "#180309", "#210610", "roach", "airlock")

ALL_ROOMS = [LOBBY, VIVARIUM, RADIO, AQUATICS, BSL4, XENO, CRYO, FLYROOM,
             GLASSWASH, TISSUE, EM, ANALYTIC, GREENHOUSE, SUITE3]

# Fixed tour of the building. Thirteen levels, thirteen different rooms.
ROOM_TOUR = [LOBBY, VIVARIUM, FLYROOM, TISSUE, AQUATICS, GREENHOUSE,
             GLASSWASH, CRYO, ANALYTIC, EM, RADIO, BSL4, XENO]


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
    time_limit: int = 0       # 0 = untimed
    sudden_death: bool = False
    hide_labels: bool = False  # frost: slot numbers iced over
    extra_tubes: int = 0       # decoys in the tray that you do not have to use
    gimmick: str = ""          # banner shown to the player


LEVELS: List[LevelSpec] = [
    LevelSpec("MICROSPIN 6", "personal microfuge", 6, 2, 1, 0, (1.5,), 0.55, 25, TEACHING, 0),
    LevelSpec("MICROSPIN 12", "12-place fixed rotor", 12, 4, 1, 0, (1.5,), 0.55, 30, TEACHING, 2),
    LevelSpec("MICROSPIN 12-X", "mixed tube sizes", 12, 6, 2, 1, (1.5, 2.0), 0.55, 45, TEACHING, 0),
    LevelSpec("BENCHTOP 16", "one bucket is cracked", 16, 8, 2, 2, (1.5, 2.0), 0.50, 55, CORE, 1),
    LevelSpec("BENCHTOP 18", "thirds, not halves", 18, 9, 2, 2, (1.5, 2.0, 5.0), 0.50, 65, CORE, 2),
    LevelSpec("SWING-24", "swinging bucket rotor", 24, 12, 3, 3, (1.5, 2.0, 5.0), 0.50, 75, CORE, 1,
              extra_tubes=2, gimmick="SURPLUS TRAY \u2014 two spare tubes you must NOT use"),
    LevelSpec("CLINICAL-20", "no thirds on this one", 20, 10, 3, 4, (2.0, 5.0, 15.0), 0.48, 80, CORE, 0,
              time_limit=60, gimmick="FIRE DRILL \u2014 60 seconds, then everyone leaves"),
    LevelSpec("SWING-24 HD", "15 mL conicals", 24, 12, 3, 5, (2.0, 5.0, 15.0), 0.45, 80, COLD, 1,
              hide_labels=True, gimmick="FROSTED LID \u2014 position numbers are iced over"),
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

CLEAN_POINTS = 400         # flat award for a clean spin
TIME_POINTS = 400
STREAK_STEP = 0.2          # multiplier gained per consecutive clean spin
STREAK_CAP = 7
FAIL_PENALTY = 75
ULTRA_BONUS = 1500
START_LIVES = 3
ULTRA_CHANCE = 0.35
ULTRA_MAX = 2
ULTRA_EARLIEST = 3


def daily_spec(datestr: Optional[str] = None) -> LevelSpec:
    """One oversized rotor per day, identical for everybody. Built from the date
    so it is reproducible without storing anything."""
    datestr = datestr or time.strftime("%Y-%m-%d")
    rng = random.Random("centrifuge-chess|daily|" + datestr)

    slots = rng.choice([36, 40, 44, 48])
    # total tubes must be reachable with groups of 2/3/4 that divide `slots`;
    # keeping it even means pairs alone always suffice.
    total = rng.choice([slots // 2, slots // 2 + 2, slots // 2 + 4])
    blocked = rng.randint(5, 10)
    while total + blocked > slots - 4:
        blocked -= 1
    to_place = rng.randint(5, 8)
    extra = rng.choice([0, 0, 2, 3])
    zone = rng.choice([TEACHING, CORE, COLD, PREP])
    return LevelSpec(
        name=f"DAILY {slots}", subtitle=f"today's rotor · {datestr}",
        slots=slots, total_tubes=total, to_place=to_place, blocked=blocked,
        masses=(1.5, 2.0, 5.0, 15.0, 50.0), tol_frac=0.40,
        par_seconds=180, zone=zone, style=rng.randint(0, 2),
        extra_tubes=extra,
        gimmick=(f"DAILY CHALLENGE \u2014 {slots} positions, {to_place} tubes"
                 + (f", {extra} spares you must NOT use" if extra else "")),
    )


def daily_room(datestr: Optional[str] = None) -> Room:
    datestr = datestr or time.strftime("%Y-%m-%d")
    pool = [r for r in ALL_ROOMS if r.key != "suite3"]
    return random.Random("room|" + datestr).choice(pool)


def streak_multiplier(streak: int) -> float:
    """1.0 on the first clean spin, +0.2 each consecutive one, capped at 2.4x."""
    return 1.0 + STREAK_STEP * min(streak, STREAK_CAP)


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

    # end-of-shift party loop for The Department
    beat = _t(0.20)
    melody = [659, 784, 880, 784, 659, 587, 523, 587,
              659, 784, 880, 988, 880, 784, 659, 523]
    bass = [131, 131, 165, 165, 196, 196, 165, 165]
    lead = np.concatenate([0.15 * _square(f, beat, 0.25) *
                           np.minimum(1, (beat[-1] - beat) * 12) for f in melody])
    low = np.concatenate([0.13 * _square(f, _t(0.40), 0.5) *
                          np.minimum(1, (0.40 - _t(0.40)) * 6) for f in bass])
    n = min(lead.size, low.size)
    track = lead[:n] + low[:n]
    lib["party"] = np.tile(track, 2)
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
    padding-top: 0.35rem !important; padding-bottom: 0.8rem !important;
    padding-left: 2rem !important; padding-right: 2rem !important;
    max-width: 1500px !important;
}
.stApp { background: #06070d; color: #e8e6f0; }
h1, h2, h3 { font-family: 'Press Start 2P', monospace !important; }
body, p, li, div[data-testid="stMarkdownContainer"] { font-family: 'IBM Plex Mono', monospace; }
[data-testid="stVerticalBlock"] { gap: 0.35rem; }

.cc-strip { font-family:'Press Start 2P',monospace; font-size:0.62rem; color:#ffb627;
            text-align:center; letter-spacing:0.05em; padding:0.15rem 0; margin-bottom:0.25rem; }
.cc-panel { background:rgba(12,16,34,0.88); border:2px solid #2b3358; border-radius:4px;
            padding:0.5rem 0.8rem; margin-bottom:0.4rem; }
.cc-hud { display:flex; justify-content:space-between; gap:0.35rem;
          font-family:'Press Start 2P',monospace; font-size:0.6rem; color:#ffb627; }
.cc-hud span.k { color:#5a6486; display:block; margin-bottom:5px; font-size:0.5rem; }
.cc-readout { font-family:'IBM Plex Mono',monospace; font-size:0.82rem; color:#5a6486;
              text-align:center; letter-spacing:0.04em; }
.cc-ok { color:#5be36a; } .cc-bad { color:#ff3d8b; } .cc-amber { color:#ffb627; }

/* --- tube tray --- */
.tray-banner { font-family:'Press Start 2P',monospace; font-size:0.64rem; text-align:center;
               padding:0.38rem 0.3rem; border-radius:3px; margin-bottom:0.35rem; line-height:1.6; }
.tray-need { background:rgba(255,182,39,0.13); border:2px solid #ffb627; color:#ffb627; }
.tray-done { background:rgba(91,227,106,0.13); border:2px solid #5be36a; color:#5be36a; }
.pips { text-align:center; font-size:1.1rem; letter-spacing:0.28rem; margin:0.05rem 0 0.3rem 0; }
.cc-gimmick { font-family:'Press Start 2P',monospace; font-size:0.62rem; color:#ff3d8b;
              text-align:center; letter-spacing:.06em; border:2px solid #ff3d8b;
              background:rgba(255,61,139,.10); border-radius:3px; padding:0.5rem;
              margin:0 auto 0.55rem auto; max-width:640px; line-height:1.7;
              animation:gpulse 1.6s ease-in-out infinite; }
@keyframes gpulse { 50% { opacity:.62; } }
.cc-centre { text-align:center; }
/* During blocking animations Streamlit keeps the previous screen on the page.
   This drops an opaque sheet over it and lifts the animation above. */
/* Streamlit keeps the PREVIOUS screen mounted while a script is still running and
   tags it data-stale. During our blocking animations that left the old rotor and
   HUD visible underneath. Removing stale elements outright is the correct fix -- an
   overlay only ever covered the viewport, never the page below the fold. */
[data-stale="true"] { display: none !important; }
[data-testid="stElementContainer"][data-stale="true"] { display: none !important; }
.cc-blackout { position:fixed; inset:0; background:#06070d; z-index:1; }
.cc-lift, .cc-lift * { position:relative; z-index:900; }
[data-testid="stCustomComponentV1"], iframe { position:relative; z-index:900; }
.element-container:has(iframe) { position:relative; z-index:900; }
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


# ==========================================================================
# ROOM FIXTURES — each room must read instantly as what it is
# ==========================================================================
def _sign(left: str, top: int, text: str, sub: str, col: str) -> str:
    return (f'<div class="sign" style="left:{left};top:{top}px;max-width:190px">{text}'
            f'<br><span style="opacity:.6">{sub}</span></div>')


def _label(left: str, bottom: int, text: str, col: str, size: int = 7) -> str:
    return (f'<div style="position:absolute;left:{left};bottom:{bottom}px;z-index:7;'
            f'font-family:\'Press Start 2P\',monospace;font-size:{size}px;color:{col};'
            f'opacity:.8;letter-spacing:.08em">{text}</div>')


def props_vivarium(room: Room, rng: random.Random) -> str:
    a = room.accent
    out = []
    # mouse + rat racks, three tiers each
    for x in (1.5, 17):
        for tier in range(3):
            y = 40 + tier * 50
            bars = "".join(f'<div style="position:absolute;left:{5+j*11}px;top:2px;bottom:2px;'
                           f'width:2px;background:#8d9a7a"></div>' for j in range(11))
            animals = "".join(
                f'<div style="position:absolute;bottom:4px;left:{12+k*32}px;width:15px;height:8px;'
                f'border-radius:50% 40% 40% 50%;background:{rng.choice(["#e6dfd4","#b9ada0","#cbbba6"])}"></div>'
                f'<div style="position:absolute;bottom:7px;left:{4+k*32}px;width:10px;height:2px;'
                f'background:#cfc6bd"></div>' for k in range(rng.randint(1, 3)))
            out.append(
                f'<div style="position:absolute;left:{x}%;bottom:{y}px;width:128px;height:46px;'
                f'border:3px solid #8d9a7a;background:rgba(220,214,190,0.10);z-index:4">{bars}{animals}'
                f'<div style="position:absolute;right:-9px;top:9px;width:9px;height:24px;'
                f'background:#bcd6e8;border:1px solid #8d9a7a"></div>'
                f'<div style="position:absolute;top:-11px;left:2px;font-family:monospace;font-size:7px;'
                f'color:{a};opacity:.75">CAGE {tier+1}{"A" if x<10 else "B"}</div></div>')
    # rabbit pens
    for k, x in enumerate((34, 46)):
        out.append(
            f'<div style="position:absolute;left:{x}%;bottom:40px;width:150px;height:96px;'
            f'border:3px solid #8d9a7a;background:rgba(255,255,255,.05);z-index:4">'
            + "".join(f'<div style="position:absolute;left:{10+j*16}px;top:0;bottom:0;width:2px;'
                      f'background:#8d9a7a;opacity:.8"></div>' for j in range(9))
            + f'<div style="position:absolute;bottom:6px;left:24px;width:30px;height:17px;'
              f'background:#e8e2d6;border-radius:50% 45% 40% 50%"></div>'
              f'<div style="position:absolute;bottom:20px;left:44px;width:13px;height:12px;'
              f'background:#e8e2d6;border-radius:50%"></div>'
              f'<div style="position:absolute;bottom:30px;left:46px;width:4px;height:13px;'
              f'background:#e8e2d6;border-radius:2px;transform:rotate(-12deg)"></div>'
              f'<div style="position:absolute;bottom:30px;left:52px;width:4px;height:13px;'
              f'background:#e8e2d6;border-radius:2px;transform:rotate(12deg)"></div>'
              f'<div style="position:absolute;bottom:6px;right:14px;width:34px;height:11px;'
              f'background:#b39a5c;border-radius:3px"></div></div>')
    # primate enclosure with rope, swing and a climbing frame
    out.append(
        f'<div style="position:absolute;left:60%;bottom:40px;width:280px;height:210px;'
        f'border:5px solid #8d9a7a;background:rgba(0,0,0,.24);z-index:4">'
        + "".join(f'<div style="position:absolute;left:{10+j*18}px;top:0;bottom:0;width:3px;'
                  f'background:#8d9a7a;opacity:.85"></div>' for j in range(15))
        + f'<div style="position:absolute;top:20px;left:8px;right:8px;height:4px;background:#7a5c3a;border-radius:2px"></div>'
          f'<div style="position:absolute;top:24px;left:46%;width:4px;height:54px;background:#7a5c3a"></div>'
          f'<div style="position:absolute;top:76px;left:38%;width:56px;height:8px;background:#7a5c3a;border-radius:3px"></div>'
          f'<div style="position:absolute;bottom:0;left:30px;width:6px;height:120px;background:#7a5c3a"></div>'
          f'<div style="position:absolute;bottom:60px;left:30px;width:80px;height:6px;background:#7a5c3a"></div>'
          f'<div style="position:absolute;bottom:110px;right:26px;width:6px;height:70px;background:#7a5c3a"></div>'
          f'<div style="position:absolute;bottom:14px;right:24px;width:46px;height:30px;'
          f'background:#5a4228;border-radius:4px"></div></div>')
    # feed bins, hay, hose, clipboard
    out.append(f'<div style="position:absolute;left:88%;bottom:40px;width:64px;height:60px;'
               f'background:#6b5a3a;border:2px solid #8d9a7a;border-radius:3px;z-index:4"></div>'
               f'<div style="position:absolute;left:94%;bottom:40px;width:58px;height:42px;'
               f'background:#b39a5c;border-radius:5px;z-index:4;opacity:.85"></div>'
               f'<div style="position:absolute;left:88%;bottom:112px;width:44px;height:56px;'
               f'background:#e8ecf5;opacity:.30;border:2px solid #8a97ab;z-index:4"></div>')
    out.append(_label("60%", 262, "PRIMATE ENCLOSURE 2", a))
    out.append(_label("2%", 200, "RODENT HOLDING", a))
    out.append(_label("34%", 148, "LAGOMORPH PENS", a))
    return "".join(out)

def props_fly(room: Room, rng: random.Random) -> str:
    a = room.accent
    out = []
    # four shelves of vials
    for shelf, y in enumerate((40, 96, 152, 208)):
        for k in range(15):
            x = 2 + k * 6.3
            fill = rng.choice(["#8a5a1a", "#a86a20", "#6d4614"])
            flies_in = "".join(
                f'<div style="position:absolute;top:{rng.randint(4,26)}px;left:{rng.randint(3,12)}px;'
                f'width:3px;height:2px;background:#2b2416;border-radius:50%"></div>'
                for _ in range(rng.randint(0, 3)))
            out.append(
                f'<div style="position:absolute;left:{x}%;bottom:{y}px;width:19px;height:48px;'
                f'background:rgba(255,200,97,.16);border:1px solid {a};border-radius:2px 2px 5px 5px;z-index:4">'
                f'<div style="position:absolute;bottom:0;left:0;right:0;height:14px;background:{fill};opacity:.85"></div>'
                f'<div style="position:absolute;top:2px;left:5px;width:8px;height:5px;background:#dcd6c4;'
                f'border-radius:2px"></div>{flies_in}</div>')
        out.append(f'<div style="position:absolute;left:1%;right:1%;bottom:{y-6}px;height:6px;'
                   f'background:#5a4a2a;z-index:3"></div>')
    # pushing station: CO2 pad, scope, brush, morgue
    out.append(f'<div style="position:absolute;left:60%;bottom:264px;width:120px;height:16px;'
               f'background:#dcd6c4;opacity:.55;border-radius:2px;z-index:4"></div>')
    out.append(microscope("62%", 280, a))
    out.append(f'<div style="position:absolute;left:70%;bottom:280px;width:5px;height:30px;'
               f'background:#8a6a3a;z-index:4"></div>'
               f'<div style="position:absolute;left:69.4%;bottom:308px;width:14px;height:9px;'
               f'background:#3a2a14;border-radius:2px;z-index:4"></div>')
    out.append(f'<div style="position:absolute;left:76%;bottom:266px;width:52px;height:38px;'
               f'background:#2a1d0e;border:2px solid {a};border-radius:3px;z-index:4">'
               f'<div style="position:absolute;bottom:4px;left:5px;font-family:monospace;font-size:7px;'
               f'color:{a};opacity:.8">MORGUE</div></div>')
    # CO2 cylinder
    out.append(f'<div style="position:absolute;left:88%;bottom:264px;width:40px;height:120px;'
               f'background:#4a4a2a;border:2px solid {a};border-radius:20px 20px 3px 3px;z-index:4">'
               f'<div style="position:absolute;top:8px;left:11px;width:18px;height:11px;'
               f'background:{a};opacity:.55;border-radius:2px"></div></div>')
    # banana crate + fruit
    out.append(f'<div style="position:absolute;left:3%;bottom:266px;width:80px;height:44px;'
               f'background:#7a5c22;border:2px solid #a8863a;z-index:4"></div>')
    for k in range(4):
        out.append(f'<div style="position:absolute;left:{4+k*1.6}%;bottom:{306+ (k%2)*9}px;width:44px;'
                   f'height:13px;background:#e8c95c;border-radius:9px;z-index:5;'
                   f'transform:rotate({-14+k*9}deg)"></div>')
    # incubator with fly stocks
    out.append(f'<div style="position:absolute;left:20%;bottom:266px;width:120px;height:100px;'
               f'background:#3a2a14;border:3px solid #a8863a;border-radius:4px;z-index:4">'
               f'<div style="position:absolute;top:12px;left:14px;width:60px;height:60px;'
               f'border-radius:50%;border:3px solid {a};background:rgba(255,200,97,.14)"></div>'
               f'<div style="position:absolute;bottom:8px;left:14px;font-family:monospace;font-size:9px;'
               f'color:{a};opacity:.85">25.0 C</div></div>')
    # giant fly poster
    out.append(f'<div style="position:absolute;left:40%;bottom:270px;width:120px;height:96px;'
               f'background:rgba(255,200,97,.08);border:3px solid {a};z-index:4">'
               f'<div style="position:absolute;top:26px;left:32px;width:56px;height:30px;'
               f'background:#3a2f18;border-radius:50% 40% 40% 50%"></div>'
               f'<div style="position:absolute;top:18px;left:26px;width:22px;height:20px;'
               f'background:#c0392b;border-radius:50%;opacity:.9"></div>'
               f'<div style="position:absolute;top:16px;left:52px;width:38px;height:14px;'
               f'background:rgba(255,255,255,.35);border-radius:50% 50% 20% 20%;transform:rotate(-18deg)"></div>'
               f'<div style="position:absolute;bottom:5px;left:0;right:0;text-align:center;'
               f'font-family:monospace;font-size:8px;color:{a}">D. MELANOGASTER</div></div>')
    # flypaper
    for k in range(5):
        out.append(f'<div style="position:absolute;left:{12+k*19}%;top:0;width:8px;height:{56+k*13}px;'
                   f'background:#c8a24a;opacity:.75;z-index:6"></div>')
    out.append(_label("2%", 380, "DROSOPHILA STOCKS", a))
    return "".join(out)

def props_aquatics(room: Room, rng: random.Random) -> str:
    a = room.accent
    out = []
    # three tiers of tanks, fish inside, labelled
    for tier, y in enumerate((40, 118, 196)):
        for k in range(6):
            x = 1.5 + k * 16.4
            fish = "".join(
                f'<div style="position:absolute;top:{rng.randint(8,46)}px;left:{rng.randint(8,110)}px;'
                f'width:11px;height:5px;border-radius:50% 20% 20% 50%;background:{a};opacity:.85"></div>'
                for _ in range(rng.randint(3, 7)))
            weed = "".join(
                f'<div style="position:absolute;bottom:9px;left:{12+j*26}px;width:4px;'
                f'height:{rng.randint(12,26)}px;background:#3f8f5a;opacity:.7;border-radius:3px;'
                f'transform-origin:bottom center;animation:sway2 {2.0+j*0.4:.1f}s ease-in-out infinite"></div>'
                for j in range(3))
            out.append(
                f'<div style="position:absolute;left:{x}%;bottom:{y}px;width:132px;height:66px;'
                f'border:3px solid {a};z-index:4;overflow:hidden;'
                f'background:linear-gradient(180deg,rgba(63,210,242,.36),rgba(63,210,242,.15));'
                f'box-shadow:inset 0 0 26px rgba(63,210,242,.45)">{fish}{weed}'
                f'<div style="position:absolute;bottom:0;left:0;right:0;height:9px;background:#2a4b57;opacity:.85"></div>'
                f'<div style="position:absolute;top:3px;left:4px;font-family:monospace;font-size:8px;'
                f'color:#d6f4ff;opacity:.75">AB{tier}{k}</div></div>')
    # filtration tower + pumps
    out.append(
        f'<div style="position:absolute;right:2%;bottom:40px;width:96px;height:260px;'
        f'background:#123844;border:3px solid {a};border-radius:5px;z-index:5">'
        + "".join(f'<div style="position:absolute;top:{18+j*46}px;left:12px;right:12px;height:28px;'
                  f'background:rgba(63,210,242,.22);border:2px solid {a}"></div>' for j in range(5))
        + f'<div style="position:absolute;bottom:10px;left:26px;width:44px;height:22px;background:{a};'
          f'opacity:.5;border-radius:3px"></div></div>')
    # overhead plumbing
    out.append(f'<div style="position:absolute;left:0;right:0;bottom:274px;height:11px;background:#4a6b78;z-index:3"></div>')
    for k in range(10):
        out.append(f'<div style="position:absolute;left:{4+k*10}%;bottom:262px;width:7px;height:18px;'
                   f'background:#4a6b78;z-index:3"></div>')
    # big display tank with a shark that should not be there
    out.append(
        f'<div style="position:absolute;left:36%;bottom:288px;width:300px;height:104px;'
        f'border:4px solid {a};z-index:5;overflow:hidden;'
        f'background:linear-gradient(180deg,rgba(63,210,242,.28),rgba(63,210,242,.10))">'
        f'<div style="position:absolute;top:38px;left:-90px;width:86px;height:26px;background:#5a7f8c;'
        f'border-radius:50% 18% 18% 50%;animation:swim 9s linear infinite">'
        f'<div style="position:absolute;top:-13px;left:32px;width:0;height:0;'
        f'border-left:9px solid transparent;border-right:9px solid transparent;'
        f'border-bottom:15px solid #5a7f8c"></div></div>'
        f'<div style="position:absolute;top:5px;left:8px;font-family:monospace;font-size:9px;'
        f'color:#d6f4ff;opacity:.8">DISPLAY TANK &mdash; DO NOT FEED</div></div>')
    # nets on the wall
    for k, x in enumerate((3, 9)):
        out.append(f'<div style="position:absolute;left:{x}%;bottom:290px;width:8px;height:56px;'
                   f'background:#8a7a5a;z-index:5"></div>'
                   f'<div style="position:absolute;left:{x-1.4}%;bottom:334px;width:46px;height:28px;'
                   f'border:3px solid #8a7a5a;border-radius:50%;z-index:5"></div>')
    out.append(_label("2%", 380, "ZEBRAFISH SYSTEM &mdash; 3,140 TANKS", a))
    return "".join(out)

def props_radio(room: Room, rng: random.Random) -> str:
    a = room.accent
    out = []
    # lead brick wall
    for row in range(4):
        for k in range(9):
            out.append(f'<div style="position:absolute;left:{2+k*7.4+ (3.7 if row%2 else 0)}%;'
                       f'bottom:{40+row*24}px;width:82px;height:22px;background:#4a4a52;'
                       f'border:1px solid #62626e;z-index:3"></div>')
    # waste drums with trefoil
    for k in range(4):
        x = 66 + k * 8
        tre = "".join(
            f'<div style="position:absolute;left:50%;top:50%;width:0;height:0;'
            f'border-left:9px solid transparent;border-right:9px solid transparent;'
            f'border-bottom:15px solid {a};transform-origin:center 0;'
            f'transform:translate(-50%,0) rotate({j*120}deg)"></div>' for j in range(3))
        out.append(
            f'<div style="position:absolute;left:{x}%;bottom:40px;width:52px;height:74px;'
            f'background:#54520e;border:3px solid {a};border-radius:5px;z-index:5;'
            f'box-shadow:0 0 32px rgba(212,255,61,.45)">'
            f'<div style="position:absolute;top:18px;left:50%;margin-left:-19px;width:38px;height:38px;'
            f'border-radius:50%;background:rgba(0,0,0,.35);overflow:hidden">{tre}</div></div>')
    # geiger counter
    out.append(f'<div style="position:absolute;left:52%;bottom:120px;width:64px;height:44px;'
               f'background:#2a2a14;border:2px solid {a};border-radius:3px;z-index:5">'
               f'<div style="position:absolute;bottom:8px;left:50%;width:3px;height:24px;'
               f'background:{a};transform-origin:bottom center;'
               f'animation:needle .28s ease-in-out infinite alternate"></div></div>')
    # hazard tape
    out.append(f'<div style="position:absolute;left:0;right:0;bottom:190px;height:16px;z-index:6;'
               f'background:repeating-linear-gradient(45deg,{a} 0 14px,#1a1907 14px 28px);opacity:.85"></div>')
    out.append(_label("2%", 212, "RADIOISOTOPE &mdash; DOSIMETER REQUIRED", a))
    return "".join(out)


def props_cryo(room: Room, rng: random.Random) -> str:
    a = room.accent
    out = []
    for k in range(5):
        x = 3 + k * 15
        out.append(
            f'<div style="position:absolute;left:{x}%;bottom:40px;width:96px;height:104px;'
            f'background:linear-gradient(180deg,#dfeef7 0%,#9fc4d6 100%);opacity:.30;'
            f'border:3px solid {a};border-radius:10px 10px 4px 4px;z-index:4"></div>'
            f'<div style="position:absolute;left:{x}%;bottom:140px;width:96px;height:16px;'
            f'background:#cfe6f2;opacity:.35;border-radius:8px;z-index:4"></div>'
            f'<div style="position:absolute;left:{x}%;bottom:152px;width:96px;height:34px;z-index:5;'
            f'background:radial-gradient(ellipse,rgba(255,255,255,.55),transparent 72%);'
            f'animation:fog {2.8+k*0.4:.1f}s ease-in-out infinite"></div>')
    # LN2 line + thermometer
    out.append(f'<div style="position:absolute;left:0;right:0;bottom:206px;height:8px;'
               f'background:#8fb8cc;opacity:.5;z-index:3"></div>')
    out.append(f'<div style="position:absolute;left:80%;bottom:150px;width:70px;height:52px;'
               f'background:#0b1c24;border:2px solid {a};border-radius:3px;z-index:6;'
               f'font-family:\'Press Start 2P\',monospace;font-size:11px;color:{a};'
               f'display:flex;align-items:center;justify-content:center">-80&deg;</div>')
    # frost on the lens
    for _ in range(26):
        out.append(f'<div style="position:absolute;left:{rng.randint(0,98)}%;top:{rng.randint(0,80)}%;'
                   f'width:{rng.randint(2,6)}px;height:{rng.randint(2,6)}px;background:#fff;opacity:.22;'
                   f'border-radius:50%;z-index:7"></div>')
    out.append(_label("2%", 250, "CRYOSTORAGE &mdash; VAPOUR PHASE", a))
    return "".join(out)


def props_bsl4(room: Room, rng: random.Random) -> str:
    a = room.accent
    out = []
    # airlock
    out.append(
        f'<div style="position:absolute;left:50%;margin-left:-95px;bottom:40px;width:190px;height:180px;'
        f'border:6px solid {a};border-radius:10px 10px 0 0;background:rgba(0,0,0,.42);z-index:4;'
        f'box-shadow:0 0 44px {a}55">'
        f'<div style="position:absolute;top:28px;left:50%;margin-left:-42px;width:84px;height:84px;'
        f'border-radius:50%;border:5px solid {a};opacity:.85;background:rgba(200,107,255,.10)"></div>'
        + "".join(f'<div style="position:absolute;top:{40+j*22}px;right:-14px;width:11px;height:11px;'
                  f'border-radius:50%;background:{a};opacity:.8"></div>' for j in range(3))
        + '</div>')
    # hazmat suits hanging
    for k, x in enumerate((6, 17, 76, 87)):
        out.append(
            f'<div style="position:absolute;left:{x}%;bottom:64px;width:52px;height:118px;'
            f'background:#e8e6f0;opacity:.20;border-radius:24px 24px 5px 5px;z-index:4"></div>'
            f'<div style="position:absolute;left:{x}%;bottom:176px;width:52px;height:8px;'
            f'background:#6b7a8a;z-index:4"></div>'
            f'<div style="position:absolute;left:calc({x}% + 14px);bottom:150px;width:24px;height:20px;'
            f'border-radius:50%;background:{a};opacity:.35;z-index:5"></div>')
    # biohazard trefoil signs
    for x in (30, 66):
        tre = "".join(
            f'<div style="position:absolute;left:50%;top:52%;width:16px;height:16px;'
            f'border:4px solid {a};border-radius:50%;transform-origin:center -6px;'
            f'transform:translate(-50%,-50%) rotate({j*120}deg)"></div>' for j in range(3))
        out.append(f'<div style="position:absolute;left:{x}%;bottom:196px;width:48px;height:48px;'
                   f'z-index:6;background:rgba(0,0,0,.35);border:2px solid {a}">{tre}</div>')
    # pressure gauge
    out.append(f'<div style="position:absolute;left:44%;bottom:224px;width:44px;height:44px;'
               f'border:3px solid {a};border-radius:50%;z-index:6;background:rgba(0,0,0,.4)">'
               f'<div style="position:absolute;left:50%;bottom:50%;width:2px;height:15px;background:{a};'
               f'transform-origin:bottom center;transform:rotate(38deg)"></div></div>')
    out.append(_label("2%", 252, "BSL-4 &mdash; POSITIVE PRESSURE", a))
    return "".join(out)


def props_xeno(room: Room, rng: random.Random) -> str:
    a = room.accent
    out = []
    # main containment pod
    tentacles = "".join(
        f'<div style="position:absolute;bottom:14px;left:{18+j*17}px;width:7px;'
        f'height:{rng.randint(40,86)}px;background:{a};opacity:.55;border-radius:4px;'
        f'transform-origin:bottom center;animation:writhe {2.2+j*0.5:.1f}s ease-in-out infinite"></div>'
        for j in range(4))
    out.append(
        f'<div style="position:absolute;left:50%;margin-left:-70px;bottom:40px;width:140px;height:190px;'
        f'border-radius:70px 70px 8px 8px;border:4px solid {a};z-index:5;overflow:hidden;'
        f'background:linear-gradient(180deg,rgba(79,255,176,.30),rgba(79,255,176,.08));'
        f'box-shadow:0 0 50px {a}66">{tentacles}</div>')
    # specimen jars
    for k in range(6):
        x = 4 + k * 7.5
        out.append(
            f'<div style="position:absolute;left:{x}%;bottom:44px;width:44px;height:60px;'
            f'border:2px solid {a};border-radius:5px;background:rgba(79,255,176,.13);z-index:4">'
            f'<div style="position:absolute;bottom:{rng.randint(6,20)}px;left:{rng.randint(6,20)}px;'
            f'width:{rng.randint(9,17)}px;height:{rng.randint(9,17)}px;border-radius:50% 20% 50% 20%;'
            f'background:{a};opacity:.6"></div></div>')
    # skeleton on the wall
    out.append(f'<div style="position:absolute;left:80%;bottom:118px;width:14px;height:60px;'
               f'background:#cfe8dc;opacity:.35;z-index:4"></div>'
               + "".join(f'<div style="position:absolute;left:{76+ (0 if j%2 else 6)}%;'
                         f'bottom:{124+j*11}px;width:52px;height:4px;background:#cfe8dc;opacity:.3;'
                         f'z-index:4"></div>' for j in range(5))
               + f'<div style="position:absolute;left:79%;bottom:180px;width:30px;height:26px;'
                 f'border-radius:50% 50% 40% 40%;background:#cfe8dc;opacity:.35;z-index:4"></div>')
    # rotating warning light
    out.append(f'<div style="position:absolute;left:50%;margin-left:-14px;bottom:236px;width:28px;'
               f'height:16px;border-radius:14px 14px 0 0;background:{MAGENTA};z-index:6;'
               f'animation:warn 1.1s ease-in-out infinite"></div>')
    out.append(_label("2%", 252, "XENOBIOLOGY &mdash; SAMPLE 9 IS AWAKE", a))
    return "".join(out)


def props_glass(room: Room, rng: random.Random) -> str:
    a = room.accent
    out = []
    # sinks
    for k in range(3):
        x = 4 + k * 20
        out.append(
            f'<div style="position:absolute;left:{x}%;bottom:40px;width:170px;height:58px;'
            f'background:#39405f;border:3px solid #6b7a8a;border-radius:4px;z-index:4"></div>'
            f'<div style="position:absolute;left:calc({x}% + 74px);bottom:98px;width:9px;height:38px;'
            f'background:#8a97ab;z-index:4"></div>'
            f'<div style="position:absolute;left:calc({x}% + 52px);bottom:130px;width:44px;height:9px;'
            f'background:#8a97ab;border-radius:4px;z-index:4"></div>')
    # drying rack with glassware
    out.append(f'<div style="position:absolute;left:66%;bottom:40px;width:210px;height:180px;'
               f'border:3px solid #6b7a8a;background:rgba(255,255,255,.05);z-index:4"></div>')
    for tier in range(3):
        for k in range(5):
            out.append(beaker(f"calc(67% + {k*38}px)", 52 + tier * 58,
                              rng.choice(["rgba(159,184,216,.5)", "rgba(63,242,224,.35)"]), 22, 30))
        out.append(f'<div style="position:absolute;left:66%;width:210px;bottom:{46+tier*58}px;'
                   f'height:4px;background:#6b7a8a;z-index:5"></div>')
    # autoclave
    out.append(f'<div style="position:absolute;left:44%;bottom:40px;width:96px;height:120px;'
               f'background:#4a5568;border:3px solid #8a97ab;border-radius:4px;z-index:4">'
               f'<div style="position:absolute;top:22px;left:50%;margin-left:-30px;width:60px;height:60px;'
               f'border-radius:50%;border:4px solid #8a97ab;background:#2a3040"></div></div>')
    # steam
    for k in range(7):
        out.append(f'<div style="position:absolute;left:{rng.randint(4,90)}%;bottom:100px;'
                   f'width:{rng.randint(30,60)}px;height:{rng.randint(30,60)}px;border-radius:50%;'
                   f'background:rgba(255,255,255,.13);z-index:6;'
                   f'animation:billow {rng.uniform(2.6,4.4):.1f}s ease-out {rng.uniform(0,2):.1f}s infinite"></div>')
    out.append(_label("2%", 234, "GLASSWASH &mdash; STILL WET", a))
    return "".join(out)


def props_lobby(room: Room, rng: random.Random) -> str:
    a = room.accent
    out = []
    out.append(f'<div style="position:absolute;left:2%;right:2%;bottom:96px;height:9px;'
               f'background:#2b3358;border-top:2px solid #4a5580;z-index:3"></div>')
    kit = [beaker("4%", 105, "#5be36a"), flask("9%", 105, "#ff3d8b"),
           microscope("14%", 105, a), rack("20%", 105, "#3ff2e0", 6),
           bunsen("27%", 105), monitor("32%", 105, "#5be36a"),
           beaker("39%", 105, "#ffb627", 20, 26), flask("44%", 105, "#8fd14f"),
           rack("50%", 105, "#ff3d8b", 5), microscope("58%", 105, "#3ff2e0"),
           beaker("64%", 105, "#c86bff", 18, 24), monitor("70%", 105, "#3ff2e0"),
           flask("78%", 105, "#ffb627"), rack("84%", 105, "#8fd14f", 6),
           beaker("92%", 105, "#57b6ff", 19, 25)]
    out.extend(kit)
    # whiteboard with scrawl
    out.append(f'<div style="position:absolute;left:6%;bottom:150px;width:220px;height:90px;'
               f'background:#e8ecf5;opacity:.14;border:2px solid #6b7a8a;z-index:4"></div>')
    for k in range(5):
        out.append(f'<div style="position:absolute;left:{7+ (k%2)*2}%;bottom:{160+k*15}px;'
                   f'width:{rng.randint(70,180)}px;height:3px;background:{a};opacity:.35;z-index:5"></div>')
    # coffee machine
    out.append(f'<div style="position:absolute;left:88%;bottom:150px;width:56px;height:70px;'
               f'background:#3a4258;border:2px solid #6b7a8a;border-radius:3px;z-index:4">'
               f'<div style="position:absolute;bottom:8px;left:14px;width:26px;height:18px;'
               f'background:#7a4a2a;border-radius:2px"></div></div>')
    out.append(_label("2%", 244, "MAIN LAB", a))
    return "".join(out)


def props_tissue(room: Room, rng: random.Random) -> str:
    a = room.accent
    out = []
    # laminar flow hoods with sash glass
    for k, x in enumerate((3, 36, 69)):
        out.append(
            f'<div style="position:absolute;left:{x}%;bottom:40px;width:250px;height:190px;'
            f'background:rgba(255,255,255,.07);border:4px solid #8a97ab;z-index:4">'
            f'<div style="position:absolute;top:10px;left:10px;right:10px;height:74px;'
            f'background:rgba(255,143,209,.16);border:2px solid {a}"></div>'
            f'<div style="position:absolute;bottom:10px;left:12px;right:12px;height:76px;'
            f'background:rgba(0,0,0,.30)"></div>'
            f'<div style="position:absolute;bottom:18px;left:20px;width:44px;height:26px;'
            f'background:{a};opacity:.45;border-radius:3px"></div>'
            f'<div style="position:absolute;bottom:18px;left:72px;width:44px;height:26px;'
            f'background:{a};opacity:.30;border-radius:3px"></div>'
            f'<div style="position:absolute;bottom:52px;left:20px;width:96px;height:20px;'
            f'background:rgba(255,255,255,.14)"></div></div>')
    # incubators with round windows
    for x in (25, 58):
        out.append(
            f'<div style="position:absolute;left:{x}%;bottom:236px;width:110px;height:76px;'
            f'background:#3a2440;border:3px solid #8a97ab;border-radius:4px;z-index:4">'
            f'<div style="position:absolute;top:14px;left:20px;width:46px;height:46px;'
            f'border-radius:50%;border:3px solid {a};background:rgba(255,143,209,.14)"></div>'
            f'<div style="position:absolute;top:20px;right:14px;width:8px;height:8px;'
            f'border-radius:50%;background:{a};animation:warn 2.1s ease-in-out infinite"></div>'
            f'<div style="position:absolute;bottom:8px;left:18px;font-family:monospace;font-size:9px;'
            f'color:{a};opacity:.8">37.0 5%CO2</div></div>')
    # media bottles, pink
    for k in range(6):
        out.append(
            f'<div style="position:absolute;left:{4+k*3.4}%;bottom:236px;width:26px;height:44px;'
            f'background:rgba(255,143,209,.35);border:2px solid {a};border-radius:3px 3px 5px 5px;z-index:4">'
            f'<div style="position:absolute;top:-6px;left:7px;width:12px;height:7px;background:#dcd6e4"></div></div>')
    out.append(_label("2%", 320, "TISSUE CULTURE &mdash; PLATE 4 IS CONTAMINATED", a))
    return "".join(out)


def props_em(room: Room, rng: random.Random) -> str:
    a = room.accent
    out = []
    # the column
    out.append(
        f'<div style="position:absolute;left:50%;margin-left:-58px;bottom:40px;width:116px;height:250px;'
        f'background:linear-gradient(180deg,#3a4258,#20263a);border:4px solid #8a97ab;'
        f'border-radius:8px 8px 3px 3px;z-index:5">'
        + "".join(f'<div style="position:absolute;top:{22+j*40}px;left:-12px;right:-12px;height:16px;'
                  f'background:#4a5570;border:2px solid #8a97ab;border-radius:3px"></div>' for j in range(5))
        + f'<div style="position:absolute;bottom:20px;left:50%;margin-left:-22px;width:44px;height:30px;'
          f'background:{a};opacity:.30;border-radius:3px"></div></div>')
    # console + screens
    out.append(f'<div style="position:absolute;left:9%;bottom:40px;width:230px;height:96px;'
               f'background:#2a3040;border:3px solid #6b7a8a;z-index:4"></div>')
    for k in range(2):
        out.append(
            f'<div style="position:absolute;left:{10+k*11}%;bottom:140px;width:150px;height:106px;'
            f'background:#05070d;border:3px solid #6b7a8a;z-index:5;overflow:hidden">'
            f'<div style="position:absolute;top:50%;left:50%;width:70px;height:70px;margin:-35px 0 0 -35px;'
            f'border-radius:50%;background:radial-gradient(circle,{a} 0%,transparent 68%);opacity:.35"></div>'
            f'<div style="position:absolute;top:8px;left:8px;width:60%;height:2px;background:{a};'
            f'animation:trace 2.2s linear infinite"></div></div>')
    # gas cylinders
    for k in range(3):
        out.append(f'<div style="position:absolute;right:{4+k*7}%;bottom:40px;width:44px;height:150px;'
                   f'background:#3f4a5c;border:2px solid #8a97ab;border-radius:22px 22px 3px 3px;z-index:4">'
                   f'<div style="position:absolute;top:8px;left:12px;width:20px;height:12px;'
                   f'background:{a};opacity:.5;border-radius:2px"></div></div>')
    out.append(_label("2%", 262, "ELECTRON MICROSCOPY &mdash; COLUMN UNDER VACUUM", a))
    return "".join(out)


def props_analytic(room: Room, rng: random.Random) -> str:
    a = room.accent
    out = []
    # instrument bays
    for k, x in enumerate((3, 27, 51, 75)):
        out.append(
            f'<div style="position:absolute;left:{x}%;bottom:40px;width:200px;height:160px;'
            f'background:#12252b;border:3px solid #4a6b70;border-radius:4px;z-index:4">'
            f'<div style="position:absolute;top:12px;left:12px;right:12px;height:44px;'
            f'background:#05100f;border:2px solid {a}">'
            + "".join(f'<div style="position:absolute;bottom:4px;left:{6+j*13}px;width:7px;'
                      f'height:{rng.randint(6,34)}px;background:{a};opacity:.75"></div>' for j in range(13))
            + f'</div>'
              f'<div style="position:absolute;bottom:16px;left:14px;width:60px;height:32px;'
              f'background:#2a3f44;border:2px solid #4a6b70"></div>'
              f'<div style="position:absolute;bottom:16px;left:84px;width:36px;height:32px;'
              f'border-radius:50%;border:3px solid {a};opacity:.6"></div>'
              f'<div style="position:absolute;top:66px;right:14px;width:9px;height:9px;border-radius:50%;'
              f'background:{a};animation:warn 1.7s ease-in-out infinite"></div></div>')
    # gas lines along the ceiling
    out.append(f'<div style="position:absolute;left:0;right:0;bottom:214px;height:8px;background:#3f5f66;z-index:3"></div>')
    for k in range(9):
        out.append(f'<div style="position:absolute;left:{5+k*11}%;bottom:200px;width:6px;height:18px;'
                   f'background:#3f5f66;z-index:3"></div>')
    # out of order sign
    out.append(f'<div style="position:absolute;left:52%;bottom:206px;z-index:7;background:rgba(0,0,0,.6);'
               f'border:2px solid {MAGENTA};color:{MAGENTA};font-family:monospace;font-size:11px;'
               f'padding:5px 9px">OUT OF ORDER</div>')
    out.append(_label("2%", 240, "ANALYTICAL SUITE", a))
    return "".join(out)


def props_green(room: Room, rng: random.Random) -> str:
    a = room.accent
    out = []
    # grow racks with plants under lights
    for tier, y in enumerate((40, 132)):
        out.append(f'<div style="position:absolute;left:2%;right:2%;bottom:{y+72}px;height:9px;'
                   f'background:#ff7fd0;opacity:.45;z-index:3;box-shadow:0 6px 30px rgba(255,127,208,.5)"></div>')
        out.append(f'<div style="position:absolute;left:2%;right:2%;bottom:{y-6}px;height:7px;'
                   f'background:#3a4a2a;z-index:3"></div>')
        for k in range(16):
            x = 3 + k * 6.1
            h = rng.randint(26, 56)
            leaves = "".join(
                f'<div style="position:absolute;bottom:{10+j*11}px;left:{-9 if j%2 else 7}px;'
                f'width:19px;height:9px;background:{a};opacity:.75;'
                f'border-radius:{"50% 10%" if j%2 else "10% 50%"};'
                f'animation:sway2 {2.4+j*0.3:.1f}s ease-in-out infinite"></div>' for j in range(h // 14))
            out.append(
                f'<div style="position:absolute;left:{x}%;bottom:{y}px;width:34px;height:{h+16}px;z-index:4">'
                f'<div style="position:absolute;bottom:0;left:4px;width:26px;height:15px;'
                f'background:#6b4a2a;border-radius:2px 2px 4px 4px"></div>'
                f'<div style="position:absolute;bottom:14px;left:15px;width:3px;height:{h}px;'
                f'background:#4f7a2a"></div>{leaves}</div>')
    out.append(_label("2%", 248, "PLANT GROWTH &mdash; 18 HOUR DAYS", a))
    return "".join(out)


PROP_BUILDERS = {
    "viv": props_vivarium, "fly": props_fly, "aqua": props_aquatics,
    "radio": props_radio, "cryo": props_cryo, "bsl4": props_bsl4,
    "xeno": props_xeno, "glass": props_glass, "lobby": props_lobby,
    "tissue": props_tissue, "em": props_em, "mass": props_analytic,
    "green": props_green, "suite3": props_bsl4,
}


def prop_wall(room: Room, seed: int) -> str:
    rng = random.Random(seed)
    # Deliberately no generic "bench kit" here: shared clutter competed with each
    # room's own fixtures and made every lab read the same.
    return PROP_BUILDERS.get(room.key, props_lobby)(room, rng)


EXTRA_KEYFRAMES = """
<style>
 @keyframes needle { from{transform:rotate(-32deg)} to{transform:rotate(34deg)} }
 @keyframes warn { 0%,100%{opacity:.35;box-shadow:0 0 0 rgba(255,61,139,0)}
                   50%{opacity:1;box-shadow:0 0 26px #ff3d8b} }
 @keyframes wave { from{transform:translateX(0)} to{transform:translateX(-40px)} }
 @keyframes gull { from{transform:translateX(0) translateY(0)} to{transform:translateX(120px) translateY(-14px)} }
 @keyframes vine { 0%,100%{transform:rotate(-5deg)} 50%{transform:rotate(5deg)} }
 @keyframes wave2 { from{transform:rotate(-24deg)} to{transform:rotate(26deg)} }
 @keyframes hop { 0%,100%{transform:translateY(0)} 45%{transform:translateY(-9px)} }
 @keyframes flutter { 0%,100%{transform:translate(0,0)} 25%{transform:translate(26px,-20px)}
                      50%{transform:translate(52px,4px)} 75%{transform:translate(20px,18px)} }
 @keyframes flap { from{transform:rotateY(0deg)} to{transform:rotateY(72deg)} }
 @keyframes sway2 { 0%,100%{transform:rotate(-7deg)} 50%{transform:rotate(7deg)} }
</style>
"""


def ocean_window(left: str, top: int, w: int, h: int) -> str:
    """A window onto the sea. The one nice thing about this building."""
    waves = "".join(
        f'<div style="position:absolute;left:-40px;right:-40px;top:{int(h*0.52)+k*7}px;height:3px;'
        f'background:rgba(255,255,255,.35);border-radius:2px;'
        f'animation:wave {2.2+k*0.5:.1f}s linear infinite"></div>' for k in range(5))
    gulls = "".join(
        f'<div style="position:absolute;left:{14+k*30}px;top:{16+k*9}px;width:12px;height:5px;z-index:3;'
        f'border-top:2px solid rgba(255,255,255,.75);border-radius:50%;'
        f'animation:gull {5+k*1.4:.1f}s linear infinite"></div>' for k in range(3))
    return (
        f'<div style="position:absolute;left:{left};top:{top}px;width:{w}px;height:{h}px;z-index:2;'
        f'border:6px solid #4a5580;border-radius:4px;overflow:hidden;'
        f'background:linear-gradient(180deg,#7fd4ff 0%,#bfe9ff 42%,#2b8fc4 42%,#0d5f92 100%);'
        f'box-shadow:inset 0 0 30px rgba(0,0,0,.35)">'
        f'<div style="position:absolute;right:16px;top:12px;width:26px;height:26px;border-radius:50%;'
        f'background:#fff3b0;box-shadow:0 0 24px #fff3b0"></div>'
        f'{gulls}{waves}'
        f'<div style="position:absolute;left:50%;top:{int(h*0.52)-7}px;margin-left:-16px;width:32px;'
        f'height:9px;background:#20364a;border-radius:2px 6px 0 0"></div>'
        f'<div style="position:absolute;left:0;right:0;top:50%;height:4px;background:#4a5580"></div>'
        f'<div style="position:absolute;left:50%;top:0;bottom:0;width:4px;margin-left:-2px;background:#4a5580"></div>'
        f'</div>')


def _sprite_monkey(rng, a: str) -> str:
    """Reads as a monkey: ears, muzzle, two arms, legs, curled tail."""
    top = rng.randint(14, 74)
    dur = rng.uniform(4.5, 8.5)
    d = rng.uniform(0, 4)
    fur, skin = "#8a6240", "#d9b18a"
    return (
        f'<div style="position:absolute;top:{top}px;left:-56px;z-index:8;'
        f'animation:swing {dur:.1f}s linear {d:.1f}s infinite">'
        f'<div style="position:relative;width:34px;height:40px">'
        # raised arm + hand
        f'<div style="position:absolute;top:-11px;left:13px;width:5px;height:16px;background:{fur};'
        f'border-radius:3px;transform:rotate(-16deg)"></div>'
        f'<div style="position:absolute;top:-15px;left:11px;width:9px;height:8px;background:{skin};'
        f'border-radius:50%"></div>'
        # ears
        f'<div style="position:absolute;top:5px;left:1px;width:9px;height:9px;background:{fur};border-radius:50%"></div>'
        f'<div style="position:absolute;top:5px;right:1px;width:9px;height:9px;background:{fur};border-radius:50%"></div>'
        # head + face
        f'<div style="position:absolute;top:2px;left:6px;width:22px;height:19px;background:{fur};'
        f'border-radius:50% 50% 45% 45%"></div>'
        f'<div style="position:absolute;top:7px;left:10px;width:14px;height:11px;background:{skin};'
        f'border-radius:50%"></div>'
        f'<div style="position:absolute;top:9px;left:12px;width:3px;height:3px;background:#2a1d12;border-radius:50%"></div>'
        f'<div style="position:absolute;top:9px;left:19px;width:3px;height:3px;background:#2a1d12;border-radius:50%"></div>'
        f'<div style="position:absolute;top:14px;left:15px;width:5px;height:2px;background:#2a1d12;border-radius:2px"></div>'
        # body + free arm + legs
        f'<div style="position:absolute;top:19px;left:9px;width:16px;height:16px;background:{fur};'
        f'border-radius:8px"></div>'
        f'<div style="position:absolute;top:21px;left:24px;width:12px;height:4px;background:{fur};'
        f'border-radius:3px;transform:rotate(24deg);animation:wave2 .7s ease-in-out infinite alternate"></div>'
        f'<div style="position:absolute;top:33px;left:10px;width:5px;height:9px;background:{fur};border-radius:3px"></div>'
        f'<div style="position:absolute;top:33px;left:19px;width:5px;height:9px;background:{fur};border-radius:3px"></div>'
        # curled tail
        f'<div style="position:absolute;top:24px;left:-9px;width:14px;height:14px;'
        f'border:3px solid {fur};border-radius:50%;border-right-color:transparent;'
        f'border-top-color:transparent"></div>'
        f'</div></div>')


def _sprite_rabbit(rng, a: str) -> str:
    dur = rng.uniform(4.0, 7.0)
    d = rng.uniform(0, 3.5)
    fur = rng.choice(["#e8e2d6", "#cbbba6", "#8d8378"])
    return (
        f'<div style="position:absolute;bottom:{rng.randint(4,20)}px;left:-40px;z-index:7;'
        f'animation:scurry {dur:.1f}s linear {d:.1f}s infinite">'
        f'<div style="position:relative;width:30px;height:22px;animation:hop .5s ease-in-out infinite">'
        f'<div style="position:absolute;bottom:0;left:0;width:22px;height:13px;background:{fur};'
        f'border-radius:50% 45% 40% 50%"></div>'
        f'<div style="position:absolute;bottom:7px;left:16px;width:11px;height:10px;background:{fur};'
        f'border-radius:50%"></div>'
        f'<div style="position:absolute;bottom:14px;left:17px;width:4px;height:11px;background:{fur};'
        f'border-radius:2px;transform:rotate(-11deg)"></div>'
        f'<div style="position:absolute;bottom:14px;left:22px;width:4px;height:11px;background:{fur};'
        f'border-radius:2px;transform:rotate(11deg)"></div>'
        f'<div style="position:absolute;bottom:9px;left:2px;width:6px;height:6px;background:#fff;'
        f'border-radius:50%;opacity:.85"></div></div></div>')


def _sprite_rodent(rng, a: str, big: bool) -> str:
    dur = rng.uniform(2.6, 5.4)
    d = rng.uniform(0, 3.5)
    fur = "#b9ada0" if big else "#e6dfd4"
    w, h = (20, 9) if big else (14, 7)
    return (
        f'<div style="position:absolute;bottom:{rng.randint(3,18)}px;left:-34px;z-index:7;'
        f'animation:scurry {dur:.1f}s linear {d:.1f}s infinite">'
        f'<div style="position:relative;width:{w+14}px;height:{h+6}px">'
        f'<div style="position:absolute;bottom:0;left:8px;width:{w}px;height:{h}px;background:{fur};'
        f'border-radius:50% 40% 40% 50%"></div>'
        f'<div style="position:absolute;bottom:{h-2}px;left:{w-1}px;width:6px;height:6px;background:{fur};'
        f'border-radius:50%"></div>'
        f'<div style="position:absolute;bottom:2px;left:0;width:10px;height:2px;background:{fur};'
        f'border-radius:2px;transform:rotate(-12deg)"></div>'
        f'<div style="position:absolute;bottom:{h-3}px;left:{w+3}px;width:2px;height:2px;'
        f'background:#2a1d12;border-radius:50%"></div></div></div>')


def _sprite_butterfly(rng, a: str) -> str:
    dur = rng.uniform(3.2, 6.0)
    d = rng.uniform(0, 3)
    col = rng.choice([a, "#ffd166", "#ff8fd1", "#fff3b0"])
    return (
        f'<div style="position:absolute;top:{rng.randint(16,110)}px;left:{rng.randint(3,90)}%;z-index:7;'
        f'animation:flutter {dur:.1f}s ease-in-out {d:.1f}s infinite">'
        f'<div style="position:relative;width:18px;height:12px">'
        f'<div style="position:absolute;left:0;top:0;width:8px;height:11px;background:{col};opacity:.85;'
        f'border-radius:60% 20% 60% 20%;transform-origin:right center;animation:flap .22s ease-in-out infinite alternate"></div>'
        f'<div style="position:absolute;right:0;top:0;width:8px;height:11px;background:{col};opacity:.85;'
        f'border-radius:20% 60% 20% 60%;transform-origin:left center;animation:flap .22s ease-in-out infinite alternate-reverse"></div>'
        f'<div style="position:absolute;left:8px;top:2px;width:2px;height:8px;background:#2a1d12"></div>'
        f'</div></div>')


def critters(room: Room, seed: int, n: int = 7) -> str:
    """Small animated inhabitants. Species and placement randomise per run."""
    rng = random.Random(seed)
    species = [k.strip() for k in room.critter.split(",") if k.strip()]
    a = room.accent
    out = []
    for i in range(n):
        k = rng.choice(species)
        d = rng.uniform(0, 4.2)
        dur = rng.uniform(3.0, 7.5)
        if k == "monkey":
            out.append(_sprite_monkey(rng, a))
        elif k == "rabbit":
            out.append(_sprite_rabbit(rng, a))
        elif k == "mouse":
            out.append(_sprite_rodent(rng, a, big=False))
        elif k == "rat":
            out.append(_sprite_rodent(rng, a, big=True))
        elif k == "butterfly":
            out.append(_sprite_butterfly(rng, a))
        elif k == "aphid":
            out.append(
                f'<div style="position:absolute;bottom:{rng.randint(40,120)}px;left:{rng.randint(4,92)}%;'
                f'width:6px;height:5px;border-radius:50%;background:#9bd44f;opacity:.8;z-index:7;'
                f'animation:buzz {rng.uniform(1.4,3.0):.1f}s ease-in-out {d:.1f}s infinite"></div>')
        elif k == "spore":
            out.append(
                f'<div style="position:absolute;top:{rng.randint(20,120)}px;left:{rng.randint(4,94)}%;'
                f'width:{rng.randint(6,13)}px;height:{rng.randint(6,13)}px;border-radius:50%;'
                f'background:{a};opacity:.30;z-index:7;'
                f'animation:float {dur:.1f}s ease-in-out {d:.1f}s infinite"></div>')
        elif k == "fish":
            out.append(
                f'<div style="position:absolute;top:{rng.randint(40,120)}px;left:-30px;z-index:7;'
                f'animation:swim {dur:.1f}s linear {d:.1f}s infinite;opacity:.88">'
                f'<div style="position:relative;width:24px;height:11px">'
                f'<div style="position:absolute;left:6px;top:2px;width:16px;height:7px;background:{a};'
                f'border-radius:50% 25% 25% 50%"></div>'
                f'<div style="position:absolute;left:0;top:1px;width:0;height:0;'
                f'border-top:5px solid transparent;border-bottom:5px solid transparent;'
                f'border-right:8px solid {a}"></div>'
                f'<div style="position:absolute;left:17px;top:3px;width:2px;height:2px;'
                f'background:#04202c;border-radius:50%"></div></div></div>')
        elif k == "virus":
            sz = rng.randint(11, 19)
            spikes = "".join(
                f'<div style="position:absolute;left:50%;top:50%;width:2px;height:{sz//2+4}px;'
                f'background:{a};transform-origin:top center;transform:rotate({j*45}deg)"></div>'
                for j in range(8))
            out.append(
                f'<div style="position:absolute;top:{rng.randint(20,110)}px;left:{rng.randint(4,92)}%;z-index:7;'
                f'animation:float {dur:.1f}s ease-in-out {d:.1f}s infinite;opacity:.8">'
                f'<div style="position:relative;width:{sz}px;height:{sz}px;border-radius:50%;'
                f'background:{a};opacity:.55">{spikes}</div></div>')
        elif k == "alien":
            out.append(
                f'<div style="position:absolute;bottom:{rng.randint(38,80)}px;left:{rng.randint(6,88)}%;z-index:7;'
                f'animation:writhe {dur:.1f}s ease-in-out {d:.1f}s infinite">'
                f'<div style="width:5px;height:{rng.randint(20,40)}px;background:{a};opacity:.6;'
                f'border-radius:3px;transform-origin:bottom center"></div></div>')
        elif k == "flake":
            out.append(
                f'<div style="position:absolute;top:-12px;left:{rng.randint(2,96)}%;width:4px;height:4px;'
                f'border-radius:50%;background:{a};opacity:.75;z-index:7;'
                f'animation:fall {dur:.1f}s linear {d:.1f}s infinite"></div>')
        elif k == "fly":
            out.append(
                f'<div style="position:absolute;top:{rng.randint(24,120)}px;left:{rng.randint(4,92)}%;'
                f'width:5px;height:4px;border-radius:50%;background:#2b2416;z-index:7;'
                f'animation:buzz {rng.uniform(.7,1.6):.1f}s ease-in-out {d:.1f}s infinite"></div>')
        elif k == "bubble":
            out.append(
                f'<div style="position:absolute;bottom:34px;left:{rng.randint(3,95)}%;'
                f'width:{rng.randint(5,12)}px;height:{rng.randint(5,12)}px;border-radius:50%;'
                f'border:1px solid {a};opacity:.6;z-index:7;'
                f'animation:rise {dur:.1f}s linear {d:.1f}s infinite"></div>')
        else:
            out.append(
                f'<div style="position:absolute;bottom:{rng.randint(3,16)}px;left:-24px;width:9px;height:5px;'
                f'border-radius:50%;background:#3a2a18;z-index:7;'
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


# ==========================================================================
# PLAYFIELD BACKGROUND — a real room behind the rotor while you play
# ==========================================================================
def room_svg_background(room: Room, w: int = 1600, h: int = 900) -> str:
    """Flat SVG of the room, used as the page background during play."""
    rng = random.Random(len(room.key) * 7 + 3)
    a, wt, wb = room.accent, room.wall_top, room.wall_bot
    fa, fb = room.floor_a, room.floor_b
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
         f'<defs><linearGradient id="w" x1="0" y1="0" x2="0" y2="1">'
         f'<stop offset="0" stop-color="{wt}"/><stop offset="1" stop-color="{wb}"/></linearGradient></defs>',
         f'<rect width="{w}" height="{h}" fill="url(#w)"/>']
    # ceiling strip lights
    for x in (110, 620, 1130):
        p.append(f'<rect x="{x}" y="26" width="380" height="12" fill="{a}" opacity="0.30"/>')
    floor_y = h - 210
    p.append(f'<rect y="{floor_y}" width="{w}" height="210" fill="{fa}"/>')
    for x in range(0, w, 150):
        p.append(f'<rect x="{x}" y="{floor_y}" width="75" height="210" fill="{fb}"/>')
    p.append(f'<rect y="{floor_y}" width="{w}" height="4" fill="{a}" opacity="0.35"/>')

    k = room.key
    if k == "viv":
        for cx in (70, 330, 1180, 1420):
            for tier in range(3):
                y = floor_y - 90 - tier * 96
                p.append(f'<rect x="{cx}" y="{y}" width="230" height="86" fill="none" '
                         f'stroke="#8d9a7a" stroke-width="5"/>')
                for j in range(9):
                    p.append(f'<line x1="{cx+16+j*24}" y1="{y}" x2="{cx+16+j*24}" y2="{y+86}" '
                             f'stroke="#8d9a7a" stroke-width="3" opacity="0.8"/>')
                for mnum in range(rng.randint(1, 3)):
                    mx = cx + 30 + mnum * 70
                    p.append(f'<ellipse cx="{mx}" cy="{y+70}" rx="15" ry="8" fill="#e6dfd4" opacity="0.9"/>')
        p.append(f'<rect x="640" y="{floor_y-300}" width="330" height="300" fill="none" '
                 f'stroke="#8d9a7a" stroke-width="7"/>')
        for j in range(11):
            p.append(f'<line x1="{656+j*30}" y1="{floor_y-300}" x2="{656+j*30}" y2="{floor_y}" '
                     f'stroke="#8d9a7a" stroke-width="4" opacity="0.75"/>')
        p.append(f'<line x1="660" y1="{floor_y-250}" x2="950" y2="{floor_y-250}" '
                 f'stroke="#7a5c3a" stroke-width="7"/>')
    elif k == "fly":
        for tier in range(4):
            y = floor_y - 70 - tier * 96
            p.append(f'<rect y="{y+64}" width="{w}" height="10" fill="#5a4a2a"/>')
            for j in range(28):
                x = 20 + j * 56
                p.append(f'<rect x="{x}" y="{y}" width="34" height="64" fill="{a}" opacity="0.16" '
                         f'stroke="{a}" stroke-width="2"/>')
                p.append(f'<rect x="{x}" y="{y+46}" width="34" height="18" fill="#8a5a1a" opacity="0.85"/>')
    elif k == "aqua":
        for tier in range(3):
            y = floor_y - 96 - tier * 110
            for j in range(7):
                x = 20 + j * 228
                p.append(f'<rect x="{x}" y="{y}" width="210" height="96" fill="{a}" opacity="0.20" '
                         f'stroke="{a}" stroke-width="4"/>')
                for f in range(rng.randint(2, 5)):
                    p.append(f'<ellipse cx="{x+30+f*40}" cy="{y+26+f*13}" rx="13" ry="5" '
                             f'fill="{a}" opacity="0.75"/>')
        p.append(f'<rect y="{floor_y-330}" width="{w}" height="12" fill="#4a6b78"/>')
    elif k == "radio":
        for row in range(6):
            for j in range(14):
                x = j * 120 + (60 if row % 2 else 0)
                p.append(f'<rect x="{x}" y="{floor_y-40-row*44}" width="112" height="38" '
                         f'fill="#4a4a52" stroke="#62626e" stroke-width="2"/>')
        for j in range(5):
            x = 1000 + j * 120
            p.append(f'<rect x="{x}" y="{floor_y-150}" width="86" height="150" fill="#54520e" '
                     f'stroke="{a}" stroke-width="5" rx="6"/>')
            p.append(f'<circle cx="{x+43}" cy="{floor_y-90}" r="30" fill="none" stroke="{a}" stroke-width="7"/>')
        p.append(f'<rect y="{floor_y-330}" width="{w}" height="26" fill="{a}" opacity="0.5"/>')
    elif k == "cryo":
        for j in range(8):
            x = 40 + j * 195
            p.append(f'<rect x="{x}" y="{floor_y-170}" width="150" height="170" fill="#dfeef7" '
                     f'opacity="0.22" stroke="{a}" stroke-width="4" rx="14"/>')
            p.append(f'<ellipse cx="{x+75}" cy="{floor_y-180}" rx="86" ry="26" fill="#fff" opacity="0.16"/>')
        p.append(f'<rect y="{floor_y-300}" width="{w}" height="10" fill="#8fb8cc" opacity="0.5"/>')
        for _ in range(60):
            p.append(f'<circle cx="{rng.randint(0,w)}" cy="{rng.randint(0,h)}" r="{rng.randint(2,5)}" '
                     f'fill="#fff" opacity="0.16"/>')
    elif k in ("bsl4", "suite3"):
        p.append(f'<rect x="{w//2-190}" y="{floor_y-330}" width="380" height="330" fill="none" '
                 f'stroke="{a}" stroke-width="9" rx="14"/>')
        p.append(f'<circle cx="{w//2}" cy="{floor_y-200}" r="86" fill="{a}" opacity="0.12" '
                 f'stroke="{a}" stroke-width="7"/>')
        for x in (110, 260, 1220, 1380):
            p.append(f'<rect x="{x}" y="{floor_y-230}" width="96" height="230" fill="#e8e6f0" '
                     f'opacity="0.16" rx="46"/>')
            p.append(f'<circle cx="{x+48}" cy="{floor_y-190}" r="26" fill="{a}" opacity="0.30"/>')
        for x in (520, 1000):
            p.append(f'<rect x="{x}" y="{floor_y-400}" width="90" height="90" fill="none" '
                     f'stroke="{a}" stroke-width="5"/>')
            for j in range(3):
                ang = j * 120
                p.append(f'<circle cx="{x+45}" cy="{floor_y-355}" r="17" fill="none" stroke="{a}" '
                         f'stroke-width="7" transform="rotate({ang} {x+45} {floor_y-355})" '
                         f'stroke-dasharray="18 90"/>')
    elif k == "xeno":
        p.append(f'<rect x="{w//2-130}" y="{floor_y-360}" width="260" height="360" rx="130" '
                 f'fill="{a}" opacity="0.16" stroke="{a}" stroke-width="7"/>')
        for j in range(4):
            p.append(f'<rect x="{w//2-90+j*46}" y="{floor_y-140}" width="14" height="140" '
                     f'fill="{a}" opacity="0.45" rx="7"/>')
        for j in range(9):
            x = 60 + j * 160
            if abs(x - w // 2) < 200:
                continue
            p.append(f'<rect x="{x}" y="{floor_y-120}" width="86" height="120" fill="{a}" opacity="0.12" '
                     f'stroke="{a}" stroke-width="3" rx="6"/>')
            p.append(f'<circle cx="{x+43}" cy="{floor_y-56}" r="{rng.randint(12,24)}" fill="{a}" opacity="0.45"/>')
    elif k == "glass":
        for j in range(4):
            x = 40 + j * 250
            p.append(f'<rect x="{x}" y="{floor_y-120}" width="210" height="120" fill="#39405f" '
                     f'stroke="#6b7a8a" stroke-width="5" rx="5"/>')
            p.append(f'<rect x="{x+95}" y="{floor_y-200}" width="12" height="80" fill="#8a97ab"/>')
        for tier in range(3):
            y = floor_y - 150 - tier * 96
            p.append(f'<rect x="1080" y="{y+70}" width="470" height="8" fill="#6b7a8a"/>')
            for j in range(8):
                p.append(f'<rect x="{1096+j*56}" y="{y+26}" width="36" height="46" fill="#9fb8d8" '
                         f'opacity="0.28" stroke="#9fb8d8" stroke-width="2"/>')
    elif k == "tissue":
        for x in (60, 560, 1060):
            p.append(f'<rect x="{x}" y="{floor_y-300}" width="420" height="300" fill="#fff" '
                     f'opacity="0.06" stroke="#8a97ab" stroke-width="6"/>')
            p.append(f'<rect x="{x+20}" y="{floor_y-280}" width="380" height="120" fill="{a}" opacity="0.16"/>')
            p.append(f'<rect x="{x+30}" y="{floor_y-130}" width="120" height="70" fill="{a}" opacity="0.30" rx="5"/>')
            p.append(f'<rect x="{x+170}" y="{floor_y-130}" width="120" height="70" fill="{a}" opacity="0.20" rx="5"/>')
    elif k == "em":
        p.append(f'<rect x="{w//2-90}" y="{floor_y-430}" width="180" height="430" fill="#2a3140" '
                 f'stroke="#8a97ab" stroke-width="7" rx="10"/>')
        for j in range(6):
            p.append(f'<rect x="{w//2-120}" y="{floor_y-400+j*66}" width="240" height="26" '
                     f'fill="#4a5570" stroke="#8a97ab" stroke-width="4" rx="4"/>')
        for x in (150, 1180):
            p.append(f'<rect x="{x}" y="{floor_y-250}" width="270" height="180" fill="#05070d" '
                     f'stroke="#6b7a8a" stroke-width="6"/>')
            p.append(f'<circle cx="{x+135}" cy="{floor_y-160}" r="58" fill="{a}" opacity="0.22"/>')
        for j in range(3):
            p.append(f'<rect x="{1420+j*58}" y="{floor_y-240}" width="46" height="240" fill="#3f4a5c" '
                     f'stroke="#8a97ab" stroke-width="3" rx="23"/>')
    elif k == "mass":
        for j in range(4):
            x = 40 + j * 400
            p.append(f'<rect x="{x}" y="{floor_y-260}" width="330" height="260" fill="#12252b" '
                     f'stroke="#4a6b70" stroke-width="6" rx="6"/>')
            p.append(f'<rect x="{x+22}" y="{floor_y-238}" width="286" height="86" fill="#05100f" '
                     f'stroke="{a}" stroke-width="4"/>')
            for b in range(16):
                p.append(f'<rect x="{x+34+b*17}" y="{floor_y-170+rng.randint(-46,0)}" width="10" '
                         f'height="{rng.randint(10,54)}" fill="{a}" opacity="0.7"/>')
            p.append(f'<circle cx="{x+250}" cy="{floor_y-64}" r="30" fill="none" stroke="{a}" stroke-width="6"/>')
        p.append(f'<rect y="{floor_y-330}" width="{w}" height="12" fill="#3f5f66"/>')
    elif k == "green":
        for tier in range(3):
            y = floor_y - 110 - tier * 150
            p.append(f'<rect y="{y+96}" width="{w}" height="12" fill="#3a4a2a"/>')
            p.append(f'<rect y="{y-16}" width="{w}" height="12" fill="#ff7fd0" opacity="0.45"/>')
            for j in range(24):
                x = 20 + j * 68
                hgt = rng.randint(40, 84)
                p.append(f'<rect x="{x}" y="{y+70}" width="40" height="26" fill="#6b4a2a" rx="3"/>')
                p.append(f'<rect x="{x+18}" y="{y+96-hgt}" width="5" height="{hgt-26}" fill="#4f7a2a"/>')
                for lf in range(hgt // 22):
                    off = -22 if lf % 2 else 5
                    p.append(f'<ellipse cx="{x+20+off}" cy="{y+80-lf*20}" rx="20" ry="8" '
                             f'fill="{a}" opacity="0.65"/>')
    else:
        p.append(f'<rect y="{floor_y-120}" width="{w}" height="14" fill="#2b3358"/>')
        for j in range(16):
            x = 30 + j * 100
            p.append(f'<rect x="{x}" y="{floor_y-190}" width="44" height="70" fill="{a}" opacity="0.20" '
                     f'stroke="{a}" stroke-width="2" rx="4"/>')
        p.append(f'<rect x="120" y="{floor_y-380}" width="330" height="170" fill="#e8ecf5" opacity="0.10" '
                 f'stroke="#6b7a8a" stroke-width="4"/>')
    p.append("</svg>")
    return "".join(p)


@st.cache_data(show_spinner=False)
def room_background_css(room_key: str) -> str:
    room = next((r for r in ALL_ROOMS if r.key == room_key), LOBBY)
    svg = room_svg_background(room)
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"""
<style>
.stApp {{
  background-image:
    linear-gradient(180deg, rgba(6,7,13,0.72) 0%, rgba(6,7,13,0.84) 55%, rgba(6,7,13,0.93) 100%),
    url("data:image/svg+xml;base64,{b64}");
  background-size: cover;
  background-position: center 20%;
  background-attachment: fixed;
  background-repeat: no-repeat;
}}
</style>
"""


# ==========================================================================
# TITLE + TRANSIT
# ==========================================================================
def scene_attract(seed: int) -> str:
    r = LOBBY
    rng = random.Random(seed)
    bench = "".join([
        beaker("3%", 74, "#5be36a"), beaker("6%", 74, "#3ff2e0", 13, 16),
        flask("9%", 74, "#ff3d8b"), microscope("13%", 74, "#ffb627"),
        rack("18%", 74, "#3ff2e0", 6), bunsen("25%", 74),
        beaker("29%", 74, "#ffb627", 18, 23), flask("33%", 74, "#8fd14f"),
        monitor("37%", 74, "#5be36a"), rack("44%", 74, "#ff3d8b", 5),
        beaker("51%", 74, "#c86bff", 15, 19), microscope("55%", 74, "#3ff2e0"),
        flask("60%", 74, "#ffb627"), bunsen("65%", 74),
        rack("69%", 74, "#8fd14f", 6), beaker("76%", 74, "#57b6ff", 17, 21),
        monitor("80%", 74, "#3ff2e0"), flask("86%", 74, "#5be36a"),
        beaker("90%", 74, "#ff3d8b", 16, 20), microscope("94%", 74, "#8fd14f"),
    ])
    fuges = "".join(
        f'<div style="position:absolute;left:{x}%;bottom:36px;z-index:5">'
        f'{fuge_sprite(z, "active" if i == 2 else "todo", False, i, 96)}</div>'
        for i, (x, z) in enumerate([(2, TEACHING), (16, CORE), (31, TEACHING),
                                    (60, COLD), (75, PREP), (89, CORE)]))
    # monkeys hanging from the rope by one hand, free arm waving
    rope = ('<div style="position:absolute;left:0;right:0;top:104px;height:5px;background:#7a5c3a;'
            'z-index:6;box-shadow:0 2px 0 #5a4228"></div>')
    fur, skin = "#8a6240", "#d9b18a"
    monkeys = "".join(
        f'<div style="position:absolute;left:{6+k*7}%;top:104px;z-index:7;transform-origin:top center;'
        f'animation:vine {2.6+k*0.5:.1f}s ease-in-out {k*0.35:.1f}s infinite">'
        f'<div style="position:relative;width:38px;height:78px">'
        # gripping hand ON the rope, then the arm hanging down from it
        f'<div style="position:absolute;top:-7px;left:12px;width:13px;height:11px;background:{skin};'
        f'border-radius:50% 50% 40% 40%;border:2px solid {fur}"></div>'
        f'<div style="position:absolute;top:3px;left:15px;width:6px;height:22px;background:{fur};'
        f'border-radius:3px"></div>'
        # head below the arm
        f'<div style="position:absolute;top:23px;left:3px;width:10px;height:10px;background:{fur};border-radius:50%"></div>'
        f'<div style="position:absolute;top:23px;right:3px;width:10px;height:10px;background:{fur};border-radius:50%"></div>'
        f'<div style="position:absolute;top:21px;left:8px;width:24px;height:21px;background:{fur};'
        f'border-radius:50% 50% 45% 45%"></div>'
        f'<div style="position:absolute;top:27px;left:12px;width:16px;height:12px;background:{skin};'
        f'border-radius:50%"></div>'
        f'<div style="position:absolute;top:29px;left:14px;width:3px;height:3px;background:#2a1d12;border-radius:50%"></div>'
        f'<div style="position:absolute;top:29px;left:22px;width:3px;height:3px;background:#2a1d12;border-radius:50%"></div>'
        f'<div style="position:absolute;top:35px;left:17px;width:6px;height:2px;background:#2a1d12;border-radius:2px"></div>'
        # torso, waving free arm, dangling legs, curled tail
        f'<div style="position:absolute;top:41px;left:11px;width:18px;height:19px;background:{fur};border-radius:9px"></div>'
        f'<div style="position:absolute;top:44px;left:27px;width:14px;height:5px;background:{fur};'
        f'border-radius:3px;transform-origin:left center;animation:wave2 .55s ease-in-out infinite alternate"></div>'
        f'<div style="position:absolute;top:58px;left:12px;width:6px;height:13px;background:{fur};border-radius:3px"></div>'
        f'<div style="position:absolute;top:58px;left:22px;width:6px;height:13px;background:{fur};border-radius:3px"></div>'
        f'<div style="position:absolute;top:48px;left:-8px;width:16px;height:16px;border:3px solid {fur};'
        f'border-radius:50%;border-right-color:transparent;border-top-color:transparent"></div>'
        f'</div></div>' for k in range(4))
    roaches = critters(LOBBY, seed + 2, 3)
    inner = f"""
    {CRITTER_KEYFRAMES}{EXTRA_KEYFRAMES}
    <style>
      @keyframes glowpulse {{ 0%,100%{{text-shadow:0 0 12px #ffb627,0 0 34px rgba(255,182,39,.5)}}
                              50%{{text-shadow:0 0 24px #ffb627,0 0 62px rgba(255,182,39,.9)}} }}
      @keyframes blink {{ 0%,49%{{opacity:1}} 50%,100%{{opacity:0}} }}
      @keyframes idle {{ 50%{{transform:translateY(-4px)}} }}
      .logo {{ position:absolute; top:158px; left:0; right:0; text-align:center; z-index:15;
               font-family:'Press Start 2P',monospace; color:#ffb627; animation:glowpulse 2.6s ease-in-out infinite; }}
      .logo .l1 {{ font-size:40px; display:block; letter-spacing:3px; }}
      .logo .l2 {{ font-size:40px; display:block; letter-spacing:3px; margin-top:13px; color:#3ff2e0;
                   text-shadow:0 0 14px #3ff2e0,0 0 36px rgba(63,242,224,.55); }}
      .tag {{ position:absolute; top:262px; left:0; right:0; text-align:center; z-index:15;
              font-family:'IBM Plex Mono',monospace; font-size:14px; color:#8fa0d8; letter-spacing:.46em; }}
      .ins {{ position:absolute; bottom:112px; left:0; right:0; text-align:center; z-index:15;
              font-family:'Press Start 2P',monospace; font-size:11px; color:#5be36a;
              animation:blink 1.1s steps(1) infinite; }}
      .by {{ position:absolute; bottom:8px; right:12px; z-index:22; font-family:'Press Start 2P',monospace;
             font-size:9px; color:#5a6486; letter-spacing:.14em; }}
      .by b {{ color:#ffb627; }}
      .sci {{ position:absolute; bottom:44px; left:47%; width:36px; z-index:8; animation:idle 2.3s ease-in-out infinite; }}
      .board {{ display:none; }}
    </style>
    <div class="lamp" style="left:3%;width:28%"></div>
    <div class="lamp" style="left:36%;width:28%"></div>
    <div class="lamp" style="left:69%;width:28%"></div>
    {ocean_window("4%", 150, 250, 168)}
    {ocean_window("76%", 150, 250, 168)}
    <div class="shelf" style="top:250px;left:2%;width:26%"></div>
    <div class="shelf" style="top:250px;left:76%;width:22%"></div>
    <div style="position:absolute;left:2%;right:2%;bottom:66px;height:9px;background:#2b3358;
                border-top:2px solid #4a5580;z-index:3"></div>
    {bench}{fuges}{rope}{monkeys}{roaches}
    <div class="sci"><div class="head"><div class="goggles"></div></div><div class="coat"></div><div class="legs"></div></div>
    <div class="logo"><span class="l1">CENTRIFUGE</span><span class="l2">CHESS</span></div>
    <div class="tag">BALANCE OR BURN</div>
    <div class="ins">&#9654; INSERT SAMPLE TO START</div>
    <div class="by">MADE BY <b>DYLAN</b></div>
    """
    return scene_shell(470, r, inner)


def scene_transit(room: Room, zone: Zone, level_idx: int, seed: int,
                  label: str = "") -> str:
    """Scientist crosses a themed room, stops to look at something, moves on.
    A blurred doorframe and bench edge sit in front for depth."""
    a = room.accent
    fg = (
        # blurred doorframe, near camera, left
        f'<div style="position:absolute;left:-2%;top:-10px;bottom:-10px;width:74px;z-index:14;'
        f'background:linear-gradient(90deg,#05070c 55%,rgba(5,7,12,.25));filter:blur(2.5px)"></div>'
        f'<div style="position:absolute;left:8%;top:-10px;bottom:-10px;width:16px;z-index:14;'
        f'background:rgba(5,7,12,.72);filter:blur(3px)"></div>'
        # blurred bench edge across the very front
        f'<div style="position:absolute;left:0;right:0;bottom:-6px;height:30px;z-index:15;'
        f'background:linear-gradient(180deg,rgba(8,11,20,.20),rgba(8,11,20,.92));filter:blur(2px)"></div>'
        # a foreground stool, off to the right
        f'<div style="position:absolute;right:9%;bottom:2px;width:56px;height:66px;z-index:14;'
        f'filter:blur(2px);opacity:.9">'
        f'<div style="position:absolute;bottom:44px;left:0;width:56px;height:12px;'
        f'background:#1b2233;border-radius:6px"></div>'
        f'<div style="position:absolute;bottom:0;left:24px;width:8px;height:46px;background:#1b2233"></div>'
        f'<div style="position:absolute;bottom:0;left:6px;width:44px;height:7px;'
        f'background:#1b2233;border-radius:4px"></div></div>')
    inner = f"""
    {CRITTER_KEYFRAMES}{EXTRA_KEYFRAMES}
    <style>
      /* walk in, stop and look, then continue to the machine */
      @keyframes cross {{ 0%{{left:-7%}} 22%{{left:20%}} 38%{{left:38%}}
                          40%,62%{{left:41%}} 82%{{left:64%}} 100%{{left:74%}} }}
      @keyframes steps {{ 0%,38%{{transform:translateY(0)}} 39%,62%{{transform:translateY(0)}} }}
      @keyframes lookpause {{ 0%,38%{{opacity:0;transform:scale(.6)}} 44%,58%{{opacity:1;transform:scale(1)}}
                              64%,100%{{opacity:0;transform:scale(.6)}} }}
      @keyframes arrive {{ 0%,62%{{opacity:0;transform:translateX(44px)}}
                           100%{{opacity:1;transform:translateX(0)}} }}
      @keyframes cardin {{ 0%{{opacity:0;transform:translateY(-18px)}} 12%{{opacity:1;transform:translateY(0)}}
                           74%{{opacity:1}} 100%{{opacity:0}} }}
      @keyframes fadein {{ to{{opacity:1}} }}
      .sci {{ position:absolute; bottom:40px; width:36px; z-index:11;
              animation:cross 5.4s cubic-bezier(.35,0,.5,1) forwards, bob .24s steps(2) infinite; }}
      .think {{ position:absolute; bottom:96px; left:41%; margin-left:14px; z-index:13;
                background:rgba(0,0,0,.6); border:2px solid {a}; border-radius:9px; padding:5px 8px;
                font-family:'Press Start 2P',monospace; font-size:9px; color:{a};
                animation:lookpause 5.4s ease-in-out forwards; }}
      .target {{ position:absolute; right:4%; bottom:36px; z-index:10; animation:arrive 5.4s ease-out forwards; }}
      .cap3 {{ opacity:0; animation:fadein .5s ease-out 4.1s forwards; }}
      .card {{ position:absolute; top:38%; left:0; right:0; text-align:center; z-index:18;
               animation:cardin 3.2s ease-out forwards; }}
      .card b {{ font-family:'Press Start 2P',monospace; font-size:22px; color:{a};
                 text-shadow:0 0 24px {a}; display:block; }}
      .card i {{ font-family:'IBM Plex Mono',monospace; font-style:normal; font-size:12px;
                 color:#c9d2e8; letter-spacing:.28em; display:block; margin-top:12px; }}
      .dim {{ position:absolute; inset:0; z-index:17; background:rgba(0,0,0,.45);
              animation:cardin 3.2s ease-out forwards; }}
    </style>
    {prop_wall(room, seed)}
    <div class="lamp" style="left:4%;width:44%"></div>
    <div class="lamp" style="left:52%;width:44%"></div>
    {critters(room, seed, 11)}
    <div class="sci"><div class="head"><div class="goggles"></div></div><div class="coat"></div><div class="legs"></div></div>
    <div class="think">?</div>
    <div class="target">{fuge_sprite(zone, "active", True, level_idx, 130)}</div>
    {fg}
    <div class="dim"></div>
    <div class="card"><b>{room.name}</b><i>{room.sign}</i></div>
    <div class="caption cap3">{label or f"LEVEL {level_idx+1}"} &mdash; {zone.name} &mdash; {room.name}</div>
    """
    return scene_shell(340, room, inner)

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
      @keyframes panic {{ 0%,100%{{transform:translate(0,0)}} 50%{{transform:translate(-4px,3px)}} }}
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
    <div style="animation:panic .18s steps(2) infinite">{critters(room, 21, 9)}</div>
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


def scene_department(seed: int, arriving: bool = False) -> str:
    """The Department -- AAV vector core, end of shift, morale event under way."""
    rng = random.Random(seed)
    a, viol = "#c86bff", "#c86bff"
    BENCH_TOP = 132        # distance from stage bottom to the bench surface
    out = []

    # ---------- back wall: reagent shelves ----------
    for sy in (34, 74):
        out.append(f'<div style="position:absolute;left:3%;right:3%;top:{sy}px;height:6px;'
                   f'background:#4a5580;border-top:2px solid #6b7a8a;z-index:2"></div>')
        for k in range(26):
            h = rng.randint(14, 26)
            col = rng.choice([a, "#3ff2e0", "#5be36a", "#ffb627", "#ff3d8b", "#9fb8d8"])
            out.append(f'<div style="position:absolute;left:{4+k*3.6}%;top:{sy-h}px;width:13px;'
                       f'height:{h}px;background:{col};opacity:.55;border-radius:2px 2px 1px 1px;'
                       f'z-index:2"></div>')

    # ---------- fume hood, left ----------
    out.append(
        f'<div style="position:absolute;left:2%;bottom:{BENCH_TOP}px;width:230px;height:150px;'
        f'background:rgba(255,255,255,.07);border:4px solid #8a97ab;z-index:4">'
        f'<div style="position:absolute;top:8px;left:8px;right:8px;height:58px;'
        f'background:rgba(200,107,255,.20);border:2px solid {a}"></div>'
        f'<div style="position:absolute;top:70px;left:8px;right:8px;height:5px;background:#8a97ab"></div>'
        f'<div style="position:absolute;bottom:10px;left:16px;width:40px;height:34px;'
        f'background:{a};opacity:.4;border-radius:3px"></div>'
        f'<div style="position:absolute;bottom:10px;left:64px;width:40px;height:34px;'
        f'background:{a};opacity:.25;border-radius:3px"></div>'
        f'<div style="position:absolute;bottom:12px;right:16px;font-family:monospace;font-size:8px;'
        f'color:{a};opacity:.8">HOOD 1</div></div>')

    # ---------- the bench itself, with cabinets underneath ----------
    out.append(f'<div style="position:absolute;left:0;right:0;bottom:{BENCH_TOP-14}px;height:14px;'
               f'background:#3a4258;border-top:3px solid #6b7a8a;z-index:5"></div>')
    for k in range(9):
        out.append(
            f'<div style="position:absolute;left:{2+k*11}%;bottom:34px;width:10%;height:{BENCH_TOP-48}px;'
            f'background:#252b3d;border:2px solid #39405f;z-index:3">'
            f'<div style="position:absolute;top:10px;left:12%;right:12%;height:3px;background:#4a5580"></div>'
            f'<div style="position:absolute;top:44px;left:12%;right:12%;height:3px;background:#4a5580"></div>'
            f'<div style="position:absolute;top:22px;left:44%;width:14px;height:4px;'
            f'background:#8a97ab;border-radius:2px"></div></div>')

    # ---------- kit standing on the bench ----------
    out.append(f'<div style="position:absolute;left:26%;bottom:{BENCH_TOP}px;z-index:6">'
               f'{fuge_sprite(COLD, "active", False, 0, 92)}</div>')
    for k in range(3):                                   # bioreactors
        out.append(
            f'<div style="position:absolute;left:{37+k*6}%;bottom:{BENCH_TOP}px;width:52px;height:76px;'
            f'background:rgba(200,107,255,.16);border:3px solid {a};border-radius:6px 6px 4px 4px;z-index:6">'
            f'<div style="position:absolute;bottom:5px;left:5px;right:5px;height:32px;'
            f'background:rgba(200,107,255,.45);border-radius:3px"></div>'
            f'<div style="position:absolute;top:-12px;left:50%;margin-left:-3px;width:6px;height:14px;'
            f'background:#8a97ab"></div></div>')
    for k in range(4):                                   # chromatography columns
        out.append(
            f'<div style="position:absolute;left:{57+k*4}%;bottom:{BENCH_TOP}px;width:22px;height:92px;'
            f'background:rgba(63,242,224,.20);border:2px solid #3ff2e0;border-radius:4px;z-index:6">'
            f'<div style="position:absolute;bottom:0;left:0;right:0;height:{rng.randint(18,62)}px;'
            f'background:rgba(63,242,224,.5)"></div></div>')
    for k in range(2):                                   # 96-well plates
        out.append(
            f'<div style="position:absolute;left:{75+k*5}%;bottom:{BENCH_TOP}px;width:44px;height:30px;'
            f'background:#dfe6f5;opacity:.3;border:1px solid {a};z-index:6">'
            + "".join(f'<div style="position:absolute;left:{3+c*5}px;top:{3+r*5}px;width:3px;height:3px;'
                      f'border-radius:50%;background:{a};opacity:.85"></div>'
                      for r in range(5) for c in range(8)) + '</div>')
    # sink + incubator on the right
    out.append(
        f'<div style="position:absolute;right:2%;bottom:{BENCH_TOP}px;width:104px;height:88px;'
        f'background:#3a2440;border:3px solid #8a97ab;border-radius:4px;z-index:6">'
        f'<div style="position:absolute;top:12px;left:22px;width:44px;height:44px;border-radius:50%;'
        f'border:3px solid {a};background:rgba(200,107,255,.16)"></div>'
        f'<div style="position:absolute;bottom:6px;left:14px;font-family:monospace;font-size:8px;'
        f'color:{a};opacity:.85">37.0 5%CO2</div></div>')

    # ---------- the fire nobody has noticed ----------
    out.append(
        f'<div style="position:absolute;left:69%;bottom:{BENCH_TOP}px;z-index:8">'
        + "".join(f'<div style="position:absolute;left:{j*9}px;bottom:0;width:13px;'
                  f'height:{18+j*7}px;border-radius:50% 50% 30% 30%;'
                  f'background:linear-gradient(180deg,#fff8b0,#ffb01f 55%,#ff3d0f);'
                  f'animation:lick3 {0.35+j*0.12:.2f}s ease-in-out infinite alternate"></div>'
                  for j in range(3))
        + f'<div style="position:absolute;left:-2px;bottom:36px;width:32px;height:32px;border-radius:50%;'
          f'background:rgba(60,50,50,.45);animation:billow3 2.6s ease-out infinite"></div></div>')

    # ---------- disco ball, beams, party lights ----------
    beams = "".join(
        f'<div style="position:absolute;left:50%;top:66px;width:6px;height:340px;'
        f'background:linear-gradient(180deg,{rng.choice(["#ff3d8b","#3ff2e0","#ffb627","#5be36a","#c86bff"])},'
        f'transparent 76%);transform-origin:top center;transform:rotate({j*22-77}deg);'
        f'opacity:.26;z-index:3;animation:beam3 {rng.uniform(3.0,6.0):.1f}s ease-in-out '
        f'{rng.uniform(0,2):.1f}s infinite alternate"></div>' for j in range(8))
    ball = (
        f'<div style="position:absolute;left:calc(50% - 2px);top:0;width:4px;height:30px;'
        f'background:#8a97ab;z-index:9"></div>'
        f'<div style="position:absolute;left:50%;margin-left:-27px;top:28px;width:54px;height:54px;'
        f'border-radius:50%;z-index:9;animation:spinball 4s linear infinite;'
        f'background:conic-gradient(#e8eefb 0 12%,#93a4c4 12% 25%,#e8eefb 25% 37%,#93a4c4 37% 50%,'
        f'#e8eefb 50% 62%,#93a4c4 62% 75%,#e8eefb 75% 87%,#93a4c4 87% 100%);'
        f'box-shadow:0 0 40px rgba(255,255,255,.6)"></div>')
    lights = "".join(
        f'<div style="position:absolute;left:{7+j*10}%;top:4px;width:18px;height:13px;'
        f'border-radius:0 0 9px 9px;background:{rng.choice(["#ff3d8b","#3ff2e0","#ffb627","#5be36a"])};'
        f'z-index:9;animation:blinklight {rng.uniform(.5,1.4):.1f}s steps(1) infinite"></div>'
        for j in range(9))

    # ---------- four scientists, dancing, with arms ----------
    def scientist(left, delay, tool):
        skin, coat = "#f0d2b4", "#f4f6ff"
        tools = {
            "pipette": f'<div style="position:absolute;top:-16px;right:-3px;width:4px;height:20px;'
                       f'background:#3ff2e0;border-radius:2px"></div>',
            "beaker": f'<div style="position:absolute;top:-12px;right:-6px;width:13px;height:14px;'
                      f'border:2px solid #cfe0f5;border-top:none;border-radius:0 0 3px 3px;'
                      f'background:linear-gradient(180deg,transparent 40%,#5be36a 40%)"></div>',
            "flask": f'<div style="position:absolute;top:-13px;right:-6px;width:0;height:0;'
                     f'border-left:7px solid transparent;border-right:7px solid transparent;'
                     f'border-bottom:14px solid #ff3d8b"></div>',
            "clip": f'<div style="position:absolute;top:-12px;right:-5px;width:11px;height:14px;'
                    f'background:#e8ecf5;opacity:.85;border:1px solid #8a97ab"></div>',
        }
        return (
            f'<div style="position:absolute;bottom:{BENCH_TOP-96}px;left:{left}%;width:40px;z-index:10;'
            f'animation:bobdance {rng.uniform(1.5,2.4):.1f}s ease-in-out {delay:.1f}s infinite">'
            f'<div style="position:relative;width:40px;height:88px">'
            f'<div style="position:absolute;top:0;left:10px;width:20px;height:18px;background:{skin};'
            f'border-radius:5px 5px 4px 4px"></div>'
            f'<div style="position:absolute;top:5px;left:8px;width:24px;height:7px;background:{a};'
            f'border:1px solid #10142a;border-radius:3px"></div>'
            f'<div style="position:absolute;top:18px;left:3px;width:34px;height:40px;background:{coat};'
            f'border:1px solid #b9bfd8;border-radius:4px 4px 2px 2px"></div>'
            f'<div style="position:absolute;top:18px;left:19px;width:2px;height:40px;background:#d4d9ea"></div>'
            f'<div style="position:absolute;top:22px;left:-4px;width:8px;height:24px;background:{coat};'
            f'border:1px solid #b9bfd8;border-radius:4px;transform-origin:top center;'
            f'animation:armswing .6s ease-in-out infinite alternate"></div>'
            f'<div style="position:absolute;top:22px;right:-4px;width:8px;height:24px;background:{coat};'
            f'border:1px solid #b9bfd8;border-radius:4px;transform-origin:top center;'
            f'animation:armswing .6s ease-in-out infinite alternate-reverse">{tools[tool]}</div>'
            f'<div style="position:absolute;top:58px;left:8px;width:9px;height:22px;background:#2b3358"></div>'
            f'<div style="position:absolute;top:58px;left:23px;width:9px;height:22px;background:#2b3358"></div>'
            f'</div></div>')
    out.append(scientist(15, 0.0, "pipette"))
    out.append(scientist(33, 0.5, "beaker"))
    out.append(scientist(63, 0.9, "flask"))
    out.append(scientist(84, 1.3, "clip"))

    # ---------- four monkeys in lab coats ----------
    fur, mskin = "#8a6240", "#d9b18a"
    for k in range(4):
        x = 8 + k * 23
        out.append(
            f'<div style="position:absolute;bottom:{BENCH_TOP-78}px;left:{x}%;width:34px;z-index:11;'
            f'animation:bobdance {rng.uniform(1.0,1.8):.1f}s ease-in-out {k*0.28:.1f}s infinite">'
            f'<div style="position:relative;width:34px;height:70px">'
            f'<div style="position:absolute;top:6px;left:1px;width:9px;height:9px;background:{fur};'
            f'border-radius:50%"></div>'
            f'<div style="position:absolute;top:6px;right:1px;width:9px;height:9px;background:{fur};'
            f'border-radius:50%"></div>'
            f'<div style="position:absolute;top:2px;left:7px;width:20px;height:18px;background:{fur};'
            f'border-radius:50% 50% 45% 45%"></div>'
            f'<div style="position:absolute;top:8px;left:10px;width:14px;height:10px;background:{mskin};'
            f'border-radius:50%"></div>'
            f'<div style="position:absolute;top:6px;left:8px;width:18px;height:6px;background:{a};'
            f'border:1px solid #10142a;border-radius:3px"></div>'
            f'<div style="position:absolute;top:20px;left:4px;width:26px;height:28px;background:#f4f6ff;'
            f'border:1px solid #b9bfd8;border-radius:3px"></div>'
            f'<div style="position:absolute;top:20px;left:16px;width:2px;height:28px;background:#d4d9ea"></div>'
            f'<div style="position:absolute;top:24px;left:-4px;width:7px;height:18px;background:{fur};'
            f'border-radius:3px;transform-origin:top center;animation:armswing .5s ease-in-out infinite alternate"></div>'
            f'<div style="position:absolute;top:24px;right:-4px;width:7px;height:18px;background:{fur};'
            f'border-radius:3px;transform-origin:top center;'
            f'animation:armswing .5s ease-in-out infinite alternate-reverse"></div>'
            f'<div style="position:absolute;top:48px;left:6px;width:7px;height:15px;background:{fur};'
            f'border-radius:3px"></div>'
            f'<div style="position:absolute;top:48px;left:20px;width:7px;height:15px;background:{fur};'
            f'border-radius:3px"></div>'
            f'<div style="position:absolute;top:34px;left:-11px;width:16px;height:16px;'
            f'border:3px solid {fur};border-radius:50%;border-right-color:transparent;'
            f'border-top-color:transparent"></div>'
            f'</div></div>')

    notes = "".join(
        f'<div style="position:absolute;left:{rng.randint(6,92)}%;bottom:{BENCH_TOP-40}px;z-index:12;'
        f'color:{rng.choice(["#ff3d8b","#3ff2e0","#ffb627"])};font-size:{rng.randint(14,22)}px;opacity:.8;'
        f'animation:notesup {rng.uniform(3.0,5.4):.1f}s linear {rng.uniform(0,3):.1f}s infinite">'
        f'{rng.choice(["&#9834;","&#9835;","&#9838;"])}</div>' for _ in range(10))

    # ---------- finale: the scientist walks in and the room notices ----------
    arrival = ""
    if arriving:
        confetti = "".join(
            f'<div style="position:absolute;left:{rng.randint(0,99)}%;top:-20px;'
            f'width:{rng.randint(5,10)}px;height:{rng.randint(8,15)}px;z-index:14;'
            f'background:{rng.choice(["#ff3d8b","#3ff2e0","#ffb627","#5be36a","#c86bff","#ffffff"])};'
            f'animation:confetti {rng.uniform(2.4,4.6):.1f}s linear {rng.uniform(0,2.6):.1f}s infinite"></div>'
            for _ in range(46))
        arrival = (
            confetti +
            f'<div class="arrive-sci"><div style="position:relative;width:40px;height:88px">'
            f'<div style="position:absolute;top:0;left:10px;width:20px;height:18px;background:#f0d2b4;'
            f'border-radius:5px 5px 4px 4px"></div>'
            f'<div style="position:absolute;top:5px;left:8px;width:24px;height:7px;background:{a};'
            f'border:1px solid #10142a;border-radius:3px"></div>'
            f'<div style="position:absolute;top:18px;left:3px;width:34px;height:40px;background:#f4f6ff;'
            f'border:1px solid #b9bfd8;border-radius:4px 4px 2px 2px"></div>'
            f'<div style="position:absolute;top:22px;left:-4px;width:8px;height:24px;background:#f4f6ff;'
            f'border:1px solid #b9bfd8;border-radius:4px;transform-origin:top center;'
            f'animation:armswing .5s ease-in-out infinite alternate"></div>'
            f'<div style="position:absolute;top:22px;right:-4px;width:8px;height:24px;background:#f4f6ff;'
            f'border:1px solid #b9bfd8;border-radius:4px;transform-origin:top center;'
            f'animation:armswing .5s ease-in-out infinite alternate-reverse"></div>'
            f'<div style="position:absolute;top:58px;left:8px;width:9px;height:22px;background:#2b3358"></div>'
            f'<div style="position:absolute;top:58px;left:23px;width:9px;height:22px;background:#2b3358"></div>'
            f'</div></div>'
            f'<div class="cheer">SHIFT OVER!</div>')

    inner = f"""
    <style>
      @keyframes confetti {{ to {{ transform:translateY(430px) rotate(680deg); opacity:.15 }} }}
      @keyframes walkin {{ 0%{{left:-8%}} 55%{{left:44%}} 100%{{left:47%}} }}
      @keyframes cheerin {{ 0%,40%{{opacity:0;transform:scale(.5)}} 60%{{opacity:1;transform:scale(1.12)}}
                            70%,100%{{opacity:1;transform:scale(1)}} }}
      .arrive-sci {{ position:absolute; bottom:{BENCH_TOP-96}px; width:40px; z-index:13;
                     animation:walkin 2.6s cubic-bezier(.4,0,.4,1) forwards,
                               bobdance 1.6s ease-in-out 2.6s infinite; }}
      .cheer {{ position:absolute; left:0; right:0; top:172px; text-align:center; z-index:14;
                font-family:'Press Start 2P',monospace; font-size:19px; color:#ffb627;
                text-shadow:0 0 20px #ffb627; animation:cheerin 3.2s ease-out forwards; }}
      @keyframes spinball {{ to {{ transform:rotate(360deg) }} }}
      @keyframes beam3 {{ from {{ opacity:.14 }} to {{ opacity:.40 }} }}
      @keyframes blinklight {{ 0%,49%{{opacity:1}} 50%,100%{{opacity:.22}} }}
      @keyframes bobdance {{ 0%,100%{{transform:translateY(0) rotate(-3deg)}}
                             50%{{transform:translateY(-10px) rotate(3deg)}} }}
      @keyframes armswing {{ from{{transform:rotate(-26deg)}} to{{transform:rotate(30deg)}} }}
      @keyframes lick3 {{ from{{transform:scaleY(.8)}} to{{transform:scaleY(1.28)}} }}
      @keyframes billow3 {{ from{{transform:translateY(0) scale(.5);opacity:.6}}
                            to{{transform:translateY(-56px) scale(2);opacity:0}} }}
      @keyframes notesup {{ from{{transform:translateY(0);opacity:.85}}
                            to{{transform:translateY(-140px);opacity:0}} }}
      .thanks {{ position:absolute; left:50%; margin-left:-200px; top:96px; width:400px; z-index:13;
                 background:rgba(0,0,0,.6); border:3px solid {a}; padding:12px 10px; text-align:center;
                 font-family:'Press Start 2P',monospace; font-size:11px; color:{a}; line-height:2;
                 text-shadow:0 0 14px {a}; }}
      .deptsign {{ position:absolute; left:2%; top:96px; z-index:13; font-family:'Press Start 2P',monospace;
                   font-size:9px; color:#ffb627; border:2px solid #ffb627; padding:7px 9px;
                   background:rgba(0,0,0,.55); line-height:1.9; }}
    </style>
    {beams}{ball}{lights}
    {"".join(out)}
    {notes}{arrival}
    <div class="deptsign">THE DEPARTMENT<br><span style="opacity:.65">AAV VECTOR CORE</span></div>
    <div class="thanks">THANK YOU FOR<br>CHOOSING THE DEPARTMENT</div>
    """
    return scene_shell(390, BSL4, inner)

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
# Okabe-Ito safe palette. Shapes carry the meaning too, so the rotor stays
# readable even in greyscale.
CB_PALETTE = {"locked": "#0072B2", "player": "#E69F00",
              "needle": "#CC79A7", "blocked": "#9A9A9A", "ok": "#0072B2"}
DEFAULT_PALETTE = {"locked": GREEN, "player": CYAN,
                   "needle": MAGENTA, "blocked": MAGENTA, "ok": GREEN}


def palette() -> Dict[str, str]:
    return CB_PALETTE if st.session_state.get("cb") else DEFAULT_PALETTE


CB_CSS = """
<style>
.stButton > button[kind="primary"] { background:#E69F00 !important; color:#06070d !important;
    border-color:#E69F00 !important; box-shadow:0 0 14px rgba(230,159,0,.45) !important; }
.cc-ok { color:#0072B2 !important; }
.cc-bad { color:#CC79A7 !important; }
.tray-done { border-color:#0072B2 !important; color:#0072B2 !important;
             background:rgba(0,114,178,.13) !important; }
.pip-done { color:#E69F00 !important; }
</style>
"""


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
    k = room.critter.split(",")[0].strip()
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

    pal = palette()
    cb = bool(st.session_state.get("cb"))
    # Colour alone separates locked from placed in the normal palette, so both stay
    # round. Colourblind mode switches placed tubes to a diamond so shape carries
    # the meaning when the two hues are hard to tell apart.
    player_symbol = "diamond" if cb else "circle"
    xs, ys, colors, sizes, lines, hover, syms = [], [], [], [], [], [], []
    for i in range(n):
        x, y = slot_xy(i, n, 1.0)
        xs.append(x); ys.append(y)
        m = loads[i]
        if i in blocked:
            colors.append(pal["blocked"]); sizes.append(19)
            lines.append(pal["blocked"]); syms.append("x")
            hover.append(f"{i} · cracked bucket")
        elif m is None:
            colors.append("rgba(6,7,13,0.85)"); sizes.append(20)
            lines.append(STEEL); syms.append("circle")
            hover.append(f"{i} · empty — click to load")
        elif base[i] is not None:
            colors.append(pal["locked"]); sizes.append(tube_size(m))
            lines.append("#04121f"); syms.append("circle")
            hover.append(f"{i} · locked {m:g} g")
        else:
            colors.append(pal["player"]); sizes.append(tube_size(m))
            lines.append("#2a1a00" if cb else "#062a28"); syms.append(player_symbol)
            hover.append(f"{i} · yours {m:g} g — click to lift")

    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="markers", customdata=list(range(n)),
        marker=dict(color=colors, size=sizes, symbol=syms,
                    line=dict(color=lines, width=2)),
        hovertext=hover, hoverinfo="text",
        selected=dict(marker=dict(opacity=1.0)), unselected=dict(marker=dict(opacity=1.0)),
        showlegend=False))

    ann = []
    if not spec.hide_labels:
        lab_size = 11 if n <= 24 else (9 if n <= 36 else 8)
        for i in range(n):
            lx, ly = slot_xy(i, n, 1.345)
            ann.append(dict(x=lx, y=ly, text=str(i), showarrow=False,
                            font=dict(family="IBM Plex Mono, monospace", size=lab_size, color=DIM)))
    else:
        for i in range(0, n, max(1, n // 4)):            # keep a few frost-free marks
            lx, ly = slot_xy(i, n, 1.345)
            ann.append(dict(x=lx, y=ly, text="\u2744", showarrow=False,
                            font=dict(family="IBM Plex Mono, monospace", size=12,
                                      color=_hex_rgba(room.accent, 0.55))))

    if show_needle:
        vx, vy = imbalance_vector(loads)
        mag = math.hypot(vx, vy)
        if mag > 1e-9:
            scale = min(1.02, 0.20 + mag * 0.075)
            shapes.append(dict(type="line", x0=0, y0=0, x1=scale * vx / mag, y1=-scale * vy / mag,
                               line=dict(color=pal["needle"], width=5), layer="above"))
        else:
            shapes.append(dict(type="circle", x0=-0.10, y0=-0.10, x1=0.10, y1=0.10,
                               fillcolor=pal["ok"], line=dict(color=pal["ok"], width=1),
                               layer="above"))
    else:
        ann.append(dict(x=0, y=0, text="?", showarrow=False,
                        font=dict(family="Press Start 2P, monospace", size=15,
                                  color=pal["needle"])))

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
RUNS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".runs")
RESUME_WINDOW = 6 * 3600      # seconds a dropped run stays resumable

# Streamlit drops idle websockets, and a reconnect starts a brand-new session with
# empty state -- which lands the player back on the title screen mid-run. The last
# level has by far the largest search space, so it is where people sit longest and
# where this bites. Snapshotting the run makes that recoverable.
SNAP_KEYS = ["name", "level", "in_ultra", "ultra_count", "lives", "scores", "fails",
             "streak", "best_streak", "seed", "daily", "required", "cb", "muted"]


def save_snapshot():
    ss = st.session_state
    rid = ss.get("run_id")
    if not rid or "base" not in ss:
        return
    data = {k: ss.get(k) for k in SNAP_KEYS}
    data["base"] = list(ss.base)
    data["blocked"] = sorted(int(b) for b in ss.blocked)
    data["hand"] = list(ss.hand)
    data["player"] = list(ss.player)
    data["elapsed"] = time.time() - ss.get("level_start", time.time())
    data["played"] = time.time() - ss.get("game_start", time.time())
    data["saved_at"] = time.time()
    try:
        os.makedirs(RUNS_DIR, exist_ok=True)
        with open(os.path.join(RUNS_DIR, f"{rid}.json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except Exception:
        pass


def read_snapshot(run_id: str) -> Optional[dict]:
    try:
        with open(os.path.join(RUNS_DIR, f"{run_id}.json"), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if time.time() - data.get("saved_at", 0) > RESUME_WINDOW:
            return None
        return data
    except Exception:
        return None


def drop_snapshot():
    rid = st.session_state.get("run_id")
    if not rid:
        return
    try:
        os.remove(os.path.join(RUNS_DIR, f"{rid}.json"))
    except Exception:
        pass


def restore_snapshot(run_id: str, data: dict):
    ss = st.session_state
    for k in SNAP_KEYS:
        ss[k] = data.get(k)
    ss.base = data["base"]
    ss.blocked = set(data["blocked"])
    ss.hand = list(data["hand"])
    ss.player = list(data["player"])
    ss.run_id = run_id
    ss.submitted = False
    ss.burned = False
    ss.partied = False
    # give the player a moment back rather than resuming a timer that already expired
    ss.level_start = time.time() - min(data.get("elapsed", 0), 20)
    ss.game_start = time.time() - data.get("played", 0)
    if ss.get("daily"):
        ss.daily_spec = daily_spec()
        ss.daily_room = daily_room()
    ss.nonce = ss.get("nonce", 0) + 1
    ss.phase = "play"
WORKSHEET = "scores"
WORKSHEET_DAILY = "daily"
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


def _board(daily: bool) -> Tuple[str, str]:
    if daily:
        return WORKSHEET_DAILY, LOCAL_DB.replace(".json", "_daily.json")
    return WORKSHEET, LOCAL_DB


def load_scores(daily: bool = False) -> List[dict]:
    sheet, path = _board(daily)
    conn = _sheets()
    if conn is not None:
        try:
            df = conn.read(worksheet=sheet, ttl=5, usecols=list(range(len(COLUMNS))))
            return df.dropna(how="all").to_dict("records")
        except Exception:
            pass          # worksheet may not exist yet; fall through to the local file
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return []


def save_score(row: dict, daily: bool = False) -> bool:
    sheet, path = _board(daily)
    rows = load_scores(daily)
    rows.append(row)
    rows = sorted(rows, key=lambda r: -int(float(r.get("score", 0))))[:500]
    conn = _sheets()
    if conn is not None:
        try:
            import pandas as pd
            conn.update(worksheet=sheet, data=pd.DataFrame(rows, columns=COLUMNS))
            return True
        except Exception:
            pass
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=1)
        return True
    except Exception:
        return False


def leaderboard_table(rows: List[dict], highlight: Optional[str] = None, top: int = 10) -> str:
    rows = sorted(rows, key=lambda r: -int(float(r.get("score", 0))))[:top]
    if not rows:
        return '<p class="cc-readout">No scores logged yet. Be the first.</p>'
    out = ['<table class="cc-lb"><tr><th>#</th><th>Operator</th><th>Score</th>'
           '<th>Done</th><th>Time</th></tr>']
    for i, r in enumerate(rows, 1):
        me = ' class="me"' if highlight and str(r.get("name")) == highlight else ""
        s = int(float(r.get("seconds", 0)))
        out.append(f"<tr{me}><td class='rank'>{i:02d}</td><td>{r.get('name','???')}</td>"
                   f"<td>{int(float(r.get('score',0)))}</td>"
                   f"<td>{int(float(r.get('levels',0)))}</td>"
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
    ss.setdefault("required", 1)
    ss.setdefault("streak", 0)
    ss.setdefault("best_streak", 0)
    ss.setdefault("daily", False)
    ss.setdefault("cb", False)
    ss.setdefault("run_id", "")
    ss.setdefault("seed", random.randint(0, 9999))
    ss.setdefault("submitted", False)
    ss.setdefault("muted", False)
    ss.setdefault("burned", False)
    ss.setdefault("last_result", None)
    ss.setdefault("show_help", False)


def current_spec() -> LevelSpec:
    ss = st.session_state
    if ss.get("daily"):
        return ss.daily_spec
    return ULTRA_SPEC if ss.in_ultra else LEVELS[ss.level]


def current_room() -> Room:
    ss = st.session_state
    if ss.get("daily"):
        return ss.daily_room
    return SUITE3 if ss.in_ultra else room_for(ss.level)


def level_rng(spec: LevelSpec) -> random.Random:
    """Daily runs are seeded from the date, so every player gets the same rotors."""
    ss = st.session_state
    if ss.get("daily"):
        return random.Random("rotor|" + time.strftime("%Y-%m-%d") + "|" + spec.name)
    return random.Random()


def load_level(spec: LevelSpec, keep_fails: bool = False):
    ss = st.session_state
    rng = level_rng(spec)
    base, blocked, hand = generate_level(spec, rng)
    if spec.extra_tubes:                      # decoys: solvable set plus spares
        hand = hand + [rng.choice(spec.masses) for _ in range(spec.extra_tubes)]
        hand.sort(reverse=True)
    ss.base, ss.blocked, ss.hand = base, blocked, hand
    ss.required = spec.to_place
    ss.player = [None] * spec.slots
    ss.pick = 0
    if not keep_fails:
        ss.fails = 0
    ss.nonce += 1
    ss.level_start = time.time()
    save_snapshot()


def reset_game():
    for k in ("phase", "level", "scores", "fails", "lives", "ultra_count", "in_ultra",
              "submitted", "last_result", "show_help", "burned", "seed", "partied",
              "streak", "best_streak", "daily", "required", "daily_spec", "daily_room"):
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
    st.markdown(room_background_css("lobby"), unsafe_allow_html=True)
    html_block(scene_attract(ss.seed), height=452)

    c1, c2, c5, c3, c4 = st.columns([2, 1.3, 1.3, 1.3, 1.3])
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
            ss.streak, ss.best_streak = 0, 0
            ss.run_id = uuid.uuid4().hex[:12]
            st.query_params["run"] = ss.run_id
            ss.daily = False
            ss.seed = random.randint(0, 9999)
            ss.game_start = time.time()
            load_level(LEVELS[0])
            ss.phase = "intro"
            st.rerun()
    with c5:
        if st.button("DAILY CHALLENGE", **BTN):
            ss.name = (name or "ANON").strip().upper()[:12] or "ANON"
            ss.level = 0
            ss.scores, ss.lives = [], START_LIVES
            ss.ultra_count, ss.in_ultra = 0, False
            ss.submitted, ss.burned = False, False
            ss.streak, ss.best_streak = 0, 0
            ss.run_id = uuid.uuid4().hex[:12]
            st.query_params["run"] = ss.run_id
            ss.daily = True
            ss.daily_spec = daily_spec()
            ss.daily_room = daily_room()
            ss.seed = int(time.strftime("%Y%m%d"))
            ss.game_start = time.time()
            load_level(ss.daily_spec)
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

    e1, e2 = st.columns([2, 4.9])
    with e1:
        if st.button("COLORBLIND: ON" if ss.cb else "COLORBLIND: OFF", **BTN):
            ss.cb = not ss.cb
            st.rerun()

    pending = None
    try:
        rid = st.query_params.get("run")
        if rid and not ss.get("run_id"):
            pending = read_snapshot(rid)
    except Exception:
        pending = None
    if pending:
        lv = int(pending.get("level", 0)) + 1
        st.markdown(
            f'<div class="cc-gimmick" style="color:{palette()["player"]};'
            f'border-color:{palette()["player"]};background:rgba(230,159,0,.10)">'
            f'INTERRUPTED RUN FOUND &mdash; {pending.get("name","?")} on level {lv}, '
            f'{sum(pending.get("scores") or [])} points</div>', unsafe_allow_html=True)
        r1, _ = st.columns([2, 4.9])
        with r1:
            if st.button(f"RESUME LEVEL {lv}", type="primary", **BTN):
                restore_snapshot(rid, pending)
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
            <span style="color:{palette()['locked']}">&#9679;</span> = locked in already
            &nbsp;&middot;&nbsp;
            <span style="color:{palette()['player']}">{'&#9670; diamond' if ss.cb else '&#9679;'}</span>
            = yours &nbsp;&middot;&nbsp;
            <span style="color:{palette()['blocked']}">&#10006;</span> = cracked bucket, unusable<br>
            <span class="cc-amber">3 lives.</span> Spin unbalanced and one is gone.
            If the PA calls you to Suite 3, there are no lives in there.
            </p></div>""", unsafe_allow_html=True)


def screen_intro():
    ss = st.session_state
    spec = current_spec()
    room = current_room()
    st.markdown(f'<div class="cc-strip">{room.name} &nbsp;&middot;&nbsp; {spec.name} '
                f'&nbsp;&middot;&nbsp; {spec.subtitle}</div>', unsafe_allow_html=True)
    st.markdown(room_background_css(room.key), unsafe_allow_html=True)
    st.markdown('<div class="cc-blackout"></div>', unsafe_allow_html=True)
    html_block(scene_transit(room, spec.zone, ss.level, ss.seed + ss.level,
                                  label=("DAILY CHALLENGE" if ss.get("daily")
                                         else f"LEVEL {ss.level+1}")), height=330)
    time.sleep(4.3)
    ss.phase = "play"
    ss.level_start = time.time()
    st.rerun()


def screen_ultra_intro():
    ss = st.session_state
    st.markdown('<div class="cc-strip" style="color:#ff3d8b">&#9888; UNSCHEDULED RUN &#9888;</div>',
                unsafe_allow_html=True)
    st.markdown(room_background_css("suite3"), unsafe_allow_html=True)
    st.markdown('<div class="cc-blackout"></div>', unsafe_allow_html=True)
    html_block(scene_ultra_alert(), height=280)
    time.sleep(3.0)
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
    blind = spec.sudden_death
    required = ss.get("required", spec.to_place)
    seated = sum(1 for i in range(spec.slots) if ss.player[i] is not None)
    ready = seated >= required

    if spec.time_limit and time.time() - ss.level_start > spec.time_limit:
        ss.streak = 0
        ss.last_result = ("timeout", resid, tol, 0, 0, 0, 1.0)
        play("alarm"); ss.phase = "explode"; st.rerun()

    st.markdown(room_background_css(room.key), unsafe_allow_html=True)

    header = (f'<div class="cc-strip" style="color:#ff3d8b">{spec.name} &nbsp;&middot;&nbsp; {spec.subtitle}</div>'
              if spec.sudden_death else
              f'<div class="cc-strip">{room.name} &nbsp;&middot;&nbsp; {spec.name} '
              f'&nbsp;&middot;&nbsp; {spec.subtitle}</div>')
    st.markdown(header, unsafe_allow_html=True)
    save_snapshot()
    if ss.get("daily"):
        st.markdown(f'<div class="cc-strip" style="color:{palette()["player"]};font-size:.55rem">'
                    f'DAILY CHALLENGE &middot; {time.strftime("%Y-%m-%d")} &middot; '
                    f'every player gets this exact rotor</div>', unsafe_allow_html=True)
    if spec.gimmick:
        st.markdown(f'<div class="cc-gimmick">&#9888; {spec.gimmick}</div>', unsafe_allow_html=True)

    # --- rotor, centred ---
    _, mid, _ = st.columns([1, 2.1, 1])
    with mid:
        fig = rotor_figure(spec, room, ss.base, ss.player, ss.blocked,
                           show_needle=not blind, height=440)
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

    # --- everything else, centred underneath ---
    _, right, _ = st.columns([1, 2.1, 1])
    with right:
        hearts = ("&#9829;" * ss.lives +
                  '<span style="color:#333a58">&#9829;</span>' * (START_LIVES - ss.lives))
        if ss.get("daily"):
            tag = "DAILY"
        elif spec.sudden_death:
            tag = "SUITE 3"
        else:
            tag = f"{ss.level+1:02d}/{len(LEVELS)}"
        clock = (f'<div><span class="k">LIMIT</span><span style="color:{MAGENTA}">'
                 f'{spec.time_limit}s</span></div>' if spec.time_limit
                 else f'<div><span class="k">PAR</span>{spec.par_seconds}s</div>')
        st.markdown(
            f'<div class="cc-panel"><div class="cc-hud">'
            f'<div><span class="k">LEVEL</span>{tag}</div>'
            f'<div><span class="k">SCORE</span>{sum(ss.scores)}</div>'
            f'<div><span class="k">LIVES</span><span style="color:{MAGENTA}">{hearts}</span></div>'
            f'<div><span class="k">STREAK</span>x{streak_multiplier(ss.streak):.1f}</div>'
            f'{clock}</div></div>', unsafe_allow_html=True)

        if spec.time_limit:
            left_s = max(0, spec.time_limit - (time.time() - ss.level_start))
            html_block(countdown_html(left_s), height=52)

        # ---- tube tray: make multi-tube levels unmistakable ----
        word = "TUBE" if required == 1 else "TUBES"
        if not ready:
            extra_note = (f'<br><span style="font-size:.56rem;opacity:.75">'
                          f'{len(ss.hand)} in tray &middot; {spec.extra_tubes} are spares</span>'
                          if spec.extra_tubes else
                          f'<br><span style="font-size:.62rem">{seated} SEATED &middot; '
                          f'{len(ss.hand)} IN TRAY</span>')
            banner = (f'<div class="tray-banner tray-need">PLACE {required} {word}{extra_note}</div>')
        else:
            banner = ('<div class="tray-banner tray-done">ROTOR LOADED<br>'
                      '<span style="font-size:.62rem">READY TO SPIN</span></div>')
        pips = "".join('<span class="pip-done">&#9679;</span>' for _ in range(min(seated, required)))
        pips += "".join('<span class="pip-todo">&#9675;</span>' for _ in range(max(0, required - seated)))
        st.markdown(banner + f'<div class="pips">{pips}</div>', unsafe_allow_html=True)

        if ss.hand:
            if ss.pick >= len(ss.hand):
                ss.pick = 0
            pad = max(0, (5 - len(ss.hand)) / 2)
            cols = st.columns([pad] + [1] * len(ss.hand) + [pad]) if pad else st.columns(len(ss.hand))
            cols = cols[1:-1] if pad else cols
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

        if not ready:
            need = required - seated
            spin_label = f"SEAT {need} MORE TUBE{'' if need == 1 else 'S'}"
        else:
            spin_label = "SEAL CHAMBER AND SPIN" if spec.sudden_death else "CLOSE LID AND SPIN"
        s1, s2 = st.columns([2, 1])
        with s1:
            if st.button(spin_label, type="primary", disabled=not ready, **BTN):
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
    st.markdown(room_background_css(current_room().key), unsafe_allow_html=True)
    st.markdown('<div class="cc-blackout"></div>', unsafe_allow_html=True)
    html_block(scene_spin(spec.zone, current_room(), spec.slots), height=280)
    time.sleep(2.0)

    if resid > tol:
        ss.fails += 1
        ss.streak = 0
        ss.last_result = ("fail", resid, tol, 0, 0, 0, 1.0)
        play("alarm")
        ss.phase = "explode"
    else:
        elapsed = time.time() - ss.level_start
        clean = CLEAN_POINTS
        speed = TIME_POINTS * max(0.0, (spec.par_seconds - elapsed) / spec.par_seconds)
        bonus = ULTRA_BONUS if spec.sudden_death else 0
        mult = streak_multiplier(ss.streak)
        pts = max(0, round((clean + speed + bonus) * mult - FAIL_PENALTY * ss.fails))
        ss.streak += 1
        ss.best_streak = max(ss.get("best_streak", 0), ss.streak)
        ss.scores.append(pts)
        ss.last_result = ("pass", resid, tol, round(clean), round(speed + bonus), pts, mult)
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
    st.markdown('<div class="cc-blackout"></div>', unsafe_allow_html=True)
    html_block(scene_explode(current_room(), lethal), height=280)
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
    kind, resid, tol, acc, speed, pts, mult = ss.last_result

    if kind in ("fail", "timeout"):
        why = ("The clock ran out with the chamber still open." if kind == "timeout"
               else f"Imbalance hit {resid:.3f} against a {tol:.3f} limit.")
        _, c, _ = st.columns([1, 1.7, 1])
        with c:
            st.markdown('<div class="cc-centre">', unsafe_allow_html=True)
            st.markdown('<div class="cc-strip" style="color:#ff3d8b;font-size:1.05rem">'
                        'ROTOR DESTROYED</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="cc-panel"><p class="cc-readout" style="line-height:1.9">{why}<br>'
                f'You lost a life and {FAIL_PENALTY} points.<br><br>'
                f'<span class="cc-amber">{ss.lives}</span> of {START_LIVES} lives left. '
                f'A fresh rotor is being wheeled over.</p></div>', unsafe_allow_html=True)
            if st.button("TAKE THE NEW ROTOR", type="primary", **BTN):
                load_level(spec, keep_fails=True)
                ss.phase = "play"
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        return

    title = "SUITE 3 CLEARED" if spec.sudden_death else "CLEAN SPIN"
    _, c, _ = st.columns([1, 1.7, 1])
    with c:
        st.markdown('<div class="cc-centre">', unsafe_allow_html=True)
        st.markdown(f'<div class="cc-strip" style="color:#5be36a;font-size:1.05rem">{title}</div>',
                    unsafe_allow_html=True)
        st.markdown(
            f'<div class="cc-panel"><div class="cc-hud">'
            f'<div><span class="k">RESIDUAL</span>{resid:.3f}</div>'
            f'<div><span class="k">CLEAN</span>{acc}</div>'
            f'<div><span class="k">STREAK</span>x{mult:.1f}</div>'
            f'<div><span class="k">{"BONUS" if spec.sudden_death else "SPEED"}</span>{speed}</div>'
            f'<div><span class="k">ABORTS</span>-{FAIL_PENALTY*ss.fails}</div>'
            f'<div><span class="k">LEVEL</span>{pts}</div>'
            f'<div><span class="k">TOTAL</span>{sum(ss.scores)}</div>'
            f'</div></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    if ss.in_ultra:
        with c:
            if st.button("BACK TO THE BENCH", type="primary", **BTN):
                ss.in_ultra = False
                ss.level += 1
                load_level(LEVELS[ss.level])
                ss.phase = "intro"
                st.rerun()
        return

    if ss.get("daily"):
        with c:
            if st.button("SUBMIT DAILY RUN", type="primary", **BTN):
                finish_run(f"You cleared today's {current_spec().slots}-position rotor.", False)
                st.rerun()
        return

    last = ss.level + 1 >= len(LEVELS)
    with c:
        if st.button("END SHIFT" if last else "NEXT CENTRIFUGE", type="primary", **BTN):
            if last:
                finish_run("You balanced every rotor on the bench and went home clean.", False)
            else:
                hit = (ss.level >= ULTRA_EARLIEST and ss.ultra_count < ULTRA_MAX
                       and random.Random().random() < ULTRA_CHANCE)
                if hit:
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
    st.markdown('<div class="cc-blackout"></div>', unsafe_allow_html=True)
    stage = st.empty()
    if ss.burned:
        play_now("over")
        with stage.container():
            html_block(scene_fire(ss.seed), height=300)
        time.sleep(3.0)
    # however the shift ended, everyone winds up at The Department
    play_now("party")
    ss.partied = True
    with stage.container():
        html_block(scene_department(ss.seed, arriving=True), height=404)
    time.sleep(4.4)
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
        f'<div><span class="k">CLEARED</span>'
        f'{len(ss.scores)}/{1 if ss.get("daily") else len(LEVELS)}</div>'
        f'<div><span class="k">BEST STREAK</span>x{streak_multiplier(max(0,ss.get("best_streak",1)-1)):.1f}</div>'
        f'<div><span class="k">LIVES LEFT</span>{ss.lives}</div>'
        f'<div><span class="k">SHIFT TIME</span>{shift//60}:{shift%60:02d}</div>'
        f'</div></div>', unsafe_allow_html=True)

    drop_snapshot()
    if not ss.submitted:
        save_score({"name": ss.name, "score": total, "levels": len(ss.scores),
                    "seconds": shift, "when": time.strftime("%Y-%m-%d")},
                   daily=ss.get("daily", False))
        ss.submitted = True

    a, b = st.columns([1.4, 1], gap="medium")
    with a:
        st.markdown(f'<p class="cc-readout" style="text-align:left">'
                    f'{"DAILY CHALLENGE" if ss.get("daily") else "GLOBAL"} TOP 8</p>',
                    unsafe_allow_html=True)
        st.markdown(leaderboard_table(load_scores(ss.get("daily", False)),
                                      highlight=ss.name, top=8), unsafe_allow_html=True)
        st.markdown(f'<p class="cc-readout" style="font-size:.66rem;text-align:left">'
                    f'stored in: {backend_name()}</p>', unsafe_allow_html=True)
    with b:
        st.markdown('<p class="cc-readout" style="text-align:left">PER LEVEL</p>',
                    unsafe_allow_html=True)
        rows = "".join(f"<tr><td class='rank'>{i+1:02d}</td><td>{v}</td></tr>"
                       for i, v in enumerate(ss.scores)) or "<tr><td>-</td><td>0</td></tr>"
        st.markdown(f'<table class="cc-lb"><tr><th>#</th><th>Points</th></tr>{rows}</table>',
                    unsafe_allow_html=True)
    d = st.columns([1, 1.6, 1])[1]
    with d:
        if st.button("NEW SHIFT", type="primary", **BTN):
            reset_game()
            st.rerun()

    if not ss.get("partied"):
        play_now("party")
        ss.partied = True
    html_block(scene_department(ss.seed), height=404)


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
    if st.session_state.get("cb"):
        st.markdown(CB_CSS, unsafe_allow_html=True)
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
