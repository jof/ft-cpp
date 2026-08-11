#!/usr/bin/env python3
"""San Francisco's shared bikes, drawn as what they are: a fluid on a hillside.

Bay Wheels is not a fleet of vehicles so much as a tide. Every weekday morning
the city's bikes get ridden downhill and eastward into the financial district,
and every evening they come back up -- and in between, the operator's vans push
them back the other way. The interesting quantity is therefore never "how many
bikes are there", which barely changes, but **where they have got to and which
way they are going**.

So the panel is a hill. Three hundred and eighty-three San Francisco docks are
laid out left to right in order of **ground altitude** -- Embarcadero and Mission
Bay at three metres on the left, Twin Peaks and Buena Vista at a hundred and
fifty on the right -- and the ridge line you see is the city's own hypsometry,
the sorted elevation of every dock in it. Each dock colours the strip of ridge it
sits on: **hot amber where a station is dry, quiet teal where it is healthy, cold
blue where it is jammed full**. Both ends of that ramp are failures and both are
visible; the ordinary middle is deliberately the dimmest thing on the panel, so
what glows is what is wrong.

**Why a hill and not a map.** A map of the Bay with dots on it is what `adsb.py`
already draws, and it would be the wrong picture besides: `adsb` is about
individual objects with velocity, this is a slow scalar field over fixed
locations, and geography is not the variable that explains it. Altitude is.
Bikes roll downhill for nothing and have to be pedalled, or trucked, back up, so
gravity is the force the whole system is fighting, and a chart whose x axis is
gravity shows you the fight. A map would spend three hundred columns on the fact
that San Francisco is seven miles square.

**The number in the sky is the fleet's centre of mass, in metres.** Two averages
come out of the record: the mean altitude of a bike you could go and unlock, and
the mean altitude of a *parking space*, which is where the fleet would sit if it
were spread evenly over the docks. The difference between them is the headline.
Negative -- the usual state by teatime -- means the fleet has run downhill and
the hills are running dry. It is a metre count and not a bike count, so it does
not move when the operator adds a hundred bikes to the city, and that is exactly
why it is the number: it is about *distribution*, which is the thing that fails.

**Under the hill, the same number for the last twenty-four hours**, as a signed
lane above and below the docks' own altitude. That strip is the commute pump.
The feeds are a snapshot with no history in them at all, so the series is
accumulated by the fetcher ten minutes at a time; on a cold cache the lane is
nearly empty and fills in over a day, which is honest and is drawn as such
rather than faked.

**The mist above the ridge is the other fleet.** Several hundred ebikes are
parked loose at the kerb rather than in any dock, which is a different
population with different physics -- nobody rebalances them, they simply pile up
wherever the last rider left them. They have no dock and so no altitude of their
own, so each takes the altitude of its nearest station, and the histogram of
that is drawn as a dim stipple hanging over the ridge. Where the mist is thick,
loose bikes have collected.

**The vertical scale is a square root and the panel says so.** Half of San
Francisco's docks are below twenty-one metres; drawn linearly the entire
interesting low city is squashed into six rows and the panel is a flat line with
a spike on the end. The gridlines are labelled in metres so the compression is
declared rather than hidden.

**Three honest failures.** A record past its half-hour TTL still draws, with the
age and STALE on it, because a twenty-minute-old occupancy map is nearly right.
One older than `--max-age` (six hours by default) is refused outright and gets a
card: past that, every station that was dry has probably changed, and a
confident hillside of yesterday evening's colours is the one lie this panel
could tell. No record at all gets the same card and the command that fixes it.

**Frame budget.** Everything is baked in `build()` -- the ridge, the rock, the
colours, the mist, the lane, the legend and the header are rasterised once into
two uint8 frames. `render()` copies one of them, runs a soft sheen over a
thirty-two column window, writes the dry-station flags at a pulsing brightness
through one fancy index, and draws the now-line in the lane. That is eight or
nine numpy calls, and on the wall's Pi a numpy call costs tens of microseconds
whatever the array size, so the call count is the budget and not the pixel
count. Measured here over a full loop: see the README.

Run:  python3 ftdata.py --once --only baywheels
      python3 bikes.py --host 127.0.0.1
      FT_DATA_CACHE=/tmp/empty python3 bikes.py      # the no-data card
      python3 scripts/test-bikes.py
"""

import math
import sys
import time

import numpy as np

import defcon
import demoscene as ds
import ftdata

f32 = np.float32

PRODUCT = "baywheels"

# --------------------------------------------------------------------------
# Type. defcon.py's 3x5 font, the same one caiso, tide, propagation and sort
# draw with: five rows a glyph, each row an octal digit whose three bits are
# the three columns. Anything from a real typeface is mush at five pixels, and
# the Pi does not have the same faces installed as the machine this was
# written on. One glyph is added, for the sign this panel needs and a map of a
# nuclear exchange does not.
# --------------------------------------------------------------------------

_FONT = dict(defcon._FONT)
_FONT.update({"+": "02720"})

_GLYPHS = {}
for _ch, _rows in _FONT.items():
    _g = np.zeros((5, 3), bool)
    for _r, _d in enumerate(_rows):
        _v = int(_d, 8)
        for _c in range(3):
            if _v & (4 >> _c):
                _g[_r, _c] = True
    _GLYPHS[_ch] = _g


def text_mask(s, scale=1):
    """A boolean mask for a string, one blank column between glyphs."""
    s = str(s).upper()
    if not s:
        return np.zeros((5 * scale, 1), bool)
    out = np.zeros((5, len(s) * 4 - 1), bool)
    for i, ch in enumerate(s):
        out[:, i * 4:i * 4 + 3] = _GLYPHS.get(ch, _GLYPHS[" "])
    if scale > 1:
        out = np.repeat(np.repeat(out, scale, 0), scale, 1)
    return out


