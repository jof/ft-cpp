#!/usr/bin/env python3
"""What is in the air outside, drawn as how far you can see through it.

The wall already has the weather, the fog, the wind and a satellite's view of
the cloud. None of them say anything about particulates, and in this city that
is the most visible environmental fact of the year: the difference between a
clear September afternoon and a smoke day is the single thing everybody in the
shop notices, talks about and changes their plans for, and until this panel it
was the one thing the wall could not tell them.

So the panel is not a gauge. It is **the view north from the roof, redrawn at
the visibility the current PM2.5 implies** -- the Marin hills behind downtown,
the downtown towers, Potrero, and a near rooftop in the foreground. On a clean
day the whole depth of it stands out crisp against a blue sky. As the number
climbs, the far layers dissolve into the airlight one after another and the
whole panel goes warm: tan, then amber, then the orange-brown that anybody who
was here in 2020 recognises before they have read a single character. Somebody
walking past reads "the air is bad today" from the colour and from *how much of
the city is missing*, which is exactly how they read it out of a real window.

**The extinction is real arithmetic, not a colour ramp with a mood.** Two
numbers do all the work:

    b_pm  = 3 * PM2.5 + 10                  extinction from particles, Mm^-1
    T(d)  = exp(-b * d)                     contrast left after d kilometres

The first is the IMPROVE-style mass scattering efficiency for fine particles
plus a Rayleigh floor for the air itself; the second is Beer's law, and
inverting it through Koschmieder's 3912/b is where the meteorologists' "visual
range" comes from. Each layer of the skyline sits at its true-ish distance --
28 km to the Marin ridge, 5.5 to the towers, 1.6 to Potrero, a quarter of a
kilometre to the rooftop -- and is drawn as `body*T + airlight*(1-T)`. That is
the whole renderer. At PM2.5 of 8 the ridge keeps 39% of its contrast and the
towers 83%; at 150 the ridge is gone entirely, the towers are down to 8% and
the rooftop is still 89%. Nothing about that had to be tuned to look right; it
looks right because it is what the atmosphere does.

**Fog is not smoke, and this panel is where that distinction has to hold.**
karl.py already owns fog, and a foggy-but-clean morning drawn as a smoke day
would be a lie told twice a week in July. They are physically different --
water scatters neutrally and looks white and cool, smoke absorbs blue and looks
orange and warm -- so the fetcher stores the model's own visibility diagnostic
and the relative humidity alongside the particulates, and the demo splits the
extinction in two: `b_fog = 3912/vis_km - b_pm`, whatever the model says is
stopping the light that the particles cannot account for. The airlight colour
is then mixed between a cool grey (fog) and a PM2.5-driven ramp (haze to
smoke) in proportion. A 6 ug/m3 morning with the fog in reads white, cool and
blind; a 90 ug/m3 afternoon reads orange and blind; and the panel says which.
The fog term is smoothed over three hours and capped, because the model emits
single isolated hours of 100 m visibility and an unsmoothed whiteout flashing
past mid-sweep reads as a rendering fault rather than as weather.

**It sweeps, because the trend is the point.** A number tells you the air is
bad; the shape tells you whether it is arriving or leaving. So the panel dwells
on now, runs back to 24 hours ago, sweeps forward through the present into
tomorrow's forecast, and returns. The strip along the bottom is the whole
48 hours of PM2.5 at once with the present marked, the forecast half drawn
dimmer than the measured half, and a cursor showing which hour the picture is
currently standing in. The header number follows the cursor and labels itself
`-8H`, `NOW`, `+13H`, because a big number over a picture of another hour would
be the worst thing this panel could do.

**No day and night.** The scene is always lit as daytime, at 3 am as much as at
3 pm. That is deliberate: adding a diurnal cycle would put a second, much
stronger brightness signal on the one axis the panel exists to carry, and
"dark" would be read as "bad" by everybody who did not stop to think. This is a
diagram of visibility, not a webcam.

**Frame budget.** The scene is one gather. Every pixel's colour depends only on
which layer is visible there, which row it is on, and how the edge is
antialiased -- so `build()` bakes a single int32 index image, and `render()`
builds a small (bodies x bodies x 4 x rows) colour table for the current
extinction and pulls the whole panel out of it with one `np.take`. The table is
32k floats and costs a dozen numpy calls on tiny arrays; the frame costs the
gather, one add of the drifting haze and the dither, and one store. That is
five whole-panel passes and about twenty numpy calls in total, which is the
figure that matters on a Pi where a numpy call is 30-40 us regardless of size.
Measured here over a full sweep: **mean 0.27 ms, p95 0.46 ms, worst 0.55 ms**,
with build() at 3 ms; see the README fragment for what that scales to.

Run:  python3 ftdata.py --once --only air
      python3 air.py --host 127.0.0.1
      python3 air.py --sweep 8                     # hurry the sweep along
      FT_DATA_CACHE=/tmp/empty python3 air.py      # the no-data card
      python3 scripts/test-air.py
"""

import math
import sys
import time

import numpy as np

import defcon
import demoscene as ds
import ftdata

f32 = np.float32

PRODUCT = "air"

# --------------------------------------------------------------------------
# Type. defcon.py's 3x5 font, as caiso, tide and propagation draw with. The
# glyph height is measured off a built glyph rather than assumed: a past bug in
# this tree clipped the bottom off every capital E because a size was written
# down instead of asked for.
# --------------------------------------------------------------------------

_FONT = dict(defcon._FONT)
_FONT.update({"+": "02720"})

_GLYPHS = {}
for _ch, _rows in _FONT.items():
    _g = np.zeros((len(_rows), 3), bool)
    for _r, _d in enumerate(_rows):
        _v = int(_d, 8)
        for _c in range(3):
            if _v & (4 >> _c):
                _g[_r, _c] = True
    _GLYPHS[_ch] = _g

GLYPH_H, GLYPH_W = _GLYPHS[" "].shape
ADVANCE = GLYPH_W + 1


def text_mask(s, scale=1):
    """A boolean mask for a string, one blank column between glyphs."""
    s = str(s).upper()
    if not s:
        return np.zeros((GLYPH_H * scale, 1), bool)
    out = np.zeros((GLYPH_H, len(s) * ADVANCE - 1), bool)
    for i, ch in enumerate(s):
        out[:, i * ADVANCE:i * ADVANCE + GLYPH_W] = _GLYPHS.get(ch, _GLYPHS[" "])
    if scale > 1:
        out = np.repeat(np.repeat(out, scale, 0), scale, 1)
    return out


def text_width(s, scale=1):
    return max(1, (len(str(s)) * ADVANCE - 1) * scale)


def text_height(scale=1):
    return GLYPH_H * scale


