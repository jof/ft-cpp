#!/usr/bin/env python3
"""The last twenty-four hours of the Sun's corona, on a seamless loop.

Every other space-adjacent panel on this wall draws numbers or geometry --
`propagation` plots indices, `sats` plots orbits. This one is a photograph of
the star, which is the only object outside this planet anybody walking past
can recognise on sight.

**Why 193 angstroms.** SDO's Atmospheric Imaging Assembly takes the Sun in ten
channels and they are pictures of ten different things. 193 A is Fe XII/XXIV
at about 1.2 million kelvin, which is the corona rather than the surface, and
it is the channel where the Sun's magnetic field becomes visible: active
regions as bright knots, the loops arcing between them, and coronal holes as
the black bays where the field opens and the solar wind leaves. It is the
image people mean when they say "a picture of the Sun", and unlike 4500 A --
which is the bland yellow disk -- there is something happening in it.

**It is a loop, so the wrap is the hard part.** Forty-eight half-hourly frames
is a day, and the day does not join up: the Sun turns 13.2 degrees in it, and
cutting from now back to yesterday is a visible jerk that reads as a fault.
Fixing it by holding on the newest frame -- which is what `goes.py` does, and
right for weather, where the point is that the last frame is *now* -- would be
wrong here, because the point of this one is the turning. So the loop overlaps
itself instead: the last six frames are cross-dissolved into the first six, in
intensity rather than in RGB, and the loop period is shortened by exactly that
overlap. The seam then falls in the middle of a dissolve and there is nothing
to see. That the dissolve is a genuine double exposure of two moments six
hours apart is the honest cost, and at 13.2 degrees a day the two are close
enough that it reads as a soft blur and not a ghost.

**The X-ray trace is the same day, not a second panel.** GOES' 1-8 A flux is
already fetched for `propagation`, so it costs nothing to draw, and drawn on
the *same* time axis as the time lapse it stops being a second instrument and
becomes a caption for the first: the playhead crossing a spike is the same
instant the disk flares. The scale is logarithmic from B to X rather than the
conventional A to X, because most days are quiet -- the sun was B4 the day this
was written -- and four decades flattens a quiet day onto the floor where it
looks like no data at all. Three and a half decades keeps a B-class day a
visible ripple and still leaves an X-flare at the ceiling.

**The picture comes out of a cache and this file cannot fetch.** ftdata.py
fetches on a timer, crops to the limb, and stores one 8-bit intensity plane per
frame -- not RGB, because the browse JPEG is a one-dimensional bronze colormap
and its other two channels are not independent information. That means the
ramp is applied *here*, which is what lets it be tuned for an LED panel whose
dark end is compressed rather than for a monitor. See ftdata.py's block on this
product. Run the fetcher first, or the panel says so:

    $ python3 ftdata.py --loop 1800

**Playback is an index and one blend.** Everything -- the resample, the colour
ramp, the loop overlap, the flux trace, the type -- is baked in `build()`. A
frame on the wall copies a prepared background, blends two 64x64 tiles into
the disk box, and moves a playhead two columns wide. It is deliberately the
cheapest thing it can be, because the corona is doing the work and the panel
should spend its budget on the picture.

**Missing, partial and stale are three different things and it says which.**
No cache or no sidecar gets the no-data card with the fetcher's command on it.
A ring with fewer frames than a full day plays anyway and says how much of a
day it has -- a cold start is a short ring by definition, and eight hours of
the Sun turning beats a card that says wait. A ring whose newest frame has gone
stale keeps playing with the age in red, because yesterday's corona is still
worth looking at as long as nobody can mistake it for now.
"""

import math
import sys
import time

import numpy as np

import defcon
import demoscene as ds
import ftdata

f32 = np.float32

# Colours. The disk is the only saturated thing on the panel by design, so the
# furniture is a cold blue-grey that cannot compete with bronze, and the only
# other warm colour is the flare class -- which is allowed to shout, because
# an M-flare is the one thing here worth interrupting somebody for.
C_TEXT = (150, 162, 180)
C_DIM = (86, 96, 112)
C_FAINT = (44, 50, 62)
C_WARN = (255, 88, 64)
C_HEAD = (255, 226, 170)
C_RULE = (30, 35, 46)