def text_width(s, scale=1):
    return max(1, (len(str(s)) * 4 - 1) * scale)


def text_height(scale=1):
    """Measured, not assumed. A past bug in this tree clipped the bottom off
    every capital E because five rows was guessed rather than asked for."""
    return _GLYPHS[" "].shape[0] * scale


def blit_text(dst, y, x, s, rgb, scale=1):
    """Draw a string at (y, x), clipped to `dst`. Returns the width drawn."""
    m = text_mask(s, scale)
    gh, gw = m.shape
    y0, x0 = max(0, y), max(0, x)
    y1, x1 = min(dst.shape[0], y + gh), min(dst.shape[1], x + gw)
    if y1 <= y0 or x1 <= x0:
        return gw
    sub = m[y0 - y:y1 - y, x0 - x:x1 - x]
    dst[y0:y1, x0:x1][sub] = rgb
    return gw


# --------------------------------------------------------------------------
# Colour.
#
# The occupancy ramp is the one thing on this panel that has to be learned, so
# it gets a legend and it is the only diverging ramp here. It is built to a
# rule: **the healthy middle is the dimmest part of it**. A station that is
# between a fifth and four fifths full is working, nobody needs to look at it,
# and on a wall seen from across a room the quiet band is what lets the two
# alarms read instantly. Warm is empty and cold is jammed, which is the
# convention every dock-status map uses and is worth not being clever about.
# --------------------------------------------------------------------------

FILL_RAMP = [
    (0.00, (255, 122, 44)),      # dry: nothing to unlock
    (0.09, (176, 78, 36)),
    (0.20, (44, 82, 88)),        # working, and quiet about it
    (0.55, (52, 116, 118)),
    (0.78, (66, 138, 186)),
    (0.93, (120, 184, 250)),
    (1.00, (208, 226, 255)),     # jammed: nowhere to leave one
]

C_DRY = (255, 132, 52)
C_FULL = (168, 206, 255)
C_ROCK = (22, 27, 35)            # the hill's body: present, not lit
C_ROCK_EDGE = (38, 46, 58)       # one row under the surface, so it has a lip
# The altitude contours. Dimmer than the rock on purpose: above the ridge they
# are a hint about height, and below it they are supposed to be buried. A rule
# brighter than the hill it crosses turns the body of the hill into a grid.
C_RULE = (16, 20, 26)
C_MIST = (54, 76, 102)           # loose ebikes, stippled
C_LOOSE = (96, 128, 164)         # ...and the word for them in the header
C_TEXT = (198, 210, 222)
C_DIM = (84, 96, 110)
C_FAINT = (40, 48, 58)
C_GRID = (22, 28, 36)
C_GRID_HI = (44, 54, 66)
C_SEP = (14, 18, 24)
C_WARN = (255, 96, 72)
C_NOW = (255, 246, 214)
C_NOW_HALO = (58, 56, 46)
C_DOWN = (240, 150, 70)          # the fleet has run downhill
C_UP = (110, 176, 232)           # ...or been pushed back up
# ...and the shade each of them fills under itself with. A signed lane drawn as
# solid colour is thirteen rows of one hue with a serrated top edge: legible,
# but it puts more warm ink on the panel than the dry stations on the hill do,
# and those are the thing that is supposed to shout. So the area is a quarter
# brightness and the curve on top of it is not.
C_DOWN_FILL = (62, 39, 18)
C_UP_FILL = (28, 45, 60)
C_REVEAL = (222, 236, 255)

# How much of the hill's height the tallest dock gets. Less than all of it, so
# there is sky above the summit rather than a ridge welded to the top edge.
HILL_HEAD = 0.94

# The vertical scale's exponent. 0.5 is a square root; see the docstring.
HILL_GAMMA = 0.5

# Altitudes to rule and label, in metres. Chosen for the city rather than for
# arithmetic: 10 m is the flat eastern shelf, 30 m is roughly the mean dock,
# 60 m is the shoulder of the hills and 120 m is near the top of the system.
HILL_RULES = (10, 30, 60, 120)

# How fast the dry-station flags breathe, in hertz. Slow enough to read as one
# thing rather than as flicker.
FLAG_HZ = 0.55

# The lane's minimum full scale in metres. Without a floor, a night on which
# the fleet barely moves would be drawn as a dramatic sawtooth.
LANE_MIN_M = 3.0


# --------------------------------------------------------------------------
# Clock. Everything asks for `now` rather than reading the system clock, which
# is what makes a contact sheet across a whole day possible: --at moves the
# demo's idea of the present and --rate runs it fast. The same shape as
# caiso.py's and tide.py's.
# --------------------------------------------------------------------------

def parse_when(s):
    """'now', an epoch, or 'YYYY-MM-DD HH:MM' in local time."""
    if not s or s == "now":
        return None
    try:
        return float(s)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M",
                "%Y-%m-%d"):
        try:
            return time.mktime(time.strptime(s, fmt))
        except ValueError:
            continue
    raise ValueError("cannot read a time out of %r" % s)


def clock(at=None, rate=1.0):
    """A callable returning the demo's present moment in epoch seconds."""
    base = time.time() if at is None else float(at)
    start = time.monotonic()
    if at is None and rate == 1.0:
        return time.time
    return lambda: base + (time.monotonic() - start) * rate


