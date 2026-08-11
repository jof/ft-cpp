### bikes

![bikes](screenshots/bikes.png)

One day of San Francisco's bike traffic, left to right: midnight to midnight
across 320 columns. The dark blue silhouette is **what this weekday normally
looks like** — the morning commute peak around eight, the midday trough, the
bigger evening peak around five, the long tail into the night — built from
three months of Bay Wheels' own published trip records. The bright gold line
over it is **today, so far**. A lit rule marks *now*, everything to the right of
it is what the rest of the day usually does, and the headline is an estimate of
how many trips have happened today with the word `EST` and the arithmetic that
produced it printed next to the number.

**This is the third design of this panel and the first one that answers the
question that was asked.** The first drew all 383 docks as a hillside sorted by
altitude and coloured by occupancy: a good picture of **state**, and the wall's
owner said, correctly, that it was hard to tell what people were doing. The
second replayed twelve hours of inferred flow as a swarm over a
distance-and-altitude cross-section of the city: a genuinely good instrument,
rejected twice — *"just some random arc"* (the altitude profile does not read as
anything to somebody walking past) and *"doesn't really communicate a clear
visual message"*. What had actually been asked for was *"the patterns of the
day, and where we are in the cycle"*, and this is that question drawn literally:
one shape everybody in the building already knows from their own commute, and a
line moving along it.

#### The honesty problem, which is the whole of the design

**The silhouette is measured. The gold line is estimated.** They are not the
same kind of number and everything about the panel is arranged so that nobody
can mistake one for the other.

Bay Wheels publishes a monthly CSV of every trip taken — start time, end time,
which dock at each end — at
`https://s3.amazonaws.com/baywheels-data/YYYYMM-baywheels-tripdata.csv.zip`,
keyless, about 20 MB zipped a month. That is a *census*, and the silhouette
comes out of it. The live GBFS feed publishes **no trips at all**: it is a
snapshot of how many bikes are in each dock right now. Everything the panel
knows about today comes from differencing those counts every ten minutes, which
sees a **floor** on movement and not a trip count — two riders swapping a dock
inside one window cancel out, a rebalancing van looks like fifteen riders, and
the several hundred free-floating ebikes that never touch a dock are invisible
to it entirely.

Putting those two on one axis and printing "+12% vs a typical Monday" would
claim a commensurability nobody had established. Three ways out were available:

1. **Plot both in absolute trips and print the percentage anyway.** Rejected:
   the percentage would be a made-up figure with two significant digits.
2. **Normalise both to their own peak and compare shape only.** Honest, and
   shape is most of what was asked for — but today's own peak is not known
   until the day has ended, so at nine in the morning the normalisation has
   nothing to divide by, and every substitute reintroduces the assumption it
   was meant to avoid. Rejected on mechanics rather than on principle.
3. **Calibrate the estimator against the archive and disclose the calibration
   on the panel.** Chosen.

**The calibration is measurable because the archive contains both halves of
it.** Every trip in the census can be replayed as the two dock-count changes it
would have caused — minus one at the dock it left, when it left; plus one at the
dock it reached, when it reached it — so the estimator can be *run on the
census*, bucket by bucket, and its output compared with the true number of trips
in the same bucket. Over 92 days in May, June and July 2026:

    true trips / dock-count moves = 1.83   (median day; 1.72 to 1.94, p10-p90)

varying by hour of the day from about 1.30 at four in the morning to 2.21 at
five in the afternoon — busy hours cancel more inside a ten-minute bucket, and
the free-floating share moves with the hour too. The gold line is the live
estimator multiplied by that hour-of-day factor. **The panel prints the
factor:**

    11711  TRIPS TODAY                              USUAL FOR A MONDAY
           EST FROM DOCK COUNTS X1.7        SHADED - 13 RECENT MONDAYS

`X1.7` is the effective multiplier over the slots actually measured so far.
Somebody who reads that line knows precisely how much of the number is
measurement and how much is arithmetic, which is a better disclosure than an
error bar they have no way to check.

**There is deliberately no percentage on the panel, and this is the part worth
arguing about.** The 5.9% figure above is the spread of the calibration measured
*by simulating the estimator on the archive*, not by comparing live GBFS against
the archive — nobody has months of paired snapshots, so that comparison cannot
be made yet. The live estimator sees things the simulation cannot: rebalancing
vans, bikes going out of service, a one-minute feed sampled every ten. So 5.9%
is a **floor** on the real error, not the error.

Against that, the thing being compared barely moves: the middle half of thirteen
Mondays' daily totals is within about **3%** of the median. The estimator's
uncertainty is roughly twice the signal a percentage would be reporting.
Printing "+12%" would be reporting noise to two digits. So the panel prints a
**verdict word** — `BUSIER THAN USUAL`, `QUIETER THAN USUAL`,
`USUAL FOR A MONDAY` — and only leaves the middle verdict when today is outside
the typical range *widened by the calibration's own uncertainty*, floored at ten
per cent. On an ordinary day it says the ordinary thing, which is the correct
output and not a failure of nerve.

