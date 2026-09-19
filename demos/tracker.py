#!/usr/bin/env python3
"""The motion tracker from Aliens, watching a corridor.

Hudson holds up the tracker and the whole scene is on that little screen: a
sweep going out, blips lighting up where it finds something, and a range
readout that does nothing but get smaller. The film sells terror with one
number counting down and a beep that speeds up. This panel is that screen,
stretched along the one axis the film never had room for: 320x64 is the plan
view of a long corridor, and a corridor is where every one of those scenes
happens.

**The tracker is at the left; the corridor runs away to the right.** One
metre is seven pixels, so the forty-metre range of the sweep ends just short
of the readout box in the far-right corner, and the corridor is drawn as what
a deck plan of it would be: two bulkhead walls, ribs every five metres, a
side door in each wall now and then, a blast door at the end. Under all of it
are the range arcs -- faint circles centred on the tracker, one per five
metres -- which are the only thing that says *this is a sensor display and
not a map.* They tie the two ideas together: the corridor is real geometry,
the arcs are how the machine sees it.

**The blips are what the last pulse saw, not where the contacts are.** A
pulse leaves the tracker every so often and walks down the corridor at about
forty metres a second; a contact lights up the instant the front crosses it,
then decays until the next one refreshes it. Between pulses, the picture is
stale. That is how the prop worked and it is what makes it frightening: the
thing you are watching is always a step behind the thing that is coming.
Contacts move in bursts -- a dash, a hold, a dash -- and sometimes drop out
into the ducts for a few seconds and come back closer, so what the screen
shows is a blip that jumps, vanishes and reappears nearer, with one or two
dimmer ghosts marking where it used to be.

**The pulse rate is driven by the nearest contact.** Two seconds between
sweeps with the corridor empty; under half a second with something at two
metres. This is where the film's soundtrack lives and it is the one place the
demo breaks its own rule about state: every pulse time depends on the range
at the previous pulse, so the sequence is simulated once in `build()` and
`render(t)` only binary searches it. Same reason as every other demo here --
a sequencer builds this ahead of time and starts it at `t=0`, and the
preview baker steps it at a fixed rate, so nothing may live between frames.

**The cycle is a scene, about 76 s.** A clean, slow sweep. One contact at
the edge of range, closing in fits and starts. Then a second, a third, a
fourth. The rate climbs. Around a minute in, the nearest is inside five
metres and *more contacts appear from the side doors* at short range -- they
are in the walls -- and the readout drops to one, then zero, flashes, and the
screen tears into static. A second of black, a self-test banner, and the
sweep resumes over an empty corridor for the loop. Everything is generated
from `--seed`; the same seed is the same scene every time.

Run:  python3 tracker.py --host 127.0.0.1
      python3 tracker.py --seed 11 --palette amber   # a different night, LV-426 orange
      python3 tracker.py --cycle 50                  # tighter
"""

import bisect
import math
import sys

import numpy as np

import demoscene as ds

f32 = np.float32

# --------------------------------------------------------------------------
# Geometry. Everything in pixels; metres are converted at PX_PER_M.
# --------------------------------------------------------------------------

PX_PER_M = 7.0
ORIGIN_X = 14                       # the tracker's position on the panel
RANGE_M = 40.0                      # maximum sensor range
WALL_TOP, WALL_BOT = 6, 57          # inner faces of the two corridor walls
RIB_EVERY_M = 5.0                   # bulkhead ribs, one per five metres
DOORS = [(9.0, "top"), (17.0, "bot"), (24.0, "top"), (31.0, "bot"), (36.0, "top")]
DOOR_W_M = 1.6
PULSE_SPEED_M = 40.0                # metres per second the sweep front covers
READOUT_X = 296                     # left edge of the range readout box
H_MID = 32.0                        # corridor centreline


def door_x(d_m):
    return ORIGIN_X + d_m * PX_PER_M


# --------------------------------------------------------------------------
# A 3x5 pixel font, five rows a glyph, each row an octal digit whose three
# bits are its three columns. Same as esper.py's, kept local for the same
# reason: the Pi has no TrueType faces installed and a font that falls through
# is a demo that dies on the wall and nowhere else.
# --------------------------------------------------------------------------