# The AIA 193 colour ramp, measured off a browse frame rather than guessed.
# Binning a real image by (R+G+B)/3 recovers this table to within a level or
# two; see ftdata.py on why one channel is stored and re-coloured here. It runs
# black -> oxblood -> bronze -> gold -> cream -> white, and the top end matters:
# flare cores go white, and a ramp that saturates to flat orange instead would
# throw away the only part of the picture that is ever urgent.
AIA193 = [
    (0.000, (0, 0, 0)), (0.024, (1, 0, 0)), (0.071, (44, 9, 1)),
    (0.118, (69, 19, 2)), (0.165, (90, 32, 3)), (0.212, (108, 46, 8)),
    (0.259, (123, 61, 14)), (0.306, (137, 74, 22)), (0.353, (149, 88, 31)),
    (0.400, (161, 102, 41)), (0.447, (171, 116, 53)), (0.494, (181, 129, 65)),
    (0.541, (190, 142, 79)), (0.588, (199, 155, 94)), (0.635, (207, 167, 109)),
    (0.682, (215, 179, 125)), (0.729, (222, 191, 142)), (0.776, (229, 203, 159)),
    (0.824, (236, 214, 176)), (0.871, (244, 225, 194)), (0.918, (252, 236, 209)),
    (0.965, (250, 249, 247)), (1.000, (255, 255, 255)),
]

# Flux thresholds and the colour a column of the trace gets. The same ladder
# propagation.py uses at the hot end -- C yellow, M orange, X red, so the two
# panels cannot disagree about what a C looks like -- but the sub-C colour is
# a cold blue-grey rather than propagation's green. The disk is the only warm
# thing on this panel by design, so a quiet Sun should read cold and heat
# should be the thing that appears when a flare does.
XRAY_COLOURS = ((1e-4, (255, 96, 96)), (1e-5, (255, 150, 60)),
                (1e-6, (240, 205, 90)), (0.0, (96, 126, 152)))

# How far the filled body of the trace is knocked back from its ridge line.
# The fill alone is a slab -- on a quiet day it is a flat-topped bar across a
# quarter of the panel and reads as a block of colour, not as a measurement.
# A bright one-pixel ridge over a dim body reads as a curve.
XRAY_FILL = 0.34

# The log window the trace is drawn in. Not the conventional A..X: see the
# module docstring.
XRAY_LO, XRAY_HI = -7.5, -4.0


# --------------------------------------------------------------------------
# Type. defcon.py's 3x5 font, the same table goes.py, propagation.py and
# tide.py use. There is no font file to be missing on the Pi, and nothing
# built from a real typeface survives five pixels. It is uppercase, digits and
# a little punctuation only -- which is why the wavelength is labelled "193 A"
# and not with an angstrom sign.
# --------------------------------------------------------------------------

_GLYPHS = {}
for _ch, _rows in defcon._FONT.items():
    _g = np.zeros((5, 3), bool)
    for _r, _digit in enumerate(_rows):
        _v = int(_digit, 8)
        for _c in range(3):
            if _v & (4 >> _c):
                _g[_r, _c] = True
    _GLYPHS[_ch] = _g


def text_mask(s):
    """A (5, 4n-1) bool mask for a string, one blank column between glyphs."""
    s = str(s).upper()
    if not s:
        return np.zeros((5, 1), bool)
    out = np.zeros((5, len(s) * 4 - 1), bool)
    blank = _GLYPHS[" "]
    for i, ch in enumerate(s):
        out[:, i * 4:i * 4 + 3] = _GLYPHS.get(ch, blank)
    return out


def text_w(s, scale=1):
    return max(0, (4 * len(str(s)) - 1) * scale)


def stamp(buf, x, y, s, colour, scale=1):
    """Draw text into a uint8 (H, W, 3) buffer, clipped. Returns its width.

    Clipped rather than asserted, for goes.py's reason: the panel is laid out
    for 320x64 but has to survive being asked for something else, and a demo
    that raises on a narrow canvas takes the whole rotation down with it.
    """
    m = text_mask(s)
    if scale > 1:
        m = np.repeat(np.repeat(m, scale, 0), scale, 1)
    h, w = m.shape
    H, W = buf.shape[:2]
    x, y = int(x), int(y)
    sx, sy = max(0, -x), max(0, -y)
    ex, ey = min(w, W - x), min(h, H - y)
    if ex > sx and ey > sy:
        buf[y + sy:y + ey, x + sx:x + ex][m[sy:ey, sx:ex]] = colour
    return w


