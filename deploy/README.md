# Putting the wall in Home Assistant

The wall is not a light. It plays generated animations and little clips, and if
you model it as one light entity you get a colour picker that does nothing and a
brightness slider that fights whatever is on screen. It *is* also twenty
thousand lumens on a wall in a workshop, and people reasonably want to turn that
off with a switch. So it is both, as several entities on one device.

```
Home Assistant ──MQTT──▶ broker ──▶ ftctl ──unix socket──▶ ft_server ──▶ panel
                                      │                        ▲
   phone/browser ──▶ nginx :80 ───────┤                        │
                       └──▶ ftsched :8081 ───────UDP :1337─────┘
```

Only the broker and Home Assistant are elsewhere. `ftctl` runs on betelgeuse,
because the control socket is a unix socket.

## Why the pieces are where they are

**Global state lives in `ft_server`.** It owns the panel and composites every
client onto it, so how bright the wall is and whether it is showing anything are
properties of the display rather than of whoever happens to be drawing. Put them
in a client and a laptop pushing pixels could override the wall being off.

**`ftctl` is a separate daemon, not routes in `ftsched`.** The whole point of a
global off switch is that it works when the rest does not. `ftsched` is
`BindsTo=ft_server` and restarts with it; an off switch living there would be
missing exactly when somebody is trying to deal with a misbehaving wall.

**`ftctl` is also what remembers.** `ft_server` deliberately persists nothing:
after it drops privileges it can write nowhere, and a dragged slider is dozens of
commands a second, which is not a thing to point at an SD card. `ftctl` keeps
desired state and re-applies it when the `generation` field changes, which is how
a server restart gets noticed rather than guessed at.

**`nginx` replaces `ftindex`.** That was a Python front door doing four things
nginx does in a page of config. The reason it was a separate process — that
pushing megabytes of previews through `ftsched` would run them through the GIL
the render loop waits on — stops applying when the process is nginx.

## Install order

Each step is useful on its own, so stop anywhere.

### 1. The server

```sh
sudo cp server/ft_server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart ft_server.service
```

This adds `--control-socket /run/ft/control.sock` and the `RuntimeDirectory` it
needs, and drops the old `start-ft.sh` wrapper. Keep that script until this has
survived a reboot; going back is one `ExecStart` line.

The protocol is lines of text, so the client is whatever is to hand -- except
that betelgeuse has no netcat (`apt install netcat-openbsd` if you want
`nc -U /run/ft/control.sock`). `tools/ftc.py` is the fifteen lines that replace
it:

```sh
python3 tools/ftc.py get
python3 tools/ftc.py brightness 40
python3 tools/ftc.py blank on
python3 tools/ftc.py wipe
```

`tools/ftstairs.py` holds a series of levels long enough to actually judge them,
which is the only sane way to look at the bottom of the range:

```sh
python3 tools/ftstairs.py --freeze sunset --hold 10        # 100 60 30 15 5
python3 tools/ftstairs.py --freeze sunset 40 20 10 5 --hold 15
```

Freezing matters: banding shows up in a still gradient and not at all in
something moving, and a mostly-dark demo hides it entirely. A webcam will lie to
you here too -- auto-exposure compensates as the wall dims, so 20% looks much
like 80% on a stream. Look at the wall.

Nothing listens without `--control-socket`, so an unflagged server behaves
exactly as before.

### 2. ftctl

```sh
sudo apt install python3-paho-mqtt        # optional; without it, HTTP only
sudo cp demos/ftctl.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ftctl.service
curl -s localhost:8082/api/display | python3 -m json.tool
```

### 3. MQTT credentials

They do not belong in a file in the repository:

```sh
sudo systemctl edit ftctl.service
```
```ini
[Service]                          # <- this line matters, see below
Environment=FTCTL_MQTT_HOST=mqtt.lan
Environment=FTCTL_MQTT_USER=ftctl
Environment=FTCTL_MQTT_PASS=...
Environment=FTCTL_PUBLIC_URL=http://betelgeuse.local/
```

**Keep the `[Service]` header.** Without it systemd discards every `Environment=`
line with an "Assignment outside of section" warning in the journal, `--mqtt-host`
arrives empty, and the wall never turns up in Home Assistant. `journalctl -u ftctl`
says which happened:

```
ftctl: MQTT connected to broker:1883, publishing discovery to homeassistant/device/betelgeuse/config
ftctl: no --mqtt-host, so no Home Assistant; HTTP control API only
ftctl: MQTT refused connection, rc=5 (not authorised)
```

The wall then appears in Home Assistant by itself — discovery is the
device-based form, one retained payload describing every entity, so it arrives
as one device rather than eight loose entities.

