#!/usr/bin/env python3
"""The 19, 22 and 55 approaching our door, drawn against the walk you have left.

The wall is in a makerspace at 1736 18th Street and the wiki names three buses
that serve it. Somebody walking past the wall has exactly one question about
them, and it is not "where is the bus". It is **do I need to leave now?**

That question has two halves and every departure board in the world shows only
one. "22 in 4 minutes" is useless on its own, because the 22's stop is four
hundred metres away and it takes seven minutes to walk there. The bus is not
early; you are late. So this panel draws the other half, to the same scale, on
the same axis:

  * **The left edge is the door.** A vertical warm line, fixed, ours.
  * **Rightwards is time** -- twenty minutes of it across the panel. Because
    you walk at a roughly constant speed, rightwards is *also distance*. One
    pixel is about four seconds, either way.
  * **The dotted stretch out of the door is the walk to that route's stop**,
    drawn at exactly that scale, ending in a post. The 19's post is close: its
    stop is 140 m away, two and a half minutes. The 22's post is a third of the
    way across the panel, because its stop is 413 m away and that is seven
    minutes of Potrero Hill.
  * **Every bus is a bus, sliding left**, at its predicted arrival. It reaches
    the post at the moment it reaches the stop.

And now the whole thing reads without a legend, because the geometry *is* the
answer. You leave the door and walk right. The bus comes left. **While the bus
is still right of the post you can make it. Once it is inside the dotted
stretch it is gone** -- it will reach the stop before you can -- and it goes
grey to say so. The number in the walking stretch is how many minutes you have
before you must start walking. NOW means put your shoes on.

Putting the walk and the bus on one axis instead of two is the one choice that
makes everything else fall out. It is why this is not a departure board and not
a map. The wall already has `adsb`, `quake`, `sats` and `ships` doing dots on
maps, and `stringline` drawing a Marey diagram of BART, which is the closest
neighbour -- it also has time on one axis and distance on the other. The
difference is what the axes are *for*. A stringline is about the trains: their
speed, their headway, where they pass each other, and it deliberately carries
no map. This is about the viewer. The only distance it plots is the distance
you personally have to cover, and the buses are drawn in exactly as much detail
as it takes to say whether you have missed one.

**The bar under the street is lateness, and it is drawn to the same scale as
everything else.** 511 gives both what the timetable promised and what is
actually going to happen, so the gap between them is a length on this axis, not
a number to read. A bar trailing left of a bus is a bus running late. A bar
ahead of it is one running early, which sounds harmless and is not -- an early
22 is a 22 you will miss. On a typical afternoon the 19 runs a minute early and
the 55 four minutes late, and you can see both at a glance.

**Live where it can be, honest where it cannot.** The header says LIVE and goes
green when it is drawing 511 predictions of tracked vehicles. A bus 511 is not
actually watching -- `Monitored: false`, meaning it is quoting its own
timetable back -- is drawn as an outline instead of a solid, so a scheduled bus
never wears the clothes of a tracked one. And with no key, no fetch or a record
past its TTL, the panel falls back to SFMTA's published timetable, turns the
header amber and says SCHEDULE. It never claims more than it has.

**Where the data comes from.** Two products, and the split is deliberate.
`muni-18th` is SFMTA's static GTFS off San Francisco's open data portal --
keyless, fetched daily -- and it is the source of the *geometry*: which stop is
nearest for each route in each direction (derived from `ftsite`, not
hardcoded), how far away it is, how long that is to walk, and the fallback
timetable. `muni-live` is 511.org SIRI StopMonitoring, which needs a free token
in `$FT_511_KEY`, and it is the source of the *predictions*. 511 rate-limits to
sixty requests an hour and one stop per request, so six stops is six requests
and the fetch interval is fifteen minutes -- 24 requests an hour. `ftdata.py`
explains that budget at length. What is cached is absolute arrival timestamps,
so the countdown on the wall stays correct between fetches even though the
revisions being counted down to do not get revised.

    $ python3 ftdata.py --once --only muni-18th     # geometry + timetable
    $ FT_511_KEY=... python3 ftdata.py --once --only muni-live

**The clock.** This is one of the wall-clock panels: it takes the present
moment from `time.time()` once, in `build()`, and every frame is a pure
function of `t` from there. So a segment animates, a preview bakes
reproducibly, and `--now` pins the moment, which is how the tests and the
screenshot get a fixed picture.

    $ python3 muni.py --now 1786566746        # a fixed weekday morning
    $ python3 muni.py --horizon 30            # half an hour of street
    $ python3 muni.py --source schedule       # ignore live, draw the timetable
"""

