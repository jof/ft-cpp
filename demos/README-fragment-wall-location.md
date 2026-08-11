### where the wall is — `site.json` and `ftsite.py`

The installation's own coordinate, in one file, read by everything that needs it.

**What it replaced.** The wall's latitude and longitude used to be written out
seven times: `quake.py`, `adsb.py`, `sats.py`, and three separate constant pairs
in `ftdata.py` (`WX_LAT/WX_LON`, `ADSB_LAT/ADSB_LON`, `QUAKE_LAT/QUAKE_LON`),
plus fixtures in three test scripts. All seven said `37.7627, -122.3966`, and all
seven were wrong by 273 m — a coordinate for somewhere a couple of blocks away,
carried forward from whatever first guess it started as, and described in one
comment as "the Mission" when the wall is in Dogpatch. Seven copies of a fact is
how a fact goes wrong quietly: nothing disagrees with anything, so nothing
complains.

The true position is `37.7624929274026, -122.39969356310202` — Sequoia Fabrica,
1736 18th Street.

**The file.**

```json
{
  "name":  "Sequoia Fabrica",
  "short": "SF",
  "lat":   37.7624929274026,
  "lon":   -122.39969356310202
}
```

`name` is the long form for a label with room; `short` is what `sats.py` puts
next to the tick on the world map, where four characters is the budget. Unknown
keys are kept and ignored, so a file may carry settings a given checkout does not
understand yet.

`FT_SITE` points at another file, the same way `FT_DATA_CACHE`, `FT_GBFS_BASE`
and `FT_PIXELART_DIR` work. `python3 ftsite.py` prints which file was found and
what came out of it, which is the fastest way to answer "why does the wall think
it is in the wrong place".

**Why a file and not just one constant in `ftdata.py`.** Consolidating the seven
literals into one would have fixed the drift, but not the other half of the
problem: this tree has two long-lived branches, one that goes upstream to
FlaschenTaschen and one that is this wall. An address compiled into `adsb.py` is
exactly the sort of fact that makes those two diverge and stay diverged. In a
file, the demo code goes upstream unchanged and the installation carries its own
`site.json`.

The loader is its own module rather than part of `ftdata` because `ftdata` is the
data layer — the fetchers, the cache, the network — and a demo that draws a map
but fetches nothing should be able to ask where it is without importing any of
that. The dependency runs one way: `ftdata` imports `ftsite`, never the reverse.
`ftsite` imports `json`, `os` and `sys` and nothing else.

**Failure is a warning, not an outage.** The defaults compiled into `ftsite.py`
are the real address, so a fresh checkout with no `site.json` draws a real panel.
Every failure mode falls back key by key: absent (silent — that is the normal
upstream case), unparseable, not an object, a latitude that is a string, a
longitude off the globe. A file that gets `lon` right and `lat` wrong still
contributes its longitude and gets one line of complaint on stderr about the
rest. Nothing here raises. The wall coming up in the wrong city is a bug somebody
notices; the wall not coming up is an evening lost.

**What moved on screen: nothing you can see.** 273 m at the scales these panels
draw at is:

| panel | scale | 273 m is |
|---|---|---|
| `adsb` | 50 nm across 320 px | 0.24 px — measured diff over a full loop: **0 pixels** |
| `quake` bay tile | ~1.4 km/px | 0.20 px; the site marker rounds to the same pixel on both tiles |
| `quake` region tile | ~10 km/px | 0.03 px |
| `sats` | world map, 1.125°/px | 0.003 px — measured diff: **0 pixels** |

Rendering each demo for a 60 s loop at both coordinates with the clock frozen
(these panels take "now" from `time.time()`, so an unfrozen A/B compares two
different moments and tells you nothing) gives zero differing pixels for `adsb`
and `sats`, and for `quake` up to 7 pixels in a frame — all of them single-pixel
steps in the anti-aliased 100 km and 300 km range rings, in `C_RING` (22, 30, 40)
against near-black. Invisible at any distance, and invisible up close.

The numbers that do change are the printed ones, and they change by less than
their own rounding: the Berkeley seismometer goes from 17.1 km at 44° to 17.3 km
at 45°, which `helicorder` still draws as `BRK 17KM NE`, and every event distance
in the `quake-usgs` payload shifts by up to 273 m depending on its direction.

**Deploying it: the wx products get renamed.** This is the one consequence that
needs a hand. `ftdata._wx_site()` builds product names out of the coordinate to
four decimals, so moving the site renames two products:

```
wx-model-37.7627_-122.3966   ->   wx-model-37.7625_-122.3997
wx-air-37.7627_-122.3966     ->   wx-air-37.7625_-122.3997
```

Nothing renames the *files*. What happens on the Pi, in order:

1. The moment the new code is in place, `wx` asks for the new names, finds no
   record, and draws its no-data card. It does not throw and it does not go
   blank — this is the "absent" state the panel already knows how to draw.
2. `ftmotd`'s data line counts registered products, not files, so the two new
   names show up as `absent` and are named on the continuation line until the
   fetcher runs. The two old files are no longer registered, so ftmotd cannot see
   them at all: no spurious count, no phantom failure. Nothing reports an error
   anywhere in the gap.
3. The next `ftdata.timer` pass fetches both new products (met.no and Open-Meteo,
   ~600 bytes each) and the panel is back. If you would rather not wait, run one
   pass by hand.
4. The old files sit in the cache directory as orphans forever. `prune_blobs()`
   and `sweep_blobs()` will not touch them: both deal only with `.npz` sidecars
   in the tmpfs blob directory, and `sweep_blobs()` deliberately refuses to run
   against a cache directory at all, because a thing that deletes records by age
   is the exact fault it exists to prevent. So they need deleting by hand. It is
   about 1 KB; it is tidiness, not urgency.

```sh
# on the wall, as the user the fetcher runs as
rm -f ~/.cache/ftdata/wx-model-37.7627_-122.3966.json \
      ~/.cache/ftdata/wx-air-37.7627_-122.3966.json
python3 ~/ft-cpp/demos/ftdata.py --once \
    --only wx-model-37.7625_-122.3997,wx-air-37.7625_-122.3997
python3 ~/ft-cpp/demos/ftdata.py --list | grep wx-      # both should be fresh
```

`wx-obs-SFOC1` is keyed by station id, not by coordinate, and is unaffected. So
are `adsb-bay` and `quake-usgs`, whose names carry no coordinate — their *payload*
distances change on the next fetch and nothing else does.

**What should move into this file next, and did not now.** The tide station
(`tide.py`, 9414290), the swell buoy (`swell.py`, 46026), the NWS observation
station (`WX_STATION`, SFOC1), the ADS-B query radius, the BART line
`stringline.py` follows, and the satellite roster are all installation facts by
the same argument. They were left alone deliberately: this change went in
alongside six other agents editing these same demos, and a diff that touched
every panel at once would have been a merge conflict in six directions. The
schema takes new keys without a version bump, so they can move one at a time.
