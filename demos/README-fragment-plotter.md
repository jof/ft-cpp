### plotter

![plotter](screenshots/plotter.png)

A pen plotter drawing. A carriage rides a rail across the top of the panel, an
arm hangs off it down onto the sheet, and a pen at the end of the arm goes
down, walks a path, comes up, flies to the start of the next one and goes down
again. The line art is not revealed — it is *drawn*, at a feed rate, by a
machine that is visibly in the way of its own work.

A plotter bed is another subject that genuinely is this shape: an X rail
spanning the full width with a sheet under it. The pen crosses the whole 320
columns, and the sheet is a 310x52 rectangle with a footer margin the artwork
never enters, which is where the print gets signed when it comes off.

The representation is **a list of paths, each a polyline in sheet
coordinates**, and the plot is one *tour* over them: travel to the start of a
path with the pen up, drop the pen, walk the polyline, lift the pen, travel to
the next. `build()` flattens that into a single array of moves —
`(x0, y0, x1, y1, kind, t0, t1)`, kind being ink, travel or a servo dwell —
carrying cumulative **times** rather than lengths, so a pen-up dwell sits in the
sequence as a first-class move instead of being special-cased. A frame is then
a lookup: `searchsorted` the current time into `t1` and everything before that
index is finished, the move at that index is in progress, and the pen is
somewhere along it. Everything else — the servo's overshoot, which travel
moves are still ghosting, whether the sheet is coming in or going out — falls
out of the same index.

Ink stays on the paper and travel does not, and that contrast is what the demo
is about. The last few travel moves are drawn as faint dashed lines that decay
over about a second and a half, so you can always see where the pen just came
from. It is also how plotter people think about a file: minimising travel is the
whole optimisation, and every piece with more than a couple of paths gets a
greedy nearest-endpoint reordering at build time — allowed to reverse a path
where that is closer — which takes the flow field's travel from 2500 px down to
500 and turns the ghosts from a cat's cradle into short hops between
neighbours.

**The interesting problem was that an ink buffer is accumulated state, and
`render` may not accumulate.** Anti-aliasing is not optional at 64 rows — a 1 px
diagonal is a staircase — so every stroke is laid into a float coverage buffer
by evaluating the exact distance to the segment over its bounding tile, and a
frame that re-rasterised the two thousand segments already on the paper would
cost a hundred times its budget. The resolution is to define the buffer as a
pure function of one integer: `ink(i)` is "every ink move with index < i,
rasterised", and then *memoise* it rather than accumulate it. The cache holds
`(i, buffer)`. When a frame asks for a larger `i` — the usual case, one to three
moves — the moves in between are added. When it asks for a smaller one, which is
what a cold start, a loop wrap or a preview baker's rewind looks like, the
buffer is restored from the nearest snapshot below it and walked forward;
snapshots are taken every 128 moves as the cache sweeps past them, so they cost
memory and no work at all. Because coverage composites with `maximum`, which is
exact, and the moves are always applied in increasing index order, "restore and
walk forward" is *bit identical* to "walk forward from zero" — which is why the
purity assertion in `scripts/test-plotter.py` compares with `array_equal` and
passes rather than nearly passing. The partially drawn current segment never
enters the buffer at all; it is stroked into a scratch copy each frame, so the
tip of the line is not quantised either.

Five pieces, from the plotter-art tradition, all generated in code:

- **hilbert** — order-4 Hilbert blocks chained across the sheet. The standard
  construction enters at a block's bottom-left cell and leaves at its
  bottom-right, so eight blocks laid side by side join with one ordinary step
  between them and the entire sheet is drawn *without the pen ever lifting*. One
  stroke, no travel, a sheet that gradually fills up rather than being filled
  in. It is the best of the five on the wall and it is the one in the shot.
- **spiro** — hypotrochoids, alternating a large pen offset (the dense woven
  disc) with a small one (an open rosette), because four of the same kind in a
  row is four green blobs. Integer parameters, so each curve provably closes.
- **lissa** — a row of Lissajous figures at rising frequency ratios, which is
  the classic plotter demo sheet and works because the ratio is legible from the
  lobe count at a glance.
- **flow** — streamlines of a smooth vector field; the piece with the most pen
  lifts and therefore the most ghosting.
- **truchet** — Smith tiles, whose quarter arcs all end at cell-edge midpoints
  shared with exactly one arc in the neighbouring cell. Walking that graph
  chains its 138 little arcs into 28 long continuous strokes, which is precisely
  the optimisation a plotter file gets before it is sent, and it takes the piece
  from 138 pen lifts to 28.

Each finishes, holds for a beat so the completed print can be seen, is signed
in the footer margin with its name and pen, and feeds out for a fresh sheet in a
new colour. The whole cycle is a hundred and eighteen seconds at the default
feed rate.

The sheet is dark and the ink glows, which is backwards from paper and right
for the wall — thin bright detail on a dark ground survives being seen at an
angle from three metres and thin dark detail on a lit ground does not.
`--paper light` is the honest white-paper version; it is lovely up close and
much weaker across the room.

Cost is measured in *strokes a frame* rather than pixels, since each stroke is
a dozen numpy calls on a tile of a few dozen pixels and the panel work is
otherwise four passes over a 52x310 sheet: 6.5 strokes a frame on average and
17 in the worst frame, which is 0.35 ms mean and 0.7 ms worst on a desktop. The
dash count on a ghost is capped rather than its length fixed, because a travel
move right across the sheet at a fixed 6 px period is thirty strokes on its
own.

Two bugs worth recording, both of which drew perfectly attractive wrong
pictures. One Truchet arc was written `linspace(pi, -pi/2)` instead of
`linspace(pi, 1.5*pi)` — the same angle, but taken the long way round through
`pi/2`, so a quarter of the arcs bulged out of their cell and off the bottom of
the sheet. It looked like a nice scaly pattern and survived several screenshots;
what caught it was asserting that no ink lands in the sheet's margins. And the
first purity check failed against `round(t*fps)/fps` rather than against `t`,
which on a demo that moves a pen two pixels a frame compares two different
moments and reports a cache bug that does not exist.

```console
$ python3 plotter.py --piece hilbert --pen amber
$ python3 plotter.py --paper light --speed 240 --line 1.4
$ python3 plotter.py --piece flow --no-ghost      # what it loses without them
$ python3 scripts/test-plotter.py
```
