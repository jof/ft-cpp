#!/usr/bin/env python3
"""Checks for bikes.py that a screenshot cannot make.

This demo can draw a beautiful, confident, wrong hillside in at least six ways,
and not one of them looks wrong:

  1. **The hill can run the other way.** A ridge that descends left to right is
     exactly as pretty as one that rises, and it says the opposite thing about
     which end of the city the panel is talking about.
  2. **The occupancy ramp can be inverted.** Amber for full and blue for empty
     is a perfectly attractive picture of a city whose hills are overflowing.
  3. **The altitude anomaly's sign can flip.** "4M DOWNHILL" drawn when the
     fleet is four metres *above* its docks is a whole sentence that is wrong,
     printed in the largest type on the panel.
  4. **The lane can join up its gaps.** An hour when the fetcher was not
     running, drawn as a smooth line between the two sides of it, is an
     invention, and an invention in the shape of data.
  5. **The mist can eat the ridge.** The loose ebikes are drawn near the
     surface; one row of overlap and the occupancy colours are gone under a
     stipple, which reads as "quiet" rather than as "missing".
  6. **A record from breakfast draws perfectly.** It parses, it has 383
     stations, it is a lovely hill, and every dry station on it has been
     refilled since.

So the drawing is asserted **in pixels** against synthetic cities whose answers
cannot be argued with -- a city whose hills are dry and whose flats are full,
and then the same city upside down -- and the arithmetic is asserted against
the record separately.

Two things about how these are run, both learned the hard way in this tree.
With the default `--reload`, the demo asks the wall clock whether to re-read
the cache, so the checks that care about determinism pass `reload=0`, under
which `render` is a **pure function of t** and is asserted to be. And
`ftdata.CACHE_DIR` binds at import, so the three data states a demo must handle
-- fresh, stale, absent -- are each run in a **separate process** with
FT_DATA_CACHE set, at the bottom of this file. Reloading the module in one
process does not test what it looks like it tests.

    $ python3 scripts/test-bikes.py                     # uses the live cache
    $ python3 scripts/test-bikes.py --cache-dir /tmp/c  # or a pointed one

The live cache is only needed for the checks against real data; everything else
builds its own cache directory and needs nothing. Populate it with
`python3 ftdata.py --once --only baywheels`.
"""

import argparse
import json
import math
import os
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

N_STATIONS = 300
BUCKET = 600.0


def check(name, ok, detail=""):
    PASSED[0] += 1
    if ok:
        print("  ok   %-58s %s" % (name, detail))
    else:
        print("  FAIL %-58s %s" % (name, detail))
        FAILED.append(name)


def opts(**kw):
    kw.setdefault("reload", 0.0)
    return ds.options(bikes, **kw)


def frames(args, n=8):
    """Render `n` frames in order from a fresh build. Never sample sparsely."""
    r = bikes.build(args)
    out = None
    for i in range(n):
        out = r(i / 20.0, i)
    return r, out.copy()


def settled(args, n=200):
    """A frame from after the reveal has finished, still rendered in order."""
    return frames(args, n)