_FONT = {
    "0": "75557", "1": "26227", "2": "71747", "3": "71717", "4": "55711",
    "5": "74717", "6": "74757", "7": "71222", "8": "75757", "9": "75717",
    "A": "25755", "B": "65656", "C": "34443", "D": "65556", "E": "74647",
    "F": "74644", "G": "34553", "H": "55755", "I": "72227", "J": "11152",
    "K": "55655", "L": "44447", "M": "57755", "N": "65555", "O": "25552",
    "P": "65644", "Q": "25573", "R": "65655", "S": "34216", "T": "72222",
    "U": "55557", "V": "55552", "W": "55775", "X": "55255", "Y": "55222",
    "Z": "71247", " ": "00000", "-": "00700", ".": "00002", ":": "02020",
    "/": "11244",
}
GLYPH_W, GLYPH_H, PITCH = 3, 5, 4


def text_mask(s, scale=1):
    """A bool mask of the string, one pixel between glyphs, integer-scaled."""
    s = s.upper()
    out = np.zeros((GLYPH_H, max(1, len(s) * PITCH - 1)), bool)
    for i, ch in enumerate(s):
        rows = _FONT.get(ch, _FONT[" "])
        for r, digit in enumerate(rows):
            bits = int(digit, 8)
            for c in range(GLYPH_W):
                if bits & (4 >> c):
                    out[r, i * PITCH + c] = True
    if scale > 1:
        out = np.kron(out, np.ones((scale, scale), bool))
    return out


def stamp(buf, mask, x, y, value):
    """max() a scalar `value` into buf where mask is set, clipped to buf."""
    h, w = mask.shape
    H, W = buf.shape
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    sub = mask[y0 - y:y1 - y, x0 - x:x1 - x]
    region = buf[y0:y1, x0:x1]
    np.maximum(region, np.where(sub, f32(value), region), out=region)


# --------------------------------------------------------------------------
# Palettes: one scalar intensity per pixel, coloured through a ramp. The CRT
# in the prop is a cold blue-white; amber is the other colour a 1986 sensor
# might have been.
# --------------------------------------------------------------------------

PALETTES = {
    "tracker": [(0.00, (0, 2, 5)), (0.12, (0, 22, 30)), (0.35, (0, 80, 92)),
                (0.65, (40, 190, 190)), (1.00, (220, 255, 245))],
    "green":   [(0.00, (0, 3, 1)), (0.12, (0, 26, 8)), (0.35, (10, 95, 35)),
                (0.65, (70, 210, 100)), (1.00, (225, 255, 220))],
    "amber":   [(0.00, (4, 1, 0)), (0.12, (30, 12, 0)), (0.35, (110, 50, 0)),
                (0.65, (230, 140, 20)), (1.00, (255, 240, 200))],
}


def make_lut(name):
    stops = PALETTES[name]
    xs = np.array([s[0] for s in stops])
    lut = np.zeros((256, 3), np.uint8)
    q = np.linspace(0, 1, 256)
    for c in range(3):
        ys = np.array([s[1][c] for s in stops], float)
        lut[:, c] = np.clip(np.interp(q, xs, ys), 0, 255).astype(np.uint8)
    return lut


# --------------------------------------------------------------------------
# The scene: contacts as piecewise-linear paths in (t, range_m, y_px), with
# gaps where the tracker cannot see them. Generated once from the seed.
# --------------------------------------------------------------------------

class Contact:
    """A thing in the corridor. `legs` are (t0, t1, r0, r1, y0, y1, visible)."""

    def __init__(self):
        self.legs = []

    def at(self, t):
        """(range_m, y_px) at t, or None if out of sight or not yet here."""
        for (t0, t1, r0, r1, y0, y1, vis) in self.legs:
            if t0 <= t < t1:
                if not vis:
                    return None
                k = (t - t0) / max(1e-6, t1 - t0)
                return r0 + (r1 - r0) * k, y0 + (y1 - y0) * k
        return None


def lane_y(rng, edge=None):
    """A lateral position in the corridor; `edge` pins it to a wall."""
    if edge == "top":
        return WALL_TOP + 3.0
    if edge == "bot":
        return WALL_BOT - 3.0
    return float(rng.uniform(WALL_TOP + 8, WALL_BOT - 8))