def hhmm(epoch, ampm=True):
    """A compact local-time label: '5:47P' or '17:47'."""
    lt = time.localtime(epoch)
    if not ampm:
        return time.strftime("%H:%M", lt)
    h = lt.tm_hour % 12 or 12
    return "%d:%02d%s" % (h, lt.tm_min, "A" if lt.tm_hour < 12 else "P")


# --------------------------------------------------------------------------
# Reading what ftdata left behind.
#
# `load()` hands back a payload and an age and never raises, so everything that
# can still be wrong is wrong about *content* and is caught here. The arrays
# have to be the same length as each other and long enough to be a city; the
# history is optional and a record without one still draws a hill.
# --------------------------------------------------------------------------

MIN_STATIONS = 20


def read_bikes(cache_dir):
    """(record, age, problem). `record` is None if there is nothing drawable."""
    got = ftdata.load(PRODUCT, cache_dir)
    if got is None:
        return None, None, "no cached bay wheels record"
    payload, age = got
    try:
        elev = np.asarray(payload["elev_m"], f32)
        fill = np.asarray(payload["fill_pct"], f32) / 100.0
        docks = np.asarray(payload["free_docks"], f32)
        openm = np.asarray(payload["open"], np.int8).astype(bool)
        loose_bins = np.asarray(payload.get("loose_bins") or [], f32)
        totals = dict(payload["totals"])
        alt = dict(payload["altitude_m"])
    except Exception:                                        # noqa: BLE001
        return None, age, "bay wheels record is malformed"

    n = len(elev)
    if n < MIN_STATIONS or not (len(fill) == len(docks) == len(openm) == n):
        return None, age, "bay wheels record has no usable stations"
    # Sorted ascending is the record's contract and every index in this file
    # relies on it. Cheap to check and impossible to see if it is wrong: an
    # unsorted array draws a plausible, meaningless mountain range.
    if np.any(np.diff(elev) < -0.5):
        return None, age, "bay wheels stations are not sorted by altitude"

    hist = None
    h = payload.get("hist")
    if isinstance(h, dict) and h.get("t"):
        try:
            ht = np.asarray(h["t"], np.float64)
            hf = _series(h["fleet_m"])
            hd = _series(h["docks_m"])
            if len(ht) == len(hf) == len(hd) and len(ht):
                hist = {"t": ht, "fleet": hf, "docks": hd,
                        "bucket": float(h.get("bucket") or 600.0),
                        "hours": float(h.get("hours") or 24.0)}
        except Exception:                                    # noqa: BLE001
            hist = None

    return {"elev": elev, "fill": fill, "docks": docks, "open": openm,
            "loose_bins": loose_bins, "totals": totals, "alt": alt,
            "hist": hist, "age": age,
            "as_of": float(payload.get("as_of") or 0.0),
            "n": n}, age, None


def _series(values):
    """A list that may contain nulls, as float with NaN for 'did not happen'."""
    return np.array([np.nan if v is None else float(v) for v in values], f32)


def anomaly(rec):
    """Metres the fleet sits below (negative) or above its own docks."""
    fleet, docks = rec["alt"].get("fleet"), rec["alt"].get("docks")
    if fleet is None or docks is None:
        return None
    return float(fleet) - float(docks)


def trend(rec, hours=2.0):
    """Metres per hour the anomaly has moved over the last `hours`, or None.

    Two hours rather than one: the series is ten-minute buckets, the fleet
    moves a couple of metres over a whole commute, and an hour of it is inside
    the noise of a van dropping six bikes at one dock.
    """
    hist = rec["hist"]
    if hist is None or len(hist["t"]) < 3:
        return None
    a = hist["fleet"] - hist["docks"]
    ok = np.isfinite(a)
    if ok.sum() < 3:
        return None
    t, a = hist["t"][ok], a[ok]
    span = t[-1] - t[0]
    if span < 1800.0:
        return None
    t0 = t[-1] - min(hours * 3600.0, span)
    sel = t >= t0
    if sel.sum() < 2:
        return None
    dt = (t[sel][-1] - t[sel][0]) / 3600.0
    if dt <= 0:
        return None
    return float((a[sel][-1] - a[sel][0]) / dt)


# --------------------------------------------------------------------------
# Options.
# --------------------------------------------------------------------------

def add_arguments(ap):
    ap.add_argument("--cache-dir", default=None,
                    help="ftdata cache to read (default: ftdata's own)")
    ap.add_argument("--max-age", type=float, default=6 * 3600.0,
                    help="refuse a record older than this many seconds")
    ap.add_argument("--reveal", type=float, default=2.0,
                    help="seconds the hill takes to draw itself in (0 = off)")
    ap.add_argument("--sweep", type=float, default=7.0,
                    help="seconds between sheen passes (0 = off)")
    ap.add_argument("--sweep-width", type=int, default=32,
                    help="columns the sheen is wide")
    ap.add_argument("--sweep-gain", type=float, default=0.5,
                    help="how far towards white the sheen lifts what it crosses")
    ap.add_argument("--no-mist", action="store_true",
                    help="leave the loose ebikes off the hill")
    ap.add_argument("--24h", dest="h24", action="store_true", help="24 hour clock")
    ap.add_argument("--at", default="now",
                    help="pretend the present moment is this (epoch or "
                         "'YYYY-MM-DD HH:MM' local)")
    ap.add_argument("--rate", type=float, default=1.0,
                    help="displayed seconds per real second")
    ap.add_argument("--reload", type=float, default=300.0,
                    help="seconds between re-reads of the cache (0 = never)")


# --------------------------------------------------------------------------
# Layout. Four regions down a 64-row panel. What gives way first on a shorter
# one is the lane's label row, then the lane, then the header -- the hill is
# the demo and it is the last thing to go.
# --------------------------------------------------------------------------

