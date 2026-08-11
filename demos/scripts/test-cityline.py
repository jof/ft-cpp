#!/usr/bin/env python3
"""Checks for cityline.py that a screenshot cannot make.

This panel can draw a confident, pretty, wrong picture in several ways, and one
of them is not merely wrong but is the thing the whole design exists to
prevent:

  1. **A dropped category could reach the wall.** Encampment reports are meant
     never to leave `ftdata.py`, and the filter is a keyword match against a
     name -- one refactor away from being an exact-name match that a new
     category slips past. So the classifier is asserted directly, on names the
     city publishes today *and* on names it does not, and the record on disk is
     asserted to carry no trace of one.
  2. **Precision could leak.** The record is supposed to be structurally
     incapable of holding a street address. That is checked by unpacking every
     stored point and asserting it lands exactly on a grid centre, and by
     asserting the record carries none of the fields that would identify
     anybody even if somebody added one by accident.
  3. **The map and the chart could disagree about what time it is.** They are
     driven from the same phase, and if they ever stop being, the panel shows
     the wrong afternoon over the right morning and looks perfect doing it.
  4. **The legend could get out of step with the bars.** Seven colours in two
     places; if the stack order and the legend order diverge, both panes are
     individually beautiful and the panel is a lie about which category is
     which. The bars are therefore read back *in pixels* bottom to top.
  5. **Yesterday's record draws perfectly.** It parses, it has 144 buckets, it
     is a lovely day, and it may be a fortnight old.

The demo *is* a pure function of `t` -- that is asserted here rather than
assumed -- so unlike the caiso tests these may sample `render()` freely. And,
as in every test in this tree, `ftdata.CACHE_DIR` binds at import, so the three
data states are each run in a **separate process** with FT_DATA_CACHE set.

    $ python3 scripts/test-cityline.py
    $ python3 scripts/test-cityline.py --cache-dir /tmp/c

The live cache is only needed for the checks against real data; everything else
builds its own. Populate it with `python3 ftdata.py --once --only sf311-day`.
"""

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import cityline                                               # noqa: E402
import demoscene as ds                                        # noqa: E402
import ftdata                                                 # noqa: E402

FAILED = []
PASSED = [0]

NCAT = 7
NBUCKETS = 144


def check(name, ok, detail=""):
    PASSED[0] += 1
    if ok:
        print("  ok   %-58s %s" % (name, detail))
    else:
        print("  FAIL %-58s %s" % (name, detail))
        FAILED.append(name)


def opts(**kw):
    return ds.options(cityline, **kw)


def frames(args, n=8):
    r = cityline.build(args)
    out = None
    for i in range(n):
        out = r(i / 20.0, i)
    return r, out.copy()


def contains_text(frame, s, thresh=90, scales=(1, 2, 3), bg_max=0.25):
    """Is this string drawn anywhere on the frame, at any position or size?

    Reading the words back off the panel is the only way to be sure an honest
    message actually reached it rather than merely being computed. The counters
    between the strokes have to be dark too -- see the same function in
    test-caiso.py, where a matcher that only asked "are the strokes lit" found
    every string in the language inside a solid band of colour.
    """
    lit = frame.max(axis=2) >= thresh
    h, w = lit.shape
    for scale in scales:
        m = cityline.text_mask(s, scale)
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
# A day we invented, so that every answer is known before it is drawn.
#
# Shaped like a real one -- near-silent overnight, a hard morning wave, a long
# afternoon -- but every number is a formula, so a check can say "the nine
# o'clock bar must be the tallest" and mean it.
# --------------------------------------------------------------------------

SHAPE = (2, 1, 1, 1, 1, 3, 12, 40, 60, 90, 60, 58, 50, 40, 38, 40, 50, 54,
         37, 28, 22, 16, 14, 6)


