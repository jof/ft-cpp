### solar

![solar](screenshots/solar.png)

Will our own website survive the night? sequoia.garden is Sequoia Fabrica's
website — this makerspace's website, on a machine in this building, on a 12 V
battery behind a solar panel — and its front page says so itself: *"This is a
solar powered website. It may go offline!"* Nothing else on this wall is ours in
that way. `sfmix` and `bgp` are infrastructure we happen to sit near, `caiso` is
the whole state's grid seen from orbit; this is one battery, one panel, one
small computer, and it can actually lose. The panel draws its last twenty-four
hours as a landscape: terrain that rises and falls with the battery voltage, a
sky lit by the sun and glowing where charge actually went in, a cursor at the
present moment, and a battery in the right-hand margin with the state of charge
in it.

**One column per five minutes, and every other decision falls out of that.**
The endpoint publishes `sparklines`: seven parallel arrays of 288 buckets, with
`sparkline_meta` giving `bucket_ms` 300000 and `window_ms` 86400000 — exactly
one day at five-minute resolution. The panel is 320 columns wide. 288 of them
are the day at native resolution with no resampling, no interpolation and no
decimation, and the remaining 32 are the readout. It is the rare case where the
source and the display already agree about how wide a moment is, and the whole
design is just refusing to spoil that.

**x is time of day, not "the last twenty-four hours".** Those are the same 288
buckets either way, but binning them by *local time of day* rather than by age
nails dawn and dusk to fixed columns — midnight at the left edge, noon at column
144, midnight again at the right — so the lit band sits in the middle of the
panel every single day and the overnight trough is always the two dark ends.
Somebody who walks past this wall twice a week is then looking at the same
picture, differently lit, which is worth a great deal more than an axis whose
landmarks slide a column every five minutes. The cost is that the columns to
the right of the cursor are *yesterday's* tail rather than empty space. They
are drawn at six tenths brightness to say so — and six tenths is the second
number that went there. The first was a third, which looked correct in the
abstract and was wrong in practice: at nine in the morning, when a makerspace
fills up, the cursor is a third of the way across and *the entire solar event is
on the yesterday side*, so a third threw away the best part of the picture for
most of the hours anybody is standing in front of it.

**The battery turned out not to be the interesting variable, and finding that
out changed the panel.** The bank sits at 99.7–100 % state of charge essentially
all summer; a "battery fills and drains" chart of that is a flat line and there
is no picture in it. What is *not* flat is the terminal voltage: it sags all
night to about 13.24, lifts at first light, spikes to the charge controller's
absorb voltage — 14.32 V was observed at noon in August — and decays through the
afternoon. So the terrain is voltage, scaled to the day's own range with a floor
under the span so that a becalmed day is not amplified into a mountain range out
of sensor noise. The needle at midday is real and it is that sharp: it is the
controller hitting its absorb limit for two buckets and then backing off.

**The sky is two different things at once, and the gap between them is the
point.** Its blue comes from the *computed* solar elevation for this latitude
and this date — astronomy, what light was theoretically available — mixed
between a night gradient and a day gradient over the first twelve degrees of
elevation. The warm glow hugging the ridge comes from the *measured* charge
current, which runs 5–15 mA in the dark and past 300 mA at solar noon, and it
falls off exponentially above each column's own terrain so it moves up and down
with the hill under it. On a clear day the two agree and there is a white-hot
band over the hill at midday. On a foggy San Francisco week the sky is bright
blue and the ridge stays dark, and that difference — *the sun was up, and we got
nothing* — is the case this whole panel exists to be ready for. Both gradients
are darkest at the top, which is also how a real sky works and, more usefully,
means the header type sits on the deepest colour on the panel at every hour.

**Three states, because the demo is about fragility.** Fresh and full is serene,
and it is most of the time; that is allowed to be the boring case. Draining
tenses up — the ridge goes amber and then red, the ground turns from garden
green to something dry, and the state of charge blinks once it is under the
reserve mark drawn dashed across the battery. That mark is the reason the case
is worth 44 rows: without it the empty space above the level is just dark.
Silent is the funny one. If the record has aged past three TTLs — ninety minutes
of nobody answering — the panel stops pretending, dims the last day it *did* see
to two fifths as a ghost behind the words, and prints `NO ANSWER`,
`SEQUOIA.GARDEN LAST SPOKE 3H AGO` and `IT DID SAY IT MIGHT`. It does not claim
the site is down, because from the wall a dead server and a dead fetcher are
identical silences; it quotes the site's own warning back at it, which is true
either way. The site's separate `data_stale` flag — the web server answering
while the battery monitor behind it has gone quiet — is a different failure and
reads `QUIET` on a panel that still draws.

**Politeness is a design constraint here, which is new.** The fetch interval is
fifteen minutes, deliberately slower than the five-minute publication cadence,
because every request costs *that* battery a little radio and a little CPU and
it is the battery on the panel. Three extra columns at the right-hand edge are
not worth it from three metres away. The server is also, unsurprisingly,
sometimes slow to answer, so the timeout is thirty seconds and a failure simply
leaves the last record in place with an honest age on it. About 6 kB lands in
the cache: three of the seven published series rounded to the precision that
survives being drawn on a 64 row panel, plus a dozen scalars. `powerUsage` is
reconstructible from the other two and goes; `load_W`, `p_in_W` and
`powerUsage` all read exactly 0 for long stretches while the current is plainly
nonzero, so none of the three is trusted for anything the panel prints.

**Frame budget.** Everything is baked in `build()` — the sky field, the terrain,
the stars, the battery and every string — including both degraded cards, which
in an earlier draft re-rasterised three strings every frame and cost five times
what the panel with data on it cost. `render()` does one full-frame copy, two
ops for a sweep that only touches the ground, and writes a handful of short
columns: seven or eight numpy calls, none of them scaling with anything a knob
controls. Measured over 1500 frames: **mean 0.021 ms, p95 0.030 ms**, worst
frame 0.35 ms; the silent card is 0.014 ms and the no-data card 0.002 ms.
`build()` is about 3 ms, most of it a Python loop over 288 buckets doing a
`localtime()` and a solar-elevation series apiece — call it a third of a second
on the Pi, once, on the worker thread.

The one thing worth knowing about the sweep is why it is masked to the ground.
`caiso` lifts everything lit towards white and that works because its panel is
mostly black. This one has a lit sky across most of its width, and an unmasked
sweep was a travelling white bar. Baking the delta as zero everywhere except
the terrain costs nothing per frame and fixes it.

```console
$ python3 ftdata.py --once --only solar-garden
$ python3 solar.py --host 127.0.0.1
$ python3 solar.py --soc 24            # a foggy week, simulated — stamps SIM
$ python3 solar.py --off               # the website is not answering
$ python3 solar.py --quiet-sensor      # the site answers, its monitor does not
$ FT_DATA_CACHE=/tmp/empty python3 solar.py
$ python3 scripts/test-solar.py
```
