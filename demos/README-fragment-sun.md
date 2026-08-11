### sun

![sun](screenshots/sun.png)

The last day of the Sun's corona, in the 193 Å channel of SDO/AIA, on a
fourteen-second loop that has no seam in it. Forty-eight half-hourly frames
from NASA's Solar Dynamics Observatory play left to right while a playhead
sweeps the last twenty-four hours of GOES X-ray flux beside them, so the
picture and the number are the same day at the same instant. It is the only
panel on the wall that is a photograph of another object in space —
`propagation` and `sats` are numbers and geometry about space, which is not the
same thing — and it is there because a picture of the star is legible to
somebody who knows nothing about any of the rest of it.

**Why 193 Å.** AIA takes the Sun in ten channels and they are pictures of ten
different things, not ten filters on one picture. 193 Å is Fe XII/XXIV at about
1.2 million kelvin, which puts the *corona* on screen instead of the surface,
and it is the channel where the magnetic field becomes visible: active regions
as bright knots, the loops arcing between them, and coronal holes as the black
bays where the field opens and the solar wind gets out. 4500 Å — the bland
yellow disk everyone pictures — has nothing happening in it at 60 pixels.
`FT_SDO_WAVE` will fetch 0171 or 0304 instead; the stored colour ramp is 193's
and would want re-measuring for another channel.

**The loop is the hard part, and it is measured rather than eyeballed.** A day
does not join up. The Sun turns 13.2° in it, so cutting from now back to
yesterday is a jerk once a cycle — the kind of fault a passer-by registers as
"that looks cheap" without being able to say why. Holding on the newest frame,
which is what `goes.py` does and is right for weather, is wrong here: the point
of this panel is the turning, and a hold puts a stutter exactly where the motion
should be. So the loop **overlaps itself**. The last six frames are
cross-dissolved into the first six and the period is shortened by exactly that
overlap, which puts the seam in the middle of a dissolve where there is nothing
to see.

That it works is a number, not an opinion. Taking the mean absolute difference
between consecutive loop frames, the step across the wrap is **14.7× a typical
interior step with the overlap off, and 2.16× with it on** — 1.7 levels out of
255, which is under what the panel can show. `scripts/test-sun.py` asserts both,
including the control: a test that only checked the blended loop would pass
against a broken implementation that blended nothing.

The honest cost is that the dissolve is a genuine double exposure of two moments
three hours apart. At 13.2° a day they are close enough that it reads as a soft
blur rather than a ghost. The other cost is subtler and was a bug before it was
a feature: the overlap **consumes** the newest frames, so the loop's last
unblended frame is three hours short of the ring's newest. The axis originally
ran to the newest frame anyway, and the playhead stopped a thirteenth short of
the right edge every cycle. The trace and the window label now describe exactly
the interval the playhead sweeps; how stale the imagery is stays a separate
claim, made separately in the corner.

**The X-ray trace is the same day, not a second instrument.** GOES' 1–8 Å flux
is already fetched for `propagation`, so it costs no network at all, and drawn
on the *same* time axis as the time lapse it stops being a second panel and
becomes a caption for the first: the playhead crossing a spike is the same
instant the disk flares. The scale is logarithmic from **B to X rather than the
conventional A to X**, because most days are quiet — the Sun was B4 the day this
was written — and four decades flattens a quiet day onto the floor where it
reads as no data at all. Three and a half decades keeps a quiet day a visible
ripple and still leaves an X-flare at the ceiling. The C and M rules are named,
because otherwise the empty two thirds above the trace is just black when what
it actually says is "there is room here for a flare two hundred times bigger and
there has not been one". Sub-C columns are drawn cold blue-grey rather than
`propagation`'s green: the disk is the only warm thing on this panel by design,
so heat should be the thing that *appears* when a flare does. The trace is a
garnish and never a dependency — with no flux record the Sun draws alone.

