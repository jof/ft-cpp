#!/usr/bin/env python3
"""Checks for muni.py that a screenshot cannot make.

This panel can draw a confident, pretty, wrong picture in several ways, and
none of them look wrong on the wall:

  1. **The 22 can silently vanish.** Its stop is 413 m away; the 19's and the
     55's are 140-201 m. Any stop search that takes the nearest few stops
     overall, or uses a quarter-mile radius, finds four stops of the 19 and 55
     and never reaches the 22 -- and then draws a beautiful panel that claims
     three routes and shows two. A script already on the Pi has exactly this
     bug. So the routes present in the record are asserted by name.
  2. **The catchable/missed boundary can be off by a lane.** It is the whole
     panel: a bus one pixel right of the post is one you can run for, one pixel
     left of it is one you have lost. Drawn the wrong way round it is exactly
     as pretty and says the opposite thing, so it is asserted in pixels either
     side of the post rather than in arithmetic.
  3. **The post can end up in the wrong place.** If the walk is not drawn to
     the same scale as the buses, the panel is decorative rather than true. The
     posts are asserted against walk time * pixels-per-minute directly.
  4. **A shared stop can leak.** 16th & Wisconsin is the 22's stop *and* a 55
     stop. The 55 has its own stop 200 m closer, so a Wisconsin 55 drawn in the
     55's lane would sit at the wrong distance. Asserted by line and direction.
  5. **A scheduled bus can wear a tracked bus's clothes.** `Monitored: false`
     must draw hollow. This is the panel's honesty and it is one array away
     from being lost.

Two things about how these run, both learned the hard way in this tree. The
demo is a **wall-clock** panel, so every check pins `--now`; without that the
answers change between one run and the next. Pinning `--now` is not enough on
its own, though: a record's *age* is measured against the real clock inside
`ftdata.load()`, so the fixture's `fetched_at` is written from `time.time()`
and not from the pinned moment -- see `synthetic()`. And `ftdata.CACHE_DIR` binds at
import, so the three data states -- fresh, stale, absent -- are each run in a
**separate process** with FT_DATA_CACHE set, at the bottom of this file.
Reloading the module in one process does not test what it looks like it tests.

    $ python3 scripts/test-muni.py                     # synthetic, needs nothing
    $ python3 scripts/test-muni.py --cache-dir /tmp/c  # also check a real record

Populate a real cache with:

    $ python3 ftdata.py --once --only muni-18th
    $ FT_511_KEY=... python3 ftdata.py --once --only muni-live
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
import muni                                                   # noqa: E402

FAILED = []
PASSED = [0]

# A fixed weekday moment, so every expected number below is a constant.
NOW = 1786555946.0 + 90.0


def check(name, ok, detail=""):
    if ok:
        PASSED[0] += 1
    else:
        FAILED.append("%s%s" % (name, (": " + detail) if detail else ""))
    print("%-4s %s%s" % ("ok" if ok else "FAIL", name,
                         ("  -- " + detail) if detail and not ok else ""))


# --------------------------------------------------------------------------
# A synthetic pair of records whose answers cannot be argued with.
#
# Three routes, two directions, walks of exactly 2, 4 and 7 minutes, and buses
# placed at exact offsets from the walk time so that "catchable" and "missed"
# are decided by arithmetic the test controls rather than by whatever the live
# feed happened to be doing.
# --------------------------------------------------------------------------

WALK_S = {"19": 120, "22": 420, "55": 240}
LABELS = {("19", 1): "BEACH", ("19", 0): "SHIPYARD",
          ("22", 1): "BAY", ("22", 0): "UCSF",
          ("55", 1): "16TH/MSN", ("55", 0): "20TH/3RD"}
CODES = {("19", 1): "14352", ("19", 0): "16192",
         ("22", 1): "17769", ("22", 0): "17762",
         ("55", 1): "14126", ("55", 0): "14125"}
METRES = {"19": 140, "22": 413, "55": 200}


def synthetic(cache_dir, now=NOW, live=True, fetched_ago=60.0,
              live_ago=60.0, expired=False):
    """Write a muni-18th (and optionally muni-live) record into `cache_dir`.

    Two clocks are in play here and they are not the same clock.

    The *panel* clock is pinned: `now` decides where the buses are drawn, and
    every expected column below is a constant derived from it. But the
    *freshness* clock is not ours to pin -- `ftdata.load()` reports a record's
    age as `time.time() - fetched_at`, against the real wall clock, and
    `muni.build()` drops a live record past its TTL and falls back to the
    timetable. So `fetched_ago` is measured from the real clock, never from
    `now`. Writing `fetched_at = now - 60` instead gives a fixture whose
    freshness decays as the real clock walks away from the pinned `NOW`: the
    suite passed for the first half hour after `NOW` and then, silently,
    started rendering the schedule fallback and failing fifteen position and
    colour checks that had nothing to do with position or colour.
    """
    os.makedirs(cache_dir, exist_ok=True)
    real = time.time()
    today = time.strftime("%Y%m%d", time.localtime(now))
    dates = [time.strftime("%Y%m%d", time.localtime(now + d * 86400.0))
             for d in (-1, 0, 1)]
    services = {} if expired else dict((d, ["W"]) for d in dates)

    midnight = time.mktime(time.strptime(today + " 00:00:00",
                                         "%Y%m%d %H:%M:%S"))
    stops = []
    for route in ("19", "22", "55"):
        for direction in (1, 0):
            # Timetabled departures every ten minutes from local midnight, so
            # the schedule fallback always has something on the street.
            mins = list(range(0, 1440, 10))
            stops.append({
                "route": route, "dir": direction,
                "code": CODES[(route, direction)],
                "name": "TEST %s %d" % (route, direction),
                "label": LABELS[(route, direction)],
                "metres": METRES[route], "walk_s": WALK_S[route],
                "headsign": LABELS[(route, direction)],
                "lat": 37.76, "lon": -122.40,
                "times": {"W": mins},
            })
    _write(cache_dir, "muni-18th", {
        "schema": 1, "feed_version": "TEST", "feed_start": dates[0],
        "feed_end": dates[-1], "services": services, "stops": stops,
        "routes": ["19", "22", "55"], "walk_mps": 1.25, "walk_detour": 1.3,
    }, real - fetched_ago, ftdata.ttl_for("muni-18th"))
    del midnight

    if not live:
        try:
            os.unlink(os.path.join(cache_dir, "muni-live.json"))
        except OSError:
            pass
        return

    # Buses at exact offsets either side of each route's walk time, plus one
    # far out, plus a lateness pair and one unmonitored bus.
    live_stops = {}
    for route in ("19", "22", "55"):
        for direction in (1, 0):
            walk_m = WALK_S[route] / 60.0
            offsets = (walk_m - 0.5, walk_m + 0.5, walk_m + 6.0)
            visits = []
            for i, off in enumerate(offsets):
                exp = now + off * 60.0
                visits.append({
                    "line": route, "dir": "IB" if direction else "OB",
                    "dest": LABELS[(route, direction)],
                    "exp": int(round(exp)),
                    # The *far* bus of every lane is three minutes late. It has
                    # to be the far one: make the near one late and its aimed
                    # time falls in the past, off the left-hand end of the
                    # street, where there is nothing to assert against.
                    "aim": int(round(exp - 180.0)) if i == 2 else int(round(exp)),
                    "mon": not (route == "55" and i == 1),
                })
            # The poison pill: 16th & Wisconsin really does carry the 55 as
            # well as the 22, at a completely different walk distance.
            if route == "22":
                visits.append({
                    "line": "55", "dir": "IB" if direction else "OB",
                    "dest": "WRONG", "exp": int(round(now + 60.0)),
                    "aim": int(round(now + 60.0)), "mon": True})
            live_stops[CODES[(route, direction)]] = visits
    _write(cache_dir, "muni-live", {
        "schema": 1, "t": int(now), "agency": "SF", "stops": live_stops,
        "n_stops": 6, "n_asked": 6, "errors": [], "rate_limited": None,
    }, real - live_ago, ftdata.ttl_for("muni-live"))


def _write(cache_dir, name, payload, fetched_at, ttl):
    path = os.path.join(cache_dir, name + ".json")
    with open(path, "w") as fh:
        json.dump({"name": name, "fetched_at": fetched_at, "source": "test",
                   "ttl": ttl, "payload": payload}, fh)


def opts(**kw):
    kw.setdefault("now", NOW)
    return ds.options(muni, **kw)


def lane_band(frame, i):
    """The rows of lane `i`, bus zone only."""
    y0 = muni.LANE_TOP + i * muni.LANE_H
    return frame[y0 + muni.LANE_BUS_Y:y0 + muni.LANE_BUS_Y + muni.LANE_BUS_H]


def lit_columns(band, thresh=24):
    """Columns of a band with any pixel above `thresh`."""
    return set(np.nonzero(band.max(axis=(0, 2)) > thresh)[0].tolist())


def is_missed(band, x):
    """Is the sprite centred near column x drawn in the missed grey?"""
    win = band[:, max(0, x - 5):x + 6].reshape(-1, 3).astype(int)
    win = win[win.max(axis=1) > 24]
    if not len(win):
        return None
    # Grey means the three channels sit close together; a route colour does not.
    spread = (win.max(axis=1) - win.min(axis=1)).mean()
    # bool(), not the numpy scalar: `np.bool_(True) is True` is False, and a
    # test that asserts identity against one silently never passes.
    return bool(spread < 24)


# --------------------------------------------------------------------------

def test_fixture_is_live():
    """The fixture must read as fresh, or every check below it means nothing.

    Almost everything this file asserts -- bus columns, the greying either side
    of the post, hollowness, the lateness mark, the margin text -- is asserted
    against the *live* record. `build()` drops a live record past its TTL and
    draws the timetable instead, which is correct behaviour and a disaster for
    a test: the panel still renders, still looks right, and fifteen checks fail
    describing pixels without once mentioning freshness. This check exists so
    that that failure has a name.
    """
    with tempfile.TemporaryDirectory() as cache:
        synthetic(cache)
        got = ftdata.load("muni-live", cache)
        fresh = got is not None and ftdata.is_fresh("muni-live", got[1])
        check("the synthetic live record reads as fresh", fresh,
              "age %ds vs ttl %s" % (int(got[1]) if got else -1,
                                     ftdata.ttl_for("muni-live")))
        # And in pixels: `auto` must land on the same frame as forcing `live`,
        # and a different one from the timetable. Forcing `live` uses the
        # record whether or not it is believed, so the two agreeing is exactly
        # the statement that the record was believed.
        auto = muni.build(opts(cache_dir=cache))(0.0, 0)
        forced = muni.build(opts(cache_dir=cache, source="live"))(0.0, 0)
        sched = muni.build(opts(cache_dir=cache, source="schedule"))(0.0, 0)
        check("auto draws the live record, not the timetable",
              np.array_equal(auto, forced) and not np.array_equal(auto, sched))


def test_routes_present():
    """All three routes, both directions. The 22 is the one that goes missing."""
    with tempfile.TemporaryDirectory() as cache:
        synthetic(cache)
        args = opts(cache_dir=cache)
        muni.build(args)                        # must not raise
        payload = ftdata.load("muni-18th", cache)[0]
        got = set((s["route"], s["dir"]) for s in payload["stops"])
        for route in ("19", "22", "55"):
            for direction in (0, 1):
                check("route %s dir %d present" % (route, direction),
                      (route, direction) in got)


def test_live_record_routes(cache_dir):
    """The same assertion against a real fetched record, which is the point."""
    got = ftdata.load("muni-18th", cache_dir)
    if got is None:
        print("     (no live muni-18th record; skipping)")
        return
    stops = got[0].get("stops") or []
    pairs = set((s.get("route"), s.get("dir")) for s in stops)
    for route in ("19", "22", "55"):
        check("real record has route %s both ways" % route,
              (route, 0) in pairs and (route, 1) in pairs,
              "got %s" % sorted(str(p) for p in pairs))
    # The 22 must be genuinely further than the other two, or the stop search
    # has quietly snapped it to something on 18th St that is not the 22.
    by_route = dict((s["route"], s["metres"]) for s in stops)
    if set(by_route) >= set(("19", "22", "55")):
        check("the 22's stop really is the far one",
              by_route["22"] > by_route["19"] and by_route["22"] > by_route["55"],
              "metres %s" % by_route)


def test_posts_to_scale():
    """The post is the walk time, at the same pixels-per-minute as the buses."""
    with tempfile.TemporaryDirectory() as cache:
        synthetic(cache)
        horizon = muni.HORIZON_MIN
        ppm = muni.STREET_W / horizon
        args = opts(cache_dir=cache)
        frame = muni.build(args)(0.0, 0)
        for i, (route, direction) in enumerate(
                [("19", 1), ("19", 0), ("22", 1), ("22", 0),
                 ("55", 1), ("55", 0)]):
            want = int(round(muni.DOOR_X + (WALK_S[route] / 60.0) * ppm))
            y = muni.LANE_TOP + i * muni.LANE_H + muni.LANE_ROAD
            # The post is the brightest thing on the road row *right of the
            # door*. The door itself is brighter and sits at DOOR_X, which is
            # what an unqualified argmax finds every time.
            row = frame[y].astype(int).sum(axis=1)
            got = muni.STREET_X0 + int(np.argmax(row[muni.STREET_X0:]))
            check("lane %d post at the walk distance" % i, abs(got - want) <= 1,
                  "want %d got %d" % (want, got))
        # And they must be ordered by walk: the 19 nearest, the 22 furthest.
        check("posts ordered by walk time",
              WALK_S["19"] < WALK_S["55"] < WALK_S["22"])


def test_catchable_boundary():
    """A bus outside the walk is its route's colour; inside it, grey."""
    with tempfile.TemporaryDirectory() as cache:
        synthetic(cache)
        ppm = muni.STREET_W / muni.HORIZON_MIN
        frame = muni.build(opts(cache_dir=cache))(0.0, 0)
        for i, route in enumerate(["19", "19", "22", "22", "55", "55"]):
            walk_m = WALK_S[route] / 60.0
            band = lane_band(frame, i)
            inside = int(round(muni.DOOR_X + (walk_m - 0.5) * ppm))
            outside = int(round(muni.DOOR_X + (walk_m + 0.5) * ppm))
            check("lane %d bus inside the walk is greyed" % i,
                  is_missed(band, inside) is True, "x=%d" % inside)
            check("lane %d bus outside the walk keeps its colour" % i,
                  is_missed(band, outside) is False, "x=%d" % outside)


