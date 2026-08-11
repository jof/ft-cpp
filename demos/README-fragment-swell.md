### swell

![swell](screenshots/swell.png)

What the Pacific is actually doing, drawn side-on and moving at the speed it is
actually doing it. `tide` next door draws a *prediction* — a harmonic fit
computed years ago that would print the same curve this afternoon if every buoy
in the ocean were switched off. This is a *measurement*. Eighteen nautical miles
west of the Golden Gate there is a three-metre discus hull, **NDBC station
46026**, which every ten minutes reports how high the sea around it is, how long
between crests, and which way they are running; the middle band of the panel is
that sea, in section.

**It used to be a plan view, and the plan view is what was wrong with it.** Seen
from above there is no third dimension to put a metre and a half of swell into,
so the first version encoded wave height as *contrast*: a bigger sea swung
further through the blue ramp. It was pretty and it was honest and nobody could
read it, which is exactly the complaint that produced this rewrite — "it does
kinda look like waves, but I'm not really sure what the numbers are showing".
Contrast is an encoding, an encoding needs a legend, and a legend is a sentence
nobody walking past a wall is going to read. In profile the encoding disappears.
The height of the water on the wall **is** the height of the water, on a fixed
scale, with the significant height drawn as a bracket at the left edge and
labelled `5FT`. Nobody needs told what five feet means when five feet is drawn.

**The rhythm is the point and always was.** A crest passes any given point on
the wall once every T seconds, T being the period the buoy measured: the train
is drawn at the wavelength deep water gives it (L = gT²/2π) and moved at the
speed that follows (c = L/T). Nine seconds is a rhythm somebody can feel without
reading a digit. What is new is that the panel now *says so* — the headline is a
sentence, `5FT WAVES EVERY 9 SEC`, and a bar across the top of the water spans
one crest to the next labelled `9 SEC BETWEEN CRESTS`, so the sentence and the
picture are visibly the same claim. That tie is the single biggest thing this
version does that the old one did not.

**The surface is a sum, because a sea surface is a sum.** The `.spec` sidecar
carries the directional spectral summary, which splits the sea state into a
swell part and a windsea part with a height, a period and a direction each, and
the profile adds them: a long groundswell with short chop riding on its back.
Drawn from above the two trains crossed and made a plaid; drawn in section the
superposition is simply what a clean day and a blown-out day look like, and the
difference is visible from the far end of the room. The verdict beside the
headline — CLEAN, MIXED or CHOPPY, on the ratio of the two heights — now comes
with the comparison it is making (`MOSTLY SWELL`, `SWELL AND CHOP`,
`MOSTLY CHOP`), because a word like CLEAN with nothing to lean on invites the
question "clean compared with what".

**The waves are not all the same size, and that is deliberate and also a
caveat.** Each partition is drawn as three components a few per cent either side
of its measured period, weighted 1:2:1, rather than as one pure sinusoid: a real
spectrum has width, and width is why no two crests in the ocean match. The
carrier still crosses any point every T seconds — the sidebands only beat slowly
against it — so the rhythm is untouched while the surface stops looking like
graph paper. **But the individual waves are a rendering, not a record.**
Significant height is a statistic, roughly the mean of the highest third; the
buoy never published a list of waves and this panel does not pretend it did.
What is measured is the height, the rhythm, the split and the direction. The
irregularity between one crest and the next is the model saying "and it is not a
sine wave", nothing more.

**The vertical scale is fixed at three metres significant**, which is a proper
storm off this coast, with about a fifth of headroom because the two trains sum.
Fixed rather than fitted to the day for the reason a fitted axis is always
wrong: a panel that normalises itself cannot be compared with yesterday's, and
comparing is most of what anybody wants from it. The cost is that an ordinary
one-and-a-half-metre afternoon uses a bit under half the band, which is the
truth about an ordinary afternoon. A near-flat calm draws as a still line with a
half-pixel of texture on it and the bracket collapsed to `1FT`, and that reads
as *calm* rather than as broken, which was the state most at risk from the
rewrite.

**The horizontal scale is in seconds, not metres.** The zoom is fixed at 3.4
wavelengths of the *longest* train across the panel — keyed on the swell and not
on whichever train is biggest, because "n wavelengths across" makes every train
look alike and the first cut of this drew a four-second windsea as three wide
smooth bands, the same picture as a groundswell only faster. Keyed on the swell,
the chop is drawn at its true size *relative to* it: a blown-out day is short
steep chop with a long heave under it and looks nothing like a clean one. The
old panel's scale bar said `129M`, on a panel that also said `OBS 64M` meaning
sixty-four minutes; both of those are gone and the only horizontal unit claimed
now is the seconds between crests, which is the unit the animation is keeping
anyway.