def parse_when(s):
    """'now', an epoch, or 'YYYY-MM-DD HH:MM' in local time."""
    if not s or s == "now":
        return None
    try:
        return float(s)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M",
                "%Y-%m-%d"):
        try:
            return time.mktime(time.strptime(s, fmt))
        except ValueError:
            continue
    raise ValueError("cannot read a time out of %r" % s)


def hhmm(epoch, ampm=True):
    """A compact label in the display's local time: '6:41P' or '18:41'.

    Local to the wall rather than UT, even though the instrument works in UT
    and burns UT into its own frames. Somebody standing in the workshop is
    being told when this picture was taken, and the only clock that answers
    that without arithmetic is the one on their wrist.
    """
    lt = time.localtime(epoch)
    if not ampm:
        return time.strftime("%H:%M", lt)
    return "%d:%02d%s" % (lt.tm_hour % 12 or 12, lt.tm_min,
                          "A" if lt.tm_hour < 12 else "P")


def iso_epoch(s):
    """SWPC's '2026-08-11T17:53:00Z' as an epoch. None if it will not parse."""
    if not s:
        return None
    s = str(s).strip().rstrip("Z")
    if "." in s:
        s = s.split(".", 1)[0]
    import calendar
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return float(calendar.timegm(time.strptime(s, fmt)))
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------
# Reading what ftdata left behind. Two files -- a JSON record and the array
# sidecar it names -- and everything that can be wrong with either ends up as
# one string the panel can print.
# --------------------------------------------------------------------------

def read_ring(cache_dir, product):
    """Return (ring, age, problem). Any of the first two may be None."""
    got = ftdata.load(product, cache_dir)
    if got is None:
        return None, None, "no cached sdo imagery"
    payload, age = got
    if not isinstance(payload, dict):
        return None, age, "sdo record is malformed"
    blob = ftdata.load_blob(payload.get("blob"), cache_dir)
    if blob is None:
        return None, age, "frame sidecar is missing or unreadable"
    try:
        frames = blob["frames"]
        stamps = np.asarray(blob["stamps"], np.float64)
    except Exception:                                        # noqa: BLE001
        return None, age, "frame sidecar has no frames in it"
    if (frames.ndim != 3 or frames.dtype != np.uint8
            or len(frames) == 0 or len(frames) != len(stamps)
            or frames.shape[1] != frames.shape[2]):
        return None, age, "frame sidecar is malformed"
    order = np.argsort(stamps)
    return {"frames": np.ascontiguousarray(frames[order]),
            "stamps": stamps[order], "age": age,
            "want": int(payload.get("want", len(frames))),
            "cadence": float(payload.get("cadence", 1800.0)),
            "channel": str(payload.get("channel", "193 A")),
            "instrument": str(payload.get("instrument", "SDO/AIA")),
            "disk_frac": float(payload.get("disk_frac", 0.94))}, age, None


def read_xray(cache_dir):
    """The GOES flux record, or None. Never required; it is a garnish."""
    got = ftdata.load("swpc_xray", cache_dir)
    if got is None:
        return None
    payload, age = got
    if not isinstance(payload, dict):
        return None
    series = payload.get("series") or []
    if not any(v for v in series):
        return None
    return {"series": series, "age": age,
            "start": iso_epoch(payload.get("start")),
            "end": iso_epoch(payload.get("end")),
            "current_class": payload.get("current_class"),
            "peak_class": payload.get("peak_class"),
            "fresh": ftdata.is_fresh("swpc_xray", age)}


def resample(frames, size):
    """Nearest-neighbour the square intensity stack onto `size`. Once.

    One gather over the whole stack in `build()`, never per frame. Flattening
    the tile and gathering (row * n + col) in a single pass is goes.py's trick
    and the reason is the same: indexing rows and then columns builds a whole
    intermediate stack at the half-resampled size.
    """
    n, fh = frames.shape[:2]
    if fh == size:
        return frames
    r = np.clip(((np.arange(size) + 0.5) * fh / size).astype(np.intp), 0, fh - 1)
    flat = (r[:, None] * fh + r[None, :]).reshape(-1)
    out = frames.reshape(n, fh * fh)[:, flat]
    return np.ascontiguousarray(out.reshape(n, size, size))