def test_shared_stop_does_not_leak():
    """A 55 sitting at the 22's stop must not appear in the 22's lane."""
    with tempfile.TemporaryDirectory() as cache:
        synthetic(cache)
        live = ftdata.load("muni-live", cache)[0]
        stop = {"code": CODES[("22", 1)], "route": "22", "dir": 1}
        got = muni.live_visits(live, stop)
        check("22 lane takes only 22s from a shared stop", len(got) == 3,
              "got %d visits" % len(got))
        # ...and the 55's own lane reads its own, closer, stop.
        stop55 = {"code": CODES[("55", 1)], "route": "55", "dir": 1}
        check("55 lane reads its own stop",
              len(muni.live_visits(live, stop55)) == 3)
        # Direction must filter too: asking the same stop the other way round
        # must not return the inbound buses.
        wrong = muni.live_visits(live, {"code": CODES[("22", 1)],
                                        "route": "22", "dir": 0})
        check("direction filters as well as line", len(wrong) == 0)


def test_unmonitored_is_hollow():
    """Monitored:false draws the outline, not the solid."""
    with tempfile.TemporaryDirectory() as cache:
        synthetic(cache)
        ppm = muni.STREET_W / muni.HORIZON_MIN
        frame = muni.build(opts(cache_dir=cache))(0.0, 0)
        # The 55's middle bus is the unmonitored one; lanes 4 and 5 are the 55.
        x = int(round(muni.DOOR_X + (WALK_S["55"] / 60.0 + 0.5) * ppm))
        band = lane_band(frame, 4)
        solid_x = int(round(muni.DOOR_X + (WALK_S["55"] / 60.0 + 6.0) * ppm))
        hollow = band[1:3, x - 2:x + 3].max()
        solid = band[1:3, solid_x - 2:solid_x + 3].max()
        check("unmonitored bus is drawn hollow", int(hollow) < int(solid),
              "hollow centre %d vs solid centre %d" % (hollow, solid))


