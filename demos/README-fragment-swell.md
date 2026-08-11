### swell

![swell](screenshots/swell.png)

What the Pacific is actually doing, moving at the speed it is actually doing
it. `tide` next door draws a *prediction* — a harmonic fit computed years ago
that would print the same curve this afternoon if every buoy in the ocean were
switched off. This is a *measurement*. Eighteen nautical miles west of the
Golden Gate there is a three-metre discus hull, **NDBC station 46026**, which
every ten minutes reports how high the sea around it is, how long between
crests, and which way they are running; the middle band of the panel is that
sea, drawn from above with north up.

**The wave train is the data, and that is the whole idea.** The crests cross
the panel at the measured heading, spaced at the wavelength the measured period
implies, moving at the speed that follows from it. Deep water gives the rest
for free — L = gT²/2π, c = L/T — so nine seconds of dominant period means a
crest passes any point on the wall every nine seconds, and nine seconds is a
rhythm somebody walking past can feel without reading a digit. A twenty-second
groundswell draws as wide slow bands; a four-second local chop draws as fine
fast texture. Neither of those is a stylistic choice.

**Two trains, because that is what the sea is.** The `.spec` sidecar carries
the directional spectral summary, which splits the same sea state into a swell
part and a windsea part with a height, a period and a direction each, and both
are drawn, superposed, at their own wavelengths and their own headings. A clean
groundswell day is long smooth bands with a faint texture on them; a blown-out
day is the same bands broken up by chop crossing them at forty degrees. That
distinction — is this swell, or is it slop — is the single most useful thing
the data says, and it is why the second file is fetched at all.

Drawing it as *interference* rather than as an energy-versus-period plot is
deliberate, and it is the design decision this panel turns on. A spectrum at
this size is four bars and a squint; two superposed sinusoids are simply what
the water looks like, and they cost the same to draw as one. The numbers behind
it are in the header anyway (`SWL 5.2FT 9S NW` over `SEA 1.3FT 4S W`) with a
one-word verdict beside them — CLEAN, MIXED or CHOPPY, on the ratio of the two
heights — so nothing the plot would have said is missing.

**Height is contrast, not amplitude.** In plan view there is no third dimension
to put a metre and a half of swell into, so significant height drives how far
the surface swings through the palette instead: a small sea stays in the middle
of the blue ramp and reads as flat, a big one reaches the dark trough and the
white foam at either end. Three metres is full scale, which is a proper storm
here. The scale is fixed rather than fitted to the day, because a panel whose
contrast normalises itself cannot be compared with yesterday's, and comparing
is most of what anybody wants from it.

**The zoom is fixed in wavelengths, not in metres**, at 2.6 swell wavelengths
across the panel, and the scale bar in the corner says what that came out as —
129 m on the day of the screenshot. A fixed patch of ocean would draw a
twenty-second groundswell as one vast crest filling the wall and pulsing, which
is honest and useless; fixing the number of wavelengths keeps the picture
legible at every period and keeps the thing that matters exactly right, since a
crest still passes any given point once every T seconds either way. The arrow
on the water points the way the waves are going; the header says where they are
coming *from*, which is the convention every forecast uses, and the compass in
the top-left corner is there so the two can be reconciled.

**The strip along the bottom is twenty-four hours of trend**, significant height
as a filled area with the dominant period dotted over it on a fixed 4–20 s
scale, because "1.9 m" says nothing about whether that is a swell building for
tomorrow or the end of one. The right edge is the newest *sample*, not the wall
clock. Holes are the interesting part: the buoy drops samples constantly — on
the day this was written it reported a wave height on 87 of 156 ten-minute
slots and a dominant period on 42 — and drawn faithfully that is not a trend
line, it is a comb. So holes up to half an hour are bridged and longer ones are
left as holes, which keeps the property that matters: an outage still looks
like an outage.

