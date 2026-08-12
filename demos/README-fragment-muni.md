### muni

![muni](screenshots/muni.png)

The 19, 22 and 55 — the three buses the makerspace wiki names as ours —
approaching our own front door, drawn against the walk you still have to do to
meet them. It answers one question, the one somebody walking past the wall
actually has: **do I need to leave now?**

That question has two halves and every departure board in the world shows one
of them. "22 in 4 minutes" is useless on its own, because the 22's stop is
413 m away and that is seven minutes of Potrero Hill. The bus is not early; you
are late. So the panel draws the other half **on the same axis, to the same
scale**. The left edge is the door. Rightwards is twenty minutes of time, and
because you walk at a roughly constant speed, rightwards is also distance — one
pixel is about four seconds either way. The dotted stretch running out of the
door is the walk to that route's stop, ending in a post. Buses slide left along
the street and reach the post at the moment they reach the stop.

Everything then reads without a legend, because the geometry *is* the answer.
You leave the door and walk right; the bus comes left. **While a bus is still
right of the post you can make it. Once it is inside the dotted stretch it is
gone** — it will reach the stop before you can — and it goes grey to say so.
The number printed just inside the door is minutes until you have to start
walking, and NOW means put your shoes on.

**Putting the walk and the bus on one axis instead of two is the one choice
everything else falls out of.** The posts land in different places by
themselves: the 19's stop is 140 m away so its post is close to the door, the
55's is 187 m, and the 22's is a third of the way across the panel. That
staircase of posts is the panel's real content — three routes that a timetable
would list as equivalent are visibly not, and the frequent 22 is frequently the
one you cannot reach. It is also why this is not a departure board and not a
map: the only distance plotted is the distance *you* have to cover.

Deliberately not a fourth dot-on-a-map, and deliberately not `stringline`,
which is the nearest neighbour and also has time on one axis and distance on
the other. A stringline is about the trains — their speed, their headway, where
they pass each other — and carries no map on purpose. This is about the viewer,
and the buses get exactly as much detail as it takes to say whether you have
missed one.

**The bar under the street is lateness, drawn to that same scale.** 511 hands
back both what the timetable promised (`AimedArrivalTime`) and what is going to
happen (`ExpectedArrivalTime`), so the gap between them is a *length* on this
axis rather than a number to read: a faint dotted rule from the bus back to a
bright cap at the time it was due. Warm and trailing left means running late.
Cool and reaching right means running early, which sounds harmless and is not —
an early 22 is a 22 you will miss. On the morning in the screenshot the 22 was
running four minutes early and the 55 four minutes late, both visible at a
glance, and no other panel on this wall has that number at all.

**It says what it is.** The header goes green and says LIVE when it is drawing
511 predictions of tracked vehicles. When 511 marks a visit `Monitored: false`
it is quoting its own timetable back rather than watching a bus, and that bus
is drawn as a hollow outline instead of a solid, so a scheduled bus never wears
a tracked one's clothes. With no key, no fetch, or a record past its TTL, the
whole panel falls back to SFMTA's published timetable, the header turns amber
and says SCHEDULE, and every bus on it is hollow — which is the honest picture
and, pleasingly, came for free from the same rule.

**Two products, because the two questions are different.** `muni-18th` is
SFMTA's static GTFS off San Francisco's open data portal, keyless, fetched
daily, and it supplies the *geometry*: which stop is nearest for each route in
each direction, how far it is, how long that is to walk, and the fallback
timetable. `muni-live` is 511.org SIRI StopMonitoring and supplies the
*predictions*; it needs a free token in `$FT_511_KEY` and there is no default,
so a checkout that has never heard of one still draws a real panel.

**The stops are derived, not listed, and that matters more than it sounds.**
The fetcher takes every stop within 800 m of `ftsite.LAT`/`LON` and keeps the
nearest one *per route per direction*. The obvious alternative — nearest N
stops, or a quarter-mile radius — finds four stops of the 19 and 55 within
250 m and never reaches the 22 at all, and then draws a confident panel naming
three routes and showing two. A script already running on the Pi had exactly
that bug. `scripts/test-muni.py` asserts all three route numbers are present in
both directions, against the real fetched record.

**The rate limit is the design.** 511 allows sixty requests an hour per key and
StopMonitoring filters to exactly one stop per request — a comma-separated pair
returns zero visits, not two stops. Six stops is therefore six requests a pass,
and fifteen minutes between passes is 24 an hour, which leaves most of the key
for whatever else the space points at 511 later. Unfiltered the same endpoint
returns 35,573 visits, 32 MB decoded, which is sixty times this whole cache;
the filter is not an optimisation. Fifteen-minute-old predictions sound fatal
for a panel about the next four minutes and are not, because what is cached is
**absolute arrival timestamps**: 17:34:54 is still 17:34:54 a quarter of an
hour later, and the countdown on the wall is recomputed every frame. What ages
is the revision, not the clock, and the header carries the age when it matters.

```console
$ python3 ftdata.py --once --only muni-18th          # geometry + timetable
$ FT_511_KEY=... python3 ftdata.py --once --only muni-live
$ python3 muni.py --now 1786556684                   # pin the clock
$ python3 muni.py --source schedule                  # ignore 511, draw the timetable
$ python3 muni.py --horizon 30                       # half an hour of street
$ python3 scripts/test-muni.py --cache-dir ~/.cache/ftdata
```

Two things were harder than expected. The response from 511 is gzipped whether
or not you ask and carries a UTF-8 byte order mark, so the naive read dies on
byte one with a `UnicodeDecodeError` that says nothing useful. And 16th &
Wisconsin is the 22's stop *and* a 55 stop, so its record carries both lines —
but the 55 has its own stop 200 m closer, and a Wisconsin 55 drawn in the 55's
lane would sit at completely the wrong walk distance. Folding the 55 onto the
22's stop would have saved two requests a pass and was not done for the same
reason: the walk is the one thing this panel exists to get right.

It is a **wall-clock** panel — it reads `time.time()` once in `build()` and
every frame is a pure function of `t` from there, so segments animate and
previews bake reproducibly. `--now` pins that moment, which is how the tests
and the screenshot above get a fixed picture.