import sys
import time

import numpy as np

import defcon
import demoscene as ds
import ftdata
import ftsite

f32 = np.float32

PRODUCT = "muni-18th"                   # geometry and the fallback timetable
LIVE_PRODUCT = "muni-live"              # 511 predictions

# --------------------------------------------------------------------------
# Type. defcon.py's 3x5 font, the same one caiso, propagation, sort and tide
# draw with: five rows a glyph, each row an octal digit whose three bits are
# the three columns. The height is *measured* off the built glyphs rather than
# assumed to be five, because a panel that assumes five and meets six clips the
# bottom off every capital E, which is a bug this tree has actually shipped.
# --------------------------------------------------------------------------

_GLYPHS = {}
for _ch, _rows in defcon._FONT.items():
    _g = np.zeros((len(_rows), 3), bool)
    for _r, _d in enumerate(_rows):
        _v = int(_d, 8)
        for _c in range(3):
            if _v & (4 >> _c):
                _g[_r, _c] = True
    _GLYPHS[_ch] = _g

GLYPH_H = max(g.shape[0] for g in _GLYPHS.values())
GLYPH_W = max(g.shape[1] for g in _GLYPHS.values())
GLYPH_PITCH = GLYPH_W + 1               # one blank column between glyphs


def text_mask(s):
    """A boolean mask for a string, one blank column between glyphs."""
    s = str(s).upper()
    if not s:
        return np.zeros((GLYPH_H, 1), bool)
    out = np.zeros((GLYPH_H, len(s) * GLYPH_PITCH - 1), bool)
    for i, ch in enumerate(s):
        g = _GLYPHS.get(ch, _GLYPHS[" "])
        out[:g.shape[0], i * GLYPH_PITCH:i * GLYPH_PITCH + g.shape[1]] = g
    return out


def text_width(s):
    return max(1, len(str(s)) * GLYPH_PITCH - 1)


def _shade(rgb, k):
    """One colour, scaled. `ds.shade` wants a whole image and a factor field."""
    return tuple(int(max(0, min(255, round(c * k)))) for c in rgb)


def blit_text(dst, y, x, s, rgb):
    """Draw a string at (y, x), clipped to `dst`. Returns the width drawn."""
    m = text_mask(s)
    gh, gw = m.shape
    y0, x0 = max(0, y), max(0, x)
    y1, x1 = min(dst.shape[0], y + gh), min(dst.shape[1], x + gw)
    if y1 <= y0 or x1 <= x0:
        return gw
    dst[y0:y1, x0:x1][m[y0 - y:y1 - y, x0 - x:x1 - x]] = rgb
    return gw


# --------------------------------------------------------------------------
# Geometry. All columns and rows of the 320x64 panel, and all downstream of one
# decision: how many minutes fit across the street.
# --------------------------------------------------------------------------

W, H = ds.WIDTH, ds.HEIGHT

HDR_H = 5                               # the header's single line of type
GUTTER = 46                             # route number and destination
DOOR_X = GUTTER                         # the door: a fixed vertical line
LANE_H = 8
N_LANES = 6
LANE_TOP = HDR_H + 2
LANE_BOT = LANE_TOP + LANE_H * N_LANES
AXIS_Y = LANE_BOT
AXIS_TEXT_Y = AXIS_Y + 2

# Inside a lane: air, the bus, the road it stands on, and one row under the
# road for the lateness bar. Named because "y0 + 6" would otherwise appear in
# six places and be wrong in one of them.
LANE_TEXT_Y = 1
LANE_BUS_Y = 2
LANE_BUS_H = 4
LANE_ROAD = 6
LANE_LATE = 7

STREET_X0 = DOOR_X + 1
STREET_W = W - STREET_X0