| Entity | What it is |
|---|---|
| `light.betelgeuse` | the display: on/off and brightness |
| `switch` Playing | the rotation, paused or not |
| `select` Demo | jump to a named effect |
| `button` Next | advance the rotation |
| `sensor` Now playing, Frame rate | what is on, and how it is doing |
| `image` Screen | a capture of the panel itself |

The `image` entity is the real composite off the control socket, the same frame
the login banner draws, so Home Assistant and a terminal cannot show different
walls. Home Assistant polls an image entity roughly once a second, so the
capture is cached for `--thumbnail-ttl` seconds (2 by default) and the cost is
one capture per window no matter how many dashboards are watching — about 25 ms
of Pi to take a frame and deflate it. A blanked panel is dimmed the same way the
banner dims it. If the snapshot cannot be had at all — an older `ft_server`, or
the socket gone — it falls back to the baked preview clip for whatever is
playing.

On/off and brightness are separate channels and **off is never brightness 0** —
which is what AWTRIX and WLED both settled on, because people expect off to
remember how bright it was. It matters more here than on a strip: a HUB75 panel
at minimum duty cycle is not off, it is dim and banding.

Pause is a separate entity from power on purpose. Staying on one effect while the
wall is lit, and blanking a wall that is still rotating, are both things people
want, and one entity cannot say both. By default turning the light off also
pauses the rotation, which is policy that lives in `ftctl` and nowhere else; the
`--no-pause-when-off` flag turns it off.

Note what pause does and does not do. `ftsched` calls `show.hold(dt)` — *the
effect keeps running, the slot just never ends.* So Playing off does not freeze
the picture; it stops the changeover. Toggling it looks like nothing happened,
and the difference only shows up 45 seconds later when the wall does not move
on. That is the intended behaviour and it is worth knowing before diagnosing it
as a broken switch.

**Wipe and Restart rotation are deliberately not here.** Restart is
`invalidate_from(index + 1)` plus the same `skip()` as Next, so from the room it
was Next with a different label; its queue rebuild only matters right after
editing the rotation, which happens at the panel. Wipe clears every layer in
`ft_server`, and `ftsched` repaints layer 0 at 30–60 fps, so the wall is back
inside a single frame — it is a real tool for a stuck client, used with the
scheduler stopped, not a button for a room. Both remain on the control socket
and in the panel. Removing them from Home Assistant takes two publishes, not
none: see `RETIRED` in `ftctl_mqtt.py`, because HA does not drop an entity it has
registered merely because you stopped describing it.

Everything that needs `ftsched` carries its own availability topic, so when the
scheduler is down those entities go unavailable on their own and the light stays
usable. That is the whole reason `ftctl` is its own daemon.

**If entities do not appear, nothing here will tell you.** A discovery config
Home Assistant refuses produces no entity, no repair issue, and no error `ftctl`
can see — the publish succeeded, after all. The only trace is a line in HA's own
log, and one payload describes every entity, so one bad key loses all of them at
once. Check from the box rather than guessing:

```sh
sudo python3 tools/ftmqttcheck.py
```

It reads what is really retained on the broker and replays the parts of HA's
validation that are easy to fall foul of: the device-level body is merged into
every component that does not set a key itself, and `availability_topic` and
`availability` are mutually exclusive — so a shared `availability_topic` lands on
top of per-component `availability` lists and invalidates the lot. That is why
availability is stated on every component here and never in the shared body. It
also lists stale per-component discovery topics from any older scheme, which
drift out of agreement with the device payload; publish an empty retained
payload to a discovery topic to delete it.

**Traffic.** Anything a person changes is published at once; otherwise nothing
is sent until the heartbeat (`--mqtt-heartbeat`, 60s). Idle, that is about
0.05 messages a second. The rotation moving to its next effect counts as a
change, so expect a small burst every 45 seconds or so and near-silence between.
Frame rate rides along with whatever publish happens next rather than causing
one — it wobbles constantly and is only a diagnostic.

### 4. nginx

```sh
sudo apt install nginx
sudo cp deploy/nginx-betelgeuse.conf /etc/nginx/sites-available/betelgeuse
sudo ln -sf ../sites-available/betelgeuse /etc/nginx/sites-enabled/betelgeuse
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
sudo systemctl disable --now ftindex.service
```

`ftindex.py` and its unit are gone. If you are upgrading a box that still runs
it, `sudo systemctl disable --now ftindex.service` is the missing step above, and
the stale unit in `/etc/systemd/system` can go with it. `tailscale serve --bg
--https=443 http://127.0.0.1:80` is unaffected.

Optionally, advertise the web interface to things that have never heard of
FlaschenTaschen — Safari's Bonjour list, `avahi-browse`, a phone scanning the
network:

```sh
sudo cp deploy/avahi-betelgeuse-http.service \
        /etc/avahi/services/betelgeuse-http.service
```

