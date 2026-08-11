### docks

![docks](screenshots/docks.png)

The Bay Wheels docks within a walk of the front door: how many minutes to the
nearest bike, whether it is electric, and whether there is anywhere near here to
leave one. It is the only panel on this wall that can change what somebody does
in the next sixty seconds, and that is the whole justification for the space it
takes. On the left, a map of the walking radius with the building at the centre.
In the middle, the eight nearest docks **by name**, with walk times. On the
right, the headline: `4 MIN`, and what and where.

**It is the companion to `bikes`, not a second version of it.** That panel is
the city — twelve kilometres of commute axis, half a day replayed, net flow
*inferred* from how dock counts changed between snapshots. This one is one
kilometre, right now, *counted*. They are deliberately drawn nothing like each
other: `bikes` is a dark landscape with comets crossing it and is meant to be
arresting; this is three panes of instrument, still except for one breathing
mark and a slow ring, and is meant to be read by somebody standing at the door
with a bag over their shoulder.

**A map is right here for exactly the reason it is wrong in `bikes`.** San
Francisco's 383 docks are a blob 11.8 by 11.3 km — square, 0.96:1 — so a
citywide map on a 5:1 letterbox spends three hundred columns saying the city is
square, which is why `bikes` uses distance-from-downtown as its axis instead. A
*local* map does not have that problem, because a local map does not have to
fill the panel: 58 × 57 pixels of it is a fifth of the width, at 39 m to the
pixel, and the other four fifths carry the words. The projection is
equirectangular with the same metres per pixel on both axes — isotropic, unlike
either of `quake`'s tiles — because at this size the rings have to be rings or
no distance can be read off it at all. There is no basemap under it: no streets,
no shoreline. At 39 m to the pixel a street grid is lit pixels edge to edge and
every one of them competes with a dock. What locates the eye is a green cross on
the building, rings at five and ten minutes' walk, and a 500 m bar.

**Every dock is a two-ended bar chart, and the mnemonic is up and down.** The
bright pixel is the dock. What grows *upward* is bikes you can take — green for
pedal, amber for electric, one to three pixels for 1–2, 3–6, 7+ — and what grows
*downward* is free docks you can leave one in, in blue, on the same scale. A
dock with nothing above it has no bikes and gets a red pip; a dock with nothing
below it is jammed full and gets one too, and it is **the same red**, because
they are the same disappointment from opposite directions. That symmetry is the
design. A station that is full is exactly as useless to somebody arriving as an
empty one is to somebody leaving, and a panel that drew only bike counts would
answer half the question and look complete doing it. Three steps rather than a
linear scale, because the map is not where you read a number off — the list is,
and the list prints it. What the map has to say from across a workshop is none /
a couple / a handful / plenty.

**The electric count is a field trap and it is half the point of the panel.**
GBFS 2.x defines `num_bikes_available_types`, which is the obvious place to look
for docked ebikes and which Lyft's San Francisco feed **does not publish at
all** — the key is absent from every one of the 634 stations, so code that reads
it finds zero everywhere and confidently reports a city with no docked electric
bikes. It has plenty: 79 of the 237 docked bikes within 1.5 km on the Monday
evening this was written, a third of the fleet. The field that works is
`num_ebikes_available`, and it is a *subset* of `num_bikes_available`, so the
pedal count is the difference. The panel splits them into two disjoint columns
that add to the total, in one place (`Station`), so that no two parts of the
panel can disagree about it. This matters because Potrero Hill is a hill, and an
ebike is a different proposition from a pedal bike on the way home.

**The free-floating ebikes are on the map too, as bare amber dots with no dock
pixel under them.** One of them is regularly closer than any dock — 321 m
against Jackson Playground's 292 on the evening this was written — and a panel
that preferred a dock for being a dock would be answering the wrong question.
The headline picks the nearest bike over *both* fleets and says `ON THE STREET`
when it is a loose one.

**Names, because a dot on a map is not something you can say out loud.**
"Jackson Playground" and "Rhode Island and 17th" are how people in this
neighbourhood actually refer to these, so the list is names and the shortener is
the transformation a person makes out loud: `Rhode Island St at 17th St` becomes
`RHODE ISLAND/17TH`, `22nd St at Potrero Ave` becomes `22ND/POTRERO`, and
anything that is not a junction — `Jackson Playground`, `Esprit Park` — is
already what people call it and is left exactly alone. Only a *trailing* street
type is dropped and never the only word in a part, so `St Mary's Square` keeps
its saint.

**Walk minutes, not metres.** 75 m/min is an ordinary adult pace, applied to the
straight-line distance, which in a grid like Dogpatch is close and in general is
a floor. It is the unit somebody standing at the door thinks in, and it
reproduces a hand-measured table of the neighbourhood exactly: 292 m → 4 min,
682 m → 9, 838 m → 11. The metres are in the record for anybody who wants them.

**Elevation is in the list because uphill and downhill are different walks.**
The heights are `bikes-terrain.npz`, the committed USGS 3DEP bake that `bikes`
uses, and the mark before each name is a caret up, a caret down or a dash at ±8
metres against the shop floor — warm for up, cool for down, so it survives being
seen from an angle where three pixels do not resolve into a shape. Potrero Ave
at Mariposa is 14 m above this room; Hubbell St is further away and 2 m below.
The shop's own height is the nearest baked dock's, because the bake is dock
locations and not a DEM, and the payload calls it `approx`.

