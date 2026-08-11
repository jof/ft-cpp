### helicorder

![helicorder](screenshots/helicorder.png)

Six hours of raw ground motion from a seismometer ten miles away, drawn as a
drum recorder. Six traces, an hour each, oldest at the top, newest at the
bottom, the pen at the leading edge of the data.

`quake` is the other end of this pipeline and the two are deliberately a pair.
That panel shows earthquakes *after* somebody's algorithm has decided they were
earthquakes: located, magnitudes assigned, plotted as discs on a map. This one
shows the measurement all of that is derived from — one station, one channel,
the ground going up and down — before anything has been decided about it. The
drum is one of the most recognisable scientific images there is, and it happens
to fit a 5:1 letterbox exactly.

**The quiet is the data.** Most of the time this panel is six ragged flat
lines, and the raggedness is not instrument noise: it is the microseism, the
whole Pacific coast ringing at five to eight seconds from swell hitting the
continental shelf. It gets louder when there is weather offshore, and you can
watch that happen over a few days. Nothing on this panel is more important than
the fact that a normal afternoon looks like a normal afternoon, because
everything the panel is for depends on the eye knowing what normal is.

**The clipping is deliberate.** The vertical scale is fixed against the
*background* — one trace lane is 2.5 times the background's own peak-to-peak,
so a quiet hour fills about two fifths of its lane — and an event that will not
fit is allowed to run out of its lane and scribble over its neighbours, in a
warmer colour so it is obvious whose ink it is. That is what the paper ones do
and what the framed ones in every seismology department look like. Rescaling to
fit would be worse in both directions: it would flatten the background to a
hairline on the rare days it mattered, and it would draw an M5 and an M2 at the
same size with a different number on the axis. The overrun is capped at one and
a half lanes, which is reached often — the M5.6 in the screenshot is five
hundred times the background, or two hundred and sixty lanes of trace asking
for twenty rows of panel — so the cap is doing real work and one local
earthquake still cannot black out the whole picture.

The screenshot is a real six hours: 04:00 to 09:20 Pacific on 24 June 2026,
ending seventy minutes after the M5.6 near Redwood Valley, 190 km north. The
lane it lands in saturates for the rest of that hour, which is the coda and the
aftershock sequence and not a drawing fault — the columns after the burst sit
at two to four times the background for another fifty minutes. It was captured
by pinning `FT_HELICORDER_END=2026-06-24T16:20:00` (UTC), which is the
fetcher's one testing lever and is unset on the wall.

**Where the numbers come from.** BK.BRK, Byerly Vault, an STS-2 broadband
seismometer under the UC Berkeley campus, 37.8735 N 122.2610 W — 17 km
north-east of this building, close enough that anything the room would feel is
emphatic on the trace, and a real instrument somebody could go and look at.
BHZ is its 40 samples-a-second vertical channel. Berkeley runs its own network
and NCEDC serves it over FDSN, keyless and with no signup:
`service.ncedc.org/fdsnws/dataselect/1/query?net=BK&sta=BRK&cha=BHZ&...`. The
data is about a second behind real time, which is startling the first time you
notice it. BK.BRIB (Briones) and BK.BKS answer the same query shape if this
vault ever goes off the air.

**The one real cost was the compression.** NCEDC hands out miniSEED with Steim2
compression and there is no ASCII option for this network — EarthScope's
`irisws/timeseries` will serve ASCII but does not archive BK, only the global
networks, and a panel captioned "the ground near you" showing a station in New
Mexico would be a lie told to avoid writing a decoder. So `ftdata.py` has a
Steim2 decoder in it, about a hundred lines: 64-byte frames of sixteen
big-endian words, word 0 a map of two bits per following word saying how many
differences that word holds, and the samples are the running sum of those
differences with the first sample carried separately.

Two things about it are worth writing down. The first is that **the
differences are packed right-aligned against bit 0**, and the obvious thing to
write — shift down from bit 31 — decodes every record into a plausible-looking
wiggle of entirely invented numbers, because for the two- and three-nibble
cases the top two bits are a sub-type field and the differences live in what is
left. Seven 4-bit differences occupy bits 0–27 and bits 28–29 are simply
unused. The second is that **the format carries the answer**: each record
stores its own last sample redundantly in the header frame, the reverse
integration constant, for no other reason than to let a decoder prove it walked
the differences correctly. It is asserted on every record and a mismatch
raises, so a subtly wrong decoder cannot quietly become six hours of fiction.
`scripts/test-helicorder.py` round-trips the decoder against a Steim2 *encoder*
written for the test, over a series chosen so that all seven packings are
exercised, and separately checks that corrupting that constant is refused.

The decoder is vectorised rather than looped because it runs on the wall's own
Pi: six hours is 864,000 samples, and a per-sample Python loop is a minute
there against about eighty milliseconds like this.

**What is stored is an envelope, not a waveform.** Six hours of BHZ is 1.7 MB
of miniSEED and what the panel can draw is 1800 columns one pixel wide, so each
12 seconds is reduced to its minimum and its maximum — which is exactly what a
pen does, and is the one decimation that does not lie about amplitude. A mean
would flatten every burst and a subsample would hit or miss one at random. That
is 3600 numbers, about 23 kB of JSON, and it is the whole six hours at the
finest resolution the panel has.

