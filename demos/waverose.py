#!/usr/bin/env python3
"""The shape of the sea off Ano Nuevo, drawn as the buoy actually measures it.

`swell.py` next door draws one wave train in section: a height, a period and a
direction, the sea reduced to the three numbers a surf report gives. This panel
draws the thing those numbers are a summary *of* -- the directional wave
spectrum, the full answer to "how much energy is running, at what period, from
which way" -- because a Sofar Spotter measures exactly that and most buoys do
not.

**The rose is the spectrum in polar form.** Angle is compass bearing: a petal
to the lower-left is energy arriving from the south-west. Radius is wave period,
long swell at the rim and short chop at the core, so a clean groundswell shows
as a bold arc reaching out toward the direction it comes from and a blown-out
local sea shows as a broad fuzzy centre. Brightness is energy density -- how
much sea is running at that period and bearing. Nothing here is an encoding
that needs a legend: the bright reach of the rose *is* where the swell is from
and how long it is.

**Radius is period, not frequency, on purpose.** The buoy's frequency bins run
from a thirty-four second sway to a one-second ripple, and almost all the
energy on any ordinary day sits below a tenth of a hertz -- which, drawn
straight, is a bright dot at the centre and eighty per cent of the rose empty.
Period is the reciprocal, and spreading it linearly puts the twenty-second
groundswell four fifths of the way out where it can be seen and read, and
leaves the chop a small core where it belongs.

**Each frequency bin is drawn as a lobe, not a point.** The buoy reports, per
period, a mean bearing and a directional spread -- how tightly the energy at
that period is aimed. The rose draws each as a bearing-centred bell whose width
is that spread, weighted by the energy there. A real directional spectrum can
be bimodal at one period -- a west swell crossing a south one -- and a mean and
a spread cannot say so; this is the conventional first-moment picture and no
more, which is why the panel says SPREAD rather than pretending to a fidelity
the two numbers do not carry.

**The strip on the right is the last several hours of that same spectrum**, so
the rose is never just now. Time runs left to old, right to now; height is the
same period axis as the rose, swell low and chop high; brightness is the same
energy. A vertical playhead sweeps it, and the rose is the spectrum *at the
playhead* -- so watching the panel is watching the sea state build, veer and
lengthen over the afternoon, not a single frozen reading. This is the animation
the panel is built around: the change in the data over time, played as a loop.

**Nothing here touches the network.** `ftdata.py` fetches on a slow timer in a
process of its own -- no faster than the buoy transmits and no faster than this
panel comes up in the wall's rotation, because a record nobody will see is a
request on a buoy owner's allowance for nothing -- and leaves a JSON record in
a cache. This reads that and imports no HTTP library. The record carries hours
of past spectra, so the loop above is always full even when the last fetch is
old.

**Two ages, because they are two failures.** The fetch age says whether the
fetcher is alive; the observation age says whether the buoy is. A buoy can go
quiet while the fetcher downloads its silence every ninety minutes, so past a
few hours stale the observation age is called out, and past half a day the rose
is not drawn at all -- animating a spectrum the ocean has stopped keeping is
the one lie this panel could tell.

**The panel opens on a credit.** The spectra are Sofar Ocean's, so the first
few seconds are their logomark held on black, then a wavy tide rises up the
wall and dissolves it to reveal the spectrum behind -- a wave washing the mark
away, which is on the nose and is the point. It is their own logomark image,
scaled to a sidecar, not a redraw; `--intro 0` or `--no-logo` skips it, and it
skips itself if the sidecar is not in the tree.

    $ python3 ftdata.py --once --only sofar-SPOT-32653C
    $ python3 waverose.py --host 127.0.0.1
    $ python3 waverose.py --spotter SPOT-0564
    $ python3 waverose.py --intro 0                     # straight to the data
    $ FT_DATA_CACHE=/tmp/empty python3 waverose.py      # the no-data card

**Frame budget.** The headline, the spectrogram and the compass ring are baked
once per record into a base frame; a frame is a copy of that base, one rose,
and one playhead line. The rose is ten numpy calls on a (61, 61) array -- three
gathers to pull the interpolated spectrum onto the pixels by period, a wrapped
angle difference, one exp for the directional bell, a lookup-table colour and a
masked write -- none of which allocate after build(). The spectrogram is built
column by column but only when the record changes.
"""

import math
import os
import sys
import time

import numpy as np

import defcon
import demoscene as ds
import ftdata

f32 = np.float32

