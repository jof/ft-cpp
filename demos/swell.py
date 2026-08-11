#!/usr/bin/env python3
"""What the Pacific is actually doing, at the speed it is doing it.

`tide.py` next door draws a prediction: a harmonic fit computed years ago that
would print the same curve for this afternoon if every buoy in the ocean were
switched off. This panel draws a **measurement**. Eighteen nautical miles west
of the Golden Gate there is a three-metre discus hull, NDBC station 46026,
which every ten minutes reports how high the sea around it is, how long between
crests, and which way they are running. The wall shows that -- and it shows it
by moving the water at the speed the water is moving.

**The wave train is the data.** The middle band is a patch of open ocean seen
from above, north up, and the crests crossing it are the swell the buoy is
measuring: at the measured heading, spaced at the wavelength the measured
period implies, and travelling at the speed that follows. Nine seconds of
dominant period means a crest crosses any given point every nine seconds, and
nine seconds is a rhythm somebody walking past can feel without reading a
single digit. That is the whole idea. Deep water gives the rest for free --
L = gT^2/2pi, c = L/T -- so a long-period groundswell draws as wide, slow,
smooth bands and a short local windsea draws as fine chop, and the difference
between the two is visible from the far end of the room.

**Two trains, not one, because that is what the sea is.** The `.spec` sidecar
carries the directional spectral summary, which splits the same sea state into
a swell part and a windsea part with a height, a period and a direction each.
Both are drawn, superposed, at their own wavelengths and their own headings. A
clean groundswell day is long smooth bands with a faint texture on them; a
blown-out day is the same bands broken up by chop running across them at
forty degrees. This is the one thing the spectral file says that the standard
file cannot, and drawing it as *interference* rather than as an energy-versus-
period plot is the reason it earns its place on a 64-row panel: a spectrum at
this size is four bars and a squint, whereas two superposed sinusoids are
simply what the water looks like. If the sidecar is missing -- not every
station publishes one -- the panel falls back to one train from the standard
file and nothing else changes.

**Height is contrast, not amplitude.** Drawing a metre and a half of swell as a
metre and a half of anything is meaningless in plan view; there is no third
dimension to put it in. So significant wave height drives how far the surface
swings through the palette: a small sea stays in the middle of the blue ramp
and reads as flat, a big one reaches the dark trough and the white foam at
either end. Four metres is full scale, which is a proper storm here and not a
number anybody will see often.

**The strip along the bottom is the trend**, twenty-four hours of significant
height as a filled area with the dominant period dotted over it, because
"1.9 m" says nothing about whether that is a swell building for tomorrow or the
end of one. Gaps in it are real: the buoy misses samples, and a line drawn
across a six-hour hole is a claim nobody measured.

**Nothing here touches the network.** `ftdata.py` fetches on a timer in a
process of its own and leaves a 2.7 kB JSON record in a cache; this reads that
and does not import a HTTP library. It has to be that way round -- the
scheduler builds the next segment on a worker thread, Python threads share the
GIL, and a `build()` blocked on a socket does not merely wait, it stops the
render loop getting the interpreter back. The buoy's file is 600 kB and the
fetcher takes the newest sixteen of them with a ranged GET; see ftdata.py.

    $ python3 ftdata.py --once --only ndbc-46026
    $ python3 swell.py --host 127.0.0.1
    $ python3 swell.py --rate 6            # a minute of ocean in ten seconds
    $ FT_DATA_CACHE=/tmp/empty python3 swell.py       # the no-data card
    $ python3 scripts/test-swell.py

**Age is part of the data, twice over.** The fetch age says whether the fetcher
is alive; the observation age says whether the *buoy* is. They are different
failures and they are shown separately, because a buoy can go quiet for a week
while the fetcher happily downloads its silence every ten minutes -- station
46237 on the San Francisco bar was doing exactly that while this was written.
Past an hour the observation age is called out in warning colour; past half a
day the wave train is not drawn at all, because animating a stale sea state at
a rhythm the ocean is no longer keeping is the one lie this panel could tell.

**Frame budget.** Everything is baked in `build()`: the header, the trend
strip, the compass and the two phase images. A frame is two table lookups for
the wave field, one palette lookup, one scatter for the overlay and the adds
between them -- seven numpy calls, none of which allocate, and the header and
strip are never touched at all because they live in the same buffer and do not
change between fetches. Numpy costs tens of microseconds a call on the wall's
Pi whatever the array size, so the call count is the budget and not the pixel
count.
"""

import math
import os
import sys
import time

import numpy as np

import defcon
import demoscene as ds
import ftdata

f32 = np.float32

STATION = "46026"                       # 18 nm west of the Golden Gate
PRODUCT = "ndbc-"

M_FT = 3.28084
MS_KT = 1.94384
G = 9.80665

# Deep-water dispersion: L = g T^2 / 2pi. The buoy sits in 1400 m of water and
# the panel is a patch of open ocean, so the deep-water form is the right one --
# nothing here is in water shallow enough to shoal.
DEEP = G / (2.0 * math.pi)              # 1.5613 m per second squared