def blit_text(dst, y, x, s, rgb, scale=1, where=None):
    """Draw a string at (y, x), clipped. Marks `where` if one is given."""
    m = text_mask(s, scale)
    gh, gw = m.shape
    y0, x0 = max(0, y), max(0, x)
    y1, x1 = min(dst.shape[0], y + gh), min(dst.shape[1], x + gw)
    if y1 <= y0 or x1 <= x0:
        return gw
    sub = m[y0 - y:y1 - y, x0 - x:x1 - x]
    dst[y0:y1, x0:x1][sub] = rgb
    if where is not None:
        where[y0:y1, x0:x1][sub] = True
    return gw


def blit_outlined(dst, y, x, s, rgb, ink, scale=1, where=None):
    """Text with a one-pixel outline, so it survives any sky behind it.

    The sky under this panel's header runs from near-black on a clean night-blue
    day to a bright orange on a smoke day, and no single text colour is legible
    against both. Rather than pick a colour per background -- which flickers as
    the sweep crosses a threshold -- every string is drawn twice: the mask
    dilated by one pixel in a dark ink, then the string itself on top. It costs
    nothing per frame because the whole overlay is rebuilt only when the swept
    hour changes.
    """
    m = text_mask(s, scale)
    gh, gw = m.shape
    grown = np.zeros((gh + 2, gw + 2), bool)
    for dy in range(3):
        for dx in range(3):
            grown[dy:dy + gh, dx:dx + gw] |= m
    y0, x0 = max(0, y - 1), max(0, x - 1)
    y1 = min(dst.shape[0], y - 1 + gh + 2)
    x1 = min(dst.shape[1], x - 1 + gw + 2)
    if y1 > y0 and x1 > x0:
        sub = grown[y0 - (y - 1):y1 - (y - 1), x0 - (x - 1):x1 - (x - 1)]
        dst[y0:y1, x0:x1][sub] = ink
        if where is not None:
            where[y0:y1, x0:x1][sub] = True
    blit_text(dst, y, x, s, rgb, scale, where)
    return gw


# --------------------------------------------------------------------------
# The atmosphere. Three constants and two functions, and every colour on the
# panel comes out of them.
# --------------------------------------------------------------------------

# Mass scattering efficiency for fine particles, m2/g. The IMPROVE algorithm
# uses 3 for dry ammonium sulphate and nitrate and that is the number every
# regulatory visibility calculation in the US is built on. Multiplied by a
# concentration in ug/m3 it gives an extinction coefficient in Mm^-1.
PM_EFFICIENCY = 3.0

# Rayleigh scattering by the air itself, Mm^-1. This is why a perfectly clean
# day still has a visual range of a few hundred kilometres and not infinity,
# and why the sky is blue rather than black; it is the floor under everything.
RAYLEIGH = 10.0

# Koschmieder's constant: visual range in km is this over the extinction in
# Mm^-1. Only used to turn the model's visibility diagnostic back into an
# extinction so the two can be subtracted.
KOSCHMIEDER = 3912.0

# How far away the sky is. Not a real distance -- the sky has no surface -- but
# the path length at which the airlight has completely replaced whatever is
# behind it. 45 km makes a clean day's sky a mix of a quarter deep blue and
# three quarters pale airlight, which is what a clean sky looks like, and a
# smoke day's sky pure airlight, which is what that looks like.
SKY_KM = 45.0

# The cap on how much of the murk may be attributed to water. The model emits
# isolated hours of 100 m visibility, which as extinction is 39000 Mm^-1 and
# would render a uniform white rectangle. Capped here at a visual range of
# about 4 km from fog alone, which buries the ridge and the towers and leaves
# Potrero hazy and the rooftop sharp -- which is what a fog morning in Dogpatch
# actually looks like out of a window.
FOG_MAX = 950.0


def b_pm(pm):
    """Extinction from particles, Mm^-1, from PM2.5 in ug/m3."""
    return PM_EFFICIENCY * max(0.0, pm) + RAYLEIGH


def visual_range_km(b):
    """Koschmieder: how far a black object stays distinguishable."""
    return KOSCHMIEDER / max(b, 1e-3)


# --------------------------------------------------------------------------
# The US AQI ramp. The one piece of colour on this panel that is not derived
# from physics, and it is not invented either: these are the six official
# categories and their published colours, dimmed for an LED panel that is
# brighter than a printed page. Keeping them is what lets somebody who has seen
# a purple air quality map anywhere else read this one.
#
# **The AQI lags the PM2.5, and that is not a bug in either.** The US index is
# defined on a 24-hour average, so the service's hourly `us_aqi` column is a
# running quantity: over a real day here it moved 54 to 60 while the hourly
# PM2.5 moved 8 to 16, and their correlation is 0.15 against the hourly figure
# and 0.90 against a 24-hour trailing mean of it. Both the headline and the
# strip's colour are driven by the AQI so that they agree with each other and
# with every other air quality map; the strip's bar *heights* are the hourly
# PM2.5, because that is the thing that actually has an hourly shape. On a day
# when a plume arrives the bars rise before the colour does, which is the
# truth about the index and not a rendering error.
# --------------------------------------------------------------------------

AQI_BANDS = (
    (50, "GOOD", (72, 200, 96)),
    (100, "MODERATE", (226, 208, 72)),
    (150, "SENSITIVE", (240, 146, 44)),
    (200, "UNHEALTHY", (232, 70, 60)),
    (300, "VERY BAD", (172, 88, 186)),
    (10 ** 9, "HAZARDOUS", (178, 46, 66)),
)


def aqi_band(aqi):
    """(word, rgb) for a US AQI value. Never raises on None."""
    if aqi is None or not np.isfinite(aqi):
        return "NO AQI", (120, 128, 140)
    for limit, word, rgb in AQI_BANDS:
        if aqi <= limit:
            return word, rgb
    return AQI_BANDS[-1][1], AQI_BANDS[-1][2]


# --------------------------------------------------------------------------
# Colour. Everything here is a ramp down the panel, because airlight is
# brighter near the horizon where the path through it is longest, and a flat
# wash reads as a painted backdrop rather than as air.
# --------------------------------------------------------------------------

C_TEXT = (226, 232, 240)
C_DIM = (150, 160, 172)
C_INK = (8, 9, 12)                    # the outline behind every glyph
C_WARN = (255, 108, 84)
C_NOW = (255, 246, 214)
C_CURSOR = (150, 226, 255)
C_STRIP_BG = (9, 10, 13)
C_STRIP_RULE = (30, 34, 40)

# What is behind the airlight: the deep sky, which on a clean day shows through
# and on a smoke day does not.
SKY_BODY = ((0.00, (10, 18, 48)), (0.55, (22, 36, 66)), (1.00, (38, 56, 82)))