class Layout(object):
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.th = text_height()
        self.head_h = self.th + 1 if h >= 24 else 0
        self.lane_h = 13 if h >= 52 else (7 if h >= 34 else 0)
        self.lane_label = self.th if (self.lane_h and h >= 60 and w >= 200) else 0
        self.tick_h = 1 if self.lane_h and h >= 46 else 0
        used = self.head_h + self.lane_h + self.lane_label + self.tick_h
        self.hill_y = self.head_h
        self.hill_h = max(6, h - used - (2 if self.lane_h else 0))
        # Everything below the hill, from the bottom up, so the tick row is
        # always the last row of the panel and the lane always sits on it.
        self.tick_y = h - self.tick_h if self.tick_h else h
        self.lane_y = self.tick_y - 1 - self.lane_h if self.lane_h else h
        self.label_y = self.lane_y - self.lane_label if self.lane_label else h
        self.hill_h = min(self.hill_h,
                          (self.label_y if self.lane_h else h) - self.hill_y - 1)
        self.hill_h = max(4, self.hill_h)

    @property
    def hill_bot(self):
        return self.hill_y + self.hill_h - 1

    @property
    def lane_mid(self):
        return self.lane_y + self.lane_h // 2


# --------------------------------------------------------------------------
# Baking the picture. All of this happens once per cache read.
# --------------------------------------------------------------------------

def column_slices(n, w):
    """Which stations land in which of `w` columns. Returns (start, stop).

    Rank to column, not altitude to column: 383 docks over 320 pixels is one
    or two per column with none dropped, whereas laying them out by metre would
    pile two hundred of them into the leftmost fifty pixels and leave the right
    half of the panel almost empty. The x axis is therefore "docks in order of
    height", and the ridge it draws is the elevation profile of the city's
    dock network, which is what the gridlines are labelled in.
    """
    edges = (np.arange(w + 1, dtype=np.float64) * n / w)
    start = np.floor(edges[:-1]).astype(int)
    stop = np.maximum(np.ceil(edges[1:]).astype(int), start + 1)
    return np.clip(start, 0, n - 1), np.clip(stop, 1, n)


def hill_rows(elev_col, top_m, lay):
    """Altitude in metres to a row inside the hill region."""
    frac = np.clip(elev_col / max(top_m, 1.0), 0.0, 1.0) ** HILL_GAMMA
    span = (lay.hill_h - 1) * HILL_HEAD
    return np.clip(np.round(lay.hill_bot - frac * span),
                   lay.hill_y, lay.hill_bot).astype(int)


