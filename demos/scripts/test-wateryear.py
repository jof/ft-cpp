#!/usr/bin/env python3
"""Checks for wateryear.py that a screenshot cannot make.

This panel can draw a calm, plausible, wrong picture in at least six ways, and
not one of them looks wrong:

  1. **The transect can be mirrored.** Eight vessels are eight vessels. Pine
     Flat on the left and Trinity on the right is exactly as pretty and says
     the opposite thing about which end of the state is short of water.
  2. **The level can be upside down.** A vessel drawn from the top is a
     perfectly good picture of a reservoir that is 34% full when it is 66%.
  3. **The snow can grow the wrong way.** Snow that fills upward from the
     valley instead of down from the crest still whitens in February and still
     melts in May.
  4. **The normal line can be a season out.** The day-of-water-year mapping is
     an index into a 366-long curve, and an axis that starts in October is
     exactly the kind of thing that ends up 92 or 273 days wrong while still
     producing a smooth, believable dashed line on every vessel.
  5. **The last sample is usually empty.** CDEC's numbers for today land in the
     morning; before that, reading `[-1]` reports an empty Shasta.
  6. **Last year's record draws perfectly.** It parses, it has a full year in
     it, and it is the wrong year.

So the drawing is asserted **in pixels** against a synthetic year whose answers
cannot be argued with -- eight reservoirs at eight known fractions, a snowpack
that is a known bell, a normals file that is a known constant -- and the
arithmetic is asserted separately against the same numbers.

Two things about how these are run, both learned in this tree. `render` here
*is* a pure function of `t` and the purity check below asserts it, so frames
may be sampled anywhere; but `ftdata.CACHE_DIR` binds at import, so the three
data states a demo must handle -- fresh, stale, absent -- are each run in a
**separate process** with FT_DATA_CACHE set, at the bottom of this file.
Reloading the module in one process does not test what it looks like it tests.

    $ python3 scripts/test-wateryear.py                     # uses the live cache
    $ python3 scripts/test-wateryear.py --cache-dir /tmp/c  # or a pointed one

The live cache is only needed for the checks against real CDEC data;
everything else builds its own cache directory and its own normals file and
needs nothing. Populate it with `python3 ftdata.py --once --only wateryear`.

    $ python3 scripts/test-wateryear.py --write-winter /tmp/wy-winter

writes a synthetic snow-heavy record into that directory and nothing else, so
a reviewer in August can point the demo at it and see what February looks like
without waiting six months:

    $ FT_DATA_CACHE=/tmp/wy-winter python3 wateryear.py --host 127.0.0.1
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

import demoscene as ds                                        # noqa: E402
import ftdata                                                 # noqa: E402
import wateryear as wy                                        # noqa: E402

FAILED = []
PASSED = [0]


def check(name, ok, detail=""):
    PASSED[0] += 1
    if ok:
        print("  ok   %-58s %s" % (name, detail))
    else:
        print("  FAIL %-58s %s" % (name, detail))
        FAILED.append(name)


def opts(**kw):
    return ds.options(wy, **kw)


def frame_at(args, t=40.0):
    """One frame, and the render callback it came from."""
    r = wy.build(args)
    return r, r(t, int(t * 20)).copy()


def contains_text(frame, s, thresh=90, scales=(1, 2), bg_max=0.25):
    """Is this string drawn anywhere on the frame, at any position or size?

    Reading the words back off the panel is the only way to be sure the honest
    message reached it rather than merely being computed. The counters between
    the strokes have to be dark as well -- without that check a matcher says
    yes to every string in the language somewhere inside a block of lit water,
    which cost caiso's version of this function four false passes.
    """
    lit = frame.max(axis=2) >= thresh
    h, w = lit.shape
    for scale in scales:
        m = wy.text_mask(s, scale)
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


def wet_rows(frame, lay, x):
    """How many rows of column x inside the vessel band read as water.

    Water is the only thing in that band with a blue bias; the empty shell,
    the walls and the reservoir label are all neutral or lighter. Counting by
    hue rather than by exact colour survives the dither, which moves every
    channel by a level or two.
    """
    seg = frame[lay.ves_y0:lay.ves_y1 + 1, x].astype(int)
    # +40 and not +24: the dry reservoir label is a blue-grey and slips under a
    # looser threshold, which made every vessel read two or three rows fuller
    # than it was drawn -- and read them fuller in proportion to how long the
    # label was, which is not a pattern anybody would have noticed by eye.
    return int(((seg[:, 2] > seg[:, 0] + 40) & (seg[:, 2] > 40)).sum())


def snow_rows(frame, lay, x):
    """Rows of column x inside the ridge band that read as snow, not rock."""
    seg = frame[lay.ridge_y0:lay.ridge_y1 + 1, x].astype(int)
    return int((seg.min(axis=1) > 120).sum())


def amber_rows(frame, lay, x):
    """Rows of column x that carry the amber 'normal for this date' mark."""
    seg = frame[lay.ves_y0:lay.ves_y1 + 1, x].astype(int)
    return [i for i in range(len(seg))
            if seg[i, 0] > seg[i, 2] + 40 and seg[i, 0] > 120]


# --------------------------------------------------------------------------
# A water year we invented, so that every answer is known before it is drawn.
#
# Eight reservoirs at eight fractions that ascend left to right, which makes a
# mirrored transect impossible to miss; a snowpack that is a clean bell peaking
# on 1 April; and normals that are a flat half of capacity all year, so the
# expected row of every dashed line is one number and not a curve.
# --------------------------------------------------------------------------

FRACS = (0.10, 0.20, 0.30, 0.40, 0.55, 0.65, 0.75, 0.85)
SNOW_PEAK_DOY = 182                     # 1 April on the leap template
SNOW_PEAK_IN = 24.0
NORM_FRACTION = 0.5


def synthetic(cache_dir, wy_year=None, days_in=None, fetched_ago=0.0,
              fracs=FRACS, snow_peak=SNOW_PEAK_IN, last_null=True,
              drop=(), mangle=None, stride=2):
    """Write a wateryear record by hand. Returns (path, truth dict)."""
    now = time.time()
    real_wy, start = ftdata._wy_water_year(now)
    if wy_year is None:
        wy_year = real_wy
    if wy_year != real_wy:
        start = time.mktime((wy_year - 1, 10, 1, 0, 0, 0, 0, 0, -1))
    n_days = days_in if days_in is not None else \
        min(ftdata.WY_DAYS, int(round((now - start) / 86400.0)) + 1)
    idx = sorted(set(range(n_days - 1, -1, -stride)) | {max(0, n_days - 2)})

    codes = [c for c, _l, _cap, _lat in ftdata.WY_RESERVOIRS]
    caps = {c: int(round(cap / 1000.0))
            for c, _l, cap, _lat in ftdata.WY_RESERVOIRS}
    labels = {c: l for c, l, _cap, _lat in ftdata.WY_RESERVOIRS}
    lats = {c: lat for c, _l, _cap, lat in ftdata.WY_RESERVOIRS}

    res = {}
    for k, c in enumerate(codes):
        f = fracs[k % len(fracs)]
        v = [None if c in drop else int(round(caps[c] * f)) for _ in idx]
        if last_null and v:
            # The normal state of this record for most of every day: CDEC has
            # not published today yet.
            v[-1] = None
        res[c] = v

    def doy(i):
        lt = time.localtime(start + i * 86400.0 + 43200.0)
        d = ftdata.wateryear_doy(lt.tm_mon, lt.tm_mday)
        return ftdata.WY_DAYS - 1 if d is None else d

    snow = {}
    for region, _stations in ftdata.WY_SNOW:
        vals = []
        for i in idx:
            # Asymmetric, like the real thing: five months to build and two
            # to go. A symmetric bell still has snow on it in July, which is
            # not a season anybody in California would recognise.
            d = doy(i) - SNOW_PEAK_DOY
            x = d / (90.0 if d < 0 else 38.0)
            vals.append(round(snow_peak * math.exp(-x * x), 1)
                        if abs(x) < 3.0 else 0.0)
        snow[region] = vals

    asof = None
    for j in range(len(idx) - 1, -1, -1):
        if any(res[c][j] is not None for c in codes):
            asof = start + idx[j] * 86400.0
            break

    payload = {
        "wy": wy_year, "start": start, "n_days": n_days, "days": idx,
        "asof": asof, "res_order": codes, "res_label": labels,
        "res_lat": lats, "cap_kaf": caps, "res_kaf": res,
        "snow_order": [r for r, _s in ftdata.WY_SNOW], "snow_in": snow,
        "snow_n": {r: [6] * len(idx) for r, _s in ftdata.WY_SNOW},
        "snow_stations": {r: 6 for r, _s in ftdata.WY_SNOW},
        "units": {"storage": "thousand acre-feet", "snow": "inches"},
    }
    if mangle:
        mangle(payload)

    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, "wateryear.json")
    with open(path, "w") as fh:
        json.dump({"name": "wateryear", "fetched_at": now - fetched_ago,
                   "source": "synthetic", "ttl": ftdata.WY_TTL,
                   "payload": payload}, fh)

    truth = {"codes": codes, "caps": caps, "fracs": list(fracs),
             "idx": idx, "start": start, "wy": wy_year, "asof": asof,
             "n_days": n_days,
             "stored": sum(caps[c] * fracs[k % len(fracs)]
                           for k, c in enumerate(codes) if c not in drop),
             "capacity": sum(caps[c] for c in codes if c not in drop)}
    return path, truth


def synthetic_normals(path, fraction=NORM_FRACTION, snow_peak=SNOW_PEAK_IN):
    """A normals file that is a flat fraction of capacity all year.

    Flat on purpose: the expected row of every dashed line is then a single
    number, so a mapping that is a season out shows up as a line in the wrong
    place rather than as a line that is plausibly somewhere else.
    """
    codes = [c for c, _l, _cap, _lat in ftdata.WY_RESERVOIRS]
    res = np.stack([np.full(ftdata.WY_DAYS, cap / 1000.0 * fraction, np.float32)
                    for _c, _l, cap, _lat in ftdata.WY_RESERVOIRS])
    doy = np.arange(ftdata.WY_DAYS, dtype=np.float32)
    d = doy - SNOW_PEAK_DOY
    bell = snow_peak * np.exp(-(d / np.where(d < 0, 90.0, 38.0)) ** 2)
    snow = np.stack([bell.astype(np.float32)
                     for _r, _s in ftdata.WY_SNOW])
    np.savez_compressed(path, res_codes=np.array(codes), res_norm=res,
                        snow_regions=np.array([r for r, _s in ftdata.WY_SNOW]),
                        snow_norm=snow,
                        years=np.arange(2011, 2026, dtype=np.int32))
    return path


# --------------------------------------------------------------------------
# 1. The calendar. Everything downstream indexes a 366-long curve with it.
# --------------------------------------------------------------------------

def test_calendar():
    print("\nday-of-water-year")
    check("1 October is day 0", ftdata.wateryear_doy(10, 1) == 0)
    check("30 September is day 365", ftdata.wateryear_doy(9, 30) == 365)
    check("1 January is day 92", ftdata.wateryear_doy(1, 1) == 92,
          str(ftdata.wateryear_doy(1, 1)))
    check("29 February has a slot of its own",
          ftdata.wateryear_doy(2, 29) == 151, str(ftdata.wateryear_doy(2, 29)))
    check("1 March follows it", ftdata.wateryear_doy(3, 1) == 152)
    seen = sorted(ftdata.wateryear_doy(m, d)
                  for m, n in ftdata._WY_MONTH_DAYS for d in range(1, n + 1))
    check("every date maps to a distinct day and the year is full",
          seen == list(range(ftdata.WY_DAYS)))
    check("a date outside the calendar is None",
          ftdata.wateryear_doy(2, 30) is None
          and ftdata.wateryear_doy(13, 1) is None)

    # The water year boundary itself: 30 September and 1 October are different
    # years, and getting that backwards moves every axis by a full year.
    sep = time.mktime((2026, 9, 30, 12, 0, 0, 0, 0, -1))
    oct_ = time.mktime((2026, 10, 1, 12, 0, 0, 0, 0, -1))
    check("30 Sep 2026 is water year 2026",
          ftdata._wy_water_year(sep)[0] == 2026)
    check("1 Oct 2026 is water year 2027",
          ftdata._wy_water_year(oct_)[0] == 2027)


# --------------------------------------------------------------------------
# 2. The vessels, in pixels.
# --------------------------------------------------------------------------

def test_vessels():
    print("\nthe eight vessels")
    tmp = tempfile.mkdtemp(prefix="wy-ves")
    try:
        synthetic(tmp)
        norm = synthetic_normals(os.path.join(tmp, "n.npz"))
        r, f = frame_at(opts(cache_dir=tmp, normals=norm, sweep=0.0,
                             melt=0.0, snowfall=0.0))
        lay = r.layout
        rec = r.state["rec"]
        vx = wy.vessel_columns(lay.w, len(rec["order"]))

        got = [wet_rows(f, lay, x0 + 2) for x0, x1 in vx]
        want = [int(round(FRACS[k] * lay.ves_h)) for k in range(len(vx))]
        check("each vessel is filled to its own fraction, in rows",
              all(abs(a - b) <= 1 for a, b in zip(got, want)),
              "got %s want %s" % (got, want))
        check("the fill ascends left to right, so the transect is not mirrored",
              got == sorted(got) and got[0] < got[-1], str(got))

        # Bottom-anchored. A vessel drawn from the top is the same row count.
        x = vx[3][0] + 2
        col = f[lay.ves_y0:lay.ves_y1 + 1, x].astype(int)
        wet = [i for i in range(len(col))
               if col[i, 2] > col[i, 0] + 40 and col[i, 2] > 40]
        check("the water sits on the bottom of the vessel, not the top",
              wet and wet[-1] == lay.ves_h - 1 and wet[0] > 0
              and len(wet) < lay.ves_h,
              "rows %d..%d of %d" % (wet[0], wet[-1], lay.ves_h))

        # North to south: the record's own order must be descending latitude,
        # and vessel k must be drawn at column k.
        lats = [rec["lat"][c] for c in rec["order"]]
        check("the reservoirs are stored north to south",
              lats == sorted(lats, reverse=True), "%.1f..%.1f" % (lats[0],
                                                                 lats[-1]))
        check("the northernmost is drawn leftmost",
              rec["order"][0] == "CLE" and rec["order"][-1] == "PNF",
              "%s .. %s" % (rec["order"][0], rec["order"][-1]))
        missing = [c for c in rec["order"]
                   if not contains_text(r.background, rec["label"][c])]
        check("every reservoir is named on the dry shell", not missing,
              ",".join(missing))
        # ...and the full ones carry the dark version, drawn into the water
        # layer, which no lit-pixel matcher can see. Compare the label rows of
        # the fullest vessel against the water either side of them.
        x0, x1 = vx[-1]
        band = f[lay.ves_y0 + 1:lay.ves_y0 + 1 + wy.text_height(),
                 x0 + 1:x1].astype(int)
        check("...and the full ones carry it under the water too",
              band.min() < band.max() - 60,
              "spread %d" % int(band.max() - band.min()))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_normal_line():
    print("\nthe normal-for-this-date marks")
    tmp = tempfile.mkdtemp(prefix="wy-norm")
    try:
        synthetic(tmp)
        norm = synthetic_normals(os.path.join(tmp, "n.npz"))
        r, f = frame_at(opts(cache_dir=tmp, normals=norm, sweep=0.0,
                             melt=0.0, snowfall=0.0))
        lay = r.layout
        vx = wy.vessel_columns(lay.w, len(r.state["rec"]["order"]))
        want = lay.ves_h - int(round(NORM_FRACTION * (lay.ves_h - 1))) - 1
        rows = []
        for x0, x1 in vx:
            for x in range(x0 + 1, x1):
                got = amber_rows(f, lay, x)
                if got:
                    rows.append(got[0])
                    break
        check("every vessel carries a dashed normal", len(rows) == len(vx),
              "%d of %d" % (len(rows), len(vx)))
        check("...at the row the flat normals put it",
              rows and all(abs(v - want) <= 1 for v in rows),
              "rows %s want %d" % (sorted(set(rows)), want))

        # A season out. The normals file is flat, so a broken day mapping would
        # not move this line -- so this check uses a normals file that is a
        # ramp, where being 92 days out is 92/366 of the vessel.
        ramp = os.path.join(tmp, "ramp.npz")
        codes = [c for c, _l, _cap, _lat in ftdata.WY_RESERVOIRS]
        frac = np.linspace(0.05, 0.95, ftdata.WY_DAYS, dtype=np.float32)
        np.savez_compressed(
            ramp, res_codes=np.array(codes),
            res_norm=np.stack([frac * (cap / 1000.0)
                               for _c, _l, cap, _lat in ftdata.WY_RESERVOIRS]),
            snow_regions=np.array([r for r, _s in ftdata.WY_SNOW]),
            snow_norm=np.zeros((len(ftdata.WY_SNOW), ftdata.WY_DAYS),
                               np.float32),
            years=np.arange(2011, 2026, dtype=np.int32))
        # Not --sweep 0, which means "open on today": this check is about
        # what the mark says on the first day of the year.
        r2, f2 = frame_at(opts(cache_dir=tmp, normals=ramp,
                               melt=0.0, snowfall=0.0), t=0.0)
        # At t=0 the sweep is on 1 October, where the ramp normal is 5%.
        lay = r2.layout
        want0 = lay.ves_h - int(round(0.05 * (lay.ves_h - 1))) - 1
        first = None
        for x in range(vx[0][0] + 1, vx[0][1]):
            got = amber_rows(f2, lay, x)
            if got:
                first = got[0]
                break
        check("on 1 October the mark is at 1 October's normal",
              first is not None and abs(first - want0) <= 1,
              "row %s want %d" % (first, want0))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 3. The mountain.
# --------------------------------------------------------------------------

def test_snow():
    print("\nthe snowpack")
    tmp = tempfile.mkdtemp(prefix="wy-snow")
    try:
        synthetic(tmp)
        norm = synthetic_normals(os.path.join(tmp, "n.npz"))
        base = dict(cache_dir=tmp, normals=norm, melt=0.0, snowfall=0.0)

        r_oct, f_oct = frame_at(opts(hold_at="2000-10-15", **base))
        r_apr, f_apr = frame_at(opts(hold_at="2000-04-01", **base))
        r_jul, f_jul = frame_at(opts(hold_at="2000-07-15", **base))
        lay = r_apr.layout
        crest = wy.ridge_profile(lay.w, lay.ridge_y0, lay.ridge_y1)
        tall = int(np.argmin(crest))            # the highest column

        oct_n = snow_rows(f_oct, lay, tall)
        apr_n = snow_rows(f_apr, lay, tall)
        jul_n = snow_rows(f_jul, lay, tall)
        check("there is no snow in October", oct_n == 0, "%d rows" % oct_n)
        check("there is snow on 1 April", apr_n >= 4, "%d rows" % apr_n)
        check("it has melted out by mid July", jul_n == 0, "%d rows" % jul_n)

        # Downward, not upward: the snow has to start at the crest.
        col = f_apr[lay.ridge_y0:lay.ridge_y1 + 1, tall].astype(int)
        white = [i for i in range(len(col)) if col[i].min() > 120]
        top = crest[tall] - lay.ridge_y0
        check("the snow starts at the crest and lies down the flank",
              white and white[0] == top and white[-1] < lay.ridge_h - 1,
              "rows %d..%d, crest %d" % (white[0], white[-1], top))

        # The snowline descends as the pack grows, which is the entire visual
        # claim of the winter half of this panel.
        r_feb, f_feb = frame_at(opts(hold_at="2000-02-01", **base))
        feb_n = snow_rows(f_feb, lay, tall)
        check("the snowline descends between February and April",
              apr_n > feb_n > 0, "%d then %d rows" % (feb_n, apr_n))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_melt_connects():
    print("\nmeltwater")
    tmp = tempfile.mkdtemp(prefix="wy-melt")
    try:
        synthetic(tmp)
        norm = synthetic_normals(os.path.join(tmp, "n.npz"))
        args = opts(cache_dir=tmp, normals=norm, snowfall=0.0,
                    hold_at="2000-05-10")
        r = wy.build(args)
        lay = r.layout
        # The gap between the mountain and the vessels is where a stream can
        # only be a stream: nothing else is ever drawn there.
        # Between the snowline and the water: the streams cross the bare rock
        # and the valley, and nothing else is ever drawn in exactly C_MELT.
        gap = slice(lay.ridge_y0, lay.ves_y0)
        seen = 0
        for i in range(60):
            f = r(i / 20.0, i)
            seen += int((f[gap] == np.array(wy.C_MELT, np.uint8)
                         ).all(axis=2).sum())
        check("meltwater runs from the snow down to the lakes in May",
              seen > 0, "%d stream pixels over 60 frames" % seen)

        args = opts(cache_dir=tmp, normals=norm, snowfall=0.0,
                    hold_at="2000-11-20")
        r = wy.build(args)
        seen = 0
        for i in range(60):
            f = r(i / 20.0, i)
            seen += int((f[gap] == np.array(wy.C_MELT, np.uint8)
                         ).all(axis=2).sum())
        check("...and does not, in November", seen == 0,
              "%d stream pixels" % seen)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 4. The numbers.
# --------------------------------------------------------------------------

def test_numbers():
    print("\nthe arithmetic")
    tmp = tempfile.mkdtemp(prefix="wy-num")
    try:
        _p, truth = synthetic(tmp)
        norm = synthetic_normals(os.path.join(tmp, "n.npz"))
        r, f = frame_at(opts(cache_dir=tmp, normals=norm, sweep=0.0))
        st = r.state

        want_cap = 100.0 * truth["stored"] / truth["capacity"]
        check("percent of capacity is storage over capacity",
              abs(st["pct_cap"] - want_cap) < 0.5,
              "%.1f%% want %.1f%%" % (st["pct_cap"], want_cap))
        # Flat normals at half of capacity, so the answer is fixed whatever the
        # fractions are: mean fraction over a half.
        want_avg = want_cap / (100.0 * NORM_FRACTION) * 100.0
        check("percent of average is storage over the day's normal",
              abs(st["pct_avg"] - want_avg) < 0.5,
              "%.1f%% want %.1f%%" % (st["pct_avg"], want_avg))
        check("million acre-feet is thousand acre-feet over a thousand",
              abs(st["maf"] - truth["stored"] / 1000.0) < 0.01,
              "%.2f MAF" % st["maf"])
        check("both numbers reach the panel",
              contains_text(f, "%d%%" % round(st["pct_avg"]))
              and contains_text(f, "%d%% OF CAPACITY" % round(st["pct_cap"])))
        check("the baseline period is named on the panel",
              contains_text(f, "VS 2011-25 AVG"))

        # The trap this file exists for: the newest slot is empty every
        # morning, and reading it rather than the newest number reports a
        # state-wide drought at breakfast.
        # The trap in full: the record really does end in a hole, and the
        # headline really is the day before it rather than None or zero.
        rec = st["rec"]
        holes = [rec["res"][c][-1] for c in rec["order"]]
        check("the record's newest slot is genuinely empty",
              all(not np.isfinite(v) for v in holes))
        check("...and the headline is the newest real day, not that hole",
              abs(st["pct_cap"] - want_cap) < 0.5 and st["maf"] > 0,
              "%.1f%%" % st["pct_cap"])

        # No normals at all: the panel keeps everything that needs no history.
        r2, f2 = frame_at(opts(cache_dir=tmp, normals=os.path.join(tmp, "x"),
                               sweep=0.0))
        check("a missing normals file costs the average and nothing else",
              r2.state["pct_avg"] is None and r2.state["pct_cap"] is not None
              and not contains_text(f2, "NO WATER DATA"),
              "%.1f%% of capacity" % r2.state["pct_cap"])

        # A dead gauge leaves both sides of the ratio rather than reading zero.
        holed = os.path.join(tmp, "holed")
        _p, htruth = synthetic(holed, drop=("SHA", "ORO"))
        r3, _f3 = frame_at(opts(cache_dir=holed, normals=norm, sweep=0.0))
        want = 100.0 * htruth["stored"] / htruth["capacity"]
        check("two dead gauges leave the ratio, they do not zero it",
              abs(r3.state["pct_cap"] - want) < 0.5,
              "%.1f%% want %.1f%%" % (r3.state["pct_cap"], want))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 5. Motion, purity and the sweep.
# --------------------------------------------------------------------------

def test_purity_and_sweep():
    print("\nthe sweep, and purity in t")
    tmp = tempfile.mkdtemp(prefix="wy-pure")
    try:
        synthetic(tmp)
        norm = synthetic_normals(os.path.join(tmp, "n.npz"))
        args = opts(cache_dir=tmp, normals=norm)

        cold = wy.build(args)(9.31, 0).copy()
        warm = wy.build(args)
        for i in range(int(9.31 * 20) + 1):
            warm(i / 20.0, i)
        hot = warm(9.31, 999).copy()
        check("render(t) cold equals render(t) reached frame by frame",
              np.array_equal(cold, hot))

        r = wy.build(args)
        check("the sweep starts on 1 October", r.step_of(0.0) == 0)
        check("...reaches the last day it has, at --sweep seconds",
              r.step_of(args.sweep) == r.state["steps"] - 1
              and r.step_of(args.sweep * 4) == r.state["steps"] - 1)
        check("...and the last step is the latest day CDEC published",
              abs(r.state["steps"] - 1
                  - round((r.state["rec"]["asof"] - r.state["rec"]["start"])
                          / 86400.0 / r.state["rec"]["year_days"] * args.width))
              <= 1)

        # Something has to move in every frame or the wall looks crashed.
        prev = None
        still = 0
        for i in range(120):
            f = r(30.0 + i / 20.0, i).copy()      # after the sweep has landed
            if prev is not None and np.array_equal(prev, f):
                still += 1
            prev = f
        check("the settled panel still moves frame to frame", still <= 2,
              "%d identical frames of 119" % still)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 6. Degraded records.
# --------------------------------------------------------------------------

def test_degraded():
    print("\nrecords that are wrong rather than merely old")
    tmp = tempfile.mkdtemp(prefix="wy-bad")
    try:
        norm = synthetic_normals(os.path.join(tmp, "n.npz"))

        old = os.path.join(tmp, "lastyear")
        synthetic(old, wy_year=ftdata._wy_water_year(time.time())[0] - 1)
        r, f = frame_at(opts(cache_dir=old, normals=norm))
        check("last water year's record is refused, not drawn",
              r.state["rec"] is None and contains_text(f, "NO WATER DATA"),
              str(r.state["problem"])[:52])
        check("...and says which year it refused",
              contains_text(f, "RECORD IS WATER YEAR"),
              str(r.state["problem"])[:52])

        stale = os.path.join(tmp, "stale")
        synthetic(stale, fetched_ago=ftdata.WY_TTL + 7200.0)
        r, f = frame_at(opts(cache_dir=stale, normals=norm))
        check("a record past its TTL still draws the year",
              r.state["rec"] is not None
              and not contains_text(f, "NO WATER DATA"))
        check("...and says STALE on the panel",
              r.state["stale"] and contains_text(f, "STALE"),
              "age %s" % ftdata.describe_age(r.state["rec"]["age"]))

        thin = os.path.join(tmp, "thin")
        synthetic(thin, days_in=1)
        r, f = frame_at(opts(cache_dir=thin, normals=norm))
        check("a record with one sample says NO WATER DATA",
              contains_text(f, "NO WATER DATA"), str(r.state["problem"])[:52])

        broken = os.path.join(tmp, "broken")
        synthetic(broken, mangle=lambda p: p.pop("res_kaf"))
        r, f = frame_at(opts(cache_dir=broken, normals=norm))
        check("a record missing its storage says so and does not raise",
              r.state["rec"] is None and contains_text(f, "NO WATER DATA"),
              str(r.state["problem"])[:52])

        empty = os.path.join(tmp, "empty")
        os.makedirs(empty)
        r, f = frame_at(opts(cache_dir=empty, normals=norm))
        check("no record at all draws the no-data card",
              r.state["rec"] is None and contains_text(f, "NO WATER DATA"))
        check("...and says how to fix it",
              contains_text(f, "FTDATA.PY"))

        # Every gauge dead is not a picture of an empty California.
        allgone = os.path.join(tmp, "allgone")
        synthetic(allgone,
                  drop=tuple(c for c, _l, _c2, _l2 in ftdata.WY_RESERVOIRS))
        r, f = frame_at(opts(cache_dir=allgone, normals=norm))
        check("every gauge dead does not print a zero per cent",
              r.state["rec"] is None or r.state["pct_cap"] is None,
              str(r.state["pct_cap"]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 7. Fresh, stale and absent, each in a process of its own.
#
# `ftdata.CACHE_DIR` is read at import time, so a test that sets FT_DATA_CACHE
# and reloads the module is testing its own import machinery. Each state gets a
# fresh interpreter, with the environment set the way the wall sets it and no
# --cache-dir to paper over it.
# --------------------------------------------------------------------------

def _one_state(state, cache_dir):
    args = opts()                      # note: no cache_dir, so CACHE_DIR wins
    r = wy.build(args)
    out = r(40.0, 800)
    card = contains_text(out, "NO WATER DATA")
    stale = contains_text(out, "STALE")
    drew = r.state["rec"] is not None
    verdict = {
        "fresh": (drew and not card and not stale, "drew the year, no flags"),
        "stale": (drew and not card and stale, "drew the year with STALE on it"),
        "absent": (not drew and card, "drew the no-data card"),
    }[state]
    print("RESULT %s %s cache=%s drew=%s card=%s stale=%s"
          % (state, "ok" if verdict[0] else "FAIL",
             os.path.basename(cache_dir), drew, card, stale))
    return 0 if verdict[0] else 1


def test_states_in_separate_processes():
    print("\nfresh, stale and absent -- one process each, FT_DATA_CACHE set")
    tmp = tempfile.mkdtemp(prefix="wy-proc")
    try:
        fresh = os.path.join(tmp, "fresh")
        synthetic(fresh, fetched_ago=600.0)
        stale = os.path.join(tmp, "stale")
        synthetic(stale, fetched_ago=ftdata.WY_TTL + 86400.0)
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
# 8. Other panel sizes, and the promise that none of this talks to anyone.
# --------------------------------------------------------------------------

def test_sizes():
    print("\nother panel sizes")
    tmp = tempfile.mkdtemp(prefix="wy-size")
    try:
        synthetic(tmp)
        norm = synthetic_normals(os.path.join(tmp, "n.npz"))
        for w, h in ((320, 64), (256, 64), (128, 64), (320, 32), (192, 96),
                     (512, 128), (64, 32), (320, 16)):
            try:
                r = wy.build(opts(cache_dir=tmp, normals=norm,
                                  width=w, height=h))
                f = None
                for i in range(0, 600, 7):
                    f = r(i / 20.0, i)
                lay = r.layout
                ok = (f.shape == (h, w, 3) and f.dtype == np.uint8
                      and f.max() > 0)
                detail = "ridge %d rows, vessels %d, axis %d" % (
                    lay.ridge_h, lay.ves_h, lay.axis_h)
            except Exception as e:                           # noqa: BLE001
                ok, detail = False, repr(e)[:70]
            check("%dx%d renders" % (w, h), ok, detail)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_no_network():
    print("\nthe network promise")
    before = set(sys.modules)
    ftdata.load("wateryear", tempfile.mkdtemp(prefix="wy-net"))
    new = set(sys.modules) - before
    bad = [m for m in new
           if m.split(".")[0] in ("urllib", "http", "socket", "ssl", "requests")]
    check("ftdata.load() imports no network module", not bad, ",".join(bad))
    src = open(os.path.join(HERE, "wateryear.py")).read()
    imported = [m for m in ("urllib", "http.client", "socket", "requests",
                            "ssl") if ("import " + m) in src]
    check("wateryear.py does not import one either", not imported,
          ",".join(imported))
    check("...and never reads [-1] off a series",
          "[-1]" not in src.split('"""')[2], "see last_finite()")


