### wateryear

![wateryear](screenshots/wateryear.png)

California's water year, played in about twenty seconds and landing on today. A
mountain range across the top is the Sierra snowpack; eight vessels underneath
it are the state's major reservoirs, north to south; and the panel sweeps from
1 October to the latest day CDEC has, so you watch the snow build down the
mountain through winter, watch the snowline climb back up in April with
meltwater running off it into the lakes below, and watch the lakes rise while
it happens. Percent of capacity and percent of average for the date are the two
numbers on it, the second one big.

The wall already had the ocean — `tide`, `swell`, `ships` — and none of that is
the water anybody in this state argues about. The water that matters is stored
water, and it arrives on an annual clock: essentially everything California
gets falls between October and April, most of it lands as snow, and the
snowpack is a second reservoir — in a good year larger than every concrete one
put together — that releases itself over the following three months. That is
why this is not a row of bar charts. **The melt has to visibly become the
storage**, and that connection is the panel.

**Left to right is latitude.** Trinity, Shasta, Oroville, Folsom, New Melones,
Don Pedro, McClure, Pine Flat: 17.9 million acre-feet of the state's forty-odd,
running 40.8°N to 36.8°N in monotonic order, so the horizontal axis of the
picture is the map. The snow above them is in the same order — the Cooperative
Snow Surveys' North, Central and South Sierra indices, blended across the width
rather than drawn as three blocks, because a hard vertical seam between two
survey regions is a boundary that does not exist on the ground. The coupling is
**by latitude and not by watershed**, and that is worth saying plainly: Shasta
and Trinity are fed by the Trinity Alps and the southern Cascades and not by
the Sierra at all. What is true is that the mountains melt into the lakes and
that both are ordered north to south, which is enough for the picture to be
honest at a glance and is why the streams fall straight down. San Luis is
deliberately absent from the eight: it is off-stream, filled by pumping, and
its curve is a delivery schedule rather than a watershed.

A small `SF` tick on the valley floor is this wall's own latitude, read from
`ftsite.py` and interpolated between the two reservoirs it falls between (Don
Pedro and New Melones, as it happens). It is a position on the transect, not a
claim that anything about Sequoia Fabrica is in the Sierra.

**The amber dashes are the reference, and they move with the sweep.** Each
vessel carries its own normal storage *for the day being drawn*. Water above
the dashes is a surplus and water below them is a deficit, and eight of those
read at once with no arithmetic. On the screenshot Pine Flat is the one lake
visibly under its line while the other seven are over — the southern Sierra had
its own drought inside a statewide good year, which no single statewide
percentage would ever show you. That is the whole argument for drawing eight
vessels instead of one bar.

**Percent of average is derived here, and the panel says what the baseline
is.** CDEC's `RES` report does publish its own "% of historical average", but
against an unstated period of record, and only for today — there is no way to
ask it what average storage on the 3rd of February looks like, which is exactly
what a panel that animates the year needs. So fifteen complete water years,
2011 through 2025, are fetched once by hand and baked into
`wateryear-normals.npz`:

    $ python3 -c "import ftdata; ftdata.wateryear_bake_normals()"

Thirty-odd requests, about a hundred megabytes, a couple of minutes, run once a
year and committed. Nothing on the fetch timer ever touches history. The
resulting figure runs a few points *above* CDEC's, because 2011–2025 contains
two historic droughts and is a drier baseline than the longer one they use — so
the panel prints `VS 2011-25 AVG` under the number rather than the word
"average". A percentage whose baseline is a secret is not a number.

Averaging is by calendar date on a leap template rather than by "days since 1
October", which sounds like pedantry and is not: a leap water year is 366 days
long and a common one is 365, so indexing by day offset smears every normal
after February by a day, and 29 February ends up averaged against 1 March in
eleven years out of fifteen. The template puts 29 February in a slot of its
own; common years leave it empty and the mean skips it. `wateryear_doy()` is
that mapping and the test asserts every date in the year lands somewhere
distinct.

**Snow is measured, not scraped.** CDEC's `DLYSWEQ` summary has exactly the
numbers you want — stations reporting, average snow water equivalent, percent
of normal for the date, by region — and it is useless here, because it only
serves dates inside the snow season and freezes on the last one. Asked in
August it will cheerfully hand you June's numbers with today's date on the
page. So the index is computed instead: six snow pillows per region, sensor 82
(revised daily snow water equivalent), the mean of whichever of the six
answered that day, and a floor of three — two pillows out of six is not a
regional index, it is two mountains, and in a melt-out week the two that still
report are the two that are highest. The eighteen stations were picked for a
spread of basins and elevations and then checked one at a time against the
servlet for a continuous record back to 2011.