The one end-to-end check that *can* be made was made: on a live record from a
Monday night, the estimator plus calibration produced 33 trips over ten measured
minutes against 23 for the same ten minutes in the archive — a factor of 1.4 on
a sample of ten minutes, which is the right *size*, and that is all a sample
that small can establish. `scripts/test-bikes.py` runs the check against
whatever is in the live cache and fails outside 0.4 to 2.5, because it is
looking for a factor of ten and not a few per cent.

#### How the silhouette was computed

`demos/bikes-typical.npz`, 43 kB, baked offline and committed the way
`adsb-coast.npz` and `bikes-terrain.npz` are:

    $ python3 bikes.py --bake-typical                    # last 3 whole months
    $ python3 bikes.py --bake-typical 202605 202606 202607

Three monthly CSVs (1.5 M trips, 66 MB of zip, about ten seconds), cropped to
San Francisco by the start coordinate against the same bounding box `ftdata.py`
crops the live feed with — Bay Wheels is one system covering four separated
cities and San Jose's commute is not this wall's. 92 dates come out, 13 or 14 of
each weekday, 514 000 SF trips a month.

The asset stores two raw matrices per weekday, one row per date and 144
ten-minute columns: the trips that happened, and what the estimator would have
reported. Raw counts rather than percentiles, so that everything on the panel
can be re-derived and argued with, and because a cold-started panel needs sums
over an arbitrary subset of the day.

The band is the **10th to 90th percentile across the dates of that weekday**,
after each date is smoothed with a 30-minute centred mean. Both of those are
drawing decisions as much as statistical ones, and both went the other way
first. The quartiles were tried and are *invisible*: the middle half of thirteen
Mondays is within 3% of the median at the morning peak, which on a 40-row chart
is a band one pixel high that reads as a rendering artefact. And without the
smoothing the band is mostly Poisson noise — a single ten-minute bucket of a
single Monday is a couple of hundred trips at the peak and a dozen at four in
the morning, so its sampling noise is comparable to the day-to-day variation the
band exists to show. Smoothing costs the morning peak about 2% of its height,
which is a smaller lie than a band twice as wide as the truth. What is left is a
crust two rows deep at the morning peak and six in the middle of the afternoon,
which is itself a true statement about when this city is predictable.

Public holidays, Bay to Breakers and rainy days are all left in. Thirteen dates
a weekday is too few to identify outliers without also removing real variety,
and a 10-to-90 band is exactly the right instrument for absorbing one odd Monday
in thirteen.

The parse was sanity-checked against what everybody already knows, and the
checks are in the test script: weekdays must peak between seven and nine and
again between four and six, with both peaks at least 1.5× the noon rate;
weekends must be a single hump between eleven and four with eight in the morning
under 60% of it. A CSV parsed as UTC instead of local would put the morning peak
at one in the morning and every one of those fails.

#### The record grew a day

`ftdata.py`'s `baywheels` product already accumulated a rolling twelve hours,
which is what the previous design replayed and is deliberately not longer. A
panel drawing *today* needs something else: every ten minutes since local
midnight, whether that is one hour ago or twenty-three. So the record gained a
`today` block — 144 slots from local midnight carrying two scalars each, `mov`
and `dt`, about 1.5 kB of JSON, reset when the local date rolls over. It is
local midnight and not UTC because the thing being drawn is a day as somebody
who rides a bike experiences one.

`dt` is not redundant, and it is where the one subtle bug in this panel lived. A
missed pass makes the next difference forty minutes long instead of ten, and
charging that to the single slot it was written into draws a tower with three
holes beside it — so the demo spreads the measurement across the four slots it
actually describes, at the rate it measured, and counts its trips exactly once.

The bug was the other direction. Coverage was first tracked in whole **slots**,
which is right only if the fetcher is on its ten minute timer; run it every five
and every slot is marked fully observed while only half of it was. Today's five
minutes then get compared against the archive's ten and the headline is silently
halved. It was caught by the live check above coming out at 0.83 when the
arithmetic said 1.4. Coverage is now counted in **seconds**, the comparison
weights each historical slot by the fraction of it that was actually watched,
and both are asserted in the test script. It is the kind of error this whole
panel is supposed to be careful about, and it still got in once.

**One real bug was found and fixed on the way in.** `_bikes_flow()` returned
`int(mov) * 2` where `mov` was already the sum of |change| over the stations —
which already counts both ends of every move. The record's own `units` block
says "/2 is bikes moved" and the old demo dutifully halved it, so **every
bike-movement figure this product has ever put on the wall was exactly twice the
truth**. Fixed in the fetcher rather than compensated for in the demo, because
the unit the record documents is the unit it should carry. Buckets written by
the old code age out of the rolling history within twelve hours.

#### Four states, all deliberate

