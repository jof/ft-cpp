#!/usr/bin/env python3
"""The wall's status as a login banner, rendered ahead of time.

The obvious way to do this is a script in /etc/update-motd.d/ that asks the wall
how it is doing. On this Pi that costs two to three seconds -- interpreter
startup, an HTTP call, `systemctl is-active`, `vcgencmd` -- on a machine that is
already CPU-starved and, right now, voltage-throttled. Three seconds of staring
at nothing before every prompt is not a banner, it is a penalty.

So nothing is computed at login. ftctl renders this to a file whenever the state
it already polls actually changes, and the login banner is a `cat`. That reuses
the change detection written for MQTT: a repaint happens when the effect changes
or somebody moves the brightness, a few times a minute, and never on a timer for
its own sake.

The expensive facts -- systemctl, vcgencmd -- are refreshed at most once a minute
and cached, so a burst of effect changes does not drag a subprocess along behind
each one.

The picture is the wall itself: ft_server's `snapshot` hands back the composite
as raw RGB, and it is box-averaged down and drawn in half-blocks at the wall's
own 5:1 aspect. It used to be a stock preview clip of whichever effect was
playing, which was cheap and looked right and was capable of being badly wrong
-- the daliclock preview was recorded at 19:51 one evening, so anybody logging
in while the clock was up saw a wall confidently displaying 7pm. A picture of
the wall cannot drift from the wall.

Two things the frame is not. It is the *content*, so a blanked panel still has
one: `blanked` comes back in the same reply and a dark wall is drawn as a ghost
of what is behind it, captioned as such, rather than as a lit picture of a wall
that is off. And it is only as fresh as the last repaint, so unlike everything
else here the picture does get a timer -- MOTD_PICTURE_TTL, below. A frame from
a few seconds ago is a capture; a frame from twenty minutes ago is a fib. The
caption carries its age either way.

The data cache gets a line too, because a dead feed is invisible from the wall:
the panel that wanted it draws its no-data card and keeps cycling, and nobody
finds out until they read a K index that stopped moving on Tuesday. What that
line must not do is cost anything. The ages come from a `stat` and the first
few bytes of each record rather than from `ftdata.load()`: `load()` parses the
whole file, and the tide curve is a thousand samples of JSON to recover one
float that `_store` wrote at the top, next to a mtime it set in the same
rename. Nothing here imports a network module, which is the same promise
`ftdata.load()` makes and for the same reason. The one fact that needs a
subprocess -- when systemd will next run the fetcher -- is asked for in
`Extras`, once a minute, alongside the other subprocesses.

Downsampling is done in Python rather than with Pillow on purpose: Pillow costs
the better part of a second to import on this Pi, against a few tens of
milliseconds of arithmetic for 20k pixels a couple of times a minute.

It reaches a login through /etc/motd, which is a symlink to the rendered file.
That is the one path pam_motd takes on every interactive session
(`session optional pam_motd.so noupdate`). The /etc/update-motd.d/ route looks
like the obvious home for this and is a trap here: pam_motd on this Debian does
not actually run `run-parts` for sshd sessions, so a script there is never
executed. The symlink also fails well -- ftctl's RuntimeDirectory goes away with
the daemon, so a wall with no ftctl prints nothing rather than something wrong.

Run by hand to see it, or to check it after editing:

  python3 ftmotd.py                 # to stdout
  python3 ftmotd.py --out /run/ft-motd/banner.ansi
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

# The cache reader. It is imported for its registry and its TTLs, not to fetch
# anything: ftdata pulls in nothing but the standard library at import time and
# keeps urllib inside the fetch path, so this costs a few milliseconds and no
# sockets. A wall without it still gets a banner, saying so.
try:
    import ftdata
except Exception:                                            # noqa: BLE001
    ftdata = None

# The panel's own palette, so the terminal and the web UI look like one system.
AMBER = (255, 176, 58)
GREEN = (69, 209, 122)
GREY = (136, 145, 165)
RED = (255, 92, 92)
WHITE = (232, 236, 244)

ART_WIDTH = 62                    # columns
ART_ROWS = ART_WIDTH // 10        # two pixels per row, so W/(2*ROWS) == 5:1
EXTRAS_TTL = 60.0                 # seconds to cache systemctl/vcgencmd
SERVICES = ("ft_server", "ftsched", "ftctl", "nginx")
DATA_TIMER = "ftdata.timer"       # what refills the data cache

# How much of a record to read to find its `fetched_at`. _store writes the
# envelope first -- name, fetched_at, source, ttl -- so the stamp is inside the
# first hundred bytes of anything this version wrote, and a record that does
# not look like an envelope at all is reported as unreadable rather than
# silently believed.
DATA_HEAD_BYTES = 256
DATA_STAMP = re.compile(rb'"fetched_at"\s*:\s*(-?[0-9][0-9.eE+-]*)')
# At most this many lines naming products in trouble. Six today, and the
# registry grows by a line each time somebody adds a station; a banner that can
# push the whole wall picture off a short terminal is worse than a count.
DATA_TROUBLE_LINES = 3

# How stale the picture may get before it is worth a repaint on its own. The
# rest of this file repaints only on a change a person would notice; a frame of
# the wall goes out of date quietly, all by itself, which is the one thing here
# that actually justifies a timer.
MOTD_PICTURE_TTL = 30.0
# What a blanked panel is drawn at. Not zero, because six rows of pure black
# reads as a broken banner rather than a dark wall, and the frame underneath is
# worth seeing; not anywhere near full, because the wall is off and the picture
# must not suggest otherwise. The caption is what actually says so.
BLANKED_GHOST = 0.14


def rgb(colour, text, bold=False):
    return "\x1b[%s38;2;%d;%d;%dm%s\x1b[0m" % (
        "1;" if bold else "", colour[0], colour[1], colour[2], text)


def bar(fraction, width, colour):
    """Rounded down, so a full bar means full and nothing else does."""
    filled = int(max(0.0, min(1.0, fraction)) * width)
    return rgb(colour, "█" * filled) + rgb(GREY, "░" * (width - filled))


# -- the expensive facts ---------------------------------------------------

def _timespan(value):
    """systemd's '1h 11min 5.387316s' -> seconds. None if it is not one.

    systemd 247 pretty-prints the USec properties that newer versions hand back
    as raw integers, so both spellings have to be understood: a bare number is
    microseconds, anything else is a run of value-and-unit pairs. 'infinity',
    'n/a' and the empty string all mean there is no answer.
    """
    value = (value or "").strip()
    if not value or value in ("infinity", "n/a", "0"):
        return None
    if value.isdigit():
        return float(value) / 1e6
    units = {"us": 1e-6, "ms": 1e-3, "s": 1.0, "sec": 1.0, "second": 1.0,
             "seconds": 1.0, "m": 60.0, "min": 60.0, "h": 3600.0, "hr": 3600.0,
             "d": 86400.0, "day": 86400.0, "days": 86400.0, "w": 604800.0,
             "week": 604800.0, "weeks": 604800.0, "month": 2629800.0,
             "months": 2629800.0, "y": 31557600.0, "year": 31557600.0,
             "years": 31557600.0}
    total = None
    for number, unit in re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*([a-z]+)", value):
        if unit not in units:
            return None
        total = (total or 0.0) + float(number) * units[unit]
    return total


def _uptime():
    """Seconds since boot, or None. A file read, deliberately not a subprocess."""
    try:
        with open("/proc/uptime") as fh:
            return float(fh.read().split()[0])
    except Exception:                                        # noqa: BLE001
        return None


class Extras(object):
    """systemctl and vcgencmd, at most once a minute."""

    def __init__(self, ttl=EXTRAS_TTL):
        self.ttl = ttl
        self._at = 0.0
        self.services = []
        self.throttled_now = False
        self.throttled_ever = False
        self.throttled_raw = None
        # ftdata.timer: whether it is installed and running, and when it fires
        # next. None everywhere means nobody has been able to ask -- no
        # systemctl, or a run that failed -- which is not the same as a timer
        # that is off, and the banner says neither in that case.
        self.timer_load = None
        self.timer_active = None
        self.timer_next = None            # epoch seconds

    def stale(self, now=None):
        return (now or time.time()) - self._at >= self.ttl

    def refresh(self):
        self._at = time.time()
        try:
            out = subprocess.run(["systemctl", "is-active"] + list(SERVICES),
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL,
                                 timeout=5).stdout.decode().split()
        except Exception:
            out = []
        out += ["?"] * (len(SERVICES) - len(out))
        self.services = list(zip(SERVICES, out))
        self._refresh_timer()

        try:
            raw = subprocess.run(["vcgencmd", "get_throttled"],
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL,
                                 timeout=5).stdout.decode()
            value = int(raw.strip().split("=")[1], 16)
        except Exception:
            return
        # Low bits are live; the 0x10000 range is "has happened since boot",
        # which deserves a quieter mention than something happening now.
        self.throttled_raw = value
        self.throttled_now = bool(value & 0x7)
        self.throttled_ever = bool(value & 0x70000)

    def _refresh_timer(self):
        """When systemd will next refill the data cache. One subprocess.

        This lives up here with the other expensive facts rather than beside
        the cache reading in `render`, which runs several times a minute: the
        answer changes once every fifteen, and a banner that forks systemctl on
        every repaint is the thing this whole module exists to avoid.
        """
        self.timer_load = self.timer_active = self.timer_next = None
        try:
            out = subprocess.run(
                ["systemctl", "show", DATA_TIMER,
                 "--property=LoadState", "--property=ActiveState",
                 "--property=NextElapseUSecRealtime",
                 "--property=NextElapseUSecMonotonic"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=5).stdout.decode()
        except Exception:                                    # noqa: BLE001
            return
        props = dict(line.split("=", 1)
                     for line in out.splitlines() if "=" in line)
        self.timer_load = props.get("LoadState") or None
        self.timer_active = props.get("ActiveState") or None

        # A monotonic timer -- OnUnitActiveSec, which is what ftdata.timer uses
        # -- has no realtime elapse to report, so the answer comes back as a
        # time since boot and is turned into a wall-clock instant here. Storing
        # the instant rather than the remaining seconds means a banner painted
        # forty seconds later still counts down correctly.
        realtime = _timespan(props.get("NextElapseUSecRealtime"))
        monotonic = _timespan(props.get("NextElapseUSecMonotonic"))
        up = _uptime()
        if realtime and realtime > 1e9:      # raw µs since the epoch
            self.timer_next = realtime
        elif monotonic is not None and up is not None:
            self.timer_next = time.time() - up + monotonic


# -- the data cache --------------------------------------------------------

def _short_age(seconds):
    """ftdata's phrasing when it is here, the same shape when it is not."""
    if ftdata is not None:
        return ftdata.describe_age(seconds)
    if seconds < 5400:
        return "%dm" % int(seconds / 60)
    return "%dh" % int(seconds / 3600)