def stalker(rng, t_start, r_start, t_end_target, r_end, lunge_at=None):
    """A contact that closes from r_start to r_end in dashes, holds and ducts.

    It arrives at r_end at about t_end_target; each leg is a dash, a hold or a
    duct (invisible, and it comes back nearer), chosen at random.
    """
    c = Contact()
    t, r = t_start, r_start
    y = lane_y(rng)
    duration = max(5.0, t_end_target - t_start)
    while r > r_end + 0.5:
        remaining_t = max(0.5, t_start + duration - t)
        need = r - r_end
        rate = need / remaining_t                  # metres/s still to make
        kind = rng.choice(["dash", "hold", "duct"], p=[0.5, 0.32, 0.18])
        if kind == "dash":
            dt = float(rng.uniform(0.8, 2.2))
            dr = min(need, dt * rate * float(rng.uniform(1.0, 1.9)))
            ny = float(np.clip(y + rng.normal(0, 6), WALL_TOP + 4, WALL_BOT - 4))
            c.legs.append((t, t + dt, r, r - dr, y, ny, True))
            r -= dr
            y = ny
        elif kind == "hold":
            dt = float(rng.uniform(1.0, 3.5))
            c.legs.append((t, t + dt, r, r, y, y, True))
        else:
            dt = float(rng.uniform(2.0, 4.5))
            dr = min(need, dt * rate * float(rng.uniform(1.2, 2.2)))
            c.legs.append((t, t + dt, r, r - dr, y, y, False))
            r -= dr
            y = lane_y(rng)
        t += dt
    # Once at r_end, lurk. With `lunge_at`, the lurk ends in a rush to
    # point blank -- the readout's zero.
    if lunge_at is not None and lunge_at > t + 0.5:
        c.legs.append((t, lunge_at - 0.5, r, r, y, y, True))
        c.legs.append((lunge_at - 0.5, lunge_at, r, 0.2, y, H_MID, True))
        t, r, y = lunge_at, 0.2, H_MID
    c.legs.append((t, 1e9, r, r, y, y, True))
    return c


def wall_crawler(rng, t_start, r_m, edge):
    """A contact that drops out of a side door at short range and closes fast."""
    c = Contact()
    y0 = lane_y(rng, edge)
    y1 = lane_y(rng)
    t = t_start
    c.legs.append((t, t + 0.6, r_m, r_m, y0, y0, True))
    t += 0.6
    hold = float(rng.uniform(0.6, 1.6))
    c.legs.append((t, t + hold, r_m, r_m, y0, y1, True))
    t += hold
    dash = float(rng.uniform(1.2, 2.4))
    r1 = max(0.6, r_m * float(rng.uniform(0.15, 0.4)))
    c.legs.append((t, t + dash, r_m, r1, y1, y1, True))
    t += dash
    c.legs.append((t, 1e9, r1, r1, y1, y1, True))
    return c


def make_scene(rng, cycle):
    """Contacts and the scene's key times for one cycle of `cycle` seconds."""
    climax = cycle - 12.0                     # readout hits zero here
    swarm = climax - 9.0                      # side doors open
    contacts = []
    # The stalkers: staggered arrivals at the edge of range, converging so the
    # nearest is inside ~2 m at the climax and the rest are close behind.
    n_stalkers = 4
    for i in range(n_stalkers):
        t0 = 4.0 + i * float(rng.uniform(6.0, 10.0))
        r0 = float(rng.uniform(RANGE_M - 4, RANGE_M - 0.5))
        r_end = (0.4 if i == 0 else 1.5) + i * float(rng.uniform(1.5, 3.0))
        contacts.append(stalker(rng, t0, r0, climax - 1.0 - i * 1.5, r_end,
                                lunge_at=climax - 0.7 if i == 0 else None))
    # The swarm: things out of the walls at short range.
    doors = list(DOORS)
    rng.shuffle(doors)
    for i, (d_m, edge) in enumerate(doors[:4]):
        t0 = swarm + i * float(rng.uniform(1.0, 2.2))
        contacts.append(wall_crawler(rng, t0, d_m + float(rng.uniform(-0.5, 0.5)), edge))
    return contacts, climax, swarm


# --------------------------------------------------------------------------
# The pulse train. Interval is a function of the nearest visible range at
# the moment the pulse fires, so it is simulated forward once.
# --------------------------------------------------------------------------

def interval_for(nearest_m):
    if nearest_m is None:
        return 2.0
    k = min(1.0, max(0.0, nearest_m / RANGE_M))
    return 0.38 + 1.6 * k ** 0.8


def nearest_range(contacts, t):
    best = None
    for c in contacts:
        p = c.at(t)
        if p is not None and p[0] <= RANGE_M and (best is None or p[0] < best):
            best = p[0]
    return best


