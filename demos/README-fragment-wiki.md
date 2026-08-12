### wiki

![wiki](screenshots/wiki.png)

Forty seconds of Wikipedia being written, played back at the speed it happened.
Every change to every Wikimedia wiki — nine hundred of them, three hundred
languages — goes out on one public event stream in real time, tens of edits a
second, continuously. This panel is one stroke per edit, arriving right to left,
rising above the line for bytes added and falling below it for bytes taken away,
with the titles of the articles crawling underneath in three lanes.

The titles are the point. LA MANO CHE NUTRE LA MORTE. FREIBURG CATHEDRAL BOYS'
CHOIR. LIST OF PRESERVED BC RAIL ROLLING STOCK. SAN ROQUE, MORGADANS, GONDOMAR.
2026 UNITED STATES GUBERNATORIAL ELECTIONS. LAKE MILLS, IOWA. They are absurd
and human and never the same twice, and everything else on the panel is arranged
so that somebody walking past reads two or three of them and understands,
without being told, that this is an encyclopedia being written right now by
people they will never meet.

**It is the only panel here that draws events rather than a state.** Tides, grid
mix, air quality, aircraft, the routing table — every other data demo on this
wall is a picture of how things are at a moment. A firehose is not that, and the
one thing it has that a snapshot does not is *burstiness*, so nothing here is
averaged into a rate. The horizontal axis is time and a stroke's column is when
its edit actually happened, to the millisecond. Where four edits land inside a
tenth of a second the strokes pile into a picket; where the stream draws breath
there is a gap. A chart of edits-per-second would have been much easier and
would have thrown the whole subject away.

**One representation choice made everything else fall out: the window is a
strip.** Lay the forty seconds out along its own time axis at twenty pixels a
second, draw every stroke and every title into that 790-pixel image once, then
scroll it at twenty pixels a second. Playback is then exactly 1:1 with reality
for free, the burstiness is preserved by construction rather than by any code
that thinks about it, a title can crawl along underneath the stroke it belongs
to because they are the same object at the same x, and `render()` is two slice
copies. At twenty frames a second the strip advances exactly one pixel a frame,
which is the smoothest a crawl can be, and it is why twenty is the default for
both numbers.

**Three encodings, and only one of them needs a key.**

  * **Up or down** is added or removed. Nothing else uses the vertical axis, so
    there is nothing to disambiguate at three metres: a panel leaning upwards is
    an encyclopedia growing, which most minutes it is — a typical window adds
    about 600 kB and removes about 20 kB. Both directions use the same
    bytes-per-pixel scale, so a deletion is never made to look bigger than the
    addition that undid it, and the lower half of the panel being nearly empty
    is a true statement and not wasted space. When a rare deep one does arrive —
    a blanking, a revert of a big paste — it punches a long spike downwards and
    it is the most conspicuous thing on the wall.
  * **Height** is the size of the edit, square root against a 900-byte full
    scale. A typo fix is two pixels, a paragraph is six, somebody pasting a
    filmography hits the top. Square root because the median edit is thirty
    bytes and the largest in a window is twenty thousand: linear draws the
    median — which is most of the panel — as nothing at all.
  * **Colour** is the project: hue from the language, saturation and value from
    the family. The English, Spanish and Basque Wikipedias are three different
    colours; `fr.wikipedia` and `fr.wiktionary` are two shades of one violet.
    Commons and Wikidata have no language and get colours nothing else uses — a
    dusty gold and a pale steel — and being the two least saturated things on
    the panel is deliberate, because between them they are usually half the
    traffic and the language projects are the interesting minority.

Two colour schemes were tried and thrown away first. A hue straight off a hash
of the wiki name gives forty unrelated colours: confetti, pretty for one second
and unreadable after that, and it puts `enwiki` and `enwiktionary` in unrelated
places. A hue by family alone — all Wikipedias blue, all Wiktionaries green —
reads beautifully and discards the language, which is the more interesting axis.

