### dither

![dither](screenshots/dither.png)

One photograph, quantised five ways, with the boundary sliding across it. An
LED matrix *is* a dithering device — every picture on this wall is a
quantisation of something continuous — so this panel is the wall showing its
own working. A satellite frame is on screen, a wipe travels across it, and on
either side of the wipe the same image is rendered by a different quantiser:
continuous tone, then **Floyd–Steinberg**, then **Atkinson**, then **ordered
Bayer 8x8**, then a hard **threshold**, each named in the strip at the top of
its own half. The ladder is monotone in how much of the quantisation error a
method bothers to account for, which is the argument the panel is making.
Floyd–Steinberg pushes all of it into the pixels it has not visited yet and
reproduces the picture's mean brightness exactly. Atkinson — out of the 1984
Macintosh — pushes six eighths and throws a quarter away, which crushes the
darkest and lightest few percent and in exchange gives that bright, open
MacPaint look. Bayer does not diffuse at all, and its fixed threshold matrix
weaves a crosshatch that is the same everywhere. Threshold accounts for
nothing, and the gradients go to slabs.

The picture comes from `goes-psw`, the same cached GOES-18 GeoColor window
`goes.py` plays as a time lapse, which `ftdata.py` has already cropped to
exactly 320x64 — so there is nothing to resample and no second product to
fetch. Weather from orbit turns out to be close to an ideal dithering subject:
huge smooth gradients of ocean, haze and valley with hard bright cloud on top
of them. One frame out of the seventy-odd is picked and held. The wipe is the
motion here; a time lapse underneath it would be a second idea on a panel that
is allowed one.

**The one representation choice is that every state of the panel is a whole
baked frame.** Error diffusion is strictly sequential — each pixel's decision
depends on the residue left by the one before it — so there is no vectorised
form and no way to do it per frame; a Python loop over 20480 pixels is tens of
milliseconds on a laptop and the better part of a second on the wall's Pi.
So `build()` runs each quantiser once and produces ten finished 320x64 uint8
panels, dot pattern and captions and ladder ticks and all, and `render(t)`
copies the left part of one and the right part of another and writes a single
bright column between them. Three numpy calls a frame, no arithmetic, no
allocation, and a demo that is trivially a pure function of `t` because there
is nothing left in it to have state. The performance design and the purity
requirement turned out to be the same design.

That baking is also why the labels work. Each panel carries its own algorithm's
name at *both* ends, which looks redundant on a panel showing one algorithm and
is exactly what makes the wipe read: composited as the left half, a panel's
right-hand name is hidden under its neighbour's and vice versa, so during a
crossing the incoming name is at the left and the outgoing name at the right,
and when the crossing finishes the label simply stays where it is. No
typesetting per frame, and no pop when a wipe ends. The ladder ticks along the
bottom are baked the same way, so the marker walks across with the boundary.

**Two things had to be found by looking rather than reasoned about.** The first
was tone: the obvious pick for "best frame in the window" is the one with the
most contrast, and the highest-contrast GOES frame is bimodal — black ocean
under white cloud — which quantises to a silhouette that all four methods
render identically. What shows a dither off is *midtone*, so both the frame and
the punch-in window are chosen on how much of them lands in the middle of the
range, and a gamma of 1.25 pulls a bright daylight frame back off the white
clip. The second was that Atkinson and Bayer look the same at 1:1 on a subject
this busy, which is why there is a second act: the panel steps into an 80x16
detail of itself at 2x and then 4x — integer magnifications of the *dithered
output*, so what is on screen is the real dot pattern with each dot four LEDs
across — and runs the wipe again between the two, where Bayer's regular weave
and Atkinson's clumpy organic dots are unmistakable. It steps into the
threshold panel first, which at 4x is a blank white slab, which is the joke.

Everything is one warm ink on black. Dithering to a small colour palette on
half the panel was tempting and is a second idea; what makes these algorithms
legible from three metres is black-and-white dot texture, and the
continuous-tone region uses the same ink at 256 levels so the two sides of the
first wipe differ in exactly one property. The only colour anywhere is the
one-pixel wipe edge, cold blue, which is furniture.

The three cache states are the usual three, except that the absent one does
something better than a card: with no cached imagery at all, `build()` draws a
lit sphere over a graded ground with a linear ramp bar beside it — the classic
thing you dither to show a dithering algorithm off, generated from arithmetic —
and says `TEST IMAGE` where the satellite's name goes. Stale imagery plays as
it is with the age in red, because the subject of this panel is the arithmetic
and two-day-old cloud dithers exactly as well as this morning's.

```console
$ python3 dither.py --stats                 # build timings and per-method error
$ python3 dither.py --source test           # the generated subject
$ python3 dither.py --wipe 6 --no-zoom      # slow, the ladder only
$ python3 dither.py --zoom-factor 2 --gamma 1.5
$ python3 scripts/test-dither.py            # 57 checks incl. all three states
```

The cycle is 28.8 s at 20 fps. Desktop cost is 0.003 ms a frame mean, p95
0.003, max 0.009 — it is two memcpys — and `build()` is 32–80 ms, of which the
two diffusion loops are about 15 ms; on the Pi expect roughly a second of
build and well under a millisecond a frame.
