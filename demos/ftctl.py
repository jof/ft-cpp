#!/usr/bin/env python3
"""The wall's global state: on/off, brightness, wipe -- and its way into MQTT.

ft_server owns the panel and composites every client onto it, so how bright the
wall is and whether it is showing anything belong to it rather than to any one
client. It exposes those on a unix socket as lines of text. This is the only
thing that speaks that protocol; everything else comes through here.

Why a daemon of its own rather than a few routes inside ftsched:

  The whole point of a global off switch is that it works when the rest is not.
  ftsched drives the rotation on a frame deadline and is BindsTo=ft_server, so
  it restarts whenever the server does; if "turn the wall off" lived in it, the
  switch would be missing exactly when somebody is trying to deal with a
  misbehaving wall. This has no dependency on ftsched at all: it reads it when
  it is there, reports it as absent when it is not, and controls the display
  either way.

  It is also the thing that remembers. ft_server deliberately does not persist
  brightness -- after it drops privileges it can write nowhere, and a dragged
  slider is dozens of commands a second, which is not something to point at an
  SD card. So desired state lives here, and gets re-applied when the generation
  in `get` changes, which is how a server restart is noticed.

Reads are served from a cache refreshed on a timer, never by doing a socket
round trip inside a request. ftsched's web API made the same promise for the
same reason: a phone on bad wifi must not be able to stall anything by holding
a request open. Writes do go straight through, with a timeout, and update the
cache optimistically so a slider does not snap back under the finger.

MQTT is optional. Without paho-mqtt installed this is still a working HTTP
control API; with it, the wall appears in Home Assistant as one device -- a
light for the display itself, and separate entities for the rotation, so that
"off" and "paused" stay different things. See --mqtt-host.

Run:
  python3 ftctl.py --socket /run/ft/control.sock --listen 127.0.0.1:8082
  python3 ftctl.py --mqtt-host mqtt.lan --mqtt-user ha --mqtt-pass ...
"""

import argparse
import json
import os
import select
import socket
import struct
import sys
import threading
import time
import urllib.error
import urllib.request
import zlib

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_HERE = os.path.dirname(os.path.abspath(__file__))

# One command per connection, so these are per-command and not per-session.
SOCKET_TIMEOUT = 2.0
SCHED_TIMEOUT = 2.0
POLL_SECONDS = 1.0

# A snapshot header is five short lines; anything longer is not one, and saying
# so keeps a confused server from being able to make us buffer without end.
MAX_SNAPSHOT_HEADER = 4096
# 320x64 is 61 kB. The ceiling is for a garbled length field, not for a panel
# anybody actually has: refusing to allocate on it is the whole point.
MAX_SNAPSHOT_BYTES = 8 << 20

# How old the picture Home Assistant is shown may be. HA polls an image entity
# about once a second; this decouples what it costs us from how often it asks,
# and from how many dashboards are asking.
THUMBNAIL_TTL = 2.0
# Deflate level for that PNG. A wall frame is mostly black and compresses hard
# whatever we ask for, so this buys speed with bytes nobody misses: level 1 on a
# 320x64 frame is several times quicker than level 6 and lands within a few kB.
PNG_LEVEL = 1
_BLANKED_TABLE = None

# -- the live stream --------------------------------------------------------
#
# Measured on betelgeuse, which is what these defaults are chosen against: a
# snapshot round trip is 4.2 ms, encode_png is 5.2 ms, and the PNG lands between
# 2.7 and 8.4 kB depending on how much of the wall is lit. So one viewer at 20
# fps is about 1.1 Mbps and 0.43 of a core -- against a wifi link that tops out
# near 12 Mbps and three cores that are not the isolated one driving the panel.
#
# 20 fps because that is what ftsched renders at; asking for more would only
# resend frames the wall never had.
LIVE_FPS = 20
# Two, and the reason is the radio rather than the CPU: the frame is encoded once
# however many people are watching, so a second viewer costs one more sendall().
# What it does cost is another 1.1 Mbps out of a 2.4 GHz SDIO link whose airtime
# the wall's own traffic is not competing for but the shop's everything else is.
LIVE_MAX_VIEWERS = 2
LIVE_BOUNDARY = "ftframe"
# A viewer that cannot absorb a 7 kB frame in this long is not watching a wall,
# it is holding a socket open. Dropping it is how one bad link stays one bad
# link; without it a dead client parks a viewer slot until TCP gives up on it.
LIVE_SEND_TIMEOUT = 10.0
# How long a viewer waits for a new frame before writing two bytes at its client
# just to find out whether anyone is still there.
#
# This exists because of a still wall. A viewer only discovers its client has
# gone by writing to it, and it only writes when there is a new frame -- so on a
# wall that is not changing, a browser that closed an hour ago would hold a
# viewer slot and keep the producer running, forever, with nobody watching. The
# probe is a bare CRLF between multipart parts, which every client ignores and a
# closed socket refuses.
LIVE_IDLE_PROBE = 2.0


