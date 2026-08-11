#!/usr/bin/env python3
"""Checks for bikes.py that a screenshot cannot make.

This panel infers movement from two snapshots that contain no movement in
them, and almost every way it can be wrong is a way that still looks
convincing on a wall.

1. **The direction can be backwards.** Green runs towards downtown, and the
   whole claim of the panel is that green in the morning means people rode
   into the financial district. One sign error in `cumsum` or in the transport
   coupling and the panel is a fluent, confident lie, drawn at the right times
   of day with the right magnitudes. So the direction is asserted three ways:
   off the arithmetic, off the baked particle endpoints, and off the *pixels*,
   by counting which hue is on the panel while a synthetic city empties its
   hills into its downtown.
2. **The flux can fail to conserve.** `cumsum(net)` is only the number of
   bikes that had to cross each distance if the net changes sum to zero, and
   the docked fleet is not closed. If the imbalance correction is wrong the
   panel invents traffic at the city limit, which looks like a busy afternoon.
3. **The headline can double or halve.** `mov` counts both ends of a move,
   so the panel halves it. Forgetting to is a two-times error nobody can see.
4. **The replay can lie about time.** The window is anchored on the newest
   bucket the record actually holds, not on the clock, and a gap must stay a
   gap in the strip rather than being joined across.
5. **Cold start can be a blank panel.** The flow needs two fetches. A wall
   that booted ten minutes ago has one, and what it draws then is a designed
   state that has to be checked like any other.
6. **The fetcher's differencing can break benignly and silently.** A doubled
   pass, a missed pass, a backwards clock and a station being installed all
   have to degrade in a stated way, and none of them raises.

So the methodology is: build synthetic cities whose answer is known by
arithmetic before anything is drawn, assert the panel against that number,
then repeat the measurement on a city built the other way round and require
the answer to come out the other way. Words are read back off the rendered
pixels rather than trusted to have been computed. Every data state is run in
a process of its own, because `ftdata.CACHE_DIR` binds at import.

    $ python3 scripts/test-bikes.py                     # uses the live cache
    $ python3 scripts/test-bikes.py --cache-dir /tmp/c  # or a pointed one
    $ python3 scripts/test-bikes.py --shot out.png      # and a 3x screenshot

Only `test_live` needs a populated cache; everything else builds its own.
Populate it with `python3 ftdata.py --once --only baywheels`, twice, ten
minutes apart -- one pass alone gives you the cold-start panel.
"""

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import bikes                                                   # noqa: E402
import demoscene as ds                                         # noqa: E402
import ftdata                                                  # noqa: E402

FAILED = []
PASSED = [0]

N_STATIONS = 383
BINS = ftdata.BIKES_FLOW_BINS
BUCKET = ftdata.BIKES_HIST_BUCKET
KM = ftdata.BIKES_FLOW_KM


def check(name, ok, detail=""):
    PASSED[0] += 1
    if ok:
        print("  ok   %-58s %s" % (name, detail))
    else:
        print("  FAIL %-58s %s" % (name, detail))
        FAILED.append(name)


def opts(**kw):
    """The demo's defaults with the cache re-read switched off.

    `reload=0` is what makes render a pure function of t: with it on, the demo
    asks the wall clock whether to go back to the file, exactly as caiso does.
    """
    kw.setdefault("reload", 0.0)
    return ds.options(bikes, **kw)


def frames(args, n=8):
    """Render `n` frames in order from a fresh build. Never sample sparsely."""
    r = bikes.build(args)
    out = None
    for i in range(n):
        out = r(i / 20.0, i)
    return r, out.copy()


def contains_text(frame, s, thresh=90, scales=(1, 2), bg_max=0.30):
    """Is this string drawn anywhere on the frame, at any position or size?

    Reading the words back off the panel is the only way to be sure the honest
    message reached it rather than merely being computed. The counters between
    the strokes have to be dark as well: this panel has a terrain band and a
    filled strip on it, and a matcher that only asks "are the strokes lit"
    answers yes to most of the language somewhere inside the landscape. The
    caption's halo darkens exactly those counters, which is what lets the
    threshold here stay tight.
    """
    lit = frame.max(axis=2) >= thresh
    h, w = lit.shape
    for scale in scales:
        m = bikes.text_mask(s, scale)
        gh, gw = m.shape
        if gh > h or gw > w:
            continue
        for y in range(h - gh + 1):
            row = lit[y:y + gh]
            for x in range(w - gw + 1):
                win = row[:, x:x + gw]
                if not np.array_equal(win & m, m):
                    continue
                if (win & ~m).mean() <= bg_max:
                    return True
    return False


def _count_palette(region, pal):
    """How many pixels of `region` are exactly one of `pal`'s colours.

    Level zero of every palette block is black, and black is most of the
    panel, so it is dropped before the comparison -- counting it would answer
    "is the panel mostly dark", which it is.
    """
    flat = region.reshape(-1, 3)
    total = 0
    for rgb in pal:
        if not rgb.any():
            continue
        total += int((flat == rgb).all(axis=1).sum())
    return total


def hue_counts(frame, lay):
    """(green pixels, violet pixels) in the map region, by nearest swarm hue.

    Counted as "is this pixel more like C_IN than C_OUT, and lit at all",
    rather than by exact match: a particle is drawn at one of eight brightness
    levels and only the brightest is the palette colour itself.
    """
    reg = frame[lay.map_y:lay.map_bot + 1].astype(np.int32)
    lit = reg.max(axis=2) > 40
    # Green minus violet, which for these two colours is dominated by the
    # blue channel: C_IN is (128, 246, 132) and C_OUT is (196, 130, 255).
    score = reg[:, :, 1] - reg[:, :, 2]
    return int((lit & (score > 30)).sum()), int((lit & (score < -30)).sum())


# --------------------------------------------------------------------------
# A synthetic San Francisco, and a synthetic day over it.
#
# The city is a function of distance from downtown so that every geometric
# assertion below has an arithmetic answer: elevation rises to a crest at six
# kilometres and falls into the flats beyond, which is the real shape and is
# also the shape whose *median* the panel draws.
#
# The day is a commute: bikes flow from the outer bands to the inner ones in
# the morning and back in the evening, with the amplitude of a real one. It is
# written as net change per band, which is exactly what the record stores, so
# nothing here has to model a station.
# --------------------------------------------------------------------------