**One channel is stored, not three, and that is lossless here.** The browse JPEG
is already false colour: 193 Å is drawn through a fixed one-dimensional bronze
colormap, so G and B are functions of R rather than independent information.
Binning a real frame confirms it — at a given intensity the spread in the other
two channels is one to five levels, which is JPEG ringing. So the fetcher keeps a
single 8-bit intensity plane and the demo maps it back through its own copy of
that ramp, measured off a real frame rather than guessed. That thirds the
sidecar and, more usefully, puts the contrast curve under the panel's control
instead of NASA's, which matters on an LED wall whose dark end is compressed.
The index is `(R+G+B)/3` and not R alone because R saturates first, and the
pixels where it saturates are exactly the flare cores worth keeping apart from
merely bright.

**The limb was found, not assumed.** On the 512 px browse image the Sun is
centred on (255.5, 255.5) with a photospheric radius of about 203 px, measured
off the radial profile — which peaks sharply at r=200 where the limb brightens
and has fallen to a tenth by r=250. Cropping tight to that gets the biggest
possible disk and looks wrong, because the corona is still bright where the
square ends: the Sun ends up in a luminous box, bright at the middle of each
edge and black only in the corners. The crop is 248 px of half-width instead and
the demo fades the last of the corona to black with a vignette that starts at
the limb, so **no photospheric pixel is touched** and the disk sits in a halo
rather than a border. It costs disk diameter — 52 px rather than 60 — and buys a
star instead of a photograph of one. The crop also throws away the caption GSFC
burns into the bottom of every browse frame, which would otherwise arrive as
unreadable smeared type along the panel.

**Fetching is a ring, and the expensive endpoint is only used to repair.** This
is where most of the work went. Frames live in a per-day Apache directory index
which is **1.2 MB of HTML, served uncompressed** — no gzip, and `Range` requests
are ignored outright, returning all 1.2 MB with a 200. The filenames cannot be
predicted either, which is what makes the listing necessary at all: `goes.py`
gets away with naming tomorrow's files because its scans are exactly on a
five-minute grid, but AIA's wander (00:07, 00:17, 00:27, 00:37, 00:48, 00:57)
with seconds only ever on a twelve-second grid, and there are holes. Pulling the
listing every pass would cost **57 MB a day** to learn the name of one new file.

What saves it is that `latest_512_0193.jpg` is the newest frame at a fixed URL,
44 kB, with a `Last-Modified` that dates publication rather than the fetch. So
the ring is topped up from `latest` and nothing else in the ordinary case, and
the listing is fetched only when there is a hole older than an hour — a cold
start, or a fetcher that has been down. **Steady state is about 2 MB a day**
against 57. `Last-Modified` is not the observation time and the difference is
stored rather than ignored: a frame shot at 17:38:05 UT appeared with
`Last-Modified` 17:43:06, so publication trails the shutter by very close to
five minutes and `SDO_PUBLISH_LAG` backs that out. Backfilled frames get their
exact time from the filename, so the two paths agree to a few minutes on a
twenty-four hour axis — under a pixel.

Half-hourly is as fine as the panel can resolve, which is why the ring is 48 and
not 144: half an hour of rotation moves a feature about a tenth of a pixel on a
52-pixel disk, so a ten-minute ring would triple the fetching to show the same
picture. What half-hourly still catches is what actually moves at this scale —
an active region brightening, a flare, a coronal hole changing shape. The record
is 436 bytes and the sidecar about 150 kB.

**Playback is an index and one blend.** Everything — the resample, the vignette,
the colour ramp, the loop overlap, the flux trace, the type — is baked in
`build()`, which takes 3.8 ms. A frame on the wall copies a prepared background,
blends two tiles into the disk box with the integer blend `goes.py` uses, and
moves a playhead: about eight numpy calls, **0.014 ms mean and 0.017 ms p95** on
a desktop over a full loop. It is deliberately the cheapest thing it can be,
because the corona is doing the work.

**Missing, partial and stale are three different things and it says which.** No
cache, no sidecar or an unreadable one gets the no-data card with the fetcher's
command on it. A ring shorter than a day plays anyway and says how much of a day
it has — a cold start is a short ring by definition, and eight hours of the Sun
turning beats a card that says wait. A ring whose newest frame has gone stale
keeps playing with the age in red, because yesterday's corona is still worth
looking at as long as nobody can mistake it for now.