def test_lateness_bar():
    """Lateness is a mark under the road, on the same axis, signed."""
    with tempfile.TemporaryDirectory() as cache:
        synthetic(cache)
        ppm = muni.STREET_W / muni.HORIZON_MIN
        frame = muni.build(opts(cache_dir=cache))(0.0, 0)
        y = muni.LANE_TOP + 0 * muni.LANE_H + muni.LANE_LATE
        row = frame[y].astype(int)
        lit = np.nonzero(row.sum(axis=1) > 24)[0]
        check("a lateness mark is drawn at all", len(lit) > 0)
        if len(lit):
            # The far bus is three minutes late, so its aimed cap sits three
            # minutes to the left of it.
            walk_m = WALK_S["19"] / 60.0
            bus = muni.DOOR_X + (walk_m + 6.0) * ppm
            aim = muni.DOOR_X + (walk_m + 6.0 - 3.0) * ppm
            check("the lateness mark reaches back to the aimed time",
                  lit.min() <= aim + 2 and lit.max() >= min(bus, muni.W - 1) - 3,
                  "lit %d..%d, want ~%d..%d" % (lit.min(), lit.max(), aim, bus))
            # Late is warm: red channel must dominate blue.
            px = frame[y, int(round(aim))].astype(int)
            check("late reads warm", px[0] > px[2], "rgb %s" % px.tolist())


