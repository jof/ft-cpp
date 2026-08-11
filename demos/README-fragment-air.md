### air

![air](screenshots/air.png)

What is in the air outside, drawn as how far you can see through it. The wall
already had the weather, the fog, the wind and a satellite's view of the cloud
over the Bay, and not one of them said anything about particulates — which in
this city is the most visible environmental fact of the year. The difference
between a clear September afternoon and a smoke day is the thing everybody in
the shop notices, talks about and changes their plans for, and until this panel
it was the one thing the wall could not tell them.

So it is not a gauge. It is the view north from the roof, redrawn at the
visibility the current PM2.5 implies: the Marin hills behind, the downtown
towers, Potrero and the near warehouses, and a rooftop in the foreground with a
chimney and a water tank on it. On a clean day the whole depth of it stands out
crisp against a blue sky and the tower windows are lit. As the number climbs
the far layers dissolve into the airlight one after another and the panel goes
warm — tan, then amber, then the orange-brown that anybody who was here in 2020
recognises before they have read a single character. Somebody walking past
reads *the air is bad today* off the colour and off how much of the city is
missing, which is how they read it out of a real window.

**The extinction is arithmetic, not a mood.** Two lines do all of it:

    b_pm = 3 * PM2.5 + 10        extinction from particles, Mm^-1
    T(d) = exp(-b * d)           contrast a target keeps at d kilometres

The first is the IMPROVE mass scattering efficiency for fine particles — the
number every regulatory visibility calculation in the US is built on — plus a
Rayleigh floor for the air itself, which is why a perfectly clean day has a
visual range of 391 km and not infinity. The second is Beer's law; inverting it
through Koschmieder's 3912/b is where the meteorologists' "visual range" comes
from. Each depth plane sits at its real-ish distance and is drawn as `body*T +
airlight*(1-T)`, and that is the entire renderer. At 8 µg/m³ the Marin ridge
keeps 39% of its contrast and the towers 83%; at 150 the ridge is gone, the
towers are at 8% and the rooftop is still at 89%. None of that was tuned to
look right. It looks right because it is what the atmosphere does.

The four distances are the one place where a free parameter was spent
deliberately: 28 km, 5.5 km, 1.6 km and 250 m are roughly a factor of four
apart so that each plane drops out at a different, useful concentration. The
ridge goes at about 25 µg/m³, the towers at 137, Potrero at 477 and the rooftop
never. That gives four steps of legible bad instead of one binary, and it
guarantees the panel is never an empty rectangle.

**Fog is not smoke, and this is the panel where that had to hold.** `karl`
already owns fog, and a 6 µg/m³ foggy morning drawn orange would be the wall
claiming a fire, twice a week in July. Water scatters neutrally and looks white
and cool; smoke absorbs blue and looks orange and warm. So the fetcher stores
the model's own visibility diagnostic and the relative humidity beside the
particulates, and the demo splits the extinction in two: `b_fog = 3912/vis_km −
b_pm`, whatever is stopping the light that the particles cannot account for.
The airlight colour is then mixed between a cool grey and a PM2.5-driven ramp
in proportion, and the caption says FOG, SMOKE, HAZE or CLEAR. A foggy morning
and a smoke afternoon can hide the towers equally well and are 135 levels apart
in red-minus-blue, which is not a distinction anybody has to squint at.

Two things had to be done to the fog term to make it usable. It is **capped**,
at about 4 km of visual range from water alone: the model emits isolated hours
of 100 m visibility, which as extinction is 39 000 Mm⁻¹ and renders a uniform
white rectangle. And it is **smoothed over three hours and gated on humidity**,
because those isolated hours flashing past mid-sweep read as a rendering fault,
and because a 200 m visibility at 52% relative humidity is the diagnostic
having an opinion rather than fog. Both are compromises and both are in the
code with the reasoning next to them.

**It sweeps, because the trend is the point.** A number tells you the air is
bad; the shape tells you whether it is arriving or leaving. The panel dwells on
the present moment, runs back to 24 hours ago, sweeps forward through now into
tomorrow's forecast, and returns — and the headline follows the cursor,
labelled `-8H`, `NOW`, `+13H`. A big number over a picture of another hour
would be the worst thing this panel could do, so the label is drawn above the
age rather than below it and the sweep starts and ends on the present, which
means a segment cut short has still shown somebody today's number. The strip
along the bottom is the whole 48 hours at once: bar heights are hourly PM2.5,
colours are the six official US AQI categories, the forecast half is drawn
dimmer than the measured half, and the present moment is a bright rule.

**The AQI lags the PM2.5 and that is not a bug in either.** The US index is
defined on a 24-hour average, so the service's hourly `us_aqi` column is a
running quantity. Over a real day here it moved 54 to 60 while the hourly PM2.5
moved 8 to 16 — correlation 0.15 against the hourly figure and 0.90 against a
24-hour trailing mean of it. Both the headline and the strip's colour are
driven by the index so that they agree with each other and with every other air
quality map anybody has seen; the bar *heights* are the hourly mass, because
that is the thing with an hourly shape. When a plume arrives the bars rise
before the colour does. That is the index, not the panel.