`ft_server` separately advertises `_flaschen-taschen._udp` with `ui=` pointing at
this same panel, and sets bit 4 of its feature mask when `--control-socket` is
configured, so a FlaschenTaschen client can tell that brightness and blanking are
available before trying them. Check both with:

```sh
avahi-browse -rt _flaschen-taschen._udp
avahi-browse -rt _http._tcp
```

The panel then shows a display row under the transport controls. It is hidden
whenever `/api/display` does not answer, so `ftsched` served straight off :8081
looks exactly as it did.

### 5. The login banner

`ftctl` renders the wall's status to `/run/ft-motd/banner.ansi` whenever
something a person would notice changes. To show it at login:

```sh
sudo rm -f /etc/motd                       # keep a copy if you want the Debian text
sudo ln -s /run/ft-motd/banner.ansi /etc/motd
sudo chmod -x /etc/update-motd.d/10-uname  # its output is already in the banner
```

**Not** a script in `/etc/update-motd.d/`, which is where this obviously belongs
and does not work: `pam_motd` on Debian 11 does not run `run-parts` for sshd
sessions, so a script there is simply never executed. `/etc/motd` is the path
that does fire, via `session optional pam_motd.so noupdate`.

Nothing is computed at login. Asking the wall for its status at every prompt cost
2.8 seconds on this Pi; reading a pre-rendered file costs 60 ms. The symlink also
fails well: `RuntimeDirectory` removes the file with the daemon, so a box with no
`ftctl` prints nothing rather than something stale.

The picture in the banner is the wall itself, from the control socket's
`snapshot` command, not a stock clip of whichever effect is playing. That
distinction is worth the round trip: the old preview for `daliclock` had been
recorded at 19:51, so anybody logging in while the clock was up was shown a wall
apparently displaying 7pm, at any hour of the day. Because the frame goes stale
on its own with nothing in the state to show it, this is the one thing here on a
timer -- `--motd-picture-ttl`, 30 seconds by default, `0` to repaint only on
state changes. A blanked panel is drawn as a dimmed ghost of the frame behind
the blank and captioned as dark, rather than as a lit picture of a wall that is
off.

```sh
python3 demos/ftmotd.py                    # render to stdout to see it
```

### 6. The data fetcher

Only needed if `propagation` or `tide` are in the rotation. Without it both
render correctly and say they have no data, which is the honest answer but not
an interesting one.

```sh
sudo cp deploy/ftdata.service deploy/ftdata.timer /etc/systemd/system/
sudo -u pi mkdir -p /home/pi/.cache/ftdata
sudo systemctl daemon-reload
sudo systemctl enable --now ftdata.timer
```

The `mkdir` is load-bearing and is the step that will be skipped. `ftdata.service`
runs `ProtectHome=read-only` and carves out that one directory with
`ReadWritePaths=`, which systemd implements as a bind mount -- and it cannot bind
mount a directory that is not there. A missing directory gives a unit that
refuses to start, which is at least loud.

**Enable the timer, not the service.** The service is one pass: fetch every
product, write the cache, exit. Enabling it directly would run it once at boot
and then never again, and the wall would show data that got older all week.

**Why the cache is in `/home/pi`.** `ftsched.service` runs `ProtectHome=read-only`,
which means it can still *read* everything under `/home/pi`. So the fetcher
writing `~/.cache/ftdata` and the scheduler reading it need no `FT_DATA_CACHE`
in either unit, and a demo run by hand for debugging reads the same cache the
wall is reading. Move it to `/var/cache` and that stops being true in both
directions.

**Why the pixels are not in `/home/pi`.** `goes` caches a six-hour window of
satellite imagery as a 3.5 MB array and rewrites the whole thing every pass to
add the three frames that are new, which at four passes an hour is **336 MB a
day onto the SD card the Pi boots from** -- more than everything else on the
machine put together, for data that its own TTL calls stale half an hour after
it is written. So the two halves of a record go to different places. The JSON
stays in `~/.cache/ftdata`, where it is worth keeping: a tide prediction fetched
yesterday is still true this morning, so those panels come up with a curve on
them rather than a card. The binary sidecar goes to `/run/ftdata`, which is
tmpfs, and the card sees **1,636 bytes a pass** -- the record and nothing else,
157 kB a day, a two-thousandfold cut. Measured, on betelgeuse, over two
consecutive passes against a populated cache.