def blanked_table():
    """Byte map for dimming a blanked frame, cached, from ftmotd's own constant.

    One definition of how dark "dark" looks, so Home Assistant and a terminal
    cannot disagree about it. Imported lazily and in this direction only --
    ftctl already reaches for ftmotd to render the banner, and ftmotd importing
    ftctl at module scope would load a second copy of this module whenever
    ftctl is the one being run as a script.

    A 256-entry table because translate() is then one pass in C; a Python loop
    over 61 kB, twice a second, is not free on this Pi.
    """
    global _BLANKED_TABLE
    if _BLANKED_TABLE is None:
        import ftmotd
        _BLANKED_TABLE = bytes(int(i * ftmotd.BLANKED_GHOST)
                               for i in range(256))
    return _BLANKED_TABLE


def encode_png(width, height, rgb, level=PNG_LEVEL):
    """A truecolour PNG from raw RGB, using nothing but the standard library.

    Pillow would do this too, and is what the baked previews still go through,
    but it costs the better part of a second to import on this Pi and this path
    wants to be quick and dependency-free. A PNG is four chunks and a CRC; the
    per-row filter byte is 0 (None) throughout, because deflate already does
    very well on a frame that is mostly black and picking filters per row would
    cost more than it saves here.
    """
    stride = width * 3
    raw = bytearray()
    for y in range(height):
        raw.append(0)                        # filter: None
        raw += rgb[y * stride:(y + 1) * stride]

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))

    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(bytes(raw), level)) +
            chunk(b"IEND", b""))

# Brightness the wall reports in percent, 1..100. Home Assistant lights want
# 0..255. Converting in one place, and rounding so that a round trip through
# HA does not drift a percent at a time.
HA_BRIGHTNESS_SCALE = 255


def pct_to_ha(percent):
    return max(1, min(HA_BRIGHTNESS_SCALE,
                      int(round(percent * HA_BRIGHTNESS_SCALE / 100.0))))


def ha_to_pct(value):
    return max(1, min(100, int(round(value * 100.0 / HA_BRIGHTNESS_SCALE))))


class Control(object):
    """The ft_server control socket. One connection per command."""

    def __init__(self, path):
        self.path = path

    def _round_trip(self, line):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(SOCKET_TIMEOUT)
        try:
            sock.connect(self.path)
            sock.sendall((line + "\n").encode("ascii"))
            chunks = []
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks).decode("ascii", "replace")
        finally:
            sock.close()

    def get(self):
        """Current display state as a dict, or None if the server is not there.

        Absent is a normal condition -- the server restarts, or was started
        without --control-socket -- so it is reported rather than raised.
        """
        try:
            reply = self._round_trip("get")
        except (socket.error, OSError):
            return None
        state = {}
        for row in reply.splitlines():
            if not row.strip():
                continue
            key, _, value = row.partition(" ")
            try:
                state[key] = int(value)
            except ValueError:
                state[key] = value
        if "brightness" not in state:
            return None            # not a reply we understand
        return {
            "brightness": state["brightness"],
            "blanked": bool(state.get("blanked")),
            "dimmer": bool(state.get("dimmer")),
            "width": state.get("width"),
            "height": state.get("height"),
            "generation": state.get("generation"),
        }

    def command(self, line):
        """(ok, message). ok is False both for a refusal and for no server."""
        try:
            reply = self._round_trip(line).strip()
        except (socket.error, OSError) as exc:
            return False, "display server unreachable: %s" % exc
        if reply == "ok":
            return True, ""
        return False, reply[4:].strip() if reply.startswith("err ") else reply

    def snapshot(self):
        """The composite as raw RGB, with the state that goes with it, or None.

        Its own round trip rather than a field in `get`: this is 61 kB, `get`
        runs once a second, and the only caller repaints a banner a few times a
        minute. Paying for the pixels on every poll to have them ready for the
        rare reader would be exactly backwards.

        `blanked` and `brightness` come back in the same reply as the frame,
        because they are what decides whether the frame is being shown at all
        and pairing pixels with separately-read state is how a status display
        ends up cheerfully rendering a bright picture of a dark wall.
        """
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(SOCKET_TIMEOUT)
        try:
            sock.connect(self.path)
            sock.sendall(b"snapshot\n")
            buf = b""
            while b"\n\n" not in buf:
                chunk = sock.recv(4096)
                if not chunk:
                    return None                  # hung up before the header
                buf += chunk
                if len(buf) > MAX_SNAPSHOT_HEADER:
                    return None
            header, _, body = buf.partition(b"\n\n")
            lines = header.decode("ascii", "replace").splitlines()
            fields = lines[0].split() if lines else []
            # snapshot rgb24 <width> <height> <bytes>
            if len(fields) != 5 or fields[0] != "snapshot" \
                    or fields[1] != "rgb24":
                return None                      # an older server, or an error
            width, height, count = (int(fields[2]), int(fields[3]),
                                    int(fields[4]))
            if width <= 0 or height <= 0 or count != width * height * 3 \
                    or count > MAX_SNAPSHOT_BYTES:
                return None
            while len(body) < count:
                chunk = sock.recv(65536)
                if not chunk:
                    return None                  # truncated mid-frame
                body += chunk
            state = {}
            for row in lines[1:]:
                key, _, value = row.partition(" ")
                try:
                    state[key] = int(value)
                except ValueError:
                    pass
            return {"width": width, "height": height,
                    "brightness": state.get("brightness"),
                    "blanked": bool(state.get("blanked")),
                    "generation": state.get("generation"),
                    "pixels": body[:count],
                    "at": time.time()}
        except (socket.error, OSError, ValueError):
            return None
        finally:
            sock.close()


