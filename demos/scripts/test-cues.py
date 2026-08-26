#!/usr/bin/env python3
"""Checks for ftsched's cues: the demos that belong at a time of day.

Cue logic is the kind that is only ever exercised by waiting, which is why
`due()` is a pure function of (cues, now, already-fired) with no clock in it.
Everything awkward about a wall clock can then be asked as a question instead
of waited for: a restart two minutes late, the second showing at 21:25, a
Tuesday-only cue on a Wednesday, the same minute arriving twenty times because
the frame loop is faster than a second.

The other half is the mechanism, and there is exactly one thing to prove about
it: **a cue does not move the carousel.** Pinning an index leaves the
rotation's offset alone, so when the cued minute is over the running order
resumes on precisely the effect it would have played had nobody cued anything.
That is asserted here by reading the mapping either side of a pin.

    $ python3 scripts/test-cues.py
"""

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import demoscene as ds
import ftsched

PASSED = [0]
FAILED = []


def check(name, ok, detail=""):
    if ok:
        PASSED[0] += 1
    else:
        FAILED.append(name)
    print("%-4s %s%s" % ("ok" if ok else "FAIL", name,
                         ("  -- " + detail) if detail and not ok else ""))


def at(y, m, d, hh, mm, ss=0):
    """A local struct_time, without going anywhere near the real clock."""
    return time.struct_time((y, m, d, hh, mm, ss,
                             time.struct_time(time.localtime()).tm_wday, 1, -1))


def on(y, m, d, hh, mm, ss=0):
    """As above, but with the weekday the calendar actually says."""
    stamp = time.mktime((y, m, d, hh, mm, ss, 0, 1, -1))
    return time.localtime(stamp)


def a_cue(**kw):
    kw.setdefault("name", "dolly")
    kw.setdefault("times", ["09:25", "21:25"])
    return ftsched.Cue(**kw)


def names(hits):
    return [(c.name, a) for c, a, _ in hits]


# --------------------------------------------------------------------------

def test_fires_on_its_minute():
    cue = a_cue()
    check("nothing at 09:24", not ftsched.due([cue], on(2026, 9, 1, 9, 24, 59), set()))
    check("fires at 09:25:00",
          names(ftsched.due([cue], on(2026, 9, 1, 9, 25, 0), set()))
          == [("dolly", "09:25")])
    check("still the same event at 09:25:59",
          names(ftsched.due([cue], on(2026, 9, 1, 9, 25, 59), set()))
          == [("dolly", "09:25")])


def test_fires_once():
    cue = a_cue()
    now = on(2026, 9, 1, 9, 25, 0)
    hits = ftsched.due([cue], now, set())
    fired = {hits[0][2]}
    check("does not fire twice in the same minute",
          not ftsched.due([cue], now, fired))
    check("does not fire again a minute later",
          not ftsched.due([cue], on(2026, 9, 1, 9, 26, 30), fired))
    check("fires again tomorrow",
          names(ftsched.due([cue], on(2026, 9, 2, 9, 25, 0), fired))
          == [("dolly", "09:25")])


def test_the_evening_showing_is_its_own_event():
    cue = a_cue()
    morning = ftsched.due([cue], on(2026, 9, 1, 9, 25, 0), set())[0][2]
    check("21:25 is not blocked by 09:25 having played",
          names(ftsched.due([cue], on(2026, 9, 1, 21, 25, 0), {morning}))
          == [("dolly", "21:25")])


def test_catch_up_window():
    cue = a_cue(window=600.0)
    check("a wall that came up two minutes late still plays it",
          ftsched.due([cue], on(2026, 9, 1, 9, 27, 0), set()))
    check("nine minutes late is still inside the window",
          ftsched.due([cue], on(2026, 9, 1, 9, 34, 0), set()))
    check("eleven minutes late is not",
          not ftsched.due([cue], on(2026, 9, 1, 9, 36, 0), set()))
    check("and it does not ambush anybody at noon",
          not ftsched.due([cue], on(2026, 9, 1, 12, 0, 0), set()))


def test_days():
    weekdays = a_cue(days=["mon", "tue", "wed", "thu", "fri"])
    # 2026-09-05 is a Saturday, 2026-09-07 a Monday.
    check("not on the Saturday",
          not ftsched.due([weekdays], on(2026, 9, 5, 9, 25, 0), set()))
    check("on the Monday",
          ftsched.due([weekdays], on(2026, 9, 7, 9, 25, 0), set()))
    check("'*' is every day",
          ftsched.due([a_cue()], on(2026, 9, 5, 9, 25, 0), set()))