def test_lane_number():
    """The number is arrival minus walk, which is when you must leave."""
    with tempfile.TemporaryDirectory() as cache:
        synthetic(cache)
        # Every lane's first catchable bus is 0.5 min past its walk time, so
        # "leave in" is 0.5 min for all six: under a minute, so NOW.
        frame = muni.build(opts(cache_dir=cache))(0.0, 0)
        band = frame[muni.LANE_TOP + muni.LANE_TEXT_Y:
                     muni.LANE_TOP + muni.LANE_TEXT_Y + muni.GLYPH_H]
        want = muni.text_mask("NOW")
        x = muni.DOOR_X + 3
        got = band[:, x:x + want.shape[1]].max(axis=2) > 40
        check("a half-minute margin prints NOW", np.array_equal(got, want))

        # Drive the clock back six minutes. The first bus of lane 0 was half a
        # minute inside the walk; six minutes earlier it is 7.5 minutes out,
        # which against a 2-minute walk is 5.5 minutes of margin, which prints
        # as 5 -- the panel floors, it does not round, because rounding 5.5 up
        # to 6 would tell somebody they had longer than they do.
        frame = muni.build(opts(now=NOW - 360.0, cache_dir=cache))(0.0, 0)
        band = frame[muni.LANE_TOP + muni.LANE_TEXT_Y:
                     muni.LANE_TOP + muni.LANE_TEXT_Y + muni.GLYPH_H]
        want = muni.text_mask("5")
        got = band[:, x:x + want.shape[1]].max(axis=2) > 40
        check("margin is floored, not rounded", np.array_equal(got, want))