class Scheduler(object):
    """ftsched's HTTP API, as far as we need it. Absence is expected."""

    def __init__(self, base):
        self.base = base.rstrip("/")

    def _fetch(self, path, payload=None):
        url = self.base + path
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=SCHED_TIMEOUT) as fh:
            return json.loads(fh.read().decode("utf-8"))

    def state(self):
        try:
            return self._fetch("/api/state")
        except (urllib.error.URLError, OSError, ValueError):
            return None

    def command(self, op, **fields):
        payload = {"op": op}
        payload.update(fields)
        try:
            self._fetch("/api/command", payload)
            return True, ""
        except urllib.error.HTTPError as exc:
            try:
                return False, json.loads(exc.read().decode("utf-8")).get(
                    "error", str(exc))
            except Exception:
                return False, str(exc)
        except (urllib.error.URLError, OSError) as exc:
            return False, "scheduler unreachable: %s" % exc


class Desired(object):
    """What we want the display to be, across restarts of anything.

    Small enough that it is written whole, and only when it changes -- this
    sits on an SD card that a wall in a workshop will outlive only if nothing
    writes to it every time a slider moves.
    """

    def __init__(self, path):
        self.path = path
        self.brightness = None      # None until something has set one
        self.blanked = False
        self._load()

    def _load(self):
        if not self.path:
            return
        try:
            with open(self.path) as fh:
                saved = json.load(fh)
        except (OSError, ValueError):
            return
        if isinstance(saved.get("brightness"), int):
            self.brightness = saved["brightness"]
        self.blanked = bool(saved.get("blanked"))

    def save(self):
        if not self.path:
            return
        blob = {"brightness": self.brightness, "blanked": self.blanked}
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w") as fh:
                json.dump(blob, fh)
            os.replace(tmp, self.path)      # atomic; a torn file is unreadable
        except OSError as exc:
            sys.stderr.write("ftctl: cannot write %s (%s)\n" % (self.path, exc))