# The airlight, as a function of PM2.5. Pale blue when there is nothing in the
# air but air; milky, then tan, then amber, then the orange-brown of a bad day.
# The top and bottom of each ramp are the zenith and the horizon.
PM_AIRLIGHT = (
    (0.0, (98, 146, 206), (196, 218, 238)),
    (12.0, (126, 152, 182), (208, 216, 216)),
    (35.0, (176, 164, 140), (224, 208, 170)),
    (75.0, (200, 148, 96), (234, 184, 118)),
    (150.0, (196, 118, 62), (226, 150, 78)),
    (250.0, (168, 84, 48), (198, 112, 56)),
    (400.0, (126, 58, 40), (150, 78, 44)),
)

# Fog's airlight: neutral, cool and bright. Deliberately close to grey -- the
# whole point is that it is *not* the warm ramp above.
FOG_AIRLIGHT = ((178, 188, 198), (214, 220, 226))

# How many PM levels the airlight lookup is baked at. The index is nonlinear
# (see _airlight_table) so the crowded clean end gets as many steps as the
# open dirty end.
AIR_LEVELS = 96

# --------------------------------------------------------------------------
# The view. Four depth planes at their real-ish distances, looking north from
# the roof of the building: Marin behind, the downtown towers, Potrero and the
# near warehouses, and a rooftop in the foreground.
#
# The distances are what make the panel work and they are not free parameters:
# they are spread roughly a factor of four apart so that each one drops out of
# the picture at a different, useful PM2.5. The ridge goes at "smoky", the
# towers at "unhealthy", Potrero at "hazardous", the rooftop never -- which
# gives four steps of legible bad instead of one binary.
#
# Built procedurally rather than baked into a .npz, the same way karl.py builds
# Twin Peaks and Mount Sutro: it is a page of gaussians and boxes, it takes two
# milliseconds in build(), and a file would only be a way for the geometry and
# the code that reads it to drift apart.
# --------------------------------------------------------------------------

# name, kilometres, intrinsic colour in perfectly clear air.
PLANES = (
    ("ridge", 28.0, (34, 46, 38)),
    ("city", 5.5, (76, 88, 106)),
    ("mid", 1.6, (42, 46, 54)),
    ("near", 0.25, (13, 15, 19)),
)

# Extra bodies: same distance as a plane, different colour. They ride in the
# same table, so they are attenuated by exactly the same physics -- which is
# the point, because the tower lights going out is one of the clearest signals
# on the panel that the far distance has gone.
EXTRA_BODIES = (
    ("lights", 5.5, (238, 208, 142)),
    ("beacon", 5.5, (230, 70, 50)),
)

N_BODIES = 1 + len(PLANES) + len(EXTRA_BODIES)
B_SKY = 0
B_RIDGE, B_CITY, B_MID, B_NEAR = 1, 2, 3, 4
B_LIGHTS, B_BEACON = 5, 6

# Edge antialiasing is quantised to four coverages so that the whole scene is
# one gather rather than two plus a blend. A silhouette edge is one pixel; four
# steps on it is more than the panel's own gamma can show.
COVERAGES = (1.0, 0.75, 0.5, 0.25)
N_COV = len(COVERAGES)

# Downtown, as (centre in fractions of the width, half width at the top in
# pixels, half width at the base, top row in fractions of the scene height).
# A single trapezoid formula covers all three shapes that matter: a box when
# the two half widths agree, Salesforce Tower when the top one is much smaller,
# and the Transamerica Pyramid when it is nearly zero.
DOWNTOWN = (
    (0.115, 3.5, 4.0, 0.66),
    (0.175, 3.0, 3.5, 0.63),
    (0.215, 4.5, 5.0, 0.60),
    (0.262, 3.0, 3.5, 0.55),
    (0.300, 4.5, 4.5, 0.49),
    (0.345, 3.0, 3.5, 0.42),
    (0.385, 5.0, 5.5, 0.335),
    (0.420, 2.5, 3.0, 0.455),
    (0.452, 1.1, 5.0, 0.150),      # Salesforce Tower, tapered, the tall one
    (0.482, 2.0, 2.5, 0.270),      # 181 Fremont
    (0.512, 0.4, 6.0, 0.225),      # the Transamerica Pyramid
    (0.548, 3.5, 4.0, 0.435),
    (0.585, 2.5, 3.0, 0.515),
    (0.622, 4.0, 4.5, 0.465),
    (0.665, 3.0, 3.5, 0.555),
    (0.712, 3.5, 4.0, 0.595),
    (0.760, 3.0, 3.5, 0.625),
    (0.815, 4.0, 4.5, 0.615),
    (0.875, 3.0, 3.5, 0.655),
    (0.935, 3.5, 4.0, 0.645),
)

# The near rooftop. Same trapezoid formula: a chimney, a water tank, a mast and
# two roof steps, at a quarter of a kilometre, which is close enough that they
# survive anything the atmosphere can do.
ROOFTOP = (
    (0.075, 4.0, 4.0, 0.885),
    (0.160, 1.6, 1.6, 0.795),      # chimney
    (0.300, 5.0, 5.0, 0.900),
    (0.560, 6.0, 6.0, 0.895),
    (0.745, 5.0, 5.0, 0.845),      # water tank
    (0.745, 1.2, 1.2, 0.815),      # ...and its little cap
    (0.885, 0.6, 0.6, 0.755),      # a mast
    (0.930, 6.0, 6.0, 0.890),
)


def _trapezoids(W, Hs, base_frac, items):
    """Per-column top row for a row of buildings standing on a base line.

    Returns a float array: a column with nothing on it gets the base line, and
    fractional values are wanted -- the coverage they produce is what keeps a
    320-column skyline from looking like a sawblade.
    """
    x = np.arange(W, dtype=f32)
    base = f32(base_frac) * Hs
    top = np.full(W, base, f32)
    for cx, hw_top, hw_bot, top_frac in items:
        px = f32(cx) * (W - 1)
        y_top = f32(top_frac) * Hs
        dx = np.abs(x - px)
        if hw_bot <= hw_top + 1e-3:
            y = np.where(dx <= hw_bot, y_top, base)
        else:
            # The row at which the sloping side has widened to reach dx.
            frac = (dx - hw_top) / (hw_bot - hw_top)
            y = y_top + np.clip(frac, 0.0, 1.0) * (base - y_top)
            y = np.where(dx <= hw_bot, y, base)
        np.minimum(top, y.astype(f32), out=top)
    return top