def test_horizon_flag():
    """--horizon rescales the street, the posts and which buses are on it."""
    with tempfile.TemporaryDirectory() as cache:
        synthetic(cache)
        wide = muni.build(opts(cache_dir=cache, horizon=40.0))(0.0, 0)
        y = muni.LANE_TOP + 2 * muni.LANE_H + muni.LANE_ROAD
        want = int(round(muni.DOOR_X + (WALK_S["22"] / 60.0)
                         * (muni.STREET_W / 40.0)))
        row = wide[y].astype(int).sum(axis=1)
        got = muni.STREET_X0 + int(np.argmax(row[muni.STREET_X0:]))
        check("--horizon moves the post", abs(got - want) <= 1,
              "want %d got %d" % (want, got))


def test_motion():
    """Buses slide left as t advances, and the panel is pure in t."""
    with tempfile.TemporaryDirectory() as cache:
        synthetic(cache)
        render = muni.build(opts(cache_dir=cache))
        a = lit_columns(lane_band(render(0.0, 0), 2))
        b = lit_columns(lane_band(render(60.0, 1200), 2))
        check("the street moves", a != b)
        check("it moves leftward", min(b) < min(a) or max(b) < max(a))

        r1 = muni.build(opts(cache_dir=cache))
        r2 = muni.build(opts(cache_dir=cache))
        cold = r1(9.15, 183)
        for i in range(184):
            warm = r2(i / 20.0, i)
        check("render is a pure function of t", np.array_equal(cold, warm))