def _record_age(path, now):
    """(kind, age) for one cached record. kind: 'ok', 'absent' or 'bad'.

    Reads the head of the file and its mtime, and nothing else. `fetched_at` is
    the second key `_store` writes and the file is renamed into place in the
    same breath, so the stamp is both inside the first hundred bytes and within
    milliseconds of the mtime -- and the banner reports ages in minutes.
    Insisting on the stamp rather than falling back to the mtime is what makes
    a truncated record show up as unreadable instead of as fresh, which is what
    the demo reading it with `load()` will make of it too.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(DATA_HEAD_BYTES)
            mtime = os.fstat(fh.fileno()).st_mtime
    except OSError:
        return "absent", None                 # missing, or a directory gone
    except Exception:                                        # noqa: BLE001
        return "bad", None
    if not head.lstrip().startswith(b"{"):
        return "bad", None
    match = DATA_STAMP.search(head)
    if not match:
        return "bad", None
    try:
        stamp = float(match.group(1))
    except ValueError:
        stamp = mtime
    return "ok", max(0.0, now - stamp)


def data_states(cache_dir=None, now=None):
    """[(name, state, age)] for every registered product, or None with no ftdata.

    state is 'fresh', 'stale', 'absent' or 'bad'; age is seconds, or None when
    there was nothing to age. Freshness is each product's own `ttl` and not one
    threshold for all of them: a tide prediction is still true two days later
    and a K index is not worth reading after ninety minutes.

    Never raises. A missing cache directory, a file with the wrong permissions,
    a record from a future version -- each is a word on a line, because a login
    banner that throws is a login nobody can read.
    """
    if ftdata is None:
        return None
    now = now or time.time()
    states = []
    for name in sorted(ftdata.PRODUCTS):
        try:
            # record_path() rather than path_for(), because a volatile product
            # writes its record to the /run tmpfs beside the image sidecars
            # instead of to the card, and this line would otherwise report the
            # liveliest thing on the wall as permanently absent. It returns the
            # file load() would actually read, or None when there is none --
            # which _record_age() reads as absent, correctly.
            kind, age = _record_age(
                ftdata.record_path(name, cache_dir) or
                ftdata.path_for(name, cache_dir), now)
        except Exception:                                    # noqa: BLE001
            kind, age = "bad", None
        if kind != "ok":
            states.append((name, kind, None))
        elif ftdata.is_fresh(name, age):
            states.append((name, "fresh", age))
        else:
            states.append((name, "stale", age))
    return states


def _timer_note(extras, now):
    """What systemd said about ftdata.timer, from the once-a-minute cache."""
    if extras.timer_load == "not-found":
        return rgb(RED, "  %s not installed" % DATA_TIMER)
    if extras.timer_active == "failed":
        return rgb(RED, "  timer failed")
    if extras.timer_active and extras.timer_active not in ("active",
                                                           "activating"):
        return rgb(AMBER, "  timer %s" % extras.timer_active)
    if extras.timer_next:
        left = extras.timer_next - now
        if left <= 0:
            return rgb(GREY, " · next due")
        return rgb(GREY, " · next in %s" % _short_age(left))
    return ""                       # nobody could ask; do not guess out loud


def data_lines(extras, states, now=None, cache_dir=None):
    """The data-cache line, and continuation lines naming what is wrong.

    Two things a person wants at a glance: is anything arriving at all, and
    which feed died -- because one dead endpoint is the usual failure and the
    panel that wanted it is showing a no-data card right now with no way to
    tell from across the room.
    """
    now = now or time.time()
    label = rgb(WHITE, "data     ")
    indent = " " * 11                       # under the label, past the dot
    note = _timer_note(extras, now)

    if states is None:
        return [rgb(AMBER, "●") + " " + label +
                rgb(AMBER, "no ftdata.py here, so no cache to read") + note]
    if not states:
        return [rgb(AMBER, "●") + " " + label +
                rgb(AMBER, "no products registered") + note]

    total = len(states)
    fresh = sum(1 for _, state, _ in states if state == "fresh")
    ages = [age for _, _, age in states if age is not None]
    colour = GREEN if fresh == total else (AMBER if fresh else RED)

    head = (rgb(colour, "●") + " " + label +
            bar(fresh / float(total), 12, colour) +
            rgb(GREY, " %d/%d fresh" % (fresh, total)))
    if ages:
        head += rgb(GREY, "  newest %s" % _short_age(min(ages)))
    else:
        # Only asked when there is nothing at all, so this is not a stat per
        # product per repaint. It is worth asking then: a cache directory that
        # does not exist is the documented way ftdata.service fails to start,
        # and it wants a different fix from a fetcher that is merely failing.
        where = cache_dir or (ftdata.CACHE_DIR if ftdata else None)
        if where and not os.path.isdir(where):
            head += rgb(RED, "  no %s" % where)
        else:
            head += rgb(RED, "  nothing cached")
    lines = [head + note]

    # Worst first: absent and unreadable before merely old, and the oldest of
    # the stale ones ahead of the rest, so a truncated list drops the products
    # least worth naming.
    rank = {"absent": 0, "bad": 1, "stale": 2}
    trouble = sorted((s for s in states if s[1] != "fresh"),
                     key=lambda s: (rank[s[1]], -(s[2] or 0.0), s[0]))

    cells = []
    for name, state, age in trouble:
        if state == "stale":
            tail = " " + _short_age(age)
            cells.append((rgb(AMBER, name) + rgb(GREY, tail),
                          len(name) + len(tail)))
        elif state == "absent":
            cells.append((rgb(RED, name) + rgb(GREY, " absent"),
                          len(name) + 7))
        else:
            cells.append((rgb(RED, name) + rgb(GREY, " unreadable"),
                          len(name) + 11))

    # Wrapped by hand against the width the picture already sets, because the
    # registry grows -- another tide station is one line in ftdata.py -- and a
    # status that wraps in the terminal reads as a broken banner.
    avail = ART_WIDTH - len(indent)
    rows, row, used = [], [], 0
    for i, (text, width) in enumerate(cells):
        step = width if not row else width + 2
        if row and used + step > avail:
            rows.append(row)
            if len(rows) >= DATA_TROUBLE_LINES:
                rows[-1].append(rgb(GREY, "+%d more" % (len(cells) - i)))
                row = None
                break
            row, used, step = [], 0, width
        row.append(text)
        used += step
    if row:
        rows.append(row)
    for row in rows:
        lines.append(indent + "  ".join(row))
    return lines


# -- the picture -----------------------------------------------------------

def downsample(pixels, width, height, out_w, out_h):
    """Box-average raw RGB down to out_w x out_h, as a grid of (r, g, b).

    Averaging rather than sampling, because the wall is mostly small bright
    things on black: one sample per cell drops a 3-pixel-wide clock hand
    entirely and turns a starfield into an empty box, while the average keeps a
    dim smudge where the light actually is.

    Every input pixel is visited exactly once, and the bounds are computed so
    that the cells tile the frame with no gaps and no overlap even when the
    sizes do not divide evenly.
    """
    grid = []
    for oy in range(out_h):
        y0 = oy * height // out_h
        y1 = max(y0 + 1, (oy + 1) * height // out_h)
        row = []
        for ox in range(out_w):
            x0 = ox * width // out_w
            x1 = max(x0 + 1, (ox + 1) * width // out_w)
            r = g = b = 0
            for y in range(y0, y1):
                base = y * width * 3
                for i in range(base + x0 * 3, base + x1 * 3, 3):
                    r += pixels[i]
                    g += pixels[i + 1]
                    b += pixels[i + 2]
            n = (y1 - y0) * (x1 - x0)
            row.append((r // n, g // n, b // n))
        grid.append(row)
    return grid


def art(snap):
    """Half-block render of the frame ft_server just handed back.

    Returns (picture, caption) or (None, None). The caption is part of the job:
    the same pixels mean different things depending on whether the panel is
    lit, and the picture cannot say which on its own.
    """
    if not snap or not snap.get("pixels"):
        return None, None
    width, height = snap.get("width"), snap.get("height")
    if not width or not height:
        return None, None
    try:
        grid = downsample(snap["pixels"], width, height,
                          ART_WIDTH, ART_ROWS * 2)
    except (IndexError, ZeroDivisionError, TypeError):
        return None, None                    # a frame we cannot make sense of

    blanked = snap.get("blanked")
    scale = BLANKED_GHOST if blanked else 1.0

    rows = []
    for row in range(ART_ROWS):
        cells = []
        for col in range(ART_WIDTH):
            top = grid[row * 2][col]
            low = grid[row * 2 + 1][col]
            # An upper half-block with the foreground painting the top pixel and
            # the background the bottom: one cell, two pixels, square aspect.
            cells.append("\x1b[38;2;%d;%d;%dm\x1b[48;2;%d;%d;%dm▀"
                         % (int(top[0] * scale), int(top[1] * scale),
                            int(top[2] * scale),
                            int(low[0] * scale), int(low[1] * scale),
                            int(low[2] * scale)))
        rows.append("".join(cells) + "\x1b[0m")

    age = max(0.0, time.time() - (snap.get("at") or 0.0))
    when = "just now" if age < 2.0 else "%ds ago" % int(age)
    if blanked:
        caption = ("↑ the panel is dark · this is the frame behind the blank, "
                   "dimmed · %s" % when)
    else:
        caption = "↑ the panel itself, %s · %d×%d" % (when, width, height)
    return "\n".join(rows), caption


# -- the banner ------------------------------------------------------------

def render(display, sched, extras, urls, snap=None, cache_dir=None):
    now = (sched or {}).get("now") or {}
    health = (sched or {}).get("health") or {}
    demo = now.get("name")
    out = []
    pad = "  "

    title = "BETELGEUSE"
    letters = []
    for i, ch in enumerate(title):
        # Amber into a warmer red across the word: roughly what the wall looks
        # like with sunset on it.
        f = i / float(len(title) - 1)
        letters.append(rgb((255, int(176 - 90 * f), int(58 + 20 * f)), ch, True))
    size = "%d×%d" % (display["width"], display["height"]) \
        if display and display.get("width") else "320×64"
    out.append("")
    out.append(pad + " ".join(letters) + "   " +
               rgb(GREY, size + " · flaschen taschen"))
    out.append("")

    picture, caption = art(snap)
    if picture:
        for line in picture.split("\n"):
            out.append(pad + line)
        out.append(pad + rgb(GREY, caption))
        out.append("")

    if display is None:
        out.append(pad + rgb(RED, "●") + " " + rgb(WHITE, "wall     ") +
                   rgb(RED, "the display server is not answering"))
    else:
        pct = display["brightness"]
        lit = rgb(GREY, "blanked") if display["blanked"] else rgb(GREEN, "on")
        dot = rgb(GREY if display["blanked"] else GREEN, "●")
        out.append(pad + dot + " " + rgb(WHITE, "wall     ") + lit + "  " +
                   bar(pct / 100.0, 12, AMBER) + rgb(GREY, " %d%%" % pct) +
                   ("" if display.get("dimmer") else rgb(GREY, "  no dimmer")))

    if sched is None:
        out.append(pad + rgb(RED, "●") + " " + rgb(WHITE, "playing  ") +
                   rgb(RED, "the scheduler is not answering"))
    else:
        rotation = sched.get("rotation") or []
        live = sum(1 for e in rotation if e.get("enabled", True))
        actual = health.get("actual_fps") or 0.0
        target = health.get("target_fps") or 0.0
        dropped = health.get("dropped_packets") or 0
        paused = sched.get("paused")
        fps_colour = GREEN if target and actual >= target * 0.9 else AMBER
        out.append(
            pad + rgb(GREY if paused else GREEN, "●") + " " +
            rgb(WHITE, "playing  ") + rgb(AMBER, demo or "—", True) +
            rgb(GREY, "  %d/%d  " % ((now.get("position") or 0) + 1, live)) +
            bar((now.get("elapsed") or 0.0) / (now.get("duration") or 1.0),
                12, WHITE) +
            "  " + rgb(fps_colour, "%.0f/%.0f fps" % (actual, target)) +
            (rgb(GREY, " · paused") if paused else "") +
            (rgb(RED, " · %d dropped" % dropped) if dropped else ""))

    if extras.services:
        cells = [rgb(GREEN if state == "active" else RED, name)
                 for name, state in extras.services]
        out.append(pad + rgb(GREY, "●") + " " + rgb(WHITE, "services ") +
                   rgb(GREY, " ").join(cells))

    # Whatever happens in here, it happens as text. render() is called from a
    # daemon and its output is somebody's only way back in.
    try:
        for line in data_lines(extras, data_states(cache_dir),
                               cache_dir=cache_dir):
            out.append(pad + line)
    except Exception as exc:                                 # noqa: BLE001
        out.append(pad + rgb(RED, "●") + " " + rgb(WHITE, "data     ") +
                   rgb(RED, "cannot read the data cache") +
                   rgb(GREY, "  %s" % exc))

    if extras.throttled_now:
        out.append(pad + rgb(RED, "⚠", True) + " " +
                   rgb(WHITE, "power    ") +
                   rgb(RED, "under-voltage and throttling right now", True) +
                   rgb(GREY, "  0x%x · ~/docs/hardware.md"
                       % extras.throttled_raw))
    elif extras.throttled_ever:
        out.append(pad + rgb(AMBER, "⚠") + " " + rgb(WHITE, "power    ") +
                   rgb(AMBER, "under-voltage has occurred since boot") +
                   rgb(GREY, "  0x%x" % extras.throttled_raw))

    out.append("")
    if urls.get("lan"):
        line = pad + rgb(GREY, "  reach  ") + rgb(AMBER, urls["lan"])
        if urls.get("tailnet"):
            line += rgb(GREY, "   tailnet ") + rgb(GREY, urls["tailnet"])
        out.append(line)
    out.append(pad + rgb(GREY, "  docs   ") + rgb(WHITE, "~/docs/README.md") +
               rgb(GREY, "   control  ") +
               rgb(WHITE, "python3 ~/ft-cpp/tools/ftc.py get"))
    # When this was painted. It is only repainted on a change, so a couple of
    # minutes old is normal and healthy -- but if ftctl has died, /etc/motd
    # dangles and nothing prints at all, which is the louder signal.
    out.append(pad + rgb(GREY, "  as of  " + time.strftime("%H:%M:%S")))
    out.append("")
    return "\n".join(out) + "\n"


def write(path, text):
    """Atomic, so a login can never read half a banner."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(text)
    os.chmod(tmp, 0o644)                  # pam_motd reads this as root
    os.replace(tmp, path)