def vignette(frames, disk_frac, feather=0.30):
    """Fade the corona to black outside the limb, in place.

    The stored tile is a square crop of a round object, and the corona is
    still bright where the square ends -- so without this the Sun sits in a
    luminous box: bright at the middle of each edge, black only in the
    corners. That reads as a rendering fault rather than as a photograph.

    The taper starts at the limb and reaches zero at the inscribed circle, so
    **no photospheric pixel is touched** and the only thing attenuated is
    coronal emission that the crop was going to truncate anyway. It is a
    composition choice and it does throw away real signal; the alternative
    throws away the same signal with a straight edge.
    """
    n, size = frames.shape[:2]
    c = (size - 1) / 2.0
    y = (np.arange(size, dtype=f32) - c)[:, None]
    x = (np.arange(size, dtype=f32) - c)[None, :]
    # Radius as a fraction of the tile's half-width, which is the same unit
    # `disk_frac` is quoted in.
    r = np.sqrt(y * y + x * x) / max(1e-6, c)
    inner = float(disk_frac)
    outer = min(1.0, inner + max(1e-3, feather))
    k = np.clip((outer - r) / (outer - inner), 0.0, 1.0)
    # Smoothstep, so the halo has no visible ring where the taper begins.
    k = k * k * (3.0 - 2.0 * k)
    out = frames.astype(f32) * k[None, :, :]
    return np.clip(out, 0, 255).astype(np.uint8)


def loop_stack(frames, overlap):
    """Overlap the tail into the head so the cycle has no seam.

    Given f[0..n-1] oldest to newest and an overlap of K, the loop period
    becomes L = n - K and the first K frames are replaced by a dissolve from
    the tail f[L..n-1] into the head f[0..K-1]. Playing g[0..L-1] on repeat
    then steps g[L-1] = f[L-1] straight into g[0] ~ f[L], which is an ordinary
    consecutive pair, and finishes the dissolve at g[K-1] ~ f[K-1] just as
    ordinary playback resumes. Nothing in the sequence is a cut.

    Done in intensity, before the colour ramp, which is both cheaper and more
    correct: interpolating along a one-dimensional colormap is what a dissolve
    between two frames of it means, whereas mixing the RGB it maps to cuts the
    corner of the ramp and desaturates the midpoint.
    """
    n = len(frames)
    if overlap <= 0 or n < 2 * overlap + 2:
        return frames, n
    period = n - overlap
    out = frames.astype(f32)
    w = ((np.arange(overlap, dtype=f32) + 1.0)
         / (overlap + 1.0))[:, None, None]
    head = out[:overlap].copy()
    tail = out[period:period + overlap]
    out[:overlap] = tail * (1.0 - w) + head * w
    return np.clip(out[:period], 0, 255).astype(np.uint8), period


# --------------------------------------------------------------------------
# Options.
# --------------------------------------------------------------------------

def add_arguments(ap):
    ap.add_argument("--cache-dir", default=None,
                    help="ftdata cache to read (default: ftdata's own)")
    ap.add_argument("--product", default=ftdata.SDO_PRODUCT,
                    help="ftdata product name to play")
    ap.add_argument("--frame-rate", type=float, default=3.0,
                    help="solar frames per wall second; at half-hourly "
                         "frames this makes the day about fourteen seconds")
    ap.add_argument("--overlap", type=int, default=6,
                    help="frames of tail dissolved into the head to hide the "
                         "loop's seam (0 = cut, and it shows)")
    ap.add_argument("--gamma", type=float, default=0.85,
                    help="contrast curve on the intensity before the colour "
                         "ramp; under 1 lifts the faint corona")
    ap.add_argument("--vignette", type=float, default=0.30,
                    help="width, in tile half-widths, of the fade from the "
                         "limb out to space (0 = keep the square crop)")
    ap.add_argument("--no-xray", dest="xray", action="store_false",
                    help="draw the disk alone, no flux trace")
    ap.add_argument("--no-blend", dest="blend", action="store_false",
                    help="cut between frames instead of dissolving")
    ap.add_argument("--24h", dest="h24", action="store_true", help="24 hour clock")
    ap.add_argument("--reload", type=float, default=900.0,
                    help="seconds between re-reads of the cache (0 = never)")
    ap.add_argument("--at", default="now",
                    help="pretend the present moment is this, for testing the "
                         "stale path (epoch or 'YYYY-MM-DD HH:MM' local)")


# --------------------------------------------------------------------------
# The no-data card. Same shape as goes.py's and tide.py's: say what is
# missing, say the command that fixes it, say where it was looked for.
# --------------------------------------------------------------------------