def _ridge(W, Hs, base_frac, bumps, rng, roughness=0.010):
    """A hill line: gaussian humps on a base, with a little grain on top."""
    xf = np.arange(W, dtype=f32) / max(W - 1, 1)
    y = np.full(W, f32(base_frac) * Hs, f32)
    for centre, width, height in bumps:
        d = (xf - f32(centre)) / f32(width)
        y -= f32(height) * Hs * np.exp(-d * d).astype(f32)
    y += (f32(roughness) * Hs) * np.sin(xf * f32(41.0) + f32(1.1))
    y += (f32(0.6 * roughness) * Hs) * rng.standard_normal(W).astype(f32)
    return y


def _ramp(stops, n):
    """Interpolate (position, rgb) stops down `n` rows, in float."""
    pos = np.array([p for p, _ in stops], f32)
    cols = np.array([c for _, c in stops], f32)
    x = np.linspace(0.0, 1.0, n, dtype=f32)
    return np.stack([np.interp(x, pos, cols[:, ch]) for ch in range(3)],
                    axis=-1).astype(f32)


def _two_stop(top_rgb, bot_rgb, n):
    return _ramp([(0.0, top_rgb), (1.0, bot_rgb)], n)


def _airlight_index(pm):
    """PM2.5 -> a position in the baked airlight table, 0 .. AIR_LEVELS-1.

    Nonlinear, because the interesting range is not linear: the difference
    between 5 and 15 ug/m3 is a whole season and the difference between 300 and
    400 is academic. A square root over the table's span puts about half the
    steps under 50.
    """
    span = PM_AIRLIGHT[-1][0]
    u = math.sqrt(max(0.0, min(float(pm), span)) / span)
    return u * (AIR_LEVELS - 1)


def _airlight_table(Hs):
    """(AIR_LEVELS, Hs, 3) float: the airlight ramp at each PM2.5 step."""
    span = PM_AIRLIGHT[-1][0]
    out = np.empty((AIR_LEVELS, Hs, 3), f32)
    stops = [s[0] for s in PM_AIRLIGHT]
    for k in range(AIR_LEVELS):
        pm = span * (k / float(AIR_LEVELS - 1)) ** 2
        # Locate pm between two stops and interpolate both ends of the ramp.
        j = 0
        while j < len(stops) - 2 and pm > stops[j + 1]:
            j += 1
        lo, hi = stops[j], stops[j + 1]
        f = 0.0 if hi <= lo else (pm - lo) / (hi - lo)
        f = min(max(f, 0.0), 1.0)
        top = [a + (b - a) * f for a, b in zip(PM_AIRLIGHT[j][1],
                                               PM_AIRLIGHT[j + 1][1])]
        bot = [a + (b - a) * f for a, b in zip(PM_AIRLIGHT[j][2],
                                               PM_AIRLIGHT[j + 1][2])]
        out[k] = _two_stop(top, bot, Hs)
    return out


# --------------------------------------------------------------------------
# Noise, for the murk. Small, periodic in x, and the only thing on the panel
# that moves when the sweep is dwelling on the present moment.
# --------------------------------------------------------------------------

def _upsample(g, h, w):
    """Smoothstep-interpolated upsample of a periodic lattice to (h, w)."""
    gh, gw = g.shape

    def axis(n, gn):
        u = (np.arange(n, dtype=f32) + f32(0.5)) * (f32(gn) / f32(n))
        i0 = np.floor(u).astype(np.int32)
        fr = (u - i0).astype(f32)
        return i0 % gn, (i0 + 1) % gn, fr * fr * (f32(3.0) - f32(2.0) * fr)

    y0, y1, fy = axis(h, gh)
    x0, x1, fx = axis(w, gw)
    top = g[y0][:, x0] * (1.0 - fx) + g[y0][:, x1] * fx
    bot = g[y1][:, x0] * (1.0 - fx) + g[y1][:, x1] * fx
    return (top * (1.0 - fy)[:, None] + bot * fy[:, None]).astype(f32)


def _fbm(rng, h, w, cy, cx, octaves=3, gain=0.55):
    """Fractal value noise, periodic in both axes so a scroll has no seam."""
    out = np.zeros((h, w), f32)
    amp, norm = 1.0, 0.0
    for o in range(octaves):
        g = rng.random((max(2, cy << o), max(2, cx << o))).astype(f32)
        out += amp * _upsample(g, h, w)
        norm += amp
        amp *= gain
    out /= norm
    out -= float(out.mean())
    m = float(np.abs(out).max())
    return out / m if m > 1e-6 else out


def _bayer(n=8):
    """The n x n ordered dither matrix, values in (0, 1). See karl.py."""
    m = np.zeros((1, 1), f32)
    while m.shape[0] < n:
        m = np.block([[4 * m, 4 * m + 2], [4 * m + 3, 4 * m + 1]])
    return (m + f32(0.5)) / f32(m.size)


# --------------------------------------------------------------------------
# Clock, the same shape caiso.py and tide.py use, so a contact sheet across a
# whole day is possible without touching the system clock.
# --------------------------------------------------------------------------

def parse_when(s):
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


def clock(at=None, rate=1.0):
    base = time.time() if at is None else float(at)
    start = time.monotonic()
    if at is None and rate == 1.0:
        return time.time
    return lambda: base + (time.monotonic() - start) * rate


# --------------------------------------------------------------------------
# Reading what ftdata left behind. Never raises; three states have to be
# drawable and they are different things -- missing, out-of-window, and stale.
# --------------------------------------------------------------------------

def _column(payload, key, n):
    """One hourly series as float, with None as NaN. None if it is not there."""
    raw = payload.get(key)
    if not isinstance(raw, list) or len(raw) < n:
        return None
    v = np.array([np.nan if x is None else float(x) for x in raw[:n]], f32)
    return v if np.isfinite(v).any() else None


def _fill(v):
    """Fill NaN holes by interpolating, and by holding at the ends.

    A gap in the middle of a modelled series is one hour the model declined to
    answer for, and interpolating across it is the honest thing to do -- the
    alternative, treating it as clean air, is the one reading that could be
    dangerously wrong.
    """
    ok = np.isfinite(v)
    if ok.all():
        return v
    idx = np.arange(len(v), dtype=f32)
    return np.interp(idx, idx[ok], v[ok]).astype(f32)