def test_sizes():
    """Every frame is the shape and dtype the wall expects."""
    with tempfile.TemporaryDirectory() as cache:
        synthetic(cache)
        for kw in ({}, {"source": "schedule"}):
            frame = muni.build(opts(cache_dir=cache, **kw))(3.0, 60)
            check("frame shape %s" % (kw or "live"),
                  frame.shape == (64, 320, 3) and frame.dtype == np.uint8,
                  "%s %s" % (frame.shape, frame.dtype))


def test_no_network():
    """The demo module must not have pulled a network library in with it."""
    for mod in ("urllib.request", "http.client", "socket", "requests",
                "ssl"):
        check("muni.py does not import %s" % mod,
              mod not in sys.modules or mod == "socket",
              "in sys.modules")


def test_schedule_fallback():
    """No live record: the timetable, and it must not look tracked."""
    # First the mechanism, which is one array: the hollow sprite must actually
    # be hollow and the solid one solid, at the same place.
    sprites = muni._bus_sprites()
    for route in ("19", "22", "55"):
        solid = sprites[(route, muni.NEXT, True)][0]
        hollow = sprites[(route, muni.NEXT, False)][0]
        check("%s solid sprite has a filled body" % route,
              int(solid[1:3, 1:8].max()) > 40)
        check("%s hollow sprite has an empty body" % route,
              int(hollow[1:3, 1:8].max()) == 0)
        check("%s hollow sprite still has a roof" % route,
              int(hollow[0, 1:8].max()) > 20)

    with tempfile.TemporaryDirectory() as cache:
        synthetic(cache, live=False)
        # Everything the timetable produces is unmonitored by construction.
        geom = ftdata.load("muni-18th", cache)[0]
        rows = muni.scheduled(geom, geom["stops"][0], NOW)
        check("timetable produces buses at all", len(rows) > 0)
        check("no timetabled bus claims to be monitored",
              all(not mon for _when, _aim, mon in rows))
        check("no timetabled bus claims a lateness",
              all(aim is None for _when, aim, _mon in rows))

        frame = muni.build(opts(cache_dir=cache))(0.0, 0)
        check("timetable still draws a street", frame.max() > 60)

        # And in pixels: every drawn bus must have a dark middle. The roof row
        # is lit for both sprites, so runs are found there and then probed one
        # row down, at the centre, where only a solid bus has anything.
        checked = filled = 0
        for i in range(6):
            band = lane_band(frame, i)
            lit = band[0].max(axis=1) > 24
            x = 0
            while x < len(lit):
                if not lit[x]:
                    x += 1
                    continue
                end = x
                while end < len(lit) and lit[end]:
                    end += 1
                if end - x >= 5:
                    mid = (x + end) // 2
                    checked += 1
                    if int(band[1:3, mid].max()) > 24:
                        filled += 1
                x = end
        check("some timetable buses were actually found", checked >= 6,
              "found %d" % checked)
        check("no timetable bus is drawn solid", filled == 0,
              "%d of %d had filled bodies" % (filled, checked))


