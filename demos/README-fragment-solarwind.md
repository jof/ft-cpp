### solarwind

![solarwind](screenshots/solarwind.png)

The Sun on the left, the Earth's magnetosphere on the right, and the hour of
solar wind that is in flight between them drawn in the middle — with the
interplanetary field it is carrying, and what that field is doing to the Earth
when it arrives. Three small numbers: wind speed, Bz with its sign, Kp.
Everything else on the panel is a picture.

`propagation.py` already reads these same NOAA numbers and lays them out as an
instrument panel for a ham choosing a band. This is deliberately not that. The
numbers cannot say *where* the plasma is, which way the field in it points, or
that the thing about to make Kp bad is already halfway here — and those are
exactly the things a 320x64 letterbox is the right shape to show.

**The one representation choice, from which everything else falls out: x is
distance, and distance is also time.** SWPC publishes
`products/geospace/propagated-solar-wind-1-hour.json` — one row a minute for
the last hour, measured at L1, each carrying a `propagated_time_tag` saying
when that plasma reaches the bow shock. At ordinary wind speeds the trip takes
about fifty minutes and the file holds sixty, so the file is, near enough, an
inventory of the plasma currently between the spacecraft and us. Draw the
oldest row on the right and the newest on the left and the result is not a
chart with a time axis pretending to be a picture; it is a picture, with the
plasma in the right places. The stream flows rightward because the plasma does.
A southward patch of field sits at the x where that patch actually is. And the
magnetosphere is squeezed by the *rightmost* sample — the one arriving now —
not by the headline figure at the left, which will not get here for another
three quarters of an hour.

**Scale, honestly.** The corridor covers one hour of travel, about 0.01 AU. The
other 99% of the way to the Sun is simply not drawn: the limb at the left edge
is an emblem of where the wind came from, and at true scale the Sun would be a
hundred panels further left and the Earth would be one pixel. Inside the
magnetosphere the scale is real and consistent — 1.55 panel pixels per Earth
radius — with only the planet itself drawn about four times oversized, because
otherwise an aurora is half a pixel. So the compression is a true compression
even though the corridor is not to scale, and that is the trade the panel
makes.

**The magnetopause is the Shue model, not a doodle.** Shue et al. (1997) fit
the standoff distance and the flaring of the boundary to two inputs, Bz and the
dynamic pressure `1.6726e-6 n v²`:

    r0    = (10.22 + 1.29 tanh(0.184 (Bz + 8.14))) · Dp^(-1/6.6)
    alpha = (0.58 - 0.007 Bz) (1 + 0.024 ln Dp)
    r(θ)  = r0 (2 / (1 + cos θ))^alpha

A quiet day puts the nose at about 10.9 Earth radii; 22 protons per cc at 800
km/s with Bz at -18 puts it at 5.6, and the cavity on the panel visibly caves
in. The bow shock is drawn at 1.3 r0, which is a rule of thumb rather than a
model, and the magnetosheath between the two is the brightest plasma on the
panel because that is where shocked plasma piles up. When the nose has come in
by more than a couple of radii, a dotted ghost of the quiet-day boundary stays
behind, so that the compression reads in a single frame instead of needing
somebody to remember yesterday.

**Why the field is a comb and not field lines.** The first version integrated
honest field lines across the panel, and they were beautiful for eighty columns
and then left through the floor — which is not a bug, it is what a sustained
southward Bz *means*. So the field is drawn the way a wind field is drawn on a
chart: short dashes on a staggered grid, each tilted by the local clock angle.
A uniform field lines them up into what reads as continuous lines; a rotation
passing through visibly turns the comb over. Colour is binary and carries the
message — cool blue for northward, hot magenta for southward — and brightness
within each band is |Bz|/|B|, so a field that is strongly one way shouts and a
flat one recedes. The staggering matters: aligned, the dashes read as diagonal
hatching over the whole panel and fight the stream underneath them.

**The chain the panel exists to teach.** When the field arriving at the nose is
southward, reconnection knots appear at the subsolar magnetopause and slide
back along both flanks, the tail's X-line flashes a beat later, and the poles
light up. When it is northward, none of that happens and the aurora is a dim
smudge. Southward Bz → coupling → aurora is the one idea here, and it is drawn
as a cause and an effect rather than written down.

**What it costs.** The whole panel is a uint8 *index* image through a single
256-entry palette cut into bands — plasma 0..63, north field 64..95, south
field 96..127, shock, aurora, sun, sparks, cavity, type — so every layer
composites in integers and colour happens exactly once, in one `np.take`. The
streaming plasma is a seeded streak texture baked in `build()`, made periodic
in the panel width and stored twice side by side, so scrolling it is a *slice*:
no roll, no take, no cost. Everything static is baked into one overlay and
stamped in with a single `np.copyto(where=)`. That leaves five whole-panel
numpy calls a frame plus a dozen writes of a handful of pixels for the sparks
and the poles: 0.06 ms a frame on a desktop, and on the wall's Pi 3 it is the
cheapest data panel here after `propagation`. Greying out a stale panel is done
to the palette in `build()`, so `render()` never learns that anything changed.

**Fresh, stale, absent.** The age is in the bottom-right corner always. Past
the TTL the whole palette desaturates and the age turns amber; past three TTLs
it greys out hard and the numbers become `--`, because a confident picture of
an hour of solar wind that is in fact six hours old is worse than no picture.
With no record at all it draws a no-data card naming the fetcher. And anything
drawn from `--storm` or an override says `SIM` where the age goes, because a
synthetic severe storm labelled "0s" is a panel claiming a G4 is happening
right now.

Data: `swpc_l1_wind` in `ftdata.py` — the propagated L1 wind (6.6 kB of JSON
trimmed to about 1.9 kB of four parallel arrays) plus the Ovation hemispheric
power in gigawatts from `text/aurora-nowcast-hemi-power.txt`. TTL an hour,
fetched every ten minutes. Kp is read from the existing `swpc_kp` product
rather than fetched again, so this panel and `propagation` can never disagree
about whether there is a storm.

```console
$ python3 ftdata.py --once --only swpc_l1_wind    # the fetcher
$ python3 solarwind.py --host ft.local
$ python3 solarwind.py --storm                    # a G4, which is rare
$ python3 solarwind.py --bz -18 --speed 750 --kp 7
$ FT_DATA_CACHE=/tmp/empty python3 solarwind.py   # the no-data card
$ python3 scripts/test-solarwind.py               # 51 checks, incl. the Shue fit
```
