### crash

![crash](screenshots/crash.png)

A gallery of famous computer deaths. Five screens a generation learned to
dread, each held for eight and a half seconds and captioned like an exhibit:
the C64's `?SYNTAX ERROR`, the Sad Mac, the Amiga's Guru Meditation, a Windows
blue screen and a Linux kernel panic. The whole loop is 42.8 seconds, which is
one slot, and it is chronological — 1982, 1984, 1985, 2001, 2020.

**The museum label along the bottom is the safety catch, not decoration.** A
convincing blue screen on a wall in a public workshop makes somebody think the
wall has crashed and go looking for whoever runs it. That reaction is half the
joke and it is also a support call. So the bottom eight rows are a plinth: a
hairline rule, near-black, and a caption in a bone colour that belongs to no
specimen — `AMIGA OS 1.3 - GURU MEDITATION, 1985` on the left, `3/5` on the
right — in the same place, in the same face, in every single frame of the loop.
It reads in well under two seconds and it turns the panel from a prank into a
small history exhibit, which is a much better fit for a makerspace than a
prank is. Two more tells come free: the screens visibly change every few
seconds, and a real crash does not become a different crash later; and the
plinth reads as a matte around an object. Of the three the caption is the one
doing the work, and `scripts/test-crash.py` asserts it by reading the words
back off all 855 frames of the loop, because it is the one property here that
is a safety property rather than a taste one.

**Each specimen is rendered at its native column count, and the column count
picks the font.** That one decision settles every layout question in the file.
A C64 is a 40-column machine, so it gets an 8x8 cell — 320 divides by 8 exactly
— and those chunky glyphs are the whole reason anyone recognises it; four
pixels of border each side buys the two-tone frame that makes it a C64 rather
than a blue rectangle, at the cost of one column nobody has ever counted.
Everything else is an 80-column screen and gets a 4 px cell, 78 columns inside
a margin, which is the *same proportion* a 640-wide Amiga or VGA screen gives
80 columns of 8x8 text. That is why the guru box comes out occupying about the
fraction of the width it really did rather than being eyeballed, and why
`*** STOP: 0x000000D1 (0x0000002C,0x00000002,...)` fits on one line, as it must
— that line is the icon of the blue screen and breaking it would be wrong.

**Both fonts are bitmaps written out in the file, not TrueType.** The Pi does
not have the faces this was written on, a fallback face is a different metric,
and at six pixels of cap height an antialiased edge is a smudge. More to the
point, DejaVu Sans Mono at 8 px is not a C64 and no thresholding makes it one.
The 8x8 set is the Commodore ROM shape; the 4 px set is a 3x5 body with real
ascenders and a descender row, because a blue screen set in small capitals is
instantly wrong and the ragged rhythm of mixed case is most of what makes a
wall of 3-pixel-wide text read as English. Every glyph is checked for being
non-empty, for fitting its cell and for being distinct from every other glyph:
a hand-typed hex table's characteristic failure is a typo that silently
duplicates a shape you already have, and eyeballing does not catch it. It
caught `~` and `-`.

**Colours are looked up, and asserted.** VIC-II blue is 0x352879 and light blue
0x6C5EB5 (Pepto's measurements off a real 6569, which is what every emulator
ships). The blue screen ground is VGA attribute 1, 0x0000AA, with attribute 15
white text. The Linux console is VGA attribute 7, 0xAAAAAA — grey, *not* white,
and drawing a panic in white is the commonest mistake in a recreation because
it makes it look like a blue screen that lost its background. The guru is pure
red on black. Getting one of these wrong is the most visible possible failure
for this demo, so the test asserts each against its documented value and
against how much of its panel it covers.

**Only two things move.** The guru's border flashes and the C64's cursor blinks
— a third of a second on, a third off, which is a 60 Hz jiffy counter toggling
every twenty frames. Everything else is dead still, because these screens are
static by nature and the stillness is what makes them read as death rather than
as a screensaver. Between specimens the picture collapses to a bright line and
the next opens back out of it over half a second. The collapse needed an
*additive* white term as well as a gain: the Sad Mac's centre row is black, so
brightening alone collapsed it to nothing and the cut read as a dropped frame
rather than as a CRT.

Everything is baked in `build()` as complete 64x320 frames, blink variants
included, so a held frame is one memcpy — 0.002 ms/frame measured, 0.035 ms
through a collapse, which is the cheapest thing in the show by a wide margin.
The cost is 430 KB of baked frames, which is the right way round on a machine
where an operation costs more than a page of pixels. Nothing reads the clock;
the order and every hex code come from `--seed`.

Two things it does not do. The Sad Mac had a chime — four notes of doom on the
Mac II — and the wall has no speakers, so that half of it is simply missing.
And DOS's `Abort, Retry, Fail?` was cut: grey text on black is the kernel
panic's territory already, and five specimens rendered well beat six rendered
approximately. One honest uncertainty: the C64 error is printed here as
`?SYNTAX ERROR` with one space, which is what the ROM's message-plus-` ERROR`
concatenation gives; the two-space form is widely reproduced and may be what
you remember.

```console
$ python3 crash.py --only guru --hold 30      # sit on one specimen
$ python3 crash.py --shuffle --seed 7         # a different exhibition
$ python3 crash.py --hold 4 --gap 0.2         # the whole gallery in a slot
```