**The wall's own coordinates, and a discrepancy worth knowing about.** This
product carries 37.7624929274026, −122.39969356310202, surveyed to the building.
`adsb.py`, `quake.py` and ftdata's `QUAKE_LAT`/`QUAKE_LON` carry
(37.7627, −122.3966), which is **273 m north-east of it**. At a 50-nautical-mile
radar picture or a 300 km earthquake map that is a fifth of a pixel and not
worth touching three products for; at 39 m to the pixel it is seven pixels, and
the difference between the nearest dock being Jackson Playground and being Rhode
Island St. So this one carries its own constant deliberately, and the two should
be reconciled on purpose rather than by one of them drifting.

**The data.** A new ftdata product, `docks-nearby`, off the same three keyless
GBFS feeds `baywheels` uses — `station_information`, `station_status`,
`free_bike_status` — but asking a different question of them, so it is a
separate product rather than more fields on that one. `baywheels` must not be
sampled faster than its ten-minute history bucket and must never be volatile,
because the accumulated half day is the only thing in it that cannot be
re-fetched; this one wants two minutes and is worth nothing after a reboot. The
crop is a *circle*, 1.5 km, sorted by distance: 45 docks and about 25 loose
bikes, stored against the panel's default 1.0 km of drawing so `--radius` can be
turned up on the wall without the fetcher having to agree. TTL ten minutes,
interval two — under `FAST_INTERVAL`, so the fast timer takes it — and the
record is volatile, so it lives in tmpfs and does not write the SD card 720
times a day.

**One piece of caching, and it is the only one in `ftdata.py`.** The three feeds
are 795 kB: information 348, status 243, free bikes 204. Taking all three every
two minutes would be 6.6 kB/s sustained, five times what `baywheels` costs and
more than this panel is worth. But `station_information` is near-static — names,
coordinates and capacities — so the *trimmed* version of it, the forty-odd
stations inside the radius at about 4 kB, is kept in the record and reused for
an hour. Steady state is 447 kB every two minutes, **3.7 kB/s**, with one 348 kB
request an hour on top. What that costs is that a station installed inside the
radius can take up to an hour to appear, which for a thing that happens a few
times a year is the right trade, and the cache is refused outright if it is from
a different radius or a different site rather than being paired with this pass's
counts. The record is 10.1 kB, of which 5.7 is what the panel draws and 4.2 is
that cache.

**No identifier of any kind is read out of `free_bike_status` here.** `bikes`
hashes the printed bike number because it has to match one snapshot to the next
to observe a journey; this product never compares two snapshots, so it has no
use for identity and takes none.

**Three honest failures.** Past the ten-minute TTL the panel draws with `OLD`
and the age in the header. Past thirty minutes the counts are **not drawn at
all** — the map furniture, the rings and the building stay, and the panel says
`COUNTS 45M OLD — NOT DRAWN` and, in the list pane, *a dock count this old is
not late, it is wrong about which dock is dry*. That is a sharper rule than most
panels here need and it is the right one: a tide table half an hour late is a
stale reading of a slow quantity, and a dock count half an hour late on a Friday
evening is a specific claim about which dock has two bikes in it that has been
false for twenty minutes. No record at all gets the card and the command that
fixes it. A record whose columns disagree in length is refused rather than
indexed into, because that draws perfectly and pairs one station's name with
another's counts.

**Motion, deliberately almost none.** One dim ring walks outward from the
building every seven seconds — which is not decoration, it is the radius being
paced out, and it is what the numbers on the right are counting — the nearest
bike's marker breathes at half a hertz, and a heartbeat blinks in the corner.
Everything else is baked once in `build()`. `render()` is a **pure function of
`t`** with `--reload 0`, which the test asserts by comparing a cold render at
t = 3.7 s against t = 3.7 s reached frame by frame from zero; with the default
`--reload 120` it consults `time.time()` only to decide whether to `os.stat` the
record, and re-parses only when the mtime has actually changed.

Measured over 400 sequential frames on the development desktop: **mean 0.019 ms,
p95 0.031 ms, max 0.050 ms**, about nine numpy calls a frame on arrays no bigger
than the 58 × 57 map pane. At the 20–115× this project keeps measuring between
here and the wall's Pi, call it 0.4–2.2 ms — comfortably inside the 20 ms budget
at 20 fps, with the rebake (a full re-read and redraw, once every two minutes at
worst) the only thing in it worth watching.

`python3 scripts/test-docks.py` is 104 checks: the projection against
hand-measured distances (the nearest dock **must** be Jackson Playground at
292 m, or the origin is wrong and the map still looks fine), up-versus-down read
back in pixels, the electric subset clamped so the pedal count cannot go
negative, a shut station's bikes not counted as available, the name shortener,
purity in `t`, and fresh/aging/stale/absent each in a process of its own with
`FT_DATA_CACHE` and `FT_DATA_BLOBS` set — the second of those because a volatile
product is looked for in the blob directory *first*, and seven checks in that
file passed against the live cache once before anybody noticed.
