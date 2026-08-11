#!/usr/bin/env python3
"""Checks for sun.py that a screenshot cannot make.

A panel that plays a stack of photographs is unusually good at looking
correct while being wrong, because the photographs carry the picture and the
demo only has to index them. The failures worth testing for here are:

  1. **The loop can be a cut.** The whole design claim of this panel is that
     the day joins up. A broken overlap still plays -- forty-one perfectly
     good frames of the Sun -- and jerks once a cycle, which is exactly the
     kind of fault somebody walking past registers as "that looks cheap"
     without being able to say why. So the seam is measured in pixels, against
     the same loop built with the overlap turned off.
  2. **The stack can be out of order, or reversed.** Time-lapse frames sorted
     backwards are as pretty as frames sorted forwards, and the panel would
     then be running the Sun backwards with a playhead sweeping the right way.
  3. **The playhead can drift off the trace.** It is the one thing tying the
     picture to the flux, and if it does not start at the left, end at the
     right and advance monotonically, the alignment claim in the docstring is
     false.
  4. **The vignette can eat the disk.** It is a multiply over every frame in
     `build()`; a wrong radius quietly dims the photosphere instead of only
     the corona, and the result still looks like a plausible Sun.
  5. **Yesterday's ring draws perfectly.** It parses, it loops, it is a lovely
     Sun, and it is not today's.

Two things about how these are run, both taken from test-caiso.py. The demo
takes "now" from the wall clock for its age label, so every check that cares
about determinism pins the clock with `--at`. And `ftdata.CACHE_DIR` binds at
import, so the three data states -- fresh, stale, absent -- are each run in a
**separate process** with FT_DATA_CACHE set, at the bottom of this file.
Reloading the module in one process does not test what it looks like it tests.

    $ python3 scripts/test-sun.py                     # uses the live cache
    $ python3 scripts/test-sun.py --cache-dir /tmp/c  # or a pointed one

The live cache is only needed for the check against real data; everything else
builds its own. Populate it with `python3 ftdata.py --once --only sdo-aia193`.
"""

import argparse
import json
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
import sun                                                    # noqa: E402

FAILED = []
PASSED = [0]

# A fixed instant, so every synthetic ring and every label is reproducible.
PINNED = 1786470000.0                       # 2026-08-11 17:40:00 UTC


def check(name, ok, detail=""):
    PASSED[0] += 1
    if ok:
        print("  ok   %s" % name)
    else:
        FAILED.append(name)
        print("  FAIL %s%s" % (name, ("  -- " + detail) if detail else ""))


def opts(**kw):
    kw.setdefault("at", repr(PINNED))
    return ds.options(sun, **kw)


def frames(args, n, step=1 / 20.0):
    """Drive a fresh build sequentially from t=0 and keep every frame."""
    r = sun.build(args)
    return r, [r(i * step, i).copy() for i in range(n)]


# --------------------------------------------------------------------------
# A synthetic ring, whose answers cannot be argued with.
#
# The disk is a hard-edged circle whose *brightness encodes its frame index*,
# and there is a single bright marker pixel that walks one column per frame.
# That makes order, direction and blending all readable straight out of the
# pixels: if frame k does not have intensity k, the stack is not in the order
# it claims to be.
# --------------------------------------------------------------------------

