### cityline

A whole day of San Francisco asking the city for something, replayed in half a
minute.

Every other city panel here is about vehicles — `stringline` is trains, `bikes`
and `docks` are bikeshare, `ships` is the bay, `adsb` is what is overhead. None
of them is about people. 311 is the other half of a city: the number you call
when the sidewalk is filthy, when somebody has tagged your roll-up door, when
the tree out front has dropped a limb, when the car across the driveway has not
moved in a week. Two and a half thousand of those land in a day and they have a
shape — three requests at four in the morning, three hundred and twenty in the
nine o'clock hour, a long afternoon that does not let up until the light goes.
That shape is the panel.

**Three panes, left to right.** The map is 62×57 pixels of San Francisco at
270 m to the pixel; each request blooms where it was filed, in its category's
colour, and fades to a floor rather than to nothing, so by mid-afternoon you are
looking at the accumulated day with the last hour bright on top of it. The
middle is twenty-four stacked hourly bars in the same seven colours, with a
playhead sweeping it — everything to its left in colour, everything to its right
a dim ghost of itself, so the day ahead is visible as well as the day behind.
The right is the total in the biggest type on the panel and then the legend,
which is also the tally: seven categories, seven colours, seven numbers that add
to the headline. The map and the chart are driven from one phase, so the bloom
and the bar are always the same ten minutes.

The white cross is the building. Nothing else on the panel is white. It gets no
label on the map, because `ftsite.SHORT` is `SF` and beside a map of San
Francisco that reads as the city rather than as this room; the name is spelled
out in the header instead, with the number of requests filed within a kilometre
of it — 45 on the day this was written, which is the number that makes the panel
land in the workshop rather than merely be about a city.

**The data.** DataSF's 311 Cases dataset (`vw6y-z8j6`) over Socrata's SODA API,
keyless. A `$select` of four fields turns a 1 kB row into 130 bytes; a day is
about three thousand of them, 380 kB on the wire, and about 16 kB reaches the
cache.

The dataset advertises itself as changing "multiple times per hour" and is in
fact a **nightly snapshot**: the newest case in it is always around midnight of
the previous day, loaded some time between one and four in the morning. So there
is no honest way to draw "today so far" from it, and the first design — a
rolling 24 hours ending now — would have drawn an empty afternoon every day.
What is there instead is better for this panel: one *complete* calendar day,
midnight to midnight, which is exactly the window a daily rhythm needs. The
fetcher asks for `max(requested_datetime)`, takes the calendar date off it and
fetches that day, so the window comes from the data rather than from the clock
and would still be right if the city ever went hourly. The header names the day
and how long ago its last case was filed; a dim dotted column marked NOW is
where the clock stands today against that curve.

`requested_datetime` is a floating timestamp in local time, which is convenient
— the `$where` bounds are local midnight to local midnight with no conversion —
and is a trap on a machine that is not set to Pacific. The wall is.

**What is not on this panel, and why.** 311 records are public and every one of
them is a record about a specific address. `address`, `service_request_id`,
`status_notes` and often a photograph are all in the response, and none of them
are read. Three reductions happen in `ftdata.py`, before anything is written to
disk:

* **Position is snapped to a 0.002° grid** — 223 m north-south, 176 m
  east-west, about two city blocks. That number was not chosen for privacy
  alone: the map above is 270 m to the pixel, so the quantum is *smaller than a
  drawn pixel* and the quantisation costs the picture nothing. A quantisation
  that is visible is one somebody will eventually be tempted to loosen. The cell
  is stored as a pair of small integers against a fixed origin, so the record is
  structurally incapable of holding a street address back, and the test asserts
  that by unpacking every point and checking it lands exactly on a grid centre.
* **Time is bucketed to ten minutes**, and duplicate (bucket, category, cell)
  triples collapse to one point. The exact counts survive in an hourly
  histogram, which carries no position at all — which is why the chart is drawn
  from the histogram and not from the points, and why the two disagree about
  totals on purpose.
* **Encampment reports are dropped outright** and never reach the cache. Matched
  on a keyword list — `ENCAMPMENT`, `HOMELESS`, `WELLNESS`, `WELFARE`,
  `MENTAL HEALTH`, `CRISIS`, `OVERDOSE`, `SYRINGE`, `NEEDLE` — rather than on
  today's category names, so a category the city adds next year cannot arrive
  through the unlabelled OTHER bucket. Deliberately not `SHELTER`, which would
  take MTA's bus-shelter complaints with it.