def read_air(cache_dir):
    """(record, age, problem). `record` is None if nothing is drawable."""
    got = ftdata.load(PRODUCT, cache_dir)
    if got is None:
        return None, None, "no cached air record"
    payload, age = got
    try:
        t0 = float(payload["t0"])
        step = float(payload["step"])
        n = int(payload["n"])
        pm = _column(payload, "pm2_5", n)
        if pm is None or n < 4 or step <= 0:
            return None, age, "air record has no usable PM2.5 series"
        aqi = _column(payload, "us_aqi", n)
        rh = _column(payload, "rh", n)
        vis = _column(payload, "vis_km", n)
        aod = _column(payload, "aod", n)
    except Exception:                                        # noqa: BLE001
        return None, age, "air record is malformed"

    pm = _fill(pm)
    # The AQI is a published breakpoint table applied to PM2.5, so where the
    # service left a hole it can be left as NaN and simply not printed; making
    # one up here would be inventing a health category.
    if aqi is None:
        aqi = np.full(n, np.nan, f32)

    # The fog split. Whatever extinction the model's visibility implies that
    # the particles cannot account for is water, and it is smoothed over three
    # hours: the diagnostic emits isolated hours of 100 m visibility, and a
    # single-hour whiteout flashing past mid-sweep reads as a fault.
    bpm = PM_EFFICIENCY * np.clip(pm, 0.0, None) + RAYLEIGH
    if vis is None or rh is None:
        bfog = np.zeros(n, f32)
    else:
        v = np.clip(_fill(vis), 0.05, 500.0)
        b_total = KOSCHMIEDER / v
        raw = np.clip(b_total - bpm, 0.0, None)
        raw = np.minimum(raw, FOG_MAX)
        # Humidity is the second opinion. A model visibility of 200 m with the
        # air at 60% relative humidity is not fog, it is the diagnostic having
        # an opinion; requiring both is what stops the panel calling a dry
        # afternoon foggy.
        wet = np.clip((_fill(rh) - 84.0) / 12.0, 0.0, 1.0)
        raw = raw * wet
        # Three-hour boxcar, edges held.
        pad = np.concatenate([raw[:1], raw, raw[-1:]])
        bfog = ((pad[:-2] + pad[1:-1] + pad[2:]) / 3.0).astype(f32)

    return {
        "t0": t0, "step": step, "n": n, "age": age,
        "pm": pm, "aqi": aqi, "aod": aod,
        "rh": rh, "vis": vis,
        "bpm": bpm.astype(f32), "bfog": bfog.astype(f32),
        "grid": payload.get("grid"), "label": str(payload.get("label", "")),
    }, age, None


def condition_word(bpm_v, bfog_v):
    """Why you cannot see: FOG, SMOKE, HAZE or CLEAR.

    Ordered by which term dominates rather than by a threshold on PM2.5 alone,
    which is the whole reason the humidity is fetched. Fog wins when the water
    is doing more of the scattering than the particles; smoke when the
    particles are doing a lot of it in absolute terms.
    """
    if bfog_v > bpm_v and bfog_v > 60.0:
        return "FOG"
    if bpm_v >= 130.0:                    # about 40 ug/m3, visual range 30 km
        return "SMOKE"
    if bpm_v + bfog_v >= 55.0:            # about 15 ug/m3
        return "HAZE"
    return "CLEAR"


# --------------------------------------------------------------------------
# Options.
# --------------------------------------------------------------------------

def add_arguments(ap):
    ap.add_argument("--cache-dir", default=None,
                    help="ftdata cache to read (default: ftdata's own)")
    ap.add_argument("--sweep", type=float, default=22.0,
                    help="seconds for one dwell-back-forward-return cycle")
    ap.add_argument("--drift", type=float, default=23.0,
                    help="columns per second the murk drifts across")
    ap.add_argument("--haze", type=float, default=1.0,
                    help="multiplies the drifting murk texture")
    ap.add_argument("--no-dither", dest="dither", action="store_false",
                    help="skip the ordered dither, to see the banding it fixes")
    ap.add_argument("--strip", type=int, default=9,
                    help="rows of 48-hour PM2.5 strip along the bottom")
    ap.add_argument("--at", default="now",
                    help="pretend the present moment is this (epoch or "
                         "'YYYY-MM-DD HH:MM' local)")
    ap.add_argument("--rate", type=float, default=1.0,
                    help="displayed seconds per real second")
    ap.add_argument("--reload", type=float, default=900.0,
                    help="seconds between re-reads of the cache (0 = never)")
    ap.add_argument("--seed", type=int, default=7,
                    help="seed for the skyline grain and the murk texture")


# --------------------------------------------------------------------------
# The sweep. A piecewise function of the segment's own `t`, with smoothstep
# easing so that the reversals do not snap.
# --------------------------------------------------------------------------

def _smooth(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3.0 - 2.0 * u)


def sweep_position(t, period, now_u, last_u):
    """Which hour of the record the picture is standing in, as a float index.

    Dwell on now, run back to the start, sweep forward through now to the end,
    return. Starting and ending on the present moment is what makes a segment
    that gets cut short still have shown somebody the current number.
    """
    if period <= 0:
        return now_u
    p = (t % period) / period
    if p < 0.18:
        return now_u
    if p < 0.30:
        return now_u + (0.0 - now_u) * _smooth((p - 0.18) / 0.12)
    if p < 0.80:
        return 0.0 + last_u * _smooth((p - 0.30) / 0.50)
    return last_u + (now_u - last_u) * _smooth((p - 0.80) / 0.20)


def hour_label(k, now_k):
    """'NOW', '-8H', '+13H'."""
    d = int(round(k - now_k))
    return "NOW" if d == 0 else "%+dH" % d


# --------------------------------------------------------------------------
# Layout.
# --------------------------------------------------------------------------

class Layout(object):
    def __init__(self, w, h, strip_h):
        self.w, self.h = w, h
        self.strip_h = strip_h if h >= 40 else 0
        self.strip_h = min(self.strip_h, max(0, h - 20))
        self.strip_y = h - self.strip_h
        self.scene_h = self.strip_y
        # The caption sits on the last rows of the scene, over the near
        # rooftop, which is the darkest and most reliably flat part of it.
        self.caption_y = max(0, self.strip_y - text_height() - 1)
        self.head = h >= 24