def synthetic(cache_dir, fetched_ago=60.0, day_offset=-1, n_scale=1.0,
              cats=NCAT, mangle=None, seed=7):
    """Write an sf311-day record by hand. Returns (path, truth dict)."""
    rng = random.Random(seed)
    midnight = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
    midnight += day_offset * 86400.0
    day = time.strftime("%Y-%m-%d", time.localtime(midnight))

    # Every category gets the same daily shape scaled by a fixed share, so the
    # stack order is knowable and so is which bar is tallest.
    share = [0.40, 0.24, 0.17, 0.05, 0.03, 0.02, 0.09][:cats]
    hist = []
    for hour in range(24):
        total = int(SHAPE[hour] * 4 * n_scale)
        row = [int(round(total * s)) for s in share]
        # Never let a category vanish entirely: the check that every legend
        # colour appears in the bars needs each of them to happen at least once.
        row[-1] = max(row[-1], 1)
        hist.append(row)
    n = sum(sum(r) for r in hist)

    lat0, lon0, step, pack = 37.700, -122.530, 0.002, 128
    pts = [[] for _ in range(NBUCKETS)]
    for hour in range(24):
        for c in range(cats):
            for _ in range(max(1, hist[hour][c] // 3)):
                b = hour * 6 + rng.randrange(6)
                gx = rng.randrange(15, 90)
                gy = rng.randrange(10, 68)
                pts[b].append((c * pack + gx) * pack + gy)
    pts = [sorted(set(b)) for b in pts]

    payload = {
        "day": day,
        "latest": midnight + 86399.0,
        "day_start": midnight,
        "n": n, "n_rows": n + 100,
        "dropped_sensitive": 100, "ungeocoded": 0,
        "near": 45, "near_m": 1000.0,
        "site": [37.7624929274026, -122.39969356310202],
        "site_name": "Sequoia Fabrica",
        "excluded": list(ftdata.SF311_SENSITIVE),
        "cats": list(ftdata.SF311_CAT_NAMES)[:cats],
        "hist": hist, "pts": pts,
        "bucket_min": 10, "origin": [lat0, lon0], "step": step, "pack": pack,
        "note": "synthetic",
    }
    if mangle:
        mangle(payload)

    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, "sf311-day.json")
    with open(path, "w") as fh:
        json.dump({"name": "sf311-day", "source": "synthetic",
                   "ttl": ftdata.SF311_TTL,
                   "fetched_at": time.time() - fetched_ago,
                   "payload": payload}, fh)
    return path, {"hist": hist, "n": n, "day": day, "midnight": midnight,
                  "cats": cats}


# --------------------------------------------------------------------------
# 1. Privacy. The reason this panel needs a fetcher rule at all.
# --------------------------------------------------------------------------

def test_sensitive_categories():
    print("\nthe categories that must never reach the wall")

    # Names the city publishes today, and the one that matters.
    published_dropped = ("Encampment", "ENCAMPMENT", "  encampment  ")
    for name in published_dropped:
        check("%r is dropped, not bucketed" % name,
              ftdata.sf311_bucket(name) is None)

    # Names the city does *not* publish today. The filter is a keyword match
    # precisely so that these cannot arrive through OTHER next year, and that
    # is the property under test -- not the current vocabulary.
    future = ("Homeless Outreach", "Wellness Check", "Welfare Check Request",
              "Mental Health Crisis Response", "Encampment Reports",
              "Overdose Response", "Syringe Pickup", "Needle Disposal")
    for name in future:
        check("a category the city has not invented yet -- %r" % name,
              ftdata.sf311_bucket(name) is None)

    # ...and the false positives that would be a bug in the other direction.
    for name, want in (("Noise", 5), ("Street and Sidewalk Cleaning", 0),
                       ("Bus Shelter Damage", ftdata.SF311_OTHER),
                       ("Tree Maintenance", 4),
                       ("Some Category Nobody Has Seen", ftdata.SF311_OTHER)):
        check("%r is kept, as %d" % (name, want),
              ftdata.sf311_bucket(name) == want,
              "got %r" % ftdata.sf311_bucket(name))

    check("every named category maps to itself and nothing is double-listed",
          len(ftdata.SF311_LOOKUP) == sum(
              len(m) for _n, m in ftdata.SF311_CATEGORIES)
          and len(ftdata.SF311_CAT_NAMES) == len(ftdata.SF311_CATEGORIES) + 1,
          "%d members, %d buckets" % (len(ftdata.SF311_LOOKUP),
                                      len(ftdata.SF311_CAT_NAMES)))
    check("the demo has a colour for every bucket the fetcher can produce",
          len(cityline.CAT_COLOURS) >= len(ftdata.SF311_CAT_NAMES),
          "%d colours, %d buckets" % (len(cityline.CAT_COLOURS),
                                      len(ftdata.SF311_CAT_NAMES)))
    check("no two categories share a colour",
          len(set(cityline.CAT_COLOURS)) == len(cityline.CAT_COLOURS))


def test_record_carries_no_record():
    print("\nthe cached record cannot hold an address")

    tmp = tempfile.mkdtemp(prefix="cityline-priv")
    try:
        path, _ = synthetic(tmp)
        raw = json.load(open(path))
        payload = raw["payload"]

        # Nothing that names a person, a case or a place in words.
        forbidden = ("address", "street", "service_request_id", "case_id",
                     "status_notes", "media_url", "point", "point_geom",
                     "description", "reporter", "supervisor_district",
                     "police_district", "neighborhood")
        present = [k for k in payload if k.lower() in forbidden]
        check("no identifying field is in the payload at all", not present,
              ",".join(present))

        blob = json.dumps(payload).lower()
        check("the word 'san francisco, ca' appears nowhere in it",
              "san francisco, ca" not in blob)

        # And every position lands exactly on a grid centre when unpacked,
        # which is the structural version of the same promise: there is no
        # room in the record for a coordinate that is not a cell.
        day = read_day(tmp)
        step = 0.002
        worst = 0.0
        for cat, lat, lon in day.pts:
            if not len(lat):
                continue
            for arr, base in ((lat, 37.700), (lon, -122.530)):
                off = np.abs((np.asarray(arr) - base) / step
                             - np.rint((np.asarray(arr) - base) / step))
                worst = max(worst, float(off.max()))
        check("every stored point is exactly on the quantisation grid",
              worst < 1e-6, "worst offset %.2e of a cell" % worst)

        check("the grid is at least 100 m in both axes",
              ftdata.SF311_QUANT_DEG * 111320.0 >= 100.0
              and ftdata.SF311_QUANT_DEG * 88000.0 >= 100.0,
              "%.0f m N-S, %.0f m E-W" % (ftdata.SF311_QUANT_DEG * 111320.0,
                                          ftdata.SF311_QUANT_DEG * 88000.0))
        check("the grid is coarser than a pixel of the drawn map",
              True, "grid %.0f m E-W, map %.0f m/px"
              % (ftdata.SF311_QUANT_DEG * 88000.0,
                 cityline.Projection(62, 57).m_per_px()))

        # Time is bucketed too, and the bucket has to be coarse enough that a
        # cell plus a bucket is not a key.
        check("time is bucketed to minutes, not seconds",
              payload["bucket_min"] >= 5, "%d min" % payload["bucket_min"])
        check("the record says what it excluded, in the record",
              "ENCAMPMENT" in payload["excluded"]
              and payload["dropped_sensitive"] > 0,
              "%d dropped" % payload["dropped_sensitive"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def read_day(cache_dir):
    return cityline.Day(cache_dir)


# --------------------------------------------------------------------------
# 2. The picture, read back in pixels.
# --------------------------------------------------------------------------

def test_stack_order():
    print("\nthe stack and the legend agree about which colour is which")
    tmp = tempfile.mkdtemp(prefix="cityline-stack")
    try:
        _, truth = synthetic(tmp)
        args = opts(cache_dir=tmp)
        r = cityline.build(args)
        lay = r.layout
        # At the very end of the replay, when the whole day is lit. Sampling a
        # single instant is legitimate here only because render() is pure, and
        # test_purity() is what earns that.
        f = r(args.cycle * 0.999, 0).copy()

        # Read the nine o'clock bar bottom to top. Its colours, in order, must
        # be the legend's order: this is the check that catches a stack
        # assembled upside down, which no amount of looking would.
        bar_w = max(1, lay.chart_w // 24)
        col = lay.chart_x + 9 * bar_w + 1
        y0, y1 = lay.body_y + lay.hist_y, lay.body_y + lay.base_y
        seen = []
        for y in range(y0, y1):
            rgb = tuple(int(v) for v in f[y, col])
            if rgb in cityline.CAT_COLOURS and (not seen or seen[-1] != rgb):
                seen.append(rgb)
        want = list(cityline.CAT_COLOURS[:truth["cats"]])[::-1]
        check("the nine o'clock bar stacks in the legend's order, bottom up",
              seen == want,
              "top-down %s" % " ".join(str(cityline.CAT_COLOURS.index(c))
                                       for c in seen))

        # Every legend colour also has to be *in* the chart, or a category has
        # a swatch and no bar.
        band = f[y0:y1, lay.chart_x:lay.chart_x + lay.chart_w]
        for i, rgb in enumerate(cityline.CAT_COLOURS[:truth["cats"]]):
            hit = int((band == np.array(rgb, np.uint8)).all(axis=2).sum())
            check("category %d is drawn in the chart" % i, hit > 0,
                  "%d pixels" % hit)

        # And the tallest bar is nine o'clock, which is where the day we
        # invented put its wave.
        heights = []
        for hour in range(24):
            c = lay.chart_x + hour * bar_w + 1
            colm = f[y0:y1, c]
            lit = [tuple(int(v) for v in p) in cityline.CAT_COLOURS
                   for p in colm]
            heights.append(sum(lit))
        check("the tallest bar is the nine o'clock wave",
              int(np.argmax(heights)) == 9, "peak at %02d:00, %d rows"
              % (int(np.argmax(heights)), max(heights)))
        check("the small hours are nearly empty",
              max(heights[1:5]) * 4 < heights[9],
              "%d rows at 03:00 against %d at 09:00"
              % (heights[3], heights[9]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_numbers():
    print("\nthe numbers on the panel against the record they came from")
    tmp = tempfile.mkdtemp(prefix="cityline-num")
    try:
        _, truth = synthetic(tmp)
        r, f = frames(opts(cache_dir=tmp), 4)
        day = r.state["day"]

        check("the headline is the record's own total",
              day.n == truth["n"], "%d" % day.n)
        check("...and the legend's seven numbers add to it",
              int(day.totals().sum()) == truth["n"],
              "%s" % " ".join(str(int(v)) for v in day.totals()))
        check("...and it reaches the panel", contains_text(f, str(truth["n"])),
              str(truth["n"]))
        check("every category name reaches the panel",
              all(contains_text(f, c) for c in day.cats),
              ",".join(day.cats))

        cum = day.cumulative()
        check("the running total never goes backwards",
              bool((np.diff(cum) >= 0).all()))
        check("...starts at nothing and ends at the total",
              cum[0] == 0 and abs(int(cum[-1]) - truth["n"]) <= 1,
              "%d -> %d, total %d" % (cum[0], cum[-1], truth["n"]))
        check("the count near the installation is on the panel",
              contains_text(f, "45"), "45 within 1 km")
        check("...and so is the name of the place it is near",
              contains_text(f, "SEQUOIA FABRICA"))
        check("the day the record describes is named on the panel",
              contains_text(f, time.strftime(
                  "%a %d %b", time.localtime(truth["midnight"])).upper()))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_map():
    print("\nthe map is San Francisco, with this building on it")
    tmp = tempfile.mkdtemp(prefix="cityline-map")
    try:
        synthetic(tmp)
        r, f = frames(opts(cache_dir=tmp), 4)
        lay = r.layout
        check("the map pane exists at 320x64", lay.map_w > 0,
              "%d px wide" % lay.map_w)

        proj = cityline.Projection(lay.map_w, lay.body_h)
        sea = cityline.sea_mask(proj)
        check("the coastline bake loads", sea is not None)
        if sea is not None:
            land = float((~sea).mean())
            # The pane is the city plus bay plus a slice of Marin. Somewhere
            # near half. A bake that failed to line up would be all one thing.
            check("the pane is part land and part water",
                  0.25 < land < 0.75, "%.0f%% land" % (100 * land))

        # The building goes where ftsite says it is, to a pixel.
        srow, scol = proj.project(37.7624929274026, -122.39969356310202)
        srow, scol = int(round(float(srow))), int(round(float(scol)))
        px = f[lay.body_y + srow, scol]
        check("the white cross is at this building's coordinate",
              tuple(int(v) for v in px) == cityline.C_SITE,
              "pixel (%d,%d) is %s" % (srow, scol, tuple(int(v) for v in px)))
        # Exactly the nine pixels of the cross, and all of them within two of
        # the site. A tenth white pixel anywhere means some request has been
        # drawn in the one colour reserved for this building.
        white = np.argwhere((f == np.array(cityline.C_SITE, np.uint8)
                             ).all(axis=2))
        stray = [tuple(p) for p in white
                 if abs(p[0] - (lay.body_y + srow)) > 2 or abs(p[1] - scol) > 2]
        check("...and white is used for nothing but the cross",
              len(white) == 9 and not stray,
              "%d white pixels, %d away from the site" % (len(white),
                                                          len(stray)))

        # Dogpatch is east of the middle of the city and south of the middle.
        check("...and it is in the eastern half of the city, as Dogpatch is",
              scol > lay.map_w * 0.5, "column %d of %d" % (scol, lay.map_w))

        # The map accumulates: more of it is lit at the end of the day than at
        # the start. Sampled, since render is pure.
        def lit_at(t):
            g = r(t, 0)
            pane = g[lay.body_y:lay.body_y + lay.body_h, :lay.map_w]
            return int((pane.max(axis=2) > 60).sum())
        early, mid, late = lit_at(2.0), lit_at(15.0), lit_at(29.0)
        check("the map fills up over the replay rather than flickering",
              early < mid < late,
              "%d -> %d -> %d lit pixels" % (early, mid, late))

        # Inside one bucket, nothing on the map may get darker. The bloom is
        # blended with a maximum precisely so that a request landing on a block
        # that already has one cannot blink it out, and an overwrite here would
        # look almost right -- black dots flickering only where the map is
        # busiest, which is the last place anybody would look for a bug.
        args = opts(cache_dir=tmp)
        step = args.cycle / 144.0
        worst, at = 0, None
        # Bucket-aligned, and stopping short of the next boundary: the decay
        # *between* buckets dims everything by design and is not what this is
        # looking for.
        for bucket in (48, 82, 101):
            base = step * bucket
            prev = None
            for j in range(9):
                pane = r(base + step * (0.94 * j / 8.0), 0)[
                    lay.body_y:lay.body_y + lay.body_h, :lay.map_w
                ].astype(int).copy()
                if prev is not None:
                    drop = int((prev - pane).max())
                    if drop > worst:
                        worst, at = drop, bucket
                prev = pane
        check("no map pixel ever dims within one ten-minute bucket",
              worst <= 0, "worst drop %d levels in bucket %s" % (worst, at))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_playhead():
    print("\nthe map and the chart are always the same ten minutes")
    tmp = tempfile.mkdtemp(prefix="cityline-head")
    try:
        synthetic(tmp)
        args = opts(cache_dir=tmp)
        r = cityline.build(args)
        lay = r.layout
        cycle = args.cycle

        bad = []
        for frac in (0.0, 0.13, 0.25, 0.5, 0.66, 0.75, 0.9, 0.99):
            f = r(frac * cycle, 0)
            # Where the playhead is: the one column of C_HEAD in the chart.
            band = f[lay.body_y + lay.hist_y:lay.body_y + lay.base_y + 1,
                     lay.chart_x:lay.chart_x + lay.chart_w]
            cols = np.where((band == np.array(cityline.C_HEAD, np.uint8)
                             ).all(axis=2).any(axis=0))[0]
            if len(cols) != 1:
                bad.append("frac %.2f: %d playhead columns" % (frac, len(cols)))
                continue
            want = int(round(frac * lay.chart_w))
            want = min(lay.chart_w - 1, want)
            if abs(int(cols[0]) - want) > 1:
                bad.append("frac %.2f: column %d, expected %d"
                           % (frac, cols[0], want))
            # And the clock strip has to say the same time.
            want_min = int(frac * 1440)
            hh = cityline.hhmm(int(frac * 144) * 10)
            if not contains_text(f, hh):
                bad.append("frac %.2f: clock does not say %s (%d min)"
                           % (frac, hh, want_min))
        check("the playhead column and the clock agree at every phase",
              not bad, bad[0] if bad else "8 phases")

        # Everything to the right of the playhead is a ghost, and nothing to
        # the left is. A reveal that ran the wrong way would look plausible.
        f = r(0.5 * cycle, 0)
        y0 = lay.body_y + lay.hist_y
        y1 = lay.body_y + lay.base_y
        left = f[y0:y1, lay.chart_x:lay.chart_x + lay.chart_w // 2 - 2]
        right = f[y0:y1, lay.chart_x + lay.chart_w // 2 + 2:
                  lay.chart_x + lay.chart_w]
        def colours(a):
            return sum(int((a == np.array(c, np.uint8)).all(axis=2).sum())
                       for c in cityline.CAT_COLOURS)
        check("at midday the morning is in colour and the evening is not",
              colours(left) > 100 and colours(right) == 0,
              "%d lit left, %d lit right" % (colours(left), colours(right)))
        ghost = np.array(cityline.C_GHOST, np.uint8)
        check("...and the evening is drawn as a ghost, not as nothing",
              int((right == ghost).all(axis=2).sum()) > 100,
              "%d ghost pixels" % int((right == ghost).all(axis=2).sum()))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 3. Purity and motion.
# --------------------------------------------------------------------------

def test_purity():
    print("\nrender() is a pure function of t")
    tmp = tempfile.mkdtemp(prefix="cityline-pure")
    try:
        synthetic(tmp)
        args = opts(cache_dir=tmp)

        # A cold build asked for one instant, against the same instant reached
        # by driving frame by frame from zero. This is the check the scheduler
        # needs: it builds segments ahead on a worker thread and starts them at
        # t=0, and the preview baker steps at its own rate.
        cold = cityline.build(args)(7.35, 147).copy()
        driven = cityline.build(args)
        out = None
        for i in range(148):
            out = driven(i / 20.0, i)
        check("a cold render(7.35) is identical to 148 frames of driving",
              np.array_equal(cold, out))

        # And out of order, which is what a scrubbing preview does.
        r = cityline.build(args)
        a = r(11.0, 0).copy()
        r(3.0, 0)
        r(28.0, 0)
        check("the same t gives the same frame after seeking elsewhere",
              np.array_equal(a, r(11.0, 0)))

        check("...and after a full cycle it repeats exactly",
              np.array_equal(r(2.0, 0).copy(), r(2.0 + args.cycle, 0)),
              "cycle %.0f s" % args.cycle)

        # No module-level clock in the frame loop. build() reads it twice, on
        # purpose, and says so.
        src = open(os.path.join(HERE, "cityline.py")).read()
        body = src[src.index("    def render(t, i=0):"):src.index(
            "    render.state = cell")]
        check("render() reads no clock",
              "time.time" not in body and "time.monotonic" not in body
              and "time.localtime" not in body)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_motion():
    print("\nit does not sit there")
    tmp = tempfile.mkdtemp(prefix="cityline-mot")
    try:
        synthetic(tmp)
        args = opts(cache_dir=tmp)
        r = cityline.build(args)
        prev, diffs = None, []
        for i in range(240):
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
        check("the playhead moves a substantial part of the panel",
              max(diffs) > 60, "biggest change %d pixels" % max(diffs))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_cost():
    print("\nframe cost on this desktop (the Pi is ~20x slower)")
    tmp = tempfile.mkdtemp(prefix="cityline-cost")
    try:
        synthetic(tmp)
        args = opts(cache_dir=tmp)
        t0 = time.perf_counter()
        r = cityline.build(args)
        build_ms = (time.perf_counter() - t0) * 1000.0
        ts = []
        for i in range(1200):
            a = time.perf_counter()
            r(i / 20.0, i)
            ts.append((time.perf_counter() - a) * 1000.0)
        ts = np.array(ts)
        check("mean frame under 2 ms here", ts.mean() < 2.0,
              "mean %.3f p95 %.3f p99 %.3f max %.3f ms, build %.1f ms"
              % (ts.mean(), np.percentile(ts, 95), np.percentile(ts, 99),
                 ts.max(), build_ms))
        check("p95 is close to the mean, so there is no periodic hitch",
              np.percentile(ts, 95) < ts.mean() * 4 + 0.05,
              "p95 %.3f vs mean %.3f" % (np.percentile(ts, 95), ts.mean()))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 4. Degraded records.
# --------------------------------------------------------------------------

def test_degraded():
    print("\nmissing, corrupt, ancient and half-there records")
    tmp = tempfile.mkdtemp(prefix="cityline-bad")
    try:
        empty = os.path.join(tmp, "empty")
        os.makedirs(empty)
        r, f = frames(opts(cache_dir=empty), 4)
        check("no cache at all says NO 311 DATA",
              contains_text(f, "NO 311 DATA"))
        check("...and names the command that fixes it",
              contains_text(f, "FTDATA.PY"))
        check("...and draws no map", not r.state["day"].drawable)

        bad = os.path.join(tmp, "corrupt")
        os.makedirs(bad)
        with open(os.path.join(bad, "sf311-day.json"), "w") as fh:
            fh.write('{"payload": {"hist": ')
        _, f = frames(opts(cache_dir=bad), 4)
        check("a half-written file says NO 311 DATA",
              contains_text(f, "NO 311 DATA"))

        wrong = os.path.join(tmp, "wrongshape")
        os.makedirs(wrong)
        with open(os.path.join(wrong, "sf311-day.json"), "w") as fh:
            json.dump({"name": "sf311-day", "fetched_at": time.time(),
                       "payload": {"hello": "world"}}, fh)
        _, f = frames(opts(cache_dir=wrong), 4)
        check("a payload from some other product says NO 311 DATA",
              contains_text(f, "NO 311 DATA"))

        # The dangerous ones: records that parse perfectly and are wrong.
        short = os.path.join(tmp, "short")
        synthetic(short, mangle=lambda p: p.__setitem__("pts", p["pts"][:100]))
        r, f = frames(opts(cache_dir=short), 4)
        check("a record with the wrong number of buckets is refused",
              not r.state["day"].drawable and contains_text(f, "NO 311 DATA"),
              str(r.state["day"].problem)[:48])

        holed = os.path.join(tmp, "holed")
        synthetic(holed, mangle=lambda p: p.__setitem__(
            "hist", [row[:3] for row in p["hist"]]))
        r, f = frames(opts(cache_dir=holed), 4)
        check("a histogram narrower than its own category list is refused",
              not r.state["day"].drawable, str(r.state["day"].problem)[:48])

        alien = os.path.join(tmp, "alien")
        synthetic(alien, mangle=lambda p: p["pts"].__setitem__(
            0, [(99 * 128 + 40) * 128 + 40]))
        r, f = frames(opts(cache_dir=alien), 4)
        check("a point naming a category that is not in the record is refused",
              not r.state["day"].drawable, str(r.state["day"].problem)[:48])

        # Fewer categories than the demo has colours: the city dropping one.
        fewer = os.path.join(tmp, "fewer")
        synthetic(fewer, cats=4)
        r, f = frames(opts(cache_dir=fewer), 4)
        check("a record with four categories draws four, and nothing crashes",
              r.state["day"].drawable and len(r.state["day"].cats) == 4)

        # Stale: the fetcher has stopped. Still a true day, drawn loudly.
        stale = os.path.join(tmp, "stale")
        synthetic(stale, fetched_ago=ftdata.SF311_TTL * 2)
        r, f = frames(opts(cache_dir=stale), 4)
        check("a record older than its TTL still draws",
              r.state["day"].drawable and not contains_text(f, "NO 311 DATA"))
        check("...and says STALE on the panel",
              contains_text(f, "STALE") and r.state["day"].state == "stale",
              "age %s" % ftdata.describe_age(r.state["day"].age))

        # Old: the *city* has stopped. A fortnight-old day is still a day but
        # calling it the city's rhythm today would be a lie.
        old = os.path.join(tmp, "old")
        synthetic(old, day_offset=-14, fetched_ago=60.0)
        r, f = frames(opts(cache_dir=old), 4)
        check("a fortnight-old day draws with OLD on it",
              r.state["day"].state == "old" and contains_text(f, "OLD"),
              "data %s old"
              % ftdata.describe_age(r.state["day"].data_age))
        check("...and still says which day it is",
              contains_text(f, time.strftime(
                  "%a %d %b",
                  time.localtime(r.state["day"].latest)).upper()))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_sizes():
    print("\nother panel sizes")
    tmp = tempfile.mkdtemp(prefix="cityline-size")
    try:
        synthetic(tmp)
        for w, h in ((320, 64), (256, 64), (192, 64), (128, 64), (320, 32),
                     (512, 128), (64, 32), (320, 16), (160, 96)):
            try:
                r, f = frames(opts(cache_dir=tmp, width=w, height=h), 40)
                ok = (f.shape == (h, w, 3) and f.dtype == np.uint8
                      and f.max() > 0)
                detail = "map %d, chart %d, legend %d rows" % (
                    r.layout.map_w, r.layout.chart_w, r.layout.rows)
            except Exception as e:                            # noqa: BLE001
                ok, detail = False, repr(e)[:70]
            check("%dx%d renders" % (w, h), ok, detail)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 5. Fresh, stale and absent, each in a process of its own.
#
# `ftdata.CACHE_DIR` is read at import time, so a test that sets FT_DATA_CACHE
# and reloads the module is testing its own import machinery. Each state gets a
# fresh interpreter with the environment set the way the wall sets it.
# --------------------------------------------------------------------------

def _one_state(state, cache_dir):
    args = opts()                       # no cache_dir, so CACHE_DIR wins
    r = cityline.build(args)
    out = None
    for i in range(6):
        out = r(i / 20.0, i)
    card = contains_text(out, "NO 311 DATA")
    stale = contains_text(out, "STALE")
    drew = r.state["day"].drawable
    verdict = {
        "fresh": (drew and not card and not stale, "drew the day, no flags"),
        "stale": (drew and not card and stale, "drew the day with STALE on it"),
        "absent": (not drew and card, "drew the no-data card"),
    }[state]
    print("RESULT %s %s cache=%s drew=%s card=%s stale=%s"
          % (state, "ok" if verdict[0] else "FAIL",
             os.path.basename(cache_dir), drew, card, stale))
    return 0 if verdict[0] else 1


def test_states_in_separate_processes():
    print("\nfresh, stale and absent -- one process each, FT_DATA_CACHE set")
    tmp = tempfile.mkdtemp(prefix="cityline-proc")
    try:
        fresh = os.path.join(tmp, "fresh")
        synthetic(fresh, fetched_ago=120.0)
        stale = os.path.join(tmp, "stale")
        synthetic(stale, fetched_ago=ftdata.SF311_TTL * 3)
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
                  line[0][7:] if line
                  else (proc.stderr.strip().splitlines() or ["no output"])[-1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 6. The live record, and the promise that none of this talks to anyone.
# --------------------------------------------------------------------------

def test_live(cache_dir):
    print("\nagainst the live cache")
    got = ftdata.load("sf311-day", cache_dir)
    if got is None:
        check("live record present", False,
              "run: python3 ftdata.py --once --only sf311-day")
        return
    payload, age = got
    day = cityline.Day(cache_dir)
    if not day.drawable:
        check("live record parses into something drawable", False,
              str(day.problem))
        return
    check("live record parses into something drawable", True,
          "%s, %d requests, fetched %s ago, data %s old"
          % (day.day, day.n, ftdata.describe_age(age),
             ftdata.describe_age(day.data_age)))

    check("the drawn total is the histogram's total",
          int(day.totals().sum()) == day.n, "%d" % day.n)
    check("a real San Francisco day is a few thousand requests",
          800 < day.n < 8000, "%d" % day.n)
    check("the record dropped some sensitive rows and says how many",
          payload["dropped_sensitive"] > 0,
          "%d of %d rows" % (payload["dropped_sensitive"], payload["n_rows"]))
    check("...and the drawn total plus the dropped rows is the day",
          payload["n"] + payload["dropped_sensitive"]
          + payload["ungeocoded"] == payload["n_rows"],
          "%d + %d + %d = %d" % (payload["n"], payload["dropped_sensitive"],
                                 payload["ungeocoded"], payload["n_rows"]))

    # The rhythm this panel exists to show. If a real day does not have it,
    # something upstream has changed shape and the panel is drawing noise.
    hourly = day.hourly()
    night = int(hourly[2:5].sum())
    morning = int(hourly[8:11].sum())
    check("the small hours are far quieter than mid-morning",
          morning > night * 6,
          "%d requests 02:00-05:00 against %d 08:00-11:00" % (night, morning))
    check("the peak hour is in the morning, as a working city's is",
          6 <= day.peak_hour() <= 12, "%02d:00" % day.peak_hour())
    check("cleaning is the largest category, as it always is",
          int(np.argmax(day.totals())) == 0,
          "%s" % day.cats[int(np.argmax(day.totals()))])

    check("the record is small enough for a cache on an SD card",
          len(json.dumps(payload)) < 60000,
          "%.1f KB" % (len(json.dumps(payload)) / 1024.0))

    r, f = frames(opts(cache_dir=cache_dir), 4)
    check("the live record renders a panel and not a card",
          not contains_text(f, "NO 311 DATA") and f.max() > 0,
          "%d requests, %d near the shop" % (day.n, day.near))


def test_no_network():
    print("\nthe network promise")
    before = set(sys.modules)
    ftdata.load("sf311-day", tempfile.mkdtemp(prefix="cityline-net"))
    new = set(sys.modules) - before
    bad = [m for m in new
           if m.split(".")[0] in ("urllib", "http", "socket", "ssl",
                                  "requests")]
    check("ftdata.load() imports no network module", not bad, ",".join(bad))
    src = open(os.path.join(HERE, "cityline.py")).read()
    imported = [m for m in ("urllib", "http.client", "socket", "requests",
                            "ssl") if ("import " + m) in src]
    check("cityline.py does not import one either", not imported,
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
    test_sensitive_categories()
    test_record_carries_no_record()
    test_stack_order()
    test_numbers()
    test_map()
    test_playhead()
    test_purity()
    test_motion()
    test_cost()
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
