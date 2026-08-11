### sfmix

![sfmix](screenshots/sfmix.png)

A NOC weathermap for the San Francisco Metropolitan Internet Exchange: the
oldest picture in network operations, drawn for the exchange this wall's owner
helps run. The fibre goes where the fibre actually goes, each span is coloured
by how much traffic is on it, and light runs along it at a speed proportional
to that traffic, so the map is alive rather than a diagram. Five metros from
San Francisco down to San Jose, the five inter-metro trunks between them, and
on the right the number an exchange is judged by — how many bits are crossing
it right now, today's curve, and where the peak was.

**The data is the exchange's own, from three keyless endpoints.**
`portal.sfmix.org/statistics/map/map.json` is the public structure: twelve
sites, five metros, twenty-two cables, and — the part that matters here —
`metro_cables`, pre-aggregated inter-metro trunks carrying their real coarse
fibre routes as lon/lat polylines. `/statistics/map/traffic` is live bits per
second per opaque cable id. `/statistics/metrics/?panel=ix_total&range=24h` is
the aggregate, ingress and egress summed over every member port at 300 s
resolution. Nothing needs a key and nothing here is private: the precise
carrier geometry and the cable-id-to-circuit mapping live in files the portal
never serves, and this panel never asks for them.

Both map.json and the traffic feed carry a `generation` string, and the fetcher
treats it as a **safety interlock rather than a version number**. The cable ids
are opaque *per generation* — rebuilt from scratch every time the portal re-runs
its NetBox build — so traffic joined onto the wrong generation does not fail
loudly, it quietly colours trunks with numbers belonging to other trunks. The
two are fetched, compared, and the structure refetched once if they disagree
(the ordinary race: the builder republished between the two GETs). A second
disagreement raises, and `fetch()` keeps the last good record.

About 135 KB of JSON becomes a 7 KB record. The twelve sites collapse to five
metros, because at this scale — eighty kilometres across two hundred columns,
so a third of a kilometre a pixel — the six Santa Clara facilities are the same
pixel and the six intra-metro cables between them are zero pixels long. The per
link 24-hour series and per-member breakdowns go entirely. The routes are
Douglas–Peucker simplified from 846 vertices to 153 at a tolerance of a third
of a pixel. The aggregate curve is bucketed from 289 points to 97 taking each
bucket's **maximum**, and the true peak and its timestamp are carried
separately, because the peak is the whole point of the curve and a decimation
that shaved it would be the one lie this record could tell.

**The map is turned forty-five degrees, and that decides the entire layout.**
SFMIX's footprint is a corridor — San Francisco and Oakland at the top, then
Fremont, Santa Clara and San Jose strung down the south bay. North up, that
cloud is 56 × 64 km: very nearly square, and a square on a 5:1 letterbox wastes
three quarters of the wall. Turned 45°, it is 82 × 23 km, an aspect of 3.62
against the map pane's 3.6, and it fits **at true scale in both axes with
nothing stretched**. The rotation is not a stylistic choice, it is the only way
this geography is a letterbox. So the arrow bottom-right says where north is
and the bar bottom-left says how far ten kilometres is, and it stays a real
map: anisotropic scaling would have filled the box exactly and would silently
have been a lie about distance, so the slack went into margin instead.

The alternative was the schematic subway diagram the portal itself draws when
zoomed out, which is more legible in the abstract and throws away the one thing
this particular audience already knows by heart — the shape of their own bay.
The coastline is the label that needs no text, and it is why the Dumbarton
crossing on the San Francisco–Fremont trunk reads as a bridge rather than as a
line that happens to bend.

**Two strands per trunk, because in and out are different numbers.** A
weathermap has split every link into two half-arrows since MRTG, and the reason
is that a link is not one quantity: San Jose–Fremont was carrying 118 Gb/s one
way and 67 the other while this was written, 19.6% and 11.2% of the same 600
Gb/s of fibre. So each trunk is two parallel one-pixel tracks either side of its
route, each coloured by *its own* direction's load, with light running along it
in that direction. The counter-flow reads from across the room, and the busier
half is both the warmer one and the faster one.

**The colour ramp is the portal's own, compressed four-fold, and the legend
says so.** SFMIX's map colours 0–80% blue-green-yellow-orange-red, which is the
right scale for a map you lean into and can spot a link about to melt. An
exchange deliberately overbuilds its backbone, so on that scale every trunk
here is blue, all day, forever — a dead panel that is also uninformative. This
one keeps the five hues and runs them **0 to 30 per cent**, which is where the
traffic actually lives: on a normal evening the quiet Santa Clara–San Jose
trunk is blue at 2.5%, San Francisco–Santa Clara is a yellow-green 11.9%, and
San Francisco–Fremont is orange at 24.3%. The ramp is drawn bottom right with
its numbers on it, because a colour scale without its numbers is decoration.
The compression is honest in the direction that matters: nothing on this panel
can look calmer than it is, and 30% or more clamps to red rather than wrapping.
The scale is fixed and not derived from the day's own maximum — a traffic light
whose boundaries move with the traffic is not a traffic light.