class Bridge(object):
    """Cache, reconciler, and the single place either backend is written to."""

    def __init__(self, control, scheduler, desired, pause_when_off):
        self.control = control
        self.scheduler = scheduler
        self.desired = desired
        self.pause_when_off = pause_when_off
        self.lock = threading.Lock()
        self.display = None            # last good control state, or None
        self.sched = None              # last good ftsched state, or None
        self._generation = None
        self._listeners = []           # called after every refresh
        self._stop = threading.Event()

    # -- reads ------------------------------------------------------------

    def snapshot(self):
        with self.lock:
            return {"display": self.display, "scheduler": self.sched}

    def add_listener(self, fn):
        self._listeners.append(fn)

    # -- writes -----------------------------------------------------------
    #
    # Straight through to the socket rather than into ftsched's command queue:
    # that one is bounded and drains at the render loop's pace, so a dragged
    # slider would push rotation commands out of it.

    def set_brightness(self, percent):
        percent = max(1, min(100, int(percent)))
        ok, err = self.control.command("brightness %d" % percent)
        if ok:
            self.desired.brightness = percent
            self.desired.save()
            self._patch(brightness=percent)
        return ok, err

    def set_blanked(self, blanked):
        ok, err = self.control.command("blank %s" % ("on" if blanked else "off"))
        if not ok:
            return ok, err
        self.desired.blanked = bool(blanked)
        self.desired.save()
        self._patch(blanked=bool(blanked))
        # The policy that "off" also stops the rotation lives here and nowhere
        # else. ft_server has never heard of ftsched, and having ftsched watch
        # the display state would point the dependency the wrong way. Failing
        # to reach the scheduler is not a failure of turning the wall off.
        if self.pause_when_off:
            self.scheduler.command("pause" if blanked else "resume")
        return True, ""

    def wipe(self):
        return self.control.command("wipe")

    def _patch(self, **fields):
        """Fold an accepted write into the cache, so reads do not lag a poll."""
        with self.lock:
            if self.display is not None:
                self.display = dict(self.display, **fields)

    # -- the refresh loop -------------------------------------------------

    def run(self):
        while not self._stop.is_set():
            display = self.control.get()
            sched = self.scheduler.state()
            with self.lock:
                self.display = display
                self.sched = sched
            if display is not None:
                self._reconcile(display)
            for fn in self._listeners:
                try:
                    fn()
                except Exception as exc:            # a listener is not the boss
                    sys.stderr.write("ftctl: listener failed (%s)\n" % exc)
            self._stop.wait(POLL_SECONDS)

    def stop(self):
        self._stop.set()

    def _reconcile(self, display):
        """Re-apply what we want after the server has been restarted.

        `generation` is stamped once per run of ft_server, so a change in it is
        a restart -- which is cheaper and more certain than inferring one from
        the brightness having gone back to whatever --led-brightness said.
        """
        generation = display.get("generation")
        first_sight = self._generation is None
        if generation == self._generation:
            self._adopt(display)
            return
        self._generation = generation
        if first_sight and self.desired.brightness is None:
            # Nothing to restore and nothing remembered: adopt what the server
            # booted with, so the first slider position is honest.
            self.desired.brightness = display.get("brightness")
            return
        if self.desired.brightness is not None and \
                display.get("brightness") != self.desired.brightness:
            self.control.command("brightness %d" % self.desired.brightness)
        if self.desired.blanked != display.get("blanked"):
            self.control.command(
                "blank %s" % ("on" if self.desired.blanked else "off"))

    def _adopt(self, display):
        """Take the display's word for it when it changed without us.

        The control socket is world-writable and documented as such, so
        `ftc.py blank on` from a shell, or anything else local, is a legitimate
        way to change the wall. What is not legitimate is what used to happen
        next: `desired` kept saying the wall was on, Home Assistant kept showing
        it on, and the banner kept reporting the remembered state instead of the
        real one -- until the next restart of ft_server, when the stale desire
        was helpfully re-applied and turned the wall back on by itself.

        So an observed change with the same generation is adopted rather than
        fought. Reconciling instead -- pushing `desired` back every poll --
        would make ftctl undo any direct command within a second, which turns a
        documented interface into a race.
        """
        changed = False
        if display.get("brightness") is not None and \
                display["brightness"] != self.desired.brightness:
            self.desired.brightness = display["brightness"]
            changed = True
        if bool(display.get("blanked")) != bool(self.desired.blanked):
            self.desired.blanked = bool(display.get("blanked"))
            changed = True
        # Only on a real change: this runs once a second, on an SD card.
        if changed:
            self.desired.save()


# -- live stream -----------------------------------------------------------

