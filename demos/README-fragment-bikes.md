### bikes

![bikes](screenshots/bikes.png)

San Francisco's shared bikes, drawn as what they actually are: a fluid on a
hillside. Bay Wheels is less a fleet of vehicles than a tide — every weekday
morning the city's bikes get ridden downhill and eastward into the financial
district, and every evening they come back up, while the operator's vans push
them the other way in between. The count of bikes in the city barely moves. What
moves is *where they are*, and a station at zero bikes and a station with no free
dock are both failures that a total cannot show. So the panel is a hill: all 383
San Francisco docks laid out left to right in order of **ground altitude**,
Embarcadero and Mission Bay at three metres on the left, Twin Peaks and Buena
Vista at a hundred and fifty on the right. The ridge is the city's own
hypsometry. Each dock colours the strip of ridge it sits on — hot amber where it
is dry, quiet teal where it is healthy, cold blue where it is jammed — and the
big number in the sky says how far the whole fleet has slid.

**Why a hill and not a map.** A map of the Bay with dots on it is what `adsb`
already draws, and `adsb` is about individual objects with velocity vectors,
which this is the opposite of: a slow scalar field over three hundred fixed
locations. But the stronger argument is that geography is not the variable that
explains this data and altitude is. Bikes roll downhill for free and have to be
pedalled, or trucked, back up, so gravity is the force the whole system spends
its day losing to, and putting gravity on the x axis is what makes the fight
visible. A map would spend three hundred columns saying that San Francisco is
seven miles square, and would put a station on Nob Hill two pixels from one at
the foot of it. Sorting by height puts them at opposite ends of the panel, which
is where they belong. The cost is that the picture is not a place — you cannot
find your own dock on it — and that is a real loss, taken deliberately.

**The number in the sky is the fleet's centre of mass.** The record carries two
averages: the mean altitude of a bike you could go and unlock, and the mean
altitude of a *parking space*, which is where the fleet would sit if it were
spread evenly across the docks. The difference is the headline, in metres.
Negative — the usual state by teatime — means the fleet has run downhill and the
hills are running dry. It is deliberately a metre count and not a bike count, so
it does not move when the operator adds a hundred bikes to the city overnight:
this panel is about *distribution*, which is the thing that actually fails, and
a number that mixed distribution with fleet size would be neither.

**The source.** GBFS, the open bikeshare standard, keyless and with no signup, at
`gbfs.lyftbikes.com/gbfs/en/` — note that `gbfs.baywheels.com` 301-redirects
there, so the demo uses the destination directly. Three files a pass:
`station_information.json` (348 kB, near-static: names, coordinates,
capacities), `station_status.json` (243 kB, regenerated every minute: bikes and
docks per station) and `free_bike_status.json` (200 kB: the undocked ebikes).
790 kB every ten minutes is 1.3 kB/s averaged, about half what `quake` costs.
`station_information` could be fetched far more rarely, and the first draft did;
re-fetching it every pass is what makes a newly-installed dock appear correctly
instead of being silently dropped, and 348 kB is not worth a staleness bug.
The record that comes out is **6.8 kB** — four arrays over the stations inside
the city, sorted by height, a 64-bin histogram of the loose bikes, and two dozen
scalars. The arrays stay per-station rather than being binned into panel columns
by the fetcher, for the same reason `caiso-mix` stores thirteen fuels and not
five bands: how to bin them is a drawing decision and belongs where it can be
argued with.

**GBFS has no elevation in it, so the elevation is baked.** `demos/bikes-terrain.npz`
carries the ground height of all 634 system stations, keyed by station id.

    source     opentopodata.org public API, dataset ned10m — the USGS 3D
               Elevation Program 1/3 arc-second seamless DEM, ~10 m posting,
               public domain, keyless
    stations   gbfs.lyftbikes.com/gbfs/en/station_information.json
    retrieved  2026-08-10, 100 locations per request at 1 request/second
    arrays     ids, elev (m), lat, lon, meta (the recipe, as text)
    licence    public domain (USGS); Bay Wheels GBFS is published openly

Baked rather than fetched because a terrain service is a second thing that can
be down and the ground does not move. A station the bake has never heard of —
one installed since — takes the height of the nearest baked station, which in a
city with a dock every few blocks is a great deal better than dropping it, and
is counted in the payload as `interpolated` so the number is checkable. Note the
`aster30m` dataset, which is the obvious first choice, is wrong here by ten
metres at the waterfront: it reads 11 m at Embarcadero and Bay where NED reads
2.8. On a panel whose whole low end is the interesting part that is not a
rounding error. There is no `scripts/make-bikes-terrain.py` in the tree because
adding one was outside the file list this demo was written under; the recipe
above is complete and reproduces the file exactly.

**The crop is San Francisco only.** Bay Wheels is one system covering four
separated cities — SF, Oakland/Emeryville/Berkeley across the bay, and San Jose
fifty miles south — and they do not share a commute, a terrain or a tide.
Putting them on one altitude axis would sit a San Jose dock at 25 m next to a
Nob Hill dock at 25 m and mean nothing by it. The box (37.700–37.840 N,
122.530–122.350 W) is the city and county plus the handful of Daly City docks on
its south edge: 383 of the system's 634 stations, and the ones whose hill is the
story. The other 251 are in the elevation bake, so changing the crop is one
constant.

