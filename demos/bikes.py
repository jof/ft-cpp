#!/usr/bin/env python3
"""Bay Wheels, replayed: half a day of San Francisco's bikes moving, in half a minute.

A **cross-section of the city along its commute axis**. Left edge is the Ferry
Building at the foot of Market Street; right edge is twelve kilometres out, at
Ocean Beach and the county line. Height is ground altitude, so the shape is the
climb out of downtown -- sea level on the left, the ridge of Nob Hill and Buena
Vista and Twin Peaks bulging in the middle, the low sandy flats of the Sunset
falling away on the right. All 383 San Francisco docks are dots on it.

Over that landscape runs the thing the panel is for: **bikes, moving.** It is a
time lapse in the shape `goes.py` established -- one pass through the last
twelve hours at an hour every 2.3 seconds, then a hold on the newest hour so
the loop lands on now. In one rotation slot you watch a whole commute happen:
the morning pull into the financial district, the midday lull, the evening
scatter back out over the hills. Time of day is the entire story this data has,
and a panel showing only the present moment would be a nearly still picture at
nine in the evening.

Two things move over the landscape and they are **two different kinds of
claim**, drawn differently on purpose.

**The bright comets were watched happening.** GBFS rotates `bike_id` between
rentals precisely so trips cannot be reconstructed -- across two snapshots
thirty-six minutes apart not one of 634 tokens survived -- but it does not
rotate `name`, the number printed on the physical bike, of which 585 of 620
survived the same interval with a median displacement of 4.5 m. So for the
**free-floating ebikes, and only for those**, a journey is an observation: the
same bike at a new place. Those are the near-white marks with a coloured tail,
the brightest thing on the panel, and the legend says how many of the roughly
620 they are.

**The dim field is inferred, and the panel says so.** Docked bikes have no
per-bike record in GBFS at all -- station_status is counts and nothing else --
so for the other 2 700 the panel has only how the counts changed. The city is
cut into forty bands of distance from downtown; the running sum of their net
changes is the number of bikes that **had to** cross each distance, which is
arithmetic rather than a model; and each dim dot is one bike of that net
displacement carried from an emptying band to a filling one along the
least-total-displacement matching. It is not a person and it is not a trip.
The legend reads `REST FROM DOCK COUNTS - NOT TRIPS`, and the caption repeats
`NET FLOW - NOT TRIPS` beside the number, forever.

**What is deliberately not drawn.** In four minutes about nineteen ebikes
vanish from the feed and thirteen appear. Vanishing usually means docked or
picked up by a van; appearing means undocked or released. They are journey
endpoints with one end unobservable, so they are counted in the record and
never drawn -- a dot appearing out of nothing reads as a bike arriving from
somewhere, which is exactly the claim that cannot be made.

**No bike number reaches this file, the record, or the wall.** The printed
number is hashed in the fetcher the moment it is read; the tokens live in one
snapshot that is overwritten every pass; nothing in the rolling twelve hours
carries an identifier of any kind, so there is no trip history in the cache to
obtain however long it has been running. The panel shows traffic, never a bike
somebody could go and look for. See the BIKES_TRACK_* block in `ftdata.py`.

**The headline is a floor.** It counts docked bikes that changed place: the sum
of |change| over every station, halved, because a bike ridden from one dock to
another is minus one at one end and plus one at the other. Roughly 800-1000 an
hour at ten at night on the live feed, four figures in the peaks. It undercounts
two riders who cancel inside one ten-minute window and a bike left loose at the
kerb, and it cannot tell a rebalancing van from fifteen riders.

**Why this is not `winds.py` with bicycles.** `winds` is already a particle
field over a map of this bay and a second one would be the worse mistake. Wind
is smooth and continuous and is drawn as one -- a full-bleed colour wash with
streaks; bike flow is discrete, sourced and sunk at fixed points, so this is
near-black with a constellation of docks and marks that arrive in bursts.
`winds` sweeps *forward* through a forecast; this sweeps *backward* through the
observed past. `winds` colours by speed; this colours by a direction that means
something socially. And a map would be wrong anyway: San Francisco's docks are
a blob 11.9 by 12.4 km -- square -- so a map of them on a 5:1 panel spends
three hundred columns saying the city is square. Distance from downtown is the
one axis the data varies along, and it buys 37 m a column.

**Gravity is the other axis because gravity is the explanation.** Bikes roll
downhill for free and have to be pedalled, or trucked, back up. The elevation
is a committed bake, `bikes-terrain.npz`; the terrain band is the 25th to 75th
percentile of dock height in each band, drawn rather than hidden, because at
four kilometres out the city contains both the Mission flats and Buena Vista
Park and one line would be a lie about that.

**Restraint is a design decision here.** An earlier draft carried a ten-row bar
chart of the last twelve hours along the bottom. It was a good instrument and
the wrong thing to spend a sixth of the panel on -- the replay *is* the time
axis. Taking it out gave the landscape 51 rows instead of 40. What is left is a
header, one headline, one legend row and `goes`'s one-row scrub bar.

**Cold start is designed, and will be the first thing the wall shows.** The
flow needs two snapshots. A wall that booted ten minutes ago has one, draws the
city and its docks, and says `LEARNING FLOW` and when the first movement lands.
As buckets accumulate the window grows with them -- `REPLAY OF LAST 40M`, then
`2H`, then `12H` -- and the header prints `12/72` beside the age while the
window is materially short, which is `goes`'s convention and its threshold.

**Three honest failures.** Past its half-hour TTL the panel still draws with
`STALE` and the age. Past `--max-age` (six hours) it is refused: a confident
swarm of this morning under an evening clock is the one lie it could tell. No
record at all gets the same card and the command that fixes it.

**Frame budget.** Landscape, docks, header, legend and all twelve captions are
rasterised once in `build()`. `render()` copies one frame, blits the caption
box for the step, and advances the two swarms through five passes of about
fifteen numpy calls each on arrays of a few hundred. On the wall's Pi a numpy
call costs tens of microseconds whatever the array size, so the call count is
the budget and not the pixel count. Measured here over a full loop: see the
README.

Run:  python3 ftdata.py --once --only baywheels   # twice, ten minutes apart
      python3 bikes.py --host 127.0.0.1
      python3 bikes.py --no-seen --hours 6        # inferred field only
      FT_DATA_CACHE=/tmp/empty python3 bikes.py   # the no-data card
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


def blit_text(dst, y, x, s, rgb, scale=1, halo=0.0):
    """Draw a string at (y, x), clipped to `dst`. Returns the width drawn.

    `halo` darkens the one-pixel border around every stroke by that factor
    before the stroke is drawn, and it is what lets the caption sit over the
    landscape instead of being dropped whenever the two would meet. The first
    version of this panel checked the terrain under each line and gave way; on
    a city whose upper quartile of dock heights is thirty metres at four
    kilometres out, that meant the caveat vanished on exactly the days the
    panel was busiest. A halo keeps the text legible over the dim terrain band
    and leaves no rectangle behind it -- the darkening follows the letterforms,
    so on the black sky where most of it lands it is invisible.
    """
    m = text_mask(s, scale)
    gh, gw = m.shape
    y0, x0 = max(0, y), max(0, x)
    y1, x1 = min(dst.shape[0], y + gh), min(dst.shape[1], x + gw)
    if y1 <= y0 or x1 <= x0:
        return gw
    if halo > 0.0:
        # A one-pixel dilation, done as four shifted ors into a padded copy.
        # These are 5-by-40 arrays and this runs a dozen times a replay, not a
        # dozen times a frame, so the shape of it is chosen for legibility.
        pad = np.zeros((gh + 2, gw + 2), bool)
        pad[1:-1, 1:-1] = m
        grow = (pad[:-2, 1:-1] | pad[2:, 1:-1] | pad[1:-1, :-2]
                | pad[1:-1, 2:] | m)
        sub = grow[y0 - y:y1 - y, x0 - x:x1 - x]
        reg = dst[y0:y1, x0:x1]
        reg[sub] = (reg[sub].astype(f32) * (1.0 - halo)).astype(np.uint8)
    sub = m[y0 - y:y1 - y, x0 - x:x1 - x]
    dst[y0:y1, x0:x1][sub] = rgb
    return gw


# --------------------------------------------------------------------------
# Colour.
#
# Two ramps, and they are kept apart on purpose because they mean unrelated
# things. **Direction is green and violet**: green runs towards downtown,
# violet runs away from it, and both are named in a legend on the panel because
# neither is a convention anybody arrives already knowing. **Occupancy is amber
# and blue**, which every dock-status map in the world uses and which was not
# worth being clever about -- but it is now only spent on the two *failures*, a
# dock with nothing to unlock and a dock with nowhere to leave one. The healthy
# majority is a dim slate dot. The previous version of this panel put the whole
# diverging ramp on every dock; on a panel that now has a swarm moving over it,
# three hundred coloured dots competed with the thing you are meant to watch,
# and the ramp's own principle -- that the quiet middle should be the dimmest
# thing on it -- taken to its limit says to draw the middle as nearly nothing.
# --------------------------------------------------------------------------

C_IN = (128, 246, 132)           # flowing towards downtown
C_OUT = (196, 130, 255)          # ...and away from it
C_FLAT = (150, 160, 180)         # net flow too small to have a direction

C_DRY = (255, 132, 52)           # a dock with nothing to unlock
C_FULL = (150, 196, 255)         # ...and one with nowhere to leave one
C_DOCK = (58, 70, 88)            # every other dock: present, quiet
C_CLOSED = (34, 38, 46)          # out of service: no colour, no claim

C_ROCK = (16, 20, 26)            # under the lowest quartile of dock heights
C_BAND = (28, 34, 44)            # the 25th-to-75th spread of dock heights
C_RIDGE = (46, 56, 70)           # the median: the line the swarm rides
C_LOOSE = (40, 34, 58)           # undocked ebikes, stippled on the floor

# Observed journeys. A near-white head over a tail in the direction hue: the
# brightest thing on the panel, because it is the only thing on it that was
# actually watched happening.
C_SEEN = (255, 250, 232)

C_TEXT = (198, 210, 222)
C_DIM = (86, 98, 112)
C_FAINT = (44, 52, 64)
C_GRID = (24, 30, 38)
C_GRID_HI = (46, 56, 68)
C_SEP = (14, 18, 24)
C_WARN = (255, 96, 72)
C_NOW = (255, 246, 214)
C_NOW_DIM = (96, 92, 78)
C_TRACK = (62, 74, 88)          # goes.py's scrub bar, filled behind the head

# How many brightness steps a particle fades through at each end of its
# journey, and what fraction of the journey each fade takes. Step 0 is black
# and is also what an inactive particle gets, which is what makes the swarm
# branch-free: see render().
FADE_LEVELS = 8
FADE_FRAC = 0.16

# Of each replay step, the fraction spent launching particles and the fraction
# one particle spends in flight. They overlap: bikes leave over the first third
# of the step and each takes two thirds of it to arrive, so the step reads as a
# shower rather than as a parade. The discreteness is deliberate -- the data
# really does arrive in buckets, and pretending otherwise is what a smooth
# continuous field would do.
LAUNCH_FRAC = 0.34
TRAVEL_FRAC = 0.62

# How far the one-pixel border around each caption stroke is darkened. Enough
# that white text reads over the terrain band, little enough that the halo is
# invisible against the black sky where most of the caption lands.
HALO = 0.72

# Rows of sky kept above the highest dock, and rows of plinth kept below the
# lowest. The plinth is what stops downtown -- which is at three metres and is
# where most of the flow is -- being drawn on the bottom row of the map with
# nowhere for the swarm to fly.
MAP_SKY = 2
MAP_PLINTH = 6

# Where each layer flies relative to the terrain median under it, in rows.
# The observed journeys ride higher than the inferred field and are drawn over
# it, which is the point: the two are separated in space as well as in colour
# and in size, so that nobody has to read a legend to see that the bright fast
# things and the dim numerous things are different claims.
SWARM_LIFT = 2
SWARM_BAND = 5
OBS_LIFT = 11
OBS_BAND = 5

# A comet is a head and two tail samples, spaced by this much of its journey.
# Two, not four: there are a handful of these against a couple of hundred of
# the other kind, and what makes them read is brightness and size rather than
# length.
OBS_TRAIL = (0.0, 0.045, 0.09)
OBS_TRAIL_K = (1.0, 0.55, 0.28)

# The inferred field gets a shorter, dimmer trail of its own. A field of
# single pixels reads as confetti; two pixels with a gradient between them
# read as something going somewhere, and a couple of hundred of those read as
# a current. It is one extra pass over arrays of a few hundred, which is the
# cheapest thing on this panel that changes how it looks.
FLOW_TRAIL = (0.0, 0.05)
FLOW_TRAIL_K = (1.0, 0.42)

# Distances to rule and label, in kilometres. Two is roughly the edge of the
# dense downtown grid, six is the crest of the hills, ten is the avenues.
DIST_RULES = (2, 6, 10)

# The least a replay step can claim to be. Below this the interval is mostly
# quantisation -- see BIKES_FLOW_MIN_DT in ftdata.py, which refuses to compute
# it in the first place.
MIN_STEP_S = 600.0

MIN_STATIONS = 20


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


def describe_span(seconds):
    """A window length as somebody would say it: '40M', '2H', '12H'."""
    if seconds < 5400:
        return "%dM" % int(round(seconds / 60.0))
    return "%dH" % int(round(seconds / 3600.0))


# --------------------------------------------------------------------------
# Reading what ftdata left behind.
#
# `load()` hands back a payload and an age and never raises, so everything that
# can still be wrong is wrong about *content* and is caught here. The arrays
# have to be the same length as each other and long enough to be a city; the
# flow history is optional, and a record with none of it still draws a city.
# --------------------------------------------------------------------------

def read_bikes(cache_dir):
    """(record, age, problem). `record` is None if there is nothing drawable."""
    got = ftdata.load(PRODUCT, cache_dir)
    if got is None:
        return None, None, "no cached bay wheels record"
    payload, age = got
    try:
        dist = np.asarray(payload["dist_m"], f32)
        elev = np.asarray(payload["elev_m"], f32)
        fill = np.asarray(payload["fill_pct"], f32) / 100.0
        free = np.asarray(payload["free_docks"], f32)
        openm = np.asarray(payload["open"], np.int8).astype(bool)
        loose_bins = np.asarray(payload.get("loose_bins") or [], f32)
        totals = dict(payload["totals"])
        alt = dict(payload["altitude_m"])
        flow_meta = dict(payload.get("flow") or {})
    except Exception:                                        # noqa: BLE001
        return None, age, "bay wheels record is malformed"

    n = len(dist)
    if n < MIN_STATIONS or not (len(elev) == len(fill) == len(free)
                                == len(openm) == n):
        return None, age, "bay wheels record has no usable stations"
    # Sorted ascending by distance is the record's contract and every index
    # here relies on it. Cheap to check and impossible to see if it is wrong:
    # an unsorted array draws a plausible, meaningless landscape.
    if np.any(np.diff(dist) < -1.0):
        return None, age, "bay wheels stations are not sorted by distance"

    km_max = float(flow_meta.get("km") or 12.0)
    bins = int(flow_meta.get("bins") or 40)
    hist = read_hist(payload.get("hist"), bins,
                     float(flow_meta.get("track_unit_m") or 100.0))

    return {"dist": dist, "elev": elev, "fill": fill, "free": free,
            "open": openm, "loose_bins": loose_bins, "totals": totals,
            "alt": alt, "hist": hist, "age": age, "n": n,
            "km_max": km_max, "bins": bins,
            "as_of": float(payload.get("as_of") or 0.0)}, age, None


def read_hist(h, bins, unit=100.0):
    """The rolling series, or None. Rows with no difference in them are dropped.

    A bucket exists in the record whether or not a difference could be computed
    for it -- a restart, a doubled pass and a clock jump all leave one with
    nulls in it -- and this is where that distinction is turned into what the
    panel needs. `want` is how many buckets a full window would hold, kept so
    the panel can print `12/72` on a short one exactly as `goes` does.

    `trk` is the observed half and is allowed to be absent on a bucket that has
    a flow, because free_bike_status is permitted to fail on its own while
    station_status succeeds. A bucket with a flow and no tracks draws the
    inferred field and no comets, which is the truth about that ten minutes.
    """
    if not isinstance(h, dict) or not isinstance(h.get("t"), list):
        return None
    try:
        n = len(h["t"])
        cols = [h[k] for k in ("mov", "dt", "flow")]
        if not all(isinstance(c, list) and len(c) == n for c in cols):
            return None
        trk_col = h.get("trk") if isinstance(h.get("trk"), list) else None
        if trk_col is not None and len(trk_col) != n:
            trk_col = None

        def col(name):
            v = h.get(name)
            return v if isinstance(v, list) and len(v) == n else None

        seen_col, gone_col, came_col = col("seen"), col("gone"), col("came")
        t, mov, dt, flow, trk, seen, gone, came = [], [], [], [], [], [], [], []
        for i in range(n):
            f, m, d = h["flow"][i], h["mov"][i], h["dt"][i]
            if not isinstance(f, list) or len(f) != bins:
                continue
            if m is None or d is None or float(d) <= 0.0:
                continue
            t.append(float(h["t"][i]))
            mov.append(float(m))
            dt.append(float(d))
            flow.append([float(v) for v in f])
            raw = trk_col[i] if trk_col is not None else None
            if isinstance(raw, list) and len(raw) >= 2:
                # Even length only: a truncated pair is a track with one end,
                # which is the one thing this panel must not draw.
                trk.append([int(v) for v in raw[:len(raw) // 2 * 2]])
            else:
                trk.append([])
            seen.append(int(seen_col[i] or 0) if seen_col else 0)
            gone.append(int(gone_col[i] or 0) if gone_col else 0)
            came.append(int(came_col[i] or 0) if came_col else 0)

        bucket = float(h.get("bucket") or 600.0)
        hours = float(h.get("hours") or 12.0)
        want = max(1, int(round(hours * 3600.0 / max(bucket, 1.0))))
        out = {"bucket": bucket, "hours": hours, "want": want,
               "t": np.asarray(t, np.float64),
               "mov": np.asarray(mov, f32), "dt": np.asarray(dt, f32),
               "flow": (np.asarray(flow, f32) if flow
                        else np.zeros((0, bins), f32)),
               "trk": trk,
               "seen": np.asarray(seen, np.int64),
               "gone": np.asarray(gone, np.int64),
               "came": np.asarray(came, np.int64),
               "unit": float(unit)}
        return out
    except Exception:                                        # noqa: BLE001
        return None


def anomaly(rec):
    """Metres the fleet sits below (negative) or above its own docks."""
    fleet, docks = rec["alt"].get("fleet"), rec["alt"].get("docks")
    if fleet is None or docks is None:
        return None
    return float(fleet) - float(docks)


# --------------------------------------------------------------------------
# The flow, and the one inference this panel makes.
#
# Given `net`, the change in docked bikes in each of K bands of distance from
# downtown over some interval, the running sum `cumsum(net)` is exactly the
# number of bikes that crossed each band boundary heading inward. That much is
# arithmetic: whatever the inner bands gained, something had to carry.
#
# Turning a flux into *journeys* needs one more step, and it is the only place
# here where a choice is made. Sources (bands that lost bikes) are matched to
# sinks (bands that gained them) in sorted order along the axis, by cumulative
# mass -- the classic one-dimensional optimal transport coupling, which is the
# **least total displacement** consistent with the observations. It never
# claims a bike went further than it had to. Matching them at random instead
# would produce the same flux and a great deal more apparent traffic, and the
# extra would be invention.
#
# Before any of that, the imbalance is removed. The docked fleet is not closed:
# bikes leave it for the kerb as loose ebikes, for a van, for a workshop, and
# come back the same ways, so `sum(net)` is rarely zero and a flux that does
# not return to zero at the city limit is not a flow. The imbalance is spread
# over the bands in proportion to how many docks each has, which is an
# assumption, is stated here, and is small: it is a couple of bikes a band on a
# typical ten minutes.
# --------------------------------------------------------------------------

def balance(net, weight):
    """Net change per band with the docked fleet's own gain/loss removed."""
    # Float64 throughout, and not the f32 everything else here uses: the
    # correction is a small number subtracted from every band and the test
    # that the flux returns to zero at the city limit is a sum of forty of
    # them, which in single precision leaves a residual of a few hundredths
    # of a bike -- harmless on the panel and enough to fail an exact check.
    net = np.asarray(net, np.float64)
    total = float(net.sum())
    w = np.asarray(weight, np.float64)
    s = float(w.sum())
    if s <= 0:
        return net - total / max(len(net), 1)
    return net - (total * w / s)


