### cnc

![cnc](screenshots/cnc.png)

A 3-axis mill cutting a part, seen from straight above: adaptive clearing in
trochoidal loops, drilling, a finishing raster, a contour pass round the walls,
and the shop's name engraved into the island the roughing left behind. Then the
part slides off the pallet and a fresh billet comes in.

This is the deliberate opposite of `printer`, which is additive and side-on.

Everything comes out of one array: **a height Z per panel pixel**, initialised
to the top of the stock. The endmill is a disc, and cutting is

```python
Z[disc footprint] = np.minimum(Z, tool_bottom)
```

which is not a model of milling — a min-composite of the tool swept along the
path *is* the definition of the machined surface. Nothing in the demo draws the
part. The part is whatever is left of the field.

Shading is the **gradient of Z**: a shifted difference in each axis, dotted
with a light direction, on top of a depth term. So the pocket walls, the raised
boss, the through-holes and the individual tool marks are all consequences of
the representation rather than things that had to be drawn. Two terms and their
balance is the whole look: the depth term carries most of the range, because
telling a 3.2 mm pocket floor from the top of the stock at three metres is the
one thing that has to work; the gradient term saturates at about a third of a
millimetre per pixel, so a wall pins bright on one side and dark on the other
while a few hundredths of surface roughness still reads as a tool mark.

The boss is the clearest payoff. It is never drawn and never decided — it is
simply the region the inward spiral does not reach, so it appears at exactly
the top of the stock with a wall the shape of the toolpath. Move the last inset
and it changes size; nothing else has to know.

The adaptive spiral is one traversal. A rounded rectangle is a plain rectangle
Minkowski-summed with a disc, and offsetting it inward only shrinks the disc —
the core rectangle never moves. So walking the core once, carrying an outward
normal, generates the whole family of offset curves as `core + normal * r`, and
a spiral is that walk with `r` decreasing as you go. The trochoidal loops ride
on top of it, a fixed radius rotating about the guide with the phase advanced
per sample, which is what keeps the tool engagement constant and is why modern
roughing looks like this.

The arc from chaos to discipline is one line. Roughing cuts each *loop* a few
hundredths of a millimetre off the others, so the loops stay in the floor as
scallops after the tool has gone; the finishing raster cuts 0.2 mm lower and
erases them, because a lower minimum wins. Halfway through the finish, half the
floor is smooth and half is still a field of loops — that frame is the
screenshot. The offset has to be per loop and not per sample: white noise along
the path is invisible, because the field is a minimum over a five-pixel disc
which takes the deepest of a dozen neighbours and averages it away. Measured, a
per-sample jitter of 0.075 mm left a floor with a standard deviation of 0.011
mm, three levels of brightness. Per loop it survives, because a whole loop's
worth of samples agrees.

`render` is a pure function of `t`, which for a demo that accumulates a height
field takes some care. The whole toolpath — position, tool-bottom Z, feed rate
and operation per sample, plus the cumulative time at each — is generated once
in `build()` from the seed. `render(t)` looks up where the tool is and advances
a cursor, stamping whatever samples it crossed. Because Z only ever decreases
and stamping a sample twice is a no-op, replaying the program from zero gives a
bit-identical field, so a cold `render(t0)` and the same `t0` reached frame by
frame agree exactly, and 8 fps and 30 fps agree exactly. Chips are ballistic
from their birth sample rather than integrated, for the same reason.

A frame is two whole-panel operations — the table copy and the stock blit — and
then only the bounding box the tool actually touched is re-shaded, a couple of
hundred pixels. Desktop mean is 0.10 ms, p95 0.12, max 0.17 over a full cycle.
The one hitch worth knowing about is a cold call at a large `t`, which replays
the whole program in one go: 13 ms on a desktop at the very end of the cycle.
The scheduler starts segments at `t=0`, where the replay is empty, so this
never happens in practice.

The cycle is about 66 seconds and wants 20 fps.

```console
$ python3 cnc.py --speed 1.6 --text 'MADE HERE'
$ python3 cnc.py --stepover 1.0 --trochoid 3.2      # more laps, bigger loops
$ python3 scripts/test-cnc.py --dump /tmp/cnc
```