The mountain is white at 28 inches of index, which is set to a *normal* April
rather than to the record: the mean 1 April index across the fifteen baked
years is 29, 35 and 26 inches for the three regions, and in a normal April the
Sierra genuinely is white from the crest to the foothills. 2017 clips, which is
the right failure — the mountain is already as white as it can be drawn and the
caption is what separates a big year from a huge one.

**Everything CDEC gives you is a trap somewhere.** Missing data is `-9999`, not
null, so a fetcher that only checks for null writes minus nine thousand
acre-feet into the record. The date field is `2026-8-11 00:00` — unpadded — so
anything slicing fixed columns works for ten days a month. Rows for days a
station never reported are simply absent, so the response length is not the
number of days asked for and the series has to be assembled by date. And the
service is a state service on a state budget: it times out, and one dead
station here costs one vessel, one dead region costs a third of the snow band,
and a failed fetch leaves yesterday's record in place with an honest age on it.

**Reading `[-1]` is the bug this panel was always going to have.** CDEC's daily
values for today land some time in the morning, so for most of every day the
newest slot in every series is empty. Reading it rather than the newest number
reports a state-wide drought at breakfast and recovers by lunch, which is
exactly the kind of failure nobody catches by looking. Nothing in `wateryear.py`
indexes `[-1]`; `last_finite()` does it, per reservoir, and the test asserts
both that the synthetic record really does end in a hole and that the headline
is not it.

**Frame budget.** Everything is baked in `build()`. The sky, the rock, the
vessel shells, their labels, the year axis and the month letters are one uint8
frame; snow and water are two more, drawn through per-step thresholds so that
the entire picture is *two integer comparisons and two masked copies* a frame —
`ROWV >= LEV[j]` is exactly the wet pixels, because `LEV` is 32000 in every
column that is not inside a vessel. The water levels, the normal marks and the
snowline are precomputed as `(steps, 320)` int16 tables, one step per panel
column, which also makes the sweep index and the cursor's column the same
number and removes a class of off-by-one between the picture and the axis. Two
tiny particle systems and a few short writes are the rest.

The one thing that had to be fixed after measuring was the size of those two
comparisons. Done at full panel width they were 0.21 ms a frame here; cut down
to the band each one describes — seventeen rows of mountain, fourteen of vessel
— they are 0.08 ms. Measured over 1500 frames on the desktop: **mean 0.078 ms,
p50 0.073, p95 0.100, p99 0.116**, worst frame 0.162 ms; `build()` is 6 ms.
Against `caiso`'s measured desktop-to-Pi factor that is a few milliseconds a
frame on the wall, well inside 20 ms.

`render` is a pure function of `t` — the sweep, the surface shimmer, the
meltwater and the cursor all come off the segment clock, and the shimmer phase
in particular is derived from `t` and not from the frame counter, because a
demo that animates on `i` is a different animation under the preview baker than
it is on the wall. The test asserts a cold `render(t)` against the same `t`
reached frame by frame.

**Nothing here touches the network.** `build()` calls `ftdata.load()`, reads
one 13 kB JSON file and one 15 kB `.npz` beside the demo, and that is all. The
product is `wateryear`, ttl 30 h, refetched every 6 h against a source that
moves once a day, and deliberately not `volatile` — the payload is the year so
far, so a record that survives a reboot is the difference between coming back
up with the winter on the panel and coming back up with one column of it. Four
requests and 1.4 MB off the wire, trimmed to eleven series of about a hundred
and sixty samples: every second day, counted back from today, with both
of the last two days kept regardless of parity so the leading edge is never a
day older than it has to be.

A record past its TTL still draws — a year-shaped picture that is two days
behind is still that year — with the age and `STALE` in the header. A record
from the *previous* water year is refused outright and says so, because an axis
that runs October to September drawn with last year's numbers is a confident
picture of a season that did not happen. No record at all gets a no-data card.

Because the panel is a whole year, it is genuinely different in February from
how it is in August, which nothing else on the wall does. To see the other
season without waiting for it:

    $ python3 wateryear.py --hold-at 2026-02-15        # freeze on a date
    $ python3 scripts/test-wateryear.py --write-winter /tmp/wy-winter
    $ FT_DATA_CACHE=/tmp/wy-winter python3 wateryear.py --host 127.0.0.1

Run:

    $ python3 ftdata.py --once --only wateryear
    $ python3 wateryear.py --host 127.0.0.1
    $ FT_DATA_CACHE=/tmp/empty python3 wateryear.py   # the no-data card
    $ python3 scripts/test-wateryear.py
