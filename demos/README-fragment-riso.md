### riso

![riso](screenshots/riso.png)

A Risograph duplicator printing, seen along the paper path: feed deck at the
left, ink drum in the middle, catch tray at the right. A sheet slides out of
the deck, passes under the drum, and the ink wipes onto it at the nip — so the
new colour arrives as a left-to-right sweep across a sheet that is already
carrying the previous ones. It sits in the tray long enough to be looked at,
whips back to the deck, and goes again in the next colour. Between passes the
drum drops out of frame and comes back a different colour, and a new master
burns on the thermal head, because on a real Riso every colour needs both.

The one representation choice: the artwork is never an image, it is **N ink
channels**, one per colour, each a coverage map over the printable area of the
sheet. Rendering is compositing those channels with a per-pass integer offset
and a multiply blend, and everything else falls out of it. Misregistration is
the offset. Overprint colour is the multiply — there is no table anywhere in
the file saying pink over blue is purple, it just is, because Riso inks are
semi-transparent and multiplying two of them is what physically happens.
And the sheet after *k* passes is the *k*-th partial product, so `build()`
bakes the whole cumulative stack once: a frame halfway through laying the
third colour is literally `cum[3]` to the left of the drum and `cum[2]` to the
right of it. Two blits, no arithmetic, and the wipe boundary is exact.

The inks are the published Riso colours at their real hex values. Not all of
them work here: multiply is a darkening operator, so the default drawer is
Fluorescent Pink `FF48B0`, Yellow `FFE800`, Orange `FF6C2F`, Bright Red
`F15060`, Green `00A95C`, Blue `0078BF` and Medium Blue `3255A4`, and Federal
Blue `3D5588`, Teal, Purple and Black are left out — two of those over each
other is a black rectangle at three metres, which is authentic and unwatchable.
A job takes at most one dark ink and prints lightest first, which is both what
a print shop does (a light ink cannot cover a dark one) and the only order in
which the last pass still reads as type rather than mud. That ordering is why
the wordmark is always the final colour down.

Every channel goes through a coarse angled dot screen before compositing, each
on its own angle the way a real separation is. Flat coverage stays flat and a
ramp becomes a visible field of dots, which is what makes the sheet read as
printed rather than as a drawn rectangle. The threshold field is squeezed into
(0.02, 0.98) rather than left at (0, 1): coverage of exactly 1.0 has to beat
every threshold in the grid or solids pick up pinholes at the dot centres.

Three built-in artworks, all generated in code — the Flaschen Taschen wordmark
over a graded field with a bottle, a three-colour poster, and a two-ink
landscape whose sun sits deliberately behind a peak so the overlap is
unmissable. Registration marks in every channel at the corners of the plate are
the tell: three passes means three sets of ticks a pixel or two apart, exactly
like the trim edge of a real misregistered print.

What was hard was one bug that looked like a perfectly good frame. The sheet is
split at the nip in *sheet-local* coordinates, `nip - x`, and once the sheet's
left edge is past the nip that goes negative; clipped to zero it showed the
un-inked image, so a sheet that had just been fully printed went blank as it
travelled on to the tray. Nothing about a still frame of a blank sheet looks
wrong. `scripts/test-riso.py` now asserts across the whole loop that ink never
disappears from a sheet that already had it, and asserts the overprint pixels
against the literal product of the two inks and the paper.

```console
$ python3 riso.py --art poster --seed 7
$ python3 riso.py --misreg 4 --screen 7      # sloppy registration, coarse screen
$ python3 riso.py --inks pink,federal,black  # authentic, and much too dark
$ python3 scripts/test-riso.py
```