# --------------------------------------------------------------------------
# Colour. One hue per route, and it cannot come from the feed: SFMTA paints
# every one of its bus routes the same corporate blue (005B95), so GTFS
# route_color would give three identical lanes. These three are picked to
# survive three metres and a lit room, and they are the wall's existing
# vocabulary -- the warm/cool pair tide and stringline share, plus a green.
# --------------------------------------------------------------------------

ROUTE_RGB = {
    "19": (255, 168, 58),               # amber
    "22": (86, 198, 255),               # cyan
    "55": (118, 224, 132),              # green
}
ROUTE_FALLBACK = (200, 200, 210)

C_BG = (6, 7, 10)
C_ROAD = (26, 29, 38)                   # the street, right of the post
C_WALK = (86, 76, 56)                   # the stretch you have to walk
C_POST = (150, 140, 110)                # the stop itself
C_DOOR = (255, 214, 140)                # our own door
C_DOOR_DIM = (92, 74, 44)
C_TEXT = (198, 212, 226)
C_DIM = (96, 106, 120)
C_FAINT = (46, 52, 62)
C_LIVE = (120, 235, 150)                # the header tag when 511 is answering
C_SCHED = (255, 176, 48)                # ...and when it is not
C_STALE = (255, 96, 72)
C_URGENT = (255, 246, 226)              # "leave now": the brightest thing here
C_MISSED = (76, 70, 78)                 # a bus inside the walk: gone
C_LATE = (214, 78, 66)                  # running behind the timetable
C_EARLY = (72, 140, 190)                # running ahead of it, which is worse

# How far right the street reaches, in minutes. Twenty puts the 22's post --
# seven minutes of walking -- a third of the way across, which is the honest
# picture, and still leaves thirteen minutes of catchable street beyond it.
HORIZON_MIN = 20.0

# Buses are drawn a little past the door so "you have just missed one" is
# visible, rather than a bus vanishing at the instant it mattered.
PAST_MIN = -0.6

# Below this, a bus is on time and the lateness bar is clutter.
LATE_FLOOR_MIN = 0.4

# 511 DirectionRef against the GTFS direction_id the geometry product carries.
DIR_OF = {1: "IB", 0: "OB"}


def add_arguments(ap):
    ap.add_argument("--horizon", type=float, default=HORIZON_MIN,
                    help="minutes of street across the panel")
    ap.add_argument("--now", type=float, default=0.0,
                    help="pin the clock to this epoch time (0 = the real one)")
    ap.add_argument("--source", choices=("auto", "live", "schedule"),
                    default="auto",
                    help="auto uses 511 when a fresh record is cached")
    ap.add_argument("--cache-dir", default=None,
                    help="ftdata cache to read (default: ftdata's own)")


# --------------------------------------------------------------------------
# The data, turned into six lanes of buses with absolute arrival times.
# --------------------------------------------------------------------------

def _load(name, cache_dir):
    return ftdata.load(name, cache_dir) if cache_dir else ftdata.load(name)


def _midnight(date):
    """Epoch seconds of the local midnight starting a GTFS service date."""
    y, m, d = int(date[0:4]), int(date[4:6]), int(date[6:8])
    return time.mktime((y, m, d, 0, 0, 0, 0, 0, -1))


def scheduled(payload, stop, now, span=(-900.0, 5400.0)):
    """One stop's timetabled departures near `now`, as absolute epoch times.

    Three service dates are unrolled, not one, and that is the whole reason
    this is a function rather than a lookup. GTFS spells "still Tuesday's
    service" as an hour past 24 -- the 22 runs to 30:09 -- so this morning's
    owl trips live under *yesterday's* date, and a panel that unrolled only
    today would show an empty street at 05:00 with a bus a block away.
    Tomorrow is unrolled for the mirror-image reason, so that at 23:55 the
    00:10 departure is already on the street.
    """
    lo, hi = now + span[0], now + span[1]
    services = payload.get("services") or {}
    times = stop.get("times") or {}
    out = []
    for delta in (-1, 0, 1):
        date = time.strftime("%Y%m%d", time.localtime(now + delta * 86400.0))
        active = services.get(date)
        if not active:
            continue
        base = _midnight(date)
        for service in active:
            for minute in times.get(service, ()):
                when = base + minute * 60.0
                if lo <= when <= hi:
                    out.append((when, None, False))
    out.sort()
    return out


