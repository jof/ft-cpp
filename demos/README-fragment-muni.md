### muni

![muni](screenshots/muni.png)

The 19, 22 and 55 — the three buses the makerspace wiki names as ours —
converging on the four corners we actually stand at, drawn against the walk you
still have to do to meet them. It answers one question, the one somebody
walking past the wall actually has: **do I need to leave now?**

That question has two halves and every departure board in the world shows one
of them. "22 in 4 minutes" is useless on its own, because the 22's stop is
413 m away and that is seven minutes of Potrero Hill. The bus is not early; you
are late. So the panel draws the other half **on the same axis, to the same
scale**.

**One row of the panel is one stop, its name is written across the middle of
it, and the two directions come in from opposite edges to meet there.** That is
the representation everything else falls out of, and it is the second one this
panel has had. The first gave a row to each *route*, put our front door at the
left edge and ran time rightwards; it was true, it was legible, and it had one
hole in it — direction of travel was not modelled at all. Every bus arrived
from the same side of the world, and the only thing distinguishing the 19 going
to Beach from the 19 going to the Shipyard was a seven-letter word in the
gutter. Standing at the window watching a 19 go past the wrong way, you could
not point at the row it was on.

Now distance from the centre is minutes-until-arrival, so buses slide *inwards*
and touch the name at the moment they pull in: inbound in from the left along
the top of the road, outbound in from the right along the bottom. Two buses on
the same street heading opposite ways, meeting the place you stand, which is
what is physically out there on 18th Street.

**The walk survived the move, and it is now drawn twice.** A post stands on the
road at exactly walking-time from the centre on each side, and the road between
the two posts is dotted rather than solid. The width of that dotted gate *is*
the walk, at the same pixels-per-minute the buses move at — so De Haro & 18th,
140 m away, wears a narrow collar around its name, and 16th & Wisconsin, 413 m
away, has a gate half the row wide with only a few catchable minutes of street
left outside it. Nothing is drawn equidistant. The old layout said the same
thing as a staircase of posts marching rightwards; the new one says it as four
gates of visibly different widths, and mirroring it makes the comparison
easier, not harder, because both ends of each gate are on the same row.

**"Too late" still reads without a legend.** A bus outside the gate is one you
can still run for; a bus inside it will reach the stop before you can walk
there, and it goes grey to say so. Same rule as before, mirrored. The two
numbers flanking the name are minutes before you must leave, one per direction,
each on the side of the name that its direction comes in from; NOW means put
your shoes on, and when nothing on that side is catchable inside the horizon it
prints the clock time of the next one instead of going blank.

**Six flows, four rows, and the rows are not the same height.** Grouping by
stop rather than by route collapses six (route, direction) pairs into four real
places, because the 55 and the 22 each have both directions at one corner — and
the 19 does not. Its two directions stop a block apart, at De Haro and at Rhode
Island, so it gets two rows with one live half each and one dark half each, and
that asymmetry is a true fact about the neighbourhood the old layout could not
express. The four rows then get 16, 14, 14 and 14 of the 58 available rows,
nearest first: the near stop earns the extra pixels and a four-row bus instead
of a three-row one, because the stop you can reach in two minutes is the one
you can act on and the one seven minutes away is mostly there to explain why
you cannot. Equal bands were the old answer and they are the wrong answer.

**The names are the new focal type, so they are cut down deliberately.** Three
reductions, in order: street-type words go (every name here is an intersection
of two San Francisco streets, so ST/AVE distinguish nothing); `&` becomes `/`,
because defcon's 3x5 font — measured, not assumed — has no ampersand and `/` is
already what the fetcher uses for headsigns; and the street the panel itself is
on is elided, because writing 18TH on three rows out of four is three rows of
nothing. That street is *derived*, not hardcoded: whichever street appears in
the most stop names is ours by definition, it needs at least two appearances
before it counts, and it is then written once in the header where it labels the
whole panel. "Connecticut St & 18th St" becomes CONNECTICUT, and the one stop
that is genuinely somewhere else stays 16TH/WISCONSIN — which is exactly the
distinction worth the columns, since that is the far one.

**The bar along the road is lateness, drawn to that same scale.** 511 hands
back both what the timetable promised (`AimedArrivalTime`) and what is going to
happen (`ExpectedArrivalTime`), so the gap between them is a *length* on this
axis rather than a number to read: a faint dotted rule from the bus back to a
bright cap at the time it was due, on the lateness row belonging to that
direction. Warm and trailing means running late. Cool and reaching ahead means
running early, which sounds harmless and is not — an early 22 is a 22 you will
miss. Missed buses get no mark at all: how late a bus you cannot catch is
running is not information.