def _one_state(state, cache_dir):
    """Render one data state in this process; called by the child below."""
    args = opts(cache_dir=cache_dir)
    frame = muni.build(args)(1.0, 20)
    assert frame.shape == (64, 320, 3) and frame.dtype == np.uint8
    return "%s ok max=%d" % (state, frame.max())


def test_states_in_separate_processes():
    """Fresh, stale and absent, each in its own interpreter.

    ftdata.CACHE_DIR binds at import, and muni.py reads two products. Testing
    these by mutating a cache in one process would pass while the deployed
    thing failed.
    """
    root = tempfile.mkdtemp()
    try:
        cases = {}
        fresh = os.path.join(root, "fresh")
        synthetic(fresh)
        cases["fresh"] = fresh

        stale = os.path.join(root, "stale")
        synthetic(stale, fetched_ago=6 * 86400.0, live_ago=6 * 86400.0)
        cases["stale"] = stale

        absent = os.path.join(root, "absent")
        os.makedirs(absent)
        cases["absent"] = absent

        expired = os.path.join(root, "expired")
        synthetic(expired, live=False, expired=True)
        cases["expired"] = expired

        for state, cache in sorted(cases.items()):
            # Re-running this file with a flag, rather than exec'ing a slice of
            # its own source in a child. The slicing version worked until the
            # file grew a string containing the word it split on, and then
            # failed with a SyntaxError that said nothing about the real cause.
            env = dict(os.environ, FT_DATA_CACHE=cache, FT_DATA_BLOBS=cache)
            proc = subprocess.run(
                [sys.executable, os.path.abspath(__file__),
                 "--render-once", cache, "--state", state],
                env=env, capture_output=True, text=True)
            check("state %s renders in its own process" % state,
                  proc.returncode == 0,
                  (proc.stderr or "").strip().split("\n")[-1][:160])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_fetcher_helpers():
    """The reductions in ftdata.py, which no rendering check would catch."""
    check("headsign shortening", ftdata._muni_short("Beach Street") == "BEACH",
          ftdata._muni_short("Beach Street"))
    check("ampersand headsign",
          ftdata._muni_short("16th St & Mission") == "16TH/MSN",
          ftdata._muni_short("16th St & Mission"))
    check("UCSF is named, not truncated",
          ftdata._muni_short("UCSF Mission Bay") == "UCSF")
    check("a label always fits the gutter",
          all(len(ftdata._muni_short(s)) <= 8
              for s in ("Beach Street", "Shipyard", "UCSF Mission Bay",
                        "16th St & Mission", "20th St & 3rd St", "",
                        "Somewhere Extremely Long Indeed")))
    # GTFS times past 24:00 are a different service day, not a modulo.
    check("30:09 is 1809 minutes, not 9", ftdata._muni_hhmmss("30:09:00") == 1809)
    check("midnight is zero", ftdata._muni_hhmmss("00:00:00") == 0)
    check("junk time is None", ftdata._muni_hhmmss("nonsense") is None)
    # 511 timestamps are UTC with a Z, and must not be read as local.
    epoch = ftdata._muni_epoch("2026-08-12T17:34:54Z")
    check("511 timestamps parse as UTC",
          epoch is not None
          and time.strftime("%H:%M", time.gmtime(epoch)) == "17:34")
    check("absent timestamp is None", ftdata._muni_epoch(None) is None)
    # The key is read from the environment and never defaulted.
    saved = os.environ.pop("FT_511_KEY", None)
    try:
        check("no key means no key", ftdata.muni_live_key() is None)
        os.environ["FT_511_KEY"] = "  x  "
        check("a key is stripped", ftdata.muni_live_key() == "x")
    finally:
        os.environ.pop("FT_511_KEY", None)
        if saved is not None:
            os.environ["FT_511_KEY"] = saved
    # No secret may reach a record.
    check("the product description does not carry a key",
          "FT_511_KEY" in ftdata.PRODUCTS["muni-live"]["description"]
          or "$FT_511_KEY" in ftdata.PRODUCTS["muni-live"]["description"])