# --------------------------------------------------------------------------
# 9. Against the live cache, if there is one.
# --------------------------------------------------------------------------

def test_live(cache_dir):
    print("\nthe live cache: %s" % cache_dir)
    got = ftdata.load("wateryear", cache_dir)
    if got is None:
        print("  --   no record; run: python3 ftdata.py --once --only wateryear")
        return
    payload, age = got
    size = os.path.getsize(os.path.join(cache_dir, "wateryear.json"))
    n = sum(len([v for v in payload["res_kaf"][c]])
            for c in payload["res_order"])
    n += sum(len(payload["snow_in"][r]) for r in payload["snow_order"])
    check("the record is small", size < 64 * 1024,
          "%d bytes, %d samples, age %s" % (size, n, ftdata.describe_age(age)))
    check("it is this water year",
          payload["wy"] == ftdata._wy_water_year(time.time())[0],
          "WY%s" % payload["wy"])
    check("every reservoir has a capacity and most have a level",
          all(payload["cap_kaf"].get(c) for c in payload["res_order"])
          and sum(any(v is not None for v in payload["res_kaf"][c])
                  for c in payload["res_order"]) >= 6)
    check("snow is inches and never negative",
          all(v is None or -0.01 <= v < 200.0
              for r in payload["snow_order"] for v in payload["snow_in"][r]))

    r, f = frame_at(opts(cache_dir=cache_dir))
    st = r.state
    check("the live panel draws with real numbers on it",
          st["rec"] is not None and st["pct_cap"] is not None,
          "%.0f%% of capacity, %s of average, %.1f MAF"
          % (st["pct_cap"],
             "--" if st["pct_avg"] is None else "%.0f%%" % st["pct_avg"],
             st["maf"]))
    check("percent of capacity is a number a reservoir can have",
          0.0 < st["pct_cap"] < 130.0)
    check("percent of average is within living memory",
          st["pct_avg"] is None or 10.0 < st["pct_avg"] < 300.0)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache-dir", default=ftdata.CACHE_DIR)
    ap.add_argument("--state", default="",
                    choices=("", "fresh", "stale", "absent"),
                    help="internal: run one data state and print RESULT")
    ap.add_argument("--write-winter", default="",
                    help="write a synthetic snow-heavy record here and exit")
    a = ap.parse_args()
    if a.state:
        return _one_state(a.state, a.cache_dir)
    if a.write_winter:
        path, _truth = synthetic(a.write_winter, days_in=138, snow_peak=34.0,
                                 fracs=(0.42, 0.48, 0.44, 0.39, 0.58, 0.61,
                                        0.52, 0.35))
        print("wrote %s -- a mid-February water year, 34 inches of snow" % path)
        print("  FT_DATA_CACHE=%s python3 wateryear.py --host 127.0.0.1"
              % a.write_winter)
        return 0

    test_no_network()
    test_calendar()
    test_vessels()
    test_normal_line()
    test_snow()
    test_melt_connects()
    test_numbers()
    test_purity_and_sweep()
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
