#!/usr/bin/env python3
"""Checks for air.py that a screenshot cannot make.

This panel can draw a beautiful, confident, wrong picture in several ways and
none of them look wrong:

  1. **The murk can run the wrong way.** A bad-air day that renders *crisper*
     than a clean one is exactly as pretty as the right picture and says the
     opposite thing. So the depth planes are read back off the panel and the
     contrast between each of them and the sky is asserted to fall as PM2.5
     rises, plane by plane, in the right order.
  2. **Fog can be drawn as smoke.** This is the whole reason the humidity is
     fetched, and it is the failure that would matter: karl.py owns fog, and a
     6 ug/m3 foggy morning drawn orange is the panel claiming a fire. Two
     synthetic days with the *same* visibility and opposite causes are rendered
     and their hue is compared.
  3. **The headline can belong to another hour.** The picture sweeps through
     49 hours; a number that does not follow the cursor is worse than no
     number. The label and the value are read back off the panel at several
     sweep positions.
  4. **A record whose window has ended draws perfectly.** It parses, it has 49
     hours, it is a lovely curve, and the cursor is on the wrong hour.

Two things about how these are run, both learned the hard way in this tree.
The demo is **not a pure function of the wall clock but is a pure function of
`t`**, and that is asserted directly. And `ftdata.CACHE_DIR` binds at import,
so the three data states -- fresh, stale, absent -- are each run in a
**separate process** with FT_DATA_CACHE set, at the bottom of this file.

    $ python3 scripts/test-air.py                     # uses the live cache
    $ python3 scripts/test-air.py --cache-dir /tmp/c  # or a pointed one
    $ python3 scripts/test-air.py --shot ../screenshots/air.png
    $ python3 scripts/test-air.py --shot-clean /tmp/clean.png \\
                                  --shot-smoke /tmp/smoke.png \\
                                  --shot-fog   /tmp/fog.png

The live cache is only needed for the checks against real data; everything
else builds its own cache directory and needs nothing. Populate it with
`python3 ftdata.py --once --only air`.
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

import air                                                    # noqa: E402
import demoscene as ds                                        # noqa: E402
import ftdata                                                 # noqa: E402

FAILED = []
PASSED = [0]

N_HOURS = 49
NOW_I = 24


def check(name, ok, detail=""):
    PASSED[0] += 1
    if ok:
        print("  ok   %-58s %s" % (name, detail))
    else:
        print("  FAIL %-58s %s" % (name, detail))
        FAILED.append(name)


def opts(**kw):
    return ds.options(air, **kw)


def frames(args, n=8):
    """Render `n` frames in order from a fresh build."""
    r = air.build(args)
    out = None
    for i in range(n):
        out = r(i / 20.0, i)
    return r, out.copy()


def contains_text(frame, s, thresh=90, scales=(1, 2), bg_max=0.35):
    """Is this string drawn anywhere on the frame, at any position or size?

    Reading the words back off the panel is the only way to be sure the honest
    message reached it rather than merely being computed. The background
    tolerance is looser than caiso.py's because every glyph here is drawn with
    a one-pixel dark outline over a lit sky, so the counters are guaranteed
    dark but the ring around them is not part of the mask.
    """
    lit = frame.max(axis=2) >= thresh
    h, w = lit.shape
    for scale in scales:
        m = air.text_mask(s, scale)
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
# Days we invented, so that every answer is known before it is drawn.
#
# The three that matter are a clean day, a smoke day and a fog morning, and the
# last two are deliberately built to have *similar visibility and opposite
# causes* -- which is the one comparison this panel exists to get right.
# --------------------------------------------------------------------------

def us_aqi(pm):
    """The published PM2.5 breakpoints. Written out so the test does not
    borrow the demo's arithmetic to check the demo's arithmetic."""
    table = ((0.0, 12.0, 0, 50), (12.0, 35.4, 51, 100), (35.4, 55.4, 101, 150),
             (55.4, 150.4, 151, 200), (150.4, 250.4, 201, 300),
             (250.4, 500.4, 301, 500))
    for lo, hi, ilo, ihi in table:
        if pm <= hi:
            return int(round(ilo + (ihi - ilo) * (pm - lo) / (hi - lo)))
    return 500


def synthetic(cache_dir, pm=None, rh=None, vis=None, n=N_HOURS,
              fetched_ago=120.0, t0_offset=0.0, mangle=None, drop=()):
    """Write an `air` record by hand. Returns (path, truth dict)."""
    now = time.time()
    t0 = (now // 3600.0) * 3600.0 - NOW_I * 3600.0 + t0_offset
    pm = [8.0] * n if pm is None else [float(pm(i)) for i in range(n)]
    rh = [60] * n if rh is None else [rh(i) for i in range(n)]
    vis = [24.0] * n if vis is None else [vis(i) for i in range(n)]

    payload = {
        "site": [37.76, -122.40], "name": "test",
        "grid": [37.80, -122.40], "wx_grid": [37.76, -122.41], "wx_error": "",
        "t0": t0, "step": 3600.0, "n": n, "now": now,
        "past_h": NOW_I, "ahead_h": n - 1 - NOW_I,
        "pm2_5": [round(v, 1) for v in pm],
        "pm10": [round(v * 1.6, 1) for v in pm],
        "us_aqi": [us_aqi(v) for v in pm],
        "aod": [round(0.05 + v / 400.0, 2) for v in pm],
        "rh": list(rh), "vis_km": list(vis),
        "units": {"pm2_5": "ug/m3"}, "model": "synthetic",
        "label": "SYNTHETIC",
    }
    for k in drop:
        payload[k] = None
    if mangle:
        mangle(payload)

    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, "air.json")
    with open(path, "w") as fh:
        json.dump({"name": "air", "source": "synthetic", "ttl": ftdata.AIR_TTL,
                   "fetched_at": now - fetched_ago, "payload": payload}, fh)
    return path, {"t0": t0, "pm": pm, "rh": rh, "vis": vis, "n": n}


def flat(v):
    return lambda i: v


def CLEAN(cache_dir, **kw):
    return synthetic(cache_dir, pm=flat(3.5), rh=flat(58), vis=flat(30.0), **kw)


def MODERATE(cache_dir, **kw):
    return synthetic(cache_dir, pm=flat(16.0), rh=flat(70), vis=flat(18.0),
                     **kw)


def SMOKE(cache_dir, **kw):
    # A plume arriving: quiet yesterday, 170 ug/m3 now, easing tomorrow. The
    # visibility the model would report at that loading, so the fog term is
    # zero by construction and the murk is all particles.
    def pm(i):
        return 12.0 + 160.0 * math.exp(-((i - NOW_I) / 10.0) ** 2)

    def vis(i):
        return round(3912.0 / (3.0 * pm(i) + 10.0), 1)
    return synthetic(cache_dir, pm=pm, rh=flat(48), vis=vis, **kw)


def FOG(cache_dir, **kw):
    # The other way to lose the city: six micrograms of particles and the
    # marine layer in. Same visual range as the smoke day, opposite cause.
    return synthetic(cache_dir, pm=flat(6.0), rh=flat(97), vis=flat(0.5), **kw)


# --------------------------------------------------------------------------
# Reading the picture back.
# --------------------------------------------------------------------------

def edge_contrast(r, frame, body, gap=2):
    """How visible one depth plane's own silhouette is, in raw levels.

    Comparing a patch of sky with a patch of ridge would also be measuring the
    sky's vertical gradient, which on a smoke day is steep -- an early version
    of this test "proved" the ridge got *more* visible in smoke. So the
    measurement is local: every pixel just inside the plane's top edge against
    the pixel a couple of rows above it, which is whatever is behind. Beer's
    law says that difference is |body - behind| * T, so it falls to zero as the
    extinction rises, and it falls fastest for the furthest plane. That is
    exactly the property the panel is built on.
    """
    geo = r.geometry
    front, cov, Hs = geo["front"], geo["cov"], geo["scene_h"]
    ys, xs = np.nonzero((front == body) & (cov >= 0.999))
    keep = ys >= gap
    ys, xs = ys[keep], xs[keep]
    if not len(ys):
        return 0.0
    above = front[ys - gap, xs] != body
    ys, xs = ys[above], xs[above]
    if not len(ys):
        return 0.0
    a = frame[:Hs][ys, xs].astype(float)
    b = frame[:Hs][ys - gap, xs].astype(float)
    return float(np.abs(a - b).mean())


def warmth(frame, y0, y1):
    """Mean red-minus-blue over a band. Positive is warm, negative is cool."""
    band = frame[y0:y1].astype(float)
    return float(band[:, :, 0].mean() - band[:, :, 2].mean())


def at_now(cache_dir, **kw):
    """A settled frame with the sweep parked on the present moment."""
    args = opts(cache_dir=cache_dir, sweep=0.0, haze=0.0, **kw)
    return frames(args, 6)


# --------------------------------------------------------------------------
# 1. The physics, which is the whole panel.
# --------------------------------------------------------------------------

def test_extinction_arithmetic():
    print("\nthe extinction model, against the textbook")
    # Clean air: Rayleigh alone is 10 Mm^-1, a visual range near 400 km.
    check("clean air is Rayleigh-limited, a few hundred km of visual range",
          380.0 < air.visual_range_km(air.b_pm(0.0)) < 400.0,
          "%.0f km" % air.visual_range_km(air.b_pm(0.0)))
    # 35 ug/m3 is the top of the 24-hour standard; 12 is the annual one.
    v12 = air.visual_range_km(air.b_pm(12.0))
    v150 = air.visual_range_km(air.b_pm(150.0))
    check("12 ug/m3 still leaves the far ridge in sight",
          70.0 < v12 < 100.0, "%.0f km, ridge at 28 km" % v12)
    check("150 ug/m3 puts the visual range inside the city",
          6.0 < v150 < 12.0, "%.0f km, towers at 5.5 km" % v150)
    check("the model is monotone in PM2.5",
          all(air.b_pm(a) < air.b_pm(b)
              for a, b in zip(range(0, 300, 10), range(10, 310, 10))))

    # Beer's law through the four plane distances, which is what the table
    # does per frame. Asserted as the ordering that makes the panel legible:
    # each plane must drop out at a different concentration.
    def gone_at(km, thresh=0.10):
        for pm in range(0, 500):
            if math.exp(-air.b_pm(pm) * 1e-3 * km) < thresh:
                return pm
        return None
    order = [(name, gone_at(km)) for name, km, _rgb in air.PLANES]
    far = [v for _n, v in order[:-1]]
    check("the three far planes vanish in order, at separated concentrations",
          all(v is not None for v in far) and far == sorted(far)
          and far[1] - far[0] > 40 and far[2] - far[1] > 100,
          " ".join("%s@%s" % (n, v) for n, v in order))
    check("...and the near rooftop never vanishes at all",
          order[-1][1] is None, "the panel is never an empty rectangle")


def test_murk_runs_the_right_way():
    print("\nbad air draws murkier, plane by plane")
    tmp = tempfile.mkdtemp(prefix="air-murk")
    try:
        cl, sm = os.path.join(tmp, "cl"), os.path.join(tmp, "sm")
        CLEAN(cl)
        SMOKE(sm)
        rc, fc = at_now(cl)
        rs, fs = at_now(sm)

        # Every plane must lose its silhouette. The near rooftop is allowed to
        # keep most of its own, because it is 250 m away and that is the point
        # of having it in the picture at all.
        got = {}
        for name, body in (("ridge", air.B_RIDGE), ("city", air.B_CITY),
                           ("mid", air.B_MID), ("near", air.B_NEAR)):
            got[name] = (edge_contrast(rc, fc, body),
                         edge_contrast(rs, fs, body))
        for name in ("ridge", "city"):
            a, b = got[name]
            check("the %s loses its silhouette on a smoke day" % name,
                  b < a * 0.3, "%.1f levels clean -> %.1f smoke" % (a, b))
        a, b = got["near"]
        check("...but the near rooftop is still a silhouette",
              b > 0.45 * a and b > 8.0,
              "%.1f levels clean -> %.1f smoke" % (a, b))

        # Ordered by distance, which is the property the whole picture rests
        # on. Note it is NOT "everything gets fainter": the mid plane's
        # *absolute* contrast goes up in smoke, because a dark building 1.6 km
        # away against a bright orange murk is a stronger edge than the same
        # building against the grey towers behind it on a clear day. That is
        # what a silhouette in smoke actually looks like. What must hold is
        # the ordering, and it is the ordering that makes "how much of the
        # city is missing" readable across the room.
        smoke_order = [got[n][1] for n in ("ridge", "city", "mid", "near")]
        check("in smoke the planes are ordered ridge < city < mid < near",
              smoke_order == sorted(smoke_order),
              " ".join("%.1f" % v for v in smoke_order))
        check("the far ridge is all but gone while the rooftop is not",
              got["ridge"][1] < 3.0 and got["near"][1] > 20.0,
              "ridge %.1f vs near %.1f" % (got["ridge"][1], got["near"][1]))

        # The tower lights are drawn at the towers' distance, so they must be
        # swallowed with them rather than shining through the smoke. Measured
        # against the wall they are set into, not against absolute brightness:
        # on a smoke day the whole panel is bright.
        def light_pop(r, f):
            return edge_contrast(r, f, air.B_LIGHTS, gap=1)
        pc, ps = light_pop(rc, fc), light_pop(rs, fs)
        check("the tower lights are swallowed too", ps < pc * 0.5,
              "%.1f levels clean -> %.1f smoke" % (pc, ps))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_fog_is_not_smoke():
    print("\nfog and smoke, which is the distinction this panel is for")
    tmp = tempfile.mkdtemp(prefix="air-fog")
    try:
        fg, sm, cl = (os.path.join(tmp, x) for x in ("fg", "sm", "cl"))
        FOG(fg)
        SMOKE(sm)
        CLEAN(cl)
        rf, ff = at_now(fg)
        rs, fs = at_now(sm)
        rc, fc = at_now(cl)
        Hs = rf.layout.scene_h

        check("a foggy clean morning is called FOG",
              rf.state["word"] == "FOG",
              "%s, pm %.1f, b_fog %.0f"
              % (rf.state["word"], rf.state["pm"], rf.state["bfog"]))
        check("a smoke day is called SMOKE",
              rs.state["word"] == "SMOKE",
              "%s, pm %.1f, b_fog %.0f"
              % (rs.state["word"], rs.state["pm"], rs.state["bfog"]))
        check("a clean dry day is called CLEAR", rc.state["word"] == "CLEAR",
              rc.state["word"])

        # Both hide the city. That is the premise of the comparison: if they
        # did not, the colour test below would be proving nothing.
        cf = edge_contrast(rf, ff, air.B_CITY)
        cs = edge_contrast(rs, fs, air.B_CITY)
        cc = edge_contrast(rc, fc, air.B_CITY)
        check("both the fog and the smoke hide the downtown towers",
              cf < 0.35 * cc and cs < 0.45 * cc,
              "clean %.1f, fog %.1f, smoke %.1f levels" % (cc, cf, cs))

        # ...and the sky says which. Warm is smoke; near-neutral is fog.
        wf, ws, wc = (warmth(f, 0, Hs // 3) for f in (ff, fs, fc))
        check("the smoke sky is strongly warm", ws > 60.0, "R-B %+.0f" % ws)
        check("the fog sky is not", abs(wf) < 25.0, "R-B %+.0f" % wf)
        check("the clean sky is cool", wc < -30.0, "R-B %+.0f" % wc)
        check("fog and smoke are unmistakable from colour alone",
              ws - wf > 60.0, "%.0f apart" % (ws - wf))

        # The health number must not follow the visibility. This is the trap:
        # a panel that drew fog as bad air would also have to call it bad air.
        check("the fog morning still reads GOOD, not UNHEALTHY",
              rf.state["band"] == "GOOD" and rf.state["aqi"] <= 50,
              "AQI %s %s" % (rf.state["aqi"], rf.state["band"]))
        check("...and the panel says so in words",
              contains_text(ff, "FOG") and contains_text(ff, "GOOD"))
        check("the smoke day says UNHEALTHY on the panel",
              contains_text(fs, "SMOKE")
              and rs.state["band"] in ("UNHEALTHY", "VERY BAD", "HAZARDOUS"),
              rs.state["band"])

        # A dry afternoon with a silly visibility diagnostic must not become
        # fog: that is what the humidity is a second opinion for.
        dry = os.path.join(tmp, "dry")
        synthetic(dry, pm=flat(7.0), rh=flat(52), vis=flat(0.2))
        rd, _fd = at_now(dry)
        check("a 200 m visibility at 52% humidity is not called fog",
              rd.state["word"] != "FOG" and rd.state["bfog"] < 1.0,
              "%s, b_fog %.1f" % (rd.state["word"], rd.state["bfog"]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 2. The number, and whether it belongs to the hour under the cursor.
# --------------------------------------------------------------------------

def test_headline_follows_the_sweep():
    print("\nthe headline belongs to the hour the picture is standing in")
    tmp = tempfile.mkdtemp(prefix="air-head")
    try:
        SMOKE(tmp)
        r, f = at_now(tmp)
        aqi = r.state["aqi"]
        check("the AQI reaches the panel as a number",
              contains_text(f, "%d" % aqi), "AQI %d" % aqi)
        check("...labelled AQI, so it is not read as a temperature",
              contains_text(f, "AQI"))
        check("...and PM2.5 is printed too, in ug/m3",
              contains_text(f, "PM2.5"), "%.1f" % r.state["pm"])
        check("the present moment is labelled NOW", contains_text(f, "NOW"))

        # Now sweep. At several points in the cycle the label and the value
        # must agree with the record at that hour.
        args = opts(cache_dir=tmp, haze=0.0)
        rr = air.build(args)
        rec = rr.state["rec"]
        seen = set()
        bad = []
        for i in range(int(args.sweep * 20) + 4):
            t = i / 20.0
            out = rr(t, i)
            u = air.sweep_position(t, args.sweep, rr.state["now_u"],
                                   rr.state["last_u"])
            k = int(round(u))
            seen.add(k)
            if k in (0, rec["n"] - 1, 10, 34) and k not in ():
                want = int(round(float(rec["aqi"][k])))
                if rr.state["aqi"] != want:
                    bad.append((k, rr.state["aqi"], want))
                lab = air.hour_label(float(k), rr.state["now_u"])
                if not contains_text(out, lab):
                    bad.append((k, lab, "label missing"))
        check("the number under the cursor is that hour's number", not bad,
              str(bad[:3]))
        check("the sweep visits both ends of the window",
              0 in seen and (rec["n"] - 1) in seen,
              "%d of %d hours visited" % (len(seen), rec["n"]))
        check("...and dwells on the present moment",
              sum(1 for i in range(int(args.sweep * 20))
                  if int(round(air.sweep_position(i / 20.0, args.sweep,
                                                  rr.state["now_u"],
                                                  rr.state["last_u"])))
                  == int(round(rr.state["now_u"]))) > 20,
              "frames parked on now")

        # The hour offsets have to be signed and right, or the label is worse
        # than useless.
        check("hour labels are signed offsets from now",
              air.hour_label(24.0, 24.0) == "NOW"
              and air.hour_label(16.0, 24.0) == "-8H"
              and air.hour_label(37.0, 24.0) == "+13H",
              air.hour_label(37.0, 24.0))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_strip():
    print("\nthe 48-hour strip along the bottom")
    tmp = tempfile.mkdtemp(prefix="air-strip")
    try:
        SMOKE(tmp)
        r, f = at_now(tmp)
        lay = r.layout
        check("the strip exists at 320x64", lay.strip_h >= 6,
              "%d rows" % lay.strip_h)
        band = f[lay.strip_y:]

        # The plume peaks at NOW, so the tallest bars must be in the middle.
        lit = (band.max(axis=2) > 24).sum(axis=0)
        peak = int(np.argmax(lit))
        want = int(round(r.state["now_u"] / (r.state["rec"]["n"] - 1.0)
                         * (lay.w - 1)))
        check("the tallest bars are where the plume is", abs(peak - want) < 40,
              "peak column %d, now column %d" % (peak, want))

        # The forecast half is dimmer than the measured half at the same
        # concentration, which is how somebody knows which is which.
        rec = r.state["rec"]
        pairs = []
        for d in (4, 6, 8):
            ca = int(round((r.state["now_u"] - d) / (rec["n"] - 1.0)
                           * (lay.w - 1)))
            cb = int(round((r.state["now_u"] + d) / (rec["n"] - 1.0)
                           * (lay.w - 1)))
            pairs.append((float(band[:, ca].max()), float(band[:, cb].max())))
        check("the forecast half is drawn dimmer than the measured half",
              all(a > b for a, b in pairs), str([(int(a), int(b))
                                                 for a, b in pairs]))

        # The present moment is marked, or the strip is 48 anonymous hours.
        # Rendered with the sweep running and stepped away from now, because
        # with the sweep parked the cursor sits exactly on the now line and
        # covers it -- which is correct on the panel and useless as a test.
        r2 = air.build(opts(cache_dir=tmp, haze=0.0))
        away = None
        for i in range(int(r2.state["rec"] and 200)):
            away = r2(i / 20.0, i)
            if abs(air.sweep_position(i / 20.0, opts().sweep,
                                      r2.state["now_u"],
                                      r2.state["last_u"])
                   - r2.state["now_u"]) > 4.0:
                break
        col = away[lay.strip_y:][:, want]
        check("the present moment is marked on the strip",
              int((col > 190).all(axis=1).sum()) >= 3,
              "%d bright rows in column %d" %
              (int((col > 190).all(axis=1).sum()), want))
        check("...and the strip is labelled",
              contains_text(f, "48H PM2.5"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 3. Purity and motion.
# --------------------------------------------------------------------------

def test_purity():
    print("\nrender() is a pure function of t")
    tmp = tempfile.mkdtemp(prefix="air-pure")
    try:
        SMOKE(tmp)
        # reload=0, because re-reading the cache on a timer is the one piece
        # of wall clock inside render(). --at with --rate 0 freezes the other
        # one: `now` is read once in build() to place the cursor on the present
        # hour, and two builds a fifth of a second apart would otherwise place
        # it a hair differently and fail this for the wrong reason.
        frozen = dict(cache_dir=tmp, reload=0.0, at="%.3f" % time.time(),
                      rate=0.0)
        args = opts(**frozen)
        warm = air.build(args)
        for i in range(137):
            warm(i / 20.0, i)
        driven = warm(137 / 20.0, 137).copy()

        cold = air.build(opts(**frozen))
        fresh = cold(137 / 20.0, 137).copy()
        check("a cold render(t) equals the same t reached frame by frame",
              np.array_equal(driven, fresh),
              "%d pixels differ" % int((driven != fresh).any(axis=2).sum()))

        # And again at a t in the middle of the reversal, where the easing is
        # steepest and an accumulated state would show first.
        t2 = args.sweep * 0.86
        a = air.build(opts(**frozen))
        for i in range(int(t2 * 20)):
            a(i / 20.0, i)
        va = a(t2, int(t2 * 20)).copy()
        b = air.build(opts(**frozen))
        vb = b(t2, int(t2 * 20)).copy()
        check("...and again inside the return sweep", np.array_equal(va, vb),
              "%d pixels differ" % int((va != vb).any(axis=2).sum()))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_motion():
    print("\nit does not sit there")
    tmp = tempfile.mkdtemp(prefix="air-mot")
    try:
        CLEAN(tmp)          # the hardest case: nothing in the air to move
        args = opts(cache_dir=tmp)
        r = air.build(args)
        prev = None
        diffs = []
        for i in range(int(args.sweep * 20) + 20):
            f = r(i / 20.0, i)
            if prev is not None:
                diffs.append(int((f != prev).any(axis=2).sum()))
            prev = f.copy()
        run = best = 0
        for d in diffs:
            run = run + 1 if d == 0 else 0
            best = max(best, run)
        check("the panel never holds the same frame for a tenth of a second",
              best <= 1, "longest identical run %d frames of %d"
              % (best, len(diffs)))
        check("the sweep moves a substantial part of the panel",
              max(diffs) > 400, "biggest change %d pixels" % max(diffs))

        # The murk must actually drift on a bad day, which is the other half
        # of the motion budget.
        sm = os.path.join(tmp, "sm")
        SMOKE(sm)
        rs = air.build(opts(cache_dir=sm, sweep=0.0))
        d2 = []
        prev = None
        for i in range(40):
            f = rs(i / 20.0, i)
            if prev is not None:
                d2.append(int((f != prev).any(axis=2).sum()))
            prev = f.copy()
        check("the murk drifts even with the sweep parked",
              min(d2) > 100, "smallest frame-to-frame change %d px" % min(d2))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 4. Degraded records.
# --------------------------------------------------------------------------

def test_degraded():
    print("\nmissing, ended, corrupt and half-there records")
    tmp = tempfile.mkdtemp(prefix="air-bad")
    try:
        empty = os.path.join(tmp, "empty")
        os.makedirs(empty)
        r, f = frames(opts(cache_dir=empty), 8)
        check("no cache at all says NO AIR DATA", contains_text(f, "NO AIR DATA"))
        check("...and names the command that fixes it",
              contains_text(f, "FTDATA.PY"))
        check("...and draws no skyline", r.state["rec"] is None)

        bad = os.path.join(tmp, "corrupt")
        os.makedirs(bad)
        with open(os.path.join(bad, "air.json"), "w") as fh:
            fh.write('{"payload": {"pm2_5": ')
        _, f = frames(opts(cache_dir=bad), 8)
        check("a half-written file says NO AIR DATA",
              contains_text(f, "NO AIR DATA"))

        wrong = os.path.join(tmp, "wrongshape")
        os.makedirs(wrong)
        with open(os.path.join(wrong, "air.json"), "w") as fh:
            json.dump({"name": "air", "fetched_at": time.time(),
                       "payload": {"hello": "world"}}, fh)
        _, f = frames(opts(cache_dir=wrong), 8)
        check("a payload from some other product says NO AIR DATA",
              contains_text(f, "NO AIR DATA"))

        # The dangerous one. A complete, well formed record of a window that
        # ended yesterday would draw a perfect panel about the wrong day.
        old = os.path.join(tmp, "ended")
        SMOKE(old, t0_offset=-72 * 3600.0, fetched_ago=72 * 3600.0)
        r, f = frames(opts(cache_dir=old), 8)
        check("a record whose window has ended is refused, not drawn",
              r.state["rec"] is None and contains_text(f, "NO AIR DATA"),
              str(r.state["problem"])[:52])
        check("...and says so", contains_text(f, "WINDOW ENDED"),
              str(r.state["problem"])[:52])

        # Four hours old, past the three-hour TTL. The curve it holds is still
        # very nearly the curve, so it draws -- loudly.
        stale = os.path.join(tmp, "stale")
        MODERATE(stale, fetched_ago=4 * 3600.0)
        r, f = frames(opts(cache_dir=stale), 8)
        check("a four-hour-old record still draws",
              r.state["rec"] is not None
              and not contains_text(f, "NO AIR DATA"))
        check("...and says STALE on the panel",
              contains_text(f, "STALE") and r.state["stale"],
              "age %s" % ftdata.describe_age(r.state["rec"]["age"]))

        # Humidity is an enrichment. Losing it must cost the fog distinction
        # and nothing else.
        nofog = os.path.join(tmp, "nofog")
        FOG(nofog, drop=("rh", "vis_km"))
        r, f = frames(opts(cache_dir=nofog, sweep=0.0, haze=0.0), 8)
        check("no humidity or visibility still draws the particulates",
              r.state["rec"] is not None and r.state["bfog"] == 0.0,
              "%s, pm %.1f" % (r.state["word"], r.state["pm"]))
        check("...and does not invent fog it cannot see",
              r.state["word"] != "FOG", r.state["word"])

        # Holes in the middle of the series.
        holed = os.path.join(tmp, "holed")

        def punch(payload):
            for i in (5, 6, 7, 30):
                payload["pm2_5"][i] = None
                payload["us_aqi"][i] = None
        SMOKE(holed, mangle=punch)
        r, f = frames(opts(cache_dir=holed, sweep=0.0, haze=0.0), 8)
        check("a hole in the series is interpolated, not treated as clean",
              r.state["rec"] is not None
              and np.isfinite(r.state["rec"]["pm"]).all()
              and float(r.state["rec"]["pm"][6]) > 10.0,
              "pm[6] = %.1f" % float(r.state["rec"]["pm"][6]))

        # A record with two hours cannot be a 48-hour strip.
        thin = os.path.join(tmp, "thin")
        synthetic(thin, n=2)
        r, f = frames(opts(cache_dir=thin), 8)
        check("a two-hour record says NO AIR DATA",
              contains_text(f, "NO AIR DATA"), str(r.state["problem"])[:52])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 5. Fresh, stale and absent, each in a process of its own.
# --------------------------------------------------------------------------

def _one_state(state, cache_dir):
    args = opts()                       # note: no cache_dir, so CACHE_DIR wins
    r = air.build(args)
    out = None
    for i in range(8):
        out = r(i / 20.0, i)
    card = contains_text(out, "NO AIR DATA")
    stale = contains_text(out, "STALE")
    drew = r.state["rec"] is not None
    verdict = {
        "fresh": (drew and not card and not stale, "drew the view, no flags"),
        "stale": (drew and not card and stale, "drew the view with STALE on it"),
        "absent": (not drew and card, "drew the no-data card"),
    }[state]
    print("RESULT %s %s cache=%s drew=%s card=%s stale=%s"
          % (state, "ok" if verdict[0] else "FAIL",
             os.path.basename(cache_dir), drew, card, stale))
    return 0 if verdict[0] else 1


def test_states_in_separate_processes():
    print("\nfresh, stale and absent -- one process each, FT_DATA_CACHE set")
    tmp = tempfile.mkdtemp(prefix="air-proc")
    try:
        fresh = os.path.join(tmp, "fresh")
        MODERATE(fresh, fetched_ago=300.0)
        stale = os.path.join(tmp, "stale")
        MODERATE(stale, fetched_ago=5 * 3600.0)
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
                  (line[0][7:] if line else
                   (proc.stderr.strip().splitlines() or ["no output"])[-1]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 6. Cost, sizes, the network promise, and the live cache.
# --------------------------------------------------------------------------

def test_cost():
    print("\nwhat a frame costs")
    tmp = tempfile.mkdtemp(prefix="air-cost")
    try:
        SMOKE(tmp)
        args = opts(cache_dir=tmp)
        t0 = time.perf_counter()
        r = air.build(args)
        build_ms = (time.perf_counter() - t0) * 1e3
        r(0.0, 0)
        ts = []
        for i in range(int(args.sweep * 20) + 40):
            a = time.perf_counter()
            r(i / 20.0, i)
            ts.append((time.perf_counter() - a) * 1e3)
        ts = np.array(ts)
        check("build() is under 50 ms here", build_ms < 50.0,
              "%.1f ms" % build_ms)
        check("mean frame is under 1 ms here", float(ts.mean()) < 1.0,
              "mean %.3f  p95 %.3f  max %.3f ms"
              % (ts.mean(), np.percentile(ts, 95), ts.max()))
        check("p95 is close to the mean, so there is no periodic spike",
              float(np.percentile(ts, 95)) < 4.0 * float(ts.mean()) + 0.2,
              "%.3f vs %.3f" % (np.percentile(ts, 95), ts.mean()))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_sizes():
    print("\nother panel sizes")
    tmp = tempfile.mkdtemp(prefix="air-size")
    try:
        SMOKE(tmp)
        for w, h in ((320, 64), (256, 64), (128, 64), (320, 32), (192, 96),
                     (512, 128), (64, 32), (320, 16)):
            try:
                r, f = frames(opts(cache_dir=tmp, width=w, height=h), 40)
                ok = (f.shape == (h, w, 3) and f.dtype == np.uint8
                      and f.max() > 0)
                detail = "scene %d rows, strip %d" % (r.layout.scene_h,
                                                      r.layout.strip_h)
            except Exception as e:                           # noqa: BLE001
                ok, detail = False, repr(e)[:70]
            check("%dx%d renders" % (w, h), ok, detail)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_no_network():
    print("\nthe network promise")
    before = set(sys.modules)
    ftdata.load("air", tempfile.mkdtemp(prefix="air-net"))
    new = set(sys.modules) - before
    bad = [m for m in new
           if m.split(".")[0] in ("urllib", "http", "socket", "ssl", "requests")]
    check("ftdata.load() imports no network module", not bad, ",".join(bad))
    src = open(os.path.join(HERE, "air.py")).read()
    imported = [m for m in ("urllib", "http.client", "socket", "requests",
                            "ssl") if ("import " + m) in src]
    check("air.py does not import one either", not imported,
          ",".join(imported))


def test_fetcher_shape():
    print("\nthe fetcher's own shape, without fetching")
    url = ftdata._air_url(ftdata.OPENMETEO_AQ_URL, "pm2_5,us_aqi")
    check("the request carries an explicit timezone, not the default",
          "timezone=UTC" in url, url.split("?")[1][:90])
    check("...and the site's coordinate, from ftsite",
          ("%.4f" % ftdata.ftsite.LAT) in url
          and ("%.4f" % ftdata.ftsite.LON) in url)
    check("the product's TTL is hours, not minutes",
          3600 <= ftdata.ttl_for("air") <= 6 * 3600,
          "%d s" % ftdata.ttl_for("air"))
    check("...and it is not fetched more often than it changes",
          ftdata.interval_for("air") >= 1800,
          "%d s" % ftdata.interval_for("air"))
    check("the window is symmetric about the present",
          ftdata.AIR_PAST_H == ftdata.AIR_AHEAD_H,
          "-%dh .. +%dh" % (ftdata.AIR_PAST_H, ftdata.AIR_AHEAD_H))


def test_live(cache_dir):
    print("\nagainst the live cache")
    got = ftdata.load("air", cache_dir)
    if got is None:
        check("live record present", False,
              "run: python3 ftdata.py --once --only air")
        return
    payload, age = got
    rec, _, err = air.read_air(cache_dir)
    if rec is None:
        check("live record parses into something drawable", False, err)
        return
    check("live record parses into something drawable", True,
          "%d hours, %s old" % (rec["n"], ftdata.describe_age(age)))
    check("the window straddles the present moment",
          rec["t0"] < time.time() < rec["t0"] + rec["step"] * (rec["n"] - 1),
          "%d h back, %d h ahead"
          % ((time.time() - rec["t0"]) / 3600.0,
             (rec["t0"] + rec["step"] * (rec["n"] - 1) - time.time()) / 3600.0))
    check("PM2.5 is a plausible surface concentration",
          0.0 <= float(np.nanmin(rec["pm"])) and
          float(np.nanmax(rec["pm"])) < 900.0,
          "%.1f .. %.1f ug/m3" % (np.nanmin(rec["pm"]), np.nanmax(rec["pm"])))
    aqi = rec["aqi"]
    if np.isfinite(aqi).any() and float(np.nanstd(aqi)) > 0.5:
        # The AQI has to agree with the PM2.5 about which way is bad, or one
        # of the two columns has been read out of the wrong key. It is *not*
        # asserted against the hourly figure: the US index is defined on a
        # 24-hour average and the service's hourly column is a running
        # quantity, so on a real day here it correlates 0.15 with the hourly
        # PM2.5 and 0.90 with a 24-hour trailing mean of it. Getting that
        # backwards is how somebody would "fix" the panel into being wrong.
        ok = np.isfinite(aqi)
        pm = rec["pm"]
        trail = np.array([pm[max(0, i - 23):i + 1].mean()
                          for i in range(len(pm))])
        corr = float(np.corrcoef(trail[ok], aqi[ok])[0, 1])
        check("AQI tracks a 24-hour trailing mean of PM2.5, as it is defined",
              corr > 0.7, "r = %.2f (against the hourly figure, r = %.2f)"
              % (corr, float(np.corrcoef(pm[ok], aqi[ok])[0, 1])))
    check("the fetcher stored the grid cell it was actually answered for",
          isinstance(payload.get("grid"), list),
          "site %s -> cell %s" % (payload.get("site"), payload.get("grid")))
    if payload.get("vis_km"):
        vis = [v for v in payload["vis_km"] if v is not None]
        check("visibility came back too, in kilometres",
              vis and max(vis) < 200.0, "%.1f .. %.1f km" % (min(vis), max(vis)))

    r, f = frames(opts(cache_dir=cache_dir, sweep=0.0), 6)
    check("the live record renders the view and not a card",
          not contains_text(f, "NO AIR DATA") and f.max() > 0,
          "AQI %s, %s, %s, %.0f km visual range"
          % (r.state["aqi"], r.state["band"], r.state["word"],
             r.state["vis_km"]))


# --------------------------------------------------------------------------
# Screenshots, including the two nobody can wait for.
# --------------------------------------------------------------------------

def write_shot(path, cache_dir, at_t=3.0, **kw):
    """A 3x screenshot, 960x192 from the 320x64 panel."""
    from PIL import Image
    r = air.build(opts(cache_dir=cache_dir, **kw))
    out = None
    for i in range(int(at_t * 20) + 1):
        out = r(i / 20.0, i)
    im = Image.fromarray(np.asarray(out, np.uint8).copy(), "RGB")
    im = im.resize((im.width * 3, im.height * 3), Image.NEAREST)
    im.save(path)
    print("wrote %s (%dx%d)  AQI %s %s %s"
          % (path, im.width, im.height, r.state["aqi"], r.state["band"],
             r.state["word"]))


def write_synthetic_shot(path, kind):
    """A screenshot of a day that is not happening, so a reviewer can see it.

    A smoke day cannot be waited for and should not be, and a panel whose
    entire point is what it looks like when the air is bad has to be reviewable
    on a clear afternoon. So the record is fabricated in a scratch cache the
    same way the tests do it -- the demo is not told, and reads the cache it
    always reads.
    """
    tmp = tempfile.mkdtemp(prefix="air-shot")
    try:
        {"clean": CLEAN, "moderate": MODERATE,
         "smoke": SMOKE, "fog": FOG}[kind](tmp)
        write_shot(path, tmp, at_t=3.0, sweep=0.0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache-dir", default=ftdata.CACHE_DIR)
    ap.add_argument("--shot", default="", help="write a 3x screenshot")
    ap.add_argument("--shot-clean", default="")
    ap.add_argument("--shot-smoke", default="")
    ap.add_argument("--shot-fog", default="")
    ap.add_argument("--state", default="",
                    choices=("", "fresh", "stale", "absent"),
                    help="internal: run one data state and print RESULT")
    a = ap.parse_args()
    if a.state:
        return _one_state(a.state, a.cache_dir)

    print("cache: %s" % a.cache_dir)
    test_no_network()
    test_fetcher_shape()
    test_extinction_arithmetic()
    test_murk_runs_the_right_way()
    test_fog_is_not_smoke()
    test_headline_follows_the_sweep()
    test_strip()
    test_purity()
    test_motion()
    test_degraded()
    test_states_in_separate_processes()
    test_cost()
    test_sizes()
    test_live(a.cache_dir)

    for path, kind in ((a.shot_clean, "clean"), (a.shot_smoke, "smoke"),
                       (a.shot_fog, "fog")):
        if path:
            write_synthetic_shot(path, kind)
    if a.shot:
        write_shot(a.shot, a.cache_dir)

    print("\n%d checks, %d failed" % (PASSED[0], len(FAILED)))
    for name in FAILED:
        print("  - %s" % name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