def synthetic_ring(cache_dir, n=48, cadence=1800.0, newest_ago=600.0,
                   fetched_ago=120.0, tile=64, disk_frac=0.82):
    os.makedirs(cache_dir, exist_ok=True)
    c = (tile - 1) / 2.0
    yy, xx = np.mgrid[0:tile, 0:tile].astype(np.float32)
    r = np.sqrt((yy - c) ** 2 + (xx - c) ** 2) / c

    # A dim corona outside the limb, falling off with radius. Without it the
    # synthetic tile is a disk on black and the vignette has nothing to fade,
    # which would make the vignette's control check vacuously pass.
    corona = np.clip(70.0 * (disk_frac / np.maximum(r, 1e-6)) ** 2, 0, 70)

    frames_a = np.zeros((n, tile, tile), np.uint8)
    stamps = np.zeros(n, np.float64)
    for k in range(n):
        # 40..240 over the ring, so every frame is a different, ordered level.
        level = 40 + int(200 * k / max(1, n - 1))
        f = np.where(r <= disk_frac, float(level), corona).astype(np.uint8)
        # The walking marker, inside the disk so the vignette cannot touch it.
        col = 8 + (k % (tile - 16))
        f[tile // 2, col] = 255
        frames_a[k] = f
        stamps[k] = PINNED - newest_ago - (n - 1 - k) * cadence

    name = ftdata.SDO_PRODUCT
    blob = "%s-test.npz" % name
    np.savez_compressed(os.path.join(cache_dir, blob),
                        frames=frames_a, stamps=stamps)
    payload = {"blob": blob, "count": n, "oldest": float(stamps[0]),
               "newest": float(stamps[-1]), "cadence": cadence, "want": 48,
               "tile": tile, "wave": "0193", "crop": 248.0,
               "instrument": "SDO/AIA", "channel": "193 A",
               "disk_frac": disk_frac, "fetched": n, "missing": 0,
               "listings": 0}
    rec = {"name": name, "fetched_at": PINNED - fetched_ago,
           "source": "test", "ttl": ftdata.SDO_TTL, "payload": payload}
    with open(os.path.join(cache_dir, name + ".json"), "w") as fh:
        json.dump(rec, fh)
    return payload


def synthetic_xray(cache_dir, spike_at=None, fetched_ago=300.0):
    """96 quarter-hour buckets of B-class, optionally with one M-flare."""
    n = 96
    series = [5e-7] * n
    if spike_at is not None:
        series[spike_at] = 3e-5                       # M3
    end = PINNED - 120.0
    start = end - (n - 1) * 900.0

    def iso(t):
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))

    payload = {"series": series, "minutes_per_bucket": 15,
               "start": iso(start), "end": iso(end),
               "current": series[-1], "current_class": "B5.0",
               "peak": max(series), "peak_class": "M3.0" if spike_at else "B5.0",
               "satellite": 18}
    rec = {"name": "swpc_xray", "fetched_at": PINNED - fetched_ago,
           "source": "test", "ttl": 3600, "payload": payload}
    with open(os.path.join(cache_dir, "swpc_xray.json"), "w") as fh:
        json.dump(rec, fh)
    return payload


# --------------------------------------------------------------------------