**Cold start is the interesting one.** The silhouette is baked, so it is on the
panel in the very first frame of a fresh install — there is no version of this
demo that shows an empty rectangle, which is a nice property for a data panel to
have. The gold line is the opposite: it starts empty at local midnight and fills
in as the day goes, and on the day the fetcher is first started it begins only
from when it started. Every slot nobody looked at is a null in the record, so
the panel knows the difference between "nothing happened" and "nobody was
looking": it draws the line only where it was looking, leaves a **gap** where a
fetch was missed rather than interpolating a measurement that was not made, and
changes the headline from `TRIPS TODAY` to `TRIPS SINCE 2:40P`. The comparison
follows it — today is only ever compared against the typical day *over the same
slots* — so a wall that has been up for two hours makes a two-hour comparison,
and under two hours it says `TOO EARLY TO SAY` rather than guessing.

**Stale.** Past the half-hour TTL the header says `STALE` with the age and the
gold line simply stops where the data stopped while the now-rule keeps moving,
so the gap between the two is the panel telling you. That is deliberately not a
refusal, unlike the previous design's: this chart's whole subject is the day so
far, and a day so far that ends an hour early is still true.

**Yesterday.** A record whose day does not match the local date draws no line at
all and the headline says `LAST DATA 8/9`. A day-shaped picture of the wrong day
is the one lie this panel could tell.

**Absent.** No live record but the asset present: the silhouette, the axis and
the now-rule are drawn, the headline says `NO LIVE DATA` and the command that
fixes it, and there is nothing on the panel that could be mistaken for today.
Only a missing *asset* gets the plain no-data card.

#### Why it does not look like caiso

`caiso` is also one day across 320 columns with now marked, and the two had to
be tellable apart from across the room. They are, three ways. caiso is
**full-bleed** — a stacked area of five saturated fuels filling the panel edge to
edge and top to bottom, whose subject is the *composition* of a total. This is
**mostly black**: one dark blue silhouette that touches the top of the chart for
about twenty minutes a day, one gold line, and nothing else, and its subject is
*one quantity against its own history*. caiso is five hues at once; this is two,
and one of them is nearly the background. And caiso draws one day where this
draws two at the same time, which is the entire reason for the
silhouette-plus-line form. The shared vocabulary — a day axis, a now-rule, a
breathing pulse — is deliberate; that is the house style for a day chart in this
tree and it should be the same in both.

#### Motion, and the frame budget

Three things move, none of them decorative. Today's line **draws itself in**
over 1.6 seconds when the segment starts, wiping over a chart that already has
the silhouette on it rather than over a black hole. A **light runs along the
line** every 3.6 seconds, which is the one animation that says what the line is
— the day, moving. And a short pulse runs up the now-rule, which is the only
thing guaranteed to move in *every* frame; both are driven by the segment's own
`t` rather than the wall clock, so a test harness rendering a hundred frames in
a millisecond sees the same animation the wall does.

Everything else is rasterised once per cache read: the silhouette, the crust,
the line, the gridlines, the axis, the header and all five strings of the
headline strip, including the ladder of shorter forms each of them shortens
through. `render()` copies one frame, writes a comet of two dozen pixels and
draws the now-rule — about seven numpy calls on top of the copy. Measured here
over 700 frames: **mean 0.006 ms, p95 0.006 ms, worst frame 0.014 ms**, with
`build()` at 2.5 ms. At the 50–60× this tree measures desktop-to-Pi that is well
under a millisecond on the wall against a 50 ms budget; the full-frame copy is
memory-bound rather than clock-bound so call it 1–1.5 ms, which is still an
order of magnitude of headroom.

`render()` takes the present moment from the wall clock, exactly as `caiso`
does, so the now-rule is really now. With `--reload 0` it is a pure function of
`t` and the test script asserts that, because a demo that accumulates state
between calls desyncs from a scheduler that builds segments ahead on a worker
thread.

#### The other thing that had to be said in hyphens

`defcon.py`'s 3×5 font has no `=` glyph and silently draws a space for one, so
the first render of the note under the headline read `SHADED   13 RECENT
MONDAYS` and looked like a typesetting fault. It is `SHADED - 13 RECENT MONDAYS`
by necessity, which is the same trap the previous design hit with commas. The
axis labels and the scale tick were also drawn in the panel's faintest colour on
the grounds that they are small print; that colour peaks at 64 of 255, which is
under what a 3×5 glyph needs to survive being looked at from ten feet away.
Small print that has to be read is still print.

The screenshot above is the panel driven by a real Monday from the archive,
played back through the live code path at ten to six in the evening — the wall's
own record covers only the hours since the fetcher last started, and a
screenshot taken at half past eleven at night is a flat line in a corner. The
test script builds the same kind of record to assert the picture in pixels.

    python3 ftdata.py --once --only baywheels     # twice, ten minutes apart
    python3 bikes.py --host 127.0.0.1
    python3 bikes.py --at '2026-08-10 08:40'      # pretend it is the peak
    FT_DATA_CACHE=/tmp/empty python3 bikes.py     # the typical day alone
    python3 scripts/test-bikes.py