class FrameBroadcaster(object):
    """The wall as a stream of PNGs: encoded once, handed to every viewer.

    The thumbnail above answers "what is on the wall" for something that asks
    about once a second. This answers "what is the wall doing" for somebody
    watching a demo from the other end of a tailnet, which is a different
    problem: it wants twenty frames a second, and it must not cost the wall
    anything to provide them.

    Three properties, in the order they matter:

      One encode, however many viewers. The producer thread renders a frame and
      publishes the bytes; viewer threads write that same immutable object. A
      second viewer is one more sendall(), not a second deflate. This is the
      whole reason the fan-out lives here rather than each request rendering for
      itself the way the thumbnail does -- and it is why the viewer cap is about
      the radio and not about this Pi.

      A slow viewer drops frames rather than holding anything up. The producer
      never touches a socket and never waits for a viewer. Whoever was still
      writing when frame N went out simply misses it and picks up N+1 -- which
      is the right answer for live video anyway, and more importantly is what
      keeps somebody's bad hotel wifi from turning into judder on the wall.

      Nothing runs when nobody is watching. The thread starts on the first
      viewer and exits with the last, so an unwatched wall pays exactly nothing.
      A wall in a workshop is unwatched almost all of the time.
    """

    def __init__(self, render, fps=LIVE_FPS, max_viewers=LIVE_MAX_VIEWERS):
        self.render = render            # () -> (raw_pixels, png), or None
        self.period = 1.0 / max(1, fps)
        self.max_viewers = max_viewers
        self._cond = threading.Condition()
        self._seq = 0                   # bumped only when the picture changes
        self._png = None
        self._viewers = 0
        self._thread = None             # the running producer, or None

    def join(self):
        """Claim a viewer slot, starting the producer if it is the first.

        False when the slots are full, which the caller turns into a 503. The
        count is what bounds the bandwidth, so it is taken here and released in
        a finally: a viewer that leaks a slot costs the next person the stream.
        """
        with self._cond:
            if self._viewers >= self.max_viewers:
                return False
            self._viewers += 1
            if self._thread is None:
                thread = threading.Thread(target=self._run, daemon=True)
                # Published before start() so the thread's own identity check
                # cannot lose a race against a viewer that leaves immediately.
                self._thread = thread
                thread.start()
            return True

    def leave(self):
        with self._cond:
            self._viewers = max(0, self._viewers - 1)
            if not self._viewers:
                # Dropping the reference is the stop signal: the producer
                # compares identity on each pass and returns when it is no
                # longer the current thread. No flag to get out of step, and a
                # viewer arriving in the meantime just starts a fresh one.
                self._thread = None
                self._cond.notify_all()

    def next_frame(self, seen, timeout=LIVE_IDLE_PROBE):
        """Wait for a frame the caller has not had. (seq, png), or None.

        `seen` is the sequence the caller last wrote, or None for "give me
        whatever is current" -- so a viewer joining a static wall gets a picture
        immediately rather than waiting for one to change.
        """
        with self._cond:
            self._cond.wait_for(
                lambda: self._png is not None and self._seq != seen, timeout)
            if self._png is None or self._seq == seen:
                return None             # timed out; the caller decides
            return self._seq, self._png

    def _run(self):
        me = threading.current_thread()
        nxt = time.time()
        last_raw = None
        while True:
            with self._cond:
                if self._thread is not me:
                    return              # the last viewer left
            frame = None
            try:
                frame = self.render()
            except Exception as exc:    # a broken render must not kill the loop
                sys.stderr.write("ftctl: live render failed (%s)\n" % exc)
            if frame is not None:
                raw, png = frame
                # An unchanged wall costs a socket read and a 61 kB memcmp, and
                # nothing else: no deflate, no sequence bump, so no viewer is
                # sent a frame identical to the one it is already showing. A
                # blanked or paused wall is very nearly free to be watching.
                # The first render always publishes: last_raw is None and raw
                # is bytes, so the very first frame cannot compare equal.
                if raw != last_raw:
                    last_raw = raw
                    with self._cond:
                        self._seq += 1
                        self._png = png
                        self._cond.notify_all()
            # Against a fixed deadline rather than sleeping a period: encode
            # time would otherwise accumulate into drift and 20 fps would
            # quietly become 17. If we have fallen behind entirely, give up on
            # the frames we missed instead of trying to catch up in a burst.
            nxt += self.period
            delay = nxt - time.time()
            if delay > 0:
                time.sleep(delay)
            else:
                nxt = time.time()