def transport(net, count):
    """`count` unit journeys from the emptying bands to the filling ones.

    Returns (from_band, to_band) as float arrays in band units, plus the total
    mass moved. Stratified sampling of the monotone coupling: particle p takes
    the source and the sink at the same point of their cumulative mass, which
    is that coupling by definition and is two searchsorted calls rather than a
    Python merge loop.
    """
    src = np.maximum(-net, 0.0)
    snk = np.maximum(net, 0.0)
    mass = min(float(src.sum()), float(snk.sum()))
    if mass <= 0.0 or count <= 0:
        return np.zeros(0, f32), np.zeros(0, f32), 0.0
    cs = np.cumsum(src)
    ck = np.cumsum(snk)
    u = (np.arange(count, dtype=f32) + 0.5) * (mass / count)
    a = np.searchsorted(cs, u, side="right")
    b = np.searchsorted(ck, u, side="right")
    k = len(net) - 1
    return np.clip(a, 0, k).astype(f32), np.clip(b, 0, k).astype(f32), mass


def steps_of(hist, now, window, step_s):
    """Chop the usable history into replay steps. Returns a list of dicts.

    The window is anchored on the newest bucket the record actually has rather
    than on the wall clock, so a fetcher that stopped an hour ago replays the
    twelve hours it *did* see instead of eleven hours of blank followed by an
    hour of data. The strip underneath is anchored on `now`, which is what
    makes that difference visible instead of hidden.
    """
    if hist is None or not len(hist["t"]):
        return []
    t_hi = float(hist["t"].max()) + hist["bucket"]
    t_lo = max(float(hist["t"].min()), t_hi - window)
    span = max(t_hi - t_lo, step_s)
    nsteps = max(1, int(round(span / step_s)))
    step = span / nsteps
    out = []
    for i in range(nsteps):
        a = t_lo + i * step
        sel = (hist["t"] >= a) & (hist["t"] < a + step)
        out.append({"t0": a, "t1": a + step, "sel": sel,
                    "n": int(sel.sum())})
    return out


