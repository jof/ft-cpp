### stringline

![stringline](screenshots/stringline.png)

Every BART train on one line, drawn the way railways have drawn them since the
1880s: a **Marey diagram**, distance down, time across, one diagonal per train.
The picture reads without a legend once you know what the axes are. The
**slope** of a line is the train's speed, so the run through the Berkeley hills
is visibly steeper than the crawl down Market Street, and a train standing at a
platform is flat. Trains going the **other way** lean the other way. Where two
lines **cross**, two trains passed each other, and those crossings are drawn in
white because "where do they meet" is the question the notation was invented to
answer. **Headway** is the horizontal gap between parallel lines, so bunching —
two lines converging — is visible half an hour before anybody on a platform
could know about it. The bright vertical is now, and the dots standing on it
are where the trains are at this instant.

Deliberately **not** another dot-on-a-map panel; the wall already has `adsb`,
`quake` and `sats`. There is no route map here on purpose. A map of BART tells
you where the stations are, which has not changed since 2018. A stringline tells
you what the trains are doing.

**Distance is real track kilometres, and that is the whole design.** Stations
are horizontal gridlines spaced by how far apart they actually are, not evenly:
the eight stations between Embarcadero and Balboa Park share seven rows because
they share seven kilometres, and Orinda to Rockridge gets more rows than all of
them because the tunnel under the hills is longer than the whole of downtown
San Francisco. An evenly spaced axis is tidier and is a diagram of a railway
where every train travels at a constant speed, which throws away the one thing
the notation is for. The kilometres come out of BART's own GTFS shape
polylines — each station projected onto the line's alignment and the cumulative
arc length taken, every station landing within 69 m of the shape — so the
Transbay Tube is as long here as it is under the bay.

**The Yellow line, because it is the one that crosses the whole picture.** It
is the busiest of the five (26 of the 83 trains BART had running the evening
this was written), the longest at 100 km, and the only one that touches
Antioch, the hills, the tube, Market Street and SFO. A hundred kilometres in
ninety minutes against ninety minutes of panel width means an end-to-end run is
very nearly the diagonal of the screen, which is exactly the scale a Marey
diagram wants. `--line` takes `orange`, `green`, `red` or `blue` as well; they
are shorter, and Red in particular is a beautiful sparse picture with the
crossings very clear, but they leave more of the panel empty.

**Past and future are drawn differently, because they are different.** Left of
the now-line the trains are solid; right of it they are dashed and knocked back
to half brightness. That is not decoration and it is not a guess about which is
which: a GTFS-Realtime TripUpdate contains only the stops a train has **not**
reached yet, and a stop drops out of the feed behind the train as it passes it.
So the solid half is composed of times BART published for stops within sixty
seconds of the train actually being there — an observation in every sense that
matters here — and the dashed half is BART's prediction, still being revised.
The right-hand edge thins out honestly too: a train that has not been dispatched
from Antioch yet is not in the feed at all, so nothing is drawn for it rather
than a timetable pretending to be a forecast.

The **colours are directions**, warm one way and cool the other, the same pair
`tide` uses for flood and ebb. Slope already says direction, but at this scale a
stringline leans about seventeen degrees off horizontal and telling +17 from −17
on a one-pixel line across a room is not something anybody should have to do.
The two terminals in the gutter are labelled in the colour of the trains heading
towards them, which is the entire legend.

**BART, because BART needs no key.** `https://api.bart.gov/gtfsrt/tripupdate.aspx`
answers 200 with about 39 kB of protobuf to anybody who asks — no signup, no
token, no terms beyond politeness. The obvious first choice for a wall in the
Mission is Muni, and 511.org's GTFS-RT returns **401 without a free-but-
registered key**, which was verified before any of this was written.

**The protobuf is decoded by hand, in about sixty lines**, rather than dragging
`gtfs-realtime-bindings` and therefore `protobuf` — a C extension, a wheel and a
version skew — onto a Raspberry Pi that has enough of those already. The wire
format is self-describing: every field is a tag varint carrying a number and a
type, and the four types that appear are a varint, a length-delimited block and
two fixed widths that can be skipped without understanding them. What is
actually needed is five field numbers. The honest cost of no schema is that a
field which *changed meaning* would be read as the old meaning; against that,
the reader cannot be broken by a field being **added**, which is the thing that
actually happens to these feeds. The test file encodes its own FeedMessage and
asserts the reader against it, including the two cases the live feed rarely
shows: a negative delay (protobuf writes a negative int32 as a 64-bit two's
complement varint, and reading it naively gives 1.8×10¹⁹) and a `SKIPPED` stop.