class Writer(object):
    """An ftctl listener: repaint when what a person would see has changed."""

    def __init__(self, path, urls, snapshot_fn=None,
                 picture_ttl=MOTD_PICTURE_TTL, cache_dir=None):
        self.path = path
        self.urls = urls
        self.cache_dir = cache_dir
        self.snapshot_fn = snapshot_fn
        self.picture_ttl = picture_ttl
        self.extras = Extras()
        self._key = None
        self._painted = 0.0

    def update(self, display, sched):
        now = (sched or {}).get("now") or {}
        key = (display and display.get("brightness"),
               display and display.get("blanked"),
               now.get("name"), (sched or {}).get("paused"),
               display is None, sched is None)
        refresh_extras = self.extras.stale()
        # The picture ages on its own, with nothing in `key` to show it. Without
        # this, a long effect would leave a banner showing its opening frame for
        # as long as it ran, which is the class of bug that got the stock
        # previews replaced in the first place.
        stale_picture = (self.snapshot_fn is not None and
                         time.time() - self._painted >= self.picture_ttl)
        if key == self._key and not refresh_extras and not stale_picture:
            return False
        if refresh_extras:
            self.extras.refresh()

        snap = None
        if self.snapshot_fn is not None:
            try:
                snap = self.snapshot_fn()
            except Exception as exc:      # a missing picture is not a reason
                sys.stderr.write("ftmotd: no snapshot (%s)\n" % exc)

        self._key = key
        self._painted = time.time()
        write(self.path, render(display, sched, self.extras, self.urls, snap,
                                self.cache_dir))
        return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--ftctl", default="http://127.0.0.1:8082/api/display")
    ap.add_argument("--socket", default="/run/ft/control.sock",
                    help="ft_server's control socket, for the picture; '' to "
                         "render without one")
    ap.add_argument("--lan", default="http://betelgeuse.local/")
    ap.add_argument("--tailnet", default="")
    ap.add_argument("--data-cache", default=None,
                    help="ftdata cache directory; default is ftdata's own")
    ap.add_argument("--out", default=None, help="write here instead of stdout")
    args = ap.parse_args()

    import urllib.request
    try:
        with urllib.request.urlopen(args.ftctl, timeout=2.0) as fh:
            state = json.loads(fh.read().decode("utf-8"))
    except Exception:
        state = {"display": None, "scheduler": None}

    # Straight to the control socket rather than through ftctl: ftctl's HTTP API
    # deliberately serves a cache and 61 kB of pixels do not belong in it. The
    # import is here rather than at the top because ftctl imports this module.
    snap = None
    if args.socket:
        try:
            import ftctl
            snap = ftctl.Control(args.socket).snapshot()
        except Exception as exc:
            sys.stderr.write("ftmotd: no snapshot (%s)\n" % exc)

    extras = Extras()
    extras.refresh()
    text = render(state.get("display"), state.get("scheduler"), extras,
                  {"lan": args.lan, "tailnet": args.tailnet}, snap,
                  args.data_cache)
    if args.out:
        write(args.out, text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