def step_flow(hist, s, weight):
    """One replay step reduced to what the swarm and the headline need.

    `rate` is docked bikes changing place per hour: `mov` counts both ends of
    every move, so it is halved, and it is divided by the seconds the
    differences actually covered rather than by the nominal step, because a
    missed pass makes those two different and the nominal one would understate.
    """
    if not s["n"]:
        return {"rate": None, "net": None, "mass": 0.0, "pull": 0.0,
                "trk": np.zeros((0, 2), f32), "seen": 0, "gone": 0, "came": 0}
    sel = s["sel"]
    secs = float(hist["dt"][sel].sum())
    mov = float(hist["mov"][sel].sum())
    net = hist["flow"][sel].sum(axis=0)
    net = balance(net, weight)
    flux = np.cumsum(net)
    mass = float(np.maximum(net, 0.0).sum())
    # The observed half: every free-ebike journey seen inside this step, in
    # metres from downtown. Concatenated across the step's buckets rather than
    # summed -- these are events, not a field, and two of them are two.
    pairs = []
    for i in np.flatnonzero(sel):
        raw = hist["trk"][i]
        for j in range(0, len(raw), 2):
            pairs.append((raw[j] * hist["unit"], raw[j + 1] * hist["unit"]))
    trk = (np.asarray(pairs, f32) if pairs else np.zeros((0, 2), f32))
    return {"rate": (mov * 0.5) * 3600.0 / secs if secs > 0 else None,
            "net": net, "flux": flux, "mass": mass, "secs": secs,
            "trk": trk,
            "seen": int(hist["seen"][sel].max()) if sel.any() else 0,
            "gone": int(hist["gone"][sel].sum()),
            "came": int(hist["came"][sel].sum()),
            # Mean bands travelled inward per bike moved. Positive is towards
            # downtown. It is a signed average and not a count, so a step where
            # as much went out as came in reads as balanced rather than as
            # whichever direction happened to have the larger total.
            "pull": float(flux.sum()) / mass if mass > 0 else 0.0}