**The fetcher keeps the other half of the diagram.** Because a TripUpdate is
only the future, the past has to be remembered: each pass merges the new
predictions into what the previous record held for that trip, and a stop that
has fallen out of the feed keeps the last time it was given. `bart-stringline`
is therefore the only product in `ftdata.py` whose new record is a function of
its old one — it is registered with the same `["blob"] = True` marker `goes`
uses, purely to be handed the cache directory so it can read itself. It carries
ninety minutes, which is one end-to-end run of the Yellow line, and comes to
16 kB on a cold start and about 23 kB once the history has filled — a hundred
trips and sixteen hundred stop times, for all five lines. The cold-start consequence
is visible and worth knowing about: for the first forty minutes after the
fetcher is started, the left of the panel fills in from the now-line outwards,
because there is no history yet to draw.

**Trips have to be matched to a line, and the feed does not say.** BART's
TripDescriptor carries a trip_id and nothing else — no route, no direction, no
headsign. Two things recover it. First, a `trip_id → line` table baked out of
the static schedule; trip ids are regenerated whenever BART publishes a new
timetable, so this is only ever a *hint*, accepted when the live stop list is
consistent with it (all stations on that line, running the right way round,
ending at or before the scheduled terminal) and ignored otherwise. That check
had to be loosened once: BART's feed drops a trip's **final stop a station
early** — a Millbrae train's last update is SFO — and requiring an exact
terminal match threw away a quarter of the feed. Second, failing the hint, the
set of stations the trip calls at: a trip whose stops all lie on exactly one
line is on that line. Run against the whole static schedule that is right for
2384 trips, wrong for none, and undecidable for 346 — the SFO–Millbrae and
Warm Springs–Berryessa shuttles, which really are on two lines at once. A trip
neither method resolves is counted and dropped, never guessed at. Guessing
would put a Red train on the Yellow diagram, which on a stringline is not a
small error: it invents a headway that does not exist.

**Station order and distance are baked**, in `stringline-lines.npz` (16 kB, all
five lines, 105 platform ids and the trip hint table), because the static GTFS
is an 892 kB zip that must never be on a fetch timer. The baker lives in the
demo itself so that the asset and the code that reads it cannot drift apart:

```console
$ python3 stringline.py --bake-lines https://www.bart.gov/dev/schedules/google_transit.zip
$ python3 ftdata.py --loop 60 --due --fast &     # this one wants a minute
```

Re-bake it when BART publishes a new schedule. Nothing breaks if you forget —
the trip hints stop matching and the station-set fallback carries it — but a
station that moves or opens will be missing until you do.

**The panel is a sliding strip, which is the whole performance story.** A
stringline is a picture in *absolute time*: a train that passed MacArthur at
5:42 passed it at 5:42 no matter when you look at the panel. So the picture is
never redrawn as the clock advances — it is **slid**. Everything, gridlines and
clock ruler included, is rasterised once into a strip seven minutes wider than
the panel, and a frame is two slices out of it: solid up to the now column and
dashed after it, which works out to a fixed split because the now column never
moves. That comes to **about ten numpy calls a frame regardless of how many
trains are running**, against the several hundred line segments a naive redraw
would need, and it also removes any possibility of the picture jittering — it
translates by whole columns and by nothing else. One column is eighteen seconds,
so it steps left three times a minute, which is the honest speed of the thing
being drawn.

The dots on the now-line are read straight out of the same rasterised field at
the now column, rather than computed separately, so a dot **is** the place a
string crosses the present moment and the two cannot disagree.

The rebuild is one `np.interp` per train — a train is a *function* of time, in
one place at any moment, so its whole diagonal falls out of a single
interpolation onto the strip's columns instead of a segment-by-segment
rasteriser. Thirty trains rebuild in 1.2 ms on a desktop; it happens once a
minute, when a new record lands. Steady-state frames are 0.017 ms mean, 0.019
p95, on the same machine.

Three degraded states, all deliberate. No record at all draws `NO BART DATA`
and the command that fixes it. A record older than its five-minute TTL still
draws its trains — the geometry is still a true account of what was happening
then — with `STALE` and the age on the header. And **BART is shut for six hours
every night**, which is not an error: an empty record draws the grid, the
station names and the time ruler with `NO TRAINS RUNNING` across the top, so
the panel looks like a railway at three in the morning rather than like a
crashed demo.

Like `tide` and `adsb`, `render()` takes the present moment from the wall clock
rather than from `t`, so it is not a pure function of its argument. `--at` and
`--rate` move and scale its idea of now, which is how the contact sheets and
the tests are made.