**No day and night.** The scene is lit as daytime at 3 am as much as at 3 pm.
Adding a diurnal cycle would put a second and much stronger brightness signal
on the one axis the panel exists to carry, and "dark" would be read as "bad" by
everybody who did not stop to think about it. This is a diagram of visibility,
not a webcam.

**The data.** Open-Meteo, free and keyless, two endpoints an hour: the
air-quality API for `pm2_5, pm10, us_aqi, aerosol_optical_depth` and the
ordinary forecast API for `relative_humidity_2m, visibility`. One request each
gets the past and the forecast together, so the whole 49-hour window is two
round trips. `past_days` and `forecast_days` snap to whole days, so the request
covers five and the fetcher throws away everything outside now±24 h: about 6 kB
over the wire becomes a 2.2 kB record of roughly 250 numbers. Times are asked
for in UTC explicitly — the documented default is GMT but a default is not a
promise, and `timezone=` also decides where the day boundaries fall. The
coordinate comes from `ftsite`, never from the source. TTL three hours,
interval one hour; the model is revised hourly at best and a curve fetched two
hours ago is still very nearly the curve.

A surprise worth writing down: the two endpoints answer for **different grid
cells**. The chemistry model is CAMS at about 11 km and answered for 37.80,
−122.40 — Fisherman's Wharf, 4 km north of the building — while the forecast
model answered for 37.763, −122.413, half a mile away. Both are stored, because
"modelled for a cell containing most of the northeast quadrant of the city" is
the honest description of this number.

There is already a `wx-air-<site>` product a thousand lines up in `ftdata.py`
and this is deliberately not it. That one asks for `current=`: one instant,
five species, a number for `wx` to print in a corner. This one wants one
species and forty-nine hours of it, half in the future, because the panel is
about a trend arriving. Bolting `hourly=` onto the wx product would have made
every `wx` fetch forty times bigger for a series `wx` does not draw.

**Frame budget.** Every pixel's colour depends only on which depth plane is
visible there, which row it is on, and how its edge is antialiased — so
`build()` bakes one int32 index image and `render()` builds a small
(bodies × bodies × coverage × rows) colour table for the current extinction and
pulls the entire panel out of it with a single `np.take`. The table is 32 k
floats and a dozen numpy calls on tiny arrays; the frame is the gather, one add
of the drifting murk and the dither, and one store. Five whole-panel passes,
about twenty numpy calls. Quantising the edge coverage to four steps is what
collapsed two gathers and a blend into one; four steps on a one-pixel silhouette
is finer than the panel's own gamma can show. The tower lights and the aviation
beacon cost nothing per frame at all, because they are simply two more rows of
the same table at the towers' own distance — which is why they are swallowed by
the smoke along with the towers, rather than shining through it.

Measured over a full sweep on the desktop: **mean 0.27 ms, p95 0.46 ms, worst
frame 0.55 ms**, with `build()` at 3 ms. Against the calibration figure in this
tree — a demo at 0.3 ms here measuring 44 ms on the Pi while it was throttled to
600 MHz, call it 20 ms now that the clock is fixed — that scales to roughly
**18 ms mean on the wall's Pi 3**, inside the 20 ms target at 20 fps but not by
much. The p95 tracks the mean, so there is no periodic spike to be surprised
by. If it turns out marginal, the first thing to give up is the four-step edge
antialiasing, which halves the table and costs one silhouette pixel of
smoothness.

The murk drifts across at 23 columns a second and its amplitude follows the
extinction, so a clean day is still and crisp and a smoke day visibly moves.
The floor under that amplitude is not decoration: the drift is what guarantees
no two consecutive frames are identical while the sweep is dwelling on the
present, and a panel that holds one frame for half a second on a wall between
two animated demos reads as a crash. `caiso` learned the same lesson the same
way.

Records past the three-hour TTL still draw — a curve from breakfast is still
breakfast's curve — with the age and `STALE` on the panel. A record whose
window has *ended* is refused outright and says so, because a 49-hour picture
of the wrong 49 hours is worse than an empty rectangle. No record at all gets
the no-data card and the command that fixes it.

    python3 ftdata.py --once --only air
    python3 air.py --host 127.0.0.1
    python3 air.py --sweep 8              # hurry the sweep along
    python3 scripts/test-air.py           # 83 checks
    python3 scripts/test-air.py --shot-smoke /tmp/smoke.png   # a day to come

That last one matters. A panel whose entire point is what it looks like when
the air is bad cannot be reviewed on a clear afternoon, so the test script will
fabricate a plausible smoke day, a fog morning or a clean day into a scratch
cache and screenshot the panel reading it. The demo is not told; it reads the
cache it always reads.