SPOTTER = "SPOT-32653C"                  # off Ano Nuevo; its spectra transmit live
PRODUCT = "sofar-"

M_FT = 3.28084

# The period band the rose and the spectrogram span, in seconds. The rim is a
# twenty-five second swell -- longer than the Pacific delivers to this coast
# more than a few days a year -- and the core is a two-and-a-half second ripple,
# short enough to hold all the wind chop without wasting radius on periods the
# buoy's own bins barely resolve. Fixed, never fitted to the day: a rose whose
# radius means something different every afternoon cannot be read against
# yesterday's.
T_MIN = 2.5
T_MAX = 25.0

# The narrowest directional bell drawn, in degrees. The buoy's own spread runs
# thirty to eighty degrees, so this floor almost never binds; it exists so a
# freak tight bin does not draw a one-pixel spoke that reads as a fault.
SIG_MIN = 9.0

# Directional contrast. The measured spread is broad -- forty to eighty degrees
# -- so a bell drawn straight fills most of the compass and the rose reads as
# concentric rings, not as a sea running from somewhere. This lifts the foot of
# each bell off the floor so the lobe darkens to background on its far side and
# the bearing the energy is from is legible from across the room. It costs the
# faint 360-degree skirt of a real directional distribution, which is the right
# trade for a panel whose whole job is to show where the swell is from.
DIR_FLOOR = 0.30

# Energy is drawn against the record's own peak with a floor under it, so a calm
# afternoon is legible instead of black and a storm is not off the top. This is
# a self-scaling the fixed-axis swell panel refuses on principle; the difference
# is that this panel exists to show the *shape* of the spectrum, which is a
# thing you compare within a record -- swell against chop, now against an hour
# ago -- far more than between days. GAMMA lifts the mid-tones so the broad low
# skirts of the lobes show at all.
E_FLOOR = 0.06
GAMMA = 0.62

# Beyond OBS_WARN the observation age is called out; beyond OBS_DEAD the rose is
# not drawn. Wider than swell's bounds because a Spotter's satellite backhaul is
# lumpier than a coastal buoy's landline -- a three-hour gap is a quiet sea and
# a slow uplink, not a dead buoy.
OBS_WARN = 3.5 * 3600.0
OBS_DEAD = 12 * 3600.0

C_TEXT = (198, 210, 222)
C_DIM = (86, 98, 112)
C_WARN = (255, 96, 72)
C_SWELL = (120, 208, 255)
C_PERIOD = (255, 186, 96)
C_DIRN = (255, 214, 128)
C_RING = (30, 40, 54)                    # the compass ring and its ticks
C_RING_N = (150, 120, 90)                # the north tick, warmer so it is found
C_PLAY = (236, 246, 255)                 # the playhead
C_PLAY_DIM = (70, 90, 110)
C_CREDIT = (92, 150, 170)                # the SOFAR data-source credit
C_FOAM = (198, 234, 252)                 # the crest of the intro's rising tide

# Intro. The panel opens on the Sofar logomark held on black -- the data's
# source, and a nod to the buoy people who might be watching -- then a wavy
# tide rises up the wall and dissolves the mark to reveal the spectrum behind
# it. Their real logomark image, not a redraw; see load_logo().
INTRO_HOLD_FRAC = 0.42                   # share of the intro spent holding still
WASH_AMP = 3.0                           # crest wobble of the rising tide, px
WASH_FOAM = 2                            # foam band thickness at the crest, px
WASH_SPEED = 6.0                         # crest travel, rad/s
C_BG = (2, 5, 11)                        # the sea at rest: near-black blue
C_GRID = (18, 26, 38)

# The energy ramp: the dark of deep water, up through the blue an LED panel is
# actually good at, to a cyan-white crest. Built once into a 256-entry table.
E_RAMP = [(0.00, (3, 8, 22)), (0.16, (12, 46, 104)), (0.40, (26, 116, 186)),
          (0.68, (72, 194, 226)), (1.00, (224, 250, 255))]


def _ramp_lut(stops, n=256):
    lut = np.zeros((n, 3), np.uint8)
    xs = [s[0] for s in stops]
    for i in range(n):
        v = i / (n - 1)
        j = min(range(len(xs)), key=lambda k: (xs[k] > v, abs(xs[k] - v)))
        # find bracketing pair
        hi = 0
        while hi < len(xs) - 1 and xs[hi] < v:
            hi += 1
        lo = max(0, hi - 1)
        span = xs[hi] - xs[lo]
        f = 0.0 if span <= 0 else (v - xs[lo]) / span
        a, b = stops[lo][1], stops[hi][1]
        lut[i] = [int(round(a[c] + (b[c] - a[c]) * f)) for c in range(3)]
    return lut


