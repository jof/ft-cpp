### muni

![muni](screenshots/muni.png)

The 19, 22 and 55 — the three buses the makerspace wiki names as ours —
converging on the four corners we actually stand at, drawn against the walk you
still have to do to meet them. It answers one question, the one somebody
walking past the wall actually has: **should I leave now, and for which bus?**

That question has two halves and every departure board in the world shows one
of them. "22 in 4 minutes" is useless on its own, because the 22's stop is
413 m away and that is seven minutes of Potrero Hill. The bus is not early; you
are late. So the panel draws the other half **on the same axis, to the same
scale** — and, since the second round of this design was watched on the wall,
also writes it out in words.

**One row of the panel is one stop, its name is written across the middle of
it, and the two directions come in from opposite edges to meet there.** That is
the representation everything else falls out of. The first layout gave a row to
each *route*, put our front door at the left edge and ran time rightwards; it
was true, it was legible, and direction of travel was not modelled at all.
Every bus arrived from the same side of the world, and the only thing
distinguishing the 19 going to Beach from the 19 going to the Shipyard was a
seven-letter word in the gutter. Standing at the window watching a 19 go past
the wrong way, you could not point at the row it was on.

Now distance from the centre is minutes-until-arrival, so buses slide *inwards*
and touch the name at the moment they pull in: inbound in from the left along
the top of the road, outbound in from the right along the bottom. Two buses on
the same street heading opposite ways, meeting the place you stand, which is
what is physically out there on 18th Street. This part worked on the wall and
is untouched.

**Two things did not work on the wall, and this round is about them.** The
feedback was "it's a bit unclear what the lines are meant to mean; it seems like
there is a dotted line under each bus somehow", and separately that what the
numbers measured was unclear. Both were real and both had the same root: the
panel was saying three things and drawing two of them the same way.

**The walk is now stated, not only drawn.** A post stands on the road at
exactly walking-time from the centre on each side, and the road between the two
posts is dotted rather than solid. The width of that dotted gate *is* the walk,
at the same pixels-per-minute the buses move at — so De Haro & 18th, 140 m
away, wears a narrow collar around its name, and 16th & Wisconsin, 413 m away,
has a gate half the row wide with only a few catchable minutes of street left
outside it. Nothing is drawn equidistant, and that inequality is the panel's
real content. But a width is not self-describing: it is elegant and a viewer
who has not been told what it is cannot work it out. So each direction now also
says `7 MIN WALK` in figures, in the gate's own colour, in the gap between the
destination label at the edge and the readout beside the name. Sharing the hue
is the entire trick — the caption teaches the mark, and `scripts/test-muni.py`
asserts the two colours are still one hue so that a later tweak to one constant
cannot quietly separate them. The figure is rounded **up**, never to nearest: a
caption reading 6 for a six-and-a-half-minute walk hands somebody half a minute
they do not have, which is the exact error this panel exists to remove. There
is no room for a fixed caption column — the space left depends on how long the
stop's name is — so the fit is measured and the widest of `7 MIN WALK`,
`7MIN WALK`, `7MIN` that fits is the one drawn.

**The numbers carry their verb now: `LEAVE 4`.** They always meant arrival
minus your walk, which is not what a bare figure beside a stop name means to
anybody who has ever seen a departure board — it means minutes until the bus.
So it was being read as the wrong quantity, silently, which is the worst way
for a panel to be wrong. The other option was to print minutes-to-arrival and
move leave-by somewhere else; that was rejected because minutes-to-arrival is
*already on screen*, to scale, as the bus's own distance from the centre.
Printing it again as a figure would spend the panel's most valuable columns
restating what the picture already says. The readout flanks the name on the
side that its direction comes in from, which is what says which buses it is
about; when nothing on that side is catchable inside the horizon it prints the
clock time of the next one instead, which needs no verb because the colon
carries its units.

**And "leave now" is a lit block.** Inside a minute of margin the reserved slot
inverts: filled with the warm near-white, `LEAVE NOW` punched out of it in the
background colour, pulsing on a 1.6-second triangle wave that never dims below
62% — a highlight that blinks dark is one somebody can walk past during the off
half. It is the only filled block anywhere on the panel and the only thing that
moves other than the buses, so it reads as *an alarm* from across the room
before anybody has read a word of it. One step below it, between one and three
minutes, the readout goes white-hot but stays type.