def city(n=N_STATIONS, dry=(), jammed=(), closed=()):
    """Parallel arrays for a synthetic San Francisco, ascending by distance."""
    r = np.linspace(0.0, 1.0, n)
    dist = np.round(r * (KM * 1000.0 - 100.0)).astype(int)
    # A crest at six kilometres, plus a repeatable jitter so the quartiles the
    # panel draws have something to be quartiles of.
    base = 3.0 + 95.0 * np.sin(np.pi * np.clip(r * 1.15, 0, 1)) ** 1.6
    jit = 26.0 * np.sin(np.arange(n) * 2.399963) ** 2
    elev = np.round(np.clip(base + jit - 13.0, 2.0, 160.0)).astype(int)
    fill = np.full(n, 45)
    free = np.full(n, 9)
    openf = np.ones(n, int)
    for i in dry:
        fill[i] = 0
    for i in jammed:
        free[i] = 0
    for i in closed:
        openf[i] = 0
    return dist, elev, fill, free, openf


def tracks_for(hour, net):
    """Observed free-ebike journeys for one bucket, in hundreds of metres.

    A handful, running the same way the net flow does, because that is what a
    real evening looks like: two movers in four minutes at ten at night on the
    live feed, more at the peaks. The panel must not need many of these to be
    legible, and the tests must not pretend there are many.
    """
    n = int(round(abs(sum(abs(v) for v in net)) / 26.0))
    inbound = sum(np.cumsum(net)) > 0
    out = []
    for i in range(n):
        far = 18 + (i * 7) % 60
        near = 3 + (i * 5) % 12
        out.extend([far, near] if inbound else [near, far])
    return out


def commute(hour):
    """(net change per band, gross |change|) for one ten-minute bucket.

    Positive net is a band gaining docked bikes. In the morning the inner
    bands gain and the outer ones lose, which is people riding to work; in the
    evening it reverses. The profile peaks at 8 and at 18 and is nearly flat
    at four in the morning, which is what the strip is meant to show.
    """
    k = np.arange(BINS, dtype=np.float64)
    inner = np.exp(-((k - 2.0) / 3.5) ** 2)
    outer = np.exp(-((k - 22.0) / 9.0) ** 2)
    inner /= inner.sum()
    outer /= outer.sum()
    morning = math.exp(-((hour - 8.3) / 1.5) ** 2)
    evening = math.exp(-((hour - 17.8) / 1.7) ** 2)
    amp = 150.0 * morning - 130.0 * evening
    net = np.round(amp * (inner - outer)).astype(int)
    # Churn is always several times the net: most rides are short and cancel
    # inside a band. `mov` counts both ends, hence the two.
    gross = int(2 * (np.abs(net).sum() * 0.5 + 26 + 40 * (morning + evening)))
    return net.tolist(), gross