def direction_word(pull, threshold=0.4):
    if pull > threshold:
        return "INBOUND", C_IN
    if pull < -threshold:
        return "OUTBOUND", C_OUT
    return "BALANCED", C_FLAT


# --------------------------------------------------------------------------
# Options.
# --------------------------------------------------------------------------

def add_arguments(ap):
    ap.add_argument("--cache-dir", default=None,
                    help="ftdata cache to read (default: ftdata's own)")
    ap.add_argument("--max-age", type=float, default=6 * 3600.0,
                    help="refuse a record older than this many seconds")
    ap.add_argument("--hours", type=float, default=12.0,
                    help="hours of history to replay")
    ap.add_argument("--step", type=float, default=3600.0,
                    help="seconds of city per replay step")
    ap.add_argument("--cycle", type=float, default=28.0,
                    help="seconds for one replay of the whole window")
    ap.add_argument("--hold", type=float, default=5.0,
                    help="seconds held on the newest step at the end of each "
                         "pass, so the loop lands on now")
    ap.add_argument("--no-seen", action="store_true",
                    help="leave the observed ebike journeys off")
    ap.add_argument("--particles", type=int, default=440,
                    help="most dots in flight in one step")
    ap.add_argument("--density", type=float, default=1.6,
                    help="dots per bike of net displacement")
    ap.add_argument("--no-loose", action="store_true",
                    help="leave the undocked ebikes off the floor")
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
# one is the legend row, then the strip, then the header -- the cross-section
# and its swarm are the demo and they are the last thing to go.
# --------------------------------------------------------------------------

class Layout(object):
    """Header, landscape, caption, scrub bar. In that order and no more.

    An earlier draft of this panel also carried a ten-row bar chart of the
    last twelve hours along the bottom, which was a good instrument and the
    wrong thing to spend a sixth of the panel on: the replay *is* the time
    axis, and the commute surges in the swarm itself. Taking it out gave the
    landscape 51 rows instead of 40, which is the difference between a chart
    with dots on it and a place with weather in it.
    """

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.th = text_height()
        self.head_h = self.th + 1 if h >= 24 else 0
        self.tick_h = 1 if h >= 40 else 0
        self.leg_h = self.th if (h >= 52 and w >= 220) else 0
        self.tick_y = h - self.tick_h if self.tick_h else h
        self.leg_y = self.tick_y - self.leg_h if self.leg_h else self.tick_y
        self.map_y = self.head_h
        self.map_bot = max(self.map_y + 7,
                           (self.leg_y - 2) if self.leg_h else self.tick_y - 1)
        self.map_bot = min(self.map_bot, h - 1)
        self.map_h = self.map_bot - self.map_y + 1

    @property
    def alt_bot(self):
        """The row zero metres sits on: the top of the plinth."""
        return self.map_bot - min(MAP_PLINTH, max(0, self.map_h - 6))

    @property
    def alt_top(self):
        return self.map_y + min(MAP_SKY, max(0, self.map_h - 6))