**Brightness is the bot share, and that is the fact the panel most wants to get
across.** Somewhere between half and two thirds of all edits are made by
software: category maintenance, interwiki links, Commons file housekeeping,
Wikidata bots grinding through a database import. They are drawn at 40% of a
human edit's brightness, so the panel is a dim churning mass with bright human
strokes standing out of it, which is the true shape of the thing. The number is
printed anyway, with a two-segment bar beside it, because "more than half the
edits to Wikipedia are made by robots" is worth stating outright.

**The titles are Latin-script only, and the panel says so.** The font is
`defcon.py`'s 3x5 bitmap — A-Z, digits, and a dozen punctuation marks added here
because article titles are full of apostrophes, commas and parentheses and
ST. MICHAEL'S ABBEY (ORANGE COUNTY, CALIFORNIA) with those silently dropped is a
different title. Roughly 44% of main-space titles in any window are Cyrillic,
CJK, Devanagari, Arabic or Hebrew, and a wall of tofu boxes is a failure rather
than a compromise. So the two channels split: **colour carries every project,
including the ones whose script cannot be drawn; type carries only the ones that
can.** The strokes from `ruwiki` and `zhwikisource` are up there in their own
colours doing their share of the work, their titles simply never enter the
crawl, and the key says LATIN TITLES so that nobody concludes the encyclopedia
is written in English. Accented Latin is folded rather than rejected — NFD, drop
the combining marks, plus a short table for ß, æ, ø, ł, þ and the rest that do
not decompose — which is what keeps Spanish, French, Czech, Portuguese and
Basque in the crawl instead of only English.

**Privacy, which is why this source needed care.** Every message on the stream
carries `user`: a username for a registered editor, and a bare IP address for an
anonymous one. It never reaches the cache, because `ftdata.py` never reads it
into anything — there is no field for it, no hash of it, and no count keyed on
it. Nor is there any handle that could be turned back into it: the edit
summaries go (free text written by a person, routinely naming people), and so do
the revision ids and notify URLs, because a revision id is a one-call lookup
back to its author and keeping one would be keeping `user` in a costume. Titles
are kept only from namespace 0, which is both the privacy rule and the quality
rule in one line: `User:Someone/sandbox` is a person's name in the title field,
and main-space article titles were the only ones this panel wanted. What is
stored is the public shape of the encyclopedia and nothing about who wrote it —
article titles, database names, byte deltas, the bot flag, the millisecond.
`scripts/test-wiki.py` asserts all of that against the *live* record rather than
a synthetic one, including a sweep for anything shaped like an IPv4 or IPv6
address anywhere in the JSON.

**Why it is a recording.** The wall cannot hold a socket open — `ftsched` builds
segments on a worker thread, and a `build()` blocked on a network read stops the
render loop getting the interpreter back — so the fetcher opens the stream,
listens for forty seconds, aggregates, and hangs up. What is on the panel is
therefore the last window Wikipedia published, and the age is in the top right
corner like every other data panel here. Forty seconds of firehose is about
1.7 MB off the wire, because every message carries the full rendered HTML of its
edit summary whether you want it or not and there is no server-side filter to
ask for less; that is the largest per-fetch number in `ftdata.py` and is why the
interval is fifteen minutes and not five. It becomes a 13 kB record: 560 events
as three parallel integer lists, sixty candidate titles, and a dozen aggregates.

Slightly over half of what arrives is thrown away before any of that. The stream
is 36 messages a second, but more than half are `categorize` — MediaWiki emitting
one message per category as a page's categories change, machine bookkeeping about
an edit that already has its own message — and `log` is account creations, blocks
and deletions, which is the identity-adjacent part of the stream and nothing this
panel wants. What is left is `edit` and `new`: about 15 a second, and that is the
number on the wall.

The `new` ones — an article that did not exist a second ago — get a white pip at
the tip of their stroke. There are a few dozen a window and they are the single
most interesting event in the stream.

```console
$ python3 ftdata.py --once --only wiki-stream     # 40 s of listening
$ python3 wiki.py --host 127.0.0.1
$ python3 wiki.py --speed 32 --lanes 2            # faster crawl, fewer titles
$ python3 wiki.py --full 3000                     # only big edits get tall
$ FT_DATA_CACHE=/tmp/empty python3 wiki.py        # the no-data card
$ python3 scripts/test-wiki.py
```
