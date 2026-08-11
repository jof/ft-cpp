### bikes

![bikes](screenshots/bikes.png)

Half a day of San Francisco's bikes moving, replayed in half a minute. The
picture is a **cross-section of the city along its commute axis**: the left edge
is the Ferry Building at the foot of Market Street, the right edge is twelve
kilometres out at Ocean Beach and the county line, and height is ground
altitude — so the shape is the climb out of downtown, sea level on the left, the
ridge of Nob Hill and Buena Vista and Twin Peaks bulging through the middle, the
low sandy flats of the Sunset falling away on the right. All 383 San Francisco
docks are dots on it. Over that landscape, bikes move. It is a **time lapse**,
in the shape `goes` established: one pass through the last twelve hours at an
hour every 2.3 seconds, then a hold on the newest hour so the loop lands on now.
In one rotation slot you watch a whole commute — the morning pull into the
financial district, the midday lull, the evening scatter back out over the hills.

This replaced a version that drew the same feed as a hillside: 383 docks sorted
by altitude, coloured by occupancy, under a headline giving the fleet's altitude
anomaly in metres. That was a good picture of **state**, and the wall's owner
said, correctly, that it was hard to tell what people were doing. State is not
what people are doing. Movement is. What survived the rewrite is the committed
elevation bake, the honest degraded states, and the rolling series the fetcher
grows for itself; what went is the hill, the altitude-rank axis, the metre-count
headline and — late, and deliberately — a twelve-hour bar chart along the bottom
that was a good instrument and the wrong use of a sixth of the panel.

**Two things move, and they are two different kinds of claim.**

**The bright comets were watched happening.** This is the part that took a
measurement rather than a decision. `free_bike_status.json` carries two
identifiers per undocked ebike: `bike_id`, an opaque 32-hex token, and `name`,
the number printed on the physical bike (`190-591`). GBFS rotates `bike_id`
between rentals *specifically* so that trips cannot be reconstructed, and it
does — across two snapshots 36 minutes apart, **0 of 634 tokens survived**, and
across two four minutes apart 590 of 624 survived but not one of the survivors
had moved, which is the signature of a token that is stable exactly while the
bike sits still. `name` is not rotated: **585 of 620 survived 36 minutes**, with
a median displacement of 4.5 m and a 90th percentile of 11 m — GPS jitter — and
nine bikes that had plainly been ridden somewhere, the furthest 4.1 km. So for
the free-floating ebikes, a journey is an *observation*: the same physical bike
at a new place at a new time. Those are the near-white marks with a coloured
tail, the brightest thing on the panel.

**The dim field is inferred, and the panel says so.** Docked bikes have no
per-bike record in GBFS at all — `station_status` is counts and nothing else,
and `ebikes_at_stations.json` currently returns zero stations — so for the other
~2 700 bikes the panel has only how the counts changed between two snapshots ten
minutes apart. The city is cut into forty bands of distance from downtown; the
running sum of their net changes is the number of bikes that **had to** cross
each distance, which follows from arithmetic and not from a model; and each dim
dot is one bike of that net displacement carried from an emptying band to a
filling one along the **least-total-displacement matching** (the one-dimensional
optimal transport coupling, which never claims a bike went further than it had
to; matching at random would give the same flux and a great deal more apparent
traffic, and the extra would be invention). Before any of that the imbalance is
removed — the docked fleet is not closed, bikes leave it for the kerb and for
vans — by spreading the residual across the bands in proportion to how many docks
each has, which is an assumption, is stated in the code, and is a couple of bikes
a band on a typical ten minutes.

The two are separated three ways so nobody has to read a legend to see that they
are different: the observed marks are **brighter**, they have a **longer trail**,
and they fly in a **lane of their own** eleven rows above the terrain while the
inferred field hugs it. The legend then says it in words anyway:

    SEEN▮ 298 OF 602 FREE EBIKES        IN▮ OUT▮ REST FROM DOCK COUNTS - NOT TRIPS

and the caption beside the headline repeats `NET FLOW - NOT TRIPS`, with a
ladder of shorter forms — `REST FROM DOCK COUNTS - NOT TRIPS`, `FROM DOCK
COUNTS - NOT TRIPS`, `NOT TRIPS` — so the caveat is the last thing a narrow panel
drops rather than the first. (There are no commas anywhere on this panel:
`defcon.py`'s 3×5 font has no comma glyph and silently draws a space for one, so
the first render read `NET FLOW  NOT TRIPS` and looked like a typesetting bug.
The punctuation is hyphens by choice.)

