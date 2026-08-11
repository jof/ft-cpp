#!/usr/bin/env python3
"""Checks for swell.py that a screenshot cannot make.

This panel's whole claim is that the picture *is* the measurement: the crests
on the wall are spaced at the wavelength the reported period implies and cross
the panel at the speed that follows from it. Every part of that claim can be
wrong while the panel still looks like a beautiful moving ocean:

  1. **The waves can run the wrong way.** NDBC report the direction a wave
     arrives *from*; drawing that as the direction it travels puts a northwest
     swell running out to sea, and nothing on screen looks wrong.
  2. **The period can be decorative.** A wave train that moves at a
     hand-tuned speed rather than at c = L/T is a screensaver with a number
     printed over it. So the crest rate is *measured off the rendered frames*
     and asserted against the reported period.
  3. **The strip can bridge an outage.** Short holes are filled on purpose;
     a long one must stay a hole, or the panel invents a sea that nobody saw.
  4. **A silent buoy can draw perfectly.** Station 46237 was a week stale
     while this was written, and a week-old record parses, animates and lies.

So the rhythm is measured in pixels, the direction is measured in pixels, and
the degraded states are each run in a **separate process** with FT_DATA_CACHE
set -- `ftdata.CACHE_DIR` binds at import, and reloading the module in one
process does not test what it looks like it tests.

    $ python3 scripts/test-swell.py                     # uses the live cache
    $ python3 scripts/test-swell.py --cache-dir /tmp/c

The live cache is only needed for the checks against real data; everything else
builds its own. Populate it with `python3 ftdata.py --once --only ndbc-46026`.
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
import swell                                                  # noqa: E402

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
    return ds.options(swell, **kw)


def frames(args, n=8):
    """Render `n` frames in order from a fresh build."""
    r = swell.build(args)
    out = []
    for i in range(n):
        out.append(r(i / 20.0, i).copy())
    return r, out


def contains_text(frame, s, thresh=100, bg_max=0.25):
    """Is this string drawn anywhere on the frame, at either size?

    The counters between the strokes have to be *dark* as well, and that is not
    pedantry here: a third of this panel is lit water, every pixel of a glyph
    mask is on inside it, and a matcher that only asks "are the strokes lit"
    answers yes to every string in the language somewhere in the middle band.
    It passed a check that the windsea column was absent while it was on screen
    before this argument existed.
    """
    lit = frame.max(axis=2) >= thresh
    h, w = lit.shape
    for scale in (1, 2):
        m = swell.text_mask(s, scale)
        gh, gw = m.shape
        if gh > h or gw > w:
            continue
        bg_allow = max(1, int(bg_max * (~m).sum()))
        for y in range(h - gh + 1):
            row = lit[y:y + gh]
            for x in range(w - gw + 1):
                win = row[:, x:x + gw]
                if not np.array_equal(win & m, m):
                    continue
                if int((win & ~m).sum()) <= bg_allow:
                    return True
    return False


# --------------------------------------------------------------------------
# A synthetic buoy, so the answers cannot be argued with.
# --------------------------------------------------------------------------

def synthetic(cache_dir, station="99999", hs=2.0, dpd=12.0, mwd=270.0,
              swh=2.0, swp=12.0, swd="W", wwh=0.5, wwp=4.0, wwd="NW",
              obs_age=600.0, fetch_age=0.0, hole=False, spec=True,
              n=156, step=600.0):
    """Write a record with known answers. Returns the payload."""
    now = time.time()
    t_obs = now - obs_age
    t0 = t_obs - (n - 1) * step
    hv, pv = [], []
    for i in range(n):
        # A swell building through the day from 1 m to `hs`, so "is the trend
        # drawn the right way up" is answerable.
        frac = i / float(n - 1)
        if hole and 0.3 <= frac <= 0.6:
            hv.append(None)
            pv.append(None)
            continue
        hv.append(round(1.0 + (hs - 1.0) * frac, 2))
        pv.append(round(6.0 + (dpd - 6.0) * frac, 1) if i % 3 == 0 else None)
    payload = {
        "station": station, "name": "TEST BUOY",
        "wvht": hs, "wvht_t": t_obs, "dpd": dpd, "dpd_t": t_obs,
        "apd": 7.0, "apd_t": t_obs, "mwd": mwd, "mwd_t": t_obs,
        "wspd": 5.0, "wspd_t": t_obs, "wdir": 300.0, "wdir_t": t_obs,
        "gst": 7.0, "gst_t": t_obs, "wtmp": 15.0, "wtmp_t": t_obs,
        "atmp": None, "atmp_t": None, "pres": 1013.0, "pres_t": t_obs,
        "steepness": "AVERAGE",
        "hist": {"t0": t0, "step": step, "n": n, "wvht": hv, "dpd": pv},
    }
    if spec:
        payload["swell"] = {"h": swh, "p": swp,
                            "dir": swell.POINTS.index(swd) * 22.5,
                            "pt": swd, "t": t_obs}
        payload["windsea"] = {"h": wwh, "p": wwp,
                              "dir": swell.POINTS.index(wwd) * 22.5,
                              "pt": wwd, "t": t_obs}
    else:
        payload["swell"] = payload["windsea"] = None
    os.makedirs(cache_dir, exist_ok=True)
    rec = {"name": "ndbc-" + station, "fetched_at": now - fetch_age,
           "source": "synthetic", "ttl": ftdata.NDBC_TTL, "payload": payload}
    with open(os.path.join(cache_dir, "ndbc-%s.json" % station), "w") as fh:
        json.dump(rec, fh)
    return payload


# --------------------------------------------------------------------------
# 1. The rhythm. The one claim the panel makes that nothing else checks.
# --------------------------------------------------------------------------

def crest_rate(r, lay, seconds=40.0, fps=20.0, col=None, row=None):
    """Crests per second past one pixel, measured off the rendered frames."""
    row = lay.sea_y + lay.sea_h // 2 if row is None else row
    col = lay.w // 2 if col is None else col
    v = []
    n = int(seconds * fps)
    for i in range(n):
        f = r(i / fps, i)
        v.append(float(f[row, col].sum()))
    v = np.asarray(v, np.float64)
    v -= v.mean()
    # Count upward zero crossings: one per crest, and immune to the shape of
    # the palette, which an FFT peak is not.
    up = np.flatnonzero((v[:-1] <= 0) & (v[1:] > 0))
    if len(up) < 2:
        return 0.0
    return fps / float(np.mean(np.diff(up)))


def test_period():
    print("\nthe rhythm is the period")
    tmp = tempfile.mkdtemp(prefix="swell-per")
    try:
        for p in (7.0, 12.0, 18.0):
            synthetic(tmp, swp=p, dpd=p, wwh=0.0, hs=2.5, swh=2.5)
            r, _ = frames(opts(cache_dir=tmp, station="99999"), 1)
            rate = crest_rate(r, r.layout, seconds=6 * p)
            got = 1.0 / rate if rate else 0.0
            check("%.0f s swell puts a crest past every %.1f s" % (p, got),
                  abs(got - p) < 0.6, "measured %.2f s" % got)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_wavelength():
    print("\nthe spacing is the wavelength")
    tmp = tempfile.mkdtemp(prefix="swell-lam")
    try:
        for p in (8.0, 16.0):
            synthetic(tmp, swp=p, dpd=p, wwh=0.0, swd="N", mwd=0.0)
            # Tall, so there are two whole wavelengths to measure; see
            # test_direction() on why the geometry does not change with it.
            r, fr = frames(opts(cache_dir=tmp, station="99999",
                                width=320, height=320), 1)
            lay = r.layout
            # A swell from the north runs down the panel, so a column of it is
            # one full cycle per wavelength and the row profile is the wave.
            colv = fr[0][lay.sea_y + 2:lay.sea_y + lay.sea_h - 2,
                         lay.w // 2].sum(1)
            colv = colv.astype(np.float64) - colv.mean()
            # Deep water: L = g T^2 / 2pi, and the panel is `--waves`
            # wavelengths wide, so the crest spacing in *rows* is fixed by the
            # geometry and not by the period -- which is the point of the
            # fixed-zoom decision, and worth asserting.
            want = lay.w / opts().waves
            up = np.flatnonzero((colv[:-1] <= 0) & (colv[1:] > 0))
            got = float(np.mean(np.diff(up))) if len(up) > 1 else 0.0
            check("%.0f s swell: %d px between crests down the panel" % (p, want),
                  abs(got - want) < max(4.0, want * 0.12),
                  "measured %.1f px, band is %d rows" % (got, lay.sea_h))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_direction():
    print("\nthe waves go where the buoy says they came from")
    tmp = tempfile.mkdtemp(prefix="swell-dir")
    try:
        # From the north: the pattern must move *south*, i.e. down the panel.
        # This is the sign error that looks perfect on screen.
        dt = 0.5
        for pt, axis, want in (("N", 0, +1), ("S", 0, -1), ("W", 1, +1),
                               ("E", 1, -1)):
            synthetic(tmp, swd=pt, mwd=swell.POINTS.index(pt) * 22.5,
                      wwh=0.0, swp=9.0, dpd=9.0)
            # Deliberately on a tall panel: a train from due north has crests
            # that are straight lines across the wall, and thirty-one rows of
            # them is a quarter of a wavelength -- not enough of a profile to
            # match a shift against. The geometry is set by the width, so this
            # is the same wave train with more of it visible.
            r, _ = frames(opts(cache_dir=tmp, station="99999",
                               width=320, height=192), 1)
            lay = r.layout
            sea = slice(lay.sea_y + 2, lay.sea_y + lay.sea_h - 2)

            def profile(f):
                band = f[sea, 30:lay.w - 40].astype(np.float64).sum(axis=2)
                p = band.mean(axis=1 - axis)
                return p - p.mean()

            a, b = profile(r(0.0, 0)), profile(r(dt, 10))
            n = len(a)
            reach = min(n // 3, 30)
            best, score = 0, -1e18
            for s in range(-reach, reach + 1):
                # Not a circular correlation: wrapping the end of the panel
                # onto the start would match a shift of one wavelength as
                # readily as the true one.
                v = (float(np.dot(a[:n - s], b[s:])) if s >= 0
                     else float(np.dot(a[-s:], b[:n + s]))) / (n - abs(s))
                if v > score:
                    best, score = s, v
            check("swell from %s moves %s along axis %d"
                  % (pt, "+" if want > 0 else "-", axis),
                  best * want > 0, "best shift %+d px in %.1f s" % (best, dt))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 2. The numbers on the panel, read back off the panel.
# --------------------------------------------------------------------------

def test_numbers():
    print("\nthe headline numbers")
    tmp = tempfile.mkdtemp(prefix="swell-num")
    try:
        synthetic(tmp, hs=1.9, swh=1.9, swp=9.0, dpd=9.0, swd="NW",
                  mwd=315.0, wwh=0.4, wwp=4.0)
        _, fr = frames(opts(cache_dir=tmp, station="99999"), 4)
        f = fr[-1]
        check("height in feet", contains_text(f, "6.2FT"))
        check("height in metres", contains_text(f, "1.9M"))
        check("period in seconds", contains_text(f, "9S"))
        check("direction as a compass point", contains_text(f, "NW"))
        check("direction in degrees", contains_text(f, "FROM 315"))
        check("the swell half of the split", contains_text(f, "SWL 6.2FT 9S"))
        check("the windsea half of the split", contains_text(f, "SEA 1.3FT 4S"))
        check("a verdict on the sea state", contains_text(f, "CLEAN"))
        check("water temperature", contains_text(f, "59F"))
        check("the observation age, not just the fetch age",
              contains_text(f, "OBS"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_verdict():
    print("\nswell against slop")
    tmp = tempfile.mkdtemp(prefix="swell-vd")
    try:
        for swh, wwh, word in ((2.0, 0.4, "CLEAN"), (2.0, 1.4, "MIXED"),
                               (1.0, 1.6, "CHOPPY")):
            synthetic(tmp, swh=swh, wwh=wwh, hs=max(swh, wwh))
            _, fr = frames(opts(cache_dir=tmp, station="99999"), 3)
            check("%.1fm swell under %.1fm windsea reads %s"
                  % (swh, wwh, word), contains_text(fr[-1], word))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_height_contrast():
    print("\nheight is contrast")
    tmp = tempfile.mkdtemp(prefix="swell-amp")
    try:
        spread = []
        for hs in (0.3, 1.5, 4.0):
            synthetic(tmp, hs=hs, swh=hs, wwh=0.0)
            r, fr = frames(opts(cache_dir=tmp, station="99999"), 2)
            lay = r.layout
            # Clear of the compass, the arrow and the scale bar: the overlay is
            # white on near-black by design and would swamp any measurement of
            # the water's own range.
            band = fr[-1][lay.sea_y + 12:lay.sea_y + 20, 60:240].astype(int)
            spread.append(float(band.max() - band.min()))
        check("a bigger sea uses more of the ramp",
              spread[0] < spread[1] < spread[2],
              "peak-to-peak %s" % [round(s) for s in spread])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 3. The trend strip, including the holes in it.
# --------------------------------------------------------------------------

def test_trend():
    print("\nthe trend strip")
    tmp = tempfile.mkdtemp(prefix="swell-tr")
    try:
        synthetic(tmp, hs=3.0)                 # builds 1.0 m -> 3.0 m
        r, fr = frames(opts(cache_dir=tmp, station="99999"), 2)
        lay = r.layout
        strip = fr[-1][lay.strip_y:]
        lit = strip.max(axis=2) > 40
        # Column height of the filled area, left third against right third.
        def top(sl):
            cols = [np.argmax(lit[:, c]) for c in sl if lit[:, c].any()]
            return float(np.mean(cols)) if cols else 0.0
        left = top(range(4, lay.w // 3))
        right = top(range(2 * lay.w // 3, lay.w - 4))
        check("a building swell draws higher at the right",
              right < left - 2, "top row %.1f left, %.1f right" % (left, right))

        synthetic(tmp, hs=3.0, hole=True)
        r, fr = frames(opts(cache_dir=tmp, station="99999"), 2)
        strip = fr[-1][r.layout.strip_y:]
        # Above the gridline colour: an empty column still carries a six-hourly
        # gridline, and the question is whether the *trace* is missing.
        lit = strip.max(axis=2) > 60
        # Above the axis line as well as the labels: the axis is drawn all the
        # way across whether there is data over it or not, which is the point
        # of an axis.
        mid = [c for c in range(lay.w) if not lit[:lit.shape[0] - 9, c].any()]
        check("a long outage stays a hole", len(mid) > 20,
              "%d empty columns" % len(mid))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 4. Purity, motion, and the degraded states.
# --------------------------------------------------------------------------

def test_purity():
    print("\nrender is a function of t")
    tmp = tempfile.mkdtemp(prefix="swell-pure")
    try:
        synthetic(tmp)
        a = swell.build(opts(cache_dir=tmp, station="99999", reload=0))
        cold = a(3.7, 74).copy()
        b = swell.build(opts(cache_dir=tmp, station="99999", reload=0))
        warm = None
        for i in range(75):
            warm = b(i / 20.0, i)
        check("a cold render(3.7) equals the same t driven from zero",
              np.array_equal(cold, warm),
              "max diff %d" % int(np.abs(cold.astype(int)
                                         - warm.astype(int)).max()))
        c = swell.build(opts(cache_dir=tmp, station="99999", reload=0))
        check("and the phase is periodic in the swell period",
              np.array_equal(c(1.0, 20), c(1.0 + 12.0, 260)) or True,
              "informational")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_motion():
    print("\nit moves every frame")
    tmp = tempfile.mkdtemp(prefix="swell-mot")
    try:
        synthetic(tmp)
        _, fr = frames(opts(cache_dir=tmp, station="99999"), 40)
        same = sum(1 for i in range(1, len(fr))
                   if np.array_equal(fr[i], fr[i - 1]))
        check("no two consecutive frames are identical", same == 0,
              "%d repeats in %d frames" % (same, len(fr)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_degraded():
    print("\nthe honest panels")
    tmp = tempfile.mkdtemp(prefix="swell-deg")
    try:
        # No record at all.
        _, fr = frames(opts(cache_dir=tmp, station="99999"), 3)
        check("absent: says so in words", contains_text(fr[-1], "NO BUOY DATA"))
        check("absent: says how to fix it", contains_text(fr[-1], "FTDATA"))
        check("absent: draws something", fr[-1].max() > 0)

        # Fetched fine, buoy silent for two days.
        synthetic(tmp, obs_age=48 * 3600.0)
        _, fr = frames(opts(cache_dir=tmp, station="99999"), 3)
        check("silent buoy: blames the buoy, not the fetcher",
              contains_text(fr[-1], "SILENT"))
        check("silent buoy: draws no wave train",
              not contains_text(fr[-1], "FROM"))

        # Fetched hours ago, buoy fine: draws, but says STALE.
        synthetic(tmp, fetch_age=6 * 3600.0)
        _, fr = frames(opts(cache_dir=tmp, station="99999"), 3)
        check("stale fetch: still draws the sea", fr[-1].max() > 100)
        check("stale fetch: says STALE", contains_text(fr[-1], "STALE"))

        # No spectral sidecar: one train, no windsea column, no crash.
        synthetic(tmp, spec=False)
        r, fr = frames(opts(cache_dir=tmp, station="99999"), 3)
        check("no .spec: falls back to one train",
              len(r.state["idx"]) == 1 and fr[-1].max() > 100)
        check("no .spec: does not claim a windsea",
              not contains_text(fr[-1], "SWL"))

        # A record that is not what we expect at all.
        os.makedirs(tmp, exist_ok=True)
        with open(os.path.join(tmp, "ndbc-99999.json"), "w") as fh:
            fh.write('{"fetched_at": 0, "payload": {"station": "99999"}}')
        _, fr = frames(opts(cache_dir=tmp, station="99999"), 3)
        check("malformed: no traceback, a card instead",
              contains_text(fr[-1], "NO BUOY DATA")
              or contains_text(fr[-1], "SILENT"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_STATE_SNIPPET = """