def test_a_bad_time_is_dropped_not_fatal():
    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, "cues.json")
        with open(path, "w") as fh:
            json.dump({"version": 1, "cues": [
                {"name": "dolly", "at": ["09:25", "quarter past", "25:00"]},
                {"name": "ghost", "at": ["banana"]},
            ]}, fh)
        said = []
        cues = ftsched.load_cues(path, said.append)
        check("the good time survives its bad neighbours",
              [c.times for c in cues] == [["09:25"]], str([c.times for c in cues]))
        check("a cue with no usable time at all is dropped",
              [c.name for c in cues] == ["dolly"])
        check("and it says so", len(said) >= 2)
    check("no cue file at all is not an error",
          ftsched.load_cues("/nonexistent/cues.json", lambda m: None) == [])


def test_resolve_binds_a_copy():
    entries = ftsched.default_rotation()
    target = entries[1]
    target.enabled = False
    cue = a_cue(name=target.name, seconds=60.0)
    said = []
    kept = ftsched.resolve_cues([cue, a_cue(name="not-installed")],
                                entries, said.append)
    check("a cue naming nothing here is dropped with a sentence",
          len(kept) == 1 and said)
    check("the cue gets 60 seconds", kept[0].entry.seconds == 60.0)
    check("the rotation entry keeps its own length and stays switched off",
          target.seconds != 60.0 and not target.enabled)
    check("a cue cuts in and out", kept[0].entry.solo)


def test_a_pin_does_not_move_the_carousel():
    """The one thing the mechanism has to guarantee."""
    ap = ds.parser("test", fps=20)
    ftsched.add_arguments(ap)
    args = ap.parse_args([])
    entries = ftsched.default_rotation()
    rot = ftsched.Rotation(entries)
    import numpy as np
    builder = ftsched.Builder(rot, args, args.lead, lambda m: None,
                              np.zeros((args.height, args.width, 3), np.uint8))

    before = [builder.entry_at(i).name for i in range(12)]
    cue = ftsched.resolve_cues([a_cue(name=entries[3].name)], entries,
                               lambda m: None)[0]
    builder.pin_at(5, cue.entry)

    after = [builder.entry_at(i).name for i in range(12)]
    check("the pinned index plays the cue", builder.entry_at(5) is cue.entry)
    check("every other index is untouched",
          [n for i, n in enumerate(after) if i != 5]
          == [n for i, n in enumerate(before) if i != 5])
    check("the rotation's offset never moved", rot.offset == 0)

    builder.unpin_before(6)
    check("the pin is forgotten once the playhead is past it",
          [builder.entry_at(i).name for i in range(12)] == before)


def test_a_cued_entry_need_not_be_in_the_rotation():
    """The usual case: an entry that exists only to be cued."""
    ap = ds.parser("test", fps=20)
    ftsched.add_arguments(ap)
    args = ap.parse_args([])
    entries = ftsched.default_rotation()
    entries[2].enabled = False
    cue = ftsched.resolve_cues([a_cue(name=entries[2].name)], entries,
                               lambda m: None)[0]
    rot = ftsched.Rotation(entries)
    import numpy as np
    builder = ftsched.Builder(rot, args, args.lead, lambda m: None,
                              np.zeros((args.height, args.width, 3), np.uint8))
    check("a switched-off entry never comes up on its own",
          cue.name not in [builder.entry_at(i).name for i in range(40)])
    builder.pin_at(3, cue.entry)
    check("but a cue can still put it on the wall",
          builder.entry_at(3).name == cue.name)


def test_fired_keys_are_per_day_and_per_time():
    now = on(2026, 9, 1, 9, 25, 0)
    a = ftsched.fired_key("dolly", now, "09:25")
    b = ftsched.fired_key("dolly", now, "21:25")
    c = ftsched.fired_key("dolly", on(2026, 9, 2, 9, 25, 0), "09:25")
    check("morning and evening are different events", a != b)
    check("today and tomorrow are different events", a != c)


def main():
    for fn in [test_fires_on_its_minute, test_fires_once,
               test_the_evening_showing_is_its_own_event,
               test_catch_up_window, test_days,
               test_a_bad_time_is_dropped_not_fatal,
               test_resolve_binds_a_copy,
               test_a_pin_does_not_move_the_carousel,
               test_a_cued_entry_need_not_be_in_the_rotation,
               test_fired_keys_are_per_day_and_per_time]:
        try:
            fn()
        except Exception as exc:
            check(fn.__name__, False, "%s: %s" % (type(exc).__name__, exc))
    print("\n%d passed, %d failed" % (PASSED[0], len(FAILED)))
    for f in FAILED:
        print("  FAIL " + f)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