**Privacy, which was a decision and not boilerplate.** The GBFS spec rotates
`bike_id` to prevent exactly what `name` makes possible again, and this panel
hangs on a wall in a public makerspace. So the printed number is hashed in the
fetcher the moment it is read and never reaches a variable that is stored; the
tokens live only in `loose_base`, which holds **one** snapshot and is overwritten
every pass; and **no identifier of any kind enters the rolling twelve hours**.
The record therefore cannot link a bike across more than a single ten-minute
interval however long the fetcher has been running — there is no accumulating
trip history in it to obtain. What survives into the history is a pair of
positions on the panel's distance axis, rounded to 100 m, with no way back to
which bike made it. The hash is not itself the control and is not claimed as one:
six-digit bike numbers are a small enough space to enumerate, so somebody holding
a record could recover the current snapshot's numbers — which the public feed
already gives them. The control is that history carries nothing. Nothing on the
panel is a bike number. A viewer sees traffic, never a bike they could go and
look for. `scripts/test-bikes.py` asserts all of that against the serialised
record, including that no `NNN-NNN` string survives anywhere at any depth.

**What is deliberately not drawn.** In four minutes about nineteen ebikes vanish
from the feed and thirteen appear. Vanishing usually means the bike was docked or
picked up by a van; appearing means undocked or released, or a rental ending.
They are journey endpoints with one end unobservable. They are counted in the
record — `hist.gone` and `hist.came` — and never drawn, because a dot appearing
out of nothing reads as a bike arriving from somewhere, which is the one claim
that cannot be made. Nineteen and thirteen against two observed movers is also
the honest scale of what this feed hides.

**Coverage, stated on the panel.** The comets are the free-floating ebike fleet,
about 620 bikes, not the 383-dock system and not the ~2 700 docked bikes. The
legend gives both numbers.

**The headline is a floor.** It counts docked bikes that changed place: the sum
of |change| over every station, halved, because a bike ridden from one dock to
another shows up as minus one at one end and plus one at the other. Measured on
the live feed at ten on a Monday night: 88 gross changes in five minutes, which
is 528 an hour; the peaks are four figures. It is a lower bound three ways over —
two riders cancelling inside one ten-minute window are invisible, a bike left
loose at the kerb is a departure with no arrival, and a rebalancing van moving
fifteen bikes at once is indistinguishable from fifteen riders. It is the biggest
honest number this feed contains and the one somebody can read in two seconds,
which is why this demo is in the SPARSE set.

**Why not a map, and why not a second `winds`.** `winds` is already a particle
field over a map of this bay, and the worst outcome of this rewrite would have
been two panels that look the same from across the room:

| | `winds` | `bikes` |
|---|---|---|
| field | smooth and continuous | discrete, sourced and sunk at fixed points |
| ground | full-bleed colour wash, filled sea and land | near-black, a dot constellation, a dim terrain band |
| marks | streaks everywhere, always present | dots that arrive in bursts and fade out, plus a few bright comets |
| colour | wind speed | direction, and what that direction means socially |
| time | sweeps *forward* through a forecast | sweeps *backward* through the observed past |
| chrome | a speed ramp along the bottom | one legend row and a one-row scrub bar |

A map would have been wrong on its own merits too. Measured off
`station_information.json`, San Francisco's 383 docks are a blob 11.9 km by
12.4 km — aspect ratio 0.96, i.e. square. On a panel five times wider than it is
tall, a map of that spends three hundred columns saying the city is square and
puts a Nob Hill dock two pixels from one at the foot of it. Distance from
downtown is the one spatial variable this data actually varies along, and putting
it on the long axis buys 320 columns over 12 km — 37 m a column.

**Gravity is the other axis because gravity is the explanation.** Bikes roll
downhill for free and have to be pedalled, or trucked, back up, which is why the
fleet drifts to sea level every day and why the operator runs vans at all. The
two axes are the two forces on the system: the social pull of downtown and the
one it is fighting. The terrain is the 25th-to-75th percentile of dock height in
each band with the median as the line the swarm rides — the spread is drawn
rather than hidden, because at four kilometres out the city contains both the
Mission flats and Buena Vista Park and one line would be a lie about that. The
scale is linear, not the square root the hillside version needed: on a rank axis
half the docks were under 21 m and had to be stretched, but on a distance axis
the median profile runs 3 m at the waterfront to about 90 m at the crest and
spreads across the rows on its own.