def draw_nodata(frame, problems, cache_dir):
    frame[:] = (6, 6, 8)
    h, w = frame.shape[:2]
    frame[0] = C_WARN
    frame[h - 1] = C_WARN
    frame[:, 0] = C_WARN
    frame[:, w - 1] = C_WARN

    title = "NO SUN"
    scale = 3
    while scale > 1 and text_w(title, scale) > w - 12:
        scale -= 1
    lines = ["RUN: PYTHON3 FTDATA.PY --LOOP 1800"]
    for p in problems[:1]:
        lines.append(p.upper())
    lines.append((cache_dir or ftdata.CACHE_DIR).upper())

    y = max(2, h // 2 - (5 * scale + 2 + 7 * len(lines)) // 2)
    stamp(frame, (w - text_w(title, scale)) // 2, y, title, C_WARN, scale)
    y += 5 * scale + 4
    for line in lines:
        while line and text_w(line) > w - 6:
            line = line[:-1]
        stamp(frame, (w - text_w(line)) // 2, y, line, C_TEXT)
        y += 7
        if y + 5 > h - 2:
            break
    return frame


# --------------------------------------------------------------------------
# build()
# --------------------------------------------------------------------------

def build(args):
    w, h = args.width, args.height
    cache = args.cache_dir
    frame = np.zeros((h, w, 3), np.uint8)

    at = parse_when(args.at)
    offset = 0.0 if at is None else at - time.time()

    def now():
        return time.time() + offset

    # The disk box is the panel's full height, so the Sun is as large as this
    # geometry allows and reads as the subject rather than as an icon. The
    # tile is stored with the photosphere covering 94 per cent of it, so a
    # 64 px box puts a 60 px Sun on the wall with a little corona around it.
    disk = max(8, min(h, w // 2))
    disk_x = 0

    # The colour ramp, as a lookup table with the contrast curve already
    # folded in, so mapping a frame is one np.take and never a pow().
    ramp = ds.gradient(AIA193, 256, dtype=np.uint8)
    if abs(args.gamma - 1.0) > 1e-3:
        idx = np.clip(
            np.rint(((np.arange(256, dtype=f32) / 255.0) ** args.gamma) * 255.0),
            0, 255).astype(np.intp)
        ramp = ramp[idx]

    cell = {"ring": None, "problem": None, "loaded": -1e18, "n": 0,
            "stack": None, "stamps": None, "period": 0, "bg": None,
            "age_key": None, "age_mask": None, "age_colour": C_DIM,
            "card": None, "axis": None}

    def bake_background(ring, xray):
        """Everything that does not move: type, the flux trace, the rules.

        One buffer, copied per frame. The alternative -- drawing the trace
        every frame -- is two hundred and fifty column writes thirty times a
        second to produce the identical picture, which is exactly the shape of
        work the Pi cannot afford and `build()` can.
        """
        bg = np.zeros((h, w, 3), np.uint8)
        x0 = disk + 6
        avail = w - x0 - 2
        if avail < 40:
            return bg, None

        # The panel's time axis: exactly the span the playhead sweeps, which
        # is the span of the loop's *unblended* frames and not the whole ring.
        #
        # The difference is the overlap, and getting this wrong is a bug this
        # panel had: the axis ran to the newest frame in the ring, but the
        # loop's last frame is `period - 1`, so the playhead stopped a
        # thirteenth of the way short of the right edge every cycle and the
        # last three hours of the trace were never swept. The frames past the
        # end are not lost -- they are what the head dissolves out of -- but
        # they are never shown at full weight, so the honest thing is to draw
        # and label the interval the loop actually sweeps. How stale the ring
        # is remains a separate claim, made separately in the corner.
        stamps = ring["stamps"]
        last = min(len(stamps) - 1, max(0, cell["period"] - 1))
        t0, t1 = float(stamps[0]), float(stamps[last])
        if t1 - t0 < 60.0:
            t1 = t0 + 60.0
        axis = (x0, avail, t0, t1)

        # Line one: what this is. The instrument and the channel, because a
        # picture of the Sun that does not say which Sun it is showing is the
        # thing this panel is most likely to be misread as -- somebody who
        # knows will ask 193 or 171, and somebody who does not learns that
        # there is a difference.
        stamp(bg, x0, 1, "%s %s" % (ring["instrument"], ring["channel"]), C_TEXT)

        # Line two: what the loop covers, in the viewer's own clock.
        span_h = max(1, int(round((t1 - t0) / 3600.0)))
        stamp(bg, x0, 9, "%dH TO %s" % (span_h, hhmm(t1, not args.h24)), C_DIM)

        if xray is None or not args.xray:
            return bg, axis

        # The flux trace, on the same axis. Columns rather than a line: at a
        # couple of dozen rows a one-pixel trace is dashes, and the filled
        # shape is what carries a flare at a glance.
        ty0, ty1 = 17, h - 12
        if ty1 - ty0 < 6:
            return bg, axis
        th = ty1 - ty0

        series = xray["series"]
        n = len(series)
        s0 = xray["start"] or t0
        s1 = xray["end"] or t1
        dim = 1.0 if xray["fresh"] else 0.45

        # Decade rules at C and M, so a spike has something to be tall
        # against, and named -- otherwise the empty two thirds of the trace is
        # just black, when what it actually says is "there is room above this
        # for a flare two hundred times bigger and there has not been one".
        # Dotted, so they never read as data.
        for level, name in ((1e-6, "C"), (1e-5, "M")):
            f = (math.log10(level) - XRAY_LO) / (XRAY_HI - XRAY_LO)
            if not 0.0 <= f <= 1.0:
                continue
            ly = ty1 - 1 - int(round(f * (th - 1)))
            bg[ly, x0 + 5:x0 + avail:3] = C_RULE
            stamp(bg, x0, ly - 2, name, C_FAINT)

        for col in range(avail):
            # Which bucket of the flux series this column is. Mapped through
            # the *time* axis rather than by proportion, because the flux
            # record and the imagery ring are fetched on different timers and
            # rarely cover exactly the same day.
            when = t0 + (col + 0.5) / avail * (t1 - t0)
            if s1 <= s0:
                continue
            j = int((when - s0) / (s1 - s0) * (n - 1) + 0.5)
            if j < 0 or j >= n:
                continue
            v = series[j]
            if v is None or v <= 0:
                continue
            f = (math.log10(v) - XRAY_LO) / (XRAY_HI - XRAY_LO)
            height = int(round(max(0.0, min(1.0, f)) * (th - 1))) + 1
            colour = XRAY_COLOURS[-1][1]
            for thresh, c in XRAY_COLOURS:
                if v >= thresh:
                    colour = c
                    break
            if dim < 1.0:
                colour = tuple(int(q * dim) for q in colour)
            top = ty1 - height
            # Body first, then the ridge over it, so the curve stays legible
            # where two neighbouring columns differ by one pixel.
            if height > 1:
                bg[top + 1:ty1, x0 + col] = tuple(
                    int(q * XRAY_FILL) for q in colour)
            bg[top, x0 + col] = colour

        # A baseline under the trace, and the two ends of the day named. The
        # right-hand end is the same instant as the newest frame, which is
        # what makes the playhead arriving there mean something.
        bg[ty1, x0:x0 + avail] = C_RULE
        label = "GOES X-RAY"
        cls = xray.get("current_class")
        if not xray["fresh"]:
            label = "X-RAY " + ftdata.describe_age(xray["age"]) + " OLD"
        stamp(bg, x0, h - 11, label, C_DIM)
        if cls:
            # The one number on the panel that is allowed to be loud, and only
            # when it is worth it: a C is ordinary, an M or an X is not.
            hot = cls[:1] in ("M", "X")
            cw = text_w(cls)
            stamp(bg, x0 + avail - cw, h - 11, cls,
                  C_HEAD if hot else C_DIM)
        return bg, axis

    def load(t):
        cell["loaded"] = t
        ring, _, problem = read_ring(cache, args.product)
        if problem != cell["problem"]:
            cell["card"] = None       # the card names the problem; it changed
        cell["problem"] = problem
        if ring is None:
            cell["ring"] = None
            cell["n"] = 0
            return
        frames = resample(ring["frames"], disk)
        if args.vignette > 0.0:
            frames = vignette(frames, ring["disk_frac"], args.vignette)
        stack, period = loop_stack(frames, max(0, args.overlap))
        # The colour ramp, once, over the whole loop. From here on the demo
        # owns nothing but ready-to-blit RGB.
        cell["stack"] = np.ascontiguousarray(ramp[stack])
        cell["period"] = period
        cell["stamps"] = ring["stamps"]
        cell["ring"] = ring
        cell["n"] = len(cell["stack"])
        cell["bg"], cell["axis"] = bake_background(ring, read_xray(cache))
        cell["age_key"] = None

    load(now())

    # Scratch for the blend. int16 for goes.py's reason: the difference of two
    # uint8 frames is signed and spans -255..255, and integer is about three
    # times cheaper than float32 a pass on the wall's Pi.
    diff = np.empty((disk, disk, 3), np.int16)

    def blend_into(dst, a, b, k):
        """dst = a + ((b - a) * k >> 7), in integers, over the disk box only.

        Sevenths of a step rather than eighths so the arithmetic stays in
        int16: 255 * 127 is 32385, inside int16 by three hundred.
        """
        np.subtract(b, a, out=diff, dtype=np.int16, casting="unsafe")
        np.multiply(diff, k, out=diff)             # k is 0..127
        np.right_shift(diff, 7, out=diff)
        np.add(diff, a, out=diff)
        np.copyto(dst, diff, casting="unsafe")

    def render(t, i):
        tnow = now()
        if args.reload and tnow - cell["loaded"] >= args.reload:
            load(tnow)
        if cell["ring"] is None or cell["n"] == 0:
            # Baked once and copied, not laid out thirty times a second.
            if cell["card"] is None:
                cell["card"] = draw_nodata(
                    np.zeros_like(frame),
                    [cell["problem"] or "cache is empty"], cache)
            np.copyto(frame, cell["card"])
            return frame

        np.copyto(frame, cell["bg"])

        n = cell["n"]
        stack = cell["stack"]
        # Where in the loop. A plain cycle with no hold: the overlap has
        # already made the wrap seamless, so stopping on the newest frame
        # would put a stutter back in that the dissolve exists to remove.
        x = (t * max(args.frame_rate, 1e-3)) % n if n > 1 else 0.0
        k = min(n - 1, int(x))
        frac = x - k
        nxt = (k + 1) % n
        kk = min(127, int(frac * 128.0))

        box = frame[0:disk, disk_x:disk_x + disk]
        if not args.blend or kk == 0 or n == 1:
            np.copyto(box, stack[k])
        else:
            blend_into(box, stack[k], stack[nxt], np.int16(kk))

        axis = cell["axis"]
        if axis is not None:
            x0, avail, t0, t1 = axis
            # The playhead, on the same axis as the trace. `k` indexes the
            # loop, whose first `overlap` frames are a dissolve of two
            # moments; the head's timestamp is the one used, so the playhead
            # restarts at the left exactly as the picture does.
            when = float(cell["stamps"][min(k, len(cell["stamps"]) - 1)])
            f = (when - t0) / max(1e-6, t1 - t0)
            px = x0 + int(round(max(0.0, min(1.0, f)) * (avail - 1)))
            ty0, ty1 = 18, h - 12
            if ty1 > ty0:
                frame[ty0:ty1, px] = C_HEAD

        # The age of the newest frame against the wall clock -- the one number
        # that says whether any of this is still true. It changes once a
        # minute at most, so it is laid out on the half minute and blitted
        # from a mask in between.
        age = max(0.0, tnow - float(cell["stamps"][-1]))
        key = int(age // 30)
        if key != cell["age_key"]:
            cell["age_key"] = key
            stale = not ftdata.is_fresh(args.product, age)
            text = ftdata.describe_age(age)
            if stale:
                text = "STALE " + text
            elif len(cell["stamps"]) * 10 < cell["ring"]["want"] * 9:
                # A materially short ring is worth admitting: it is what a
                # cold start looks like, and it is why the loop is over in
                # four seconds instead of fourteen.
                text = "%dH" % max(
                    1, int(round((float(cell["stamps"][-1])
                                  - float(cell["stamps"][0])) / 3600.0)))
            cell["age_mask"] = text_mask(text)
            cell["age_colour"] = C_WARN if stale else C_FAINT
        m = cell["age_mask"]
        gh, gw = m.shape
        x0 = w - 2 - gw
        if x0 > disk and 1 + gh <= h:
            frame[1:1 + gh, x0:x0 + gw][m] = cell["age_colour"]
        return frame

    render.state = cell               # tests reach in here; nothing else does
    render.disk = disk
    render.clock = now
    return render


def main():
    # 20 fps: the dissolve between half-hourly frames wants a smooth ramp, and
    # at three solar frames a second there are nearly seven wall frames to
    # spend on each one.
    ds.standalone(sys.modules[__name__], __doc__.split("\n", 1)[0], fps=20)


if __name__ == "__main__":
    main()