def live_visits(live, stop):
    """One stop's 511 predictions, filtered to this lane's route and direction.

    The filter matters: 16th & Wisconsin is the 22's stop *and* a 55 stop, so
    its record carries both, and the 55 has its own stop 200 m closer. Drawing
    Wisconsin's 55 in the 55's lane would put it at the wrong walk distance,
    which is the one thing this panel exists to get right.
    """
    visits = (live.get("stops") or {}).get(str(stop.get("code") or ""))
    if not visits:
        return []
    route = str(stop.get("route") or "")
    want = DIR_OF.get(int(stop.get("dir") or 0))
    out = []
    for v in visits:
        if str(v.get("line") or "") != route:
            continue
        if want and str(v.get("dir") or "") != want:
            continue
        try:
            when = float(v["exp"])
        except (KeyError, TypeError, ValueError):
            continue
        aim = v.get("aim")
        try:
            aim = float(aim) if aim is not None else None
        except (TypeError, ValueError):
            aim = None
        out.append((when, aim, bool(v.get("mon"))))
    out.sort()
    return out


class Lane(object):
    """One (route, direction): its gutter type, its walk, and its buses."""

    def __init__(self, stop, buses, ppm, horizon):
        self.route = str(stop.get("route") or "?")
        self.label = str(stop.get("label") or "")
        self.name = str(stop.get("name") or "")
        self.code = str(stop.get("code") or "")
        self.metres = int(stop.get("metres") or 0)
        self.walk_min = float(stop.get("walk_s") or 0.0) / 60.0
        self.rgb = ROUTE_RGB.get(self.route, ROUTE_FALLBACK)
        self.buses = buses
        self.horizon = horizon
        # The post: where the stop is, in panel columns. Clamped, so that an
        # absurd walk -- a stop that moved half a kilometre in a sign-up --
        # puts the post at the edge rather than off it.
        post = DOOR_X + min(self.walk_min, horizon) * ppm
        self.post_x = max(DOOR_X + 2, min(W - 2, int(round(post))))


def build(args):
    horizon = max(4.0, float(getattr(args, "horizon", HORIZON_MIN)))
    ppm = STREET_W / horizon                        # pixels per minute
    pinned = float(getattr(args, "now", 0.0) or 0.0)
    now0 = pinned if pinned > 0 else time.time()
    want = getattr(args, "source", "auto")
    cache_dir = getattr(args, "cache_dir", None)

    got = _load(PRODUCT, cache_dir)
    if got is None:
        return _card(now0, "NO MUNI DATA",
                     "RUN FTDATA --ONLY " + PRODUCT, C_DIM)
    geom, geom_age = got
    if not isinstance(geom, dict) or not geom.get("stops"):
        return _card(now0, "NO MUNI DATA", "CACHED RECORD IS UNREADABLE",
                     C_STALE)

    # Live if we have it and it is worth believing. A record past its TTL is
    # not silently used -- eighteen-minute-old predictions are the design, but
    # hour-old ones are a different claim -- so it falls back to the timetable,
    # which does not go stale in the same way.
    live = None
    live_age = 0.0
    if want != "schedule":
        gotl = _load(LIVE_PRODUCT, cache_dir)
        if gotl is not None and isinstance(gotl[0], dict):
            if ftdata.is_fresh(LIVE_PRODUCT, gotl[1]) or want == "live":
                live, live_age = gotl

    # A static timetable can be perfectly fresh and still not cover today: the
    # feed carries a service period and the day after it ends there is no
    # answer at all. Only fatal when there is no live record to draw instead.
    today = time.strftime("%Y%m%d", time.localtime(now0))
    expired = today not in (geom.get("services") or {})
    if expired and live is None:
        return _card(now0, "SCHEDULE EXPIRED",
                     "SFMTA FEED RAN TO %s" % _pretty(geom.get("feed_end")),
                     C_STALE)

    lanes = []
    for stop in (geom.get("stops") or ())[:N_LANES]:
        if live is not None:
            buses = live_visits(live, stop)
        else:
            buses = scheduled(geom, stop, now0)
        lanes.append(Lane(stop, buses, ppm, horizon))
    if not lanes:
        return _card(now0, "NO MUNI DATA", "RECORD NAMES NO STOPS", C_STALE)

    bg = _background(lanes, horizon, ppm)
    sprites = _bus_sprites()

    if live is not None:
        tag, tag_rgb, age = "LIVE", C_LIVE, live_age
        stale = not ftdata.is_fresh(LIVE_PRODUCT, live_age)
    else:
        tag, tag_rgb, age = "SCHEDULE", C_SCHED, geom_age
        stale = not ftdata.is_fresh(PRODUCT, geom_age)
    age_txt = ftdata.describe_age(age)

    def render(t, frame):
        out = bg.copy()
        clock = now0 + t
        for i, lane in enumerate(lanes):
            _draw_lane(out, LANE_TOP + i * LANE_H, lane, clock, ppm, sprites)
        _header(out, clock, tag, tag_rgb, age_txt, stale)
        return out

    return render