**The occupancy ramp is diverging and its middle is the dimmest part of it.**
Empty and full are both failures and both have to be visible; a dock that is
between a fifth and four fifths full is working and nobody needs to look at it.
So the ramp runs hot amber at zero, through a quiet dark teal across the whole
healthy middle, to a cold near-white blue at capacity, and what glows on the
panel is what is wrong. Warm-is-empty is the convention every dock map uses and
was not worth being clever about. Individual failures also get their own marks,
because a column is one or two docks wide and averaging can hide a single dry
one: a dry dock flies a two-pixel flag above the ridge, which *pulses* — the
only animation here that carries meaning rather than merely proving the panel is
alive — and a jammed one bites two pixels down into the rock.

**The vertical scale is a square root, and the gridlines say so.** Half of San
Francisco's docks are below 21 m. Drawn linearly the entire interesting low city
is squashed into six rows and the panel is a flat line with a spike on the end;
under a square root it is a hill. The contours are labelled in metres so the
compression is declared rather than hidden.

**The mist above the ridge is a different fleet.** Several hundred ebikes are
parked loose at the kerb rather than in any dock, and they are a genuinely
different population: nobody rebalances them, they simply pile up wherever the
last rider left them. Having no dock, they have no altitude of their own, so each
takes the altitude of its nearest station and the histogram of that is stippled
at quarter density over the ridge. Where the mist is thick, loose bikes have
collected. It is drawn three rows clear of the crest and never on it — a
one-row error there would replace the occupancy colours with grey stipple and
read as "quiet" rather than as "missing", which is the failure mode the test
script checks for by name.

**The feeds have no history, so the fetcher grows one.** `station_status` is a
snapshot, and the commute pump is only visible over a day, so each pass appends
one sample to a rolling series inside the record: ten-minute buckets keyed on
absolute epoch, 24 hours, capped at 150 entries and trimmed on every write. That
keying is what makes every failure mode benign. A pass that runs twice inside one
bucket overwrites instead of lengthening the series; a missed pass leaves a hole,
and the hole is *visible* because the epochs are stored rather than assumed
regular; a clock that jumps backwards — a Pi with no RTC getting NTP for the
first time after boot — drops the future rather than leaving the series in an
order the demo would draw as a scribble. It is also the one product here that is
deliberately **not** `volatile`: the accumulated day is the only thing in this
cache that cannot be re-fetched, so it goes on disk and survives a reboot.

The lane draws that series as a signed area against the docks' own altitude, and
it **does not join up its gaps** — an hour when the fetcher was not running is
left blank rather than bridged, because the whole reason the series exists is to
show a shape and an interpolated shape is an invention in the shape of data. On a
cold cache almost the whole lane is gap, the caption reads `24H TRACK BUILDING`,
and it fills in over a day. The lane is scaled to the range the day actually had
rather than symmetrically around zero: in this city the fleet is below its docks
almost every hour of every day, so a zero-centred lane would leave half its
thirteen rows permanently blank and squeeze the few metres of daily swing —
which is the entire signal — into six. Zero is forced to stay inside the range,
so the reference line is always drawn and the sign is never in doubt.

**Three data states, and a fourth that is worse than stale.** Past its
half-hour TTL the panel still draws, with the age and `STALE` in red, because a
twenty-minute-old occupancy map is nearly right. Past `--max-age` (six hours) it
is refused outright and gets a no-data card naming the age: by then every dock
that was dry has been refilled, and a confident hillside of this morning's
colours is the one lie this panel could tell. No record at all gets the same card
and the command that fixes it.

**Frame budget.** Everything is baked in `build()` — ridge, rock, contours,
occupancy colours, mist, flags, lane, legend and header are rasterised once into
two uint8 frames. `render()` copies one, runs the sheen over a 32-column window
(one multiply, one add, one copy), writes the dry flags at a pulsing brightness
through a single fancy index, and draws the now-line in the lane. Eight or nine
numpy calls a frame, and the cost model on the wall is calls and not pixels.
Measured here over 3000 frames: **mean 0.026 ms, p50 0.027, p95 0.036, p99
0.048**, worst frame 0.067. `build()` is 2.0 ms. Even at a hundredfold that is
under 4 ms of a 50 ms budget. `render` is a pure function of `t` with
`--reload 0`, and the test script asserts it; with the default `--reload 300` it
asks the wall clock whether to re-read the cache, exactly as `caiso` does.

**What was hard.** Three things, all of them about the ridge. Laying stations
out by *metre* rather than by rank piles two hundred docks into the leftmost
fifty pixels and leaves the right half of the panel empty, so the x axis is
rank and the ridge is the sorted profile — which has to be said out loud,
because it looks like a cross-section of the city and is not one. Drawing the
ridge one pixel per column gives a dotted line wherever the hill is steep, with
sky showing through it, so the surface is a band from the ridge row up to
halfway towards its higher neighbour. And the per-column aggregation started as
`np.add.at` and then `np.add.reduceat`; the first is startlingly slow and the
second is simply wrong here, because the column slices overlap wherever a column
gets fewer docks than the one before it and `reduceat` can only sum between
consecutive start indices. It is a differenced prefix sum now, which is exact
and has no loop in it.

**One disclosure about the screenshot.** The hill, the numbers and the mist are a
real Bay Wheels snapshot. The 24-hour lane under it is synthesised, because the
series accumulates ten minutes at a time and this panel was written in an
afternoon; the first real day of it appears on the wall a day after the fetcher
starts.

    python3 ftdata.py --once --only baywheels
    python3 bikes.py --host 127.0.0.1
    FT_DATA_CACHE=/tmp/empty python3 bikes.py      # the no-data card
    python3 scripts/test-bikes.py