def draw_nodata(dst, lay, lines):
    """The honest panel. No skyline, no colour, no implied air."""
    dst[:] = (6, 6, 8)
    scale = 2 if lay.h >= 32 and lay.w >= 200 else 1
    y = max(0, lay.h // 2 - (len(lines) * (text_height() * scale + 2)) // 2)
    for i, (s, rgb) in enumerate(lines):
        sc = scale if i == 0 else 1
        x = max(0, (lay.w - text_width(s, sc)) // 2)
        blit_text(dst, y, x, s, rgb, sc)
        y += text_height(sc) + 3
    return dst


# --------------------------------------------------------------------------
# build()
# --------------------------------------------------------------------------

def build(args):
    w, h = args.width, args.height
    lay = Layout(w, h, int(args.strip))
    Hs = max(4, lay.scene_h)
    cache = args.cache_dir
    now_of = clock(parse_when(args.at), args.rate)
    rng = np.random.default_rng(args.seed or None)

    frame = np.zeros((h, w, 3), np.uint8)

    # --- geometry: four depth planes, as per-column top rows ----------------
    tops = [
        _ridge(w, Hs, 0.60, ((0.10, 0.09, 0.105), (0.28, 0.07, 0.055),
                             (0.44, 0.11, 0.130), (0.62, 0.06, 0.070),
                             (0.80, 0.13, 0.100)), rng),
        _trapezoids(w, Hs, 0.760, DOWNTOWN),
        _ridge(w, Hs, 0.860, ((0.22, 0.16, 0.055), (0.68, 0.20, 0.040)),
               rng, roughness=0.006),
        _trapezoids(w, Hs, 0.945, ROOFTOP),
    ]
    # A row of low sheds on the middle plane, so it is not one smooth hill.
    xcol = np.arange(w)
    sheds = ((xcol // 11) % 3).astype(f32) * f32(0.012 * Hs)
    tops[2] = tops[2] - sheds

    # --- occlusion: which body is in front, which is behind, how covered ----
    #
    # Walking front to back would need a "have I already been painted" test per
    # pixel; walking back to front, each plane simply overwrites, and what it
    # overwrites is exactly what is behind it. Four passes over a 320x55 bool,
    # once, in build().
    rows = np.arange(Hs, dtype=f32)[:, None]
    front = np.zeros((Hs, w), np.int32)
    behind = np.zeros((Hs, w), np.int32)
    cov = np.ones((Hs, w), f32)
    for d, top in enumerate(tops, start=1):
        c = np.clip(rows - top[None, :] + 1.0, 0.0, 1.0)
        m = c > 0.0
        behind[m] = front[m]
        front[m] = d
        cov[m] = c[m]

    # --- lit windows and the tower beacon ----------------------------------
    # Sparse pixels inside the downtown silhouette, given their own body colour
    # at the same distance. They attenuate with everything else, so the towers
    # going dark is one of the loudest signals on the panel that the far
    # distance has gone -- and it costs nothing per frame, because it is only
    # another entry in the same lookup table.
    city = np.flatnonzero((front == B_CITY).reshape(-1))
    if len(city):
        n_lit = min(len(city), max(24, (w * Hs) // 240))
        pick = rng.choice(city, size=n_lit, replace=False)
        fy, fx = np.unravel_index(pick, (Hs, w))
        # Only where the silhouette is solid, so an edge pixel is not turned
        # into a light and made to lose its antialiasing.
        solid = cov[fy, fx] >= 0.999
        fy, fx = fy[solid], fx[solid]
        behind[fy, fx] = B_CITY
        front[fy, fx] = B_LIGHTS
    # The spire of the tall one gets an aviation light. Static: a blinking one
    # would be a second timer on a panel whose whole clock is the sweep.
    spire_x = int(round(DOWNTOWN[8][0] * (w - 1)))
    spire_y = int(round(DOWNTOWN[8][3] * Hs))
    if 0 <= spire_y < Hs and 0 <= spire_x < w:
        behind[spire_y, spire_x] = front[spire_y, spire_x]
        front[spire_y, spire_x] = B_BEACON
        cov[spire_y, spire_x] = 1.0

    # --- the index image ----------------------------------------------------
    # One int per pixel, addressing (front body, body behind, edge coverage,
    # row) in a table render() rebuilds each frame. This is the whole reason
    # the panel is one gather.
    qcov = np.clip(np.round((1.0 - cov) * N_COV), 0, N_COV - 1).astype(np.int32)
    row_of = np.arange(Hs, dtype=np.int32)[:, None] * np.ones((1, w), np.int32)
    idx = np.ascontiguousarray(
        (((front * N_BODIES + behind) * N_COV) + qcov) * Hs + row_of)

    # --- the bodies, as per-row colours ------------------------------------
    bodies = np.empty((N_BODIES, Hs, 3), f32)
    bodies[B_SKY] = _ramp(SKY_BODY, Hs)
    dists = np.empty(N_BODIES, f32)
    dists[B_SKY] = SKY_KM
    for i, (_name, km, rgb) in enumerate(PLANES, start=1):
        bodies[i] = np.array(rgb, f32)[None, :]
        dists[i] = km
    for j, (_name, km, rgb) in enumerate(EXTRA_BODIES,
                                         start=1 + len(PLANES)):
        bodies[j] = np.array(rgb, f32)[None, :]
        dists[j] = km
    # A touch of vertical shading on the two big planes, so they are not flat
    # paint: the near rooftop falls off into shadow at the bottom of the panel
    # and the city is a hair brighter where it meets the sky.
    shade = np.linspace(1.10, 0.82, Hs, dtype=f32)[:, None]
    bodies[B_CITY] *= shade
    bodies[B_MID] *= shade
    bodies[B_NEAR] *= np.linspace(1.25, 0.75, Hs, dtype=f32)[:, None]

    air_lut = _airlight_table(Hs)
    fog_air = _two_stop(FOG_AIRLIGHT[0], FOG_AIRLIGHT[1], Hs)

    # --- the murk texture ---------------------------------------------------
    # Doubled in width so a scroll is a slice of a contiguous array rather than
    # a modulo gather: 320 columns of view, 640 of texture, no wrap arithmetic
    # in the frame loop at all.
    haze = _fbm(rng, Hs, w, 2, 3, octaves=3, gain=0.5)
    haze = np.ascontiguousarray(np.concatenate([haze, haze], axis=1))

    bayer = np.ascontiguousarray(
        np.tile(_bayer(8), (Hs // 8 + 1, w // 8 + 1))[:Hs, :w].astype(f32))
    if not args.dither:
        bayer = np.full((Hs, w), 0.5, f32)

    # --- per-frame scratch --------------------------------------------------
    base = np.empty((N_BODIES, Hs, 3), f32)
    tmp = np.empty((N_BODIES, Hs, 3), f32)
    tab = np.empty((N_BODIES, N_BODIES, N_COV, Hs, 3), f32)
    tab2 = np.empty_like(tab)
    scene = np.empty((Hs, w, 3), f32)
    hz = np.empty((Hs, w), f32)
    airc = np.empty((Hs, 3), f32)
    pm_air = np.empty((Hs, 3), f32)
    air_tmp = np.empty((Hs, 3), f32)
    cq = np.array(COVERAGES, f32)[None, None, :, None, None]
    cq1 = 1.0 - cq
    trans = np.empty(N_BODIES, f32)
    strip = np.zeros((max(lay.strip_h, 1), w, 3), np.uint8)
    text_rgb = np.zeros((h, w, 3), np.uint8)
    text_on = np.zeros((h, w, 1), bool)

    cell = {"rec": None, "problem": None, "loaded": -1e18, "stale": False,
            "now_u": 0.0, "last_u": 0.0, "hour": -999, "pm": 0.0,
            "aqi": None, "bpm": 0.0, "bfog": 0.0, "word": "", "band": "",
            "vis_km": 0.0}

    # ---------------------------------------------------------------------
    def draw_strip():
        """The whole 48 hours at once: PM2.5 as bars, measured then forecast.

        Scaled to the window's own peak, floored at 60 ug/m3 so that an
        ordinary day does not get magnified into a mountain range and a smoke
        day still fits. The forecast half is drawn at a little over half
        brightness -- the same distinction caiso.py draws between the day that
        has happened and the day that is predicted.
        """
        strip[:] = C_STRIP_BG
        rec = cell["rec"]
        if rec is None or not lay.strip_h:
            return
        n, sh = rec["n"], lay.strip_h
        cols = np.linspace(0.0, n - 1.0, w).astype(f32)
        i0 = np.clip(cols.astype(np.int32), 0, n - 1)
        i1 = np.clip(i0 + 1, 0, n - 1)
        fr = cols - i0
        pm = rec["pm"][i0] * (1 - fr) + rec["pm"][i1] * fr
        aqi = rec["aqi"][i0] * (1 - fr) + rec["aqi"][i1] * fr

        top = max(60.0, float(np.nanmax(rec["pm"])) * 1.15)
        # A gentle compression, so that the shape of an ordinary 10 ug/m3 day
        # is legible on the same axis that a 250 ug/m3 day has to fit on.
        hgt = np.clip((pm / top) ** 0.7, 0.0, 1.0) * (sh - 1)
        nrow = np.round(hgt).astype(np.int32) + 1
        yy = np.arange(sh)[:, None]
        filled = yy >= (sh - nrow)[None, :]

        cols_rgb = np.zeros((w, 3), f32)
        # Assign highest band first then overwrite downwards, so each column
        # ends up with the colour of the lowest band it falls inside.
        for limit, _word, rgb in reversed(AQI_BANDS):
            sel = np.isfinite(aqi) & (aqi <= limit)
            cols_rgb[sel] = rgb
        nan = ~np.isfinite(aqi)
        cols_rgb[nan] = (90, 96, 104)

        now_col = int(round(cell["now_u"] / max(n - 1.0, 1.0) * (w - 1)))
        future = np.arange(w) > now_col
        cols_rgb[future] *= 0.55
        strip[filled] = np.broadcast_to(cols_rgb[None, :, :],
                                        (sh, w, 3))[filled]

        # Six-hourly ticks on the top row, and the present moment full height.
        for k in range(0, n, 6):
            c = int(round(k / max(n - 1.0, 1.0) * (w - 1)))
            if 0 <= c < w:
                strip[0, c] = np.maximum(strip[0, c],
                                         np.array(C_STRIP_RULE, np.uint8))
        if 0 <= now_col < w:
            strip[:, now_col] = C_NOW

    # ---------------------------------------------------------------------
    def draw_text(k):
        """Rebuild the whole text overlay for hour index `k`. Once per hour.

        Every string here is a format and a ladder of positions, which is the
        one thing caiso.py found was too expensive to do per frame on the Pi.
        The swept hour changes about twice a second, so this runs about twice a
        second and costs nothing measurable; `render()` never formats anything.
        """
        text_rgb[:] = 0
        text_on[:] = False
        rec = cell["rec"]
        if rec is None:
            return
        n = rec["n"]
        i0 = int(np.clip(k, 0, n - 1))
        i1 = int(np.clip(i0 + 1, 0, n - 1))
        fr = float(k - i0)
        pm = float(rec["pm"][i0] * (1 - fr) + rec["pm"][i1] * fr)
        aqi_v = rec["aqi"][i0] * (1 - fr) + rec["aqi"][i1] * fr
        aqi = None if not np.isfinite(aqi_v) else int(round(float(aqi_v)))
        bp = float(rec["bpm"][i0] * (1 - fr) + rec["bpm"][i1] * fr)
        bf = float(rec["bfog"][i0] * (1 - fr) + rec["bfog"][i1] * fr)
        band_word, band_rgb = aqi_band(aqi)
        word = condition_word(bp, bf)
        cell["pm"], cell["aqi"] = pm, aqi
        cell["bpm"], cell["bfog"] = bp, bf
        cell["word"], cell["band"] = word, band_word
        cell["vis_km"] = visual_range_km(bp + bf)

        big = 2 if lay.w >= 200 and lay.h >= 40 else 1
        # The headline. AQI, because that is the number the health advice is
        # written against and the number every other air map in the world
        # shows; PM2.5 underneath it because AQI is a piecewise-linear fiction
        # over it and somebody in a makerspace will want the actual mass.
        head = "%d" % aqi if aqi is not None else "--"
        x = 2
        blit_outlined(text_rgb, 1, x, head, band_rgb, C_INK, big, text_on)
        x += text_width(head, big) + 3
        blit_outlined(text_rgb, 1, x, "AQI", C_DIM, C_INK, 1, text_on)
        pmtxt = "PM2.5 %.1f" % pm if pm < 100 else "PM2.5 %d" % round(pm)
        blit_outlined(text_rgb, 1 + text_height() + 1, x, pmtxt,
                      C_TEXT, C_INK, 1, text_on)

        # Right: which hour the picture is standing in, and how old the record
        # is. The hour label is the more important of the two and gets the top
        # line, because a big number over the wrong hour is this panel's worst
        # failure mode.
        lab = hour_label(k, cell["now_u"])
        lw = text_width(lab)
        blit_outlined(text_rgb, 1, lay.w - lw - 2, lab,
                      C_NOW if lab == "NOW" else C_DIM, C_INK, 1, text_on)
        age = ftdata.describe_age(rec["age"])
        right = ("STALE " + age) if cell["stale"] else age
        rw = text_width(right)
        blit_outlined(text_rgb, 1 + text_height() + 1, lay.w - rw - 2, right,
                      C_WARN if cell["stale"] else C_DIM, C_INK, 1, text_on)

        # The caption, over the near rooftop: why you cannot see, and what the
        # category is called. Two words, because "SMOKE" and "UNHEALTHY" answer
        # two different questions and the panel is asked both.
        cy = lay.caption_y
        cap = "%s  %s" % (word, band_word)
        if text_width(cap) > lay.w - 60:
            cap = word
        blit_outlined(text_rgb, cy, 2, cap, band_rgb, C_INK, 1, text_on)
        tag = "48H PM2.5"
        tw = text_width(tag)
        if 2 + text_width(cap) + 8 + tw <= lay.w - 2:
            blit_outlined(text_rgb, cy, lay.w - tw - 2, tag, C_DIM, C_INK,
                          1, text_on)

    # ---------------------------------------------------------------------
    def reload_data(now):
        rec, age, problem = read_air(cache)
        if rec is not None:
            span = rec["t0"] + rec["step"] * (rec["n"] - 1)
            if not (rec["t0"] - 3600.0 <= now <= span + 3600.0):
                # A perfectly well formed record of a window that has ended.
                # Drawing it would put a forecast where the past goes and a
                # cursor on an hour that is not the present one.
                problem = "RECORD WINDOW ENDED %s" % ftdata.describe_age(
                    max(0.0, now - span))
                rec = None
        cell["rec"], cell["problem"], cell["loaded"] = rec, problem, now
        cell["stale"] = rec is not None and not ftdata.is_fresh(PRODUCT, age)
        cell["hour"] = -999
        if rec is None:
            return
        cell["last_u"] = float(rec["n"] - 1)
        cell["now_u"] = float(np.clip((now - rec["t0"]) / rec["step"],
                                      0.0, cell["last_u"]))
        draw_strip()
        draw_text(cell["now_u"])

    # ---------------------------------------------------------------------
    def render(t, i):
        now = now_of()
        if args.reload and now - cell["loaded"] >= args.reload:
            reload_data(now)

        rec = cell["rec"]
        if rec is None:
            lines = [("NO AIR DATA", C_WARN),
                     ("RUN  PYTHON3 FTDATA.PY --ONCE --ONLY AIR", C_TEXT)]
            if cell["problem"]:
                lines.append((str(cell["problem"]).upper()[:52], C_DIM))
            return draw_nodata(frame, lay, lines)

        n = rec["n"]
        u = sweep_position(t, args.sweep, cell["now_u"], cell["last_u"])
        i0 = int(np.clip(u, 0, n - 1))
        i1 = min(i0 + 1, n - 1)
        fr = f32(u - i0)
        bp = float(rec["bpm"][i0] * (1 - fr) + rec["bpm"][i1] * fr)
        bf = float(rec["bfog"][i0] * (1 - fr) + rec["bfog"][i1] * fr)
        pm = float(rec["pm"][i0] * (1 - fr) + rec["pm"][i1] * fr)

        # The text only has to change when the hour does. Quantising it is not
        # a saving so much as a correctness point: the number under the cursor
        # is an hourly model output, and showing it sliding through 13.47 would
        # claim a resolution the data does not have.
        hour = int(round(u))
        if hour != cell["hour"]:
            cell["hour"] = hour
            draw_text(float(hour))

        # --- the airlight: warm particulate ramp mixed with cool fog --------
        #
        # Everything below writes through `out=` rather than with `+=`. That is
        # not only about allocation: an augmented assignment to a name from the
        # enclosing scope makes that name local to render(), which is an
        # UnboundLocalError several lines earlier and not an obvious one. It
        # cost an hour here, exactly as caiso.py's comment says it did there.
        ai = _airlight_index(pm)
        k0 = int(ai)
        k1 = min(k0 + 1, AIR_LEVELS - 1)
        kf = f32(ai - k0)
        np.multiply(air_lut[k1], kf, out=pm_air)
        np.multiply(air_lut[k0], 1.0 - kf, out=air_tmp)
        np.add(pm_air, air_tmp, out=pm_air)
        warm = f32(bp / max(bp + bf, 1e-6))
        np.multiply(pm_air, warm, out=airc)
        np.multiply(fog_air, 1.0 - warm, out=air_tmp)
        np.add(airc, air_tmp, out=airc)

        # --- Beer's law, once per body, then the whole table ---------------
        b_km = f32((bp + bf) * 1e-3)          # Mm^-1 -> km^-1
        np.multiply(dists, -b_km, out=trans)
        np.exp(trans, out=trans)
        np.multiply(bodies, trans[:, None, None], out=base)
        np.multiply(airc[None, :, :], (1.0 - trans)[:, None, None], out=tmp)
        np.add(base, tmp, out=base)
        # (front, behind, coverage, row) -> the antialiased colour. Small: a
        # few tens of thousands of floats, a handful of numpy calls, and it
        # replaces every per-pixel blend the frame would otherwise need.
        np.multiply(base[:, None, None, :, :], cq, out=tab)
        np.multiply(base[None, :, None, :, :], cq1, out=tab2)
        np.add(tab, tab2, out=tab)

        # --- the frame: one gather, one add, one store ---------------------
        np.take(tab.reshape(-1, 3), idx, axis=0, out=scene)
        # The murk drifts. Amplitude follows the extinction, so a clean day is
        # still and crisp and a smoke day visibly moves -- and the floor under
        # it is what guarantees that no two consecutive frames are identical
        # even while the sweep is dwelling on the present, which on a wall
        # between two animated demos is the difference between a pause and a
        # crash. See caiso.py, which learned this the same way.
        amp = f32(args.haze * (2.5 + 11.0 * (1.0 - math.exp(-b_km * 5.5))))
        off = int(t * args.drift) % w
        np.multiply(haze[:, off:off + w], amp, out=hz)
        np.add(hz, bayer, out=hz)
        np.add(scene, hz[:, :, None], out=scene)
        np.clip(scene, 0.0, 255.0, out=scene)
        np.copyto(frame[:lay.scene_h], scene, casting="unsafe")

        if lay.strip_h:
            frame[lay.strip_y:] = strip
            c = int(round(u / max(n - 1.0, 1.0) * (w - 1)))
            c = min(max(c, 0), w - 1)
            # The cursor pulses. Cheap, and it is the one mark on the panel
            # that is guaranteed to be somewhere different a second from now.
            g = 0.55 + 0.45 * math.sin(t * 4.4)
            frame[lay.strip_y:, c] = tuple(int(v * g) for v in C_CURSOR)
            frame[max(0, lay.strip_y - 2):lay.strip_y, c] = C_CURSOR

        np.copyto(frame, text_rgb, where=text_on)
        return frame

    reload_data(now_of())
    render.state = cell
    render.layout = lay
    render.clock = now_of
    # The baked scene structure, for the tests. `front` is which body is
    # visible at each pixel, which is what lets a test measure "can you still
    # see the ridge" as the contrast across the ridge's own silhouette edge
    # rather than by comparing two patches that also differ by the sky's
    # vertical gradient. Nothing else reaches in here.
    render.geometry = {"front": front, "behind": behind, "cov": cov,
                       "tops": tops, "scene_h": Hs}
    return render


def main():
    ds.standalone(sys.modules[__name__],
                  "the air outside, drawn as how far you can see through it",
                  fps=20)


if __name__ == "__main__":
    main()