def synthetic(cache_dir, n=N_STATIONS, hours=12.0, fetched_ago=120.0,
              gaps=(), no_flow=False, dry=(), jammed=(), closed=(),
              reverse=False, flat=False, mangle=None, descending=False,
              at=None, no_tracks=False):
    """Write a baywheels record by hand. Returns (path, truth dict).

    `at` moves the *data* -- what o'clock the buckets claim to be, which is
    what makes a synthetic morning rush possible -- while `fetched_ago` moves
    only the record's freshness against the real wall clock. Conflating the
    two is a trap this file fell into once: a record whose buckets were dated
    eight in the morning was also dated eight in the morning, so on an evening
    test run the demo refused it as thirteen hours old and every direction
    check silently had nothing to measure.
    """
    now = time.time() if at is None else float(at)
    fetched_at = time.time() - fetched_ago
    dist, elev, fill, free, openf = city(n, dry, jammed, closed)
    if descending:
        dist = dist[::-1].copy()

    top = float(int(now // BUCKET) * int(BUCKET))
    nb = int(hours * 3600.0 / BUCKET)
    t, mov, dt, flow = [], [], [], []
    trk, seen, gone, came = [], [], [], []
    for i in range(nb):
        bt = top - (nb - 1 - i) * BUCKET
        t.append(bt)
        if i in gaps or no_flow:
            mov.append(None)
            dt.append(None)
            flow.append(None)
            trk.append(None)
            seen.append(None)
            gone.append(None)
            came.append(None)
            continue
        hour = time.localtime(bt).tm_hour + time.localtime(bt).tm_min / 60.0
        net, gross = commute(hour)
        if reverse:
            net = [-v for v in net]
        if flat:
            net = [0] * BINS
        mov.append(gross)
        dt.append(BUCKET)
        flow.append(net)
        trk.append([] if no_tracks else tracks_for(hour, net))
        seen.append(600)
        gone.append(19)
        came.append(13)

    loose = np.round(140.0 * np.exp(-((np.arange(BINS) - 12.0) / 8.0) ** 2))
    payload = {
        "as_of": now, "region": "San Francisco",
        "bbox": list(ftdata.BIKES_BBOX), "downtown": list(ftdata.BIKES_DOWNTOWN),
        "n": n,
        "dist_m": [int(v) for v in dist], "elev_m": [int(v) for v in elev],
        "fill_pct": [int(v) for v in fill],
        "free_docks": [int(v) for v in free],
        "open": [int(v) for v in openf],
        "loose_bins": [int(v) for v in loose],
        "totals": {"stations": n, "closed": len(closed), "capacity": n * 23,
                   "bikes": int(fill.sum() * 23 // 100), "ebikes": 1500,
                   "free_docks": int(free.sum()), "empty": len(dry),
                   "jammed": len(jammed), "loose": int(loose.sum()),
                   "loose_unavailable": 0},
        "altitude_m": {"fleet": 21.5, "docks": 28.0,
                       "low": float(elev.min()), "high": float(elev.max())},
        "flow": {"bins": BINS, "km": KM, "min_dt": ftdata.BIKES_FLOW_MIN_DT,
                 "max_dt": ftdata.BIKES_FLOW_MAX_DT,
                 "track_m": ftdata.BIKES_TRACK_MIN_M,
                 "track_max": ftdata.BIKES_TRACK_MAX,
                 "track_unit_m": ftdata.BIKES_TRACK_UNIT_M},
        "interpolated": 0,
        "hist": {"t": t, "mov": mov, "dt": dt, "flow": flow,
                 "trk": trk, "seen": seen, "gone": gone, "came": came,
                 "fleet_m": [21.5] * nb, "docks_m": [28.0] * nb,
                 "bikes": [2700] * nb, "empty": [len(dry)] * nb,
                 "loose": [600] * nb, "bucket": BUCKET, "hours": hours,
                 "bins": BINS, "n": nb},
        "base": {"at": now, "sid": "0" * 6 * n, "bikes": [10] * n},
        "loose_base": {"at": now, "k": ["0" * 8] * 4,
                       "lat": [377700] * 4, "lon": [-1224000] * 4},
        "units": {}, "sources": [],
    }
    if mangle is not None:
        mangle(payload)
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, "baywheels.json")
    with open(path, "w") as fh:
        json.dump({"name": "baywheels", "source": "synthetic",
                   "ttl": ftdata.BIKES_TTL, "fetched_at": fetched_at,
                   "payload": payload}, fh)
    return path, {"dist": dist, "elev": elev, "t": t, "mov": mov, "dt": dt,
                  "flow": flow, "nb": nb}


# --------------------------------------------------------------------------
# 1. The promises: no network, and a terrain bake that exists.
# --------------------------------------------------------------------------

def test_no_network():
    print("\nthe network promise")
    before = set(sys.modules)
    ftdata.load("baywheels", tempfile.mkdtemp(prefix="bikes-net"))
    new = set(sys.modules) - before
    bad = [m for m in new
           if m.split(".")[0] in ("urllib", "http", "socket", "ssl", "requests")]
    check("ftdata.load() imports no network module", not bad, ",".join(bad))
    src = open(os.path.join(HERE, "bikes.py")).read()
    imported = [m for m in ("urllib", "http.client", "socket", "requests",
                            "ssl") if ("import " + m) in src]
    check("bikes.py does not import one either", not imported,
          ",".join(imported))


def test_terrain_bake():
    print("\nthe committed elevation bake")
    path = os.path.join(HERE, ftdata.BIKES_TERRAIN)
    check("bikes-terrain.npz is in the tree", os.path.exists(path), path)
    with np.load(path, allow_pickle=True) as z:
        ids, elev = z["ids"], z["elev"]
        check("...and carries an elevation per station id",
              len(ids) == len(elev) and len(ids) > 500,
              "%d stations" % len(ids))
        check("...whose range is a city and not a continent",
              0.0 <= float(elev.min()) and float(elev.max()) < 400.0,
              "%.1f to %.1f m" % (elev.min(), elev.max()))


# --------------------------------------------------------------------------
# 2. The axis. Downtown is on the left, and that has to be true in the record,
# in the layout arithmetic and in the pixels -- three places that could each
# be right on their own while disagreeing with each other.
# --------------------------------------------------------------------------

def test_axis():
    print("\ndowntown is on the left, and the city climbs away from it")
    tmp = tempfile.mkdtemp(prefix="bikes-axis")
    try:
        _p, truth = synthetic(tmp)
        r, f = frames(opts(cache_dir=tmp), 30)
        lay, rec = r.layout, r.state["rec"]
        check("the record is sorted ascending by distance",
              bool(np.all(np.diff(rec["dist"]) >= -1.0)))
        ridge = r.state["ridge"]
        # Rows count downward, so a higher city is a *smaller* row number.
        left = float(ridge[:lay.w // 8].mean())
        crest = float(ridge[lay.w // 2 - 20:lay.w // 2 + 20].mean())
        check("the left edge of the landscape is the lowest part of it",
              left > crest + 4, "left row %.1f, crest row %.1f" % (left, crest))
        check("...and every column of it is inside the map region",
              int(ridge.min()) >= lay.map_y and int(ridge.max()) <= lay.map_bot,
              "rows %d..%d in %d..%d" % (ridge.min(), ridge.max(),
                                         lay.map_y, lay.map_bot))
        check("the panel names both ends of the axis",
              contains_text(f, "DOWNTOWN") and contains_text(f, "KM OUT"))
        # A dock at 11.9 km must land in the last few columns; getting the
        # scale wrong by the width of one band is invisible on a wall.
        col = int(rec["dist"][-1] / (rec["km_max"] * 1000.0) * (lay.w - 1))
        check("the furthest dock lands at the right-hand edge",
              col > lay.w - 8, "column %d of %d" % (col, lay.w))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 3. The inference. This is the section that matters: the flux, the transport
# and the sign of the thing.
# --------------------------------------------------------------------------

def test_flux_conserves():
    print("\nthe flux is a conserved quantity")
    rng = np.random.default_rng(7)
    bad_end, bad_sum = [], []
    for trial in range(200):
        net = rng.integers(-9, 10, BINS).astype(np.float64)
        weight = rng.integers(1, 20, BINS).astype(np.float64)
        b = bikes.balance(net, weight)
        if abs(float(b.sum())) > 1e-6:
            bad_sum.append(trial)
        if abs(float(np.cumsum(b)[-1])) > 1e-6:
            bad_end.append(trial)
    check("balancing removes the docked fleet's own gain or loss",
          not bad_sum, "%d of 200 trials left a residual" % len(bad_sum))
    check("...so the flux returns to zero at the city limit",
          not bad_end, "%d of 200 trials did not" % len(bad_end))

    # And the imbalance really is spread by dock capacity, not evenly: a band
    # with twice the docks should absorb twice as much of it.
    net = np.zeros(BINS)
    net[0] = 10.0
    weight = np.ones(BINS)
    weight[1] = 3.0
    b = bikes.balance(net, weight)
    take = -(b - net)
    check("...and the imbalance is spread in proportion to dock capacity",
          abs(take[1] / take[2] - 3.0) < 1e-6,
          "band with 3x the docks took %.2fx the correction"
          % (take[1] / take[2]))


def test_transport_direction():
    print("\nthe transport runs the way the counts say it does")
    # Downtown gains, the hills lose: every journey must run inward.
    net = np.zeros(BINS)
    net[1] = 40.0
    net[25] = -40.0
    a, b, mass = bikes.transport(net, 120)
    check("mass moved equals what the filling bands gained",
          abs(mass - 40.0) < 1e-6, "%.1f bikes" % mass)
    check("...spread over the particles asked for", len(a) == 120,
          "%d particles" % len(a))
    check("every particle leaves the emptying band",
          bool(np.all(a == 25)), "sources %s" % np.unique(a))
    check("...and arrives at the filling one",
          bool(np.all(b == 1)), "sinks %s" % np.unique(b))
    check("...which is inward, towards downtown",
          bool(np.all(b < a)))

    # The inverse, so the check is about the arithmetic and not about which
    # end of the array happened to be positive.
    a2, b2, _m = bikes.transport(-net, 120)
    check("reversing the counts reverses every journey",
          bool(np.all(b2 > a2)), "sources %s sinks %s"
          % (np.unique(a2), np.unique(b2)))

    # Monotone coupling: two sources and two sinks must not cross.
    # Two sources and two sinks, interleaved so that the two possible
    # matchings have very different costs: 10->12 with 30->32 is four bands
    # of travel, 10->32 with 30->12 is forty. The monotone coupling must pick
    # the first, and a coupling that matched at random would average both.
    net = np.zeros(BINS)
    net[10], net[30] = -10.0, -10.0
    net[12], net[32] = 10.0, 10.0
    a3, b3, _m = bikes.transport(net, 400)
    order = np.argsort(a3, kind="stable")
    check("the coupling never crosses itself",
          bool(np.all(np.diff(b3[order]) >= 0)),
          "nearest source matched to nearest sink")
    travel = float(np.abs(a3 - b3).mean())
    check("...and it is the shorter of the two matchings available",
          travel < 4.0, "mean %.1f bands travelled, against 20 if crossed"
          % travel)


def test_headline_arithmetic():
    print("\nthe headline is bikes an hour and is halved exactly once")
    tmp = tempfile.mkdtemp(prefix="bikes-head")
    try:
        synthetic(tmp)
        r, _f = frames(opts(cache_dir=tmp, step=3600.0), 8)
        hist = r.state["rec"]["hist"]
        bad = []
        for s in r.state["steps"]:
            if s["rate"] is None:
                continue
            sel = (hist["t"] >= s["t0"]) & (hist["t"] < s["t1"])
            want = float(hist["mov"][sel].sum()) * 0.5 * 3600.0 \
                / float(hist["dt"][sel].sum())
            if abs(want - s["rate"]) > 1e-3:
                bad.append((want, s["rate"]))
        check("every step's rate is mov/2 scaled to an hour", not bad,
              "%d steps disagreed" % len(bad))
        peak = max(s["rate"] for s in r.state["steps"] if s["rate"])
        check("...and a rush hour is a four-figure number", 400 < peak < 9000,
              "peak %.0f bikes/h" % peak)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_direction_on_the_panel():
    print("\nthe direction reaches the pixels, and reverses when the day does")
    tmp = tempfile.mkdtemp(prefix="bikes-dir")
    try:
        # A day pinned to nine in the morning: every bucket is inbound.
        morning = os.path.join(tmp, "am")
        at = _at_hour(8)
        synthetic(morning, hours=2.0, at=at)
        r, _f = frames(opts(cache_dir=morning, at="%f" % at, hours=2.0), 8)
        s = [x for x in r.state["steps"] if x["rate"] is not None][-1]
        check("a morning of counts reads as inbound", s["pull"] > 0.4,
              "pull %+.2f bands per bike" % s["pull"])
        check("...and its particles are baked running left",
              float(s["flow"]["dx"].mean()) < 0,
              "mean dx %+.1f px" % s["flow"]["dx"].mean())
        gi, vi = _hue_over_step(r, 8)
        check("...and the panel is green rather than violet", gi > 3 * vi + 20,
              "%d green, %d violet pixels" % (gi, vi))
        check("...and says so in words",
              contains_text(_settle(r, 8), "INBOUND"))
        check("...and does not also say the opposite",
              not contains_text(_settle(r, 8), "OUTBOUND"))

        # The same city with every count negated. Nothing else changes.
        evening = os.path.join(tmp, "pm")
        synthetic(evening, hours=2.0, at=at, reverse=True)
        r2, _f2 = frames(opts(cache_dir=evening, at="%f" % at, hours=2.0), 8)
        s2 = [x for x in r2.state["steps"] if x["rate"] is not None][-1]
        check("negating every count reverses the reading", s2["pull"] < -0.4,
              "pull %+.2f" % s2["pull"])
        check("...and the particles run right",
              float(s2["flow"]["dx"].mean()) > 0,
              "mean dx %+.1f px" % s2["flow"]["dx"].mean())
        g2, v2 = _hue_over_step(r2, 8)
        check("...and the panel is violet rather than green", v2 > 3 * g2 + 20,
              "%d green, %d violet pixels" % (g2, v2))
        check("...and says OUTBOUND", contains_text(_settle(r2, 8), "OUTBOUND"))

        # A city where nothing moves anywhere must not pick a side.
        still = os.path.join(tmp, "flat")
        synthetic(still, hours=2.0, at=at, flat=True, no_tracks=True)
        r3, f3 = frames(opts(cache_dir=still, at="%f" % at, hours=2.0), 40)
        s3 = [x for x in r3.state["steps"] if x["rate"] is not None][-1]
        check("a day with no net change reads as balanced",
              abs(s3["pull"]) <= 0.4 and s3["flow"] is None,
              "pull %+.2f, flow=%s" % (s3["pull"], s3["flow"]))
        check("...and says BALANCED rather than a direction",
              contains_text(f3, "BALANCED"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _at_hour(hour):
    """An epoch at `hour` o'clock local, today. The commute needs a time."""
    lt = list(time.localtime())
    lt[3], lt[4], lt[5] = hour, 30, 0
    return time.mktime(tuple(lt))


def _settle(r, step_frames):
    """A frame from the middle of the current step, rendered in order."""
    out = None
    for i in range(step_frames):
        out = r(i / 20.0, i)
    return out.copy()


def _hue_over_step(r, nframes):
    """Green and violet pixel counts summed over the first `nframes`."""
    gi = vi = 0
    for i in range(nframes):
        f = r(i / 20.0, i)
        g, v = hue_counts(f, r.layout)
        gi += g
        vi += v
    return gi, vi


# --------------------------------------------------------------------------
# 3b. The observed layer, which is the one thing on this panel that was
# actually watched happening, and the privacy design that goes with it.
# --------------------------------------------------------------------------

def test_observed_layer():
    print("\nobserved ebike journeys are drawn, and drawn differently")
    tmp = tempfile.mkdtemp(prefix="bikes-obs")
    try:
        at = _at_hour(8)
        synthetic(tmp, hours=2.0, at=at)
        args = opts(cache_dir=tmp, at="%f" % at, hours=2.0)
        r = bikes.build(args)
        s = [x for x in r.state["steps"] if x["rate"] is not None][-1]
        check("a step with tracks in the record bakes comets", s["obs"],
              "%d tracks" % s["tracks"])
        check("...running the same way the morning does",
              float(s["obs"]["dx"].mean()) < 0,
              "mean dx %+.1f px" % s["obs"]["dx"].mean())
        check("...and there are far fewer of them than inferred particles",
              s["tracks"] < len(s["flow"]["x0"]),
              "%d observed against %d inferred"
              % (s["tracks"], len(s["flow"]["x0"])))
        check("...flying in a lane of their own above the inferred field",
              int(s["obs"]["yj"].min()) > int(s["flow"]["yj"].max()),
              "rows %d..%d above %d..%d"
              % (s["obs"]["yj"].min(), s["obs"]["yj"].max(),
                 s["flow"]["yj"].min(), s["flow"]["yj"].max()))

        # Off the pixels, and by exact palette match rather than by "is it
        # bright": the caption is also bright and also lives in the map region,
        # and a test that counted near-white pixels would pass on the word
        # BIKES alone. The observed blocks are the last two of the four.
        lit = _settle(r, 20)
        obs_pal = r.palette[2 * bikes.FADE_LEVELS:]
        reg = lit[r.layout.map_y:r.layout.map_bot + 1]
        hit = _count_palette(reg, obs_pal)
        check("...and they reach the panel in their own colours", hit > 0,
              "%d observed pixels" % hit)
        check("the panel says how many were seen",
              contains_text(lit, "SEEN TO MOVE"))
        check("...and which fleet they came from",
              contains_text(lit, "FREE EBIKES"))
        check("...and that the rest is inferred",
              contains_text(lit, "NOT TRIPS"))

        # And with the layer switched off, none of it is on the panel.
        r2, f2 = frames(opts(cache_dir=tmp, at="%f" % at, hours=2.0,
                             no_seen=True), 20)
        reg2 = f2[r2.layout.map_y:r2.layout.map_bot + 1]
        left = _count_palette(reg2, obs_pal)
        check("--no-seen removes them entirely", left == 0,
              "%d observed pixels left" % left)

        # A record whose free_bike_status failed keeps the inferred field.
        bare = os.path.join(tmp, "bare")
        synthetic(bare, hours=2.0, at=at, no_tracks=True)
        r3, f3 = frames(opts(cache_dir=bare, at="%f" % at, hours=2.0), 20)
        s3 = [x for x in r3.state["steps"] if x["rate"] is not None][-1]
        check("a bucket with no ebike feed still draws the inferred field",
              s3["obs"] is None and s3["flow"] is not None)
        check("...and does not claim journeys it does not have",
              not contains_text(f3, "SEEN TO MOVE"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_track_differencing():
    print("\nthe fetcher observes journeys by the printed number, not bike_id")
    # Four bikes: one sits still, one jitters by GPS, one rides a kilometre,
    # one vanishes. A fifth appears.
    def anon(nm):
        return ftdata._bikes_anon(nm)
    lat0, lon0 = 37.7800, -122.4200
    old_k = [anon("100-001"), anon("100-002"), anon("100-003"), anon("100-004")]
    base = {"loose_base": {
        "at": 1000.0, "k": old_k,
        "lat": [int(lat0 * 1e4)] * 4,
        "lon": [int(lon0 * 1e4)] * 4}}
    keys = [anon("100-001"), anon("100-002"), anon("100-003"), anon("100-009")]
    lats = np.array([lat0, lat0 + 0.00005, lat0 + 0.009, lat0])
    lons = np.array([lon0, lon0, lon0, lon0])
    trk, seen, gone, came, nxt = ftdata._bikes_tracks(
        base, keys, lats, lons, 1600.0)
    check("bikes present in both snapshots are the denominator", seen == 3,
          "seen %d" % seen)
    check("a bike that vanished is counted, not drawn", gone == 1,
          "gone %d" % gone)
    check("a bike that appeared is counted, not drawn", came == 1,
          "came %d" % came)
    check("only the bike that actually went somewhere is a journey",
          trk is not None and len(trk) == 2,
          "%d numbers = %d journeys" % (len(trk or []), len(trk or []) // 2))
    check("...and GPS jitter under the threshold is not one",
          trk is not None and len(trk) == 2,
          "threshold %.0f m" % ftdata.BIKES_TRACK_MIN_M)

    got = ftdata._bikes_tracks(None, keys, lats, lons, 1600.0)
    check("no baseline declines rather than inventing journeys",
          got[0] is None)
    got = ftdata._bikes_tracks(base, keys, lats, lons, 1030.0)
    check("a doubled pass declines and keeps the baseline",
          got[0] is None and got[4]["at"] == 1000.0)
    got = ftdata._bikes_tracks(base, keys, lats, lons, 9000.0)
    check("two hours apart declines and resets", got[0] is None
          and got[4]["at"] == 9000.0)


def test_privacy():
    print("\nthe panel and the record carry no bike number anywhere")
    tmp = tempfile.mkdtemp(prefix="bikes-priv")
    try:
        token = ftdata._bikes_anon("190-591")
        check("a printed number becomes an opaque token",
              token and "190" not in token and "591" not in token
              and len(token) == 8, "%r -> %r" % ("190-591", token))
        check("...deterministically, or nothing could be matched",
              token == ftdata._bikes_anon("190-591"))
        check("...and two bikes do not collide",
              token != ftdata._bikes_anon("190-592"))

        # The record the fetcher writes must contain no NNN-NNN string
        # anywhere, at any depth. Checked against the serialised JSON, which
        # is what actually lands on disk.
        at = _at_hour(8)
        synthetic(tmp, hours=2.0, at=at)
        blob = open(os.path.join(tmp, "baywheels.json")).read()
        hits = re.findall(r'"\d{3}-\d{3}"', blob)
        check("no bike number survives into the record", not hits,
              ",".join(hits[:4]))

        # And the history -- the part that accumulates -- carries no
        # identifier of any kind, so no trip history can be reconstructed from
        # a stolen record however long the fetcher has been running.
        h = json.loads(blob)["payload"]["hist"]
        ident = [k for k in h if k in ("k", "sid", "name", "bike_id")]
        check("the rolling history carries no identifier at all", not ident,
              ",".join(ident))
        keys = set()
        for row in h["trk"]:
            for v in (row or []):
                keys.add(type(v).__name__)
        check("...only integer positions", keys <= {"int"}, str(sorted(keys)))

        # Subscript or .get(), not the bare words: the module docstring
        # explains at length what `bike_id` and `name` are and why one of them
        # is not stored, and a substring check on the prose would forbid
        # documenting the decision.
        src = open(os.path.join(HERE, "bikes.py")).read()
        reads = re.findall(r'(?:\[|\.get\()\s*["\'](?:name|bike_id)["\']',
                           src)
        check("bikes.py never reads a bike name or id", not reads,
              ",".join(reads[:4]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 4. Time. The replay window, the strip, and the gaps that have to stay gaps.
# --------------------------------------------------------------------------

def test_window_and_gaps():
    print("\nthe replay window is what the record holds, and gaps stay gaps")
    tmp = tempfile.mkdtemp(prefix="bikes-time")
    try:
        full = os.path.join(tmp, "full")
        synthetic(full, hours=12.0)
        r, f = frames(opts(cache_dir=full), 8)
        check("twelve hours of buckets replays as twelve hours",
              abs(r.state["span"] - 12 * 3600.0) < 3600.0,
              "%.1f h" % (r.state["span"] / 3600.0))
        check("...in twelve steps of an hour", len(r.state["steps"]) == 12,
              "%d steps" % len(r.state["steps"]))
        check("...and the panel says how far back it goes",
              contains_text(f, "REPLAY OF LAST 12H"))

        # Forty minutes of history: the window must shrink to it rather than
        # replaying eleven hours of nothing.
        short = os.path.join(tmp, "short")
        synthetic(short, hours=0.7)
        r2, f2 = frames(opts(cache_dir=short), 8)
        check("forty minutes of buckets replays as forty minutes",
              r2.state["span"] <= 3600.0,
              "%.0f min" % (r2.state["span"] / 60.0))
        check("...and the panel says so rather than claiming twelve hours",
              not contains_text(f2, "REPLAY OF LAST 12H"))

        # A hole in the middle. The step that covers it must say so in words
        # rather than drawing an empty hour as a quiet one -- an earlier draft
        # of this panel carried a twelve-hour bar chart where the hole was a
        # blank column, and taking the chart out for the sake of the picture
        # means the caption is now the only thing that reports it.
        holed = os.path.join(tmp, "holed")
        gaps = tuple(range(20, 44))
        _p, truth = synthetic(holed, hours=12.0, gaps=gaps)
        r3, _f3 = frames(opts(cache_dir=holed), 8)
        empty = [s for s in r3.state["steps"] if s["rate"] is None]
        check("a four-hour hole leaves steps with no data in them",
              len(empty) >= 2, "%d of %d steps"
              % (len(empty), len(r3.state["steps"])))
        # Drive the replay to one of them and read the panel.
        idx = r3.state["steps"].index(empty[0])
        args3 = opts(cache_dir=holed)
        rr = bikes.build(args3)
        per = args3.cycle / len(rr.state["steps"])
        at_t = (idx + 0.5) * per
        out = None
        for i in range(int(at_t * 20) + 1):
            out = rr(i / 20.0, i)
        check("...and the panel says that step was never fetched",
              contains_text(out, "NEVER FETCHED"))
        check("...rather than drawing it as a quiet hour",
              not contains_text(out, "BALANCED"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_cold_start():
    print("\ncold start is a designed state and not an empty panel")
    tmp = tempfile.mkdtemp(prefix="bikes-cold")
    try:
        synthetic(tmp, no_flow=True)
        r, f = frames(opts(cache_dir=tmp), 60)
        check("a record with no differences in it still draws the city",
              r.state["rec"] is not None and r.state["cold"])
        check("...says LEARNING FLOW", contains_text(f, "LEARNING FLOW"))
        check("...says why", contains_text(f, "NEEDS TWO FETCHES"))
        check("...and draws no swarm at all",
              all(s["flow"] is None and s["obs"] is None
                  for s in r.state["steps"]),
              "%d steps" % len(r.state["steps"]))
        check("...but is not a blank panel",
              (f.max(axis=2) > 0).sum() > 2000,
              "%d lit pixels" % (f.max(axis=2) > 0).sum())
        check("...and never claims a rate it does not have",
              not contains_text(f, "BIKES/H"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 5. The fetcher's own arithmetic, which no screenshot reaches.
# --------------------------------------------------------------------------

def _sid(ids):
    return "".join(hashlib.sha1(s.encode()).hexdigest()[:6] for s in ids)


def test_fetcher_differencing():
    print("\nthe fetcher's differencing, and its four benign failures")
    ids = ["s%03d" % i for i in range(12)]
    sid = _sid(ids)
    bins = np.array([i // 3 for i in range(12)])
    was = [5] * 12
    now = [5] * 12
    now[0] = 2                      # band 0 lost three
    now[11] = 8                     # band 3 gained three

    base = {"at": 1000.0, "sid": sid, "bikes": was}
    flow, mov, dt, nxt = ftdata._bikes_flow({"base": base}, sid, now, bins,
                                            1000.0 + 600.0)
    check("a ten-minute difference is computed", flow is not None)
    check("...with the change in the right bands",
          flow is not None and flow[0] == -3 and flow[3] == 3, str(flow))
    check("...and mov counting both ends of every move", mov == 12,
          "mov %s for six bikes moved" % mov)
    check("...over the interval the feed actually spanned", dt == 600.0)
    check("...and the next baseline is this snapshot",
          nxt["at"] == 1600.0 and nxt["bikes"] == now)

    got = ftdata._bikes_flow(None, sid, now, bins, 1600.0)
    check("no previous record declines rather than inventing one",
          got[0] is None and got[1] is None)

    got = ftdata._bikes_flow({"base": base}, sid, now, bins, 1000.0 + 30.0)
    check("a doubled pass thirty seconds later declines", got[0] is None)
    check("...and keeps the old baseline so the next pass is full length",
          got[3]["at"] == 1000.0, "kept at=%.0f" % got[3]["at"])

    got = ftdata._bikes_flow({"base": base}, sid, now, bins, 1000.0 + 9000.0)
    check("two and a half hours apart declines rather than joining across",
          got[0] is None)
    check("...and resets the baseline to now", got[3]["at"] == 10000.0)

    got = ftdata._bikes_flow({"base": base}, sid, now, bins, 900.0)
    check("a clock that jumped backwards declines", got[0] is None)
    check("...and resets rather than storing a negative interval",
          got[3]["at"] == 900.0)

    # A station installed since the last pass. The stations in both snapshots
    # must still be differenced; matching by array position instead would
    # shift every station past the new one and invent a citywide flow.
    ids2 = ids[:6] + ["NEW"] + ids[6:]
    now2 = now[:6] + [7] + now[6:]
    bins2 = np.array([min(3, i // 3) for i in range(13)])
    flow2, mov2, _dt2, _n2 = ftdata._bikes_flow({"base": base}, _sid(ids2),
                                                now2, bins2, 1600.0)
    check("a station installed since the last pass costs nothing",
          flow2 is not None and mov2 == 12,
          "mov %s, flow %s" % (mov2, flow2))

    check("the identity row is six hex characters a station",
          len(sid) == 6 * len(ids) and set(sid) <= set("0123456789abcdef"),
          "%d chars for %d stations" % (len(sid), len(ids)))


def test_history_is_bounded():
    print("\nthe rolling series is bounded, ordered and idempotent")
    keys = ("fleet_m", "docks_m", "bikes", "empty", "loose", "mov", "dt",
            "flow")
    prev = None
    t0 = 1_700_000_000.0
    for i in range(400):
        sample = dict.fromkeys(keys, 1)
        sample["flow"] = [0] * BINS
        prev = {"hist": ftdata._bikes_history(prev, sample,
                                              t0 + i * BUCKET)}
    h = prev["hist"]
    check("400 passes do not grow the series without bound",
          h["n"] <= ftdata.BIKES_HIST_MAX, "%d entries" % h["n"])
    check("...and it covers no more than its stated hours",
          h["t"][-1] - h["t"][0] <= ftdata.BIKES_HIST_HOURS * 3600.0,
          "%.1f h" % ((h["t"][-1] - h["t"][0]) / 3600.0))
    check("...strictly increasing in time",
          all(b > a for a, b in zip(h["t"], h["t"][1:])))
    check("...with every column the same length as t",
          all(len(h[k]) == h["n"] for k in keys))

    n_before = h["n"]
    sample = dict.fromkeys(keys, 2)
    sample["flow"] = [1] * BINS
    again = ftdata._bikes_history(prev, sample, t0 + 399 * BUCKET + 90.0)
    check("a second pass inside one bucket overwrites rather than appends",
          again["n"] == n_before and again["mov"][-1] == 2,
          "%d -> %d entries" % (n_before, again["n"]))

    jumped = t0 + 200 * BUCKET
    floor = float(int(jumped // BUCKET) * int(BUCKET))
    back = ftdata._bikes_history(prev, sample, jumped)
    check("a clock that jumps backwards drops the future",
          back["t"][-1] == floor and all(t <= floor for t in back["t"]),
          "newest bucket %.0f, %d entries kept" % (back["t"][-1], back["n"]))
    check("...rather than leaving a series the panel would draw as a scribble",
          all(b > a for a, b in zip(back["t"], back["t"][1:])))

    stale = {"hist": {"t": [1.0, 2.0], "fleet_m": [1.0, 2.0]}}
    fresh = ftdata._bikes_history(stale, sample, t0)
    check("a record from a version that stored other columns starts fresh",
          fresh["n"] == 1)


# --------------------------------------------------------------------------
# 6. Motion, purity and cost. It is a moving picture by nature and it must be
# the same moving picture every time.
# --------------------------------------------------------------------------

def test_motion():
    print("\nthe swarm actually moves, and the replay actually advances")
    tmp = tempfile.mkdtemp(prefix="bikes-move")
    try:
        synthetic(tmp, at=_at_hour(8))
        args = opts(cache_dir=tmp, at="%f" % _at_hour(8))
        r = bikes.build(args)
        prev, diffs, seen = None, [], set()
        for i in range(int(args.cycle * 20) + 4):
            f = r(i / 20.0, i)
            seen.add(r.state["cur"])
            if prev is not None:
                diffs.append(int((f != prev).any(axis=2).sum()))
            prev = f.copy()
        run = best = 0
        for d in diffs:
            run = run + 1 if d == 0 else 0
            best = max(best, run)
        check("the panel never holds the same frame for a tenth of a second",
              best <= 2, "longest identical run %d of %d frames"
              % (best, len(diffs)))
        check("the swarm moves a substantial part of the panel",
              max(diffs) > 120, "biggest change %d pixels" % max(diffs))
        check("one cycle visits every replay step",
              len(seen) == len(r.state["steps"]),
              "%d of %d steps" % (len(seen), len(r.state["steps"])))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_purity():
    print("\nrender is a pure function of t once --reload is off")
    tmp = tempfile.mkdtemp(prefix="bikes-pure")
    try:
        at = _at_hour(8)
        synthetic(tmp, at=at)
        a = bikes.build(opts(cache_dir=tmp, at="%f" % at))
        b = bikes.build(opts(cache_dir=tmp, at="%f" % at))
        bad = []
        for t0 in (0.0, 0.35, 1.05, 1.9, 2.05, 3.7, 7.15, 11.4, 30.0, 41.6):
            cold = a(t0, int(t0 * 20)).copy()
            for i in range(int(t0 * 20) + 1):
                b(i / 20.0, i)
            if not np.array_equal(cold, b(t0, int(t0 * 20))):
                bad.append(t0)
        check("a cold render(t) equals the same t driven from zero",
              not bad, "differed at %s" % (bad or "nothing"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_cost():
    print("\nframe cost")
    tmp = tempfile.mkdtemp(prefix="bikes-cost")
    try:
        synthetic(tmp, at=_at_hour(8))
        r = bikes.build(opts(cache_dir=tmp, at="%f" % _at_hour(8)))
        for i in range(40):
            r(i / 20.0, i)
        ts = []
        for i in range(1200):
            t0 = time.perf_counter()
            r(i / 20.0, i)
            ts.append((time.perf_counter() - t0) * 1e3)
        ts = np.asarray(ts)
        p50, p95 = np.percentile(ts, (50, 95))
        # A tripwire and not a claim about the wall: desktop timings lie by
        # over an order of magnitude, and what the Pi cares about is the
        # number of numpy calls, which this cannot see. p95 near p50 is the
        # part that transfers -- a fat tail here is a fat tail there.
        check("desktop frame time", p95 < 1.5,
              "mean %.3f  p50 %.3f  p95 %.3f  max %.3f ms"
              % (ts.mean(), p50, p95, ts.max()))
        check("...with no fat tail", p95 < max(3.0 * p50, 0.25),
              "p95/p50 = %.2f" % (p95 / max(p50, 1e-6)))
        t0 = time.perf_counter()
        bikes.build(opts(cache_dir=tmp))
        check("build cost", True, "%.1f ms" % ((time.perf_counter() - t0) * 1e3))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 7. The degraded states, and the sizes.
# --------------------------------------------------------------------------

def test_degraded():
    print("\nstale, refused, malformed and absent")
    tmp = tempfile.mkdtemp(prefix="bikes-bad")
    try:
        stale = os.path.join(tmp, "stale")
        synthetic(stale, fetched_ago=45 * 60.0)
        r, f = frames(opts(cache_dir=stale), 8)
        check("a 45 minute old record still draws its city",
              r.state["rec"] is not None
              and not contains_text(f, "NO BIKE DATA"))
        check("...and says STALE on the panel",
              contains_text(f, "STALE") and r.state["stale"],
              "age %s" % ftdata.describe_age(r.state["rec"]["age"]))

        old = os.path.join(tmp, "old")
        synthetic(old, fetched_ago=9 * 3600.0)
        r, f = frames(opts(cache_dir=old), 8)
        check("a nine hour old record is refused rather than drawn",
              r.state["rec"] is None and contains_text(f, "NO BIKE DATA"),
              str(r.state["problem"])[:44])

        absent = os.path.join(tmp, "absent")
        os.makedirs(absent)
        r, f = frames(opts(cache_dir=absent), 8)
        check("no record at all gets the card",
              r.state["rec"] is None and contains_text(f, "NO BIKE DATA"))
        check("...and the command that fixes it",
              contains_text(f, "FTDATA.PY"))

        ragged = os.path.join(tmp, "ragged")

        def chop(p):
            p["fill_pct"] = p["fill_pct"][:-5]
        synthetic(ragged, mangle=chop)
        r, f = frames(opts(cache_dir=ragged), 8)
        check("arrays of different lengths are refused",
              r.state["rec"] is None, str(r.state["problem"])[:44])

        wrong = os.path.join(tmp, "wrong")
        synthetic(wrong, descending=True)
        r, f = frames(opts(cache_dir=wrong), 8)
        check("a record sorted the wrong way is refused, not drawn backwards",
              r.state["rec"] is None, str(r.state["problem"])[:44])

        corrupt = os.path.join(tmp, "corrupt")
        os.makedirs(corrupt)
        with open(os.path.join(corrupt, "baywheels.json"), "w") as fh:
            fh.write('{"payload": {"dist_m": ')
        r, f = frames(opts(cache_dir=corrupt), 8)
        check("half a file is a card and not a traceback",
              r.state["rec"] is None and contains_text(f, "NO BIKE DATA"))

        noflow = os.path.join(tmp, "noflowcol")

        def strip_flow(p):
            del p["hist"]["flow"]
        synthetic(noflow, mangle=strip_flow)
        r, f = frames(opts(cache_dir=noflow), 40)
        check("a record whose history has no flow column draws the city",
              r.state["rec"] is not None and r.state["cold"],
              "cold=%s" % r.state["cold"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _one_state(state, cache_dir):
    """The child half. Prints one RESULT line and exits."""
    args = ds.options(bikes)            # note: no cache_dir, so CACHE_DIR wins
    r = bikes.build(args)
    out = None
    for i in range(8):
        out = r(i / 20.0, i)
    card = contains_text(out, "NO BIKE DATA")
    stale = contains_text(out, "STALE")
    drew = r.state["rec"] is not None
    verdict = {
        "fresh": (drew and not card and not stale, "drew a city, no flags"),
        "stale": (drew and not card and stale, "drew a city with STALE on it"),
        "absent": (not drew and card, "drew the no-data card"),
    }[state]
    print("RESULT %s %s cache=%s drew=%s card=%s stale=%s"
          % (state, "ok" if verdict[0] else "FAIL",
             os.path.basename(cache_dir), drew, card, stale))
    return 0 if verdict[0] else 1


def test_states_in_separate_processes():
    print("\nfresh, stale and absent -- one process each, FT_DATA_CACHE set")
    tmp = tempfile.mkdtemp(prefix="bikes-proc")
    try:
        fresh = os.path.join(tmp, "fresh")
        synthetic(fresh, fetched_ago=120.0)
        stale = os.path.join(tmp, "stale")
        synthetic(stale, fetched_ago=50 * 60.0)
        absent = os.path.join(tmp, "absent")
        os.makedirs(absent)

        for state, d in (("fresh", fresh), ("stale", stale),
                         ("absent", absent)):
            env = dict(os.environ, FT_DATA_CACHE=d, FT_DATA_BLOBS=d)
            proc = subprocess.run(
                [sys.executable, os.path.abspath(__file__),
                 "--state", state, "--cache-dir", d],
                env=env, capture_output=True, text=True, timeout=180)
            line = [ln for ln in proc.stdout.splitlines()
                    if ln.startswith("RESULT")]
            check("%s cache, in its own process" % state,
                  proc.returncode == 0 and bool(line),
                  (line[0][7:] if line
                   else (proc.stderr.strip().splitlines() or ["no output"])[-1]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_sizes():
    print("\nother panel shapes")
    tmp = tempfile.mkdtemp(prefix="bikes-size")
    try:
        synthetic(tmp, at=_at_hour(8))
        for w, h in ((320, 64), (256, 64), (128, 64), (320, 32), (192, 96),
                     (512, 128), (64, 32), (320, 16)):
            try:
                r, f = frames(opts(cache_dir=tmp, width=w, height=h,
                                   at="%f" % _at_hour(8)), 60)
                ok = (f.shape == (h, w, 3) and f.dtype == np.uint8
                      and f.max() > 0)
                lay = r.layout
                detail = "map %d rows, tick %d, legend %d" % (
                    lay.map_h, lay.tick_h, lay.leg_h)
            except Exception as e:                           # noqa: BLE001
                ok, detail = False, repr(e)[:70]
            check("%dx%d renders" % (w, h), ok, detail)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_live(cache_dir):
    print("\nthe live cache, if there is one")
    got = ftdata.load("baywheels", cache_dir)
    if got is None:
        check("a baywheels record exists", False, "none in %s" % cache_dir)
        return
    payload, age = got
    size = os.path.getsize(os.path.join(cache_dir, "baywheels.json"))
    check("the record is small enough for a Pi", size < 64 * 1024,
          "%.1f kB, %d stations, %d buckets"
          % (size / 1024.0, payload.get("n", 0),
             (payload.get("hist") or {}).get("n", 0)))
    r, f = frames(opts(cache_dir=cache_dir), 60)
    check("it builds and renders", f.shape[2] == 3 and f.max() > 0,
          "%d steps, cold=%s, age %s"
          % (len(r.state["steps"]), r.state["cold"],
             ftdata.describe_age(age)))
    check("the caveat is on the panel", contains_text(f, "NOT TRIPS"))
    check("...and so is the source", contains_text(f, "DOCK COUNTS"))


def write_shot(path, cache_dir, at_t=14.0):
    """A 3x screenshot, 960x192 from the 320x64 panel."""
    from PIL import Image
    r = bikes.build(opts(cache_dir=cache_dir))
    out = None
    for i in range(int(at_t * 20) + 1):
        out = r(i / 20.0, i)
    im = Image.fromarray(np.asarray(out, np.uint8).copy(), "RGB")
    im = im.resize((im.width * 3, im.height * 3), Image.NEAREST)
    im.save(path)
    print("wrote %s (%dx%d)" % (path, im.width, im.height))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache-dir", default=ftdata.CACHE_DIR)
    ap.add_argument("--shot", default="",
                    help="also write a 3x screenshot here")
    ap.add_argument("--state", default="",
                    choices=("", "fresh", "stale", "absent"),
                    help="internal: run one data state and print RESULT")
    a = ap.parse_args()
    if a.state:
        return _one_state(a.state, a.cache_dir)

    print("cache: %s" % a.cache_dir)
    test_no_network()
    test_terrain_bake()
    test_axis()
    test_flux_conserves()
    test_transport_direction()
    test_headline_arithmetic()
    test_direction_on_the_panel()
    test_observed_layer()
    test_track_differencing()
    test_privacy()
    test_window_and_gaps()
    test_cold_start()
    test_fetcher_differencing()
    test_history_is_bounded()
    test_motion()
    test_purity()
    test_cost()
    test_degraded()
    test_states_in_separate_processes()
    test_sizes()
    test_live(a.cache_dir)
    if a.shot:
        write_shot(a.shot, a.cache_dir)

    print("\n%d checks, %d failed" % (PASSED[0], len(FAILED)))
    for name in FAILED:
        print("  - %s" % name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