def simulate_pulses(contacts, cycle, climax):
    """Pulse fire times over one cycle and, per pulse, what it saw.

    Each pulse's snapshot is the position of each contact at the moment the
    front crossed it -- that is the picture the screen holds until the next
    pulse.  Returns (times, snapshots) with snapshots[k] a list of
    (contact_idx, range_m, y_px, t_seen).
    """
    times, snaps = [], []
    t = 0.0
    while t < cycle:
        times.append(t)
        seen = []
        for i, c in enumerate(contacts):
            # Solve r(tc) = PULSE_SPEED * (tc - t) by a couple of iterations;
            # contacts are slow relative to the front, so this converges fast.
            tc = t
            p = c.at(tc)
            for _ in range(4):
                if p is None:
                    break
                tc = t + p[0] / PULSE_SPEED_M
                p = c.at(tc)
            if p is not None and p[0] <= RANGE_M and tc < climax:
                seen.append((i, p[0], p[1], tc))
        snaps.append(seen)
        t += interval_for(nearest_range(contacts, t) if t < climax else None)
    return times, snaps


# --------------------------------------------------------------------------
# Build.
# --------------------------------------------------------------------------

def add_arguments(ap):
    ap.add_argument("--seed", type=int, default=7,
                    help="scene seed; the same seed is the same scene")
    ap.add_argument("--cycle", type=float, default=76.0,
                    help="seconds per scene, blackout and reboot included")
    ap.add_argument("--palette", choices=sorted(PALETTES), default="tracker")
    ap.add_argument("--no-readout", action="store_true",
                    help="corridor only, no range box")


