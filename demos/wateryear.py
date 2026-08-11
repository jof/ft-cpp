#!/usr/bin/env python3
"""California's water year in forty seconds: the snow falls, melts, and fills.

The wall already watches the ocean -- tides, swell, ships -- and none of that
is the water anybody in this state argues about. The water that matters is the
water in storage, and it arrives on an annual clock: everything California
gets falls between October and April, most of it lands as snow on the Sierra,
and the snowpack is a second reservoir -- in a good year bigger than every
concrete one put together -- that releases itself over the following three
months. Which is why the panel is not a row of bar charts. It is a mountain
range with eight reservoirs under it, and it plays the year.

**Left to right is north to south.** Trinity, Shasta, Oroville, Folsom, New
Melones, Don Pedro, McClure, Pine Flat: eight vessels in latitude order, 17.9
million acre-feet of the state's forty-odd, spanning the Trinity Alps to the
southern Sierra. The ridge above them is the Sierra snowpack in the same
order, north index on the left and south on the right, blended across the
width because a hard seam between two survey regions would be a boundary the
data does not have. A small marker on the valley floor is this wall's own
latitude, read from ftsite.py -- Sequoia Fabrica sits between Don Pedro and
New Melones, which is a fact about the transect and not about the water.

**The year plays, then lands on today.** Over twenty-two seconds the panel
sweeps from 1 October to the latest day CDEC has: the snow builds down the
mountain through winter, the vessels rise and fall, and in April the snowline
climbs back up while meltwater runs off the mountain foot into the lakes
below. The cursor on the year axis at the bottom says where in the cycle you
are looking, and the axis behind it lights as it is crossed. When the sweep
reaches the present the three headline numbers come up to full brightness,
which is the panel arriving at now rather than merely stopping.

**Two numbers, and the second is the one that means something.** Percent of
capacity says how full the buckets are, which is mostly a fact about the size
of the buckets. Percent of average *for this date* says whether this is a good
year or a bad one, and it is the number every reservoir operator in the state
watches -- so it is the big one, on the right, coloured. The average is fifteen
complete water years, 2011 through 2025, and the panel says so rather than
saying "average", because that period contains two historic droughts and it
runs several points below the longer baselines CDEC quotes. A number whose
baseline is a secret is not a number.

**The amber dashes across each vessel are that reservoir's normal for the day
being drawn**, and they move with the sweep. Water above the dashes is a
surplus, water below them is a deficit, and the eye reads eight of those at
once without doing any arithmetic. On this writing Pine Flat is the one lake
visibly under its line and the other seven are over -- the southern Sierra had
its own drought inside a statewide good year, which no single statewide
percentage would show you.

**Slow data is the feature.** This record changes once a day, and the panel
looks completely different in February -- a white ridge, half-empty lakes
filling -- from how it looks in August. Nothing else on the wall does that.

**Nothing here touches the network.** `build()` calls `ftdata.load()`, which
reads one 13 kB JSON file, plus `wateryear-normals.npz` beside this file for
the baselines. The fetcher is a separate process on a timer, because ftsched
builds the next segment on a worker thread and a `build()` blocked on a socket
stops the render loop getting the interpreter back:

    $ python3 ftdata.py --loop 900

The source is CDEC's keyless JSON servlet -- sensor 15 for storage, sensor 82
for snow water equivalent at eighteen snow pillows. The normals are baked once
by hand and committed; see ftdata.wateryear_bake_normals(). A record past its
thirty-hour TTL still draws, with its age and STALE on the header, because a
year-shaped picture that is two days behind is still that year. No record at
all gets a no-data card.

**Frame budget.** Everything is baked in `build()`: the sky, the ridge, the
rock, the vessels, their labels, the year axis and the month letters are one
uint8 frame; the snow and the water are two more, drawn through per-step masks
that are a single integer comparison each. `render()` is one full-frame copy,
two compares, two masked copies, and a handful of writes over arrays of a few
hundred elements -- about twenty numpy calls, and on the Pi the call count is
the budget rather than the pixel count. Measured over a full loop here: see
the README. Nothing per frame formats a string or allocates a full frame.

`render` is a pure function of `t`: the sweep, the shimmer, the meltwater and
the cursor all come from the segment clock and nothing reads the wall clock
after `build()`.

Run:  python3 ftdata.py --once --only wateryear
      python3 wateryear.py --host 127.0.0.1
      python3 wateryear.py --hold-at 2026-02-15     # freeze mid-winter
      FT_DATA_CACHE=/tmp/empty python3 wateryear.py # the no-data card
      python3 scripts/test-wateryear.py
"""

import math
import os
import sys
import time

import numpy as np

import defcon
import demoscene as ds
import ftdata
import ftsite

f32 = np.float32

PRODUCT = "wateryear"

NORMALS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "wateryear-normals.npz")

# --------------------------------------------------------------------------
# Type. defcon.py's 3x5 font, the same one caiso, propagation and tide draw
# with -- five rows a glyph, each row an octal digit whose three bits are the
# three columns. The glyph size is read off the table rather than assumed:
# every measurement below comes from _GLYPH_H and _GLYPH_W, because assuming
# five rows once cost this tree the bottom row of every capital E.
# --------------------------------------------------------------------------

_FONT = dict(defcon._FONT)
_FONT.update({"%": "51245"})

_GLYPH_H = max(len(rows) for rows in _FONT.values())
_GLYPH_W = 3
_GLYPHS = {}
for _ch, _rows in _FONT.items():
    _g = np.zeros((_GLYPH_H, _GLYPH_W), bool)
    for _r, _d in enumerate(_rows):
        _v = int(_d, 8)
        for _c in range(_GLYPH_W):
            if _v & (4 >> _c):
                _g[_r, _c] = True
    _GLYPHS[_ch] = _g