# Full scale for the surface swing. Four metres significant is a proper storm
# off this coast; anything above it clips rather than rescaling, because a
# panel whose contrast is normalised to the day cannot be compared with
# yesterday's, which is most of what somebody wants from it.
HS_FULL = 3.0

# Phase resolution of the baked sine table. A wavelength is a hundred-odd
# pixels wide on screen, so a thousand samples across it is a fortieth of a
# pixel of quantisation -- well under what a slow-moving crest needs to look
# like it is gliding rather than stepping.
NPHASE = 1024

# How many swell wavelengths to fit across the panel. The alternative -- a
# fixed patch of ocean in metres -- draws a twenty-second groundswell as one
# vast crest filling the whole wall and pulsing, which is honest and useless.
# Fixing the *number* of wavelengths instead keeps the picture legible at every
# period and keeps the thing that matters exactly right: at n wavelengths
# across, a crest still passes any given point once every T seconds. The scale
# bar in the corner is what makes the zoom honest.
WAVES_ACROSS = 2.6

# Beyond this the observation is called out in warning colour; beyond DEAD the
# wave train is not drawn at all. Ninety minutes rather than an hour because
# NDBC's own pipeline is routinely half an hour behind the buoy -- the file
# 46026 serves has been observed forty minutes stale with nothing wrong at
# either end -- and a panel that cries stale every afternoon is a panel nobody
# believes on the day it matters.
OBS_WARN = 5400.0
OBS_DEAD = 12 * 3600.0

# How long a hole in the trend to bridge, in samples. The buoy publishes wave
# height on a ten-minute grid and the dominant period on a thirty-minute one,
# both with drops; joining across half an hour of a quantity that changes over
# hours is fair, and joining across six is the lie this bound exists to stop.
GAP_FILL = 3

C_TEXT = (198, 210, 222)
C_DIM = (86, 98, 112)
C_WARN = (255, 96, 72)
C_SWELL = (120, 208, 255)               # the cold blue everything wet is drawn in
C_WSEA = (255, 186, 96)                 # windsea and period: warm, so it separates
C_HT = (96, 190, 240)
C_HT_FILL = (20, 68, 108)
C_GRID = (26, 32, 42)
C_AXIS = (44, 52, 64)
C_INK = (236, 246, 255)                 # overlay marks on the water
C_INK_DIM = (128, 156, 180)             # the scale bar, which is reference
C_SHADOW = (0, 4, 10)                   # their halo, so they read over foam

# The sea ramp. Trough to crest: near-black, deep blue, the blue an LED panel
# is actually good at, then a hard turn to foam white in the last eighth. The
# turn is late on purpose -- foam is what a breaking crest looks like and most
# of the surface is not breaking, so a ramp that whitens gradually reads as fog
# rather than as water.
SEA_RAMP = [(0.00, (2, 5, 14)), (0.22, (5, 18, 44)), (0.45, (9, 44, 86)),
            (0.68, (18, 84, 140)), (0.84, (46, 140, 190)),
            (0.93, (110, 194, 224)), (1.00, (222, 242, 250))]

# --------------------------------------------------------------------------
# Type. defcon.py's 3x5 font, the same one caiso, propagation, sort and tide
# draw with: five rows a glyph, each row an octal digit whose three bits are
# the three columns. Anything from a real typeface is mush at five pixels, and
# the Pi does not have the same faces installed as the machine this was written
# on. The height is measured off the mask everywhere below rather than assumed
# -- a five that is written down twice is a five that gets changed once.
# --------------------------------------------------------------------------

_GLYPHS = {}
for _ch, _rows in defcon._FONT.items():
    _g = np.zeros((5, 3), bool)
    for _r, _d in enumerate(_rows):
        _v = int(_d, 8)
        for _c in range(3):
            if _v & (4 >> _c):
                _g[_r, _c] = True
    _GLYPHS[_ch] = _g

GLYPH_H = _GLYPHS[" "].shape[0]
GLYPH_W = _GLYPHS[" "].shape[1]
LINE_H = GLYPH_H + 1                    # one blank row between stacked lines


def text_mask(s, scale=1):
    """A boolean mask for a string, one blank column between glyphs."""
    s = str(s).upper()
    if not s:
        return np.zeros((GLYPH_H * scale, 1), bool)
    out = np.zeros((GLYPH_H, len(s) * (GLYPH_W + 1) - 1), bool)
    for i, ch in enumerate(s):
        out[:, i * (GLYPH_W + 1):i * (GLYPH_W + 1) + GLYPH_W] = \
            _GLYPHS.get(ch, _GLYPHS[" "])
    if scale > 1:
        out = np.repeat(np.repeat(out, scale, 0), scale, 1)
    return out


def text_width(s, scale=1):
    n = len(str(s))
    return max(1, (n * (GLYPH_W + 1) - 1) * scale) if n else 1


def text_height(scale=1):
    return GLYPH_H * scale


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
# Units and words.
# --------------------------------------------------------------------------

POINTS = ("N NNE NE ENE E ESE SE SSE S SSW SW WSW W WNW NW NNW").split()


def compass(deg):
    """A 16-point compass name for a bearing, or '' for nothing."""
    if deg is None:
        return ""
    return POINTS[int((float(deg) % 360.0) / 22.5 + 0.5) % 16]


