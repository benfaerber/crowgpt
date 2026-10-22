# What does an hour of pocket listening cost?

**2026-07-29** · Pixel 10 Pro (`blazer`), Android 16 `CP1A.260305.018` · unplugged,
screen off, 47% → 43% · 112 samples at 30 s · rolling buffer and pocket mic on

## Why

The last item of the recorder audit that needs neither a failure injected nor a
microphone plugged in — just a phone left alone. It decides whether pocket
listening is a feature or a warning, because a mode that eats a third of the
battery an hour cannot be armed on the way out of the door and forgotten.

Two things had to be measured rather than assumed: whether the microphone stays
genuinely open for an hour, read from audioflinger and not from the app's claim
about itself, and whether the foreground service survives Doze.

## Result

**Armable and forgettable. Listening survived the full hour, and the drain is
about 3.7% an hour.**

| | measured |
|---|---|
| charge used | **177.5 mAh** in 60.3 min (2312.5 → 2135.0) |
| rate | **172–192 mAh/h** (three estimates, below) |
| **hours to flat** | **25–28 h** from 4810 mAh usable |
| percent per hour | **3.6–4.0 %/h** (47% → 43%) |
| thermal status | **0 for all 112 samples** — never throttled |
| skin temp | 27.4–28.0 °C, against a first throttle step of **39.0 °C** |
| battery temp | 29.1 → **27.4 °C** — it cooled |
| CPU cores | 31–33 °C |
| resident set | 37.5 → 38.5 MB (+0.48 MB/h) |
| **mic genuinely open** | **112 / 112 samples** |
| **ListeningService up** | **112 / 112 samples**, pid 4106 unchanged |

**Listening was not reaped, and it survived deep Doze.** `dumpsys deviceidle get
deep` read `IDLE` during and after the hour, and batterystats tags the run's
percent steps `device-idle-on`. The app was in `FGS` process state when checked
at minute 40, which is presumably what spared it — sampled once, not tracked, so
the continuous evidence is the service column and not this. This is the finding
that would have voided the battery number, and it held.

**The rate is a range because the coulomb counter is not smooth.** It sat at
2210.0 mAh for 9.1 minutes and then stepped 27.5 mAh at once when percent
ticked; its 16 moves have a median of 10.0 mAh. So the counter quantises much
like percent does, and where a window ends relative to a jump moves the answer:

| estimate | mAh/h |
|---|---|
| least-squares fit over all samples | 171.5 |
| first minus last | 176.7 |
| percent steps × 48.1 mAh | 191.5 |
| batterystats step durations (independent) | ~171 |

The fourth is worth its own line because it does not use the coulomb counter at
all: the run's percent steps took 17m55s, 16m55s, 16m06s and 16m45s, averaging
16.9 min per point, or 171 mAh/h. Two instruments agreeing at the bottom of the
range is why the honest headline is "about 3.7%/h" and not a single decimal.

**Ignore `current_ua`.** Its median reads −291 mA, which would imply 291 mAh/h,
well above every other estimate. It is sampled during the adb wake this harness
itself causes, so it catches the phone at its busiest by construction. Recorded
because it is in the CSV, not because it measures the thing.

**Nothing got hot.** Skin held 11 °C below its first throttling threshold and the
battery *fell* 1.7 °C over the hour, which also argues the microphone is not
doing meaningful work — a phone burning 300 mA of CPU does not cool down.

**Memory is flat enough.** +0.48 MB/h with a 223 KB standard deviation over 87
distinct readings: a real but tiny upward drift, about 2 MB across a four-hour
session. Not worth acting on, worth re-checking if a run ever lasts all day.

## What this does not measure

**The marginal cost of listening.** 177 mAh/h is total device drain with
listening on, not the microphone's share. There is no listening-off control
hour, so the figure bounds pocket listening from above and does not isolate it.
The tempting comparison — an earlier `device-idle-off` step at 8m20s per
percent — is not a control, because that was the phone in use.

**Its own overhead.** Every 30 s the harness wakes the phone and runs six or
seven `dumpsys` calls over wireless adb. That cost is inside the 177 mAh. A
real pocket hour, unpolled, is cheaper by an unknown amount.

**Anything about the Pixel 8.** The brief called for the throwaway handset; the
recordist redirected to the daily phone, which was already armed and unplugged
at 47%. Read-only `dumpsys` sampling only, per CLAUDE.md. The trade was
favourable — a coulomb counter barely moves near 100%, and the Pixel 8 was at
100% and full — but a different SoC and battery means this number does not
transfer.

## The harness was measuring three things wrong

Caught before the run, by reading the dumps by hand first. Recorded because each
would have produced a confident wrong write-up rather than a gap:

- **The microphone check never fired.** It tested for `standby: 0`; this Android
  writes `Standby: no`. It would have logged `mic CLOSED` for all 112 samples and
  the write-up would have been "listening was reaped, battery number void" — the
  exact inversion of what happened. Now it requires an input thread out of
  standby *with an active record track owned by the app's pid*, because the dump
  always carries hotword threads, and because an app reaped while Assistant held
  the microphone would otherwise read as listening fine.
- **`cpu_c` read a stale cache** — the first `mType=0` match lands in
  `Cached temperatures:`, which reported `charging_therm` at 45 °C on a phone
  unplugged twenty minutes, and pinned `cpu_c` to a constant 58.000004 while the
  cores were at 31 °C. **That column is void for this run**; `thermal_sidecar.csv`
  carries the real series from minute 23, and `run.py` now reads the live HAL
  block. Its replacement had the same bug one layer down: `CoolingDevice{}`
  reuses the `mType` numbers, so an unanchored match read the GPU cooling level,
  4798000, as a skin temperature.
- **An adb dropout would have been reported as a reaping.** A wifi drop during
  Doze empties every column including `pidof`, and the loop treated a missing
  pid as "the app process is gone". There is now an `adb_ok` column and the
  early exit requires adb to answer first.

`current_now` was also absent from `dumpsys battery` on recent Pixels and now
comes from sysfs — which turned out not to matter, per above.

## What it changed

**No battery warning in the UI, and pocket listening ships as armable-and-
forgettable.** At 3.7%/h an eight-hour field day costs about 29% of the battery,
which is a thing you plan around rather than a thing that needs a dialog. The
warning that was on the table is decided against.

**The audioflinger mic check is now trustworthy and reusable.** The rest of the
recorder audit can assert "the microphone is genuinely open" instead of trusting
`isListening()`, and it is attributed to the app's pid rather than to any open
input thread.

**A control hour is now worth doing, and was not before.** Because the total is
low, the interesting question flipped from "is this affordable" to "how much of
it is even the microphone" — the same harness with listening off, same polling,
same handset. Filed in `FUTURE.txt`.

**It changed nothing about the thermal design.** There was a suspicion that an
hour of capture in a trouser pocket would throttle. It sat 11 °C under the first
threshold and cooled while doing it, on a phone in open air. Worth re-running
once inside an actual pocket before the null is trusted, since insulation is the
whole mechanism and this run did not test it.