def test_no_network():
    print("\nthe network promise")
    before = set(sys.modules)
    tmp = tempfile.mkdtemp(prefix="sun-net")
    try:
        ftdata.load(ftdata.SDO_PRODUCT, tmp)
        ftdata.load_blob(None, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    new = set(sys.modules) - before
    bad = [m for m in new
           if m.split(".")[0] in ("urllib", "http", "socket", "ssl", "requests")]
    check("load() imports no network module", not bad, ",".join(bad))
    src = open(os.path.join(HERE, "sun.py")).read()
    check("sun.py never imports a fetcher dependency",
          "urllib" not in src and "from PIL" not in src
          and "import requests" not in src)


def test_order_and_direction():
    """The stack must run oldest to newest, and say so in its own pixels."""
    print("\nframe order and direction")
    tmp = tempfile.mkdtemp(prefix="sun-order")
    try:
        synthetic_ring(tmp, n=48)
        # No overlap and no vignette: this is a statement about ordering, and
        # the dissolve deliberately mixes the ends together.
        r = sun.build(opts(cache_dir=tmp, overlap=0, vignette=0.0, xray=False))
        stack = r.state["stack"]
        n = len(stack)
        # A pixel of each frame carries that frame's level, mapped through the
        # AIA ramp -- which is monotonic, so brightness must rise. Sampled six
        # rows above centre and not at the centre itself, because the walking
        # marker crosses the centre pixel on exactly one frame of the ring and
        # would put a 255 in the middle of an otherwise ordered series.
        mid = stack[:, stack.shape[1] // 2 - 6,
                    stack.shape[2] // 2].astype(int).sum(1)
        rising = np.all(np.diff(mid) >= 0)
        check("stack runs oldest to newest", rising,
              "levels: %s" % mid[:6].tolist())
        check("stack is not reversed", mid[0] < mid[-1])
        stamps = r.state["stamps"]
        check("stamps are sorted ascending", np.all(np.diff(stamps) > 0))
        check("ring covers about a day",
              23.0 <= (stamps[-1] - stamps[0]) / 3600.0 <= 24.5,
              "%.2f h" % ((stamps[-1] - stamps[0]) / 3600.0))
        check("no overlap means full-length loop", n == 48, str(n))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_loop_seam():
    """The panel's central claim: the wrap is not a cut.

    Measured rather than asserted by eye. The mean absolute difference
    between consecutive loop frames is a step; the step across the wrap must
    not stand out against the steps inside the loop. With the overlap off it
    stands out enormously, which is what makes this a real test and not a
    tautology -- the control has to fail.
    """
    print("\nthe loop's seam")
    tmp = tempfile.mkdtemp(prefix="sun-seam")
    try:
        synthetic_ring(tmp, n=48)

        def ratio(overlap):
            r = sun.build(opts(cache_dir=tmp, overlap=overlap,
                               vignette=0.0, xray=False))
            s = r.state["stack"].astype(np.float32)
            n = len(s)
            steps = np.array([np.abs(s[(i + 1) % n] - s[i]).mean()
                              for i in range(n)])
            return steps[-1] / max(np.median(steps[:-1]), 1e-6)

        cut = ratio(0)
        blended = ratio(6)
        check("a cut loop has an obvious seam (control)", cut > 4.0,
              "wrap step is %.1fx the interior step" % cut)
        check("the overlap removes it", blended < cut / 2.0,
              "%.2fx with overlap, %.2fx without" % (blended, cut))
        check("overlap shortens the loop by exactly its own length",
              len(sun.build(opts(cache_dir=tmp, overlap=6, xray=False)
                            ).state["stack"]) == 48 - 6)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_vignette_keeps_the_disk():
    """It may darken the corona. It may not darken the photosphere."""
    print("\nthe vignette")
    tmp = tempfile.mkdtemp(prefix="sun-vig")
    try:
        synthetic_ring(tmp, n=48, disk_frac=0.82)
        plain = sun.build(opts(cache_dir=tmp, overlap=0, vignette=0.0,
                               xray=False)).state["stack"]
        faded = sun.build(opts(cache_dir=tmp, overlap=0, vignette=0.30,
                               xray=False)).state["stack"]
        size = plain.shape[1]
        c = (size - 1) / 2.0
        yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
        rr = np.sqrt((yy - c) ** 2 + (xx - c) ** 2) / c
        # Well inside the limb, nothing may change at all.
        inner = rr <= 0.75
        same = np.array_equal(plain[:, inner], faded[:, inner])
        check("photosphere is untouched", same)
        # At the tile edge midpoints, everything must be gone.
        edge = faded[:, size // 2, 0].astype(int).sum()
        check("the square edge is faded to black", edge == 0, str(edge))
        # And the plain crop is what it is protecting against.
        check("the un-vignetted crop is bright at that edge (control)",
              plain[:, size // 2, 0].astype(int).sum() > 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_playhead():
    """It must start left, finish right, and never go backwards mid-loop."""
    print("\nthe playhead")
    tmp = tempfile.mkdtemp(prefix="sun-head")
    try:
        synthetic_ring(tmp, n=48)
        synthetic_xray(tmp)
        args = opts(cache_dir=tmp)
        r = sun.build(args)
        period = len(r.state["stack"])
        span = period / args.frame_rate
        xs = []
        for i in range(140):
            t = i * span / 140.0
            f = r(t, i)
            col = np.where((f[:, :, 0] > 180) & (f[:, :, 2] > 120))[1]
            # The playhead is the warm vertical line right of the disk box.
            col = col[col >= r.disk]
            xs.append(int(np.median(col)) if len(col) else -1)
        good = [x for x in xs if x >= 0]
        check("the playhead is drawn", len(good) > 120, str(len(good)))
        check("it advances monotonically",
              all(b >= a for a, b in zip(good, good[1:])),
              "%s" % good[:8])
        check("it starts near the left of the trace", good[0] < r.disk + 20,
              str(good[0]))
        check("it ends near the right of the panel", good[-1] > 300,
              str(good[-1]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_flare_shows():
    """An M-flare must be visibly taller than a quiet day, and warm."""
    print("\nthe flux trace")
    tmp = tempfile.mkdtemp(prefix="sun-flare")
    try:
        synthetic_ring(tmp, n=48)
        synthetic_xray(tmp)
        quiet = sun.build(opts(cache_dir=tmp)).state["bg"]
        synthetic_xray(tmp, spike_at=60)
        loud = sun.build(opts(cache_dir=tmp)).state["bg"]
        # Count lit rows in the trace band, right of the disk.
        def lit(bg):
            band = bg[16:52, 70:]
            return int((band.astype(int).sum(2) > 20).sum())
        check("a flare adds height to the trace", lit(loud) > lit(quiet),
              "%d vs %d" % (lit(loud), lit(quiet)))
        # The spike must be warm: red channel well above blue somewhere.
        band = loud[16:52, 70:].astype(int)
        warm = ((band[:, :, 0] - band[:, :, 2]) > 60).sum()
        check("the flare column is warm, not blue-grey", warm > 4, str(warm))
        cool = quiet[16:52, 70:].astype(int)
        check("a quiet day is not warm (control)",
              ((cool[:, :, 0] - cool[:, :, 2]) > 60).sum() == 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_purity():
    """render(t) must not depend on how many times it has been called.

    The clock is pinned with --at, which is the documented way this demo is
    made deterministic; without it the age label moves with the wall clock and
    the panel is honestly wall-clock driven. Reload is disabled for the same
    reason.
    """
    print("\npurity of render(t)")
    tmp = tempfile.mkdtemp(prefix="sun-pure")
    try:
        synthetic_ring(tmp, n=48)
        synthetic_xray(tmp)
        t0 = 6.3
        cold = sun.build(opts(cache_dir=tmp, reload=0.0))(t0, 126).copy()
        r = sun.build(opts(cache_dir=tmp, reload=0.0))
        driven = None
        for i in range(127):
            driven = r(i / 20.0, i)
        check("driving from zero reaches the same pixels",
              np.array_equal(cold, driven))
        # And out of order, which is what a scheduler seeking does.
        r2 = sun.build(opts(cache_dir=tmp, reload=0.0))
        for t in (11.0, 2.5, 8.75, 0.0):
            r2(t, 0)
        check("after seeking about, t0 is still t0",
              np.array_equal(cold, r2(t0, 126)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_degraded():
    print("\nmissing, corrupt and half-there records")
    tmp = tempfile.mkdtemp(prefix="sun-bad")
    try:
        empty = os.path.join(tmp, "empty")
        os.makedirs(empty)
        _, fs = frames(opts(cache_dir=empty), 6)
        check("absent cache renders a card, not a traceback",
              fs[-1].shape == (64, 320, 3) and fs[-1].any())

        # A record whose sidecar is gone.
        gone = os.path.join(tmp, "gone")
        synthetic_ring(gone)
        os.unlink(os.path.join(gone, "%s-test.npz" % ftdata.SDO_PRODUCT))
        _, fs = frames(opts(cache_dir=gone), 6)
        check("missing sidecar renders a card", fs[-1].any())

        # A truncated sidecar.
        broken = os.path.join(tmp, "broken")
        synthetic_ring(broken)
        with open(os.path.join(broken, "%s-test.npz" % ftdata.SDO_PRODUCT),
                  "wb") as fh:
            fh.write(b"not an npz")
        _, fs = frames(opts(cache_dir=broken), 6)
        check("corrupt sidecar renders a card", fs[-1].any())

        # Garbage JSON.
        junk = os.path.join(tmp, "junk")
        os.makedirs(junk)
        with open(os.path.join(junk, ftdata.SDO_PRODUCT + ".json"), "w") as fh:
            fh.write("{ not json")
        _, fs = frames(opts(cache_dir=junk), 6)
        check("unparseable record renders a card", fs[-1].any())

        # A one-frame ring: no loop to speak of, must still draw.
        one = os.path.join(tmp, "one")
        synthetic_ring(one, n=1)
        _, fs = frames(opts(cache_dir=one), 12)
        check("a single-frame ring still plays", fs[-1].any())

        # A short ring, which is what a cold start looks like.
        short = os.path.join(tmp, "short")
        synthetic_ring(short, n=9)
        _, fs = frames(opts(cache_dir=short), 12)
        check("a nine-frame ring still plays", fs[-1].any())

        # No flux record at all: the trace is a garnish, not a dependency.
        nox = os.path.join(tmp, "nox")
        synthetic_ring(nox)
        _, fs = frames(opts(cache_dir=nox), 8)
        check("no x-ray record still draws the Sun", fs[-1][:, :64].any())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_sizes():
    print("\nother panel sizes")
    tmp = tempfile.mkdtemp(prefix="sun-size")
    try:
        synthetic_ring(tmp)
        synthetic_xray(tmp)
        for w, h in ((320, 64), (256, 64), (128, 64), (320, 32), (192, 96),
                     (512, 128), (64, 32), (320, 16), (96, 64)):
            try:
                r = sun.build(opts(cache_dir=tmp, width=w, height=h))
                out = None
                for i in range(6):
                    out = r(i / 20.0, i)
                ok = out.shape == (h, w, 3) and out.dtype == np.uint8
            except Exception as e:                           # noqa: BLE001
                ok, r = False, repr(e)
            check("%dx%d" % (w, h), ok, "" if ok else str(r))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_speed():
    print("\nspeed")
    tmp = tempfile.mkdtemp(prefix="sun-speed")
    try:
        synthetic_ring(tmp)
        synthetic_xray(tmp)
        args = opts(cache_dir=tmp, reload=0.0)
        r = sun.build(args)
        n = 400
        for i in range(20):                                  # warm up
            r(i / 20.0, i)
        ts = []
        for i in range(n):
            t0 = time.perf_counter()
            r(i / 20.0, i)
            ts.append((time.perf_counter() - t0) * 1000.0)
        ts = np.array(ts)
        print("    mean %.3f ms  p95 %.3f ms  max %.3f ms"
              % (ts.mean(), np.percentile(ts, 95), ts.max()))
        # Desktop numbers lie by well over an order of magnitude against the
        # Pi, so this is a regression guard and not a certificate.
        check("mean under 1.5 ms on this machine", ts.mean() < 1.5,
              "%.3f ms" % ts.mean())
        check("p95 close to the mean", np.percentile(ts, 95) < 4 * ts.mean())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_live(cache_dir):
    print("\nthe live cache")
    got = ftdata.load(ftdata.SDO_PRODUCT, cache_dir)
    if got is None:
        print("  --   no %s record; run "
              "python3 ftdata.py --once --only %s"
              % (ftdata.SDO_PRODUCT, ftdata.SDO_PRODUCT))
        return
    payload, age = got
    blob = ftdata.load_blob(payload.get("blob"), cache_dir)
    check("the sidecar opens", blob is not None)
    if blob is None:
        return
    fr, st = blob["frames"], blob["stamps"]
    check("frames are a square uint8 stack",
          fr.ndim == 3 and fr.dtype == np.uint8 and fr.shape[1] == fr.shape[2],
          str(fr.shape))
    check("one stamp per frame", len(fr) == len(st))
    check("stamps are plausible epochs",
          bool(np.all(st > 1.7e9) and np.all(st < time.time() + 3600)))
    check("the ring is not longer than a day",
          (st.max() - st.min()) <= 25 * 3600.0,
          "%.1f h" % ((st.max() - st.min()) / 3600.0))
    check("every crop in the ring is the same geometry",
          float(payload.get("crop", -1)) == float(ftdata.SDO_CROP_R),
          str(payload.get("crop")))
    # The Sun must actually be in the picture: a bright middle, dark corners.
    mid = float(fr[:, fr.shape[1] // 2, fr.shape[2] // 2].mean())
    corner = float(fr[:, :4, :4].mean())
    check("the disk is bright and the corners are not", mid > 60 > corner,
          "centre %.0f corner %.0f" % (mid, corner))
    print("    %d frames, %.1f h, age %s"
          % (len(fr), (st.max() - st.min()) / 3600.0, ftdata.describe_age(age)))
    r = sun.build(ds.options(sun, cache_dir=cache_dir))
    out = r(3.0, 60)
    check("it renders from the live cache", out.shape == (64, 320, 3))


# --------------------------------------------------------------------------
# `ftdata.CACHE_DIR` is read at import time, so a test that sets FT_DATA_CACHE
# and reloads the module is testing the state of its own import machinery and
# not the state of the cache. So each state gets a fresh interpreter, with the
# environment set the way the wall sets it and no --cache-dir to paper over it.
# --------------------------------------------------------------------------

def _one_state(state, cache_dir):
    """The child half. Prints one RESULT line and exits."""
    args = ds.options(sun, at=repr(PINNED))   # no cache_dir: CACHE_DIR wins
    r = sun.build(args)
    out = None
    for i in range(10):
        out = r(i / 20.0, i)
    lit = int((out.astype(int).sum(2) > 24).sum())
    warm = int((out[:, :, 0].astype(int) - out[:, :, 2]) .max())
    print("RESULT %s shape=%s lit=%d warm=%d" % (state, out.shape, lit, warm))
    return 0


def test_states_in_separate_processes():
    print("\nfresh, stale and absent -- one process each, FT_DATA_CACHE set")
    tmp = tempfile.mkdtemp(prefix="sun-proc")
    try:
        fresh = os.path.join(tmp, "fresh")
        synthetic_ring(fresh, newest_ago=600.0, fetched_ago=120.0)
        synthetic_xray(fresh)
        stale = os.path.join(tmp, "stale")
        # Older than SDO_TTL, so the panel must keep playing and say so.
        synthetic_ring(stale, newest_ago=5 * 3600.0, fetched_ago=5 * 3600.0)
        absent = os.path.join(tmp, "absent")
        os.makedirs(absent)

        for state, d in (("fresh", fresh), ("stale", stale),
                         ("absent", absent)):
            env = dict(os.environ, FT_DATA_CACHE=d)
            # FT_DATA_BLOBS too: the blob directory is searched as well, and a
            # stray /run/ftdata on the machine running the tests must not be
            # able to answer for this one.
            env["FT_DATA_BLOBS"] = d
            proc = subprocess.run(
                [sys.executable, os.path.abspath(__file__),
                 "--state", state, "--cache-dir", d],
                env=env, capture_output=True, text=True, timeout=180)
            line = [ln for ln in proc.stdout.splitlines()
                    if ln.startswith("RESULT")]
            check("%s cache, in its own process" % state,
                  proc.returncode == 0 and bool(line),
                  (proc.stderr or "").strip()[-300:])
            if not line:
                continue
            lit = int(line[0].split("lit=")[1].split()[0])
            if state == "absent":
                check("absent draws a card with type on it", lit > 200,
                      str(lit))
            else:
                check("%s draws the Sun" % state, lit > 900, str(lit))
        # The stale panel must say so in red somewhere on the top line.
        env = dict(os.environ, FT_DATA_CACHE=stale, FT_DATA_BLOBS=stale)
        proc = subprocess.run(
            [sys.executable, "-c",
             "import sys;sys.path.insert(0,%r);"
             "import numpy as np, demoscene as ds, sun;"
             "r=ds.build(sun, at=%r);f=r(1.0,20);"
             "band=f[0:8,64:].astype(int);"
             "print('WARN', int(((band[:,:,0]-band[:,:,2])>120).sum()))"
             % (HERE, repr(PINNED))],
            env=env, capture_output=True, text=True, timeout=180)
        warn = 0
        for ln in proc.stdout.splitlines():
            if ln.startswith("WARN"):
                warn = int(ln.split()[1])
        check("stale says so in red on the top line", warn > 4,
              (proc.stderr or "").strip()[-300:] or str(warn))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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
    test_order_and_direction()
    test_loop_seam()
    test_vignette_keeps_the_disk()
    test_playhead()
    test_flare_shows()
    test_purity()
    test_degraded()
    test_sizes()
    test_speed()
    test_states_in_separate_processes()
    test_live(a.cache_dir)

    print("\n%d checks, %d failed" % (PASSED[0], len(FAILED)))
    for name in FAILED:
        print("  - %s" % name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