def text_mask(s, scale=1):
    """A boolean mask for a string, one blank column between glyphs."""
    s = str(s).upper()
    if not s:
        return np.zeros((_GLYPH_H * scale, 1), bool)
    out = np.zeros((_GLYPH_H, len(s) * (_GLYPH_W + 1) - 1), bool)
    for i, ch in enumerate(s):
        x = i * (_GLYPH_W + 1)
        out[:, x:x + _GLYPH_W] = _GLYPHS.get(ch, _GLYPHS[" "])
    if scale > 1:
        out = np.repeat(np.repeat(out, scale, 0), scale, 1)
    return out


def text_width(s, scale=1):
    return max(1, (len(str(s)) * (_GLYPH_W + 1) - 1) * scale)


def text_height(scale=1):
    return _GLYPH_H * scale


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
# Colour. Night over a snow range, which is the one palette that lets white
# snow, blue water and amber reference marks all sit on the same panel without
# any of them being the brightest thing by accident.
# --------------------------------------------------------------------------

C_SKY_TOP = (3, 5, 14)
C_SKY_BOT = (16, 22, 42)
C_ROCK_TOP = (98, 94, 112)
C_ROCK_BOT = (44, 42, 56)
C_SNOW_TOP = (240, 246, 255)
C_SNOW_BOT = (150, 182, 218)
C_WATER_TOP = (76, 180, 228)
C_WATER_BOT = (8, 38, 88)
C_VESSEL = (17, 21, 30)          # inside of an empty vessel
C_WALL = (44, 50, 64)            # its sides and floor
C_LABEL = (92, 102, 118)         # reservoir code, on the dry part
C_LABEL_WET = (6, 34, 74)       # the same code, under water
C_SURF = (186, 236, 255)
C_NORM = (206, 148, 56)          # the "normal for this date" dashes
C_FLOOR = (30, 30, 38)
C_TEXT = (200, 212, 224)
C_DIM = (86, 98, 112)
C_WARN = (255, 96, 72)
C_MELT = (150, 220, 255)
C_MELT_TAIL = (60, 110, 150)
C_FLAKE = (206, 220, 240)
C_AXIS = (30, 36, 48)
C_AXIS_DONE = (74, 96, 126)
C_NOW = (255, 246, 214)
C_HERE = (140, 112, 70)

# The percent-of-average traffic light. Round numbers, not quantiles: a
# threshold that moves with the data is not a threshold.
C_ABOVE = (120, 214, 255)
C_NEAR = (226, 206, 96)
C_BELOW = (232, 110, 70)
PCT_ABOVE, PCT_NEAR = 100.0, 80.0

# Snow water equivalent that fills the ridge to its crest, in inches. Bigger
# It is set to a *normal* April, not to the record, and that is the whole
# argument: the mean 1 April index across the fifteen baked years is 29, 35 and
# 26 inches for the three regions, and in a normal April the Sierra genuinely
# is white from the crest to the foothills. So 28 inches paints the mountain
# out, an ordinary February reads as half-covered rather than as a dusting, and
# 2017 -- which touched 55 in the central Sierra -- clips. Clipping at "as much
# snow as this can draw" is the right failure: the mountain is already white
# and the number in the caption is what separates a big year from a huge one.
SNOW_FULL = 28.0

# How many times a second the standing wave on the water surface advances one
# of its 24 phases. Slow: this is a lake, not a bath.
SHIM_HZ = 0.35

MONTHS = ("OCT", "NOV", "DEC", "JAN", "FEB", "MAR",
          "APR", "MAY", "JUN", "JUL", "AUG", "SEP")
MONTH_NUM = (10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9)


# --------------------------------------------------------------------------
# Reading what ftdata left behind.
#
# `load()` never raises, so everything that can still be wrong is wrong about
# content, and it is caught here. Three states have to be drawable: a good
# record, a good record that is old, and no record. A fourth -- a record from
# last water year -- is refused outright, for the same reason caiso refuses
# yesterday's day: an axis that runs October to September drawn with the wrong
# year's numbers is a confident picture of a season that did not happen.
# --------------------------------------------------------------------------

def _series(values):
    """A stored list with nulls into a float array, NaN for the nulls.

    NaN and not zero: `None` means "the gauge did not report" all the way
    through this file, and a zero is a lake that has been emptied. They are
    drawn differently and they had better not become the same number here.
    """
    return np.array([np.nan if v is None else float(v) for v in values], f32)


def load_normals(path=NORMALS):
    """The baked day-of-water-year baselines, or None. Never raises.

    A missing or foreign file costs the reference dashes and the percent of
    average and nothing else -- the panel still draws the year and the percent
    of capacity, which is the half of it that needs no history.
    """
    try:
        with np.load(path) as z:
            res = {str(c): np.asarray(z["res_norm"][i], f32)
                   for i, c in enumerate(z["res_codes"])}
            snow = {str(r): np.asarray(z["snow_norm"][i], f32)
                    for i, r in enumerate(z["snow_regions"])}
            years = [int(y) for y in z["years"]]
        if not res or not years:
            return None
        return {"res": res, "snow": snow, "years": years}
    except Exception:                                        # noqa: BLE001
        return None