**It tops up rather than refetching.** The columns are anchored to absolute
12-second bins, so a fetch five minutes after the last one asks NCEDC for five
minutes — 23 kB — and slides the stored columns along by the number of bins the
window moved. A cold start, or a gap longer than the window, fetches the whole
six hours once. Refetching six hours every five minutes would be 20 MB an hour
off the shop wifi to receive the same 1.7 MB seventy times over; this is 280 kB
an hour. The fetch function takes `cache_dir` for this reason and is flagged as
a blob product to get it, which is the only hook `fetch()` has for "this
fetcher needs to read its own last record". It writes no sidecar.

The baseline is removed before storing. A broadband vault wanders a couple of
thousand counts over six hours with the temperature and the tide, which at this
scale is half a lane of slow drift that has nothing to do with anything, so a
two-minute box smoothing of the column midpoints is subtracted. That is the
modern version of the pen's zero adjustment, and nothing a local earthquake
does is slower than two minutes.

**The events are borrowed, not refetched.** `quake-usgs` is already in the
cache with a week of located events in it, so any event that falls inside the
window is marked on the trace — a dark bar under the ink with a bright cap
above and below the lane — and the largest one gets its magnitude and place in
the header. Two details make the marks honest rather than decorative. They are
slid from origin time by the P-wave travel time at 6.1 km/s, so the mark lands
where the ground here started moving rather than where the earthquake started,
which at 200 km is thirty seconds and a couple of columns. And an event is only
marked if its magnitude clears **two plus a hundredth per kilometre** of
distance: the catalogue is complete to about M1 around here and a quiet week
holds a couple of hundred events inside 300 km, nearly all far too small to
have reached this vault. An M2.5 at Willits is 190 km of rock away and is not
on this trace at any scale; marking it would be the panel claiming something
the picture does not show, which is the one thing a raw-data panel must not do.
That record belongs to `quake` and is never written here; if it is missing the
marks go and nothing else does.

**The vertical scale is stated in real units.** The instrument response comes
out of NCEDC's station service — 2.53×10⁹ counts per metre per second for this
vault, and it has changed eight times since 1996, so the epoch covering the
data is the one used — and the axis strip says what one full lane is worth in
microns per second peak to peak. Around 2.5 µm/s on a quiet day. A wiggle
nobody can put a number on is decoration.

**The three states.** Fresh draws normally with the fetch age in the corner.
Past the 1800 s TTL the corner says `STALE` in red and the drum keeps drawing,
because six hours of ground motion does not stop being six hours of ground
motion and every lane is labelled with the hour it belongs to. A gap inside the
window — the station down, the request truncated — is drawn as a red dash on
that lane's zero line rather than as a flat trace, which would be the panel
claiming the ground was still when in fact nobody was listening. The pen sits
at the end of the *data*, so if the fetcher stopped an hour ago the last lane
stops an hour short and the gap is visible. No record at all, a corrupt one or
one with no samples in it gets a clean `NO SEISMOGRAM` card.

**Motion.** The drum draws itself in reading order when the segment starts,
line by line, at about six hours in two and a half seconds, with the pen at the
writing point. It is the one animation this subject actually asks for, and it
is the reason `build()` bakes seven frames instead of two: a line's ink can
overrun into the line *below*, which has not been written yet, so the
half-drawn drum is not something the finished picture can be masked back into.
`stack[i]` is the paper with lines 0..i on it, `render()` takes everything left
of the pen from `stack[lane]` and everything right of it from `stack[lane-1]`,
and cutting the picture at the pen's column rather than at the lane's rows is
what makes the overrun appear exactly when the pen reaches it. Two whole-frame
slices, no mask. Afterwards a slow sheen crosses the paper and the pen
breathes; both are functions of the segment's own `t`, so the preview baker and
the wall see the same animation.

**Frame budget.** Everything is baked. `render()` is one frame copy plus either
two slice assignments (revealing) or a multiply-and-add over a 40-column window
(the sheen), plus two short column writes for the pen — six or seven numpy
calls, and numpy costs tens of microseconds a call on the wall whatever the
array size, so the call count is the budget and not the pixel count. Measured
over fourteen hundred frames here: **mean 0.021 ms, p50 0.023, p95 0.031, p99
0.036**, worst frame 0.083 ms; the reveal is cheaper than the steady state at
0.005 ms mean. `build()` is 3–5 ms, once, on the scheduler's worker thread. The
fetcher's cold pass is 1.7 MB and about a second of network plus 80 ms of
decode here, which is the only part of this that will be noticeably slower on
the Pi — and it happens once, in another process.

Run:

    python3 ftdata.py --once --only helicorder-bk
    python3 helicorder.py --host 127.0.0.1
    python3 helicorder.py --gain 1.5          # a louder trace
    FT_DATA_CACHE=/tmp/empty python3 helicorder.py     # the no-data card
    python3 scripts/test-helicorder.py
