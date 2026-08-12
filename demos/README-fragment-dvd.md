### dvd

![dvd](screenshots/dvd.png)

The bouncing screensaver logo, and the wait for it to land exactly in a corner.
Everyone knows the ritual: the logo drifts, changes colour on every bounce, and
the room waits. That wait is the whole demo, so the panel keeps score — corner
hits since local midnight, and how long since the last one, in burn-in grey
along the bottom.

**The wordmark is ours, not the DVD Video mark.** "FT" in a sheared 3px slab
over an ellipse reading TASCHEN, drawn in the file as a character grid and a
conic. The joke lives in the silhouette and the behaviour, and it is funnier
being ours.

**The corner period is chosen, not discovered.** Free travel is `Sx = W - logo
width` and `Sy = H - logo height`, and ideal billiard reflection makes each
axis a triangle wave, so the position is closed form: `x(t) = fold(vx·t, Sx)`
with `fold(u,S) = |((u+S) mod 2S) − S|`. x is against a wall whenever `vx·t` is
a whole multiple of `Sx`, y whenever `vy·t` is a whole multiple of `Sy`, and a
corner is both at once. Rather than pick a velocity and go hunting for corners,
pick the corner period `T` and two **coprime** integers — `q` traverses of the
long axis and `p` of the short one in that period — and read the velocities
off: `vx = Sx·q/T`, `vy = Sy·p/T`. Coprimality is what makes the two
wall-contact sets meet only at multiples of `T`, so a hit is exactly every `T`
and never a second early. That single choice is the demo.

**What T should be is the real design decision.** `T = 180 s, q = 31, p = 83`
(both prime, so coprime by inspection) gives 47.7 and 16.1 px/s, a 19-degree
drift, a bounce off the top or bottom every 2.2 seconds and a full traverse of
the long axis every 5.8. A rotation slot is 30–45 s, so roughly one slot in
five contains a hit: rare enough that catching one is an event, common enough
that standing and watching pays off within three minutes. Twenty seconds would
kill the joke; twenty minutes would make the panel a dud that nobody ever sees
pay off. Both `p` and `q` are odd, which makes successive hits alternate
between diagonally opposite corners. The near misses — closest is 1.1 px — are
frequent and are the point.

**It is driven by the wall clock**, anchored to an absolute epoch captured in
`build()` rather than to the segment's `t = 0`. With segment time the panel
would replay the same three minutes on every appearance: either every slot has
a hit at the same second or no slot ever does, and both are fatal. Anchored to
the clock, the logo is where it would be if the screensaver had genuinely been
running since before you walked up, the counter is real, and walking past twice
shows two different states. `--epoch` pins it for tests and screenshots.
`render()` is still a pure function of `t` for any one `build()`.

**Two things went wrong and are worth recording.** The ellipse was 9 rows tall
first, and at ±2 rows off centre it has already pinched in to less than TASCHEN
needs, so the ring ate the outer letters and the logo read IASCHEI; the fit is
now asserted at build with a one-pixel clearance, and it fails loudly rather
than shaving the type. And the counter first computed midnight against the
segment's own epoch instead of the trajectory clock, which put nine million
corners on the panel — plausible-looking, wrong by a constant, and invisible in
a thumbnail, so the count is now read back off the pixels in the test.

A frame is a copy of black, three small masked blits (two of them dim,
scanline-combed phosphor ghosts that follow the same closed form and so bend
round a bounce by themselves) and two short strings: 0.03 ms on a desktop, and
the only whole-panel arithmetic is the shockwave ring, which runs for 1.6 s in
every 180.

```console
$ python3 dvd.py --corner-period 60           # impatient
$ python3 dvd.py --sweeps 17 --bounces 44     # a different billiard
$ python3 scripts/test-dvd.py --bench
```