# -- HTTP ------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):

    protocol_version = "HTTP/1.1"
    server_version = "ftctl"

    def log_message(self, fmt, *a):
        pass                        # one line per poll per client, no thank you

    def _send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code, blob):
        self._send(code, json.dumps(blob), "application/json")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/api/display", "/api/display/"):
            self._json(200, self.server.bridge.snapshot())
        elif path == "/api/thumbnail.png":
            self._thumbnail()
        elif path == "/api/live.png":
            # HEAD gets the headers and no stream: something asking whether this
            # exists must not be given a viewer slot and held open forever.
            if self.command == "HEAD":
                self._send(200, b"", "multipart/x-mixed-replace; boundary=" +
                           LIVE_BOUNDARY)
            else:
                self._live()
        elif path == "/healthz":
            # Deliberately 200 even with the display unreachable: this process
            # being alive and the wall being reachable are different questions,
            # and conflating them makes a restart loop out of a blank wall.
            self._send(200, "ok\n", "text/plain")
        else:
            self._send(404, "no\n", "text/plain")

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        if self.path.split("?", 1)[0] not in ("/api/display", "/api/display/"):
            self._send(404, "no\n", "text/plain")
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if not 0 < length <= 4096:
            self._json(400, {"error": "bad body length"})
            return
        try:
            payload = json.loads(self.rfile.read(length))
        except ValueError as exc:
            self._json(400, {"error": "bad JSON: %s" % exc})
            return
        if not isinstance(payload, dict):
            self._json(400, {"error": "expected an object"})
            return

        bridge = self.server.bridge
        problems = []
        if "brightness" in payload:
            try:
                percent = int(payload["brightness"])
            except (TypeError, ValueError):
                problems.append("brightness must be a number")
            else:
                ok, err = bridge.set_brightness(percent)
                if not ok:
                    problems.append(err)
        if "blanked" in payload:
            ok, err = bridge.set_blanked(bool(payload["blanked"]))
            if not ok:
                problems.append(err)
        if payload.get("wipe"):
            ok, err = bridge.wipe()
            if not ok:
                problems.append(err)
        if not problems and not payload:
            problems.append("nothing to do")

        if problems:
            self._json(502 if "unreachable" in problems[0] else 400,
                       {"error": "; ".join(problems)})
            return
        self._json(200, bridge.snapshot())

    def _thumbnail(self):
        """A PNG of the wall as it is right now.

        The real composite, off the control socket, same as the login banner
        draws -- so Home Assistant and a terminal cannot show different walls.

        Served regardless of whether ftsched claims something is playing: the
        panel has pixels on it either way, and a wall being painted by a client
        with the rotation stopped is exactly when a picture is worth having.
        Falls back to the baked preview only when there is no snapshot to be
        had, which means an older server or a socket that has gone away.
        """
        png = self.server.screen_png()
        if png is None:
            self._send(404, "no picture available\n", "text/plain")
            return
        self._send(200, png, "image/png")

    def _client_gone(self):
        """True once the viewer has hung up, without waiting to write at it.

        A closed connection is readable and yields nothing, which is the whole
        test. Anything it did send is treated the same way: this response said
        Connection: close, so there is no next request on here to be had, and a
        client talking anyway is one to stop streaming at rather than parse.
        """
        try:
            ready, _, _ = select.select([self.connection], [], [], 0)
            return bool(ready)
        except (socket.error, OSError, ValueError):
            return True

    def _live(self):
        """The wall as multipart/x-mixed-replace, which is to say: an <img>.

        A stream a browser can display without a line of JavaScript, and that
        curl and mpv understand too. The alternative was a WebSocket and a
        canvas, which would buy client-driven rates and delta frames; at 1.1
        Mbps against a link that does twelve there is nothing yet to buy them
        with, and this needs no framing code and no nginx upgrade dance.

        Streaming under HTTP/1.1 without a Content-Length means the response
        ends when the connection does, so it says so: BaseHTTPRequestHandler
        does not chunk, and leaving keep-alive on would strand the next request
        behind a body that never finishes.
        """
        caster = self.server.caster
        if not caster.join():
            self.send_response(503)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", "0")
            self.send_header("Retry-After", "5")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            return
        try:
            # So a viewer that stops reading is dropped rather than parking a
            # slot until TCP eventually gives up on it.
            self.connection.settimeout(LIVE_SEND_TIMEOUT)
            self.send_response(200)
            self.send_header("Content-Type",
                             "multipart/x-mixed-replace; boundary=" +
                             LIVE_BOUNDARY)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            seen = None
            while True:
                frame = caster.next_frame(seen)
                if frame is None:
                    # A still wall, not a dead one -- so far as this knows yet.
                    # Ask the socket both ways, because neither question alone
                    # is prompt: a client's close arrives here as end-of-file on
                    # the read side straight away, while writing at it would
                    # succeed once more and only fail on the probe after that.
                    if self._client_gone():
                        break
                    self.wfile.write(b"\r\n")   # legal between parts, ignored
                    self.wfile.flush()
                    continue
                seen, png = frame
                self.wfile.write(
                    b"--" + LIVE_BOUNDARY.encode("ascii") + b"\r\n"
                    b"Content-Type: image/png\r\n"
                    b"Content-Length: " + str(len(png)).encode("ascii") +
                    b"\r\n\r\n" + png + b"\r\n")
                self.wfile.flush()
        except (socket.error, OSError, ValueError):
            pass                        # the viewer went away, which is normal
        finally:
            caster.leave()


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    timeout = 30

    def __init__(self, addr, bridge, previews, thumbnail_ttl=THUMBNAIL_TTL,
                 live_fps=LIVE_FPS, live_max_viewers=LIVE_MAX_VIEWERS):
        ThreadingHTTPServer.__init__(self, addr, Handler)
        self.bridge = bridge
        self.previews = previews
        self.thumbnail_ttl = thumbnail_ttl
        self.caster = FrameBroadcaster(self._live_frame, live_fps,
                                       live_max_viewers)
        self._screen_lock = threading.Lock()
        self._screen_png = None
        self._screen_at = 0.0
        self._thumb_name = None
        self._thumb_png = None

    def screen_png(self):
        """The wall as a PNG, at most thumbnail_ttl seconds old.

        Home Assistant polls this about once a second and this is a Pi that is
        usually voltage-throttled, so the TTL is the whole design: without it,
        every poll would be a 61 kB socket read and a deflate. With it, the cost
        is bounded no matter how many things are watching -- three dashboards
        open on the same wall cost exactly what one does.

        The lock makes that promise hold under ThreadingHTTPServer: without it,
        N simultaneous pollers all miss the cache and all go to the socket, which
        is the stampede the TTL exists to prevent.
        """
        now = time.time()
        with self._screen_lock:
            if self._screen_png is not None and \
                    now - self._screen_at < self.thumbnail_ttl:
                return self._screen_png
            png = self._render_screen()
            if png is not None:
                self._screen_png, self._screen_at = png, now
            return png

    def _live_frame(self):
        """The wall right now, as (raw bytes, PNG) -- or None if it cannot be had.

        Both halves because the broadcaster wants to know whether the picture
        changed, and comparing the 61 kB it already has is far cheaper than
        deflating it again to find out. The comparison is on the dimmed bytes
        deliberately: blanking the wall has to read as a change.

        No baked-preview fallback here, unlike the thumbnail. A still that
        quietly stands in for a live view is worse than a live view that stops,
        because the whole reason to watch is to find out what is really on the
        panel.
        """
        snap = self.bridge.control.snapshot()
        if snap is None:
            return None
        pixels = snap["pixels"]
        if snap.get("blanked"):
            # The same dimming the login banner uses, so the two agree about
            # what a dark wall looks like.
            pixels = pixels.translate(blanked_table())
        return pixels, encode_png(snap["width"], snap["height"], pixels)

    def _render_screen(self):
        frame = self._live_frame()
        if frame is None:
            # No snapshot: an older ft_server, or the socket has gone. Fall back
            # to the baked preview so Home Assistant keeps showing something.
            sched = self.bridge.snapshot()["scheduler"]
            name = (sched or {}).get("now", {}).get("name")
            return self.thumbnail(name) if name else None
        return frame[1]

    def thumbnail(self, name):
        """The baked preview clip for an effect. Only a fallback now."""
        if name == self._thumb_name:
            return self._thumb_png
        png = None
        path = os.path.join(self.previews, name + ".webp")
        try:
            from PIL import Image
            import io
            with Image.open(path) as img:
                img.seek(0)                     # first frame of the animation
                buf = io.BytesIO()
                img.convert("RGB").save(buf, "PNG")
                png = buf.getvalue()
        except Exception:
            png = None                          # missing preview, or no Pillow
        self._thumb_name, self._thumb_png = name, png
        return png