**Two different things can be stale, and the panel says which.** The fetch age
says whether the fetcher is alive; the observation age says whether the *buoy*
is. Station 46237 on the San Francisco bar was serving a week-old file
throughout the writing of this, perfectly parseable, and a panel that trusted
the fetch age would have animated it without a murmur. So `OBS 64M` sits in the
corner next to the fetch age, goes to warning colour past ninety minutes — NDBC's
own pipeline runs half an hour behind the buoy on a good day, and a panel that
cries stale every afternoon is one nobody believes on the day it matters — and
past twelve hours the wave train is not drawn at all, replaced by
`BUOY 46026 SILENT 5D`. Animating a sea state at a rhythm the ocean is no longer
keeping is the one lie this panel could tell.

**600 kB of text becomes 2.7 kB of JSON, and most of it is never downloaded.**
The realtime2 files are newest-row-first, which is the piece of luck the fetcher
is built on: the last day of a buoy's life is the first sixteen kilobytes of a
file that runs to six hundred, so it issues a ranged GET and NDBC's CloudFront
answers 206 with the top of the file. A server that ignored the header would
answer 200 with the lot and the parser would still be right, just dearer. `MM`
means missing and it is everywhere, so nothing assumes a row is complete: each
headline value is taken from the newest row that actually has it and carries the
time of *that* row, because a buoy with a dead wave sensor keeps reporting wind
and water temperature for months. Both files are parsed off their own
`#YY MM DD ...` header line rather than a hardcoded column order. TTL is an
hour, fetch interval ten minutes, which is the buoy's own cadence and no faster.

**Frame budget.** Everything is baked in `build()`: the header, the strip, the
compass and — the part that makes this cheap — one integer *phase image* per
wave train, the distance along that train's direction of travel at every pixel.
A frame is then two table lookups, an add, one palette lookup and one scatter
for the overlay: seven numpy calls, none of which allocate, into a buffer whose
header and strip rows are never touched at all because they cannot change
between fetches. Measured over 4000 frames on the desktop: **mean 0.038 ms, p95
0.042 ms, worst frame 0.063 ms**, with `build()` at 1.2 ms. Numpy costs tens of
microseconds a call on the wall's Pi whatever the array size, so the call count
is the budget and not the pixel count; at a hundred times the desktop figure
this is still under 5 ms against a 50 ms frame.

`render` is a pure function of `t` — asserted in `scripts/test-swell.py` by
comparing a cold `render(3.7)` against the same instant driven frame by frame
from zero — and the wall clock is read only to decide when to re-read the cache.

**It can draw a beautiful, confident, wrong picture, so it is asserted in
pixels rather than eyeballed.** `scripts/test-swell.py` measures the crest rate
off the rendered frames by counting zero crossings at one pixel and asserts it
against the reported period (7, 12 and 18 s all come back within 0.01 s); it
measures the crest *spacing* down a tall panel and asserts it against the
geometry; and it cross-correlates successive frames to assert that a swell from
the north travels south, which is the sign error that looks perfect on screen
and puts a northwest swell running back out to sea. It also checks that a long
outage stays a hole, that a silent buoy blames the buoy, and that the three
data states each render in a process of their own — `ftdata.CACHE_DIR` binds at
import, so reloading the module does not test what it looks like it tests.

```console
$ python3 ftdata.py --once --only ndbc-46026
$ python3 swell.py --host 127.0.0.1
$ python3 swell.py --waves 4 --hours 48        # wider ocean, two days of trend
$ python3 swell.py --no-windsea                # the groundswell alone
$ python3 swell.py --rate 6                    # a minute of ocean in ten seconds
$ FT_DATA_CACHE=/tmp/empty python3 swell.py    # the no-data card
$ python3 scripts/test-swell.py
```

`FT_BUOYS` is a comma-separated list the fetcher adds to its default, so
`FT_BUOYS=46013 python3 ftdata.py --once` registers and fills Bodega Bay and
`swell.py --station 46013` draws it. Any NDBC station with a wave sensor works;
one without publishes no `.spec` and gets a single wave train, which is the
fallback path and is drawn from the standard file's dominant period and mean
direction. Station 46237 is closer in, on the bar itself, and would be the
better buoy for what the water is doing *at* the Gate — it just has not
reported since the third of August.