**It says what it is.** The header goes green and says LIVE when it is drawing
511 predictions of tracked vehicles. When 511 marks a visit `Monitored: false`
it is quoting its own timetable back rather than watching a bus, and that bus
is drawn as a hollow outline instead of a solid, so a scheduled bus never wears
a tracked one's clothes. With no key, no fetch, or a record past its TTL, the
whole panel falls back to SFMTA's published timetable, the header turns amber
and says SCHEDULE, and every bus on it is hollow — which is the honest picture
and, pleasingly, came for free from the same rule. Both bus sizes have their
own hollow silhouette, and both are mirrored per side, because a bus whose
bright leading edge is at the back reads as reversing into its stop.

**Two products, because the two questions are different.** `muni-18th` is
SFMTA's static GTFS off San Francisco's open data portal, keyless, fetched
daily, and it supplies the *geometry*: which stop is nearest for each route in
each direction, how far it is, how long that is to walk, and the fallback
timetable. `muni-live` is 511.org SIRI StopMonitoring and supplies the
*predictions*; it needs a free token in `$FT_511_KEY` and there is no default,
so a checkout that has never heard of one still draws a real panel. Note that
six stops became four rows and did **not** become four requests: the panel
groups two stops onto one row, it does not stop asking 511 about them.

**The stops are derived, not listed, and there is a specific thing this panel
replaces.** A cron job on the Pi called
`find_stops_within_radius("Sequoia Fabrica", radius_miles=0.25)` and took the
first three, which were 14352 (De Haro & 18th, 0.152 km) and 14125 / 14126 (the
two sides of Connecticut & 18th, 0.189 / 0.175 km). Every 22 stop on 16th St is
0.41 km or further — outside that radius — so in 212 consecutive runs it never
once showed a 22, while cheerfully claiming to cover the neighbourhood's buses.
This panel's fetcher instead takes every stop within 800 m of `ftsite.LAT`/`LON`
and keeps the nearest one *per route per direction*, which is
{14352, 16192, 17769, 17762, 14126, 14125} — a strict superset of the cron's
three, with the 22's two stops the addition. `scripts/test-muni.py` asserts that
superset by stop code, both in the record and in the drawn layout, since rows
are places now and there is only room for four of them; the row chooser claims
one row per route before distance gets a vote, precisely so the 22 cannot be
squeezed out a second way.

```console
$ python3 ftdata.py --once --only muni-18th          # geometry + timetable
$ FT_511_KEY=... python3 ftdata.py --once --only muni-live
$ python3 muni.py --now 1786559526                   # pin the clock
$ python3 muni.py --source schedule                  # ignore 511, draw the timetable
$ python3 muni.py --horizon 25                       # a longer approach
$ python3 scripts/test-muni.py --cache-dir ~/.cache/ftdata
$ python3 scripts/test-muni.py --time-offset 86400   # prove the fixture is hermetic
```

Three things were harder than expected. The response from 511 is gzipped
whether or not you ask and carries a UTF-8 byte order mark, so the naive read
dies on byte one with a `UnicodeDecodeError` that says nothing useful. 16th &
Wisconsin is the 22's stop *and* a 55 stop, so its record carries both lines —
but the 55 has its own stop 200 m closer, and a Wisconsin 55 drawn on the 55's
row would sit at completely the wrong walk distance; folding the 55 onto the
22's stop would have saved two requests a pass and was not done for the same
reason. And the two sides of that corner are spelled differently in GTFS — "16th
Street & Wisconsin St" against "16th St & Wisconsin St" — so grouping has to
happen on normalised cross streets rather than on the name, or the panel grows
a fifth row that is the same corner twice.

The suite is 219 checks and it is **hermetic on purpose**, which took one
regression to learn. The panel's clock is pinned with `--now`, but a record's
*age* is measured against the real `time.time()` inside `ftdata.load()`, so the
fixture writes `fetched_at` relative to the real clock and never to the pinned
moment. Writing it relative to `NOW` gave a suite that passed for thirty
minutes of real time and then silently started rendering the schedule fallback,
failing fifteen assertions about position and colour that had nothing to do
with position or colour. `--time-offset` moves the real clock out from under
the suite so that property can be *checked* rather than remembered; it passes
219/219 at +1 hour and at +1 day.

It is a **wall-clock** panel — it reads `time.time()` once in `build()` and
every frame is a pure function of `t` from there, so segments animate and
previews bake reproducibly. `--now` pins that moment, which is how the tests
and the screenshot above get a fixed picture. It renders in 0.096 ms mean /
0.127 p95 on a desktop, which is where the old layout sat too, so the wall
should see about the same 3.7 ms it measured before.