def _pretty(d):
    d = str(d or "")
    return "%s-%s-%s" % (d[0:4], d[4:6], d[6:8]) if len(d) == 8 else "?"


# --------------------------------------------------------------------------
# The baked background: everything that does not move. Drawing it once is most
# of why this panel is cheap. Six dotted walks, six posts, six gutter labels
# and an axis are a few hundred numpy calls, and they happen in build() rather
# than twenty times a second.
# --------------------------------------------------------------------------

def _background(lanes, horizon, ppm):
    bg = np.zeros((H, W, 3), np.uint8)
    bg[:, :] = C_BG

    x = 1
    x += blit_text(bg, 0, x, ftsite.NAME, C_TEXT) + 4
    blit_text(bg, 0, x, "18TH ST", C_DIM)
    bg[HDR_H + 1, :] = C_FAINT

    for i, lane in enumerate(lanes):
        y0 = LANE_TOP + i * LANE_H
        road = y0 + LANE_ROAD

        # The street: dark, all the way to the right edge.
        bg[road, STREET_X0:] = C_ROAD

        # The walk: a dotted path from the door to the post, at the same scale
        # as the buses. Every other pixel, so it reads as "on foot" against the
        # solid road it interrupts.
        if lane.post_x > STREET_X0:
            bg[road, STREET_X0:lane.post_x:2] = C_WALK

        # The post: the stop, standing up out of the road.
        bg[road - 3:road + 1, lane.post_x] = C_POST

        # Gutter: the route in its own colour, the destination in grey. The
        # destination is what tells you which of the two directions this is --
        # BEACH is north, SHIPYARD is south -- and is more use than an arrow.
        blit_text(bg, y0 + LANE_TEXT_Y, 2, lane.route, lane.rgb)
        blit_text(bg, y0 + LANE_TEXT_Y, 2 + text_width("00") + 3,
                  lane.label, C_DIM)

    # The door. Drawn over the lanes, because it is the one fixed thing here
    # and everything else is measured from it. Bright across the lanes and dim
    # at the ends, so it reads as a doorway rather than a rule.
    bg[LANE_TOP:LANE_BOT, DOOR_X] = C_DOOR_DIM
    bg[LANE_TOP + 2:LANE_BOT - 2, DOOR_X] = C_DOOR

    # Axis: a tick every five minutes with its numeral, and the unit at the
    # left where there is room for it.
    bg[AXIS_Y, STREET_X0:] = C_FAINT
    step = 5.0 if horizon <= 24.0 else 10.0
    minute = step
    while minute <= horizon + 1e-6:
        x = int(round(DOOR_X + minute * ppm))
        if x >= W - 1:
            break
        bg[AXIS_Y, x] = C_DIM
        label = "%d" % int(round(minute))
        blit_text(bg, AXIS_TEXT_Y, x - text_width(label) // 2, label, C_DIM)
        minute += step
    blit_text(bg, AXIS_TEXT_Y, 2, "MIN TO STOP", C_FAINT)
    return bg


# --------------------------------------------------------------------------
# The bus. Nine columns by four rows is not enough for a vehicle, so it is not
# a vehicle: a body, a window band, and a bright leading edge on the left,
# because left is the way it is going. Four appearances are baked rather than
# multiplied per frame -- the one you should be running for, the ones behind
# it, the ones already gone, and the hollow one for a bus 511 is not actually
# watching -- because that is a few tiny arrays built once against three
# multiplies per bus per frame.
# --------------------------------------------------------------------------

BUS_W = 9
BUS_SHAPE = (
    (0.00, 0.62, 0.62, 0.62, 0.62, 0.62, 0.62, 0.62, 0.00),
    (1.35, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 0.75),
    (1.35, 0.42, 0.42, 1.00, 0.42, 0.42, 1.00, 0.42, 0.75),
    (0.55, 0.90, 0.55, 0.55, 0.55, 0.90, 0.55, 0.55, 0.00),
)

# The same silhouette with the middle knocked out: a bus 511 is quoting from
# its own timetable rather than tracking. It reads as "the shape of a bus, not
# a bus", which is exactly the claim.
BUS_GHOST = (
    (0.00, 0.62, 0.62, 0.62, 0.62, 0.62, 0.62, 0.62, 0.00),
    (0.90, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.62),
    (0.90, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.62),
    (0.55, 0.62, 0.62, 0.62, 0.62, 0.62, 0.62, 0.62, 0.00),
)

NEXT, LATER, MISSED = 0, 1, 2
BUS_GAIN = {NEXT: 1.00, LATER: 0.58, MISSED: 1.00}


def _bus_sprites():
    """(route, state, monitored) -> (rgb image, boolean mask), baked once."""
    solid = np.array(BUS_SHAPE, f32)
    hollow = np.array(BUS_GHOST, f32)
    out = {}
    routes = list(ROUTE_RGB.items()) + [(None, ROUTE_FALLBACK)]
    for route, rgb in routes:
        for state in (NEXT, LATER, MISSED):
            for mon in (True, False):
                shape = solid if mon else hollow
                base = np.array(C_MISSED if state == MISSED else rgb, f32)
                img = np.clip(shape[:, :, None] * BUS_GAIN[state] * base,
                              0.0, 255.0).astype(np.uint8)
                out[(route, state, mon)] = (img, shape > 0.0)
    return out


def _blit_sprite(dst, y, x, img, mask, xmin=0):
    """Draw a sprite at (y, x), clipped on all four sides.

    `xmin` is the door. A bus that has just gone past is drawn a little into
    the past so that "you have missed one" is visible rather than the bus
    vanishing at the instant it mattered -- but the columns left of the door
    are the gutter, where the route number lives, and half a bus parked on top
    of the word BEACH is not a design. Clipping there instead of refusing to
    draw is what makes it read as a bus leaving the picture behind the door.
    """
    gh, gw = mask.shape
    y0, x0 = max(0, y), max(xmin, x, 0)
    y1, x1 = min(dst.shape[0], y + gh), min(dst.shape[1], x + gw)
    if y1 <= y0 or x1 <= x0:
        return
    sub = mask[y0 - y:y1 - y, x0 - x:x1 - x]
    dst[y0:y1, x0:x1][sub] = img[y0 - y:y1 - y, x0 - x:x1 - x][sub]


def _draw_lane(out, y0, lane, clock, ppm, sprites):
    """One lane's buses, its lateness bars and its one number, for this instant."""
    bus_y = y0 + LANE_BUS_Y
    late_y = y0 + LANE_LATE

    first_catchable = None
    drawn = 0
    for when, aim, mon in lane.buses:
        mins = (when - clock) / 60.0
        if mins < PAST_MIN:
            continue
        if mins > lane.horizon:
            break                        # sorted, so the rest are further out
        catchable = mins >= lane.walk_min
        if catchable and first_catchable is None:
            first_catchable, state = mins, NEXT
        elif catchable:
            state = LATER
        else:
            state = MISSED

        x = int(round(DOOR_X + mins * ppm))

        # Lateness, under the road, as a length on the same axis: from where
        # the timetable put this bus to where it actually is. A faint rule with
        # a bright cap on the timetable end, rather than a solid bar -- five
        # minutes early is seventy pixels, and seventy solid pixels per bus
        # shouted louder than the buses did. The cap is what you read; the rule
        # only has to connect it to its bus. Missed buses get none of it: how
        # late a bus you cannot catch is running is not information.
        if aim is not None and state != MISSED:
            slip = (when - aim) / 60.0
            if abs(slip) >= LATE_FLOOR_MIN:
                rgb = C_LATE if slip > 0 else C_EARLY
                ax = int(round(DOOR_X + ((aim - clock) / 60.0) * ppm))
                x0, x1 = (x, ax) if ax > x else (ax, x)
                x0, x1 = max(STREET_X0, x0), min(W - 1, x1)
                if x1 > x0:
                    out[late_y, x0:x1:2] = _shade(rgb, 0.45)
                if STREET_X0 <= ax < W:
                    out[late_y - 1:late_y + 1, ax] = rgb

        img, mask = sprites.get((lane.route, state, mon),
                                sprites[(None, state, mon)])
        _blit_sprite(out, bus_y, x - BUS_W // 2, img, mask, xmin=STREET_X0)
        drawn += 1
        if drawn >= 8:
            break

    _lane_number(out, y0 + LANE_TEXT_Y, lane, clock, first_catchable)


def _lane_number(out, y, lane, clock, first_catchable):
    """The one number a lane carries, printed in the stretch it measures.

    It sits just inside the door, on top of the dotted walk, because that is
    what it measures: minutes before you have to start walking. Type over a
    dotted rule is unreadable, so it gets a dark plate under it -- one slice
    assignment, and worth it, because this number is the answer.
    """
    text, rgb = _lane_text(lane, clock, first_catchable)
    x = DOOR_X + 3
    # The plate stops one row short of the road on purpose. A row taller and it
    # erases the road, the first dots of the walk and the near end of the
    # lateness rule -- which for one afternoon made the 19's stop look as
    # though it were at the door.
    out[y - 1:y + GLYPH_H, x - 1:x + text_width(text) + 1] = C_BG
    blit_text(out, y, x, text, rgb)


def _lane_text(lane, clock, first_catchable):
    if first_catchable is not None:
        leave = first_catchable - lane.walk_min
        # Under a minute is NOW rather than "0": a lane reading 0 next to
        # another reading NOW invites the question which of the two is sooner.
        if leave < 1.0:
            return "NOW", C_URGENT
        return "%d" % int(leave), (C_URGENT if leave < 3.0 else C_TEXT)
    # Nothing catchable on the street. Say when the next one actually is,
    # rather than leaving the lane blank and ambiguous.
    for when, _aim, _mon in lane.buses:
        if (when - clock) / 60.0 >= lane.walk_min:
            return time.strftime("%H:%M", time.localtime(when)), C_DIM
    return "--", C_FAINT


def _header(out, clock, tag, tag_rgb, age_txt, stale):
    """The clock, the source tag, and the age when the age has become news."""
    right = W - 1
    stamp = time.strftime("%H:%M", time.localtime(clock))
    right -= text_width(stamp)
    blit_text(out, 0, right, stamp, C_TEXT)

    right -= 4 + text_width(tag)
    blit_text(out, 0, right, tag, C_STALE if stale else tag_rgb)

    # Age is only worth the columns once it is worth worrying about: a record
    # fetched ten minutes ago is the normal case and does not need announcing.
    if stale:
        text = age_txt + " OLD"
        right -= 4 + text_width(text)
        blit_text(out, 0, right, text, C_STALE)


# --------------------------------------------------------------------------
# The degraded state. A card rather than a blank panel or a traceback: the wall
# is in a room with people in it, and "nothing" is indistinguishable from
# "broken". Still a pure function of t, and still carrying the clock, so that
# even a no-data card is visibly alive.
# --------------------------------------------------------------------------

def _card(now0, title, detail, rgb):
    card = np.zeros((H, W, 3), np.uint8)
    card[:, :] = C_BG
    ty = H // 2 - GLYPH_H - 3
    blit_text(card, ty, (W - text_width(title)) // 2, title, rgb)
    blit_text(card, ty + GLYPH_H + 3, (W - text_width(detail)) // 2,
              detail, C_DIM)
    card[LANE_TOP:LANE_BOT, DOOR_X] = C_DOOR_DIM

    def render(t, frame):
        out = card.copy()
        stamp = time.strftime("%H:%M", time.localtime(now0 + t))
        blit_text(out, 0, W - 1 - text_width(stamp), stamp, C_DIM)
        return out
    return render


def main():
    ds.standalone(sys.modules[__name__], __doc__.split("\n", 1)[0], fps=20)


if __name__ == "__main__":
    main()