def bake_hill(dst, lay, rec, ramp, mist=True, keep_out=None):
    """The ridge, the rock beneath it, the flags and the mist. Vectorised.

    One pass of boolean masks over the whole region rather than a loop over
    columns: three hundred and twenty iterations of Python is a tenth of a
    second on the wall's Pi even once, and this runs again on every cache read.
    Returns the ridge row per column and the (y, x) of the dry-station flags,
    which render() pulses.
    """
    w = lay.w
    n = rec["n"]
    # The sky box the headline will be written into, as one row per column: the
    # mist is not allowed above it. Suppressing the mist there rather than
    # blacking the box out afterwards is what keeps the ridge intact where the
    # two overlap -- the hill is data and the caption is not.
    keep_out = (np.full(w, -1, np.int64) if keep_out is None
                else np.asarray(keep_out, np.int64))
    elev, fill = rec["elev"], rec["fill"]
    dry = (fill <= 0.0) & rec["open"]
    jam = (rec["docks"] <= 0.0) & rec["open"]

    start, stop = column_slices(n, w)
    # Per-column aggregates without a Python loop and without np.add.at, which
    # is startlingly slow: a prefix sum differenced at the slice edges. It has
    # to be a prefix sum rather than np.add.reduceat, because the slices
    # overlap wherever a column gets fewer docks than the one before it and
    # reduceat can only sum start[i]..start[i+1].
    counts = (stop - start).astype(f32)
    top_m = float(elev[-1])
    csum = np.concatenate(([0.0], np.cumsum(elev, dtype=np.float64)))
    e_col = ((csum[stop] - csum[start]) / counts).astype(f32)
    fsum = np.concatenate(([0.0], np.cumsum(fill, dtype=np.float64)))
    f_col = ((fsum[stop] - fsum[start]) / counts).astype(f32)
    dsum = np.concatenate(([0], np.cumsum(dry.astype(np.int64))))
    dry_col = (dsum[stop] - dsum[start]) > 0
    jsum = np.concatenate(([0], np.cumsum(jam.astype(np.int64))))
    jam_col = (jsum[stop] - jsum[start]) > 0
    osum = np.concatenate(([0], np.cumsum(rec["open"].astype(np.int64))))
    shut_col = (osum[stop] - osum[start]) == 0

    ridge = hill_rows(e_col, top_m, lay)
    # Where the hill is steep a column can be five rows above its neighbour,
    # and a one-pixel-per-column ridge drawn from that is a dotted line with
    # sky showing through it. So the surface is a *band*: from the ridge row up
    # to halfway towards whichever neighbour is higher, and never less than two
    # rows thick, which is also the least that lets the occupancy colour be
    # read at all.
    prev = np.concatenate((ridge[:1], ridge[:-1]))
    nxt = np.concatenate((ridge[1:], ridge[-1:]))
    crest = np.minimum(np.minimum((ridge + prev) // 2, (ridge + nxt) // 2),
                       ridge - 1)
    crest = np.clip(crest, lay.hill_y, lay.hill_bot)

    reg = dst[lay.hill_y:lay.hill_bot + 1]
    rows = np.arange(lay.hill_h)[:, None] + lay.hill_y

    # Altitude rules, drawn first so the rock buries the parts of them that are
    # underground -- which is what makes them read as contour lines on a hill
    # rather than as a grid floating over it.
    for metres in HILL_RULES:
        if metres > top_m:
            continue
        r = int(hill_rows(np.array([metres], f32), top_m, lay)[0])
        if lay.hill_y <= r <= lay.hill_bot:
            dst[r] = np.maximum(dst[r], np.array(C_RULE, np.uint8))

    # The rock. One flat dark body with a single lighter row under the surface:
    # a gradient down the whole hill costs the same to bake but spends light on
    # the bottom of the panel, which is where the lane needs the contrast.
    body = rows > ridge[None, :]
    reg[body] = C_ROCK
    lip = rows == (ridge + 1)[None, :]
    reg[lip] = C_ROCK_EDGE

    # The mist: loose ebikes, binned by the altitude of their nearest dock and
    # stippled on a checkerboard so it reads as haze rather than as a second
    # chart. Drawn before the ridge so a thick bin never eats the surface.
    if mist and len(rec["loose_bins"]):
        bins = rec["loose_bins"]
        nb = len(bins)
        peak = float(bins.max())
        if peak > 0:
            height = np.clip(np.round(bins / peak * min(6, lay.hill_h // 5)),
                             0, lay.hill_h).astype(int)
            per = height[np.clip(np.arange(w) * nb // w, 0, nb - 1)]
            gap = 3                       # rows of clear sky over the crest
            hi = crest - gap
            haze = (rows <= hi[None, :]) & (rows > (hi - per)[None, :])
            # A quarter-density stipple, not a checkerboard: at a half the mist
            # reads as a solid second chart and competes with the ridge, and
            # the whole point of it is that it is a different kind of thing.
            stipple = ((rows % 2) == 0) & ((np.arange(w)[None, :] % 2) == 0)
            reg[haze & stipple & (rows > keep_out)] = C_MIST

    # The surface, coloured by how full that column's docks are.
    lut = ds.gradient(ramp, 64)
    idx = np.clip((f_col * 63.0).astype(int), 0, 63)
    surf = lut[idx]
    surf[shut_col] = C_FAINT              # out of service: no colour, no claim
    cols = np.arange(w)
    band = (rows >= crest[None, :]) & (rows <= ridge[None, :])
    reg[band] = np.broadcast_to(surf[None, :, :], reg.shape)[band]

    # Jammed docks bite down into the rock; dry docks fly a flag above the
    # ridge. Two pixels each, which at this scale is the smallest mark that
    # survives being looked at from ten feet away.
    if jam_col.any():
        jc = cols[jam_col]
        for dy in (2, 3):
            r = np.clip(ridge[jam_col] + dy, lay.hill_y, lay.hill_bot)
            dst[r, jc] = C_FULL

    flag_y, flag_x = [], []
    if dry_col.any():
        dc = cols[dry_col]
        for dy in (1, 2):
            r = np.clip(crest[dry_col] - dy, lay.hill_y, lay.hill_bot)
            flag_y.append(r)
            flag_x.append(dc)
    if flag_y:
        flags = (np.concatenate(flag_y), np.concatenate(flag_x))
        dst[flags] = C_DRY
    else:
        flags = None
    return ridge, flags


def bake_rules_labels(dst, lay, rec):
    """Metre labels on the altitude rules, hard against the right edge.

    The right edge is where the hill is steepest and the sky is thinnest, but
    it is also the only place a horizontal label does not sit on top of the
    ridge for two hundred columns.
    """
    top_m = float(rec["elev"][-1])
    for metres in HILL_RULES:
        if metres > top_m * 0.92:
            continue
        r = int(hill_rows(np.array([metres], f32), top_m, lay)[0])
        s = "%dM" % metres
        x = lay.w - text_width(s) - 1
        if r - 2 < lay.hill_y or r + 3 > lay.hill_bot:
            continue
        blit_text(dst, r - 2, x, s, C_FAINT)


LEGEND_BAR = 48


def legend_width():
    return text_width("DRY") + 3 + LEGEND_BAR + 3 + text_width("FULL")


def bake_legend(dst, lay, ramp, x, y):
    """The occupancy ramp, with both failures named. Returns the width used."""
    lut = ds.gradient(ramp, LEGEND_BAR)
    bar_x = x + text_width("DRY") + 3
    if bar_x + LEGEND_BAR + 3 + text_width("FULL") > lay.w:
        return 0
    blit_text(dst, y, x, "DRY", C_DRY)
    dst[y + 1:y + 5, bar_x:bar_x + LEGEND_BAR] = lut[None, :, :]
    blit_text(dst, y, bar_x + LEGEND_BAR + 3, "FULL", C_FULL)
    return legend_width()


# The sky box: where the headline is written, and where the mist is not
# allowed. Fixed rather than derived from the record, because the mist has to
# be suppressed while the hill is being baked and the caption is not laid out
# until afterwards -- and a box that moved with the data would mean the mist
# changed shape for a reason nobody could see.
SKY_W = 148
SKY_ROWS = 24


def sky_keep_out(lay):
    """Per column, the last row the mist may not reach above."""
    out = np.full(lay.w, -1, np.int64)
    if lay.hill_h >= 22 and lay.w >= 200:
        out[:min(SKY_W, lay.w)] = lay.hill_y + SKY_ROWS
    return out


def bake_sky(dst, lay, rec, ridge, args):
    """The headline: how far the fleet has slid, in words and in metres.

    Every line checks the ridge under it before it is drawn. The hill is the
    data and the caption is not, so on a panel shape or a day where the two
    would collide it is the caption that gives way -- silently, one line at a
    time, longest first.
    """
    a = anomaly(rec)
    if a is None or lay.hill_h < 14:
        return

    def clear(y, height, x, width):
        """Is there sky here? Two rows of margin over the ridge."""
        if y < lay.hill_y or y + height > lay.hill_bot:
            return False
        x0, x1 = max(0, x), min(lay.w, x + width)
        if x1 <= x0:
            return False
        return y + height + 1 < int(ridge[x0:x1].min())

    rate = trend(rec)
    if rate is None:
        word = "24H TRACK BUILDING"
    elif abs(rate) < 0.12:
        word = "HOLDING STEADY"
    else:
        word = "%s %.1fM/H" % ("FALLING" if rate < 0 else "RISING", abs(rate))

    down = a < 0
    colour = C_DOWN if down else C_UP
    big = "%.1fM %s" % (abs(a), "DOWNHILL" if down else "UPHILL")
    y = lay.hill_y + 1
    for scale in (2, 1):
        if clear(y, text_height(scale), 2, text_width(big, scale)):
            blit_text(dst, y, 2, big, colour, scale)
            # The trend rides on the headline's own row, bottom-aligned to it.
            # That is the highest row in the sky and therefore the widest, and
            # width is what this line needs: everything lower runs into the
            # ridge before the sentence ends.
            tx = 2 + text_width(big, scale) + 10
            ty = y + text_height(scale) - text_height()
            if clear(ty, text_height(), tx, text_width(word)):
                blit_text(dst, ty, tx, word, C_DIM)
                word = None
            y += text_height(scale) + 2
            break
    else:
        return

    said = "FLEET %s ITS DOCKS" % ("BELOW" if down else "ABOVE")
    if clear(y, text_height(), 2, text_width(said)):
        blit_text(dst, y, 2, said, C_TEXT)
        tx = 2 + text_width(said) + 8
        if word and clear(y, text_height(), tx, text_width(word)):
            blit_text(dst, y, tx, word, C_DIM)
            word = None
        y += text_height() + 2

    if clear(y, text_height(), 2, legend_width()):
        bake_legend(dst, lay, FILL_RAMP, 2, y)
        tx = 2 + legend_width() + 8
        if word and clear(y, text_height(), tx, text_width(word)):
            blit_text(dst, y, tx, word, C_DIM)
    elif word and clear(y, text_height(), 2, text_width(word)):
        blit_text(dst, y, 2, word, C_DIM)


# --------------------------------------------------------------------------
# The header. The ladder-of-shorter-forms shape caiso and tide use: the widest
# set that fits is the one drawn, because clipping the line loses whatever
# falls off the end, and what falls off the end of this one is the age.
# --------------------------------------------------------------------------

def header_fields(rec, stale, w):
    t = rec["totals"]
    age = ftdata.describe_age(rec["age"])
    right = ("STALE " + age) if stale else age
    rungs = [
        [("BAY WHEELS SF", C_DIM), ("%d BIKES" % t.get("bikes", 0), C_TEXT),
         ("%d DRY" % t.get("empty", 0), C_DRY),
         ("%d LOOSE" % t.get("loose", 0), C_LOOSE)],
        [("BAY WHEELS SF", C_DIM), ("%d BIKES" % t.get("bikes", 0), C_TEXT),
         ("%d DRY" % t.get("empty", 0), C_DRY)],
        [("%d BIKES" % t.get("bikes", 0), C_TEXT),
         ("%d DRY" % t.get("empty", 0), C_DRY)],
        [("%d BIKES" % t.get("bikes", 0), C_TEXT)],
    ]
    for fields in rungs:
        need = sum(text_width(s) for s, _c in fields) + 6 * (len(fields) - 1)
        if need + 4 + text_width(right) <= w:
            return fields, right
    return [(str(t.get("bikes", 0)), C_TEXT)], ""


def bake_header(dst, lay, rec, stale):
    fields, right = header_fields(rec, stale, lay.w)
    x = 1
    for s, c in fields:
        x += blit_text(dst, 0, x, s, c) + 6
    if right:
        blit_text(dst, 0, lay.w - text_width(right) - 1, right,
                  C_WARN if stale else C_DIM)
    dst[lay.head_h - 1] = C_SEP


# --------------------------------------------------------------------------
# The lane: the same altitude anomaly, over the last twenty-four hours.
# --------------------------------------------------------------------------

def bake_lane(dst, lay, rec, now, h24):
    """The last twenty-four hours of the same number. Returns the `now` column.

    Gaps are gaps. A missed fetch leaves a column with nothing in it rather
    than a straight line joining the two sides of it, because the whole reason
    this series exists is to show a shape, and an interpolated shape across an
    hour of downtime is an invention. On a cold cache almost the whole lane is
    gap, which is exactly what a panel that has been up for ten minutes should
    look like, and the caption says so.
    """
    if not lay.lane_h:
        return None
    hist = rec["hist"]
    w = lay.w
    span = 24 * 3600.0 if hist is None else max(3600.0, hist["hours"] * 3600.0)
    t0 = now - span
    hi_row, lo_row = lay.lane_y, lay.lane_y + lay.lane_h - 1
    now_col = min(w - 1, max(0, int((now - t0) / span * w)))

    # Time rules every three hours, midnight and noon brighter, drawn under
    # everything so the bars sit on top of them. Local time, because the
    # commute this is a picture of is on local time.
    tick = math.ceil(t0 / (3 * 3600.0)) * (3 * 3600.0)
    while tick <= now:
        c = int((tick - t0) / span * w)
        if 0 <= c < w:
            hot = time.localtime(tick).tm_hour in (0, 12)
            dst[lay.lane_y:lay.lane_y + lay.lane_h, c] = \
                C_GRID_HI if hot else C_GRID
            if lay.tick_h:
                dst[lay.tick_y, c] = C_GRID_HI if hot else C_GRID
        tick += 3 * 3600.0

    ha = ht = None
    if hist is not None and len(hist["t"]):
        a = hist["fleet"] - hist["docks"]
        ok = np.isfinite(a) & (hist["t"] >= t0) & (hist["t"] <= now + 600.0)
        if ok.any():
            ht, ha = hist["t"][ok], a[ok]

    if ha is None:
        top, bot, zero_row = LANE_MIN_M / 2, -LANE_MIN_M / 2, lay.lane_mid
    else:
        # The lane is scaled to the day it actually had, not to a symmetric
        # window around zero. In this city the fleet is below its docks almost
        # every hour of every day, so a zero-centred lane would leave half its
        # thirteen rows permanently blank and squeeze the few metres of daily
        # swing -- which is the entire signal -- into six. Zero is forced to
        # stay inside the range, so the reference line is always drawn and the
        # sign of the number is never in doubt.
        top, bot = max(float(ha.max()), 0.0), min(float(ha.min()), 0.0)
        if top - bot < LANE_MIN_M:
            centre = 0.5 * (top + bot)
            top = max(centre + LANE_MIN_M / 2, 0.0)
            bot = min(centre - LANE_MIN_M / 2, 0.0)
        pad = 0.08 * (top - bot)
        top, bot = top + pad, bot - pad

        def row_of(v):
            f = (top - np.asarray(v, f32)) / (top - bot)
            return np.clip(np.round(hi_row + f * (lay.lane_h - 1)),
                           hi_row, lo_row).astype(int)

        zero_row = int(row_of([0.0])[0])
        cols = np.clip(((ht - t0) / span * w).astype(int), 0, w - 1)
        # One ten-minute bucket is a little over two columns at this width, so
        # each sample paints the columns it spans; one column a sample would
        # draw the day as a comb.
        per_col = max(1, int(round(hist["bucket"] / span * w)))
        value = np.full(w, np.nan, f32)
        for k in range(per_col):
            value[np.clip(cols + k, 0, w - 1)] = ha
        have = np.isfinite(value)
        v = np.nan_to_num(value, nan=0.0)
        ends = row_of(v)

        rows = np.arange(lay.lane_h)[:, None] + lay.lane_y
        band = ((rows >= np.minimum(ends, zero_row)[None, :])
                & (rows <= np.maximum(ends, zero_row)[None, :])
                & have[None, :])
        reg = dst[lay.lane_y:lay.lane_y + lay.lane_h]
        reg[band & (v < 0)[None, :]] = C_DOWN_FILL
        reg[band & (v >= 0)[None, :]] = C_UP_FILL
        # The curve itself, over its own shading, so the day reads as a line
        # with an area under it rather than as a block with a ragged top.
        lit = np.arange(w)[have]
        dst[ends[have], lit] = np.where((v[have] < 0)[:, None],
                                        np.array(C_DOWN, np.uint8),
                                        np.array(C_UP, np.uint8))

    # The docks' own altitude, dotted, drawn *over* the bars rather than under
    # them: the fleet is below its docks nearly all day, so a line drawn first
    # is a line permanently buried under the very area it calibrates.
    if hi_row <= zero_row <= lo_row:
        dst[zero_row, np.arange(0, w, 2)] = C_FAINT

    if lay.lane_label:
        left = "FLEET ALTITUDE VS DOCKS  %dH" % int(round(span / 3600.0))
        blit_text(dst, lay.label_y, 2, left, C_DIM)
        right = "%+.0fM  %s" % (bot, hhmm(now, not h24))
        rx = lay.w - text_width(right) - 1
        if rx > 2 + text_width(left) + 6:
            blit_text(dst, lay.label_y, rx, right, C_DIM)
    return now_col


def draw_nodata(dst, lay, lines):
    """The honest panel. No hill, no colours, no implied occupancy."""
    dst[:] = (6, 6, 8)
    scale = 2 if lay.h >= 32 and lay.w >= 200 else 1
    y = max(0, lay.h // 2 - (len(lines) * (text_height(scale) + 2)) // 2)
    for i, (s, rgb) in enumerate(lines):
        sc = scale if i == 0 else 1
        x = max(0, (lay.w - text_width(s, sc)) // 2)
        blit_text(dst, y, x, s, rgb, sc)
        y += text_height(sc) + 3
    return dst


# --------------------------------------------------------------------------
# build()
# --------------------------------------------------------------------------

def build(args):
    w, h = args.width, args.height
    lay = Layout(w, h)
    cache = args.cache_dir
    now_of = clock(parse_when(args.at), args.rate)

    frame = np.zeros((h, w, 3), np.uint8)
    static = np.zeros((h, w, 3), np.uint8)      # the whole panel
    base = np.zeros((h, w, 3), np.uint8)        # the same, with no hill on it

    # The sheen, exactly as caiso.py does it and for the same reason: it lifts
    # what it crosses *towards white* rather than multiplying it, because the
    # dry end of the occupancy ramp is already saturated in red and multiplying
    # it clips, which made the sweep invisible over precisely the pixels it
    # exists to draw attention to. `delta` is baked with the picture, so the
    # per-frame cost is one multiply and one add over a 32-column window and no
    # mask lookup -- delta is already zero everywhere the panel is black.
    sw = max(2, int(args.sweep_width))
    ramp = 0.5 - 0.5 * np.cos(np.linspace(0, 2 * math.pi, sw, dtype=f32))
    ramp = (ramp * float(args.sweep_gain)).astype(f32)[None, :, None]
    delta = np.zeros((h, w, 3), f32)
    sheen = np.empty((h, sw, 3), f32)

    cell = {"rec": None, "problem": None, "loaded": -1e18, "stale": False,
            "flags": None, "now_col": None, "anomaly": None, "ridge": None}

    def reload_data(now):
        rec, age, problem = read_bikes(cache)
        if rec is not None and args.max_age > 0 and age is not None \
                and age > args.max_age:
            # Not merely stale. A six-hour-old occupancy map is a picture of
            # which docks were dry at lunchtime, drawn under a teatime clock,
            # and there is no way to look at it and tell.
            problem = "RECORD IS %s OLD" % ftdata.describe_age(age).upper()
            rec = None
        cell["rec"], cell["problem"], cell["loaded"] = rec, problem, now
        if rec is None:
            cell["stale"] = False
            cell["flags"] = cell["now_col"] = cell["ridge"] = None
            return

        cell["stale"] = not ftdata.is_fresh(PRODUCT, age)
        cell["anomaly"] = anomaly(rec)

        base[:] = 0
        if lay.head_h:
            bake_header(base, lay, rec, cell["stale"])
        cell["now_col"] = bake_lane(base, lay, rec, now, args.h24)

        static[:] = base
        ridge, flags = bake_hill(static, lay, rec, FILL_RAMP,
                                 mist=not args.no_mist,
                                 keep_out=sky_keep_out(lay))
        cell["ridge"], cell["flags"] = ridge, flags
        bake_rules_labels(static, lay, rec)
        bake_sky(static, lay, rec, ridge, args)

        # Everything black stays black; everything lit has somewhere to go.
        # np.multiply(..., out=) and not `*=`: an augmented assignment to a
        # name from the enclosing scope makes it local to this function, which
        # is an UnboundLocalError several lines earlier and not an obvious one.
        np.subtract(255.0, static, out=delta, dtype=f32)
        np.multiply(delta, static.max(axis=2, keepdims=True) > 0, out=delta)

    def render(t, i):
        now = now_of()
        if args.reload and now - cell["loaded"] >= args.reload:
            reload_data(now)

        if cell["rec"] is None:
            lines = [("NO BIKE DATA", C_WARN),
                     ("RUN  PYTHON3 FTDATA.PY --LOOP 600", C_TEXT)]
            if cell["problem"]:
                lines.append((str(cell["problem"]).upper()[:52], C_DIM))
            return draw_nodata(frame, lay, lines)

        frame[:] = static

        # The reveal. Two slice copies rather than a mask: the part that has
        # not arrived yet is restored from `base`, which already carries the
        # header, the lane and the time rules, so the hill grows out of a chart
        # rather than out of a black hole.
        edge = w
        if args.reveal > 0 and t < args.reveal:
            edge = int(w * (t / args.reveal))
            frame[lay.hill_y:lay.hill_bot + 1, edge:] = \
                base[lay.hill_y:lay.hill_bot + 1, edge:]
            if edge < w:
                frame[lay.hill_y:lay.hill_bot + 1, edge] = C_REVEAL
        elif args.sweep > 0:
            phase = ((t - args.reveal) % args.sweep) / args.sweep
            x0 = int(phase * (w + 2 * sw)) - sw
            a, b = max(0, x0), min(w, x0 + sw)
            if b > a:
                buf = sheen[:, :b - a]
                np.multiply(delta[:, a:b], ramp[:, a - x0:b - x0], out=buf)
                np.add(buf, static[:, a:b], out=buf)
                frame[:, a:b] = buf

        # The dry flags breathe. This is the one animation here that carries
        # meaning rather than merely proving the panel is alive: the pixels
        # that pulse are the stations that have nothing to lend anyone right
        # now, and they are written through a single fancy index rather than a
        # second baked frame, which would have cost a whole-panel copy.
        flags = cell["flags"]
        if flags is not None and edge >= w:
            k = 0.55 + 0.45 * math.sin(t * 2.0 * math.pi * FLAG_HZ)
            frame[flags] = (int(C_DRY[0] * k), int(C_DRY[1] * k),
                            int(C_DRY[2] * k))

        # The present moment, in the lane, last and over everything. Driven by
        # the segment's own `t` and not by the wall clock, so it is the same
        # animation on the wall as under a test harness rendering a hundred
        # frames in a millisecond.
        col = cell["now_col"]
        if lay.lane_h and col is not None and col < edge:
            blink = 0.55 + 0.45 * math.sin(t * 2.0)
            y0, y1 = lay.lane_y, lay.lane_y + lay.lane_h
            frame[y0:y1, col] = tuple(int(c * blink) for c in C_NOW)
            if col - 1 >= 0:
                frame[y0:y1, col - 1] = C_NOW_HALO
            py = y0 + int(((t * 1.3) % 1.0) * lay.lane_h)
            frame[max(y0, py - 1):min(y1, py + 2), col] = C_NOW
            if lay.tick_h:
                frame[lay.tick_y, col] = C_NOW
        return frame

    reload_data(now_of())
    render.state = cell               # tests reach in here; nothing else does
    render.layout = lay
    render.clock = now_of
    render.static = static
    return render


def main():
    ds.standalone(sys.modules[__name__],
                  "Bay Wheels in San Francisco, as a fluid on a hillside",
                  fps=20)


if __name__ == "__main__":
    main()