def build(args):
    W, H = args.width, args.height
    rng = np.random.default_rng(args.seed)
    cycle = float(args.cycle)
    lut = make_lut(args.palette)

    contacts, climax, swarm = make_scene(rng, cycle)
    pulse_t, pulse_seen = simulate_pulses(contacts, cycle, climax)

    # ---- static layers ----------------------------------------------------
    yy, xx = np.mgrid[0:H, 0:W].astype(f32)
    R_px = np.hypot(xx - ORIGIN_X, yy - H / 2.0)          # distance from tracker
    R_m = R_px / PX_PER_M

    base = np.zeros((H, W), f32)
    # Range arcs, every 5 m, faint; the 10s a touch brighter.
    for m in range(5, int(RANGE_M) + 1, 5):
        ring = np.abs(R_m - m) < (0.5 / PX_PER_M) * 1.6
        base[ring] = np.maximum(base[ring], 0.10 if m % 10 else 0.14)
    # The far edge of range: a soft falloff so the corridor dies into dark.
    edge = np.clip((R_m - RANGE_M) / 3.0, 0, 1)
    # Corridor walls and ribs, in a corridor-only mask.
    inside = (yy >= WALL_TOP) & (yy <= WALL_BOT) & (xx >= ORIGIN_X - 10)
    floor = np.zeros((H, W), f32)
    floor[inside] = 0.045
    # Floor plates: a faint 4x4 grid seam.
    seam = ((xx.astype(int) % 6 == 0) | (yy.astype(int) % 6 == 0)) & inside
    floor[seam] = 0.07
    walls = np.zeros((H, W), f32)
    for wy in (WALL_TOP - 1, WALL_TOP - 2, WALL_BOT + 1, WALL_BOT + 2):
        walls[wy, ORIGIN_X - 10:] = 0.30
    m = RIB_EVERY_M
    while m <= RANGE_M:
        rx = int(round(door_x(m)))
        if rx < W:
            walls[WALL_TOP - 3:WALL_TOP, rx] = 0.42
            walls[WALL_BOT + 1:WALL_BOT + 4, rx] = 0.42
            walls[WALL_TOP:WALL_BOT + 1, rx] = np.maximum(walls[WALL_TOP:WALL_BOT + 1, rx], 0.09)
        m += RIB_EVERY_M
    # Side doors: a gap in the wall with an alcove behind it.
    hw = int(DOOR_W_M * PX_PER_M / 2)
    for d_m, edge_name in DOORS:
        dx = int(round(door_x(d_m)))
        if edge_name == "top":
            walls[WALL_TOP - 2:WALL_TOP, dx - hw:dx + hw + 1] = 0.0
            walls[0:WALL_TOP - 2, dx - hw - 1] = 0.22
            walls[0:WALL_TOP - 2, dx + hw + 1] = 0.22
            walls[0, dx - hw - 1:dx + hw + 2] = 0.22
        else:
            walls[WALL_BOT + 1:WALL_BOT + 3, dx - hw:dx + hw + 1] = 0.0
            walls[WALL_BOT + 3:H, dx - hw - 1] = 0.22
            walls[WALL_BOT + 3:H, dx + hw + 1] = 0.22
            walls[H - 1, dx - hw - 1:dx + hw + 2] = 0.22
    # The blast door at the end of range.
    bx = int(round(door_x(RANGE_M)))
    walls[WALL_TOP - 2:WALL_BOT + 3, bx:bx + 2] = 0.34
    walls[WALL_TOP + 6:WALL_BOT - 5, bx + 3] = 0.16
    # The tracker itself: a small bright chevron at the origin.
    walls[H // 2, ORIGIN_X - 3:ORIGIN_X + 2] = 0.9
    for k in range(1, 4):
        walls[H // 2 - k, ORIGIN_X - 3 + k] = 0.7
        walls[H // 2 + k, ORIGIN_X - 3 + k] = 0.7

    static = np.maximum(np.maximum(base, floor), walls)
    static *= (1.0 - 0.85 * edge)                # dim past the blast door
    static[:, READOUT_X - 2:] = 0.0              # the readout box's ground
    # Scanlines: every other row a little darker. Baked into the static layer
    # and applied to the dynamic one as a multiply.
    scan = np.where(yy.astype(int) % 2 == 0, f32(1.0), f32(0.82))

    # ---- readout box --------------------------------------------------------
    box = np.zeros((H, W), f32)
    box[8:H - 8, READOUT_X - 1] = 0.25
    box[8, READOUT_X - 1:] = 0.25
    box[H - 9, READOUT_X - 1:] = 0.25
    label = text_mask("RANGE")
    stamp(box, label, READOUT_X + 2, 11, 0.32)
    m_mask = text_mask("M")
    digit_masks = {ch: text_mask(ch, 2) for ch in "0123456789- "}
    if args.no_readout:
        box[:] = 0.0

    # ---- the reboot banner ----------------------------------------------------
    banner1 = text_mask("M314 MOTION TRACKER", 1)
    banner2 = text_mask("SELF TEST", 1)
    banner3 = text_mask("SCANNING", 1)

    # ---- per-frame scratch ----------------------------------------------------
    dyn = np.zeros((H, W), f32)
    lum = np.zeros((H, W), f32)
    out = np.zeros((H, W, 3), np.uint8)
    blip = np.array([[0, 1, 1, 1, 0],
                     [1, 1, 1, 1, 1],
                     [1, 1, 1, 1, 1],
                     [1, 1, 1, 1, 1],
                     [0, 1, 1, 1, 0]], bool)
    halo = np.array([[0, 0, 1, 1, 1, 0, 0],
                     [0, 1, 1, 1, 1, 1, 0],
                     [1, 1, 1, 1, 1, 1, 1],
                     [1, 1, 1, 1, 1, 1, 1],
                     [1, 1, 1, 1, 1, 1, 1],
                     [0, 1, 1, 1, 1, 1, 0],
                     [0, 0, 1, 1, 1, 0, 0]], bool)
    ghost = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool)

    n_pulses = len(pulse_t)
    n_shown = [0]
    black_from = climax + 1.6                    # static ends, screen goes dark
    reboot_from = black_from + 1.2
    resume_from = reboot_from + 3.6

    def draw_blips(tc, k):
        """Blips as the pulses have seen them.

        A contact shows at the position of the most recent pulse that has
        reached it, decaying until the next front refreshes it; the two
        pulses before that leave dim ghosts. Returns the nearest range shown.
        """
        nearest = None
        shown = set()
        n_shown[0] = 0
        for back in range(0, 4):
            j = k - back
            if j < 0:
                break
            for (i, r_m, y, t_seen) in pulse_seen[j]:
                if t_seen > tc:
                    continue                     # the front has not reached it
                x = int(round(ORIGIN_X + r_m * PX_PER_M))
                yi = int(round(y))
                if i not in shown:
                    shown.add(i)
                    n_shown[0] += 1
                    age = tc - t_seen
                    v = 1.0 if age < 0.12 else max(0.4, 1.0 - 0.3 * age)
                    stamp(dyn, halo, x - 3, yi - 3, v * 0.35)
                    stamp(dyn, blip, x - 2, yi - 2, v)
                    if nearest is None or r_m < nearest:
                        nearest = r_m
                else:
                    stamp(dyn, ghost, x - 1, yi - 1, 0.26 if back <= 1 else 0.13)
        return nearest

    def render(t, frame):
        tc = t % cycle
        dyn[:] = 0.0

        if tc < climax or tc >= resume_from:
            k = bisect.bisect_right(pulse_t, tc) - 1
            k = max(0, min(n_pulses - 1, k))
            # The sweep front and its wake. Front at r = speed*(tc - t_k) for
            # this pulse; the previous pulse's wake may still be fading too.
            for j in (k, k - 1):
                if j < 0:
                    continue
                age = tc - pulse_t[j]
                r_front = PULSE_SPEED_M * age
                if r_front > RANGE_M + 4:
                    continue
                d = r_front - R_m                          # >0 behind the front
                wake = np.exp(-d * 0.55) * (d >= 0)        # trailing glow
                front = np.exp(-(d * d) * 6.0)             # the bright edge
                np.maximum(dyn, (0.55 * front + 0.22 * wake) * (R_m <= RANGE_M + 0.3), out=dyn)
            nearest = draw_blips(tc, k)
            # Pulse LED beside the readout: flashes on fire.
            since = tc - pulse_t[k]
            led = max(0.0, 1.0 - since * 4.0)
            warm = min(1.0, (tc - resume_from) / 1.5) if tc >= resume_from else 1.0
            np.multiply(static, warm, out=lum)
            np.maximum(lum, box * warm, out=lum)
            if not args.no_readout:
                lum[19:21, READOUT_X + 2:READOUT_X + 4] = 0.2 + 0.8 * led
                if nearest is None:
                    txt = "--"
                    flash = 1.0
                else:
                    txt = "%2d" % int(min(99, math.floor(nearest + 0.5)))
                    flash = 1.0
                    if nearest < 3.0:                       # alarm blink
                        flash = 0.35 if int(tc * 6) % 2 else 1.0
                dx = READOUT_X + 3
                for ch in txt:
                    stamp(lum, digit_masks[ch], dx, 26, 0.95 * flash)
                    dx += 8
                stamp(lum, m_mask, READOUT_X + 19, 31, 0.45)
                # Contact count: one tick per blip seen by this pulse.
                n_seen = n_shown[0]
                for i in range(min(8, n_seen)):
                    lum[42 + (i // 4) * 3, READOUT_X + 3 + (i % 4) * 5:READOUT_X + 6 + (i % 4) * 5] = 0.6
            # Near the climax the whole picture starts to shudder.
            if tc > climax - 1.2:
                jitter = int(rng_frame(frame) * 3) - 1
                dyn[:] = np.roll(dyn, jitter, axis=1)
            np.maximum(lum, dyn * (1.0 - 0.85 * edge), out=lum)
        elif tc < black_from:
            # Static: the display tearing up. Deterministic per frame.
            noise = np.random.default_rng(int(tc * 60) + args.seed).random((H, W), dtype=f32)
            fade = 1.0 - (tc - climax) / (black_from - climax)
            lum[:] = noise * (0.25 + 0.6 * fade)
            band = int(((tc - climax) * 90) % H)
            lum[max(0, band - 2):band + 2, :] = 0.95
        elif tc < reboot_from:
            lum[:] = 0.0
        else:
            # Self-test banner; the sweep resumes on an empty corridor after.
            lum[:] = 0.0
            u = tc - reboot_from
            stamp(lum, banner1, W // 2 - banner1.shape[1] // 2, 22, 0.75 if u > 0.2 else 0.0)
            if u > 2.2:
                blink = 0.6 if int(u * 3) % 2 else 0.25
                stamp(lum, banner3, W // 2 - banner3.shape[1] // 2, 32, blink)
            elif u > 1.0:
                stamp(lum, banner2, W // 2 - banner2.shape[1] // 2, 32, 0.45)

        np.multiply(lum, scan, out=lum)
        idx = np.clip(lum * 255.0, 0, 255).astype(np.uint8)
        np.take(lut, idx, axis=0, out=out)
        return out

    return render


def rng_frame(frame):
    """A cheap deterministic hash of the frame index in [0, 1)."""
    x = (frame * 2654435761) & 0xffffffff
    return ((x >> 8) & 0xffff) / 65536.0


def main():
    ds.standalone(sys.modules[__name__], __doc__.split("\n", 1)[0], fps=30)


if __name__ == "__main__":
    main()
