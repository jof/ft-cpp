### pipes

![pipes](screenshots/pipes.png)

The Windows 3D Pipes screensaver. Pipes grow through an invisible lattice,
turning at right angles, joined by a gleaming ball at every elbow; when the
volume is full enough the panel holds for a beat, an eraser bar sweeps it black,
and a new run starts in a new colour scheme. The wall already has the bouncing
logo (`dvd`) and the flying toasters (`toasters`); this is the third pillar of
the genre and the only one of the three with *depth*.

The representation is **a self-avoiding walk on an integer lattice, flattened
into a list of primitives with timestamps**. The head sits in a cell, picks a
direction, runs a few cells, turns ninety degrees, repeats, and never revisits
an occupied cell; a pipe that paints itself into a corner dies and another is
born somewhere else, which is the original's behaviour and most of its
character. That leaves exactly two things to draw — a straight *run* between two
lattice nodes and a *joint* ball at each turn — and everything else is
bookkeeping. `build()` walks the whole lattice for each of the three schemes up
front and emits `(kind, p0, p1, colour, t0, t1)` in view-space coordinates,
sorted by finish time; `render(t)` only reveals more of a list that already
exists. That is what makes it a pure function of `t`, and it is also why the
walk can be *guaranteed* to fill the panel nicely rather than hoped to.

**There is no mesh and no triangle anywhere.** A run is rasterised as a
screen-space capsule: over the segment's bounding tile, `perp` is the signed
perpendicular distance to the projected axis and `u = perp / radius` runs −1..1
across the tube. Everything falls out of `u` alone — `w = sqrt(1 − u²)` is the
component facing the viewer, the depth is the axis depth minus `w·R`, and the
surface normal is `u·p + w·v` for the segment's screen perpendicular `p` and the
view direction `v`. A ball is the same idea in two dimensions. That is what
makes the chrome affordable: both the Lambert term and the tight specular are a
function of `u` and of the *angle the segment makes on screen* and nothing else,
so both are baked in `build()` into a table indexed by `[colour][angle
bin][u bin]`, and a frame does one `np.take` where it would otherwise do a dozen
vector operations per pixel. The highlight running down the length of a tube —
the whole reason chrome reads as chrome — costs one lookup. Balls get a 2D table
of the same kind indexed by `(nx, ny)`, plus a matching table of the bulge
towards the viewer that doubles as the coverage mask.

Occlusion is the point, so there is a real **z-buffer**: a float depth per panel
pixel, tested per fragment. Pipes crossing in front of one another is most of
what makes a flat panel read as a volume, and no amount of shading substitutes
for it. `scripts/test-pipes.py` asserts it the only way that means anything:
draw the same finished lattice with the primitives shuffled and require
essentially the same pixels back. A z-buffered scene is order independent; a
painter's-algorithm scene is not, and it is otherwise a bug that produces a
perfectly attractive picture.

**Perspective, not isometric, and for a specific reason.** Isometric is cheaper
and was tried first. It fails here because every tube is the same width at every
depth, so two tubes crossing are distinguished *only* by which occludes the
other, and at 64 rows that is a one-pixel cue. A mild perspective — the far
plane one and a half times the distance of the near one — makes near tubes
visibly fatter (6.2 px against 4.1) and, with a little depth fog, brighter. That
is a second and a third depth cue that survive being seen at an angle from three
metres, and the frustum costs one divide per lattice node at build time. The
camera is also yawed 15° and pitched 9°, because with the lattice axes exactly
on the screen axes the whole thing reads as a flat maze.

The lattice is 20 × 4 × 9 cells, which is deliberately not a cube: the panel is
a 5:1 letterbox and a wide, shallow, *short* volume fills it. The focal length
and screen centre are **solved** in `build()` by projecting all 720 nodes rather
than hardcoded, then over-scanned 14% so the near layer runs off the edges the
way it does in the original — which also means changing an angle cannot silently
push half the volume off the panel.

**The interesting problem was that cost scales with how much pipe is on screen,
and `render` may not accumulate.** A frame must not redraw the couple of hundred
primitives already there, but a persistent frame buffer is accumulated state.
The resolution is the one `plotter` uses: the buffer is a pure function of one
integer. `world(i)` is "every primitive with index < i, rasterised into colour
and depth", *memoised* rather than accumulated; a frame asking for a larger `i`
draws the difference, and one asking for a smaller — a cold start, a loop wrap,
a preview baker's rewind — restores from the nearest snapshot below it and walks
forward. Snapshots are taken every 32 primitives as the cache sweeps past them,
so they cost memory (about 140 kB each, five per run) and no work. Because the
z-test is a strict `<` and primitives are always applied in increasing index
order, restore-and-walk-forward is *bit identical* to walk-from-zero, which is
why the purity assertion compares with `array_equal` and passes rather than
nearly passing. The growing tips never enter the buffer at all: they are drawn
into a scratch copy each frame, so a pipe advances smoothly instead of a cell at
a time.

So a frame is two panel copies plus one capsule per growing tip, flat from the
first frame of a run to the last: **0.14 ms mean, 0.22 p95, 0.54 max** on a
desktop, and close to linear in `--pipes` (1 → 0.06, 2 → 0.12, 3 → 0.17, 4 →
0.20 ms while growing). `--pipes` is the knob if the wall wants it cheaper, but
it is also a pacing knob — two pipes take half again as long to fill the same
lattice, so `--pipes 2 --fill 0.22` is the pairing that keeps the cycle the same
length.

**The teapot is in.** The original famously spawns a chrome Utah teapot instead
of an elbow once in a while, and it is the best easter egg available — but a
sprite of one cannot be scaled to whatever depth it lands at without falling
apart, and a fixed-size sprite in a scene with perspective reads as a decal. So
the teapot is *modelled*, in the only two shapes this renderer knows: a fat ball
for the body, a small one for the knob, a squat capsule for the lid, a tapered
one for the spout and a four-piece loop for the handle. Eight draws, in the
pipe's own colour, into the same z-buffer, and it shrinks with distance for
free. It lands about 31 × 20 px against a 6 px tube. Honestly: at three metres it
reads as *something that is not a pipe*, and it resolves into a teapot when you
look at it — which is roughly the right amount of easter egg. It is placed in
the second half of the sequence and the nearer half of the volume, because a
teapot drawn early and far is a teapot buried behind forty pipes; even so, one
run in three puts it somewhere it is half hidden, and that is the walk's luck
rather than a bug. `--teapot 0` turns it off.

Two things worth recording. The live growing tips were first found by scanning a
small window forward from the finished index, which looks safe and is not: the
list is ordered by *finish* time, so a pipe part way through a six-cell run can
sit sixteen entries behind three other pipes turning every cell, and it stalls
for a second at a time. It is now a vectorised test over the whole list — six
numpy calls on a 170-element array, which is nothing — and the test asserts that
the window would have been too small. And the eraser first reached the right
edge exactly at the end of the cycle, so the panel cut from a half-erased frame
straight into the next run; the bar now clears four fifths of the way through
the wipe, leaving a third of a second of black, and that beat is what makes the
clear read as a decision rather than a dropped frame.

Roughly 35 s per cycle at the defaults — 30 s of growth, 3.5 s held, 1.6 s of
wipe — so one rotation slot is about one complete run. 20 fps.

```console
$ python3 pipes.py --scheme enamel --pipes 2 --fill 0.22
$ python3 pipes.py --fill 0.5 --speed 4          # spaghetti, quickly
$ python3 pipes.py --yaw 0 --pitch 0             # why the camera is turned
$ python3 scripts/test-pipes.py --bench
```