# --------------------------------------------------------------------------
# Type: defcon.py's 3x5 font, same as swell/tide/caiso. See swell.py for the
# reasoning; the font has no comma, so no string here has one.
# --------------------------------------------------------------------------

_GLYPHS = {}
for _ch, _rows in defcon._FONT.items():
    _g = np.zeros((5, 3), bool)
    for _r, _d in enumerate(_rows):
        _v = int(_d, 8)
        for _c in range(3):
            if _v & (4 >> _c):
                _g[_r, _c] = True
    _GLYPHS[_ch] = _g

GLYPH_H = _GLYPHS[" "].shape[0]
GLYPH_W = _GLYPHS[" "].shape[1]

# The 3x5 font has no N-with-tilde, so the base letter is the plain N and the
# tilde is drawn as a two-row accent in the margin above it -- which is why the
# headline sits a couple of rows down. AÑO reads as a place, not a typo.
_GLYPHS.setdefault("Ñ", _GLYPHS.get("N", _GLYPHS[" "]))
TILDE = np.array([[0, 1, 1], [1, 1, 0]], bool)      # a 2x3 wave over the N


def _blit_mask(dst, y, x, m, rgb):
    """Draw a boolean mask at (y, x), clipped to dst."""
    gh, gw = m.shape
    y0, x0 = max(0, y), max(0, x)
    y1, x1 = min(dst.shape[0], y + gh), min(dst.shape[1], x + gw)
    if y1 <= y0 or x1 <= x0:
        return gw
    dst[y0:y1, x0:x1][m[y0 - y:y1 - y, x0 - x:x1 - x]] = rgb
    return gw


def _blit_rgba(dst, y, x, rgba):
    """Alpha-composite an RGBA uint8 image onto dst at (y, x), clipped."""
    gh, gw = rgba.shape[:2]
    y0, x0 = max(0, y), max(0, x)
    y1, x1 = min(dst.shape[0], y + gh), min(dst.shape[1], x + gw)
    if y1 <= y0 or x1 <= x0:
        return gw
    sub = rgba[y0 - y:y1 - y, x0 - x:x1 - x]
    a = sub[..., 3:4].astype(np.float32) / 255.0
    reg = dst[y0:y1, x0:x1].astype(np.float32)
    reg *= (1.0 - a)
    reg += sub[..., :3].astype(np.float32) * a
    dst[y0:y1, x0:x1] = reg.astype(np.uint8)
    return gw