def feet(metres, digits=None):
    """A wave height in feet, the way a surf report says it."""
    ft = float(metres) * M_FT
    if digits is None:
        digits = 1 if ft < 10 else 0
    return "%.*fFT" % (digits, ft)


def wavelength(period):
    return DEEP * float(period) * float(period)


# --------------------------------------------------------------------------
# Reading what ftdata left behind.
#
# `load()` hands back a payload and an age and never raises. What can still be
# wrong after that is wrong about *content*, and there are three separate ways
# for that to happen here, which the demo has to tell apart: no record at all,
# a record whose fetch is old (the fetcher is down), and a record that fetched
# fine but whose newest observation is old (the buoy is down). The last one is
# not hypothetical -- see the module docstring.
# --------------------------------------------------------------------------

def _num(payload, key):
    v = payload.get(key)
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _train(payload, key):
    """A wave train out of the record: height, period, direction, or None."""
    d = payload.get(key)
    if not isinstance(d, dict):
        return None
    try:
        h, p = float(d["h"]), float(d["p"])
    except (KeyError, TypeError, ValueError):
        return None
    if p <= 0.5 or h < 0.0:
        return None
    deg = d.get("dir")
    return {"h": h, "p": p, "dir": None if deg is None else float(deg),
            "pt": str(d.get("pt") or compass(deg)),
            "t": float(d.get("t") or 0.0)}


def bridge(v, span=GAP_FILL):
    """Fill holes up to `span` samples wide from the nearer neighbour.

    The buoy drops samples constantly -- the day this was written it reported a
    wave height on 87 of 156 ten-minute slots and a dominant period on 42 --
    and drawn faithfully that is not a trend line, it is a comb, which reads as
    a barcode rather than as a sea building. So short holes are bridged and
    long ones are left as holes, which keeps the one thing that matters: an
    outage still looks like an outage.
    """
    out = v.copy()
    for d in range(1, int(span) + 1):
        for shift in (d, -d):
            need = np.isnan(out)
            if not need.any():
                return out
            src = np.roll(v, shift)
            # Wrapped ends are not neighbours, they are the other end of the
            # day; a value from yesterday teatime under this morning's hole is
            # exactly the kind of quiet nonsense this file is trying to avoid.
            if shift > 0:
                src[:shift] = np.nan
            else:
                src[shift:] = np.nan
            out[need] = src[need]
    return out


def _series(hist, key, n):
    """One history column as float32 with NaN for the holes, or None."""
    if not isinstance(hist, dict):
        return None
    raw = hist.get(key)
    if not raw:
        return None
    # A list with None in it will not go through np.asarray as a float array in
    # one step on every numpy, so the substitution is explicit.
    out = np.full(n, np.nan, f32)
    for i, v in enumerate(raw[:n]):
        if v is not None:
            out[i] = v
    return out


def read_buoy(cache_dir, station):
    """(state, error). `state` is everything the drawing needs, or None."""
    got = ftdata.load(PRODUCT + station, cache_dir)
    if got is None:
        return None, "no cached record for buoy %s" % station
    payload, age = got
    if not isinstance(payload, dict):
        return None, "buoy record is malformed"

    hs = _num(payload, "wvht")
    dpd = _num(payload, "dpd")
    mwd = _num(payload, "mwd")
    obs_t = _num(payload, "wvht_t") or 0.0

    swell = _train(payload, "swell")
    windsea = _train(payload, "windsea")
    # The standard file's own numbers are the fallback for the swell train, and
    # they are also the sanity floor: if the spectral file says nothing, the
    # dominant period and mean direction still describe a wave train, just one
    # with the chop folded into it.
    if swell is None and hs is not None and dpd:
        swell = {"h": hs, "p": dpd, "dir": mwd, "pt": compass(mwd),
                 "t": obs_t}
    if hs is None and swell is not None:
        hs = swell["h"]

    hist = payload.get("hist") or {}
    n = int(hist.get("n") or 0)
    state = {
        "station": str(payload.get("station", station)),
        "name": str(payload.get("name") or station).upper(),
        "hs": hs, "dpd": dpd, "mwd": mwd, "apd": _num(payload, "apd"),
        "swell": swell, "windsea": windsea,
        "steepness": str(payload.get("steepness") or ""),
        "wtmp": _num(payload, "wtmp"), "atmp": _num(payload, "atmp"),
        "wspd": _num(payload, "wspd"), "wdir": _num(payload, "wdir"),
        "gst": _num(payload, "gst"),
        "obs_t": obs_t,
        "obs_age": max(0.0, time.time() - obs_t) if obs_t else None,
        "age": age,
        # Not `ftdata.is_fresh()`: that answers "yes" for a product it has never
        # heard of, and a station only registered through FT_BUOYS in the
        # fetcher's environment is exactly that here. The TTL is the buoy's
        # either way, so it is taken from the module rather than the registry.
        "fresh": age <= (ftdata.ttl_for(PRODUCT + station) or ftdata.NDBC_TTL),
        "t0": float(hist.get("t0") or 0.0),
        "step": float(hist.get("step") or 600.0),
        "hs_hist": _series(hist, "wvht", n),
        "dpd_hist": _series(hist, "dpd", n),
    }
    if state["hs"] is None or state["swell"] is None:
        return state, "buoy %s reports no wave height" % station
    return state, None