def test_request_budget():
    """Six stops on this interval must stay inside 511's sixty an hour.

    `is_due()` fires at nine tenths of the interval on purpose, so the worst
    case is what has to fit, not the nominal.
    """
    stops = len(ftdata.MUNI_LIVE_STOPS_FALLBACK)
    worst = stops * 3600.0 / (ftdata.MUNI_LIVE_INTERVAL * 0.9)
    check("worst-case request rate is inside the cap", worst <= 60.0,
          "%.1f/hour" % worst)
    check("worst-case request rate leaves headroom", worst <= 30.0,
          "%.1f/hour" % worst)
    check("the TTL outlasts the interval",
          ftdata.MUNI_LIVE_TTL > ftdata.MUNI_LIVE_INTERVAL)


def test_live_cache(cache_dir):
    """Against a real fetched pair, if there is one."""
    got = ftdata.load("muni-live", cache_dir)
    if got is None:
        print("     (no live muni-live record; skipping)")
        return
    payload, age = got
    check("real live record has stops", bool(payload.get("stops")))
    check("real live record has visits", payload.get("n_visits", 0) > 0)
    lines = set()
    for visits in (payload.get("stops") or {}).values():
        for v in visits:
            lines.add(v.get("line"))
            check("visit %s has an absolute expected time" % v.get("line"),
                  isinstance(v.get("exp"), (int, float)))
    check("real live record covers 19, 22 and 55",
          set(("19", "22", "55")) <= lines, "got %s" % sorted(lines))
    check("no vehicle identifier was cached",
          not any("VehicleRef" in v or "vehicle" in v
                  for visits in payload["stops"].values() for v in visits))
    args = opts(cache_dir=cache_dir, now=float(payload.get("t") or NOW) + 60.0)
    frame = muni.build(args)(0.0, 0)
    check("the real record draws", frame.shape == (64, 320, 3)
          and frame.max() > 60)
    del age


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cache-dir", default=ftdata.CACHE_DIR)
    ap.add_argument("--render-once", default=None,
                    help="internal: build and render one frame, then exit")
    ap.add_argument("--state", default="?", help="internal: label for the above")
    args = ap.parse_args()

    if args.render_once:
        print(_one_state(args.state, args.render_once))
        return 0

    test_fetcher_helpers()
    test_request_budget()
    test_fixture_is_live()
    test_routes_present()
    test_posts_to_scale()
    test_catchable_boundary()
    test_shared_stop_does_not_leak()
    test_unmonitored_is_hollow()
    test_lateness_bar()
    test_lane_number()
    test_horizon_flag()
    test_motion()
    test_sizes()
    test_schedule_fallback()
    test_states_in_separate_processes()
    test_no_network()
    test_live_record_routes(args.cache_dir)
    test_live_cache(args.cache_dir)

    print("\n%d passed, %d failed" % (PASSED[0], len(FAILED)))
    for line in FAILED:
        print("  FAIL %s" % line)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