`RuntimeDirectory=ftdata` in `ftdata.service` makes that directory and gives it
to `pi`; **`RuntimeDirectoryPreserve=yes` is what keeps it**, because without it
systemd removes a `RuntimeDirectory` when the process exits and this is a
`Type=oneshot` -- the fetcher would write a window, exit, lose it, and refetch
sixteen megabytes of JPEG every quarter hour forever. Nothing needs adding to
`ftsched.service`: `ProtectSystem=strict` leaves `/run` readable, and the demo
finds the sidecar by the name in the record. The one thing given up is the
window across a reboot, for the two minutes until `ftdata.timer`'s `OnBootSec=`
fires, and `goes` already has an honest card for exactly that.

`FT_DATA_BLOBS` overrides the directory; with no `/run/ftdata` -- a checkout on a
workstation, which cannot make one -- sidecars fall back to sitting beside the
records, as they used to, with no setup.

Checking it works, in increasing order of effort:

```sh
systemctl list-timers ftdata.timer          # when it last ran and next will
systemctl status ftdata.service             # how the last run went
journalctl -u ftdata.service -n 20          # "ftdata: 6/6 products refreshed"
sudo -u pi python3 /home/pi/ft-cpp/demos/ftdata.py --list
sudo systemctl start ftdata.service         # force a refresh now
```

`--list` is the useful one: it prints every product with its TTL and the age of
what is actually cached, so `absent` or an age in hours localises the problem to
the fetcher rather than the demo. A single product failing is normal and
survivable -- `ftdata.py` keeps the previous record when a fetch fails, so a
missed run degrades to slightly older data rather than to none, and the demos
print the age either way.

A failed run does not stop later ones. A service in the failed state does not
disable or hold off its timer, so there is nothing to reset after an afternoon
when NOAA was unreachable; the next tick just works.

## Updating the checkout

A deploy is a fast-forward of `~/ft-cpp` and then a restart of the daemons that
hold Python state. **Both of them, not just the obvious one:**

```console
$ cd ~/ft-cpp && git pull --ff-only jof betelgeuse
$ sudo systemctl restart ftsched.service
$ sudo systemctl restart ftctl.service     # yes, this one too
```

`ftctl` is easy to forget because it is deliberately decoupled from the display
-- the whole point of a global off switch is that it survives whatever the
scheduler is doing, so nothing else restarts it. But it `import`s `ftmotd`,
which `import`s `ftdata`, and Python binds those module objects once at process
start. An ftctl left running across a deploy therefore renders the login banner
from **the product registry as it was when ftctl started**.

That is not hypothetical. On 2026-08-11 the wall's address moved into
`ftsite.py` and the two per-site weather products were renamed to embed the
corrected coordinates. `ftsched` was restarted; `ftctl` was not. For the next
day the banner reported

```
  ● data     ████████████▒▒ 14/16 fresh
             wx-air-37.7627_-122.3966 absent
             wx-model-37.7627_-122.3966 absent
```

-- two products that no longer existed, named by a registry two days stale,
while every one of the 28 products that did exist was fetching perfectly. A
banner that cries wolf is worse than no banner, because it is the thing people
read while deciding whether to look closer.

`ftmotd.registry_drift()` now detects this case directly and prints
`registry stale · restart ftctl` instead of a list of phantom absences, so the
banner tells you the truth even when this step is missed. Do not treat that as
permission to miss it: the banner is only one of the things reading a stale
registry.

## Things worth knowing

**A blanked wall is not an idle Pi.** The panel keeps being refreshed with an
all-black frame at full rate on its isolated core. Blank is what the display
shows, not what the machine is doing.

**Brightness below about 20% will band.** `SetBrightness()` scales values before
the CIE1931 curve, which is what makes the percentage perceptually linear, but
the bottom of an 8-bit range on a HUB75 panel is genuinely coarse. `--led-pwm-bits`
and `--led-pwm-dither-bits` are the knobs if it bothers you.

**Brightness does nothing to what is already on screen, by itself.** The library
bakes it in when a pixel is encoded, so the server forces a whole-frame repaint
behind every change. One repaint is enough, because the two canvases are kept
byte-identical rather than a frame apart.

**Wipe is the weakest of the three.** The garbage collector already clears
layers above the background after 15s, and `ftsched` repaints layer 0
continuously, so a live client paints over a wipe immediately. It earns its
place against a stuck client that keeps re-sending.

**Nothing here is authenticated**, deliberately and as before. Anything on the
network can already push pixels over UDP. Keep it on the LAN or the tailnet.

## Rolling back

```sh
# the server, binary and unit
cp /home/pi/ft-server.rollback-pre-dc /home/pi/ft-cpp/build/server/ft-server
sudo systemctl restart ft_server.service

# the front door: nothing to fall back to now that ftindex is gone, so this
# leaves :80 closed. ftsched is still reachable at 127.0.0.1:8081 over ssh.
sudo rm /etc/nginx/sites-enabled/betelgeuse
sudo systemctl stop nginx
```

`ftctl` can simply be stopped; nothing depends on it, which is the point.
