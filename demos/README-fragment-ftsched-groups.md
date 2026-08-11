### Group buttons

Sixty-three cards is a lot of switches. The thing people actually want from the
panel during an event is a mode — *just the data ones*, *just the movie ones*,
*just the Sequoia Fabrica ones* — and getting there by hand means working down
the whole list on a phone while the room fills up.

So the panel has a row of group buttons above the cards. Pressing one enables
that group's entries and disables everything else. It is not a view filter: the
wall changes. `All` puts the whole rotation back.

They behave as radio buttons, because the modes are exclusive — but membership
is not, and that distinction is the reason the taxonomy lives where it does.
`tide` is honestly both a data panel and a San Francisco panel; `voxel` is both
a demoscene technique and a flight over the Bay; `scroller` is both a classic
scroller and a sign that says SEQUOIA FABRICA. Each of them is in two groups. A
model that forced every demo into exactly one bucket would have had to pick a
loser in each of those cases, and the wrong answer would then be baked into the
rotation file for good.

#### The file

`rotation-groups.json`, next to the rotation and separate from it:

```json
{"version": 1,
 "groups": [
   {"key": "data", "label": "Data",
    "description": "Live panels reading the outside world",
    "members": ["propagation", "adsb", "goes", "..."]}
 ]}
```

Separate for two reasons. Groups are a presentation concern, and the same
taxonomy should survive a different running order — betelgeuse's rotation is one
installation's, the taxonomy is not. And the rotation file is the one that gets
edited every time a demo is added, by somebody who is thinking about frame
budgets and transitions rather than about the panel; a field on every entry
there would rot.

**Names it does not recognise are skipped.** This is load-bearing, not
defensive programming for its own sake. The file names demos that are not in
every installation, and in practice it is edited days before the demos it names
exist — the six live-data panels went into it while they were still being
written. Resolution happens once at startup against the loaded rotation, and
the startup log says how many names it dropped, in one line rather than one per
name. It is one line because there are usually a few in flight, and a paragraph
of warnings at every restart is how people learn to skip the startup log.

A group that resolves to nothing at all is dropped rather than kept, because a
button that would empty the wall is worse than a button that is not there.
`set_only()` refuses an empty set for the same reason, the way `set_all()`
already refused to switch the last effect off.

`all` is not in the file. It is synthesised, so that an edit to the file cannot
take away the way back.

#### The API

One new op on `/api/command`:

```json
{"op": "select", "group": "data"}
```

The obvious implementation was `all(off)` followed by a `toggle` per member,
entirely from the page. That is N+1 round trips and N+1 frames, and the wall
would visibly play a half-applied group for about a second on its way to the
right one. Every other op in this file lands at the top of one frame, and this
one does too: the whole set changes under the rotation lock, once.

The payload is the group's key rather than a list of names, so the group file
stays the only place membership is written down — a client cannot invent a set
of its own, and editing the file is genuinely enough to change what the buttons
do.

The group list rides on `/api/schema` alongside the option schemas, because it
is fixed for the life of the process and is fetched once per page load. Which
group is *active* rides on `/api/state`, because that changes.

Indices past the playhead are invalidated and the effect on air plays out its
slot, exactly as a single toggle already did. Cutting mid-segment because
somebody chose a mode is a worse answer than the next forty seconds being the
old mode.

#### When it is none of them

The interesting state is the one after somebody presses `Movies` and then flips
a single card. The live set is now no group, and a button still drawn as
pressed would be claiming a mode the wall is not in.

So the scheduler compares the enabled set against each group and answers `null`
when it matches none of them — `"group": null` in the state — and the page
lights no button and shows a quiet `custom mix` next to the row. Flip the card
back and the claim comes back. The comparison is server-side so that every
phone looking at the wall agrees, and it is a handful of frozenset comparisons
once a second against a snapshot that is being rebuilt anyway.

`all` is tested first, so a group that happened to list the entire rotation
loses the tie — that is the same selection under a more specific name than
anyone chose.

#### The taxonomy

Seven groups plus `All`, which is as many as fits across a phone without the
row becoming its own screen. Every one of the rotation's entries is in at least
one; thirteen are in two.

| group | what is in it |
|---|---|
| Data | the live outside-world panels: propagation, adsb, goes, caiso, sats, winds, quake, wx, ships, tide |
| Movies | wopr, defcon, tron, sneakers, trench, fsn, esper, headroom, gibson, wardial, ansi |
| Makerspace | console, knit, sewing, printer, lathe, wheel, laser, scope, splitflap, scroller, sf-tree, sf-tree-bounce |
| San Francisco | goldengate, karl, sunset, grove, voxel, sf-tree, sf-tree-bounce, wardial, tide, ships, quake, caiso, adsb, wx |
| Demoscene | fire, tunnel, starfield, metaballs, rotozoom, twister, water, cycle, floor, voxel, boing, scroller, fireworks, daliclock |
| Games | pacman, pacman-ghosts, space-invaders, mario, nyancat, toasters, boing |
| Algorithms | sort, wireworld, life, maze, slime, fireflies, chladni, scope |

Some of these took a decision rather than a lookup. `console` is in Makerspace
rather than anywhere filmic because it types out Arduino one-liners that people
in the space wrote, and it is the only demo anyone can add to without touching
code. `scope` is in both Makerspace and Algorithms: it is a bench instrument, and
it is also the closest thing here to a live plot of a function. `chladni` sits
in Algorithms rather than Demoscene because it is a physics simulation that
happens to be pretty, not an effect. `wardial` is in San Francisco as well as
Movies — the exchange it works through is a real one.

Bandwidth for a network group was considered and dropped. `bgp` and `sfmix`
would have been the whole of it, both are honestly data panels, and two members
does not earn a button on a phone.