def verdict(state):
    """One word for the shape of the sea: is this swell, or is it slop?

    The ratio of windsea height to swell height is the whole of it. Under a
    half and the surface is a groundswell with a texture on it; over one and
    whatever is arriving from far away is buried under what the local wind is
    making. It is the single most useful thing the spectral file says, and it
    is the reason that file is fetched at all.
    """
    sw, ws = state["swell"], state["windsea"]
    if sw is None or ws is None or sw["h"] <= 0.05:
        return "", C_DIM
    r = ws["h"] / sw["h"]
    if r < 0.5:
        return "CLEAN", C_SWELL
    if r < 1.0:
        return "MIXED", C_TEXT
    return "CHOPPY", C_WSEA


# --------------------------------------------------------------------------
# Layout. Three bands: the numbers, the water, the day.
# --------------------------------------------------------------------------

class Layout(object):
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.head_h = 2 * LINE_H if h >= 44 else (LINE_H if h >= 24 else 0)
        # The strip gets a third, bounded: under about fourteen rows there is
        # no room for a plot and a row of hour labels under it, and past
        # twenty-four rows it starts stealing from the only part of the panel
        # that moves.
        strip = int(round(h * 0.33))
        strip = max(0, min(24, min(strip, h - self.head_h - 10)))
        self.strip_h = strip if strip >= LINE_H + 8 else 0
        self.head_y = 0
        self.sea_y = self.head_h
        self.sea_h = h - self.head_h - self.strip_h
        self.strip_y = h - self.strip_h


# --------------------------------------------------------------------------
# The header: three big numbers and the small print beside them.
# --------------------------------------------------------------------------

def _fit_columns(dst, x0, x1, cols, gap=6):
    """Lay out two-line columns left to right, dropping what does not fit.

    A ladder of shorter forms per column, as tide.py's header does, rather than
    clipping: what falls off the right of this line is the part that says how
    old the data is, and that is the last thing that should go quietly missing.
    """
    x = x0
    for lines in cols:
        need = max(text_width(s) for s, _ in lines)
        if x + need > x1:
            continue
        for i, (s, rgb) in enumerate(lines):
            if s:
                blit_text(dst, i * LINE_H, x, s, rgb)
        x += need + gap
    return x