def read_year(cache_dir, now):
    """(record, age, problem). `record` is None if there is nothing drawable."""
    got = ftdata.load(PRODUCT, cache_dir)
    if got is None:
        return None, None, "no cached CDEC record"
    payload, age = got
    try:
        wy = int(payload["wy"])
        start = float(payload["start"])
        n_days = int(payload["n_days"])
        days = np.asarray(payload["days"], np.int32)
        order = [str(c) for c in payload["res_order"]]
        cap = {c: float(payload["cap_kaf"][c]) for c in order}
        label = {c: str(payload["res_label"][c]) for c in order}
        lat = {c: float(payload["res_lat"][c]) for c in order}
        res = {c: _series(payload["res_kaf"][c]) for c in order}
        sorder = [str(r) for r in payload.get("snow_order", [])]
        snow = {r: _series(payload["snow_in"][r]) for r in sorder}
        asof = payload.get("asof")
        asof = None if asof is None else float(asof)
    except Exception:                                        # noqa: BLE001
        return None, age, "CDEC record is malformed"

    if len(days) < 2 or not order:
        return None, age, "CDEC record has no usable series"
    # The water year the clock says we are in. A record for the previous one is
    # not stale, it is the wrong picture: October's axis with September's data.
    if ftdata._wy_water_year(now)[0] != wy:
        return None, age, "RECORD IS WATER YEAR %d" % wy

    # How long this water year is, in days -- 365 or 366, and worth asking
    # rather than assuming, because the axis is the whole year and the cursor's
    # position on it is the one thing the panel says about where we are.
    year_days = int(round((time.mktime((wy, 10, 1, 0, 0, 0, 0, 0, -1))
                           - start) / 86400.0))

    return {"wy": wy, "start": start, "n_days": n_days, "year_days": year_days,
            "days": days, "order": order, "cap": cap, "label": label,
            "lat": lat, "res": res, "snow_order": sorder, "snow": snow,
            "asof": asof, "age": age}, age, None


def doy_of(rec, day):
    """Day-of-water-year index (the leap template) for a day offset in `rec`."""
    lt = time.localtime(rec["start"] + float(day) * 86400.0 + 43200.0)
    i = ftdata.wateryear_doy(lt.tm_mon, lt.tm_mday)
    # 29 February in a common year has no slot; the day before is the honest
    # neighbour and the normals are smooth at that scale anyway.
    return ftdata.WY_DAYS - 1 if i is None else i


# --------------------------------------------------------------------------
# Options.
# --------------------------------------------------------------------------

def add_arguments(ap):
    ap.add_argument("--cache-dir", default=None,
                    help="ftdata cache to read (default: ftdata's own)")
    ap.add_argument("--normals", default=NORMALS,
                    help="baked day-of-year baselines (.npz)")
    ap.add_argument("--sweep", type=float, default=22.0,
                    help="seconds the year takes to play (0 = start at today)")
    ap.add_argument("--hold-at", default="",
                    help="freeze the sweep on this date, 'YYYY-MM-DD' or a "
                         "month name, instead of playing to today")
    ap.add_argument("--here", dest="here", action="store_true", default=True,
                    help="mark this wall's latitude on the transect")
    ap.add_argument("--no-here", dest="here", action="store_false")
    ap.add_argument("--melt", type=float, default=1.0,
                    help="meltwater stream density (0 = off)")
    ap.add_argument("--snowfall", type=float, default=1.0,
                    help="falling snow density (0 = off)")


# --------------------------------------------------------------------------
# Layout. Five bands down the panel, and the order they give way in on a
# shorter one is: month letters, then the caption lines, then the ridge. The
# vessels are the demo and they are the last thing to shrink.
# --------------------------------------------------------------------------

class Layout(object):
    def __init__(self, w, h):
        self.w, self.h = w, h
        gh = text_height(1)
        self.head_y = 0
        self.head_h = gh if h >= 24 else 0

        # The number block: one double-height figure on the right and three
        # single-height lines on the left, sharing the sky.
        self.big_y = self.head_h
        self.big_h = text_height(2) if (h >= 56 and w >= 200) else 0
        self.line_y = [self.big_y + i * (gh + 1) for i in range(3)]
        # The right-hand caption tucks under the big figure rather than under
        # the left column, which is what keeps the block twenty-two rows deep
        # instead of twenty-six -- and every row saved here is a row of
        # mountain, which is the half of the panel that has to carry from
        # across the room.
        self.cap_y = self.big_y + self.big_h + 1
        text_bot = max(self.line_y[2] + gh, self.cap_y + gh) if self.big_h \
            else self.head_h

        self.axis_h = gh + 2 if h >= 52 else 0
        self.axis_y = h - self.axis_h if self.axis_h else h
        self.month_y = self.axis_y + 2

        # What is left is the picture. The vessels get a fixed generous share
        # and the ridge takes the rest, because a two-row mountain is a smudge
        # while a two-row vessel is a bar chart with no room for a level in it.
        pic_y0 = text_bot + 1
        pic_y1 = (self.axis_y - 1) if self.axis_h else h
        pic = max(6, pic_y1 - pic_y0)
        self.ves_h = max(4, min(16, int(pic * 0.44)))
        self.ves_y1 = pic_y1 - 1
        self.ves_y0 = self.ves_y1 - self.ves_h + 1
        self.floor_y = self.ves_y0 - 2
        self.ridge_y1 = self.floor_y - 1
        self.ridge_y0 = pic_y0
        self.ridge_h = max(1, self.ridge_y1 - self.ridge_y0 + 1)


def vessel_columns(w, n):
    """(x0, x1) inclusive for each of `n` vessels across `w` columns.

    A gap of a fifth of the pitch either side, so that eight vessels read as
    eight objects rather than as one striped block, and so a meltwater stream
    has somewhere to land that is not another reservoir.
    """
    pitch = w / float(n)
    pad = max(2, int(round(pitch * 0.13)))
    out = []
    for k in range(n):
        x0 = int(round(k * pitch)) + pad
        x1 = int(round((k + 1) * pitch)) - pad - 1
        out.append((x0, max(x0 + 1, x1)))
    return out


