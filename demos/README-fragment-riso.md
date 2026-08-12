### riso

![riso](screenshots/riso.png)

A Risograph duplicator printing, seen along the paper path: feed deck at the
left, ink drum in the middle, catch tray at the right. A sheet slides out of
the deck, passes under the drum, and the ink wipes onto it at the nip. The nip
is a fixed column and the paper is what moves, so the sheet's leading edge —
its right edge — is inked first and the seam between the new colour and the old
sweeps backwards across the sheet, from leading edge to trailing edge, while
the sheet itself slides rightwards. Watch one pass and the new colour appears
out of the drum's contact column and the printed part grows out to the right of
it. It sits in the tray long enough to be looked at,
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
bakes the whole cumulative stack once: a frame halfway through laying the third
colour is literally `cum[2]` on the near side of the nip and `cum[3]` on the far
side, the part that has already gone under the drum. Two blits, no arithmetic,
and the wipe boundary is exact — the screenshot above is one of those frames,
with `ISO` printed and the `R` still to come.

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

What was hard was that same split, twice over, and both times it drew a
perfectly plausible still. The first version split the sheet at `nip - x` in
sheet-local coordinates and clipped that at zero, so once the sheet's left edge
was past the nip the whole thing reverted to the un-inked image: a sheet that
had just been fully printed went blank on its way to the tray. The fix for that
was a guard — if the sheet is entirely past the nip, treat it as fully printed
— and the guard papered over a worse bug underneath, which then shipped. The
two halves were the wrong way round. The paper travels left to right, so the
leading edge is the *right* edge and the fresh ink is on the right, but the
code painted `cum[k+1]` on the left. Every symptom followed: while the sheet was
still approaching, `nip - x` exceeded the sheet width and clipped, so the sheet
arrived already printed; as it advanced it visibly *lost* the new colour; and
then the guard slammed it back to printed in a single frame. The whole thing
read as a stutter rather than as a wipe, and it was only caught by watching it
on the emulator. The right quantity is `(x + ws) - nip`, clipped into `0..ws` —
how much of the sheet has been under the drum — and with the geometry right the
guard is unnecessary, because a sheet fully past the nip clips to `ws` on its
own.

The existing test did not catch it because it compared whole-sheet ink totals
between frames, and a sheet drawn inside out has an entirely reasonable total on
every frame. `scripts/test-riso.py` now drives the module with a stand-in
artwork of two full-coverage separations, which makes every column of the sheet
one of three flat colours and so classifiable by eye and by array, and asserts
the wipe as geometry: at most two ink states across the sheet's width at any
moment, the fresher one entirely on the leading side, the seam between them
pinned to the nip column rather than drifting with the paper, that seam sweeping
the full width monotonically once per pass, no sheet-local column ever losing
ink within a job, and no single frame changing how much is printed by more than
a couple of percent. Reverting the fix fails three of those five. It also still
asserts the overprint pixels against the literal product of the two inks and the
paper.

The travel curve turned out to need no retuning. `path_x` runs the sheet as
three straight segments, and its middle run was already defined as leading-edge-
at-the-nip to trailing-edge-at-the-nip; measured after the fix, the wipe starts
at u = 0.253 and finishes at u = 0.718 of the print phase, so it crosses the
sheet at about 1.8 columns a frame over the middle 47% of the pass, which is
what the easing was designed for all along. It was the blits that were wrong,
not the motion.

```console
$ python3 riso.py --art poster --seed 7
$ python3 riso.py --misreg 4 --screen 7      # sloppy registration, coarse screen
$ python3 riso.py --inks pink,federal,black  # authentic, and much too dark
$ python3 scripts/test-riso.py
```