**The docks are quiet and only the failures are loud.** The hillside version put
a diverging amber-to-blue occupancy ramp on every dock; with a swarm moving over
it, three hundred coloured dots competed with the thing you are meant to watch.
So the ramp's own principle — that the healthy middle should be the dimmest part
of it — is taken to its limit: an ordinary dock is one dim slate pixel, a dry one
is two amber pixels, a jammed one is a pale blue pixel. Amber is spent in exactly
one place on this panel. The undocked ebikes are also a stipple along the plinth
under the landscape, binned on the same distance axis.

**Restraint, because the brief for this rewrite was a compelling picture of real
data and not an instrument.** An earlier draft carried a ten-row bar chart of the
last twelve hours along the bottom, with a bar per bucket, signed by direction.
It read beautifully and it was the wrong thing to spend a sixth of the panel on —
the replay *is* the time axis, and the commute surges in the swarm itself.
Removing it gave the landscape 51 rows instead of 40, which is the difference
between a chart with dots on it and a place with weather in it. What is left is a
header, one headline, one legend row and `goes`'s one-row scrub bar.

**The source, and being polite to it.** GBFS, keyless and with no signup, at
`gbfs.lyftbikes.com/gbfs/en/` — `gbfs.baywheels.com` 301-redirects there, so the
fetcher uses the destination directly. Three files a pass:
`station_information.json` (348 kB, near-static), `station_status.json` (243 kB,
regenerated every minute) and `free_bike_status.json` (206 kB). 790 kB every ten
minutes is 1.3 kB/s averaged, about half what `quake` costs. Ten minutes is also
exactly the history bucket, so one pass is one difference; sampling faster would
lower the floor the headline represents and cost a public server more, and ten
minutes is where those two arguments met. The TTL is half an hour.

**The record, and what it costs a Raspberry Pi.** **29.8 kB** at full stretch —
twelve hours, 72 buckets — against 13 kB on a cold cache with the arrays and no
history. For scale, `goes` keeps a 3.5 MB sidecar. The shape:

    dist_m, elev_m, fill_pct, free_docks, open   383 ints each, sorted by distance
    loose_bins                                   40 ints
    hist.t / mov / dt / seen / gone / came        72 numbers each
    hist.flow                                    72 x 40 ints   <- 9 kB, the bulk
    hist.trk                                     72 x [from, to, ...] in 100 m units
    base.sid / at / bikes                        2298 chars + 383 ints
    loose_base.k / lat / lon                     ~620 x (8 chars + 2 ints)

The flow is binned to forty bands *in the fetcher* rather than kept per station,
which is the one place this record departs from the house rule that binning is a
drawing decision: 383 numbers per ten minutes for twelve hours is 55 000 of them,
and forty is already finer than the shortest real feature in the field. The
per-station arrays stay per-station, because how to draw a dock is still a
drawing decision.

`base` and `loose_base` are the only things in the payload that are state rather
than observation: the snapshots the *next* pass differences against. Station
identity is six hex characters of SHA-1 per station id — 2.3 kB, against 14 kB
for the raw UUIDs — and matching on that hash rather than on array position is
what makes a station being installed, removed or renumbered cost nothing.
Position matching would silently shift every station past the new one and invent
a citywide flow out of an insertion. Both live in the record and not in a
`store_blob` sidecar because sidecars live in tmpfs and a reboot would then cost
a bucket every time. For the same reason this is the one product in `ftdata.py`
deliberately **not** `volatile`.

**Four ways the differencing declines, all benign, all tested.** No baseline —
the first pass after a cold start or a version change — gives one bucket with no
flow in it. Two passes closer together than four minutes decline *and keep the
old baseline*, so the next ordinary pass still gets a full-length difference
rather than inheriting a ten-second one; replacing the baseline there is the bug
that would make a doubled pass erase a good interval. More than forty minutes
apart declines and resets, because by then the two snapshots straddle enough of a
commute that "net change" stops describing a flow. A clock that jumps backwards —
a Pi with no RTC getting NTP for the first time after boot — declines and resets
rather than storing a negative interval. The series itself is keyed on the
absolute ten-minute bucket, trimmed to twelve hours and 80 entries on every
write, and a record written by a version that stored different columns fails the
length check and starts fresh rather than being extended into a shape the demo
would misread. The same three windows govern the ebike tracks.

**Cold start is a designed state and will be the first thing the wall shows.**
The flow needs two snapshots, so a wall that has just booted has none. It draws
the city, the docks and their occupancy, and says `LEARNING FLOW` with `NEEDS TWO
FETCHES - FIRST IN 8M` under it, and no swarm and no rate at all. As buckets
accumulate the replay window grows with them: `REPLAY OF LAST 40M`, then `2H`,
then the full `12H` after half a day, and the header prints `12/72` beside the
age while the window is materially short — `goes`'s convention and its ninety per
cent threshold, because one or two missed passes out of seventy is the feed
having an ordinary day and is not worth a number on the wall.

