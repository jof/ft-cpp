### bgp

![bgp](screenshots/bgp.png)

The internet's routing table, churning, as San Francisco's own exchange hears
it. Fifteen minutes of the global default-free zone across 320 columns, second
by second, with a ticker of the actual prefixes scrolling underneath. The number
in the corner is how many prefixes a second are being announced or withdrawn to
the RouteViews collector at SFMIX — which is a couple of miles from the wall and
is where the makerspace's own ISP hands its traffic off. The routes on this
panel are the ones the room's packets are steered by, which is not a claim any
other vantage point could make.

BGP never stops. Somewhere on earth a network announces or withdraws a prefix a
few thousand times a second, most of it churn from a handful of unstable origins
and occasionally something that matters, and the shape of that noise is the only
thing this panel is trying to say: **a constant hiss with structure in it.** A
quarter of an hour of it is a floor of a hundred-odd prefixes a second with
spikes an order of magnitude above it, and every spike is a real event — a
session that reset and re-sent its whole table, a network that flapped,
somebody's maintenance window.

**This is the one panel on the wall showing infrastructure its audience
operates, and that makes the honesty load-bearing.** There are already five
demos here in the green-on-black terminal register — `wardial`, `ansi`, `wopr`,
`defcon`, `sneakers` — and every one of them is a prop with invented numbers in
a hacker-movie typeface. This one deliberately borrows the same visual language
and then has to earn its way back out of it. So the prefixes in the ticker are
literal strings out of the MRT dump, the AS numbers are real and lookupable,
IPv6 is in there because the real table is half IPv6, and the awkward numbers
are left on the screen rather than smoothed off. Somebody who knows what
`2a14:67c3:ff0::/44` is can check this panel against their own looking glass and
find it correct. That is the test it is built to pass.

**Why the data is a quarter of an hour old, on purpose.** The obvious source is
RIPE's RIS Live, which streams the whole DFZ over plain HTTP as
newline-delimited JSON and would put the panel a second behind the world. It was
tried first and rejected twice over. Unfiltered it delivered **78 MB in 25
seconds**, which is not going near a Pi on shop wifi; and any affordable use of
it is *sampled* — open the socket, read twenty seconds, close it, and be blind
for the other hundred and sixty. A burst lasting a minute would simply not
appear, and a chart that silently omits the interesting parts is worse than a
coarser one that does not. RouteViews has the opposite shape: every collector
writes a complete MRT dump of every update it saw in each fifteen-minute window
and publishes it about a minute after the window closes, bzip2'd. One 1.2 MB
file buys **the entire window** — 75,000 messages, 150,000 prefixes, per-second
resolution, nothing sampled away. Trading fifteen minutes of latency for a chart
with nothing missing from it is the right trade for a panel about texture, and
the age is on the screen in any case.

Two things had to be measured rather than assumed, and both are in `ftdata.py`:
the RIS Live filters go in an `X-RIS-Subscribe` **header** and not in the query
string (the query-string forms are silently ignored — a `host=rrc11` parameter
changes nothing and you get the firehose), and `socketOptions.includeRaw` does
not work on the HTTP streaming endpoint at all, so every message carries its own
hex-encoded wire form whether you want it or not. That is roughly half the
bytes. RIPEstat was also tried and timed out twice at 25 s from this machine
while every other RIPE endpoint answered, so nothing here is built on it.

**MRT is parsed by hand, in `ftdata.py`, and that needs justifying.** The usual
answers are `libbgpstream` and `mrtparse`; the first is a C library with a
build, the second a dependency tree, and neither is going on a Pi to do
something this file already does for the Port's cruise PDF. The wire format is
RFC 6396 for the framing and RFC 4271 plus RFC 4760 for the UPDATE inside it,
and the part a churn counter needs is small: walk the record frames, find the
BGP UPDATEs, count the prefixes in the withdrawn block, the NLRI block and the
two multiprotocol attributes, and read the AS_PATH. What is deliberately *not*
implemented is everything else — communities, MED, aggregators, the two-byte-ASN
subtypes nobody has emitted this decade. An attribute the parser does not
understand is stepped over by its own length field, which is why an unknown one
cannot desynchronise the walk.

It is also where all the plausible wrong answers live, so it is the part with
the most tests. `scripts/test-bgp.py` builds MRT byte by byte and asserts
against arithmetic, because every one of these failures draws a panel that looks
completely fine:

  * **A miscounted prefix block.** NLRI is a length-in-*bits* byte followed by
    that many bits rounded up to whole octets, with the trailing zero octets
    left off the wire entirely. Get the rounding wrong and the walk
    desynchronises, the rest of the record is garbage, and the chart is just a
    different height. There are `/22` and `/25` cases in the tests for exactly
    this: a `/25` is on the wire as four octets and a `/22` as three.
  * **IPv6 silently missing.** v6 routes are not in the NLRI field at all; they
    ride inside `MP_REACH_NLRI`, which is an *optional* attribute. A parser that
    skips attributes it does not recognise — which is what a parser must do —
    drops half the real table and reports a perfectly plausible rate.
  * **The AS path read off the wrong end.** The origin is the last ASN of the
    last segment. Reading the first gives the peer, and the ticker then
    confidently prints the collector's own neighbours as the origin of
    everything on the internet.
  * **The ET record variant.** Real RouteViews files are 100% type 17, which is
    type 16 with four extra bytes of microseconds ahead of the body. Four bytes
    of offset error lands the parser in the middle of a peer address.