def load_logo():
    """The Sofar logomark, pre-scaled to RGBA sidecars next to this file (a
    small credit mark and a large splash mark) so the demo needs no image
    library. Returns {name: array}, empty if the sidecar is absent."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "waverose-logo.npz")
    try:
        with np.load(path) as z:
            return {k: z[k] for k in z.files}
    except Exception:                                        # noqa: BLE001
        return {}


def text_mask(s, scale=1):
    s = str(s).upper()
    if not s:
        return np.zeros((GLYPH_H * scale, 1), bool)
    out = np.zeros((GLYPH_H, len(s) * (GLYPH_W + 1) - 1), bool)
    for i, ch in enumerate(s):
        out[:, i * (GLYPH_W + 1):i * (GLYPH_W + 1) + GLYPH_W] = \
            _GLYPHS.get(ch, _GLYPHS[" "])
    if scale > 1:
        out = np.repeat(np.repeat(out, scale, 0), scale, 1)
    return out


def text_width(s, scale=1):
    n = len(str(s))
    return max(1, (n * (GLYPH_W + 1) - 1) * scale) if n else 1


def text_height(scale=1):
    return GLYPH_H * scale


def blit_text(dst, y, x, s, rgb, scale=1):
    """Draw a string at (y, x), clipped to dst. Returns the width drawn."""
    m = text_mask(s, scale)
    gh, gw = m.shape
    y0, x0 = max(0, y), max(0, x)
    y1, x1 = min(dst.shape[0], y + gh), min(dst.shape[1], x + gw)
    if y1 <= y0 or x1 <= x0:
        return gw
    sub = m[y0 - y:y1 - y, x0 - x:x1 - x]
    dst[y0:y1, x0:x1][sub] = rgb
    return gw


def blit_name(dst, y, x, s, rgb):
    """Like blit_text, but draws the tilde over any N-with-tilde. Needs two
    rows of clear margin above `y`; the caller gives it that headroom."""
    s = str(s).upper()
    cx = x
    for ch in s:
        blit_text(dst, y, cx, ch, rgb)
        if ch == "Ñ":
            _blit_mask(dst, y - 2, cx, TILDE, rgb)
        cx += GLYPH_W + 1
    return max(1, cx - x - 1)


POINTS = ("N NNE NE ENE E ESE SE SSE S SSW SW WSW W WNW NW NNW").split()


def compass(deg):
    if deg is None:
        return ""
    return POINTS[int((float(deg) % 360.0) / 22.5 + 0.5) % 16]


def feet(metres):
    if metres is None:
        return "--"
    ft = float(metres) * M_FT
    return "%.*fFT" % (1 if ft < 0.95 else 0, ft)


def ago(seconds):
    if seconds is None:
        return "AGE UNKNOWN"
    s = max(0.0, float(seconds))
    if s < 90:
        return "JUST NOW"
    if s < 5400:
        return "%d MIN AGO" % int(s / 60)
    if s < 129600:
        return "%d HR AGO" % int(s / 3600)
    return "%d DAYS AGO" % int(s / 86400)


# --------------------------------------------------------------------------
# Reading what ftdata left behind. load() hands back a payload and an age and
# never raises; the three ways content can still be wrong -- no record, a stale
# fetch, a stale observation -- are told apart here, as in swell.py.
# --------------------------------------------------------------------------

def read_spotter(cache_dir, spotter):
    got = ftdata.load(PRODUCT + spotter, cache_dir)
    if got is None:
        return None, "no cached record for spotter %s" % spotter
    payload, age = got
    if not isinstance(payload, dict):
        return None, "spotter record is malformed"

    spectra = payload.get("spectra") or []
    freq = payload.get("freq") or []
    if not spectra or not freq:
        return None, "record carries no spectra"

    nf = len(freq)
    ts, E, D, S = [], [], [], []
    for s in spectra:
        e, d, sp = s.get("e"), s.get("d"), s.get("s")
        if (s.get("t") is None or not e or len(e) != nf
                or len(d) != nf or len(sp) != nf):
            continue
        ts.append(float(s["t"]))
        E.append(e)
        D.append(d)
        S.append(sp)
    if not ts:
        return None, "no usable spectra in record"

    obs_t = float(payload.get("obs_t") or ts[-1])
    state = {
        "spotter": spotter,
        "name": str(payload.get("name") or spotter).upper(),
        "freq": np.asarray(freq, f32),
        "period": 1.0 / np.maximum(np.asarray(freq, f32), 1e-6),
        "t": np.asarray(ts, np.float64),
        "E": np.asarray(E, f32),
        "D": np.asarray(D, f32),
        "S": np.asarray(S, f32),
        "hs": payload.get("hs"),
        "tp": payload.get("tp"),
        "tm": payload.get("tm"),
        "pdir": payload.get("pdir"),
        "mdir": payload.get("mdir"),
        "pspread": payload.get("pspread"),
        "waves": payload.get("waves") or [],
        "lat": payload.get("lat"), "lon": payload.get("lon"),
        "obs_t": obs_t,
        "obs_age": max(0.0, time.time() - obs_t) if obs_t else None,
        "age": age,
    }
    return state, None


def spectrum_at(state, tc):
    """The energy / direction / spread arrays at epoch tc, interpolated.

    Linear on energy and spread, shortest-arc on the circular direction, so a
    lobe that veers from 300 to 020 over the record swings through north rather
    than unwinding the long way round the compass.
    """
    ts = state["t"]
    E, D, S = state["E"], state["D"], state["S"]
    n = len(ts)
    if n == 1:
        return E[0], D[0], S[0]
    if tc <= ts[0]:
        return E[0], D[0], S[0]
    if tc >= ts[-1]:
        return E[-1], D[-1], S[-1]
    k = int(np.searchsorted(ts, tc) - 1)
    k = max(0, min(n - 2, k))
    span = ts[k + 1] - ts[k]
    f = 0.0 if span <= 0 else float((tc - ts[k]) / span)
    e = E[k] * (1.0 - f) + E[k + 1] * f
    s = S[k] * (1.0 - f) + S[k + 1] * f
    dd = ((D[k + 1] - D[k] + 180.0) % 360.0) - 180.0
    d = (D[k] + f * dd) % 360.0
    return e, d, s


# --------------------------------------------------------------------------
# Geometry of the rose, baked once: for every pixel in the rose box, which
# frequency bin its radius lands on (by period) and what compass bearing it
# points, plus the disc mask.
# --------------------------------------------------------------------------

def rose_geometry(R, period_bins):
    """period_bins: the buoy's periods, ascending in frequency (so descending
    in period). Returns (fidx, ang, mask), each (2R+1, 2R+1)."""
    d = 2 * R + 1
    yy, xx = np.mgrid[0:d, 0:d].astype(f32)
    dx = xx - R
    dy = yy - R
    rr = np.sqrt(dx * dx + dy * dy)
    mask = rr <= R + 0.5
    # Radius -> period (T_MIN at centre, T_MAX at rim) -> frequency -> bin.
    tt = T_MIN + np.clip(rr / max(R, 1), 0.0, 1.0) * (T_MAX - T_MIN)
    ff = 1.0 / tt
    freqs = 1.0 / np.maximum(period_bins, 1e-6)          # ascending
    order = np.argsort(freqs)
    fs = freqs[order]
    idx = np.searchsorted(fs, ff.ravel())
    idx = np.clip(idx, 0, len(fs) - 1)
    # nearest of the bracketing pair
    lo = np.clip(idx - 1, 0, len(fs) - 1)
    pick = np.where(np.abs(fs[idx] - ff.ravel())
                    <= np.abs(fs[lo] - ff.ravel()), idx, lo)
    fidx = order[pick].reshape(d, d).astype(np.intp)
    # Bearing: north is up (-y), clockwise, degrees.
    ang = (np.degrees(np.arctan2(dx, -dy)) % 360.0).astype(f32)
    return fidx, ang, mask


# --------------------------------------------------------------------------
# The static furniture: headline, compass ring, spectrogram.
# --------------------------------------------------------------------------

class Layout(object):
    def __init__(self, w, h):
        self.w, self.h = w, h
        # Tall enough headline band to carry the tilde over ANO in row zero.
        self.top_h = 8 if h >= 44 else (6 if h >= 40 else 0)
        self.head_y = 2 if self.top_h >= 7 else 0
        self.bot_h = 6 if h >= 52 else 0            # time axis band
        self.body_y0 = self.top_h + 1
        self.body_y1 = h - self.bot_h - 1
        body_h = max(8, self.body_y1 - self.body_y0)
        self.R = max(6, min(body_h // 2, (self.body_y1 - self.body_y0) // 2))
        self.cy = (self.body_y0 + self.body_y1) // 2
        self.cx = 2 + self.R
        # Spectrogram fills whatever is right of the rose.
        self.sg_x0 = self.cx + self.R + 6
        self.sg_x1 = w - 2
        self.sg_y0 = self.body_y0
        self.sg_y1 = self.body_y1
        self.has_sg = (self.sg_x1 - self.sg_x0) >= 24


def draw_ring(frame, lay):
    """A faint compass ring around the rose with N/E/S/W ticks."""
    cy, cx, R = lay.cy, lay.cx, lay.R
    d = 2 * R + 1
    yy, xx = np.mgrid[0:d, 0:d].astype(f32)
    rr = np.sqrt((xx - R) ** 2 + (yy - R) ** 2)
    ring = (np.abs(rr - R) <= 0.7)
    y0, x0 = cy - R, cx - R
    box = frame[y0:y0 + d, x0:x0 + d]
    if box.shape[:2] == ring.shape:
        box[ring] = C_RING
    # Cardinal ticks just outside the disc.
    for deg, col in ((0, C_RING_N), (90, C_RING), (180, C_RING), (270, C_RING)):
        a = math.radians(deg)
        for rad in (R + 1, R + 2):
            ty = int(round(cy - rad * math.cos(a)))
            tx = int(round(cx + rad * math.sin(a)))
            if 0 <= ty < lay.h and 0 <= tx < lay.w:
                frame[ty, tx] = col


def build_spectrogram(frame, lay, state, lut, escale, hours_span):
    """Bake the last `hours_span` hours of spectra into the right-hand strip.

    x is time (right is now), y is period (bottom is the long swell), colour is
    energy on the same scale as the rose. Columns are interpolated so a record
    of sixteen half-hourly frames does not draw as sixteen fat bars.
    """
    if not lay.has_sg:
        return
    x0, x1 = lay.sg_x0, lay.sg_x1
    y0, y1 = lay.sg_y0, lay.sg_y1
    sgw = x1 - x0
    sgh = y1 - y0
    if sgw < 2 or sgh < 2:
        return
    t_now = float(state["t"][-1])
    t_first = max(float(state["t"][0]), t_now - hours_span * 3600.0)
    span = max(1.0, t_now - t_first)
    # Row -> period: bottom row is T_MAX (swell), top row is T_MIN (chop).
    rows = np.arange(sgh)
    per = T_MAX - (rows / max(1, sgh - 1)) * (T_MAX - T_MIN)
    fq = 1.0 / per
    freqs = state["freq"]
    order = np.argsort(freqs)
    fs = freqs[order]
    ridx = np.clip(np.searchsorted(fs, fq), 0, len(fs) - 1)
    rlo = np.clip(ridx - 1, 0, len(fs) - 1)
    rpick = np.where(np.abs(fs[ridx] - fq) <= np.abs(fs[rlo] - fq), ridx, rlo)
    row_bin = order[rpick]                                # (sgh,) bin per row
    strip = frame[y0:y1, x0:x1]
    for cx in range(sgw):
        tc = t_first + span * (cx / max(1, sgw - 1))
        e, _, _ = spectrum_at(state, tc)
        col_e = np.clip(e[row_bin] * escale, 0.0, 1.0) ** GAMMA
        strip[:, cx] = lut[(col_e * 255).astype(np.intp)]
    # A faint six-hour grid and a base line, so the strip reads as time.
    for hh in range(6, int(hours_span) + 1, 6):
        gx = x1 - 1 - int(round((hh * 3600.0) / span * (sgw - 1)))
        if x0 <= gx < x1:
            frame[y0:y1, gx] = np.maximum(frame[y0:y1, gx], np.array(C_GRID))


def draw_card(frame, lay, lines):
    total = sum(text_height(sc) + 3 for _, _, sc in lines)
    y = max(0, (lay.h - total) // 2)
    for text, col, sc in lines:
        x = max(0, (lay.w - text_width(text, sc)) // 2)
        blit_text(frame, y, x, text, col, sc)
        y += text_height(sc) + 3


# --------------------------------------------------------------------------
# Options.
# --------------------------------------------------------------------------

def add_arguments(ap):
    ap.add_argument("--cache-dir", default=None,
                    help="ftdata cache to read (default: ftdata's own)")
    ap.add_argument("--spotter", default=SPOTTER,
                    help="Sofar Spotter id whose spectrum to draw")
    ap.add_argument("--hours", type=float, default=12.0,
                    help="hours of history across the spectrogram and the loop")
    ap.add_argument("--sweep", type=float, default=13.0,
                    help="seconds for the playhead to cross the whole history")
    ap.add_argument("--hold", type=float, default=4.0,
                    help="seconds the playhead holds at now before looping")
    ap.add_argument("--emax", type=float, default=0.0,
                    help="fixed energy full-scale in m2/Hz; 0 self-scales to "
                         "the record's own peak")
    ap.add_argument("--reload", type=float, default=600.0,
                    help="seconds between re-reads of the cache (0 = never)")
    ap.add_argument("--intro", type=float, default=3.4,
                    help="seconds of Sofar logomark intro before a rising tide "
                         "washes it away to reveal the spectrum; 0 disables")
    ap.add_argument("--no-logo", action="store_true",
                    help="skip the Sofar logomark intro entirely")


# --------------------------------------------------------------------------
# build()
# --------------------------------------------------------------------------

def build(args):
    w, h = args.width, args.height
    lay = Layout(w, h)
    cache = args.cache_dir
    spotter = args.spotter
    lut = _ramp_lut(E_RAMP)
    logos = {} if args.no_logo else load_logo()

    cell = {"loaded": -1e18, "state": None, "card": None, "base": None,
            "fidx": None, "ang": None, "mask": None, "escale": 1.0,
            "rose": None, "bg": None, "splash": None,
            "intro": max(0.0, float(args.intro)),
            "yy": np.arange(h, dtype=f32)[:, None]}

    # Intro splash, built once: the large logomark held on black with the SOFAR
    # OCEAN name under it. Its real image, scaled in load_logo(); no redraw.
    big = logos.get("logo_big")
    if big is not None and cell["intro"] > 0 and h >= 24:
        splash = np.zeros((h, w, 3), np.uint8)
        splash[:] = C_BG
        lh, lw = big.shape[:2]
        ly = max(0, h // 2 - lh // 2 - 3)
        _blit_rgba(splash, ly, max(0, (w - lw) // 2), big)
        cap = "SOFAR OCEAN"
        blit_text(splash, min(h - 6, ly + lh + 2),
                  max(0, (w - text_width(cap)) // 2), cap, C_CREDIT)
        cell["splash"] = splash
    if cell["splash"] is None:
        cell["intro"] = 0.0

    def make_card(lines):
        base = np.zeros((h, w, 3), np.uint8)
        base[:] = C_BG
        draw_card(base, lay, lines)
        cell["card"] = base

    def prepare(state):
        cell["card"] = None
        base = np.zeros((h, w, 3), np.uint8)
        base[:] = C_BG

        # Energy full-scale: fixed if asked, else the record's own peak (with a
        # floor so a flat-calm sea is not amplified into noise).
        if args.emax and args.emax > 0:
            peak = float(args.emax)
        else:
            peak = float(np.max(state["E"])) if state["E"].size else E_FLOOR
        cell["escale"] = 1.0 / max(peak, E_FLOOR)

        draw_ring(base, lay)
        build_spectrogram(base, lay, state, lut, cell["escale"], args.hours)

        # Headline: name (with its tilde), height, peak period, peak bearing.
        if lay.top_h:
            hy = lay.head_y
            xx = 1
            xx += blit_name(base, hy, xx, state["name"][:12], C_TEXT) + 4
            xx += blit_text(base, hy, xx, feet(state["hs"]), C_SWELL) + 3
            if state["tp"]:
                xx += blit_text(base, hy, xx, "%dS" % int(round(state["tp"])),
                                C_PERIOD) + 3
            pk = compass(state["pdir"])
            if pk:
                xx += blit_text(base, hy, xx, pk, C_DIRN) + 3

        # Time axis under the spectrogram.
        if lay.bot_h and lay.has_sg:
            ay = lay.h - lay.bot_h + 1
            blit_text(base, ay, lay.sg_x1 - text_width("NOW"), "NOW", C_DIM)
            blit_text(base, ay, lay.sg_x0, "-%dH" % int(args.hours), C_DIM)

        # Rose geometry for this record's frequency grid.
        fidx, ang, mask = rose_geometry(lay.R, state["period"])
        cell["fidx"] = fidx
        cell["ang"] = ang
        cell["mask"] = mask
        cell["rose"] = np.empty((2 * lay.R + 1, 2 * lay.R + 1, 3), np.uint8)
        cell["bg"] = base[lay.cy - lay.R:lay.cy + lay.R + 1,
                          lay.cx - lay.R:lay.cx + lay.R + 1].copy()
        cell["base"] = base
        cell["lut"] = lut

    def reload_data():
        cell["loaded"] = time.monotonic()
        state, err = read_spotter(cache, spotter)
        cell["state"] = state
        if state is None:
            make_card([("NO SPOTTER DATA", C_WARN, 1),
                       ("RUN FTDATA.PY --ONCE", C_TEXT, 1),
                       ((err or "")[:52].upper(), C_DIM, 1)])
            return
        obs = state["obs_age"]
        if obs is None or obs > OBS_DEAD:
            make_card([("%s SILENT" % state["name"][:12], C_WARN, 1),
                       ("LAST SPECTRUM %s" % ago(obs), C_DIM, 1),
                       ("FETCHED %s" % ago(state["age"]), C_DIM, 1)])
            return
        prepare(state)

    reload_data()

    def loop_time(t):
        """Playhead epoch as a function of wall seconds: sweep, then hold."""
        state = cell["state"]
        t_now = float(state["t"][-1])
        t_first = max(float(state["t"][0]), t_now - args.hours * 3600.0)
        cycle = max(0.1, args.sweep + args.hold)
        # The sweep begins when the reveal does, so the first thing the wash
        # uncovers is the oldest spectrum, not the middle of a cycle.
        te = max(0.0, t - cell["intro"])
        phase = te % cycle
        if phase < args.sweep:
            frac = phase / args.sweep
        else:
            frac = 1.0
        return t_first + (t_now - t_first) * frac, t_first, t_now

    def intro_frame(main, t):
        """The Sofar logomark, held then washed away by a rising tide to reveal
        `main`. Only runs for the first `cell['intro']` seconds."""
        splash = cell["splash"]
        intro = cell["intro"]
        hold = intro * INTRO_HOLD_FRAC
        if t < 0.4:                                  # fade up from black
            return (splash.astype(f32) * (t / 0.4)).astype(np.uint8)
        if t <= hold:
            return splash
        p = (t - hold) / max(1e-3, intro - hold)     # 0..1 wash progress
        cols = np.arange(w)
        base_y = h + WASH_FOAM - p * (h + 2 * WASH_AMP + 2 * WASH_FOAM)
        wl = base_y + WASH_AMP * np.sin(cols * 0.06 + t * WASH_SPEED)
        rel = cell["yy"] - wl[None, :]               # (h, w): below the line > 0
        below = rel >= 0.0
        # The mark dissolves as the water climbs, rather than merely hiding.
        spl = (splash.astype(f32) * (1.0 - 0.85 * p)).astype(np.uint8)
        out = np.where(below[..., None], main, spl)
        out[np.abs(rel) < 1.2] = C_FOAM              # the crest
        glow = (rel >= 1.2) & (rel < 3.2)            # a lit skirt under it
        out[glow] = np.clip(out[glow].astype(np.int16) + 44, 0, 255
                            ).astype(np.uint8)
        return out

    def render(t, i):
        if args.reload and time.monotonic() - cell["loaded"] >= args.reload:
            reload_data()
        if cell["card"] is not None:
            return cell["card"]
        state = cell["state"]
        base = cell["base"]
        frame = base.copy()
        R = lay.R

        tc, t_first, t_now = loop_time(t)
        e, d, s = spectrum_at(state, tc)

        # The rose: energy at each pixel's period, aimed by a bearing-centred
        # bell of the measured width. A slow breath keeps it alive between the
        # buoy's half-hourly steps without changing what it claims.
        fidx = cell["fidx"]
        emap = e[fidx]
        dmap = d[fidx]
        smap = np.maximum(s[fidx], SIG_MIN)
        angd = ((cell["ang"] - dmap + 180.0) % 360.0) - 180.0
        wgt = np.exp(-0.5 * (angd / smap) ** 2)
        wgt = np.clip((wgt - DIR_FLOOR) / (1.0 - DIR_FLOOR), 0.0, 1.0)
        breath = 1.0 + 0.06 * math.sin(t * 1.7)
        energy = np.clip(emap * wgt * cell["escale"] * breath, 0.0, 1.0) ** GAMMA
        rose = cell["lut"][(energy * 255).astype(np.intp)]
        rose[~cell["mask"]] = cell["bg"][~cell["mask"]]
        frame[lay.cy - R:lay.cy + R + 1, lay.cx - R:lay.cx + R + 1] = rose

        # A short pointer from the centre toward the peak bearing, so the eye is
        # given the headline direction even when the lobe is broad.
        if state["pdir"] is not None:
            a = math.radians(float(state["pdir"]))
            for rad in range(2, R - 1):
                py = int(round(lay.cy - rad * math.cos(a)))
                px = int(round(lay.cx + rad * math.sin(a)))
                if 0 <= py < lay.h and 0 <= px < lay.w:
                    frame[py, px] = np.maximum(frame[py, px],
                                               np.array(C_PLAY_DIM))

        # The playhead on the spectrogram, and the clock at its foot.
        if lay.has_sg:
            span = max(1.0, t_now - t_first)
            gx = lay.sg_x1 - 1 - int(round((t_now - tc) / span
                                           * (lay.sg_x1 - lay.sg_x0 - 1)))
            gx = max(lay.sg_x0, min(lay.sg_x1 - 1, gx))
            frame[lay.sg_y0:lay.sg_y1, gx] = C_PLAY
            if lay.bot_h:
                lt = time.localtime(tc)
                clk = "%02d:%02d" % (lt.tm_hour, lt.tm_min)
                cxk = min(lay.sg_x1 - text_width(clk),
                          max(lay.sg_x0, gx - 9))
                # Not over either edge label: -NH at the left and NOW at the
                # right already mark those ends, and the clock would overprint.
                left_x = lay.sg_x0 + text_width("-%dH" % int(args.hours)) + 3
                now_x = lay.sg_x1 - text_width("NOW") - 2
                if cxk > left_x and cxk + text_width(clk) < now_x:
                    blit_text(frame, lay.h - lay.bot_h + 1, cxk, clk, C_TEXT)

        # Observation age, called out only when it is old enough to matter.
        obs = state["obs_age"]
        if obs is not None and obs > OBS_WARN and lay.top_h:
            msg = "STALE %s" % ago(obs)
            blit_text(frame, lay.head_y, lay.w - text_width(msg) - 1, msg,
                      C_WARN)

        if t < cell["intro"] and cell["splash"] is not None:
            return intro_frame(frame, t)
        return frame

    render.state = cell
    render.layout = lay
    return render


def main():
    ds.standalone(sys.modules[__name__],
                  "the directional wave spectrum off Ano Nuevo as a polar rose",
                  fps=20)


if __name__ == "__main__":
    main()