**Three data states, and a fourth that is worse than stale.** Past the half-hour
TTL the panel still draws with the age and `STALE` in red. Past `--max-age` (six
hours) it is refused outright and gets a card naming the age: a confident swarm
of this morning's flow under an evening clock is the one lie this panel could
tell. No record, half a file, arrays of mismatched length and a record sorted the
wrong way round all get the same card and the command that fixes it. An hour that
was never fetched draws `NO DATA / THIS STEP WAS NEVER FETCHED` rather than being
replayed as a quiet one.

**Frame budget.** The landscape, the docks, the header, the legend and *all
twelve captions* are rasterised once in `build()` — the last of those is `goes`'s
rule, that a caption belongs to the moment it describes, and it is worth
following: doing it on the step change instead cost a 0.3 ms spike twelve times a
cycle, which is nothing here and six times the mean on the Pi, and is exactly the
shape of thing that becomes a dropped frame in a transition. `render()` copies
one frame, blits the 19-row caption box, and advances the two swarms through five
passes of about fifteen numpy calls each on arrays of a few hundred. Measured
here over 2000 frames of a full twelve-hour replay with the peaks saturating the
440-particle pool: **mean 0.098 ms, p50 0.112, p95 0.131, p99 0.214**, worst
frame 0.406. `build()` is 5.7 ms. At the ~60× desktop-to-Pi ratio measured across
this tree that is about 6 ms mean and 8 ms at p95 against a 50 ms budget at
20 fps. `render` is a pure function of `t` with `--reload 0` and the test script
asserts it against ten awkward values of `t`; with the default `--reload 300` it
asks the wall clock whether to re-read the cache, exactly as `caiso` does.

Two tricks paid for most of it. The swarm is written through a single unmasked
scatter: a particle outside its own flight window comes out of the fade envelope
at brightness level zero, which is black in the palette, and its target index is
multiplied by that same zero — so it writes black to pixel (0, 0), the corner of
the header, which is black anyway. No mask, no branch, no compaction. And the
caption is a halo blit rather than a clearance check: the one-pixel border around
each stroke is darkened before the stroke is drawn, which lets text sit over the
terrain instead of being dropped whenever the two would meet. The first version
checked the terrain under each line and gave way, which meant the caveat vanished
on exactly the days the panel was busiest.

**What was hard.** Four things. The axis: it took measuring the dock cloud
(11.9 by 12.4 km) to be sure a map was wrong rather than merely awkward, and the
choice of distance-from-the-Ferry-Building over a PCA principal axis or altitude
rank is the whole design. Deciding what an inferred particle is allowed to mean;
the monotone transport coupling is the answer that lets the field be drawn
without claiming anything the counts do not contain, and `scripts/test-bikes.py`
asserts its direction three separate ways — off the arithmetic, off the baked
endpoints, and off the rendered pixels by counting hues while a synthetic city
empties its hills into its downtown, then repeating the whole measurement with
every count negated and requiring the answer to come out the other way. Third,
the identifier question, which had to be answered with two live probes rather
than from the spec, because the spec says `bike_id` rotates and is silent on
`name`. And fourth, a test-harness bug worth writing down: a synthetic record
dated eight in the morning was also *fetched* at eight in the morning, so on an
evening test run the demo refused it as thirteen hours old and every direction
check silently had nothing to measure. The test script now separates the two
clocks and says why.

**One disclosure about the screenshot.** The landscape, the 383 docks, their
occupancy and the header counts are a real Bay Wheels snapshot. The twelve hours
of flow and ebike tracks under it are synthesised, because the series accumulates
ten minutes at a time and this panel was written in an evening; the live fetcher
was verified end to end and did produce real observed tracks — one ebike seen
moving from 3.7 km to 4.4 km out over five minutes, with 587 ebikes present in
both snapshots, 14 gone and 5 appeared. The first real half-day appears on the
wall twelve hours after the fetcher starts; before that the panel draws the
cold-start state described above, honestly.

    python3 ftdata.py --once --only baywheels   # twice, ten minutes apart
    python3 bikes.py --host 127.0.0.1
    python3 bikes.py --no-seen                  # the inferred field alone
    python3 bikes.py --hours 6 --step 1800      # finer, six hours
    python3 bikes.py --cycle 90 --particles 700 # slower and busier
    FT_DATA_CACHE=/tmp/empty python3 bikes.py   # the no-data card
    python3 scripts/test-bikes.py