**The axis is square root, and it says so.** This was the one real design
problem. BGP churn is a floor around 150 prefixes a second with spikes twenty
times that, and a linear axis fitted to the spikes draws the floor — the panel's
entire subject — as one row of green along the bottom with no texture in it at
all. The first version did exactly that and was unreadable. Fitting the axis to
the floor instead clips every spike flat, and the spikes are the events. Log
would be the usual answer for a rate and cannot be used here, because a stacked
area cannot be drawn on a log axis: a zero has nowhere to go, and half the
columns have no withdrawals in them. Square root splits the difference the way
this data wants — the floor lands around a fifth of the height with its texture
intact and a twentyfold spike still reaches the top.

A non-linear axis that does not admit it is a lie, so there are **two** numbers
down the left edge instead of one: the full scale and the value at half height.
Under this transform the half-height number is a *quarter* of the full scale,
not a half, and anybody who reads both discovers the axis in about a second —
which is exactly the audience this panel has. The ladder the full scale rounds
onto has 1.5, 3 and 7 on it as well as the usual 1, 2 and 5, which is not
decoration either: a 1/2/5 ladder rounds a 2760/s peak up to 5000, and on a
square-root axis that leaves the tallest event of the quarter hour at three
quarters of the height with a quarter of the chart permanently empty above it.

**Withdrawals get their own colour and the bottom of the stack.** They are about
five per cent of prefix churn and they are far more likely than an announcement
to be somebody's outage, so folding them into one line would hide the only part
of this number that is unambiguously bad news. They are underneath rather than
on top because they are the smaller quantity and a two-pixel band floating on a
moving surface cannot be read, whereas one sitting on the floor has a straight
edge to be measured against. Their band has a **one-row minimum** wherever there
were any at all: a single withdrawn prefix in a 900-second window is four
ten-thousandths of a row, and an outage that vanishes from the chart because it
was small is precisely the failure this panel must not have.

**The ticker is a reservoir sample, and that is a real distortion worth naming.**
Its 48 lines are drawn from across the whole fifteen minutes rather than off the
front, because the front of a window is regularly one router dumping its table
and forty-eight lines of the same peer is not what the routing table looks like.
Announcements and withdrawals go into the *same* reservoir at their true
proportions, which means most windows have one or two amber lines in the loop
and some have none — that is correct, and the chart is what carries the real
ratio. What the ticker cannot show is a prefix's second announcement: only the
first prefix of each UPDATE becomes a line, so a message announcing six prefixes
contributes one. The chart counts all six.

A withdrawal line names the **peer** that sent it and says `WDR BY`, because a
withdrawal genuinely has no origin — an UPDATE that withdraws a prefix carries
no AS_PATH, there being no longer a path to describe. Inventing one from a
previous announcement would be the exact kind of plausible lie this panel exists
not to tell. AS path prepending is collapsed on the way to the screen: a path
like `[16582]×9` is one network saying one thing nine times and costs 36 pixels
of a ticker line to say nothing.

One detail worth knowing, since it looks like a bug and is not: **Monkeybrains'
own prefixes never appear on this panel.** AS32329 did not show up once in a
sampled window's 2,261 distinct ASNs, and that is the system working — a stable
route generates no churn, and the whole panel is a picture of instability.
Everything on it is, by construction, somebody having a worse day than the
makerspace's ISP.

**Frame budget.** Everything is baked in `build()`: the header, the chart, the
legend and the entire ticker are rasterised once into a static frame and one
tall strip, which is what makes the scroll two slice copies a frame rather than
a re-render. `render()` does one copy of the top of the panel, one window into
the strip, and three short writes for the pulse — five or six numpy calls, and
the cost model on the wall is calls and not pixels. Measured over a full 1200
frame (60 s) loop on the desktop this was written on: **mean 0.004 ms, p50
0.004, p95 0.004, p99 0.006**, worst frame 0.022 ms. `build()` is about 4 ms.
Even at two hundred times slower this is under a millisecond a frame against a
50 ms budget, and the only thing that could change that is the ticker strip
growing, which it cannot — it is 48 lines by construction.

`render()` is a **pure function of `t`** and is asserted to be: a cold
`render(7.3)` is byte-identical to the same moment reached by driving from zero.
The scroll and the pulse are both driven by the segment's own `t` and never by
the wall clock, which is what makes them the same animation on the wall and
under a preview baker rendering a hundred frames in a millisecond. The only
clock read is the periodic cache re-read, same as `caiso`.

**Three states.** Fresh is the panel above. A record past its 45-minute TTL
still draws — a picture of the routing table from an hour ago is still a picture
of the routing table — with `STALE` and the age in red in the header, because
the one thing this panel must never do is imply that a flat stretch is happening
now. No record at all gets a no-data card. All three are rendered in separate
processes by the test script, since `ftdata.CACHE_DIR` binds at import and
reloading the module in one process does not test what it looks like it tests.

The fetcher pulls one file every 15 minutes on the collector's own cadence,
turning 1.2 MB of bzip2 (12.5 MB of MRT, 75,000 records) into an 11 kB record.
Both ends are capped — `BGP_MAX_BZ2`, `BGP_MAX_MRT`, `BGP_MAX_RECORDS` — at
roughly five times normal, so they never fire in ordinary operation and do fire
on the day a collector emits a pathological window; a capped parse says so in
the record and its rates are computed against the span actually parsed rather
than the fifteen minutes it was supposed to be. `FT_BGP_COLLECTOR` and
`FT_BGP_SITE` move the vantage point, since every RouteViews collector publishes
the identical layout and somebody forking this wall for another city should not
have to edit code.

    $ python3 ftdata.py --once --only bgp-sfmix
    $ python3 bgp.py --host 127.0.0.1
    $ FT_DATA_CACHE=/tmp/empty python3 bgp.py      # the no-data card
    $ python3 scripts/test-bgp.py
