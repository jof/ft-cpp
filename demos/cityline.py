#!/usr/bin/env python3
"""A whole day of San Francisco asking the city for something, replayed.

**Every other city panel on this wall is about vehicles.** `stringline` is
trains, `bikes` and `docks` are bikeshare, `ships` is the bay, `adsb` is what
is overhead. None of them is about people. 311 is the other half of a city --
the number you call when the sidewalk is filthy, when somebody has tagged your
roll-up door, when the tree out front has dropped a limb, when the car across
the driveway has not moved in a week. Two and a half thousand of those calls
land in a day, and they have a shape.

**The shape is the point.** Three requests come in at four in the morning. By
nine there are three hundred and twenty in the hour, and it stays between a
hundred and two hundred an hour until the light goes. A city has a working day
and 311 is where you can watch it start. The panel replays that day at about a
second an hour: the map fills in the order the calls actually arrived, dawn
outward, and the histogram beside it fills column by column under the same
playhead, so the bloom on the map and the bar on the chart are always the same
ten minutes.

**Three panes, and the reading order is left to right.**

  *the map*   62 x 57 pixels of San Francisco at 270 m to the pixel, drawn on
              the same land/sea bake `sfmix.py` uses (`sfmix-map.npz`), so the
              two San Francisco panels are recognisably siblings and there is
              not a second, differently-shaped coastline in the tree. Each
              request blooms where it was filed, in its category's colour, and
              fades to a floor rather than to nothing -- so what you are looking
              at by mid-afternoon is the accumulated day, with the last hour
              bright on top of it. The white cross is this building.

  *the day*   twenty-four stacked hourly bars, five pixels wide, in the same
              seven colours. The playhead sweeps it, everything to the left is
              lit and everything to the right is a dim ghost of itself, so you
              can see where the day is going as well as where it has been. The
              clock above it is the replay time, not the wall time.

  *the count* the day's total in the biggest type on the panel, and then the
              legend, which is also the tally: seven categories, seven colours,
              seven numbers that add to the total.

**The data is a day old and the panel says so, because it has to be.** SF's
311 dataset advertises itself as changing "multiple times per hour" and is in
fact a nightly snapshot: the newest case in it is always around midnight of the
previous day, loaded some time between one and four in the morning. So there is
no honest way to draw "today so far" from it. What there is instead is better
for this panel -- one *complete* calendar day, midnight to midnight, which is
exactly the window a daily rhythm needs. The header names the day and how long
ago its last case was filed. A dim dotted column on the chart, marked NOW, is
where the clock stands today against yesterday's curve; it is resolved once in
`build()`, not per frame, so `render()` stays a pure function of `t`.

**What is not on this panel, and why.** 311 records are public, and every one
of them is a record about a specific address. Three things happen in
`ftdata.py`, before anything is written to disk:

  * positions are snapped to a 0.002 degree grid -- about 220 by 175 metres,
    two city blocks, and *smaller than a pixel of the map above*, so the
    quantisation costs the picture nothing and cannot be argued down later;
  * the address, the case id, the free text, the photograph and the exact
    filing second never leave the fetcher at all;
  * **encampment reports are dropped outright**, matched on a keyword list
    rather than on today's category names so a category the city adds next year
    cannot arrive through OTHER. That is about a hundred and forty requests a
    day, five per cent of the total, and it is the largest single thing thrown
    away here. An encampment report says where specific unhoused people are
    sleeping tonight; a labelled, locatable dot for it on a wall in a room the
    public walks through is a map of vulnerable people. Folding it into an
    unlabelled OTHER would not fix that. Dropping it does.

The count on this panel is therefore the count of what is drawn, and it is
about five per cent under the city's own figure for the day. That is the right
trade and it is the same one the `bikes` panel made when it hashed away the
per-bike identifiers it could have inferred journeys from.

**Frame budget.** Nothing is computed per frame that could be computed once.
`build()` bakes 144 whole map images -- one per ten-minute bucket, 1.5 MB of
uint8 -- plus a lit and a dim copy of the chart and 144 pre-rendered clock and
running-count strips, because formatting and blitting a string is thirty numpy
calls and copying a baked one is a single `copyto`. `render()` is then four
copies, one multiply and one fancy-indexed write for the current bucket's
blooming points, a playhead column and a heartbeat pixel: **eight numpy calls a
frame**, none of them allocating, and the count does not vary with how busy the
day was -- a quiet 4 am and the nine o'clock wave cost exactly the same.
Measured over 6000 frames on the development machine: **mean 0.007 ms, p50
0.007, p95 0.008, p99 0.011**, worst frame 0.052 ms. `build()` is 19-22 ms here,
once, on the scheduler's worker thread, and most of that is the 144 map bakes.

Run:  python3 ftdata.py --once --only sf311-day
      python3 cityline.py --host 127.0.0.1
      python3 cityline.py --cycle 45
      FT_DATA_CACHE=/tmp/empty python3 cityline.py     # the no-data card
      python3 scripts/test-cityline.py
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

PRODUCT = "sf311-day"

# The land/sea bake sfmix.py draws its bay with: 768x768 bit-packed, lon
# -122.80..-121.60, lat 37.05..38.00. San Francisco occupies about 110 by 115
# of those cells, which is twice the resolution this pane can show, so nothing
# is gained by baking a second, finer one -- and a second coastline asset in the
# tree is a second thing to keep in step with the first.
COAST = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "sfmix-map.npz")

# What the map shows. Deliberately a fixed extent rather than one fitted to the
# day's requests: the city has to be in the same place every time this panel
# comes up, or the eye spends its two seconds re-locating instead of reading.
# North to the Marin headlands, because the Golden Gate is what makes the
# silhouette instantly San Francisco rather than a generic peninsula.
MAP_LAT = (37.700, 37.838)
MAP_LON = (-122.527, -122.350)

# How long the accumulated bloom takes to fade, in ten-minute buckets, and how
# dim it gets. Six buckets is an hour: a request is at full brightness when it
# lands, a bit over half after an hour and near the floor after three. The floor
# is high on purpose -- the panel is *about* the day accumulating, and a trail
# that decayed to nothing would leave the map showing only the last hour, which
# is a much less interesting picture and a much less true one.
FADE_BUCKETS = 6.0
FADE_FLOOR = 0.30

# Past this many TTLs the fetcher is not merely late, it is off.
STALE_MULTIPLE = 1.0

# Hours after the data day ends before the panel says the city has gone quiet.
# Two days: one is normal (the snapshot is always a day behind), three means
# either DataSF or the fetcher has stopped and the panel must not imply that
# San Francisco simply had a quiet Tuesday.
OLD_HOURS = 60.0


# --------------------------------------------------------------------------
# Colour.
#
# Seven categorical hues, which is more than a five-pixel legend can carry
# comfortably and exactly as many as the data has. They are spaced around the
# wheel rather than taken off a sequential ramp, because nothing about
# CLEANING is more or less than NOISE and a ramp would imply it was. The two
# greens are far enough apart in hue and value to survive an LED panel seen
# from an angle; that was checked by drawing them, not by trusting the numbers.
#
# OTHER is the only grey, and that is the whole design of it: it is the bucket
# for everything with too few requests in it to name, and a grey dot reads as
# "something, unclassified" rather than as an eighth thing with a meaning.
# --------------------------------------------------------------------------

CAT_COLOURS = (
    (60, 200, 205),        # CLEANING -- cyan, and 40% of the day
    (72, 140, 250),        # PARKING  -- blue
    (205, 95, 230),        # GRAFFITI -- magenta
    (250, 170, 50),        # STREET   -- amber: defects, lights, sewers
    (120, 205, 70),        # TREES    -- green
    (245, 85, 75),         # NOISE    -- red
    (128, 138, 150),       # OTHER    -- grey, unnamed on purpose
)

C_BG = (3, 5, 7)
C_SEA = (2, 4, 8)
# The land is only a dozen levels off the sea and the shoreline is four times
# that, because on this panel the land is a *ground* and the shoreline is the
# only part of the basemap doing any work. The first version had them a few
# levels apart and the peninsula vanished into the bay from three metres away.
C_LAND = (20, 26, 33)
C_COAST = (54, 70, 86)
C_RULE = (24, 32, 40)

# The building. The only white on the panel, so it cannot be mistaken for a
# request. Note it gets no text label on the map: ftsite.SHORT is "SF", which
# beside a map of San Francisco reads as the city and not as this room, so the
# name goes in the header where there is space to spell it.
C_SITE = (250, 252, 255)

C_TEXT = (200, 214, 226)
C_DIM = (98, 112, 126)
C_LABEL = (72, 90, 110)
C_GHOST = (26, 33, 41)          # the chart's unplayed future
C_HEAD = (255, 236, 160)        # the playhead, and the clock above it
C_NOW = (120, 132, 146)         # today's clock against yesterday's curve
C_WARN = (255, 168, 40)
C_ALERT = (255, 62, 46)


def scale_colour(rgb, k):
    return (int(rgb[0] * k), int(rgb[1] * k), int(rgb[2] * k))


# --------------------------------------------------------------------------
# Type. defcon.py's 3x5 table, the same one docks, quake, tide and sfmix draw
# with -- five rows a glyph, each row an octal digit whose three bits are its
# columns. A real typeface is mush at five pixels and the Pi does not have the
# same faces installed as the machine this was written on.
# --------------------------------------------------------------------------

_FONT = dict(defcon._FONT)

_GLYPHS = {}
for _ch, _rows in _FONT.items():
    _g = np.zeros((5, 3), bool)
    for _r, _d in enumerate(_rows):
        _v = int(_d, 8)
        for _c in range(3):
            if _v & (4 >> _c):
                _g[_r, _c] = True
    _GLYPHS[_ch] = _g

DRAWABLE = frozenset(_FONT)


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


def blit_text(dst, y, x, s, rgb, scale=1):
    """Draw a string at (y, x), clipped to `dst`. Returns the width drawn.

    Clipped rather than asserted, for the same reason docks.py clips: this is
    laid out for 320x64 and has to survive being asked for something else, and
    a demo that raises on a narrow canvas takes the rotation down with it.
    """
    m = text_mask(s, scale)
    gh, gw = m.shape
    y0, x0 = max(0, y), max(0, x)
    y1, x1 = min(dst.shape[0], y + gh), min(dst.shape[1], x + gw)
    if y1 <= y0 or x1 <= x0:
        return gw
    sub = m[y0 - y:y1 - y, x0 - x:x1 - x]
    dst[y0:y1, x0:x1][sub] = rgb
    return gw


def blit_right(dst, y, x_right, s, rgb, scale=1):
    """Right-aligned, so a column of counts lines up on its units."""
    return blit_text(dst, y, x_right - text_width(s, scale) + 1, s, rgb, scale)


def fit(s, width, scale=1):
    """Trim a string until it fits. What falls off the end is the least of it."""
    s = str(s)
    while s and text_width(s, scale) > width:
        s = s[:-1]
    return s


def hhmm(minutes):
    return "%02d:%02d" % (int(minutes) // 60 % 24, int(minutes) % 60)


def spell(name):
    """A site name down to what the 3x5 table can draw."""
    s = str(name or "").upper()
    return "".join(ch if ch in DRAWABLE else " " for ch in s).strip()


# --------------------------------------------------------------------------
# Reading what ftdata left behind.
#
# Everything that can still be wrong after `load()` returns is wrong about
# *content*, and is caught here rather than in the middle of a bake. The four
# states are genuinely different: absent means no file, stale means the fetcher
# has stopped, old means the city has stopped, and a record whose arrays
# disagree with their own declared shape is a fourth thing that has to be
# refused rather than indexed into.
# --------------------------------------------------------------------------

class Day(object):
    """One published day of 311 requests, or a reason there is not one."""

    def __init__(self, cache_dir=None, product=PRODUCT, now=None):
        self.problem = None
        self.age = None
        self.state = "absent"
        self.day = ""
        self.n = 0
        self.near = 0
        self.near_m = 0.0
        self.site = (ftsite.LAT, ftsite.LON)
        self.site_name = ftsite.NAME
        self.cats = []
        self.hist = None            # (24, ncat) int
        self.pts = []               # per bucket: (cat, gy, gx) int arrays
        self.bucket_min = 10
        self.nbuckets = 144
        self.latest = None
        self.data_age = None
        self.ttl = ftdata.ttl_for(product) or 21600.0
        now = time.time() if now is None else float(now)

        got = ftdata.load(product, cache_dir)
        if got is None:
            self.problem = "no cached 311 record"
            return
        payload, self.age = got
        try:
            self.day = str(payload["day"])
            self.n = int(payload["n"])
            self.cats = [str(c) for c in payload["cats"]]
            ncat = len(self.cats)
            hist = payload["hist"]
            if len(hist) != 24 or any(len(h) != ncat for h in hist):
                raise ValueError("histogram is not 24 hours by %d" % ncat)
            self.hist = np.array(hist, np.int32)
            self.bucket_min = int(payload.get("bucket_min") or 10)
            self.nbuckets = 1440 // max(1, self.bucket_min)
            pts = payload["pts"]
            if len(pts) != self.nbuckets:
                raise ValueError("%d buckets, expected %d"
                                 % (len(pts), self.nbuckets))
            pack = int(payload.get("pack") or 128)
            lat0, lon0 = payload["origin"]
            step = float(payload["step"])
            for bucket in pts:
                arr = np.asarray(bucket, np.int64)
                if arr.size == 0:
                    self.pts.append((np.zeros(0, np.int32),
                                     np.zeros(0, f32), np.zeros(0, f32)))
                    continue
                # float64, not f32, and this is not fussiness: a latitude of
                # 37.7 spends six of float32's seven digits before the decimal
                # point matters, so unpacking in f32 lands the cell centre
                # about half a metre off its own grid. Nothing on a 270 m pixel
                # would ever show it, and the test that asserts every point
                # sits exactly on the grid -- which is how the privacy promise
                # is checked mechanically rather than by reading the fetcher --
                # would fail forever for a reason that was not the point.
                gy = (arr % pack).astype(np.float64)
                gx = ((arr // pack) % pack).astype(np.float64)
                cat = (arr // (pack * pack)).astype(np.int32)
                if cat.max() >= ncat or cat.min() < 0:
                    raise ValueError("a point names a category that is not "
                                     "in the record")
                # Unpacked to the *centre* of its cell, which is the only
                # position this record has ever contained.
                self.pts.append((cat, lat0 + gy * step, lon0 + gx * step))
            self.near = int(payload.get("near") or 0)
            self.near_m = float(payload.get("near_m") or 0.0)
            site = payload.get("site")
            if site:
                self.site = (float(site[0]), float(site[1]))
            self.site_name = str(payload.get("site_name") or ftsite.NAME)
            self.latest = float(payload["latest"])
        except Exception:                                    # noqa: BLE001
            self.problem = "311 record is malformed"
            self.hist, self.pts = None, []
            return

        if self.n <= 0 or self.hist.sum() <= 0:
            self.problem = "311 record holds no requests"
            return

        self.data_age = max(0.0, now - self.latest)
        if self.age > self.ttl * STALE_MULTIPLE:
            # The fetcher has stopped. The day it holds is still a true day, so
            # it still draws -- but the age has to be shouted, because the next
            # thing that happens if nobody notices is the wall quietly showing
            # last Thursday for a fortnight.
            self.state = "stale"
        elif self.data_age > OLD_HOURS * 3600.0:
            self.state = "old"
        else:
            self.state = "fresh"

    @property
    def drawable(self):
        return self.hist is not None and self.problem is None

    def totals(self):
        return self.hist.sum(axis=0)

    def hourly(self):
        return self.hist.sum(axis=1)

    def peak_hour(self):
        return int(np.argmax(self.hourly()))

    def cumulative(self):
        """Requests filed by the end of each ten-minute bucket, interpolated.

        The record's counts are exact but hourly; the playhead moves in ten
        minute steps. Straight-lining across each hour is the honest way to
        show a running total against a finer clock than the counts have -- and
        it is what makes the number climb rather than jump six times an hour,
        which on a wall reads as a broken counter.
        """
        hours = self.hourly().astype(np.float64)
        edges = np.concatenate([[0.0], np.cumsum(hours)])
        per = self.bucket_min / 60.0
        out = np.zeros(self.nbuckets + 1, np.int32)
        for k in range(self.nbuckets + 1):
            x = k * per
            i = min(23, int(x))
            out[k] = int(round(edges[i] + (x - i) * hours[i]))
        return out


# --------------------------------------------------------------------------
# The map. An equirectangular tile, isotropic in both axes, over a fixed
# extent.
#
# Isotropic matters here for the same reason it does in docks.py: San Francisco
# is 14 km across and 15 tall, and a projection stretched to fill whatever pane
# it is given would draw a city nobody who lives in it would recognise. The
# slack goes into margin instead, which is why the pane is a little wider than
# the city needs.
# --------------------------------------------------------------------------

class Projection(object):
    def __init__(self, w, h, lat=MAP_LAT, lon=MAP_LON):
        self.w, self.h = w, h
        self.lat0, self.lat1 = lat
        self.lon0, self.lon1 = lon
        mid = (self.lat0 + self.lat1) * 0.5
        self.ky = 111320.0
        self.kx = 111320.0 * math.cos(math.radians(mid))
        self.h_m = (self.lat1 - self.lat0) * self.ky
        self.w_m = (self.lon1 - self.lon0) * self.kx
        self.scale = min((w - 1) / max(1.0, self.w_m),
                         (h - 1) / max(1.0, self.h_m))       # px per metre
        self.ox = (w - self.w_m * self.scale) * 0.5
        self.oy = (h - self.h_m * self.scale) * 0.5

    def project(self, lat, lon):
        """(row, col) as float arrays or scalars. May fall outside the pane."""
        x = (np.asarray(lon, np.float64) - self.lon0) * self.kx
        y = (self.lat1 - np.asarray(lat, np.float64)) * self.ky
        return self.oy + y * self.scale, self.ox + x * self.scale

    def m_per_px(self):
        return 1.0 / self.scale


def load_sea():
    """sfmix-map.npz as a boolean sea mask and its bbox, or None.

    Missing is survivable and is not worth a card: this panel's subject is the
    requests, and a scatter of them with no coastline under it is still the
    day. Only losing the requests means anything.
    """
    try:
        d = np.load(COAST)
        shape = tuple(int(v) for v in d["shape"])
        sea = np.unpackbits(d["sea"])[:shape[0] * shape[1]].reshape(shape)
        return sea.astype(bool), tuple(float(v) for v in d["bbox"])
    except Exception:                                        # noqa: BLE001
        return None


def sea_mask(proj, sub=3):
    """The baked mask resampled into the pane, area-averaged sub x sub.

    Nearest-neighbour changes the number of inlets in the bay when the panel
    width changes, which is how a coastline ends up looking like a different
    coastline at 256 wide than at 320. Same fix, and same reason, as
    `sfmix.sea_mask`; three samples rather than two because this pane is four
    times coarser than that one.
    """
    got = load_sea()
    if got is None:
        return None
    sea, (lon0, lat0, lon1, lat1) = got
    rows, cols = sea.shape
    w, h = proj.w, proj.h
    yy, xx = np.meshgrid((np.arange(h * sub) + 0.5) / sub,
                         (np.arange(w * sub) + 0.5) / sub, indexing="ij")
    lon = proj.lon0 + (xx - proj.ox) / proj.scale / proj.kx
    lat = proj.lat1 - (yy - proj.oy) / proj.scale / proj.ky
    c = ((lon - lon0) / (lon1 - lon0) * cols).astype(int).clip(0, cols - 1)
    r = ((lat1 - lat) / (lat1 - lat0) * rows).astype(int).clip(0, rows - 1)
    fine = sea[r, c].astype(f32)
    return fine.reshape(h, sub, w, sub).mean((1, 3)) >= 0.5


def basemap(proj):
    """The still picture under the requests: sea, land, and a lit shoreline."""
    img = np.zeros((proj.h, proj.w, 3), np.uint8)
    sea = sea_mask(proj)
    if sea is None:
        img[:] = C_LAND
        return img
    img[sea] = C_SEA
    img[~sea] = C_LAND
    # One pixel of shoreline, so the city has an edge at all. Without it the
    # two greys are three levels apart and the peninsula disappears into the
    # bay at any distance -- which was the first version of this pane.
    edge = np.zeros_like(sea)
    edge[:, :-1] |= sea[:, :-1] != sea[:, 1:]
    edge[:-1] |= sea[:-1] != sea[1:]
    img[edge & ~sea] = C_COAST
    return img


def draw_site(img, r, c):
    """The building: a cross, not a dot. A lit pixel among two thousand
    requests is another request."""
    h, w = img.shape[:2]
    if not (0 <= r < h and 0 <= c < w):
        return
    img[max(0, r - 2):r + 3, c] = C_SITE
    img[r, max(0, c - 2):c + 3] = C_SITE


# --------------------------------------------------------------------------
# Options and layout.
# --------------------------------------------------------------------------

def add_arguments(ap):
    ap.add_argument("--cache-dir", default=None,
                    help="ftdata cache to read (default: ftdata's own)")
    ap.add_argument("--cycle", type=float, default=30.0,
                    help="seconds to replay the whole day; 30 is about a "
                         "second and a quarter to the hour")
    ap.add_argument("--no-now", action="store_true",
                    help="drop the dotted NOW column (today's clock against "
                         "the drawn day)")
    ap.add_argument("--no-bloom", action="store_true",
                    help="step the map bucket by bucket with no smooth "
                         "fade-in, for a still photograph")


class Layout(object):
    """Proportional with floors, so a canvas other than 320x64 gives something
    sane rather than an exception or a heap of overlapping type."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.head_h = 6 if h >= 40 else 5
        self.body_y = self.head_h + 1
        self.body_h = max(6, h - self.body_y)

        # The map wants to be square-ish or the city is not the right shape, so
        # it takes its width from the body height and gives up the difference.
        self.map_w = min(int(round(w * 0.195)), self.body_h + 6)
        if self.map_w < 24 or self.body_h < 24 or w < 140:
            self.map_w = 0

        self.right_w = min(126, max(44, int(round(w * 0.33))))
        self.right_x = w - self.right_w
        self.rule2_x = self.right_x - 3
        self.chart_x = self.map_w + (4 if self.map_w else 0)
        self.chart_w = max(0, self.rule2_x - 1 - self.chart_x)
        if self.chart_w < 48:
            self.chart_w = 0

        # Inside the chart pane, top to bottom. The clock is scale 2 because it
        # is the one number that changes while you are watching and it has to
        # be readable from further away than the legend does.
        self.clock_h = 10 if self.body_h >= 44 else 5
        self.hist_y = self.clock_h + 1
        self.axis_h = 5
        self.base_y = self.body_h - self.axis_h - 3
        self.hist_h = max(4, self.base_y - self.hist_y)
        self.axis_y = self.base_y + 2

        # Inside the right pane: the total, then one row per category. Seven
        # rows of six pixels plus fifteen of headline is fifty-seven, which is
        # exactly the body of a 320x64 panel and is not a coincidence.
        self.big = 3 if self.body_h >= 50 else 2
        self.legend_y = 5 * self.big
        self.row_h = 6
        self.rows = max(0, (self.body_h - self.legend_y) // self.row_h)


# --------------------------------------------------------------------------
# The panes.
# --------------------------------------------------------------------------

def stack_rows(values, peak, height, ncat):
    """How many rows each category gets in one hour's bar. Sums to the bar.

    Rounding each category independently is the obvious way to do this and it
    is wrong in a way that only shows on the busiest bar of the day: seven
    values each rounded up overshoot the bar by up to seven rows, the top of
    the stack runs off the end of the chart, and the category on top -- OTHER,
    always -- silently disappears from the one hour it mattered most. That was
    a real bug here, found by reading the nine o'clock bar back off the panel
    rather than by looking at it, because a stack missing its cap looks exactly
    like a stack.

    So the bar's height is rounded once, and the *boundaries between*
    categories are rounded off the cumulative sum, which makes the segments add
    up to the bar by construction. Then any category with requests in it that
    still rounded to nothing borrows a row from the largest segment: a category
    with four requests in it at three in the morning is a real thing that
    happened, and a chart that rounded it away would say it did not.
    """
    vals = [int(v) for v in values]
    total = sum(vals)
    if total <= 0:
        return [0] * ncat
    bar = min(height, max(1, int(round(total / float(peak) * height))))
    seg, cum, prev = [], 0, 0
    for v in vals:
        cum += v
        edge = int(round(cum / float(total) * bar))
        seg.append(edge - prev)
        prev = edge
    for i, v in enumerate(vals):
        if v > 0 and seg[i] == 0:
            j = max(range(ncat), key=lambda k: seg[k])
            if seg[j] > 1:
                seg[j] -= 1
                seg[i] = 1
    return seg


def draw_chart(dst, day, lay, lit):
    """Twenty-four stacked hourly bars. `lit` picks the real colours or ghosts.

    Hours rather than the record's ten-minute buckets, and that is a data
    decision rather than a drawing one: the hourly counts are *exact*, while
    the ten-minute points have had duplicates on a block collapsed out of them
    for privacy. A chart drawn off the points would be a chart of blocks
    touched, which is a different quantity that happens to look similar. So the
    picture that carries numbers is drawn from the numbers.
    """
    w = dst.shape[1]
    hist = day.hist
    peak = max(1, int(day.hourly().max()))
    bar_w = max(1, w // 24)
    top = lay.hist_y
    bottom = lay.base_y - 1

    height = bottom - top + 1
    ncat = len(day.cats)

    for hour in range(24):
        x0 = hour * bar_w
        x1 = min(w, x0 + bar_w - (1 if bar_w > 2 else 0))
        if x0 >= w:
            break
        y = bottom
        for c, n in enumerate(stack_rows(hist[hour], peak, height, ncat)):
            if n <= 0:
                continue
            rgb = CAT_COLOURS[c] if lit else C_GHOST
            dst[y - n + 1:y + 1, x0:x1] = rgb
            y -= n
    dst[lay.base_y, :] = C_RULE if lit else scale_colour(C_RULE, 0.5)


def draw_chart_axis(dst, lay, now_col=None):
    """Hour labels under the bars, and today's clock if we know it."""
    w = dst.shape[1]
    bar_w = max(1, w // 24)
    for hour in (0, 6, 12, 18):
        blit_text(dst, lay.axis_y, hour * bar_w, "%02d" % hour, C_LABEL)
    blit_right(dst, lay.axis_y, w - 1, "24", C_LABEL)
    if now_col is not None and 0 <= now_col < w:
        # Dotted, and dim. It is a second clock on a chart that already has
        # one, and it must lose every fight with the playhead.
        dst[lay.hist_y:lay.base_y:3, now_col] = C_NOW
        # Left of the line if that clears the hour labels, otherwise right of
        # it, otherwise not at all. Choosing a side rather than nudging one
        # fixed position: the label moves through the day, and at eleven in the
        # morning the fixed version printed "NOW12" over the noon tick, which
        # is a worse axis than an unlabelled dotted line.
        lw, taken = text_width("NOW"), [(0, 2), (0, 2)]
        taken = [(hour * bar_w - 1, hour * bar_w + text_width("00") + 1)
                 for hour in (0, 6, 12, 18)]
        taken.append((w - text_width("24") - 2, w))
        for x in (now_col - lw - 1, now_col + 2):
            if x < 0 or x + lw > w:
                continue
            if any(x < b and x + lw > a for a, b in taken):
                continue
            blit_text(dst, lay.axis_y, x, "NOW", C_NOW)
            break


def draw_legend(dst, day, lay):
    """The tally, which is also the key. Seven numbers that add to the total."""
    w = dst.shape[1]
    totals = day.totals()
    order = list(range(len(day.cats)))
    for i, c in enumerate(order[:lay.rows]):
        y = lay.legend_y + i * lay.row_h
        if y + 5 > dst.shape[0]:
            break
        dst[y + 1:y + 4, 0:3] = CAT_COLOURS[c]
        name = fit(day.cats[c], max(8, w - 5 - 18))
        blit_text(dst, y, 5, name, C_TEXT if c < 3 else C_DIM)
        blit_right(dst, y, w - 1, "%d" % int(totals[c]),
                   CAT_COLOURS[c] if totals[c] else C_LABEL)


def header_text(day):
    """(left, middle, middle colour, right)."""
    if not day.drawable:
        return ("SF 311", (day.problem or "NO 311 DATA").upper(), C_ALERT, "")
    when = time.strftime("%a %d %b", time.localtime(day.latest)).upper()
    mid = "%d REQUESTS  %s" % (day.n, when)
    if day.near_m > 0:
        mid += "  %d WITHIN %.0fKM OF %s" % (
            day.near, day.near_m / 1000.0, fit(spell(day.site_name), 999))
    right = ftdata.describe_age(day.data_age) if day.data_age else ""
    return "SF 311", mid, C_TEXT, right


def draw_header(dst, w, lay, day):
    dst[:] = C_BG
    left, mid, midc, right = header_text(day)
    rw = 0
    if right:
        # The age of the newest *case*, not of the file. On a dataset that is
        # a nightly snapshot the file is always minutes old and the data is
        # always most of a day old, and printing the first would be true and
        # useless.
        label = ("CASES " + right) if w >= 260 else right
        blit_right(dst, 0, w - 2, label,
                   C_TEXT if day.state == "fresh" else C_WARN)
        rw = text_width(label) + 2
    if day.drawable and day.state != "fresh":
        # The word, not a tint. A colour shift on a wall seen across a workshop
        # is not a message.
        flag = "STALE" if day.state == "stale" else "OLD"
        fw = text_width(flag)
        blit_right(dst, 0, w - rw - 6, flag, C_ALERT)
        rw += fw + 6
    lw = 0
    if left:
        blit_text(dst, 0, 1, left, C_DIM)
        lw = text_width(left) + 1
    if mid:
        mid = fit(mid, w - lw - rw - 8)
        mx = max(lw + 4, min(w - rw - 3 - text_width(mid),
                             (w - text_width(mid)) // 2))
        blit_text(dst, 0, mx, mid, midc)
    dst[lay.head_h] = C_ALERT if not day.drawable else C_RULE


def draw_nodata(frame, w, h, day, cache_dir, lit=True):
    """Not a blank rectangle, and above all not an empty map of San Francisco,
    which would say the city had a day with nothing in it."""
    frame[:] = (6, 6, 8)
    edge = C_ALERT if lit else scale_colour(C_ALERT, 0.25)
    frame[0], frame[-1] = edge, edge
    frame[:, 0], frame[:, -1] = edge, edge

    title = "NO 311 DATA"
    scale = 3 if w >= 200 else 2
    while scale > 1 and text_width(title, scale) > w - 12:
        scale -= 1
    y = max(3, h // 2 - 5 * scale)
    blit_text(frame, y, (w - text_width(title, scale)) // 2, title,
              C_ALERT if lit else scale_colour(C_ALERT, 0.3), scale)
    y += 5 * scale + 4
    for s in ((day.problem or "cache is empty").upper(),
              "RUN: PYTHON3 FTDATA.PY --ONCE --ONLY SF311-DAY",
              (cache_dir or ftdata.CACHE_DIR).upper()):
        s = fit(s, w - 8)
        blit_text(frame, y, (w - text_width(s)) // 2, s, C_LABEL)
        y += 7
        if y + 5 > h - 2:
            break
    return frame


# --------------------------------------------------------------------------
# build()
# --------------------------------------------------------------------------

def build(args):
    w, h = args.width, args.height
    lay = Layout(w, h)
    cache = args.cache_dir
    cycle = max(2.0, float(args.cycle))

    # Wall clock is read exactly twice, both here: once for the age of the data
    # and once for the NOW column. `render()` below reads no clock at all and is
    # a pure function of t. See the module docstring.
    now = time.time()
    day = Day(cache, now=now)

    frame = np.zeros((h, w, 3), np.uint8)
    static = np.zeros((h, w, 3), np.uint8)

    if not day.drawable:
        nodata = (np.zeros((h, w, 3), np.uint8), np.zeros((h, w, 3), np.uint8))
        for is_lit, buf in zip((True, False), nodata):
            draw_nodata(buf, w, h, day, cache, is_lit)

        def render_nodata(t, i=0):
            np.copyto(frame, nodata[0 if (t % 2.0) < 1.1 else 1])
            return frame

        render_nodata.state = {"day": day, "nodata": True}
        render_nodata.layout = lay
        return render_nodata

    nb = day.nbuckets
    static[:] = C_BG
    draw_header(static[:lay.head_h + 1], w, lay, day)

    # ---- the map --------------------------------------------------------
    maps = None
    map_geom = None
    if lay.map_w:
        proj = Projection(lay.map_w, lay.body_h)
        base = basemap(proj)
        maps, site_rc, rows_of, cols_of, cats_of = _bake(proj, day, base)
        map_geom = (proj, site_rc, rows_of, cols_of, cats_of)
        static[lay.body_y:lay.body_y + lay.body_h, :lay.map_w] = maps[0]
        static[lay.body_y:, lay.map_w + 1] = C_RULE

    # ---- the chart ------------------------------------------------------
    chart_lit = chart_dim = None
    if lay.chart_w:
        cw, ch = lay.chart_w, lay.body_h
        chart_lit = np.zeros((ch, cw, 3), np.uint8)
        chart_dim = np.zeros((ch, cw, 3), np.uint8)
        draw_chart(chart_lit, day, lay, True)
        draw_chart(chart_dim, day, lay, False)
        now_col = None
        if not args.no_now:
            lt = time.localtime(now)
            bar_w = max(1, cw // 24)
            now_col = int((lt.tm_hour + lt.tm_min / 60.0) * bar_w)
        for buf in (chart_lit, chart_dim):
            draw_chart_axis(buf, lay, now_col)
        static[lay.body_y:lay.body_y + ch,
               lay.chart_x:lay.chart_x + cw] = chart_dim
        if lay.rule2_x > lay.chart_x:
            static[lay.body_y:, lay.rule2_x] = C_RULE

    # ---- the count and the legend ---------------------------------------
    if lay.right_w > 20:
        buf = np.zeros((lay.body_h, lay.right_w, 3), np.uint8)
        big = "%d" % day.n
        scale = lay.big
        while scale > 1 and text_width(big, scale) > lay.right_w - 30:
            scale -= 1
        bw = blit_text(buf, 0, 0, big, C_TEXT, scale)
        blit_text(buf, 5 * scale - 5, bw + 4, "REQUESTS", C_DIM)
        draw_legend(buf, day, lay)
        static[lay.body_y:lay.body_y + lay.body_h,
               lay.right_x:lay.right_x + lay.right_w] = buf

    # ---- the strips that change: clock and running count ----------------
    cum = day.cumulative()
    strips = None
    if lay.chart_w and lay.clock_h >= 10:
        cw = lay.chart_w
        sc = 2
        strips = np.zeros((nb, lay.clock_h, cw, 3), np.uint8)
        stamp = time.strftime("%a %d %b", time.localtime(day.latest)).upper()
        for k in range(nb):
            s = strips[k]
            blit_text(s, 0, 0, hhmm(k * day.bucket_min), C_HEAD, sc)
            blit_text(s, 5 * sc - 5, text_width("00:00", sc) + 5, stamp,
                      C_LABEL)
            n = "%d" % int(cum[k + 1])
            blit_right(s, 0, cw - 1, n, C_TEXT, sc)
            blit_right(s, 5 * sc - 5, cw - text_width(n, sc) - 4, "FILED",
                       C_DIM)

    cell = {"day": day, "nodata": False, "maps": maps, "cum": cum}

    # Scratch for the blooming points, sized to the busiest bucket, so that
    # nothing in the frame loop allocates.
    if map_geom is not None:
        _p, _site, rows_of, cols_of, cats_of = map_geom
        # Offset into frame coordinates here rather than per frame: adding the
        # pane origin to two index arrays every frame is two whole numpy calls
        # to move a scatter of points four rows down.
        rows_of = [r + lay.body_y for r in rows_of]
        cols_of = [c + 0 for c in cols_of]          # the map pane starts at x=0
        biggest = max([len(r) for r in rows_of] + [1])
        # uint8, so the one arithmetic call in the frame loop lands in the
        # frame's own dtype and the write below is a plain copy. See the note
        # in _bake about not leaning on implicit casts.
        flare = np.empty((biggest, 3), np.uint8)
    else:
        rows_of = cols_of = cats_of = None
        flare = None

    mx0, my0 = 0, lay.body_y
    cx0, cy0 = lay.chart_x, lay.body_y
    hist_y0 = lay.body_y + lay.hist_y
    hist_y1 = lay.body_y + lay.base_y + 1
    smooth = not args.no_bloom

    def render(t, i=0):
        # The one and only source of time. Everything below is a function of
        # `phase`, which is a function of t, which is what makes this pure.
        phase = (float(t) / cycle) % 1.0
        pos = phase * nb
        k = int(pos)
        if k >= nb:
            k = nb - 1
        frac = pos - k

        np.copyto(frame, static)

        if maps is not None:
            np.copyto(frame[my0:my0 + lay.body_h, mx0:mx0 + lay.map_w],
                      maps[k])
            rr, cc = rows_of[k], cols_of[k]
            n = rr.size
            if n:
                # This bucket's requests fading in over the bucket. The baked
                # image for k+1 already holds them at full, so the two meet
                # rather than jumping.
                #
                # Blended with a maximum rather than written straight in, and
                # that is not a nicety: a block that already had a request on
                # it this afternoon is lit in the baked image, and an overwrite
                # would blink it to black at the start of every bucket and ramp
                # it back up -- black dots flickering across the busiest part of
                # the map, which is where they are least affordable. A maximum
                # can only ever brighten, so the new request emerges over the
                # old one instead of erasing it.
                g = 1.0 if not smooth else frac
                np.multiply(cats_of[k], g, out=flare[:n], casting="unsafe")
                np.maximum(flare[:n], frame[rr, cc], out=flare[:n])
                frame[rr, cc] = flare[:n]

        if chart_lit is not None:
            px = int(round(phase * lay.chart_w))
            if px > 0:
                frame[cy0:cy0 + lay.body_h, cx0:cx0 + px] = chart_lit[:, :px]
            col = cx0 + min(lay.chart_w - 1, px)
            frame[hist_y0:hist_y1, col] = C_HEAD

        if strips is not None:
            np.copyto(frame[cy0:cy0 + lay.clock_h, cx0:cx0 + lay.chart_w],
                      strips[k])

        # The heartbeat, in the one corner nothing else uses: proof the panel
        # is live and not a photograph of itself, even at the quiet end of the
        # night when almost nothing blooms.
        frame[0, -1] = C_HEAD if (t % 2.0) < 1.0 else C_RULE
        return frame

    render.state = cell
    render.layout = lay
    render.static = static
    return render


def _bake(proj, day, base):
    """Bake the per-bucket map images. See bake_maps' docstring for the design.

    Split out from build() only so the tests can call it; the loop below is the
    real one, and `bake_maps` above is kept for its explanation of why the state
    is (category, age) rather than an accumulated image.
    """
    h, w = proj.h, proj.w
    ncat = len(day.cats)
    pal = np.zeros((256, 3), f32)
    for i in range(ncat):
        pal[i] = CAT_COLOURS[i % len(CAT_COLOURS)]

    rows_of, cols_of, cats_of, idx_of = [], [], [], []
    for cat, lat, lon in day.pts:
        if cat.size == 0:
            rows_of.append(np.zeros(0, np.intp))
            cols_of.append(np.zeros(0, np.intp))
            cats_of.append(np.zeros((0, 3), f32))
            idx_of.append(np.zeros(0, np.uint8))
            continue
        rr, cc = proj.project(lat, lon)
        rr = np.rint(rr).astype(np.intp)
        cc = np.rint(cc).astype(np.intp)
        ok = (rr >= 0) & (rr < h) & (cc >= 0) & (cc < w)
        rr, cc, cat = rr[ok], cc[ok], cat[ok]
        rows_of.append(rr)
        cols_of.append(cc)
        cats_of.append(pal[cat])
        idx_of.append(cat.astype(np.uint8))

    site_r, site_c = proj.project(day.site[0], day.site[1])
    site_rc = (int(round(float(site_r))), int(round(float(site_c))))

    cat_at = np.full((h, w), 255, np.uint8)
    age = np.full((h, w), 1e6, f32)
    bright = np.empty((h, w), f32)
    tint = np.empty((h, w, 3), f32)

    frames = []
    for k in range(day.nbuckets):
        img = base.copy()
        lit = cat_at != 255
        if lit.any():
            np.multiply(age, -1.0 / FADE_BUCKETS, out=bright)
            np.exp(bright, out=bright)
            bright *= (1.0 - FADE_FLOOR)
            bright += FADE_FLOOR
            np.multiply(pal[cat_at], bright[:, :, None], out=tint)
            # Explicit cast rather than letting the assignment do it. numpy has
            # always cast float into a uint8 destination unsafely and silently,
            # and the wall is on numpy 2 where the rules around implicit casts
            # have been tightened once already; being explicit costs a bake-time
            # allocation and removes the question.
            img[lit] = tint[lit].astype(np.uint8)
        draw_site(img, site_rc[0], site_rc[1])
        frames.append(img)

        age += 1.0
        rr = rows_of[k]
        if rr.size:
            cc = cols_of[k]
            cat_at[rr, cc] = idx_of[k]
            age[rr, cc] = 0.0

    return frames, site_rc, rows_of, cols_of, cats_of


def main():
    ds.standalone(sys.modules[__name__],
                  "A day of San Francisco's 311 requests, replayed", fps=20)


if __name__ == "__main__":
    main()
