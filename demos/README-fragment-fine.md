### fine

![fine](screenshots/fine.png)

A dog in a hat sits at a small table with a cup of coffee while the room fills
with fire. It blinks. Three times a cycle it lifts the cup, drinks, and puts it
back down. Around it the flame walks from one corner of the room to the whole
of it, the shelf and the picture blacken, the ceiling fills with smoke, and the
hat gets a little singed. Then the line lands, once, and holds.

The whole joke is the calm, so the demo's one hard rule is that the dog does
not react. `scripts/test-fine.py` asserts it in pixels: over nine hundred
frames the dog's own pixels change at most eight times, and every one of those
is the room's baked lighting stepping or the hat catching. The eyes are the
only thing that moves, and they only ever shut.

Everything is drawn in code from a description — the dog, the hat, the table
and the cup are character grids with a palette, as in `mario.py` and
`nyancat.py`, and the room is rectangles. Nothing is traced or downloaded.

**The fire is the interesting part.** The classic effect in `fire.py` is
inherently stateful: each frame takes the heat buffer the previous one left,
shifts it up a row and cools it. That cannot be a pure function of `t`, and on
this wall it has to be — the scheduler builds segments ahead on a worker thread
and starts them at `t=0`, and the preview baker steps at its own rate. Rerunning
sixty simulation steps from a fixed seed every frame would restore purity and
cost sixty whole-panel passes, which is not affordable on a Pi.

So the flame here is a field rather than a simulation:

```
heat(y, x, t) = clip(fuel(x, stage) * turbulence(x, y + scroll(t)) - height(y))
```

`turbulence` is one noise texture baked in `build()` — a low-resolution random
field, upsampled, blurred with wrapping rolls, and leaned by a shift that is
*itself* periodic in the tile height. That last detail is the one that took a
second attempt: the obvious lean is a linear shear, roll row `y` by `y/6`
columns, and over a 264 row tile that totals 44 columns, so at the wrap the
shift snaps back to zero and a 44 pixel step walks up the panel once per loop,
looking exactly like a torn scanline. A sinusoidal shift wraps for free, and a
wandering lean is closer to what a draught does to flame than a constant one.

Because the texture wraps top to bottom, scrolling it is a slice of a doubled
copy at `int(t * scroll) % tile_h` — no modulo arithmetic, no copy, no state.
`fuel(x, stage)` is a baked per-column profile and is what walks the fire from
the far corner to the whole room; `height(y)` is distance above the floor line,
so subtracting it is what gives each column a flame that runs out somewhere.
Six whole-panel numpy calls, pure in `t`, and it reads as fire because the
palette carries it.

The room's light is baked the same way. `build()` paints the room twice, clean
and charred, and renders `--stages` fully lit frames interpolating between them,
each with its own orange bounce and its own ceiling smoke. A frame picks one by
index, so the entire background — including the furniture blackening and the
room going dark around the fire — costs one `np.maximum` against the flame. The
dog and the cup are lit from that same field sampled at the rows they occupy,
which is what puts them *in* the light instead of on top of it.

The punchline is the repo's 3x5 font at scale 3, with a one-pixel dark outline
in every direction — on a panel that is by then entirely orange, white type
without one is unreadable. Its box is measured from the mask that is actually
drawn rather than assumed from the scale, and the test asserts every glyph
pixel including the bottom row is lit, which is the check that would have caught
the bug that once clipped the base off every capital `E` on this wall.

Timing is the joke, so the line lands at 76% of the cycle: long enough after
the room has gone that you have had time to notice the dog is not going to do
anything about it. The last second and a half is a fast collapse back to a
clean room, because a room slowly un-burning is the one shot in the loop that
cannot be sold.

0.19 ms mean a frame on a desktop (p95 0.22, max 0.24), about 45 numpy calls
of which nine touch the whole panel. 46 second cycle at 20 fps.

```console
$ python3 fine.py --cycle 30 --scroll 26
$ python3 fine.py --no-text --stages 40      # just the room, smoother light
$ python3 scripts/test-fine.py
```

**The line is dialogue, so it is drawn as dialogue.** The first cut set the
punchline as centred white type across the top of the panel with a one-pixel
halo around every glyph, and it read as a caption laid over the scene -- the
wall announcing the joke rather than the dog saying it. It is now a speech
bubble: dark ink on a light rounded ground, with a tail that points at him.
That also fixes the legibility problem more honestly than the halo did. By the
time the line appears the room is entirely orange, and white type on orange
needed an outline traced around every letter to survive; a light bubble gives
the type its own ground, so the contrast comes from an object in the scene
rather than from a per-glyph trick.

The bubble is sized from the measured glyph mask rather than a fixed box, so
`--text` and `--text-scale` grow it instead of overrunning it. Placement aims
the *tail's tip* rather than the box, which is what puts the bubble over his
shoulder; and when the text is large enough that the bubble will not fit above
his head, it moves alongside him instead, because the one thing it must never
do is overlap the dog. `bubble_layout()` is module scope so the test checks the
drawn bubble against the same geometry the demo draws from -- the banner's
placement formula had been copied into the test, which is the arrangement that
lets a demo and its test drift apart while both stay green.