def ridge_profile(w, y0, y1):
    """The crest row of the mountain range, per column.

    Deterministic: three sines of incommensurate period plus a southward tilt,
    because the southern Sierra genuinely is the high end and a range that is
    flat across 320 columns reads as a wall rather than as mountains. No RNG,
    so two builds of the same panel are the same picture -- a range that
    reshuffled itself every segment would be the most distracting thing here.
    """
    x = np.arange(w, dtype=f32) / max(1.0, w - 1.0)
    prof = (0.50 + 0.30 * np.sin(x * 11.3 + 0.7)
            + 0.22 * np.sin(x * 27.1 + 2.1)
            + 0.13 * np.sin(x * 53.7 + 4.4))
    # np.ptp(), not prof.ptp(): numpy 2.0 removed the method and the wall runs
    # numpy 2.0.
    prof = (prof - prof.min()) / max(1e-6, float(np.ptp(prof)))
    # Tilt: the crest climbs a fifth of the band's depth from north to south.
    prof = np.clip(prof * 0.78 + 0.22 * (1.0 - x), 0.0, 1.0)
    # ...and a floor under it, because the interesting thing is where the
    # snowline sits on the flank and a column three pixels tall has no flank.
    # Nothing about the real Sierra is as flat as this makes it, but a range
    # that dropped to the valley floor between peaks would spend half its
    # columns unable to show any snow at all.
    prof = 0.30 + 0.70 * prof
    depth = max(1, y1 - y0)
    return (y1 - np.round(prof * depth)).astype(np.int16)


# --------------------------------------------------------------------------
# Baking. Everything below runs once, in build().
# --------------------------------------------------------------------------

def vgradient(top_rgb, bot_rgb, y0, y1, h, w):
    """A vertical ramp between two colours over rows y0..y1 of an (h, w, 3)."""
    img = np.zeros((h, w, 3), f32)
    n = max(1, y1 - y0)
    k = np.clip((np.arange(h, dtype=f32) - y0) / n, 0.0, 1.0)[:, None]
    a = np.array(top_rgb, f32)[None, :]
    b = np.array(bot_rgb, f32)[None, :]
    img[:] = (a[None, :, :] * (1.0 - k[:, :, None])
              + b[None, :, :] * k[:, :, None])
    return img