**The lateness rule is gone, and that is the answer to the dotted lines.** 511
hands back both what the timetable promised (`AimedArrivalTime`) and what is
going to happen (`ExpectedArrivalTime`), and the previous round drew the gap
between them as a faint dotted rule running from each bus back to a bright cap
at its due time. That made two different quantities dotted — the walk on the
road, lateness under the buses — and at 64 rows a viewer sees dotted marks in
two places and reasonably concludes they mean the same kind of thing. Neither
survived. Lateness was the least important of the three things the panel said:
the expected time is the truth and it is already where the bus is drawn, so how
far that has slipped from a promise is context, not an answer. Cutting it
leaves the gate as the only dotted mark on the panel, which is the whole point.
`AimedArrivalTime` is still fetched, because it is one integer per visit and
the record's shape is not the demo's to change, but nothing on screen depends
on it — and `test_lateness_is_gone` proves that by rewriting every `aim` in a
fixture to match its `exp` and requiring the frame to be byte-identical.

**Cutting it also paid for the buses.** A row used to need `8 + 2*bus` pixels —
name, a lateness rule and a bus band each side of one road row. It now needs
`6 + 2*bus`, and rather than banking two rows of air per row the buses grew
into them: four and five rows tall instead of three and four. On a wall read at
three metres a bus a third taller is worth considerably more than a gap.

**Six flows, four rows, and the rows are not the same height.** Grouping by
stop rather than by route collapses six (route, direction) pairs into four real
places, because the 55 and the 22 each have both directions at one corner — and
the 19 does not. Its two directions stop a block apart, at De Haro and at Rhode
Island, so it gets two rows with one live half each and one dark half each, and
that asymmetry is a true fact about the neighbourhood the old layout could not
express. The four rows get 16, 14, 14 and 14 of the 58 available rows, nearest
first: the near stop earns the extra pixels and a five-row bus instead of a
four-row one, because the stop you can reach in two minutes is the one you can
act on and the one seven minutes away is mostly there to explain why you
cannot. Equal bands were the first answer and they are the wrong answer.

**"Too late" still reads without a legend.** A bus outside the gate is one you
can still run for; a bus inside it will reach the stop before you can walk
there, and it goes grey to say so.

**The names are focal type, so they are cut down deliberately.** Three
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
$ python3 muni.py --now 1786562001                   # the screenshot's moment
$ python3 muni.py --source schedule                  # ignore 511, draw the timetable
$ python3 muni.py --horizon 25                       # a longer approach
$ python3 scripts/test-muni.py --cache-dir ~/.cache/ftdata
$ python3 scripts/test-muni.py --time-offset 86400   # prove the fixture is hermetic
```

Four things were harder than expected. The response from 511 is gzipped whether
or not you ask and carries a UTF-8 byte order mark, so the naive read dies on
byte one with a `UnicodeDecodeError` that says nothing useful. 16th & Wisconsin
is the 22's stop *and* a 55 stop, so its record carries both lines — but the 55
has its own stop 200 m closer, and a Wisconsin 55 drawn on the 55's row would
sit at completely the wrong walk distance; folding the 55 onto the 22's stop
would have saved two requests a pass and was not done for the same reason. The
two sides of that corner are spelled differently in GTFS — "16th Street &
Wisconsin St" against "16th St & Wisconsin St" — so grouping has to happen on
normalised cross streets rather than on the name, or the panel grows a fifth
row that is the same corner twice. And the check that there is only one dotted
mark left has to be written carefully: the road is (26, 29, 38) and the gate
drawn on it is (86, 76, 56), so a detector with its threshold at 24 sees the
gaps between the dots as lit, finds nothing dotted anywhere on the panel, and
passes.

The suite is 312 checks and it is **hermetic on purpose**, which took one
regression to learn. The panel's clock is pinned with `--now`, but a record's
*age* is measured against the real `time.time()` inside `ftdata.load()`, so the
fixture writes `fetched_at` relative to the real clock and never to the pinned
moment. Writing it relative to `NOW` gave a suite that passed for thirty
minutes of real time and then silently started rendering the schedule fallback,
failing fifteen assertions about position and colour that had nothing to do
with position or colour. `--time-offset` moves the real clock out from under
the suite so that property can be *checked* rather than remembered; it passes
312/312 at +1 hour and at +1 day.

It is a **wall-clock** panel — it reads `time.time()` once in `build()` and
every frame is a pure function of `t` from there, so segments animate and
previews bake reproducibly (the LEAVE NOW pulse included, since its phase comes
from that same clock plus `t`). `--now` pins the moment, which is how the tests
and the screenshot above get a fixed picture. It renders in 0.117 ms mean /
0.126 p95 on a desktop, against 0.096 for the layout before it, so the wall
should see about 3.5 ms where it measured 2.9.