def draw_header(dst, lay, state):
    """The numbers, biggest first: height, period, where from."""
    dst[:] = 0
    if lay.head_h <= 0:
        return
    w = lay.w
    scale = 2 if lay.head_h >= 2 * LINE_H and w >= 200 else 1
    big_y = max(0, (lay.head_h - text_height(scale)) // 2)
    sw = state["swell"]

    # The three big numbers all come from the standard file and describe the
    # sea as a whole: significant height, dominant period, and the direction at
    # that period. Not the spectral swell's own figures, tempting as it is on a
    # panel called swell -- they describe one component, the trend strip below
    # plots the dominant period, and a headline that disagreed with the axis
    # under it would be the panel arguing with itself. The split is in the
    # small print, where it belongs, and the verdict word says which half won.
    period = state["dpd"] or sw["p"]
    heading = state["mwd"] if state["mwd"] is not None else sw["dir"]
    x = 1
    for s, rgb in (
            (feet(state["hs"]), C_TEXT),
            ("%dS" % round(period), C_TEXT),
            (compass(heading) or "--", C_SWELL)):
        x += blit_text(dst, big_y, x, s, rgb, scale) + 4 * scale

    # The right-hand block is reserved before anything else is laid out: it
    # carries the two ages, and they are what makes the rest believable.
    obs = state["obs_age"]
    rights = []
    if obs is not None:
        warn = obs >= OBS_WARN
        rights.append(("OBS %s" % ftdata.describe_age(obs),
                       C_WARN if warn else C_DIM))
    rights.append(("STALE %s" % ftdata.describe_age(state["age"])
                   if not state["fresh"] else state["station"],
                   C_WARN if not state["fresh"] else C_DIM))
    rw = max(text_width(s) for s, _ in rights)
    rx = w - rw - 1
    for i, (s, rgb) in enumerate(rights):
        blit_text(dst, i * LINE_H, w - text_width(s) - 1, s, rgb)

    word, wcol = verdict(state)
    ws = state["windsea"]
    # Metres beside the feet, because a surf report is in feet and everything
    # else in the building is in metres, and the bearing in degrees under the
    # compass point -- 315 and NW are the same fact at two resolutions and the
    # panel should not have to choose.
    cols = [[("%.1fM" % state["hs"], C_DIM),
             ("FROM %03d" % heading if heading is not None else "FROM ---",
              C_DIM)]]
    if ws is not None:
        # The two halves of the sea, one per line and in the same shape, so the
        # comparison is a glance down the column rather than a reading.
        cols.append([
            ("SWL %s %dS %s" % (feet(sw["h"]), round(sw["p"]), sw["pt"]),
             C_SWELL),
            ("SEA %s %dS %s" % (feet(ws["h"]), round(ws["p"]), ws["pt"]),
             C_WSEA)])
        if word:
            cols.append([(word, wcol), ("SWELL", wcol)])
    elif state["steepness"]:
        cols.append([(state["steepness"], C_DIM), ("SEA", C_DIM)])
    if state["wtmp"] is not None or state["wspd"] is not None:
        wt = ("WATER %.0fF" % (state["wtmp"] * 9.0 / 5.0 + 32.0)
              if state["wtmp"] is not None else "")
        wd = ("WIND %s %.0fKT" % (compass(state["wdir"]) or "?",
                                  state["wspd"] * MS_KT)
              if state["wspd"] is not None else "")
        cols.append([(wt, C_DIM), (wd, C_DIM)])
    _fit_columns(dst, x + 2, rx - 4, cols)


# --------------------------------------------------------------------------
# The trend strip: a day of significant height, with the period over it.
# --------------------------------------------------------------------------

def draw_strip(dst, lay, state, hours):
    """Twenty-four hours of sea state, newest at the right edge.

    The right edge is the newest *sample*, not the wall clock: if the buoy went
    quiet at breakfast the trace stops where the data stopped and the gap is
    visible, which is the whole reason a strip is worth having next to a
    headline number.
    """
    dst[:] = 0
    if lay.strip_h <= 0:
        return None
    h, w = dst.shape[:2]
    hs = state["hs_hist"]
    if hs is None or not np.isfinite(hs).any():
        blit_text(dst, max(0, (h - GLYPH_H) // 2), 1, "NO TREND YET", C_DIM)
        return None

    hs = bridge(hs)
    n = len(hs)
    step = state["step"] or 600.0
    span = hours * 3600.0
    t1 = state["t0"] + (n - 1) * step
    t0 = t1 - span

    plot_t = 1
    plot_b = h - LINE_H - 3
    axis_y = h - LINE_H - 2
    label_y = h - LINE_H

    # Column -> sample. Nearest, not interpolated: the samples are ten minutes
    # apart and the panel has three columns per sample, so interpolation would
    # invent a slope inside every hole rather than showing it.
    tc = t0 + (np.arange(w, dtype=np.float64) + 0.5) * span / w
    idx = np.clip(np.round((tc - state["t0"]) / step), 0, n - 1).astype(np.intp)
    # A column whose nearest sample is more than one step away is off the end
    # of the record, not a hole in it.
    off = np.abs(state["t0"] + idx * step - tc) > step
    hv = hs[idx]
    hv[off] = np.nan

    hmax = max(1.0, float(np.nanmax(hs)) * 1.15)
    good = np.isfinite(hv)
    rows = np.where(good, plot_b - hv / hmax * (plot_b - plot_t), plot_b)
    ri = np.clip(np.round(rows), plot_t, plot_b).astype(np.intp)

    yy = np.arange(h)[:, None]
    fill = (yy >= ri[None, :]) & (yy <= plot_b) & good[None, :]
    dst[fill] = C_HT_FILL
    dst[ri[good], np.flatnonzero(good)] = C_HT

    # Six-hourly gridlines behind nothing -- they are drawn first so the trace
    # covers them -- and the hour labels under the axis.
    # Six-hourly, and never at the very left edge: the label there would sit on
    # top of the station name, and "-24H" is the one tick the axis does not
    # need -- it is the end of the axis and the axis is a fixed length.
    name_w = text_width(state["name"][:12]) + 3
    for k in range(1, int(hours // 6) + 1):
        c = int(round(w * (1.0 - k * 6.0 / hours)))
        lab = "-%dH" % (k * 6)
        if not (0 <= c < w):
            continue
        col = dst[plot_t:plot_b + 1, c]
        np.maximum(col, np.array(C_GRID, np.uint8), out=col)
        lx = max(0, c - text_width(lab) // 2)
        if lx >= name_w:
            blit_text(dst, label_y, lx, lab, C_DIM)
    dst[axis_y, :] = C_AXIS

    # The period, dotted over the fill on its own fixed scale. Fixed and not
    # fitted to the day: the point of it is that fourteen seconds means the same
    # thing on the panel this afternoon as it did last week.
    pv = state["dpd_hist"]
    pmin, pmax = 4.0, 20.0
    if pv is not None:
        p = bridge(pv)[idx]
        p[off] = np.nan
        ok = np.isfinite(p)
        if ok.any():
            # Only the valid columns go through the arithmetic: clip() of a NaN
            # is a NaN and casting one to an index is a warning on numpy 2 and
            # a garbage row number on any numpy.
            pv_ok = np.clip(p[ok], pmin, pmax)
            pr = plot_b - (pv_ok - pmin) / (pmax - pmin) * (plot_b - plot_t)
            pri = np.clip(np.round(pr), plot_t, plot_b).astype(np.intp)
            dst[pri, np.flatnonzero(ok)] = C_WSEA

    blit_text(dst, label_y, 1, state["name"][:12], C_DIM)
    blit_text(dst, plot_t, 1, "%.0fFT" % (hmax * M_FT), C_HT)
    top = "%dS" % int(pmax)
    blit_text(dst, plot_t, w - text_width(top) - 3, top, C_WSEA)
    now = "NOW"
    blit_text(dst, label_y, w - text_width(now) - 1, now, C_TEXT)
    dst[plot_t:plot_b + 1, w - 1] = C_TEXT
    return hmax


# --------------------------------------------------------------------------
# The water. One index image per wave train, one palette lookup, and the marks
# on top.
#
# The whole surface is a sum of two travelling sinusoids, and both of them are
# functions of one number per pixel: the distance along the direction that
# train is travelling. So that distance is baked once, as an integer phase
# image, and a frame is `take(sine_table, phase + offset)` twice, an add, and
# `take(palette, height)`. Nothing is computed per pixel per frame and nothing
# is allocated.
#
# The tables are two wavelengths long and the offsets are kept inside one, so
# the lookups can run in 'clip' mode: a modulo over twenty thousand indices
# every frame to save four kilobytes of table would be a poor trade.
# --------------------------------------------------------------------------

def phase_image(hgt, wid, mpp, period, from_deg, nphase=NPHASE):
    """Integer phase, in table steps, for a train arriving from `from_deg`.

    Screen is north-up: +x east, +y south. A wave arriving *from* a bearing
    travels towards the reciprocal, so the direction of travel as a unit vector
    in (east, north) is (sin b, cos b) with b = from_deg + 180.
    """
    b = math.radians((float(from_deg or 0.0) + 180.0) % 360.0)
    ex, ny = math.sin(b), math.cos(b)
    lam = max(1e-3, wavelength(period))
    kx = nphase * mpp * ex / lam
    ky = -nphase * mpp * ny / lam           # screen y runs south
    x = np.arange(wid, dtype=np.float64) * kx
    y = np.arange(hgt, dtype=np.float64) * ky
    p = np.round(y[:, None] + x[None, :]).astype(np.int64) % nphase
    return np.ascontiguousarray(p, np.intp)


def sine_table(amplitude, centre=0, nphase=NPHASE):
    """One cycle of a sine, tiled twice, as int16 -- see the section comment."""
    a = np.sin(np.arange(nphase, dtype=np.float64) * (2.0 * math.pi / nphase))
    one = np.round(a * amplitude + centre).astype(np.int16)
    return np.concatenate([one, one])


def _line(mask, y0, x0, y1, x1, width=0.9):
    """Stamp a segment into a boolean mask. Baked once; not a hot path."""
    h, w = mask.shape
    lo_y = max(0, int(min(y0, y1) - width - 1))
    hi_y = min(h, int(max(y0, y1) + width + 2))
    lo_x = max(0, int(min(x0, x1) - width - 1))
    hi_x = min(w, int(max(x0, x1) + width + 2))
    if hi_y <= lo_y or hi_x <= lo_x:
        return
    py = np.arange(lo_y, hi_y, dtype=f32)[:, None] + (0.5 - y0)
    px = np.arange(lo_x, hi_x, dtype=f32)[None, :] + (0.5 - x0)
    dy, dx = y1 - y0, x1 - x0
    ll = max(dy * dy + dx * dx, 1e-6)
    tp = np.clip((py * dy + px * dx) / ll, 0.0, 1.0)
    d = np.hypot(py - tp * dy, px - tp * dx)
    mask[lo_y:hi_y, lo_x:hi_x] |= d <= width


def _arrow(mask, y, x, deg, length, width=0.9):
    """An arrow from (y,x) pointing along a compass bearing."""
    b = math.radians(float(deg) % 360.0)
    dx, dy = math.sin(b), -math.cos(b)
    hy, hx = y + dy * length, x + dx * length
    _line(mask, y, x, hy, hx, width)
    bl = max(3.0, length * 0.34)
    for s in (1, -1):
        _line(mask, hy, hx, hy - dy * bl + s * dx * bl * 0.6,
              hx - dx * bl - s * dy * bl * 0.6, width)


def build_overlay(hgt, wid, state, mpp):
    """The marks that go on the water: north, the heading, and the scale.

    Returned as flat pixel indices and colours rather than as an image, because
    that makes drawing them one scatter into the frame instead of a blend over
    the whole band -- and, unlike a maximum, it can draw a dark halo, which is
    the only thing that keeps a caption legible over foam.
    """
    ink = np.zeros((hgt, wid), bool)
    faint = np.zeros((hgt, wid), bool)
    sw = state["swell"]

    if hgt >= 16:
        # North, so the heading means something. Tail at the bottom: the arrow
        # points the way the label says.
        _arrow(ink, 10, 5, 0.0, 8.0)
        ink |= _pad_mask(text_mask("N"), hgt, wid, 3, 9)

    # Which way the water is going. The header says where it is coming from --
    # that is the convention every forecast uses -- so this arrow is the
    # reciprocal, and the two together are what makes the animation readable as
    # a direction rather than as drift.
    if sw["dir"] is not None and hgt >= 12:
        ln = max(6.0, min(18.0, hgt * 0.4))
        cy, cx = hgt * 0.5, wid - ln - 12
        # Thick, because it has to be legible over foam as well as over a
        # trough, and the dark halo below is only a pixel wide.
        _arrow(ink, cy, cx, (sw["dir"] + 180.0) % 360.0, ln, 1.4)

    # The scale bar is one swell wavelength, labelled. Without it the panel
    # implies a zoom it does not have; with it, "the crests are this far apart
    # and that is 126 metres" is readable off the wall.
    lam = wavelength(sw["p"])
    lpx = lam / mpp
    if hgt >= 20 and 8 <= lpx <= wid - 10:
        y = hgt - GLYPH_H - 4
        _line(faint, y, 4, y, 4 + lpx, 0.6)
        _line(faint, y - 2, 4, y + 2, 4, 0.6)
        _line(faint, y - 2, 4 + lpx, y + 2, 4 + lpx, 0.6)
        lab = "%dM" % round(lam)
        faint |= _pad_mask(text_mask(lab), hgt, wid, hgt - GLYPH_H - 1,
                           int(4 + max(0, (lpx - text_width(lab)) * 0.5)))

    faint &= ~ink
    lit = ink | faint
    halo = _dilate(lit) & ~lit
    idx = np.flatnonzero(lit | halo).astype(np.intp)
    flat_ink, flat_faint = ink.reshape(-1)[idx], faint.reshape(-1)[idx]
    col = np.tile(np.array(C_SHADOW, np.uint8), (len(idx), 1))
    col[flat_faint] = C_INK_DIM
    col[flat_ink] = C_INK
    return idx, np.ascontiguousarray(col, np.uint8)


def _pad_mask(m, hgt, wid, y, x):
    """A small mask placed into a (hgt, wid) one, clipped."""
    out = np.zeros((hgt, wid), bool)
    gh, gw = m.shape
    y0, x0 = max(0, y), max(0, x)
    y1, x1 = min(hgt, y + gh), min(wid, x + gw)
    if y1 > y0 and x1 > x0:
        out[y0:y1, x0:x1] = m[y0 - y:y1 - y, x0 - x:x1 - x]
    return out


def _dilate(a):
    o = a.copy()
    o[1:] |= a[:-1]
    o[:-1] |= a[1:]
    o[:, 1:] |= a[:, :-1]
    o[:, :-1] |= a[:, 1:]
    return o


# --------------------------------------------------------------------------
# The honest panels: no record, or a buoy that has stopped talking.
# --------------------------------------------------------------------------

def draw_card(dst, lay, lines):
    dst[:] = (5, 7, 12)
    scale = 2 if lay.h >= 32 and lay.w >= 200 else 1
    total = 0
    for i, _ in enumerate(lines):
        total += text_height(scale if i == 0 else 1) + 3
    y = max(0, (lay.h - total) // 2)
    for i, (s, rgb) in enumerate(lines):
        sc = scale if i == 0 else 1
        blit_text(dst, y, max(0, (lay.w - text_width(s, sc)) // 2), s, rgb, sc)
        y += text_height(sc) + 3
    return dst


# --------------------------------------------------------------------------
# Options.
# --------------------------------------------------------------------------

def add_arguments(ap):
    ap.add_argument("--cache-dir", default=None,
                    help="ftdata cache to read (default: ftdata's own)")
    ap.add_argument("--station", default=STATION,
                    help="NDBC station whose record to draw")
    ap.add_argument("--hours", type=float, default=24.0,
                    help="hours of trend across the strip")
    ap.add_argument("--waves", type=float, default=WAVES_ACROSS,
                    help="swell wavelengths across the panel; the zoom, and "
                         "the scale bar always says what it came out as")
    ap.add_argument("--rate", type=float, default=1.0,
                    help="wave speed multiplier; 1 is real time, which is the "
                         "entire point, so change it only for a screenshot")
    ap.add_argument("--full-scale", type=float, default=HS_FULL,
                    help="significant height in metres at full contrast")
    ap.add_argument("--no-windsea", action="store_true",
                    help="draw the swell alone, without the local chop")
    ap.add_argument("--reload", type=float, default=600.0,
                    help="seconds between re-reads of the cache (0 = never)")


# --------------------------------------------------------------------------
# build()
# --------------------------------------------------------------------------

def build(args):
    w, h = args.width, args.height
    lay = Layout(w, h)
    cache = args.cache_dir
    station = args.station

    frame = np.zeros((h, w, 3), np.uint8)
    palette = np.ascontiguousarray(
        ds.gradient(SEA_RAMP, 256, np.uint8), np.uint8)

    # Everything the frame loop touches, rebuilt only when the record changes.
    cell = {"card": None, "loaded": -1e18, "key": None, "state": None,
            "idx": [], "tab": [], "period": [], "buf": [], "hgt": None,
            "ovl": None, "mpp": 0.0, "sea": None, "sea_flat": None}

    def make_card(lines):
        cell["card"] = draw_card(np.zeros((h, w, 3), np.uint8), lay, lines)

    def prepare(state):
        """Bake the header, the strip, the phase images and the overlay."""
        cell["card"] = None
        if lay.head_h:
            draw_header(frame[:lay.head_h], lay, state)
        if lay.strip_h:
            draw_strip(frame[lay.strip_y:], lay, state, args.hours)
        sea_h = lay.sea_h
        if sea_h <= 0:
            cell["idx"] = []
            return
        sea = frame[lay.sea_y:lay.sea_y + sea_h]
        cell["sea"] = sea
        cell["sea_flat"] = sea.reshape(-1, 3)

        sw, ws = state["swell"], state["windsea"]
        if args.no_windsea:
            ws = None
        # Metres per pixel comes from the swell wavelength and nothing else, so
        # the windsea is drawn at its true size *relative* to the swell -- which
        # is the comparison the panel exists to make.
        mpp = wavelength(sw["p"]) * max(0.2, args.waves) / w
        cell["mpp"] = mpp

        # Amplitude split. Total swing is set by significant height against
        # full scale, with a floor so a flat calm still shows some motion --
        # a dead-flat rectangle reads as a crashed demo rather than as a calm
        # sea. The 0.7 power is because the interesting range here is one to
        # three metres and a linear map spends most of the palette on storms.
        rel = min(1.0, max(0.10, state["hs"] / max(0.5, args.full_scale)))
        span = 127.0 * rel ** 0.7
        hh = ws["h"] if ws is not None else 0.0
        tot = max(1e-3, sw["h"] + hh)
        a1 = span * sw["h"] / tot
        a2 = span - a1

        cell["idx"], cell["tab"], cell["period"], cell["buf"] = [], [], [], []
        for train, amp, centre in ((sw, a1, 128), (ws, a2, 0)):
            if train is None or amp < 1.0:
                continue
            cell["idx"].append(phase_image(sea_h, w, mpp, train["p"],
                                           train["dir"]))
            cell["tab"].append(sine_table(amp, centre))
            cell["period"].append(float(train["p"]))
            cell["buf"].append(np.empty((sea_h, w), np.intp))
        if not cell["idx"]:                       # a dead calm, drawn as one
            cell["idx"].append(np.zeros((sea_h, w), np.intp))
            cell["tab"].append(sine_table(0.0, 128))
            cell["period"].append(max(1.0, sw["p"]))
            cell["buf"].append(np.empty((sea_h, w), np.intp))
        cell["hgt"] = np.empty((sea_h, w), np.int16)
        cell["ovl"] = build_overlay(sea_h, w, state, mpp)

    def reload_data():
        # The reload timer is monotonic, never the wall clock: this is about
        # how long since *this process* last looked at the file, and a wall
        # clock that steps -- which is exactly what a Pi with no RTC does a
        # minute after it boots and finds an NTP server -- would either freeze
        # the re-read for hours or make it happen every frame.
        cell["loaded"] = time.monotonic()
        state, err = read_buoy(cache, station)
        cell["state"] = state
        if state is None:
            make_card([("NO BUOY DATA", C_WARN),
                       ("RUN  PYTHON3 FTDATA.PY --ONCE", C_TEXT),
                       ((err or "")[:52].upper(), C_DIM)])
            return
        obs = state["obs_age"]
        if err or obs is None or obs > OBS_DEAD:
            # The buoy, not the fetcher. Say which, and do not animate a sea
            # state that stopped being true half a day ago.
            gone = ("SILENT %s" % ftdata.describe_age(obs)) if obs else "SILENT"
            make_card([("BUOY %s %s" % (state["station"], gone), C_WARN),
                       ("LAST FETCH %s AGO" % ftdata.describe_age(state["age"]),
                        C_DIM),
                       ((err or "no wave observation").upper()[:52], C_DIM)])
            return
        prepare(state)

    cell["scratch"] = (np.empty((lay.sea_h, w), np.int16)
                       if lay.sea_h > 0 else None)
    reload_data()

    rate = float(args.rate)
    # Table steps per second for each train: one wavelength -- NPHASE steps --
    # every T seconds, backwards, because a crest moves *with* the direction of
    # travel while the phase at a fixed point runs the other way.
    def step_of(period):
        return -NPHASE * rate / max(0.1, period)

    def render(t, i):
        # Wall clock only for the re-read, which cannot change what is drawn
        # unless the fetcher has written a new record; see the report.
        if args.reload and time.monotonic() - cell["loaded"] >= args.reload:
            reload_data()
        if cell["card"] is not None:
            return cell["card"]

        hgt = cell["hgt"]
        for j, (idx, tab, period, buf) in enumerate(
                zip(cell["idx"], cell["tab"], cell["period"], cell["buf"])):
            off = int(step_of(period) * t) % NPHASE
            np.add(idx, off, out=buf)
            if j == 0:
                np.take(tab, buf, out=hgt, mode="clip")
            else:
                np.take(tab, buf, out=cell["scratch"], mode="clip")
                np.add(hgt, cell["scratch"], out=hgt)
        np.take(palette, hgt, axis=0, out=cell["sea"], mode="clip")
        ovl_idx, ovl_col = cell["ovl"]
        cell["sea_flat"][ovl_idx] = ovl_col
        return frame

    render.state = cell
    render.layout = lay
    return render


def main():
    ds.standalone(sys.modules[__name__],
                  "live Pacific swell, animated at the measured period",
                  fps=20)


if __name__ == "__main__":
    main()