**The section is cut along the way the water is running**, so the dominant
crests are drawn undistorted and the other train is projected onto that line —
which lengthens its apparent wavelength by 1/cos of the angle between them and
leaves its period alone, correct for a section across a crossing sea, and the
reason a cross swell shows up as a slow heave under fast chop. That leaves
direction with no natural home, since a profile has no compass, so it gets a
small inset in the corner: a north tick, an arrow the way the water is going,
and the bearing it is coming *from* spelled out beside it, which is the
convention every forecast uses.

**No buoy is drawn on the water.** It was tempting — 46026 is a three-metre
discus hull and drawing it bobbing would mark where the data comes from — but
the section is 128 m wide and 4 m tall on a band 320 px by 31, which is a
vertical exaggeration of about fourteen. Anything solid drawn on that surface is
a lie about one axis or the other, and a lie about scale is the one thing a
panel whose whole argument is "the picture is the measurement" cannot afford.
The still-water line and the height bracket do the same job and are honest.

**The strip along the bottom is twenty-four hours of trend**, significant height
as a filled area with the dominant period dotted over it on a fixed 4–20 s
scale, because "5FT" says nothing about whether that is a swell building for
tomorrow or the end of one. It used to be labelled `9FT` at one end and `20S` at
the other with nothing saying what it was or how long it ran; the axis maxima
now name their quantity in the colour of their trace (`HEIGHT 9FT`,
`PERIOD 20 SEC`) and the strip says `PAST 24 HOURS` under it. The right edge is
the newest *sample*, not the wall clock. Holes are the interesting part: the
buoy drops samples constantly — on the day this was written it reported a wave
height on 87 of 156 ten-minute slots and a dominant period on 42 — and drawn
faithfully that is not a trend line, it is a comb. So holes up to half an hour
are bridged and longer ones are left as holes, which keeps the property that
matters: an outage still looks like an outage.

**Eleven numbers became six.** Gone: the height in metres beside the height in
feet, the bearing in degrees beside the compass point, the metres-wide scale
bar, the wind speed, the station number and the `SWL`/`SEA`/`9S` shorthand. What
is left is a sentence, the two halves of the sea in words (`SWELL 5FT` over
`CHOP 1FT`), the verdict and what it means, the buoy's name, and an age that
says it is an age: `45 MIN AGO`, not `OBS 45M`. The water temperature survives
only on panels wider than this one, which is the header's ladder choosing what
to lose rather than clipping a word in half.

**Two different things can be stale, and the panel says which.** The fetch age
says whether the fetcher is alive; the observation age says whether the *buoy*
is. Station 46237 on the San Francisco bar was serving a week-old file
throughout the writing of this, perfectly parseable, and a panel that trusted
the fetch age would have animated it without a murmur. So the observation age
sits in the corner, goes to warning colour past ninety minutes — NDBC's own
pipeline runs half an hour behind the buoy on a good day, and a panel that cries
stale every afternoon is one nobody believes on the day it matters — and past
twelve hours the water is not drawn at all, replaced by `SF 18NM W SILENT` over
`LAST WAVE 5 DAYS AGO`. Animating a sea state at a rhythm the ocean is no longer
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
None of that changed in the rewrite: the record is the same record, and the
panel is a different reading of it.

**Frame budget.** Everything is baked in `build()`: the header, the strip, the
overlay marks, and one row of phase per component. A frame is then five calls to
turn the components into a one-dimensional surface — all on a (6, 320) array —
four to turn that surface into a band of water (subtract it from every row to
get a depth below the surface, clip, cast to an index, look the colour up), and
one scatter for the overlay. Ten numpy calls, none of which allocate, into a
buffer whose header and strip rows are never touched at all because they cannot
change between fetches. Measured over 1200 frames on the desktop: **p50 0.044
ms, p95 0.048 ms, worst frame 0.068 ms**, with `build()` at 1.2 ms. Numpy costs
tens of microseconds a call on the wall's Pi whatever the array size, so the
call count is the budget and not the pixel count.

`render` is a pure function of `t` — asserted in `scripts/test-swell.py` by
comparing a cold `render(3.7)` against the same instant driven frame by frame
from zero — and the wall clock is read only to decide when to re-read the cache.

**It can draw a beautiful, confident, wrong picture, so it is asserted in
pixels.** `scripts/test-swell.py` finds the water surface in the rendered frames
— the topmost row with six lit rows under it, because water is thick where a
letter is not, and the caption written across the sky is brighter than any crest
— and then measures it. The crest rate at one column comes back within 0.01 s of
7, 12 and 18 second swells. The crest *spacing* matches the geometry. The
pattern moves in the right direction at c = L/T. Doubling the reported height
doubles the RMS surface elevation to within a couple of per cent, which is the
check that fails the moment anybody normalises the amplitude to the day, and the
height bracket is asserted to be the length it claims to within a pixel. A
chop-driven sea is asserted to draw *short*, which is the bug that shipped in
the first cut of the profile view. It also checks that a long outage stays a
hole, that a silent buoy blames the buoy, that the three data states each render
in their own process, and that the strings the old panel was criticised for —
`1.9M`, `FROM 315`, `SWL 6.2FT`, `OBS 45M`, `129M` — are gone.