# --------------------------------------------------------------------------
# Baking the picture. All of this happens once per cache read.
# --------------------------------------------------------------------------

def band_profile(rec, bins):
    """(p25, p50, p75) of dock altitude in each distance band, in metres.

    Bands with no docks in them -- the city has a couple, over the water east
    of the Embarcadero and out past the zoo -- inherit their neighbours by
    interpolation rather than dropping to zero, which would draw a canyon where
    there is only an absence of bike racks.
    """
    idx = np.clip((rec["dist"] / max(rec["km_max"] * 1000.0, 1.0)
                   * bins).astype(int), 0, bins - 1)
    lo = np.full(bins, np.nan, f32)
    mid = np.full(bins, np.nan, f32)
    hi = np.full(bins, np.nan, f32)
    for k in range(bins):
        sel = idx == k
        if sel.any():
            e = rec["elev"][sel]
            lo[k], mid[k], hi[k] = np.percentile(e, (25.0, 50.0, 75.0))
    have = np.isfinite(mid)
    if not have.any():
        return np.zeros(bins, f32), np.zeros(bins, f32), np.zeros(bins, f32)
    xs = np.arange(bins, dtype=f32)
    out = []
    for a in (lo, mid, hi):
        out.append(np.interp(xs, xs[have], a[have]).astype(f32))
    counts = np.bincount(idx, minlength=bins).astype(f32)
    return out[0], out[1], out[2], counts


def bake_city(dst, lay, rec, prof, alt_top, args):
    """The cross-section: rock, spread band, ridge, loose bikes, docks.

    One vectorised pass over the map region rather than a loop over columns:
    three hundred and twenty iterations of Python is a tenth of a second on the
    wall's Pi even once, and this runs again on every cache read. Returns the
    ridge row per column, which is the line the swarm rides.
    """
    w = lay.w
    lo, mid, hi = prof
    bins = len(mid)

    def row_of(metres):
        f = np.clip(np.asarray(metres, f32) / max(alt_top, 1.0), 0.0, 1.0)
        return np.round(lay.alt_bot - f * (lay.alt_bot - lay.alt_top)
                        ).astype(int)

    # Band centres to columns, then one interpolation to panel resolution. The
    # bands are 300 m of city and eight columns of panel, so drawing them as
    # eight-wide steps would put a visible staircase on a landscape.
    bx = (np.arange(bins, dtype=f32) + 0.5) / bins * w
    cols = np.arange(w, dtype=f32)
    r_lo = row_of(np.interp(cols, bx, lo))
    r_mid = row_of(np.interp(cols, bx, mid))
    r_hi = row_of(np.interp(cols, bx, hi))

    reg = dst[lay.map_y:lay.map_bot + 1]
    rows = np.arange(lay.map_h)[:, None] + lay.map_y

    # Distance rules, drawn first so the rock buries what is underground --
    # which is what makes them read as marks on a landscape rather than as a
    # grid floating over it.
    for km in DIST_RULES:
        if km >= rec["km_max"]:
            continue
        c = int(km / rec["km_max"] * (w - 1))
        if 0 <= c < w:
            dst[lay.map_y:lay.map_bot + 1, c] = np.maximum(
                dst[lay.map_y:lay.map_bot + 1, c], np.array(C_GRID, np.uint8))

    reg[rows > r_lo[None, :]] = C_ROCK
    reg[(rows <= r_lo[None, :]) & (rows >= r_hi[None, :])] = C_BAND
    dst[r_mid, np.arange(w)] = C_RIDGE

    # The undocked ebikes: several hundred of them lying at the kerb, which is
    # a genuinely different population -- nobody rebalances them and they are
    # invisible to the flow, because a bike that leaves a dock and becomes one
    # of these is a departure with no arrival anywhere. They are drawn as a
    # stipple along the plinth, under the landscape rather than on it, so they
    # read as sediment and never as part of the terrain or the swarm.
    if not args.no_loose and len(rec["loose_bins"]):
        lb = rec["loose_bins"].astype(f32)
        peak = float(lb.max())
        if peak > 0 and lay.map_bot - lay.alt_bot >= 2:
            deep = lay.map_bot - lay.alt_bot
            per = np.clip(np.round(np.interp(cols, bx[:len(lb)], lb)
                                   / peak * deep), 0, deep).astype(int)
            floor = np.full(w, lay.map_bot)
            haze = ((rows > (floor - per)[None, :])
                    & (rows <= floor[None, :]))
            stip = ((rows + np.arange(w)[None, :]) % 2) == 0
            reg[haze & stip] = C_LOOSE

    # The docks. Drawn quiet first and loud last, so a dry dock is never buried
    # under the neighbour that is merely fine.
    dc = np.clip((rec["dist"] / max(rec["km_max"] * 1000.0, 1.0)
                  * (w - 1)).astype(int), 0, w - 1)
    dr = row_of(rec["elev"])
    dry = (rec["fill"] <= 0.0) & rec["open"]
    jam = (rec["free"] <= 0.0) & rec["open"]
    ok = rec["open"] & ~dry & ~jam
    dst[dr[~rec["open"]], dc[~rec["open"]]] = C_CLOSED
    dst[dr[ok], dc[ok]] = C_DOCK
    if jam.any():
        dst[dr[jam], dc[jam]] = C_FULL
    if dry.any():
        # Two pixels, which at this scale is the smallest mark that survives
        # being looked at from ten feet away, and the only place on the panel
        # where amber is spent.
        dst[dr[dry], dc[dry]] = C_DRY
        up = np.clip(dr[dry] - 1, lay.map_y, lay.map_bot)
        dst[up, dc[dry]] = C_DRY
    # The ridge is what the swarm rides; the skyline is the top of the spread
    # band, and it is what the caption has to keep clear of. Checking the
    # caption against the *median* instead would let it sit on top of the
    # quarter of the city that is higher than the median, which at four
    # kilometres out is Buena Vista Park and is a lot of pixels.
    return r_mid, r_hi


def bake_map_labels(dst, lay, rec):
    """Where the two ends of the axis are, said in words on the floor.

    Words rather than tick numbers: `DOWNTOWN` on the left and `11KM OUT` on
    the right is readable in the two seconds somebody spends walking past, and
    a row of kilometre figures is not. The rules themselves are drawn; this
    labels the ones that fit.
    """
    y = lay.map_bot - text_height() + 1
    if y < lay.map_y:
        return
    blit_text(dst, y, 2, "DOWNTOWN", C_DIM, halo=HALO)
    right = "%dKM OUT" % int(round(rec["km_max"]))
    x = lay.w - text_width(right) - 2
    if x > 2 + text_width("DOWNTOWN") + 8:
        blit_text(dst, y, x, right, C_DIM, halo=HALO)
    for km in DIST_RULES:
        if km >= rec["km_max"]:
            continue
        c = int(km / rec["km_max"] * (lay.w - 1))
        s = "%dK" % km
        if 2 + text_width("DOWNTOWN") + 6 < c < x - text_width(s) - 6:
            blit_text(dst, y, c + 2, s, C_DIM, halo=HALO)