Included and named: **cleaning** (street and sidewalk cleaning, litter
receptacles), **parking** (enforcement, blocked street and sidewalk, MTA sign
requests), **graffiti** (public, private, illegal postings), **street** (defects,
sidewalk and curb, streetlights, sewer, water quality), **trees**, **noise**.
Everything else that survives the keyword filter — general requests, RPD, Muni
feedback, residential building, damage to property, taxi and AV complaints, the
administrative tail — lands in **OTHER**, which is drawn in grey and not broken
out, because a category with four requests in it is a label nobody can read and
a hint about who filed them.

Encampment is about 140 requests a day, five per cent of the total, and it is
the largest single thing thrown away here. An encampment report says where
specific unhoused people are sleeping tonight; a labelled, locatable dot for it
on a wall in a room the public walks through is a map of vulnerable people, and
folding it into OTHER would not fix that. So the headline on this panel is the
count of what is *drawn*, and it is about five per cent under the city's own
figure for the day. That is the same call `bikes` made when it hashed away the
per-bike identifiers it could have inferred journeys from, and it is the right
one.

**The map is `sfmix-map.npz`**, the same 768×768 bit-packed land/sea bake
`sfmix.py` draws its bay with. San Francisco occupies about 110 by 115 cells of
it, twice what this pane can show, so baking a second and finer coastline would
have bought nothing but a second asset to keep in step with the first. The
extent is fixed rather than fitted to the day's requests — the city has to be in
the same place every time the panel comes up — and reaches north to the Marin
headlands, because the Golden Gate is what makes the silhouette instantly San
Francisco rather than a generic peninsula. The land sits a dozen levels above
the sea and the shoreline four times that; the first version had land and sea a
few levels apart and the peninsula vanished into the bay from three metres away.

**What was hard.** The stacked bars, twice. Rounding each category's height
independently overshoots the bar by up to seven rows on the busiest hour of the
day, the top of the stack runs off the chart, and the category on top — OTHER,
always — silently vanishes from the one hour it mattered in. A stack missing its
cap looks exactly like a stack, so it was found by reading the nine o'clock bar
back off the panel in `scripts/test-cityline.py` rather than by looking at it.
The fix rounds the bar once and then rounds the *boundaries* off the cumulative
sum, so the segments add up by construction, and lends a row from the largest
segment to any category that has requests but rounded to nothing.

Second, unpacking cell indices in float32 puts the cell centre about half a
metre off its own grid — a latitude of 37.7 spends six of float32's seven digits
before the decimal point matters. Invisible on a 270 m pixel, and it would have
made the mechanical check of the privacy promise fail forever for a reason that
was not the point.

**Frame budget.** Nothing is computed per frame that could be computed once.
`build()` bakes 144 whole map images — one per ten-minute bucket, 1.5 MB of
uint8 — plus a lit and a dim copy of the chart and 144 pre-rendered clock and
running-count strips, because formatting and blitting a string is thirty numpy
calls and copying a baked one is a single `copyto`. The per-bucket state is
(which category last lit each pixel, how many buckets ago) rather than an
accumulated image, so compositing a fade 144 times cannot drift the early
morning to a different colour than it started. `render()` is then four copies,
one multiply and one fancy-indexed write for the current bucket's blooming
points, a playhead column and a heartbeat pixel: **eight numpy calls a frame**,
none of them allocating, and the count does not vary with how busy the day was —
a quiet 4 am and the nine o'clock wave cost exactly the same. Measured over 6000
frames on the development machine: **mean 0.007 ms, p50 0.007, p95 0.008,
p99 0.011**, worst frame 0.052 ms. `build()` is 19–22 ms here, once, on the
scheduler's worker thread, and most of that is the 144 map bakes. The baked
frames are about 2.2 MB of uint8, which is the one thing to know before putting
two copies of this in a rotation.

`render()` is a pure function of `t` and the test asserts it — a cold
`render(7.35)` against the same instant reached by driving 148 frames from zero,
and again after seeking elsewhere and back. Wall clock is read exactly twice,
both in `build()`: the age of the data, and where the NOW column goes.

Past its six-hour TTL the panel says STALE — on a nightly dataset a TTL can only
usefully mean "the fetcher has stopped", since the data is a day old by
construction. Past sixty hours of data age it says OLD, which means the *city*
has stopped, and the panel must not imply San Francisco simply had a quiet
Tuesday. With no record at all it draws the no-data card and the command that
fixes it.

Run:

    $ python3 ftdata.py --once --only sf311-day
    $ python3 cityline.py --host 127.0.0.1
    $ python3 cityline.py --cycle 45
    $ FT_DATA_CACHE=/tmp/empty python3 cityline.py     # the no-data card
    $ python3 scripts/test-cityline.py