**Three things are deliberately not the ramp.** A `planned` trunk — San
Francisco–Oakland, in the structure and not yet lit — is dashed in the portal's
own slate blue, outside the ramp entirely, and carries no light; colouring an
unlit fibre "0%, healthy blue" would be the easiest lie available here. A trunk
whose members reported nothing at all is grey, which is a different statement
from zero. And a direction genuinely measured at zero *is* drawn at the bottom
of the ramp, because zero is a fact — but it gets no comets, since running
light along it would say bits are moving when the measurement says they are not.

**The right third is the aggregate.** Total exchanged right now, at 2x, large
enough to read from the far bench; today's 24-hour curve under it with the peak
marked as a dotted rule and labelled with its clock time; the time axis
captioned inside the chart at both ends because 64 rows had exactly one row
spare and the legend needed it. Ingress and egress across the whole exchange
agree to two parts in ten thousand — which is what an exchange *is* — so it is
one curve and the word is "exchanged" rather than a side picked arbitrarily.
The curve is zero-based: a traffic curve zoomed onto its own top few per cent is
the classic way to make a flat day look like an event.

**What was hard.** Captions. Five three-letter metro codes on an 80 × 23 km map
collide with each other and land on top of the trunks, and five-pixel white type
over a yellow cable is unreadable in a way a screenshot at 3x hides completely.
Two things fixed it: every caption gets a one-pixel dark halo around each
stroke, and each one is placed at whichever of four fixed offsets has the fewest
lit pixels already under it — scored against the half-drawn frame, so San Jose's
caption steps off the orange trunk that terminates on it. It scores once and
does not iterate, so a given metro's caption is in the same place every build.

The other one was the flow direction, and it is exactly why `test-sfmix.py`
exists. `render()` lights a pixel where `(s + speed·t) mod period` is near zero,
so the lit position along a strand is `s = −speed·t` and the sign that sends a
comet from a to z is a *negative* speed. The first version negated both the
phase and the speed for the reverse strand — which looks like the symmetric
thing to do, is a no-op on direction, and sent both tracks of every trunk the
same way. It is undetectable in a still frame and very hard to see in motion.
The test builds a synthetic trunk carrying traffic in one direction only,
identifies the comet pixels as exactly the pixels where the rendered frame
differs from the baked one, and measures a **circular** mean of their positions
modulo the comet period — a plain centroid jitters backwards at random as the
leading comet leaves the end while the next enters, and a test built on one
passes or fails by luck.

**Frame budget.** Everything is baked in `build()`: the sea, the shoreline, all
ten strands, the nodes, the captions, the header, the chart and the legend go
into one uint8 frame. `render()` does a full-frame copy, six arithmetic passes
over a flat array of the 1170 pixels that carry flowing light, one fancy-indexed
write of those pixels, and a one-pixel dot on the chart — ten numpy calls, all
into preallocated buffers, nothing that formats a string or allocates, and
nothing that depends on how many comets happen to be lit. Over 1200 frames on
the development machine: mean 0.027 ms, p50 0.026, p95 0.029, p99 0.039, worst
0.057. `build()` is 4–5 ms, once, on the scheduler's worker thread, most of it
resampling the coastline.

`render` is a **pure function of `t`**, which is unusual for a data panel here
and is asserted rather than assumed: a cold `render(4.35)` is byte-identical to
the same instant reached by stepping from zero.

**The coastline** is `sfmix-map.npz`, 4.5 KB: a 768 × 768 bit-packed land/sea
mask over lon −122.80..−121.60, lat 37.05..38.00, rasterised by an even-odd
scanline fill from the exchange's own committed, public, coarse basemap water
rings (`portal/mapbuild/data/basemap-water.json`, OSM-derived). It is
deliberately not `adsb-coast.npz`, which stops at 37.4 N and therefore has no
south bay — which is most of this map.

Product `sfmix-ix`, TTL 30 minutes, fetched every 5 minutes (the resolution of
the underlying counters; asking faster returns the same numbers and costs the
portal a Prometheus burst). Past its TTL the panel still draws, with the age and
STALE in red where the age goes, because the routes and the day's curve are
still true and only "now" has gone soft. With no record at all, a no-data card.

    python3 ftdata.py --once --only sfmix-ix
    python3 sfmix.py --host 127.0.0.1
    python3 sfmix.py --util-full 15        # a tighter ramp on a quiet day
    FT_DATA_CACHE=/tmp/empty python3 sfmix.py     # the no-data card
    python3 scripts/test-sfmix.py