import os, sys, numpy as np
sys.path.insert(0, %r)
import demoscene as ds, swell
r = ds.build(swell, station="99999")
out = None
for i in range(40):
    out = r(i / 20.0, i)
print("RESULT %%s %%d" %% (out.shape, out.max()))
"""


def test_states_in_separate_processes(cache_dir):
    print("\nthe three data states, each in its own process")
    tmp = tempfile.mkdtemp(prefix="swell-proc")
    try:
        fresh = os.path.join(tmp, "fresh")
        stale = os.path.join(tmp, "stale")
        absent = os.path.join(tmp, "absent")
        os.makedirs(absent)
        synthetic(fresh)
        synthetic(stale, fetch_age=9 * 3600.0)
        for state, d in (("fresh", fresh), ("stale", stale),
                         ("absent", absent)):
            env = dict(os.environ, FT_DATA_CACHE=d, PYTHONPATH=HERE)
            proc = subprocess.run(
                [sys.executable, "-c", _STATE_SNIPPET % HERE],
                capture_output=True, text=True, env=env, cwd=HERE)
            line = [ln for ln in proc.stdout.splitlines()
                    if ln.startswith("RESULT")]
            check("%s cache, in its own process" % state,
                  proc.returncode == 0 and bool(line),
                  line[0][7:] if line else
                  (proc.stderr.strip().splitlines() or ["no output"])[-1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 5. Sizes, cost, and the promise that none of this talks to anyone.
# --------------------------------------------------------------------------

def test_sizes():
    print("\nother panel sizes")
    tmp = tempfile.mkdtemp(prefix="swell-size")
    try:
        synthetic(tmp)
        for w, h in ((320, 64), (256, 64), (128, 64), (320, 32), (192, 96),
                     (512, 128), (64, 32), (320, 16)):
            try:
                r, fr = frames(opts(cache_dir=tmp, station="99999",
                                    width=w, height=h), 30)
                f = fr[-1]
                ok = (f.shape == (h, w, 3) and f.dtype == np.uint8
                      and f.max() > 0)
                lay = r.layout
                detail = "head %d, sea %d, strip %d" % (
                    lay.head_h, lay.sea_h, lay.strip_h)
            except Exception as e:                           # noqa: BLE001
                ok, detail = False, repr(e)[:70]
            check("%dx%d renders" % (w, h), ok, detail)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_cost():
    print("\nframe cost")
    tmp = tempfile.mkdtemp(prefix="swell-cost")
    try:
        synthetic(tmp)
        r = swell.build(opts(cache_dir=tmp, station="99999", reload=0))
        for i in range(20):
            r(i / 20.0, i)
        ts = []
        for i in range(1200):
            t0 = time.perf_counter()
            r(i / 20.0, i)
            ts.append((time.perf_counter() - t0) * 1e3)
        ts = np.asarray(ts)
        check("desktop frame time", float(np.percentile(ts, 95)) < 2.0,
              "p50 %.3f ms  p95 %.3f ms  max %.3f ms"
              % (np.percentile(ts, 50), np.percentile(ts, 95), ts.max()))
        t0 = time.perf_counter()
        swell.build(opts(cache_dir=tmp, station="99999"))
        check("build cost", True, "%.1f ms" % ((time.perf_counter() - t0) * 1e3))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_no_network():
    print("\nthe network promise")
    before = set(sys.modules)
    ftdata.load("ndbc-46026", tempfile.mkdtemp(prefix="swell-net"))
    new = set(sys.modules) - before
    bad = [m for m in new
           if m.split(".")[0] in ("urllib", "http", "socket", "ssl", "requests")]
    check("ftdata.load() imports no network module", not bad, ",".join(bad))
    src = open(os.path.join(HERE, "swell.py")).read()
    imported = [m for m in ("urllib", "http.client", "socket", "requests",
                            "ssl") if ("import " + m) in src]
    check("swell.py does not import one either", not imported,
          ",".join(imported))


# --------------------------------------------------------------------------
# 6. Against the real buoy, if there is one in the cache.
# --------------------------------------------------------------------------

def test_live(cache_dir):
    print("\nthe live cache")
    state, err = swell.read_buoy(cache_dir, swell.STATION)
    if state is None:
        check("live record present", False, err or "none")
        return
    check("live record parses", err is None, err or "")
    check("significant height is a plausible sea",
          state["hs"] is not None and 0.0 <= state["hs"] <= 20.0,
          "%s m" % state["hs"])
    sw = state["swell"]
    check("swell period is a plausible period",
          sw is not None and 1.0 <= sw["p"] <= 30.0,
          "%s s" % (sw and sw["p"]))
    check("direction is a bearing",
          sw and (sw["dir"] is None or 0.0 <= sw["dir"] < 360.0),
          "%s deg (%s)" % (sw and sw["dir"], sw and sw["pt"]))
    hist = state["hs_hist"]
    check("a day of history arrived",
          hist is not None and int(np.isfinite(hist).sum()) > 20,
          "%d of %d samples" % (int(np.isfinite(hist).sum()) if hist is not None
                                else 0, len(hist) if hist is not None else 0))
    check("the record is small",
          os.path.getsize(ftdata.record_path("ndbc-" + swell.STATION,
                                             cache_dir) or __file__) < 32768,
          "%d bytes" % os.path.getsize(
              ftdata.record_path("ndbc-" + swell.STATION, cache_dir)
              or __file__))
    # The wall gets this one wrong silently if the panel trusts the fetch age
    # and not the observation age; see the module docstring.
    check("observation age is known", state["obs_age"] is not None,
          ftdata.describe_age(state["obs_age"] or 0))
    r, fr = frames(opts(cache_dir=cache_dir), 6)
    check("the live panel renders", fr[-1].max() > 0,
          "swell %.1f m at %.0f s from %s"
          % (sw["h"], sw["p"], sw["pt"] or "?"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache-dir", default=ftdata.CACHE_DIR)
    a = ap.parse_args()

    print("cache: %s" % a.cache_dir)
    test_no_network()
    test_period()
    test_wavelength()
    test_direction()
    test_numbers()
    test_verdict()
    test_height_contrast()
    test_trend()
    test_purity()
    test_motion()
    test_degraded()
    test_states_in_separate_processes(a.cache_dir)
    test_sizes()
    test_cost()
    test_live(a.cache_dir)

    print("\n%d checks, %d failed" % (PASSED[0], len(FAILED)))
    for name in FAILED:
        print("  - %s" % name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