def contains_text(frame, s, thresh=90, scales=(1, 2), bg_max=0.25):
    """Is this string drawn anywhere on the frame, at any position or size?

    Reading the words back off the panel is the only way to be sure the honest
    message reached it rather than merely being computed. The counters between
    the strokes have to be dark as well: this panel has a solid rock body and a
    filled lane on it, and a matcher that only asks "are the strokes lit"
    answers yes to most of the language somewhere inside the hill.
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


# --------------------------------------------------------------------------
# Cities we invented, so that every answer is known before it is drawn.
#
# The elevations are a fixed curve from 2 m to 150 m, so the ridge's shape is
# known; the occupancy is whatever the caller asks for as a function of rank,
# so "the hilltops are dry" is a formula and not an observation.
# --------------------------------------------------------------------------

def city(fill_of_rank, n=N_STATIONS, closed=(), jammed=(), dry=()):
    """Parallel arrays for a synthetic San Francisco, ascending by altitude."""
    rank = np.arange(n) / (n - 1.0)
    elev = np.round(2.0 + 148.0 * rank ** 2.0).astype(int)      # convex, rising
    fill = np.array([int(round(100 * float(np.clip(fill_of_rank(x), 0, 1))))
                     for x in rank])
    cap = np.full(n, 20)
    free = cap - np.round(fill / 100.0 * cap).astype(int)
    openf = np.ones(n, int)
    for i in closed:
        openf[i] = 0
    for i in jammed:
        free[i] = 0
        fill[i] = 100
    for i in dry:
        fill[i] = 0
        free[i] = int(cap[i])
    return elev, fill, free, openf, cap


def synthetic(cache_dir, fill_of_rank=lambda x: 0.5 - 0.35 * x, n=N_STATIONS,
              closed=(), jammed=(), dry=(), fetched_ago=120.0,
              hours=24.0, hist_gap=(), no_hist=False, loose=600,
              anomaly_at=None, mangle=None, descending=False):
    """Write a baywheels record by hand. Returns (path, truth dict)."""
    elev, fill, free, openf, cap = city(fill_of_rank, n, closed, jammed, dry)
    if descending:
        elev = elev[::-1].copy()

    bikes_at = np.round(fill / 100.0 * cap).astype(int)
    fleet = float((elev * bikes_at).sum() / max(bikes_at.sum(), 1))
    docks = float((elev * cap).sum() / cap.sum())

    now = time.time() - fetched_ago
    t, hf, hd = [], [], []
    if not no_hist:
        n_buckets = int(hours * 3600.0 / BUCKET)
        for k in range(n_buckets, -1, -1):
            tt = float(int((now - k * BUCKET) // BUCKET) * int(BUCKET))
            hour = time.localtime(tt).tm_hour + time.localtime(tt).tm_min / 60.0
            if any(lo <= hour < hi for lo, hi in hist_gap):
                continue
            # A commute pump: down through the morning, back up overnight.
            a = -2.0 - 3.0 * math.exp(-((hour - 10.0) / 3.0) ** 2)
            t.append(tt)
            hd.append(round(docks, 2))
            hf.append(round(docks + a, 2))
    if anomaly_at is not None and t:
        hf[-1] = round(docks + anomaly_at, 2)
        fleet = docks + anomaly_at

    payload = {
        "as_of": now, "region": "San Francisco",
        "bbox": list(ftdata.BIKES_BBOX), "n": int(n),
        "elev_m": [int(v) for v in elev],
        "fill_pct": [int(v) for v in fill],
        "free_docks": [int(v) for v in free],
        "open": [int(v) for v in openf],
        "loose_bins": [loose // ftdata.BIKES_LOOSE_BINS] *
                      ftdata.BIKES_LOOSE_BINS,
        "totals": {"stations": int(n), "closed": int(n - openf.sum()),
                   "capacity": int(cap.sum()), "bikes": int(bikes_at.sum()),
                   "ebikes": 0, "free_docks": int(free.sum()),
                   "empty": int(((fill == 0) & (openf == 1)).sum()),
                   "jammed": int(((free == 0) & (openf == 1)).sum()),
                   "loose": int(loose), "loose_unavailable": 0},
        "altitude_m": {"fleet": round(fleet, 2), "docks": round(docks, 2),
                       "loose": round(docks, 2),
                       "low": float(elev.min()), "high": float(elev.max())},
        "interpolated": 0,
        "hist": {"t": t, "fleet_m": hf, "docks_m": hd,
                 "loose_m": [round(docks, 2)] * len(t),
                 "bikes": [int(bikes_at.sum())] * len(t),
                 "empty": [0] * len(t), "loose": [int(loose)] * len(t),
                 "bucket": BUCKET, "hours": hours, "n": len(t)},
        "units": {}, "sources": ["synthetic"],
    }
    if mangle:
        mangle(payload)

    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, "baywheels.json")
    with open(path, "w") as fh:
        json.dump({"name": "baywheels", "source": "synthetic",
                   "ttl": ftdata.BIKES_TTL, "fetched_at": now,
                   "payload": payload}, fh)
    return path, {"elev": elev, "fill": fill, "free": free, "open": openf,
                  "cap": cap, "bikes": bikes_at, "fleet": fleet,
                  "docks": docks, "t": t, "hist_fleet": hf}


def warmth(rgb):
    """How warm a pixel is: red minus blue. Positive is the dry end of the ramp."""
    return int(rgb[0]) - int(rgb[2])


def ridge_row(frame, lay, col):
    """The topmost lit row of the hill in this column, or None."""
    seg = frame[lay.hill_y:lay.hill_bot + 1, col]
    lit = np.flatnonzero(seg.max(axis=1) > 0)
    return None if not len(lit) else int(lit[0] + lay.hill_y)


def surface_rgb(frame, lay, col, ridge):
    """The colour of the surface in this column: the row above the rock."""
    return frame[ridge[col], col]


# --------------------------------------------------------------------------
# 1. The hill, in pixels, against the cities we invented.
# --------------------------------------------------------------------------

def test_hill_direction():
    print("\nthe hill rises with altitude, left to right")
    tmp = tempfile.mkdtemp(prefix="bikes-hill")
    try:
        synthetic(tmp)
        r, f = settled(opts(cache_dir=tmp, sweep=0.0, reveal=0.0, no_mist=True))
        lay = r.layout
        ridge = r.state["ridge"]
        check("the ridge is monotonically non-increasing in row",
              bool(np.all(np.diff(ridge) <= 0)),
              "rows %d -> %d" % (ridge[0], ridge[-1]))
        check("...and the right hand end is far higher than the left",
              ridge[0] - ridge[-1] >= lay.hill_h // 2,
              "%d rows of climb over %d of hill"
              % (ridge[0] - ridge[-1], lay.hill_h))

        # Rock below the ridge, sky above it. The one thing that would make the
        # picture a line chart rather than a hill is the body being missing,
        # and it is asserted over every column rather than a sampled one --
        # a hill with a hole in it is exactly the sort of off-by-one that
        # survives being looked at.
        rock = np.array(bikes.C_ROCK, np.uint8)
        has_body = np.zeros(lay.w, bool)
        for c in range(lay.w):
            seg = f[ridge[c] + 2:lay.hill_bot + 1, c]
            has_body[c] = bool(len(seg)) and bool(
                (seg == rock).all(axis=1).any())
        check("every column of the hill has a body under its ridge",
              has_body.mean() > 0.95,
              "%d of %d columns" % (has_body.sum(), lay.w))

        # And sky over it. Column 240 rather than the middle: the caption lives
        # in the upper left and this check is about the hill, not the writing.
        col = 240
        above = f[lay.hill_y:max(lay.hill_y + 1, ridge[col] - 4), col]
        check("...and nothing bright above it",
              int(above.max()) <= 40, "brightest sky pixel %d" % above.max())

        # A record whose elevations descend is a record this file cannot draw:
        # every index in it assumes ascending, and an unsorted one would draw a
        # plausible, meaningless mountain range.
        bad = tempfile.mkdtemp(prefix="bikes-desc")
        try:
            synthetic(bad, descending=True)
            rb, fb = frames(opts(cache_dir=bad), 8)
            check("a record sorted the other way is refused, not drawn",
                  rb.state["rec"] is None and contains_text(fb, "NO BIKE DATA"),
                  str(rb.state["problem"])[:44])
        finally:
            shutil.rmtree(bad, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ramp_direction():
    print("\nthe occupancy ramp, which is plausible inside out")
    tmp = tempfile.mkdtemp(prefix="bikes-ramp")
    inv = tempfile.mkdtemp(prefix="bikes-ramp2")
    try:
        # Flats full, hills dry: the ordinary weekday-evening city.
        synthetic(tmp, fill_of_rank=lambda x: 0.95 - 0.95 * x)
        r, f = settled(opts(cache_dir=tmp, sweep=0.0, reveal=0.0, no_mist=True))
        ridge = r.state["ridge"]
        lo = warmth(surface_rgb(f, r.layout, 12, ridge))
        hi = warmth(surface_rgb(f, r.layout, 307, ridge))
        check("dry hilltops are warmer than full flats", hi > lo + 60,
              "sea level r-b %d, summit r-b %d" % (lo, hi))

        # And the same city upside down has to come out the other way round,
        # which is what makes the check above about the ramp and not about the
        # fact that one end of the panel happens to be orange.
        synthetic(inv, fill_of_rank=lambda x: 0.05 + 0.95 * x)
        r2, f2 = settled(opts(cache_dir=inv, sweep=0.0, reveal=0.0,
                              no_mist=True))
        ridge2 = r2.state["ridge"]
        lo2 = warmth(surface_rgb(f2, r2.layout, 12, ridge2))
        hi2 = warmth(surface_rgb(f2, r2.layout, 307, ridge2))
        check("...and inverting the city inverts the ridge", lo2 > hi2 + 60,
              "sea level r-b %d, summit r-b %d" % (lo2, hi2))

        # The quiet middle. A ramp whose healthy band is as loud as its alarms
        # is a ramp that says nothing, and this is the one property of it that
        # is a design decision rather than a direction.
        lut = ds.gradient(bikes.FILL_RAMP, 64)
        peak = lut.max(axis=1)
        check("the healthy middle of the ramp is the dimmest part of it",
              int(peak[20:50].max()) < int(peak[0]) and
              int(peak[20:50].max()) < int(peak[-1]),
              "middle %d, dry %d, full %d"
              % (peak[20:50].max(), peak[0], peak[-1]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(inv, ignore_errors=True)


def test_flags_and_mist():
    print("\ndry flags, jammed marks and the mist that must not eat them")
    tmp = tempfile.mkdtemp(prefix="bikes-flag")
    try:
        # Three dry stations high on the hill and three jammed ones low down,
        # in a city that is otherwise uniformly comfortable.
        dry_idx = (280, 285, 290)
        jam_idx = (4, 9, 14)
        synthetic(tmp, fill_of_rank=lambda x: 0.45, dry=dry_idx,
                  jammed=jam_idx)
        r, f = settled(opts(cache_dir=tmp, sweep=0.0, reveal=0.0))
        lay, ridge = r.layout, r.state["ridge"]
        flags = r.state["flags"]
        check("every dry station raises a flag", flags is not None
              and len(flags[0]) >= 2 * len(dry_idx),
              "%d flag pixels" % (0 if flags is None else len(flags[0])))

        n = r.state["rec"]["n"]
        dry_cols = sorted(set(int(i * lay.w / n) for i in dry_idx))
        col = dry_cols[len(dry_cols) // 2]
        over = f[max(lay.hill_y, ridge[col] - 3):ridge[col], col]
        check("...above the ridge, in the dry colour",
              warmth(over.max(axis=0)) > 80, "r-b %d" % warmth(over.max(axis=0)))

        jam_cols = sorted(set(int(i * lay.w / n) for i in jam_idx))
        jcol = jam_cols[len(jam_cols) // 2]
        under = f[ridge[jcol] + 1:ridge[jcol] + 5, jcol]
        full = np.array(bikes.C_FULL, np.uint8)
        check("jammed stations bite down into the rock in the full colour",
              bool((under == full).all(axis=1).any()),
              "rows %s" % [int(v.max()) for v in under])

        # The mist has to stay off the surface. This is the check that catches
        # a one-row error in the gap, which would replace the occupancy colours
        # with a stipple and look like a working panel.
        mist = np.array(bikes.C_MIST, np.uint8)
        cols = np.arange(lay.w)
        on_ridge = (f[ridge, cols] == mist).all(axis=1)
        check("no mist pixel lands on the ridge itself",
              not on_ridge.any(), "%d of %d columns" % (on_ridge.sum(), lay.w))

        # And --no-mist has to actually remove it, or the option is decoration.
        _, f2 = settled(opts(cache_dir=tmp, sweep=0.0, reveal=0.0,
                             no_mist=True))
        anywhere = int((f2 == mist).all(axis=2).sum())
        check("--no-mist leaves none of it on the panel", anywhere == 0,
              "%d pixels" % anywhere)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 2. The headline, whose sign is a whole sentence.
# --------------------------------------------------------------------------

def test_anomaly_sign():
    print("\nthe altitude anomaly, whose sign is a sentence")
    down = tempfile.mkdtemp(prefix="bikes-down")
    up = tempfile.mkdtemp(prefix="bikes-up")
    try:
        _, truth = synthetic(down, anomaly_at=-4.3)
        r, f = settled(opts(cache_dir=down, sweep=0.0, reveal=0.0))
        a = bikes.anomaly(r.state["rec"])
        check("anomaly is fleet altitude less dock altitude",
              abs(a - (truth["fleet"] - truth["docks"])) < 0.05,
              "%.2f m" % a)
        check("a fleet below its docks says DOWNHILL",
              contains_text(f, "%.1fM DOWNHILL" % abs(a)),
              "%.1fM DOWNHILL" % abs(a))
        check("...and says which way round that is, in words",
              contains_text(f, "FLEET BELOW ITS DOCKS"))
        check("...and does not also say the opposite",
              not contains_text(f, "FLEET ABOVE ITS DOCKS"))

        _, truth2 = synthetic(up, anomaly_at=+3.1)
        r2, f2 = settled(opts(cache_dir=up, sweep=0.0, reveal=0.0))
        a2 = bikes.anomaly(r2.state["rec"])
        check("a fleet above its docks says UPHILL instead",
              a2 > 0 and contains_text(f2, "%.1fM UPHILL" % a2)
              and contains_text(f2, "FLEET ABOVE ITS DOCKS"),
              "%.1fM UPHILL" % a2)
        check("...and the headline changes colour with the sign",
              bikes.C_DOWN != bikes.C_UP
              and warmth(bikes.C_DOWN) > warmth(bikes.C_UP))

        # The counts on the header have to be the record's, not a recount.
        t = r.state["rec"]["totals"]
        check("the header carries the record's own bike and dry counts",
              contains_text(f, "%d BIKES" % t["bikes"]),
              "%d bikes, %d dry" % (t["bikes"], t["empty"]))
    finally:
        shutil.rmtree(down, ignore_errors=True)
        shutil.rmtree(up, ignore_errors=True)


def test_trend():
    print("\nthe trend, and what it says when there is nothing to trend")
    tmp = tempfile.mkdtemp(prefix="bikes-trend")
    thin = tempfile.mkdtemp(prefix="bikes-thin")
    try:
        synthetic(tmp)
        r, _ = settled(opts(cache_dir=tmp, sweep=0.0, reveal=0.0))
        rate = bikes.trend(r.state["rec"])
        check("a full day of history yields a rate in metres an hour",
              rate is not None and abs(rate) < 20.0, "%.2f m/h" % (rate or 0))

        synthetic(thin, no_hist=True)
        r2, f2 = settled(opts(cache_dir=thin, sweep=0.0, reveal=0.0))
        check("a record with no history yields no rate",
              bikes.trend(r2.state["rec"]) is None)
        check("...and the panel says the track is still building",
              contains_text(f2, "24H TRACK BUILDING"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(thin, ignore_errors=True)


# --------------------------------------------------------------------------
# 3. The lane, whose gaps must stay gaps.
# --------------------------------------------------------------------------

def test_lane():
    print("\nthe 24 hour lane")
    tmp = tempfile.mkdtemp(prefix="bikes-lane")
    try:
        # A three-hour hole in the middle of the night, which the lane must
        # leave empty rather than bridging.
        synthetic(tmp, hist_gap=((2.0, 5.0),))
        r, f = settled(opts(cache_dir=tmp, sweep=0.0, reveal=0.0))
        lay = r.layout
        if not lay.lane_h:
            check("lane exists at 320x64", False)
            return
        band = f[lay.lane_y:lay.lane_y + lay.lane_h]
        curve = np.array(bikes.C_DOWN, np.uint8)
        fill = np.array(bikes.C_DOWN_FILL, np.uint8)
        drawn = ((band == curve).all(axis=2) | (band == fill).all(axis=2))
        lit_cols = drawn.any(axis=0)
        check("most of the day is drawn", lit_cols.mean() > 0.6,
              "%d of %d columns" % (lit_cols.sum(), lay.w))
        # Where the hole is, in columns.
        now = r.clock()
        t0 = now - 24 * 3600.0
        hole = []
        for c in range(lay.w):
            tt = t0 + (c + 0.5) / lay.w * 24 * 3600.0
            hour = time.localtime(tt).tm_hour + time.localtime(tt).tm_min / 60.0
            if 2.3 <= hour < 4.7:
                hole.append(c)
        check("a three-hour hole in the series is left as a hole",
              len(hole) > 8 and not lit_cols[hole].any(),
              "%d of %d hole columns drawn"
              % (int(lit_cols[hole].sum()), len(hole)))

        # Sign: the synthetic day is below its docks throughout, so every bar
        # must hang below the reference line and none above it.
        up = np.array(bikes.C_UP_FILL, np.uint8)
        check("a day spent below the docks draws nothing above the line",
              int((band == up).all(axis=2).sum()) == 0)

        # The present moment has to be marked, and marked at the right edge.
        check("the now-line is at the right hand end",
              r.state["now_col"] >= lay.w - 2, "column %d" % r.state["now_col"])
        check("...and the local time is printed with it",
              contains_text(f, bikes.hhmm(now)), bikes.hhmm(now))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_history_is_bounded():
    print("\nthe fetcher's rolling series, which appends to itself forever")
    now = 1786400000.0
    prev, h = None, None
    for i in range(400):
        h = ftdata._bikes_history(
            prev, {"fleet_m": float(i), "docks_m": 30.0, "loose_m": 1.0,
                   "bikes": i, "empty": 0, "loose": 0},
            now - (400 - i) * ftdata.BIKES_HIST_BUCKET)
        prev = {"hist": h}
    check("400 passes leave at most a day of buckets",
          h["n"] <= ftdata.BIKES_HIST_MAX
          and (h["t"][-1] - h["t"][0]) <= ftdata.BIKES_HIST_HOURS * 3600.0,
          "%d entries over %.1f h"
          % (h["n"], (h["t"][-1] - h["t"][0]) / 3600.0))
    check("...and every column stays the same length as the timestamps",
          all(len(h[k]) == h["n"] for k in
              ("fleet_m", "docks_m", "loose_m", "bikes", "empty", "loose")))

    same = ftdata._bikes_history(prev, {"fleet_m": 999.0, "docks_m": 1.0,
                                        "loose_m": 1.0, "bikes": 1,
                                        "empty": 1, "loose": 1},
                                 now - 30.0)
    check("a second pass inside one bucket overwrites rather than appends",
          same["n"] == h["n"] and same["fleet_m"][-1] == 999.0,
          "%d entries" % same["n"])

    back = ftdata._bikes_history(prev, {"fleet_m": 1.0, "docks_m": 1.0,
                                        "loose_m": 1.0, "bikes": 1,
                                        "empty": 1, "loose": 1},
                                 now - 3 * 86400.0)
    check("a clock that jumps backwards drops the future rather than "
          "scrambling", back["n"] == 1, "%d entries" % back["n"])

    junk = ftdata._bikes_history({"hist": {"t": [1, 2, 3], "fleet_m": [1]}},
                                 {"fleet_m": 5.0, "docks_m": 1.0,
                                  "loose_m": 1.0, "bikes": 1, "empty": 1,
                                  "loose": 1}, now)
    check("a previous record of the wrong shape is started over, not fused",
          junk["n"] == 1)


# --------------------------------------------------------------------------
# 4. Motion, and purity. It is a still picture by nature and it must not look
# like one -- and it must be the same still picture every time.
# --------------------------------------------------------------------------

def test_motion():
    print("\nit does not sit there")
    tmp = tempfile.mkdtemp(prefix="bikes-mot")
    try:
        synthetic(tmp)
        args = opts(cache_dir=tmp)
        r = bikes.build(args)
        lay = r.layout

        lit = []
        for i in range(int(args.reveal * 20) + 2):
            f = r(i / 20.0, i)
            hill = f[lay.hill_y:lay.hill_bot + 1]
            lit.append(int((hill.max(axis=2) > 0).any(axis=0).sum()))
        check("the hill reveals from the left rather than appearing",
              lit[0] < lit[len(lit) // 2] < lit[-1] and lit[0] <= 3,
              "lit columns %d -> %d -> %d"
              % (lit[0], lit[len(lit) // 2], lit[-1]))

        prev, diffs = None, []
        for i in range(int(args.reveal * 20) + 2, int(args.reveal * 20) + 200):
            f = r(i / 20.0, i)
            if prev is not None:
                diffs.append(int((f != prev).any(axis=2).sum()))
            prev = f.copy()
        run = best = 0
        for d in diffs:
            run = run + 1 if d == 0 else 0
            best = max(best, run)
        check("the panel never holds the same frame for a tenth of a second",
              best <= 2, "longest identical run %d frames of %d"
              % (best, len(diffs)))
        check("the sheen moves a substantial part of the panel",
              max(diffs) > 200, "biggest change %d pixels" % max(diffs))

        r2 = bikes.build(opts(cache_dir=tmp, reveal=0.0))
        base = r2.static.astype(int)
        cols = set()
        for i in range(int(args.sweep * 20) + 4):
            f = r2(i / 20.0, i).astype(int)
            d = np.abs(f - base).sum(axis=(0, 2)).astype(float)
            nc = r2.state["now_col"] or 0
            d[max(0, nc - 2):nc + 3] = 0.0
            # The dry flags differ from the baked frame every frame by design
            # and they are scattered along the whole ridge, which would drag
            # the centroid to the middle and hide a sheen that never moved.
            flags = r2.state["flags"]
            if flags is not None:
                d[flags[1]] = 0.0
            if d.sum() <= 0:
                continue
            centre = float((d * np.arange(len(d))).sum() / d.sum())
            cols.add(int(centre) // 40)
        check("the sheen crosses the whole width over one period",
              len(cols) >= 6, "%d of 8 eighths visited" % len(cols))

        # The dry flags have to be the thing that pulses, not the whole panel.
        # A city with something actually wrong in it, or there is no flag to
        # watch: the default synthetic city never runs a station down to zero.
        dryd = tempfile.mkdtemp(prefix="bikes-mot2")
        synthetic(dryd, dry=(120, 121, 122))
        rf = bikes.build(opts(cache_dir=dryd, reveal=0.0, sweep=0.0))
        seen = set()
        for i in range(40):
            f = rf(i / 20.0, i)
            flags = rf.state["flags"]
            if flags is not None:
                seen.add(int(f[flags[0][0], flags[1][0]].max()))
        shutil.rmtree(dryd, ignore_errors=True)
        check("the dry flags breathe", len(seen) >= 4,
              "%d distinct brightnesses" % len(seen))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_purity():
    print("\nrender is a pure function of t once --reload is off")
    tmp = tempfile.mkdtemp(prefix="bikes-pure")
    try:
        synthetic(tmp)
        a = bikes.build(opts(cache_dir=tmp))
        b = bikes.build(opts(cache_dir=tmp))
        bad = []
        for t0 in (0.0, 0.35, 1.05, 1.9, 2.05, 3.7, 7.15, 11.4, 30.0):
            cold = a(t0, int(t0 * 20)).copy()
            for i in range(int(t0 * 20) + 1):
                b(i / 20.0, i)
            if not np.array_equal(cold, b(t0, int(t0 * 20))):
                bad.append(t0)
        check("a cold render(t) equals the same t driven from zero",
              not bad, "differed at %s" % (bad or "nothing"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 5. Degraded records. Every one of these has to reach the panel in words.
# --------------------------------------------------------------------------

def test_degraded():
    print("\nmissing, ancient, corrupt and half-there records")
    tmp = tempfile.mkdtemp(prefix="bikes-bad")
    try:
        empty = os.path.join(tmp, "empty")
        os.makedirs(empty)
        r, f = frames(opts(cache_dir=empty), 8)
        check("no cache at all says NO BIKE DATA",
              contains_text(f, "NO BIKE DATA"))
        check("...and names the command that fixes it",
              contains_text(f, "FTDATA.PY"))
        check("...and draws no hill", r.state["rec"] is None)

        bad = os.path.join(tmp, "corrupt")
        os.makedirs(bad)
        with open(os.path.join(bad, "baywheels.json"), "w") as fh:
            fh.write('{"payload": {"elev_m": ')
        _, f = frames(opts(cache_dir=bad), 8)
        check("a half-written file says NO BIKE DATA",
              contains_text(f, "NO BIKE DATA"))

        wrong = os.path.join(tmp, "foreign")
        os.makedirs(wrong)
        with open(os.path.join(wrong, "baywheels.json"), "w") as fh:
            json.dump({"name": "baywheels", "fetched_at": time.time(),
                       "payload": {"hello": "world"}}, fh)
        _, f = frames(opts(cache_dir=wrong), 8)
        check("a payload from some other product says NO BIKE DATA",
              contains_text(f, "NO BIKE DATA"))

        short = os.path.join(tmp, "short")
        synthetic(short, n=8)
        r, f = frames(opts(cache_dir=short), 8)
        check("eight stations is not a city and is refused",
              r.state["rec"] is None and contains_text(f, "NO BIKE DATA"),
              str(r.state["problem"])[:44])

        ragged = os.path.join(tmp, "ragged")

        def chop(p):
            p["fill_pct"] = p["fill_pct"][:-5]
        synthetic(ragged, mangle=chop)
        r, f = frames(opts(cache_dir=ragged), 8)
        check("arrays of different lengths are refused",
              r.state["rec"] is None, str(r.state["problem"])[:44])

        # The dangerous one. A record from breakfast is complete, well formed
        # and a perfectly good hill, and every dry station on it has been
        # refilled since.
        old = os.path.join(tmp, "old")
        synthetic(old, fetched_ago=9 * 3600.0)
        r, f = frames(opts(cache_dir=old), 8)
        check("a nine-hour-old record is refused, not drawn",
              r.state["rec"] is None and contains_text(f, "NO BIKE DATA"),
              str(r.state["problem"])[:44])
        check("...and says how old it was", contains_text(f, "9H"),
              str(r.state["problem"])[:44])

        # Past the TTL but well inside --max-age: draws, loudly.
        stale = os.path.join(tmp, "stale")
        synthetic(stale, fetched_ago=45 * 60.0)
        r, f = frames(opts(cache_dir=stale), 8)
        check("a 45 minute old record still draws its hill",
              r.state["rec"] is not None
              and not contains_text(f, "NO BIKE DATA"))
        check("...and says STALE on the panel",
              contains_text(f, "STALE") and r.state["stale"],
              "age %s" % ftdata.describe_age(r.state["rec"]["age"]))

        # No history and no loose bikes: both optional, and losing them must
        # cost their own marks and nothing else.
        bare = os.path.join(tmp, "bare")
        synthetic(bare, no_hist=True, loose=0)
        r, f = frames(opts(cache_dir=bare, sweep=0.0, reveal=0.0), 8)
        check("no history and no loose bikes still draws the hill",
              r.state["rec"] is not None and r.state["ridge"] is not None
              and f.max() > 0)

        # A city with nothing wrong in it: no flags at all is a legal state and
        # the fancy index that draws them must survive being empty.
        good = os.path.join(tmp, "good")
        synthetic(good, fill_of_rank=lambda x: 0.5)
        r, f = frames(opts(cache_dir=good), 20)
        check("a city with no dry station raises no flags and does not crash",
              r.state["flags"] is None and f.max() > 0)

        # ...and one where every station is dry.
        dead = os.path.join(tmp, "dead")
        synthetic(dead, fill_of_rank=lambda x: 0.0)
        r, f = frames(opts(cache_dir=dead), 20)
        check("a city with nothing to unlock anywhere still draws",
              r.state["rec"] is not None and f.max() > 0,
              "%d dry" % r.state["rec"]["totals"]["empty"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 6. Fresh, stale and absent, each in a process of its own.
#
# `ftdata.CACHE_DIR` is read at import time, so a test that sets FT_DATA_CACHE
# and reloads the module is testing the state of its own import machinery and
# not the state of the cache.
# --------------------------------------------------------------------------

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
        "fresh": (drew and not card and not stale, "drew a hill, no flags"),
        "stale": (drew and not card and stale, "drew a hill with STALE on it"),
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


# --------------------------------------------------------------------------
# 7. Other panels, the live cache, and the promise that none of this talks to
# anyone.
# --------------------------------------------------------------------------

def test_sizes():
    print("\nother panel sizes")
    tmp = tempfile.mkdtemp(prefix="bikes-size")
    try:
        synthetic(tmp)
        for w, h in ((320, 64), (256, 64), (128, 64), (320, 32), (192, 96),
                     (512, 128), (64, 32), (320, 16)):
            try:
                r, f = frames(opts(cache_dir=tmp, width=w, height=h), 60)
                ok = (f.shape == (h, w, 3) and f.dtype == np.uint8
                      and f.max() > 0)
                lay = r.layout
                detail = "hill %d rows, lane %d, label %d" % (
                    lay.hill_h, lay.lane_h, lay.lane_label)
            except Exception as e:                           # noqa: BLE001
                ok, detail = False, repr(e)[:70]
            check("%dx%d renders" % (w, h), ok, detail)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_terrain_bake():
    print("\nthe committed elevation bake")
    try:
        table, blat, blon, belev = ftdata._bikes_terrain()
    except Exception as e:                                   # noqa: BLE001
        check("bikes-terrain.npz loads", False, repr(e)[:60])
        return
    check("bikes-terrain.npz loads", True, "%d stations" % len(table))
    lo, hi = float(belev.min()), float(belev.max())
    check("its elevations are plausible for San Francisco Bay",
          -5.0 < lo < 15.0 and 100.0 < hi < 500.0, "%.1f to %.1f m" % (lo, hi))
    check("its coordinates are in the Bay Area",
          36.9 < blat.min() and blat.max() < 38.2
          and -122.7 < blon.min() and blon.max() < -121.5,
          "%.2f..%.2f N, %.2f..%.2f E"
          % (blat.min(), blat.max(), blon.min(), blon.max()))
    # A station the bake has never seen must be interpolated, not dropped.
    ids = ["not-a-real-station-id"]
    elev, missed = ftdata._bikes_elevation(ids, np.array([37.7749]),
                                           np.array([-122.4194]))
    check("an unknown station takes its nearest neighbour's height",
          missed == 1 and 0.0 < float(elev[0]) < 300.0,
          "%.1f m" % elev[0])


def test_live(cache_dir):
    print("\nagainst the live cache")
    got = ftdata.load("baywheels", cache_dir)
    if got is None:
        check("live record present", False,
              "run: python3 ftdata.py --once --only baywheels")
        return
    payload, age = got
    rec, _, err = bikes.read_bikes(cache_dir)
    if rec is None:
        check("live record parses into something drawable", False, err)
        return
    t = rec["totals"]
    check("live record parses into something drawable", True,
          "%d stations, %s old" % (rec["n"], ftdata.describe_age(age)))
    check("the station count is a plausible San Francisco",
          200 <= rec["n"] <= 600, "%d stations" % rec["n"])
    check("bikes available never exceeds the docks that exist",
          0 < t["bikes"] <= t["capacity"],
          "%d of %d docks" % (t["bikes"], t["capacity"]))
    check("the dry and jammed counts are both inside the station count",
          0 <= t["empty"] <= rec["n"] and 0 <= t["jammed"] <= rec["n"],
          "%d dry, %d jammed" % (t["empty"], t["jammed"]))
    check("the record is a fraction of the JSON it came from",
          len(json.dumps(payload)) < 40000,
          "%.1f kB" % (len(json.dumps(payload)) / 1024.0))

    lo, hi = rec["alt"]["low"], rec["alt"]["high"]
    check("the altitude range spans the actual city",
          lo < 12.0 and hi > 80.0, "%.0f to %.0f m" % (lo, hi))
    a = bikes.anomaly(rec)
    check("the anomaly is metres and not something else entirely",
          a is not None and abs(a) < 40.0, "%.2f m" % a)
    # The one Bay Wheels specific sanity check worth making: the flat eastern
    # half of the city holds far more docks than the hills, so the ridge must
    # spend most of its width below the median.
    elev = rec["elev"]
    check("half the docks are in the flat part of the city",
          float(np.median(elev)) < 0.4 * float(elev.max()),
          "median %.0f m of %.0f" % (np.median(elev), elev.max()))

    r, f = settled(opts(cache_dir=cache_dir, sweep=0.0, reveal=0.0))
    check("the live record renders a hill and not a card",
          not contains_text(f, "NO BIKE DATA") and f.max() > 0,
          "%d bikes, %d dry, %.1f m anomaly" % (t["bikes"], t["empty"], a))


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


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache-dir", default=ftdata.CACHE_DIR)
    ap.add_argument("--state", default="",
                    choices=("", "fresh", "stale", "absent"),
                    help="internal: run one data state and print RESULT")
    a = ap.parse_args()
    if a.state:
        return _one_state(a.state, a.cache_dir)

    print("cache: %s" % a.cache_dir)
    test_no_network()
    test_terrain_bake()
    test_hill_direction()
    test_ramp_direction()
    test_flags_and_mist()
    test_anomaly_sign()
    test_trend()
    test_lane()
    test_history_is_bounded()
    test_motion()
    test_purity()
    test_degraded()
    test_states_in_separate_processes()
    test_sizes()
    test_live(a.cache_dir)

    print("\n%d checks, %d failed" % (PASSED[0], len(FAILED)))
    for name in FAILED:
        print("  - %s" % name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