def parse_addr(spec, default_port=8082):
    spec = spec.strip()
    if spec.startswith("["):
        host, _, rest = spec[1:].partition("]")
        port = int(rest.lstrip(":")) if rest.lstrip(":") else default_port
        return host, port
    host, sep, port = spec.rpartition(":")
    if not sep:
        return spec, default_port
    return host, int(port)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--socket", default="/run/ft/control.sock",
                    help="ft_server's control socket")
    ap.add_argument("--listen", default="127.0.0.1:8082",
                    help="HTTP control API; nginx is the way in from outside")
    ap.add_argument("--scheduler", default="http://127.0.0.1:8081",
                    help="ftsched's base URL; absence is handled, not fatal")
    ap.add_argument("--previews", default=os.path.join(_HERE, "previews"),
                    help="baked demo previews; only a fallback for the picture "
                         "now that the panel itself can be captured")
    ap.add_argument("--thumbnail-ttl", type=float, default=THUMBNAIL_TTL,
                    help="seconds to reuse the captured PNG of the wall before "
                         "taking another; caps what Home Assistant's polling "
                         "costs, however many dashboards are open")
    ap.add_argument("--live-fps", type=float, default=LIVE_FPS,
                    help="frame rate of /api/live.png; there is no point above "
                         "the rate the rotation actually renders at")
    ap.add_argument("--live-max-viewers", type=int, default=LIVE_MAX_VIEWERS,
                    help="concurrent viewers of /api/live.png before 503; this "
                         "bounds the wifi, not the CPU -- the frame is encoded "
                         "once however many are watching")
    ap.add_argument("--state-file", default="/var/lib/ftctl/desired.json",
                    help="remembered brightness and on/off; '' to not persist")
    ap.add_argument("--no-pause-when-off", dest="pause_when_off",
                    action="store_false",
                    help="leave the rotation running while the wall is dark")
    # -- MQTT / Home Assistant
    ap.add_argument("--mqtt-host", default=None,
                    help="broker; without this, MQTT is simply not started")
    ap.add_argument("--mqtt-port", type=int, default=1883)
    ap.add_argument("--mqtt-user", default=None)
    ap.add_argument("--mqtt-pass", default=None)
    ap.add_argument("--mqtt-prefix", default="ft/betelgeuse",
                    help="topic prefix for this wall")
    ap.add_argument("--mqtt-discovery-prefix", default="homeassistant")
    ap.add_argument("--mqtt-heartbeat", type=float, default=60.0,
                    help="seconds between state publishes when nothing has "
                         "changed; anything a person changes is published at "
                         "once regardless")
    ap.add_argument("--node-id", default="betelgeuse",
                    help="stable id; it ends up in the HA entity ids")
    ap.add_argument("--friendly-name", default="Betelgeuse")
    ap.add_argument("--motd-file", default=None,
                    help="render the login banner here whenever the state a "
                         "person would notice changes; see ftmotd.py for why "
                         "this is not computed at login time")
    ap.add_argument("--motd-picture-ttl", type=float, default=30.0,
                    help="seconds before the frame in the banner is stale "
                         "enough to be worth a repaint on its own; 0 pins it "
                         "to state changes only")
    ap.add_argument("--motd-lan-url", default="http://betelgeuse.local/")
    ap.add_argument("--motd-tailnet-url", default="")
    ap.add_argument("--public-url", default=None,
                    help="how Home Assistant can reach this wall's web page, "
                         "e.g. http://betelgeuse.local/ -- used for the "
                         "thumbnail and the device's configuration link")
    args = ap.parse_args()

    if args.state_file:
        directory = os.path.dirname(args.state_file)
        if directory and not os.path.isdir(directory):
            try:
                os.makedirs(directory, exist_ok=True)
            except OSError as exc:
                sys.stderr.write("ftctl: no state directory (%s)\n" % exc)

    control = Control(args.socket)
    scheduler = Scheduler(args.scheduler)
    desired = Desired(args.state_file)
    bridge = Bridge(control, scheduler, desired, args.pause_when_off)

    host, port = parse_addr(args.listen)
    httpd = Server((host, port), bridge, args.previews, args.thumbnail_ttl,
                   args.live_fps, args.live_max_viewers)

    if args.motd_file:
        import ftmotd
        writer = ftmotd.Writer(args.motd_file,
                               {"lan": args.motd_lan_url,
                                "tailnet": args.motd_tailnet_url},
                               snapshot_fn=control.snapshot,
                               picture_ttl=args.motd_picture_ttl)

        def repaint_motd():
            # bridge.snapshot() is the cached state; the picture is fetched by
            # the writer itself, and only when it has decided to repaint.
            state = bridge.snapshot()
            writer.update(state["display"], state["scheduler"])

        bridge.add_listener(repaint_motd)

    mqtt_bridge = None
    if args.mqtt_host:
        import ftctl_mqtt
        mqtt_bridge = ftctl_mqtt.start(bridge, args)
        if mqtt_bridge is None:
            sys.stderr.write("ftctl: MQTT not started; HTTP still serving\n")
    else:
        # Say so. Silence here is indistinguishable from a broker that is simply
        # quiet, and the way this goes wrong in practice is a systemd drop-in
        # whose Environment= lines sit above the [Service] header -- systemd
        # discards them with a warning nobody is looking for, --mqtt-host arrives
        # empty, and the wall never appears in Home Assistant with nothing at all
        # to suggest why.
        sys.stderr.write("ftctl: no --mqtt-host, so no Home Assistant; "
                         "HTTP control API only\n")

    poller = threading.Thread(target=bridge.run)
    poller.daemon = True
    poller.start()

    sys.stderr.write("ftctl: %s -> http://%s:%d, display socket %s\n"
                     % (args.friendly_name, host, port, args.socket))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        bridge.stop()
        if mqtt_bridge is not None:
            mqtt_bridge.stop()


if __name__ == "__main__":
    main()