def draw_background(bg, lay, rec, vx, crest):
    """Sky, rock, valley floor, vessel shells, labels, axis and months."""
    h, w = lay.h, lay.w

    sky = vgradient(C_SKY_TOP, C_SKY_BOT, 0, max(1, lay.ridge_y1), h, w)
    bg[:] = ds.dither(sky)

    if lay.ridge_h > 1:
        rock = ds.dither(vgradient(C_ROCK_TOP, C_ROCK_BOT,
                                   lay.ridge_y0, lay.ridge_y1, h, w))
        rows = np.arange(h)[:, None]
        body = (rows >= crest[None, :]) & (rows <= lay.ridge_y1)
        np.copyto(bg, rock, where=body[:, :, None])

    if 0 <= lay.floor_y < h:
        bg[lay.floor_y] = C_FLOOR
        bg[lay.floor_y + 1] = C_SKY_TOP

    for x0, x1 in vx:
        bg[lay.ves_y0:lay.ves_y1 + 1, x0:x1 + 1] = C_VESSEL
        bg[lay.ves_y0:lay.ves_y1 + 1, x0] = C_WALL
        bg[lay.ves_y0:lay.ves_y1 + 1, x1] = C_WALL
        bg[lay.ves_y1, x0:x1 + 1] = C_WALL

    if lay.axis_h:
        bg[lay.axis_y] = C_AXIS
        for m, name in zip(MONTH_NUM, MONTHS):
            d0 = ftdata.wateryear_doy(m, 1)
            d1 = d0 + (ftdata.wateryear_doy(m, 28) - d0) * 31 // 28
            c0 = int(d0 / float(ftdata.WY_DAYS) * w)
            c1 = int(min(d1, ftdata.WY_DAYS - 1) / float(ftdata.WY_DAYS) * w)
            if 0 <= c0 < w:
                bg[lay.axis_y, c0] = C_AXIS_DONE
            letter = name[0]
            lw = text_width(letter)
            x = c0 + max(0, (c1 - c0 - lw) // 2)
            if lay.month_y + text_height() <= h and x + lw <= w:
                blit_text(bg, lay.month_y, x, letter, C_AXIS_DONE)


def draw_labels(bg, water, lay, rec, vx):
    """The three-letter code on each vessel, drawn into both layers.

    Into both because the level moves: a label drawn only on the dry shell
    disappears the moment the reservoir fills past it, and one drawn only on
    the water is missing all winter. Two colours, one dark on the bright water
    and one light on the dark shell, and the per-frame cost is nothing at all
    because the water layer is a masked copy of a baked image.
    """
    y = lay.ves_y0 + 1
    if y + text_height() > lay.ves_y1:
        return
    for k, code in enumerate(rec["order"]):
        if k >= len(vx):
            break
        x0, x1 = vx[k]
        s = rec["label"][code]
        tw = text_width(s)
        x = x0 + max(1, (x1 - x0 + 1 - tw) // 2)
        blit_text(bg, y, x, s, C_LABEL)
        blit_text(water, y, x, s, C_LABEL_WET)


def draw_here(bg, lay, rec):
    """A tick at this wall's latitude on the north-to-south transect.

    ftsite.LAT, never a literal: the whole point of that module is that the
    installation's address lives in one file. Interpolated between the two
    reservoirs it falls between, which is the only sense in which a panel about
    the Sierra has a position for a building in San Francisco -- it is a
    latitude on an axis, and the README says so.
    """
    lats = [rec["lat"][c] for c in rec["order"]]
    if len(lats) < 2 or lay.floor_y < 2:
        return
    # The axis runs north (left, high latitude) to south (right, low), so the
    # interpolation table has to be reversed into increasing order.
    centres = [(x0 + x1) * 0.5 for x0, x1 in
               vessel_columns(lay.w, len(rec["order"]))]
    col = float(np.interp(ftsite.LAT, lats[::-1], centres[::-1]))
    c = int(round(np.clip(col, 1, lay.w - 2)))
    bg[lay.floor_y - 1:lay.floor_y + 1, c] = C_HERE
    s = str(ftsite.SHORT)[:4]
    tw = text_width(s)
    y = lay.floor_y - 1 - text_height()
    x = int(np.clip(c - tw // 2, 1, lay.w - tw - 1))
    if y >= lay.ridge_y0:
        blit_text(bg, y, x, s, C_HERE)


# --------------------------------------------------------------------------
# The headline. Formatted once per build and rasterised into the background,
# because every number on it comes out of the record and can only change when
# the record does -- and finding that out costs four string formats a frame,
# which on the Pi would be the most expensive thing in this file.
# --------------------------------------------------------------------------

def last_finite(v):
    """The index of the newest real number in a series, or None.

    Every series here ends in a hole sooner or later: CDEC's daily values for
    today land some time in the morning, a gauge goes out for a week, a snow
    pillow melts out and stops transmitting. Reading the last *slot* rather
    than the last *value* is how a panel ends up reporting an empty Shasta at
    breakfast, so nothing in this file reads `[-1]`.
    """
    ok = np.flatnonzero(np.isfinite(v))
    return int(ok[-1]) if len(ok) else None


def headline(rec, norm):
    """(pct_capacity, pct_average, million acre-feet) at each lake's newest day.

    Per reservoir rather than at one shared instant, because they do not all
    report at the same hour and freezing the headline on the slowest of eight
    gauges would make the number lag by a day for no gain in truth. The normal
    each one is compared against is the normal for *its* day, so the ratio
    stays honest even when the days differ.
    """
    total = 0.0
    total_norm = 0.0
    cap = 0.0
    have_norm = norm is not None
    for code in rec["order"]:
        i = last_finite(rec["res"][code])
        if i is None:
            # A dead gauge drops out of both sides of the ratio rather than
            # counting as an empty lake, which would be a false headline of
            # exactly the kind this panel exists to avoid.
            continue
        cap += rec["cap"][code]
        total += float(rec["res"][code][i])
        if have_norm and code in norm["res"]:
            total_norm += float(norm["res"][code][doy_of(rec, rec["days"][i])])
        else:
            have_norm = False
    pct_cap = 100.0 * total / cap if cap > 0 else None
    pct_avg = (100.0 * total / total_norm
               if have_norm and total_norm > 0 else None)
    return pct_cap, pct_avg, total / 1000.0


def snow_headline(rec, norm):
    """The one thing worth saying about the snow, which depends on the season.

    Before the peak, the live number: how this year's index compares with the
    normal for today. After it, the peak itself, because a percent of normal in
    August is dividing nothing by nothing -- the normal is zero, everybody's
    snow is gone, and a panel that printed 'SNOW 0% OF AVG' in September would
    be announcing a catastrophe every single year.
    """
    if norm is None or not rec["snow_order"]:
        return None
    idx = np.zeros(len(rec["days"]), f32)
    ref = np.zeros(len(rec["days"]), f32)
    n = 0
    for region in rec["snow_order"]:
        if region not in norm["snow"]:
            continue
        v = rec["snow"][region]
        idx = idx + np.nan_to_num(v, nan=0.0)
        ref = ref + np.array([norm["snow"][region][doy_of(rec, d)]
                              for d in rec["days"]], f32)
        n += 1
    if not n:
        return None
    idx /= n
    ref /= n
    # Two inches of water on the whole range is the floor under "meaningful";
    # below it the ratio is noise from three pillows in a shaded gully.
    i = last_finite(idx)
    if i is None:
        return None
    if ref[i] >= 2.0:
        return "SNOW %d%% OF AVG" % round(100.0 * idx[i] / ref[i])
    peak = float(np.nanmax(idx)) if len(idx) else 0.0
    ref_peak = float(np.nanmax(ref)) if len(ref) else 0.0
    if ref_peak <= 0.0:
        return None
    return "SNOW PEAKED %d%%" % round(100.0 * peak / ref_peak)


def avg_colour(pct):
    if pct is None:
        return C_DIM
    if pct >= PCT_ABOVE:
        return C_ABOVE
    return C_NEAR if pct >= PCT_NEAR else C_BELOW


def draw_headline(bg, lay, rec, stale, pct_cap, pct_avg, maf, snow, years):
    """The header strip and the number block, into the baked background."""
    w = lay.w
    if lay.head_h:
        when = time.strftime("%b %-d", time.localtime(
            rec["asof"] if rec["asof"] else rec["start"])).upper()
        left = "WATER YEAR %d   %s" % (rec["wy"], when)
        age = ftdata.describe_age(rec["age"])
        right = ("STALE " + age) if stale else ("CDEC " + age)
        blit_text(bg, lay.head_y, 1, left, C_TEXT)
        rw = text_width(right)
        if rw + text_width(left) + 6 <= w:
            blit_text(bg, lay.head_y, w - rw - 1, right,
                      C_WARN if stale else C_DIM)

    if not lay.big_h:
        return

    big = "--" if pct_avg is None else "%d%%" % round(pct_avg)
    bw = text_width(big, 2)
    blit_text(bg, lay.big_y, w - bw - 2, big, avg_colour(pct_avg), 2)

    base = "VS %d-%d AVG" % (years[0], years[-1] % 100) if years else "VS AVG"
    cw = text_width(base)
    blit_text(bg, lay.cap_y, w - cw - 2, base, C_DIM)

    lines = [
        ("--% OF CAPACITY" if pct_cap is None
         else "%d%% OF CAPACITY" % round(pct_cap), C_TEXT),
        ("%.1f MAF STORED" % maf, C_TEXT),
        (snow or "", C_DIM),
    ]
    for y, (s, rgb) in zip(lay.line_y, lines):
        if s and y + text_height() <= lay.h:
            blit_text(bg, y, 2, s, rgb)


def draw_nodata(dst, lay, lines):
    """The honest panel. No mountain, no vessels, no implied year."""
    dst[:] = (6, 6, 8)
    scale = 2 if lay.h >= 32 and lay.w >= 200 else 1
    y = max(0, lay.h // 2 - (len(lines) * (text_height(scale) + 2)) // 2)
    for i, (s, rgb) in enumerate(lines):
        sc = scale if i == 0 else 1
        x = max(0, (lay.w - text_width(s, sc)) // 2)
        blit_text(dst, y, x, s, rgb, sc)
        y += text_height(sc) + 3
    return dst


def parse_hold(s, rec):
    """'--hold-at' to a column on the year axis, or None.

    Accepts a date, a month name and a bare month number, because the reason
    anybody reaches for this is "show me February" and typing a full ISO date
    to see February is a small tax on the one thing this option is for.
    """
    if not s:
        return None
    s = s.strip().upper()
    for fmt in ("%Y-%m-%d", "%m-%d", "%b %d", "%b"):
        try:
            tm = time.strptime(s, fmt)
        except ValueError:
            continue
        day = tm.tm_mday if fmt != "%b" else 15
        return ftdata.wateryear_doy(tm.tm_mon, day)
    if s in MONTHS:
        return ftdata.wateryear_doy(MONTH_NUM[MONTHS.index(s)], 15)
    raise ValueError("cannot read a date out of %r" % s)


# --------------------------------------------------------------------------
# build()
# --------------------------------------------------------------------------

def build(args):
    w, h = args.width, args.height
    lay = Layout(w, h)
    frame = np.zeros((h, w, 3), np.uint8)
    now = time.time()

    rec, age, problem = read_year(args.cache_dir, now)
    if rec is None:
        lines = [("NO WATER DATA", C_WARN),
                 ("RUN  PYTHON3 FTDATA.PY --ONCE --ONLY WATERYEAR", C_TEXT)]
        if problem:
            lines.append((str(problem).upper()[:52], C_DIM))

        def render_nodata(t, i):
            return draw_nodata(frame, lay, lines)
        render_nodata.state = {"rec": None, "problem": problem, "stale": False,
                               "pct_cap": None, "pct_avg": None, "steps": 0}
        render_nodata.layout = lay
        return render_nodata

    stale = not ftdata.is_fresh(PRODUCT, age)
    norm = load_normals(args.normals)
    n_res = len(rec["order"])
    vx = vessel_columns(w, n_res)
    crest = ridge_profile(w, lay.ridge_y0, lay.ridge_y1)

    # The sweep runs one step per panel column, which makes the step index and
    # the cursor's column the same number and removes a whole class of
    # off-by-one between the picture and the axis. The last step is the column
    # of the latest day CDEC has, not the column of today: when the fetcher is
    # a day behind, the cursor stops a pixel short and the header says so.
    last_day = int(rec["days"][-1])
    if rec["asof"] is not None:
        last_day = int(round((rec["asof"] - rec["start"]) / 86400.0))
    year_days = max(1, rec["year_days"])
    steps = int(np.clip(round(last_day / float(year_days) * w), 2, w))

    # Every series resampled onto those steps once. np.interp over the stored
    # day indices rather than over positions, because the record's samples are
    # every second day with both of the last two kept and are therefore not
    # evenly spaced.
    step_day = np.arange(steps, dtype=f32) * (year_days / float(w))
    days = rec["days"].astype(f32)
    step_doy = np.array([doy_of(rec, d) for d in np.round(step_day)], np.int32)

    def resample(v):
        ok = np.isfinite(v)
        if not ok.any():
            return np.full(steps, np.nan, f32)
        return np.interp(step_day, days[ok], v[ok]).astype(f32)

    # ---- water levels, and the normal for each day being drawn --------------
    #
    # LEV[j, c] is the row the water surface sits on in column c at step j, and
    # 32000 in every column that is not inside a vessel. That one convention is
    # what turns "draw eight tanks" into a single integer comparison per frame:
    # ROWV >= LEV[j] is exactly the wet pixels and nothing else.
    LEV = np.full((steps, w), 32000, np.int16)
    NORMROW = np.full((steps, w), 32000, np.int16)
    vh = lay.ves_h
    for k, code in enumerate(rec["order"]):
        if k >= len(vx):
            break
        x0, x1 = vx[k]
        cap = max(1.0, rec["cap"][code])
        f = np.clip(resample(rec["res"][code]) / cap, 0.0, 1.0)
        # NaN survives the clip; a vessel with no data at all stays empty
        # rather than drawing a plausible line at zero.
        f = np.nan_to_num(f, nan=0.0)
        top = (lay.ves_y1 + 1 - np.round(f * vh)).astype(np.int16)
        LEV[:, x0 + 1:x1] = top[:, None]
        if norm is not None and code in norm["res"]:
            nf = np.clip(norm["res"][code][step_doy] / cap, 0.0, 1.0)
            ntop = (lay.ves_y1 - np.round(nf * (vh - 1))).astype(np.int16)
            NORMROW[:, x0 + 1:x1] = ntop[:, None]

    # ---- the snowline ------------------------------------------------------
    #
    # Three regional indices blended across the width. The blend is a straight
    # interpolation between the three region centres rather than three blocks,
    # because a hard vertical seam in a mountain range is a rendering artefact
    # and the regions do not have an edge on the ground either.
    SNOWLINE = np.full((steps, w), np.int16(-32000), np.int16)
    frac = np.zeros((steps, w), f32)
    regions = [r for r in rec["snow_order"] if r in rec["snow"]]
    if regions:
        centres = np.array([(i + 0.5) * w / len(regions)
                            for i in range(len(regions))], f32)
        cols = np.arange(w, dtype=f32)
        per = np.stack([np.nan_to_num(resample(rec["snow"][r]), nan=0.0)
                        for r in regions])                   # (regions, steps)
        per = np.clip(per / SNOW_FULL, 0.0, 1.0)
        for j in range(steps):
            frac[j] = np.interp(cols, centres, per[:, j])
    depth = (lay.ridge_y1 - crest + 1).astype(f32)[None, :]
    SNOWLINE[:] = np.round(crest[None, :] - 1 + frac * depth).astype(np.int16)

    # ---- the two masked layers, and the row images they are compared to ----
    water_full = ds.dither(vgradient(C_WATER_TOP, C_WATER_BOT,
                                     lay.ves_y0, lay.ves_y1, h, w))
    snow_full = ds.dither(vgradient(C_SNOW_TOP, C_SNOW_BOT,
                                    lay.ridge_y0, lay.ridge_y1, h, w))

    # The row images the per-step thresholds are compared against, and the
    # only two arrays render() touches at full width. Both are cut down to the
    # band they describe -- seventeen rows of mountain and fourteen of vessel
    # rather than sixty-four of panel -- because these comparisons and the
    # masked copies that follow them are the whole per-frame cost and they are
    # memory-bound. Trimming them to their bands took the frame from 0.21 ms
    # to 0.08 ms here, which is the difference between comfortable and
    # marginal once the Pi's fifty-fold is applied.
    rows = np.arange(h, dtype=np.int16)[:, None]
    ROWV = np.full((lay.ves_h, w), np.int16(-30000), np.int16)
    for x0, x1 in vx:
        ROWV[:, x0 + 1:x1] = rows[lay.ves_y0:lay.ves_y1 + 1]
    rh = lay.ridge_y1 - lay.ridge_y0 + 1
    rrows = rows[lay.ridge_y0:lay.ridge_y1 + 1]
    ROWS_ = np.full((rh, w), np.int16(30000), np.int16)
    np.copyto(ROWS_, np.broadcast_to(rrows, (rh, w)).astype(np.int16),
              where=(rrows >= crest[None, :]))

    bg = np.zeros((h, w, 3), np.uint8)
    draw_background(bg, lay, rec, vx, crest)
    draw_labels(bg, water_full, lay, rec, vx)
    water = water_full[lay.ves_y0:lay.ves_y1 + 1]
    snow_img = snow_full[lay.ridge_y0:lay.ridge_y1 + 1]
    vband = (lay.ves_y0, lay.ves_y1 + 1)
    rband = (lay.ridge_y0, lay.ridge_y1 + 1)
    if args.here:
        draw_here(bg, lay, rec)

    pct_cap, pct_avg, maf = headline(rec, norm)
    snow_line = snow_headline(rec, norm)
    draw_headline(bg, lay, rec, stale, pct_cap, pct_avg, maf, snow_line,
                  norm["years"] if norm else None)

    # The whole title block at eight brightnesses, so the "arriving at now"
    # fade is one array copy a frame instead of a multiply over a slice. The
    # date is inside it on purpose: for most of the sweep the panel is showing
    # February, and a bright AUG 10 over a white mountain would be the one
    # actively misleading thing here. It comes up with the numbers, when the
    # cursor reaches the day it is talking about.
    blk0, blk1 = 0, min(h, lay.cap_y + text_height())
    dim_levels = 8
    HDR = np.stack([(bg[blk0:blk1].astype(f32)
                     * (0.34 + 0.66 * i / (dim_levels - 1.0))).astype(np.uint8)
                    for i in range(dim_levels)]) if blk1 > blk0 else None

    # ---- particles ---------------------------------------------------------
    #
    # Two systems, both tiny and both driven by `t`. Meltwater runs from the
    # foot of the mountain down into whichever vessel is under it, and how many
    # streams are running is the fall in the snow index at that step -- so the
    # streams appear in April because the snow is going, not because a date
    # said so. Snow falls in the sky while the index is rising, for the same
    # reason. Both counts are baked per step; per frame they are a slice.
    rng = np.random.default_rng(20261001)
    n_melt = int(28 * max(0.0, args.melt))
    n_flake = int(34 * max(0.0, args.snowfall))
    wet = np.flatnonzero(ROWV[-1] > -30000)
    if not len(wet):
        wet = np.arange(w)
    MX = rng.choice(wet, size=max(1, n_melt))
    MPH = rng.random(max(1, n_melt)).astype(f32)
    MSPD = (0.7 + 0.9 * rng.random(max(1, n_melt))).astype(f32)
    FX = rng.integers(0, w, size=max(1, n_flake))
    FPH = rng.random(max(1, n_flake)).astype(f32)
    FSPD = (0.10 + 0.16 * rng.random(max(1, n_flake))).astype(f32)

    # Rate of change of the mean snow fraction, per step, as a 0..1 signal.
    mean_frac = frac.mean(axis=1)
    d = np.diff(mean_frac, prepend=mean_frac[:1])
    melt_rate = np.clip(-d / max(1e-6, float(np.abs(d).max())), 0.0, 1.0)
    fall_rate = np.clip(d / max(1e-6, float(np.abs(d).max())), 0.0, 1.0)
    # Smoothed, because a day-to-day difference is spiky and a stream that
    # exists for two frames reads as a dead pixel.
    ker = np.ones(9, f32) / 9.0
    melt_rate = np.convolve(melt_rate, ker, mode="same")
    fall_rate = np.convolve(fall_rate, ker, mode="same")
    MELT_N = np.round(np.clip(melt_rate * 2.2, 0, 1) * n_melt).astype(np.int32)
    FALL_N = np.round(np.clip(fall_rate * 2.2, 0, 1) * n_flake).astype(np.int32)

    # Surface shimmer: a baked table of small vertical offsets per column, one
    # row of it per phase. Indexing it is one add; computing a sine per column
    # per frame would be four numpy calls and a temporary.
    scols = np.flatnonzero(ROWV[-1] > -30000)
    n_phase = 24
    ph = np.arange(n_phase, dtype=f32)[:, None] / n_phase * 2.0 * math.pi
    SHIM = np.round(np.sin(scols[None, :].astype(f32) * 0.55 + ph)
                    * 0.6).astype(np.int16)

    tick = np.flatnonzero((ROWV[-1] > -30000)
                          & (np.arange(w) % 3 == 0))

    hold = parse_hold(args.hold_at, rec)
    hold_step = None
    if hold is not None:
        hold_step = int(np.clip(round(hold / float(ftdata.WY_DAYS) * w),
                                0, steps - 1))

    vmask = np.empty((lay.ves_h, w), bool)
    rmask = np.empty((rh, w), bool)
    cell = {"rec": rec, "problem": None, "stale": stale, "pct_cap": pct_cap,
            "pct_avg": pct_avg, "maf": maf, "snow": snow_line, "steps": steps,
            "levels": LEV, "normrow": NORMROW, "snowline": SNOWLINE,
            "melt_n": MELT_N, "fall_n": FALL_N, "hold_step": hold_step}

    def step_of(t):
        """Which day of the year the panel is drawing at segment time `t`."""
        if hold_step is not None:
            return hold_step
        if args.sweep <= 0:
            return steps - 1
        return int(min(steps - 1, max(0.0, t) / args.sweep * steps))

    def render(t, i):
        j = step_of(t)
        np.copyto(frame, bg)

        # Snow, then water. Two comparisons and two masked copies for the whole
        # picture; every per-column and per-vessel decision was made in build().
        if lay.ridge_h > 1:
            np.less_equal(ROWS_, SNOWLINE[j][None, :], out=rmask)
            np.copyto(frame[rband[0]:rband[1]], snow_img,
                      where=rmask[:, :, None])
        np.greater_equal(ROWV, LEV[j][None, :], out=vmask)
        np.copyto(frame[vband[0]:vband[1]], water, where=vmask[:, :, None])

        # The normal for this date, dashed across every vessel. Drawn over the
        # water on purpose: the interesting case is water *above* the line.
        if len(tick):
            nr = NORMROW[j][tick]
            ok = nr <= lay.ves_y1
            if ok.any():
                frame[nr[ok], tick[ok]] = C_NORM

        # The surface, one lit row with a slow standing wave in it. This is the
        # thing that moves in every single frame once the sweep has landed.
        if len(scols):
            # Phase off `t`, never off the frame counter: the scheduler starts
            # a segment at t=0 and the preview baker steps at its own rate, so
            # a demo that animates on `i` is a different animation in each of
            # them -- and the purity check in scripts/test-wateryear.py would
            # be comparing two different things and passing.
            sr = LEV[j][scols] + SHIM[int(t * SHIM_HZ * n_phase) % n_phase]
            np.clip(sr, lay.ves_y0, lay.ves_y1, out=sr)
            frame[sr, scols] = C_SURF

        # Meltwater off the mountain into the lakes.
        n = MELT_N[j]
        if n:
            xs = MX[:n]
            # Out of the snow itself and down into the lake below, rather than
            # out of the foot of the hill: the whole claim this panel makes is
            # that the white on the mountain becomes the blue in the vessel,
            # and a stream that starts below the snowline does not make it.
            y0 = SNOWLINE[j][xs].astype(f32)
            y1 = LEV[j][xs].astype(f32)
            fr = (t * MSPD[:n] + MPH[:n]) % 1.0
            ys = (y0 + fr * np.maximum(0.0, y1 - y0)).astype(np.int16)
            np.clip(ys, 0, h - 1, out=ys)
            frame[ys, xs] = C_MELT
            np.subtract(ys, 1, out=ys)
            np.clip(ys, 0, h - 1, out=ys)
            frame[ys, xs] = C_MELT_TAIL

        # Snow falling in the sky, while the pack is building.
        n = FALL_N[j]
        if n:
            xs = FX[:n]
            fr = (t * FSPD[:n] + FPH[:n]) % 1.0
            ys = (lay.ridge_y0 - 8 + fr * (lay.ridge_y1 - lay.ridge_y0 + 8)
                  ).astype(np.int16)
            np.clip(ys, 0, h - 1, out=ys)
            frame[ys, xs] = C_FLAKE

        # The year axis: lit behind the cursor, dark ahead of it.
        if lay.axis_h:
            frame[lay.axis_y, :j + 1] = C_AXIS_DONE
            blink = 0.55 + 0.45 * math.sin(t * 4.0)
            y0 = max(0, lay.axis_y - 2)
            frame[y0:lay.axis_y + 2, j] = tuple(int(c * blink) for c in C_NOW)

        # Arriving at the present: the number block comes up to full over the
        # last fifth of the sweep, so the panel resolves rather than stopping.
        if HDR is not None:
            if hold_step is not None or args.sweep <= 0:
                k = dim_levels - 1
            else:
                k = int(min(dim_levels - 1,
                            max(0.0, j / max(1.0, steps - 1.0) - 0.8)
                            * 5.0 * (dim_levels - 1)))
            frame[blk0:blk1] = HDR[k]
        return frame

    render.state = cell
    render.layout = lay
    render.background = bg
    render.step_of = step_of
    return render


def main():
    ds.standalone(sys.modules[__name__],
                  "California's water year: snowpack and reservoir storage",
                  fps=20)


if __name__ == "__main__":
    main()