def header_fields(rec, stale, w, have=0, want=0):
    """The header, and the one place the age of the fetch is claimed.

    A materially short window prints `12/72` in front of the age, which is
    `goes.py`'s convention to the letter including its ninety per cent
    threshold: one or two missed passes out of seventy is an ordinary day and
    is not worth a number on the wall, and a cold start is a short window by
    definition and is worth saying out loud. It is an either/or with STALE,
    also as in goes -- a stale record's age is the more urgent of the two.
    """
    t = rec["totals"]
    age = ftdata.describe_age(rec["age"])
    if stale:
        right = "STALE " + age
    elif want and have * 10 < want * 9:
        right = "%d/%d  %s" % (have, want, age)
    else:
        right = age
    rungs = [
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


def bake_header(dst, lay, rec, stale, have=0, want=0):
    fields, right = header_fields(rec, stale, lay.w, have, want)
    x = 1
    for s, c in fields:
        x += blit_text(dst, 0, x, s, c) + 6
    if right:
        blit_text(dst, 0, lay.w - text_width(right) - 1, right,
                  C_WARN if stale else C_DIM)
    dst[lay.head_h - 1] = C_SEP


def bake_legend(dst, lay, obs, loose):
    """One row: three swatches, what the bright ones are, what the rest are.

    This is the whole of the panel's apparatus and it is deliberately the
    whole of it. The brief for this rewrite was a compelling picture of real
    data rather than an instrument, so everything that could be said in a
    label and is already said by the animation has been taken out. What is
    left is the three things a viewer cannot infer by looking: which way green
    goes, which way violet goes, and that the bright marks are 620 free ebikes
    actually watched moving while the rest is arithmetic on dock counts.
    """
    if not lay.leg_h:
        return
    y = lay.leg_y
    sw = text_width("IN") + text_width("OUT") + 2 * (2 + 5 + 5)

    def swatch(x, word, rgb):
        blit_text(dst, y, x, word, rgb)
        x += text_width(word) + 2
        dst[y + 1:y + 4, x:x + 5] = rgb
        return x + 5 + 5

    # Each swatch sits beside the sentence it belongs to rather than all three
    # in a row followed by two sentences: SEEN and its coverage on the left,
    # the two directions and their caveat on the right. A viewer reads left to
    # right and gets "these bright ones are ebikes actually seen to move, the
    # rest is arithmetic on dock counts". Both halves shorten independently,
    # and neither is allowed to grow into the other -- the first draft checked
    # each against the panel width instead of against its neighbour and
    # printed `FREE EBIKIN OUT` across the middle of the row.
    left = swatch(2, "SEEN", C_SEEN)
    for said in ("%d OF %d FREE EBIKES" % (obs, loose),
                 "%d OF %d EBIKES" % (obs, loose), "%d EBIKES" % loose, ""):
        if not said:
            break
        if left + text_width(said) <= lay.w // 2:
            blit_text(dst, y, left, said, C_DIM)
            left += text_width(said)
            break
    for said in ("REST INFERRED FROM DOCK COUNTS - NOT TRIPS",
                 "REST FROM DOCK COUNTS - NOT TRIPS",
                 "FROM DOCK COUNTS - NOT TRIPS", "NOT TRIPS"):
        wid = text_width(said)
        gx = lay.w - 2 - wid - sw
        if gx >= left + 6:
            gx = swatch(gx, "IN", C_IN)
            swatch(gx, "OUT", C_OUT)
            # C_DIM and not C_FAINT: the first draft used the faintest colour
            # on the panel for this line, on the grounds that it is small
            # print. It peaks at 64 of 255, which is under what is legible
            # across a workshop. The caveat is small print that has to be
            # readable.
            blit_text(dst, y, lay.w - 2 - wid, said, C_DIM)
            break


def bake_sky(dst, top, bot, skyline, lines, clock=None):
    """The caption, in the sky over downtown, one line at a time.

    The landscape is the data and the caption is not, so on a panel shape or a
    day where the two would collide it is the caption that gives way -- quietly,
    from the bottom up. Downtown is at three metres and the sky above it is
    twenty rows deep, so the two-line caption fits with room; the check is what
    keeps that true on a 32-row panel, and on the day the operator parks the
    whole fleet on Telegraph Hill.

    The clock rides in the top right instead of under the caption because the
    sky is deepest at both ends of this axis -- downtown is at sea level and so
    is Ocean Beach -- and shallowest over the hills in the middle, which is the
    one place nothing can be written at all.

    Every line is drawn with a halo, so `skyline` is only asked whether there
    is *room* on the panel, not whether the terrain is in the way. What the
    caption still gives way to is the rock: text over a hill reads, text buried
    under one does not.
    """
    w = dst.shape[1]

    def clear(y, height, x0, x1):
        x0, x1 = max(0, x0), min(w, max(x0 + 1, x1))
        return (y >= top and y + height <= bot
                and y + height < int(skyline[x0:x1].max()))

    if clock:
        cw = text_width(clock)
        cx = w - cw - 2
        if clear(top + 1, text_height(), cx, cx + cw):
            blit_text(dst, top + 1, cx, clock, C_DIM, halo=HALO)

    y = top + 1
    for text, rgb, scale, tail in lines:
        gh = text_height(scale)
        gw = text_width(text, scale)
        if not clear(y, gh, 2, 2 + gw):
            return
        blit_text(dst, y, 2, text, rgb, scale, halo=HALO)
        if tail and 2 + gw + 6 + text_width(tail[0]) <= w:
            blit_text(dst, y + gh - text_height(), 2 + gw + 6, tail[0],
                      tail[1], halo=HALO)
        y += gh + 2


def draw_nodata(dst, lay, lines):
    """The honest panel. No landscape, no swarm, no implied movement."""
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
    window = max(3600.0, float(args.hours) * 3600.0)
    step_s = max(MIN_STEP_S, float(args.step))
    cycle = max(2.0, float(args.cycle))
    npmax = max(8, int(args.particles))

    frame = np.zeros((h, w, 3), np.uint8)
    static = np.zeros((h, w, 3), np.uint8)

    # Scratch for the swarm, allocated once at its largest and used as views.
    # Every per-particle operation is then one numpy call on a slice, and on
    # the Pi the call is most of the cost whatever its size.
    s_u = np.empty(npmax, f32)
    s_e = np.empty(npmax, f32)
    s_x = np.empty(npmax, f32)
    s_xi = np.empty(npmax, np.int32)
    s_flat = np.empty(npmax, np.int32)
    s_lvl = np.empty(npmax, np.int32)

    # The colour table: two directions by FADE_LEVELS brightnesses, with level
    # zero black in both. A particle that has not launched or has already
    # landed comes out of the envelope at level zero, so it needs no mask of
    # its own -- see render(), where its target is redirected instead.
    def levels(rgb):
        k = np.linspace(0.0, 1.0, FADE_LEVELS, dtype=f32)[:, None]
        return (np.array(rgb, f32)[None, :] * k)
    # Four blocks of FADE_LEVELS: inferred inbound, inferred outbound, observed
    # inbound, observed outbound. Index zero of every block is black, which is
    # also what an unlaunched or landed particle gets, so the whole swarm is one
    # unmasked scatter. The observed blocks are the direction hue lifted
    # two-thirds of the way to white, so a comet's tail still says which way it
    # went while its head is unmistakably a different kind of mark.
    def bright(rgb):
        return tuple(int(c + (s2 - c) * 0.62)
                     for c, s2 in zip(rgb, C_SEEN))
    palette = np.concatenate([levels(C_IN), levels(C_OUT),
                              levels(bright(C_IN)), levels(bright(C_OUT))]
                             ).clip(0, 255).astype(np.uint8)

    rec_km_max = [12.0]
    cell = {"rec": None, "problem": None, "loaded": -1e18, "stale": False,
            "steps": [], "ridge": None, "strip": None, "cur": -1,
            "chrome": None, "chrome_box": None, "span": 0.0, "cold": True,
            "skyline": None}

    def journey(out, key, x0, x1, rng, lift, band, pal_base):
        """Bake one set of journeys into the arrays render() advances.

        Shared by the two layers because they animate identically -- a launch
        delay, a straight run and a fade at each end. What differs is where
        they fly, how bright they are and how many pixels each of them is, and
        all three of those are arguments.
        """
        n = len(x0)
        if not n:
            return
        out[key] = {
            "x0": x0.astype(f32), "dx": (x1 - x0).astype(f32),
            "launch": (rng.random(n, dtype=f32) * LAUNCH_FRAC).astype(f32),
            "yj": ((rng.random(n, dtype=f32) * band).astype(np.int32) + lift),
            "ci": np.where(x1 < x0, pal_base,
                           pal_base + FADE_LEVELS).astype(np.int32),
        }

    def bake_step(hist, s, weight, ridge, rng):
        """Everything one replay step needs, computed once."""
        info = step_flow(hist, s, weight)
        out = {"rate": info["rate"], "pull": info["pull"], "n": s["n"],
               "t0": s["t0"], "t1": s["t1"], "mass": info["mass"],
               "seen": info["seen"], "gone": info["gone"], "came": info["came"],
               "tracks": len(info["trk"]), "flow": None, "obs": None}

        # The observed layer, first because it is the one that is *seen*.
        # Positions come out of the record in metres from downtown; the only
        # transform here is the same metres-to-column one the docks get.
        if len(info["trk"]):
            km = max(rec_km_max[0] * 1000.0, 1.0)
            tx = np.clip(info["trk"] / km, 0.0, 1.0) * (w - 1)
            keep = np.abs(tx[:, 1] - tx[:, 0]) >= 2.0
            journey(out, "obs", tx[keep, 0], tx[keep, 1], rng,
                    OBS_LIFT, OBS_BAND, 2 * FADE_LEVELS)

        if info["net"] is None:
            return out
        bins = len(info["net"])
        # At least one dot whenever anything moved at all. Rounding a mass of
        # 0.4 bikes to zero particles is right arithmetically and wrong on a
        # wall: it makes "almost nothing happened" and "the feed is broken"
        # look identical.
        count = int(min(npmax, round(info["mass"] * max(args.density, 0.0))))
        if info["mass"] > 0.0:
            count = max(1, count)
        a, b, mass = transport(info["net"], count)
        if not len(a):
            return out
        # A jitter inside the band, so that ten bikes leaving the same 300 m of
        # city do not leave from the same pixel. Baked, not drawn per frame, so
        # render stays a pure function of t.
        ja = rng.random(len(a), dtype=f32)
        jb = rng.random(len(b), dtype=f32)
        x0 = (a + ja) / bins * (w - 1)
        x1 = (b + jb) / bins * (w - 1)
        keep = np.abs(x1 - x0) >= 3.0
        journey(out, "flow", x0[keep], x1[keep], rng,
                SWARM_LIFT, SWARM_BAND, 0)
        return out

    def reload_data(now):
        rec, age, problem = read_bikes(cache)
        if rec is not None and args.max_age > 0 and age is not None \
                and age > args.max_age:
            # Not merely stale. A six-hour-old record is a picture of this
            # morning's flow, drawn under an evening clock, and there is no way
            # to look at it and tell.
            problem = "RECORD IS %s OLD" % ftdata.describe_age(age).upper()
            rec = None
        cell["rec"], cell["problem"], cell["loaded"] = rec, problem, now
        if rec is None:
            cell["stale"] = False
            cell["steps"], cell["ridge"] = [], None
            cell["skyline"] = None
            return

        cell["stale"] = not ftdata.is_fresh(PRODUCT, age)
        rec_km_max[0] = rec["km_max"]
        hist = rec["hist"]
        bins = rec["bins"]
        prof = band_profile(rec, bins)
        weight = prof[3]
        alt_top = max(60.0, math.ceil(float(rec["elev"].max()) / 20.0) * 20.0)

        have = len(hist["t"]) if hist is not None else 0
        want = hist["want"] if hist is not None else 0
        static[:] = 0
        if lay.head_h:
            bake_header(static, lay, rec, cell["stale"], have, want)
        ridge, skyline = bake_city(static, lay, rec, prof[:3], alt_top, args)
        bake_map_labels(static, lay, rec)
        cell["ridge"], cell["skyline"] = ridge, skyline

        raw = steps_of(hist, now, window, step_s)
        rng = np.random.default_rng(0xB1CE5)
        cell["steps"] = [bake_step(hist, s, weight, ridge, rng) for s in raw]
        cell["span"] = (raw[-1]["t1"] - raw[0]["t0"]) if raw else 0.0
        cell["cold"] = not any(s["n"] for s in raw)
        bake_legend(static, lay, sum(x["tracks"] for x in cell["steps"]),
                    int(rec["totals"].get("loose", 0)))

        # Every step's caption is rasterised here and not in the frame loop,
        # which is goes.py's rule and for goes.py's reason: a caption belongs
        # to the moment it describes, so there are only twelve of them and
        # they can all be made once. Doing it on the step change instead cost
        # a 0.3 ms spike twelve times a cycle -- nothing here, six times the
        # mean on the Pi, and exactly the kind of thing that shows up as a
        # dropped frame in a transition. Twelve boxes of 19 by 320 is 219 kB.
        bh = min(lay.map_h - 1, text_height(2) + 2 * text_height() + 6)
        cell["chrome_box"] = (lay.map_y, lay.map_y + bh)
        cell["chrome"] = [np.empty((bh, w, 3), np.uint8)
                          for _ in range(max(1, len(cell["steps"])))]

        if cell["cold"]:
            # Nothing has been differenced yet: one fetch has landed, or the
            # clock jumped, or the wall booted ten minutes ago. Say which and
            # say when the swarm arrives, rather than drawing an empty sky.
            wait = ftdata.describe_age(
                max(0.0, ftdata.PRODUCTS[PRODUCT]["interval"] - (age or 0.0)))
            cell["cold_lines"] = [
                ("LEARNING FLOW", C_TEXT, 2, None),
                ("NO MOVEMENT YET", C_DIM, 1,
                 ("NEEDS TWO FETCHES - FIRST IN %s" % wait, C_DIM)),
            ]
        for i in range(len(cell["chrome"])):
            draw_chrome(i)

    def draw_chrome(k):
        """The headline, the direction and the replay clock for step `k`."""
        y0, y1 = cell["chrome_box"]
        box = cell["chrome"][k]
        np.copyto(box, static[y0:y1])
        sky = cell["skyline"] - y0

        if cell["cold"]:
            bake_sky(box, 0, y1 - y0 - 1, sky, cell["cold_lines"],
                     "NO REPLAY YET")
            return
        s = cell["steps"][k]
        if s["rate"] is None:
            lines = [("NO DATA", C_DIM, 2, None),
                     ("THIS STEP WAS NEVER FETCHED", C_DIM, 1, None)]
        else:
            word, rgb = direction_word(s["pull"])
            lines = [("%d BIKES/H" % int(round(s["rate"])), rgb, 2, None),
                     (word, rgb, 1, ("NET FLOW - NOT TRIPS", C_DIM))]
            # The observed layer gets its own line, in its own colour, saying
            # the one thing the inferred layer cannot: these were watched.
            # `SEEN` and `MOVED` rather than `TRIPS` or `RIDES`, because what
            # was observed is a vehicle at a new place and not a journey a
            # person took.
            if s["tracks"]:
                lines.append(("%d EBIKES SEEN TO MOVE" % s["tracks"],
                              C_SEEN, 1, None))
        bake_sky(box, 0, y1 - y0 - 1, sky, lines,
                 "%s  REPLAY OF LAST %s" % (hhmm(s["t0"], not args.h24),
                                            describe_span(cell["span"])))

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

        # Where in the loop, in goes.py's shape: one pass through the window
        # at a fixed rate, then a hold on the newest step so that the loop
        # *lands on now* rather than snapping back from the middle of this
        # morning. Unlike goes the hold is not a frozen frame -- the newest
        # hour keeps replaying under it, because a still panel for five seconds
        # reads as a crash and the swarm is the demo.
        steps = cell["steps"]
        nst = max(1, len(steps))
        per = cycle / nst
        total = cycle + max(0.0, args.hold)
        u = t % total if total > 0 else 0.0
        if u >= cycle:
            k, local = nst - 1, ((u - cycle) / per) % 1.0
        else:
            x = u / per
            k = min(nst - 1, int(x))
            local = x - k
        cell["cur"] = k
        y0, y1 = cell["chrome_box"]
        frame[y0:y1] = cell["chrome"][min(k, len(cell["chrome"]) - 1)]

        mv = frame.reshape(-1, 3)

        def fly(g, shift, gain):
            """One layer, at one point of its own trail. All of the frame cost.

            `shift` steps the whole set back in its journey, which is what
            draws a comet: the same arrays sampled at three phases. `gain`
            dims the sample, so the tail is darker than the head.
            """
            n = len(g["x0"])
            u, e = s_u[:n], s_e[:n]
            # Where each particle is in its own journey, and how bright that
            # makes it. Outside [0, 1] the envelope clips to zero, which is
            # black in the palette -- so an unlaunched or landed particle needs
            # no branch, only somewhere harmless to write. See below.
            np.subtract(local - shift, g["launch"], out=u)
            np.multiply(u, f32(1.0 / TRAVEL_FRAC), out=u)
            np.subtract(1.0, u, out=e)
            np.minimum(e, u, out=e)
            np.multiply(e, f32((FADE_LEVELS - 1) * gain / FADE_FRAC), out=e)
            np.clip(e, 0.0, FADE_LEVELS - 1, out=e)
            lvl = s_lvl[:n]
            np.copyto(lvl, e, casting="unsafe")

            x = s_x[:n]
            np.clip(u, 0.0, 1.0, out=u)
            np.multiply(g["dx"], u, out=x)
            np.add(x, g["x0"], out=x)
            xi = s_xi[:n]
            np.copyto(xi, x, casting="unsafe")
            row = np.take(cell["ridge"], xi)
            np.subtract(row, g["yj"], out=row)
            np.clip(row, lay.map_y, lay.map_bot, out=row)
            flat = s_flat[:n]
            np.multiply(row, w, out=flat)
            np.add(flat, xi, out=flat)
            # Pixel zero is the top-left corner of the header, which is black
            # and stays black: the text starts at column one. Parking every
            # particle that is not in flight there is what lets the whole swarm
            # be one unmasked scatter of a colour that happens to be black.
            np.multiply(flat, lvl > 0, out=flat)
            np.add(lvl, g["ci"], out=lvl)
            mv[flat] = palette[lvl]

        s = steps[k] if steps else None
        if s is not None:
            # The inferred field first and the observed journeys over it, so
            # that where the two meet the thing that was actually watched
            # happening is the thing you see. The comet is drawn tail first for
            # the same reason.
            if s["flow"] is not None:
                for shift, gain in zip(FLOW_TRAIL[::-1], FLOW_TRAIL_K[::-1]):
                    fly(s["flow"], shift, gain)
            if s["obs"] is not None and not args.no_seen:
                for shift, gain in zip(OBS_TRAIL[::-1], OBS_TRAIL_K[::-1]):
                    fly(s["obs"], shift, gain)

        # goes.py's scrub bar, on the last row of the panel: filled behind the
        # playhead, dim in front of it, a lit head. It is the only thing left
        # on the panel that says at a glance that this is a loop of the last
        # half day and not a live feed, which is the single most important
        # thing a viewer has to understand about it -- and one row is the whole
        # cost of saying it.
        #
        # It also guarantees the panel is never still. Half the hours of a real
        # day move so few bikes that the swarm is nearly empty, and an earlier
        # draft held one identical frame for the whole of a quiet three in the
        # morning, which on a wall is indistinguishable from a crashed demo.
        if lay.tick_h:
            done = (k + local) / nst if nst > 1 else local
            head = int(np.clip(done * (w - 1), 0, w - 1))
            frame[lay.tick_y, :head + 1] = C_TRACK
            frame[lay.tick_y, head + 1:] = C_GRID
            frame[lay.tick_y, max(0, head - 1):head + 1] = C_NOW
        return frame

    reload_data(now_of())
    render.state = cell               # tests reach in here; nothing else does
    render.layout = lay
    render.clock = now_of
    render.static = static
    render.palette = palette
    return render


def main():
    ds.standalone(sys.modules[__name__],
                  "Bay Wheels: net bike flow across San Francisco, replayed",
                  fps=20)


if __name__ == "__main__":
    main()
