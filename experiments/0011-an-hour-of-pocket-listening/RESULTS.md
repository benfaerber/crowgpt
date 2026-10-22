# What does an hour of pocket listening cost?

## Overview

The field app has a pocket-listening mode — phone in a pocket, screen off, microphone open, waiting for crows — and this experiment measured what an hour of it costs the battery, and whether Android quietly kills the microphone or the service along the way. A Pixel 10 Pro was left unplugged for an hour while a harness sampled it every 30 seconds, reading the microphone's state from the audio system itself rather than trusting the app's claim about itself. The answer: the mode is armable and forgettable. Listening survived the full hour, including deep Doze, the drain is about 3.7% of battery per hour (25–28 hours to flat), and the phone never came close to thermal throttling. A battery warning that had been on the table for the UI was decided against.

## In depth

### Setup

2026-07-29, Pixel 10 Pro (`blazer`), Android 16 `CP1A.260305.018`, unplugged, screen off, battery 47% → 43%. 112 samples at 30-second intervals, rolling buffer and pocket mic on. Two things had to be measured rather than assumed: whether the microphone stays genuinely open for an hour (read from audioflinger, not from the app), and whether the foreground service survives Doze.

The brief called for the throwaway Pixel 8, but the recordist redirected to the daily phone, which was already armed and unplugged at 47%. Read-only `dumpsys` sampling only. The trade was favourable — a coulomb counter barely moves near 100%, and the Pixel 8 was at 100% and full — but a different SoC and battery means this number does not transfer to the Pixel 8.

### Results

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

**Listening was not reaped, and it survived deep Doze.** `dumpsys deviceidle get deep` read `IDLE` during and after the hour, and batterystats tags the run's percent steps `device-idle-on`. The app was in `FGS` process state when checked at minute 40, which is presumably what spared it — sampled once, not tracked, so the continuous evidence is the service column. This is the finding that would have voided the battery number, and it held.

### Why the rate is a range

The coulomb counter is not smooth: it sat at 2210.0 mAh for 9.1 minutes and then stepped 27.5 mAh at once when percent ticked; its 16 moves have a median of 10.0 mAh. Where a window ends relative to a jump moves the answer:

| estimate | mAh/h |
|---|---|
| least-squares fit over all samples | 171.5 |
| first minus last | 176.7 |
| percent steps × 48.1 mAh | 191.5 |
| batterystats step durations (independent) | ~171 |

The fourth estimate does not use the coulomb counter at all: the run's percent steps took 17m55s, 16m55s, 16m06s and 16m45s, averaging 16.9 min per point, or 171 mAh/h. Two instruments agreeing at the bottom of the range is why the honest headline is "about 3.7%/h" and not a single decimal.

`current_ua` was ignored deliberately: its median reads −291 mA, which would imply 291 mAh/h, well above every other estimate — but it is sampled during the adb wake the harness itself causes, so it catches the phone at its busiest by construction.

### Thermals and memory

Nothing got hot. Skin held 11 °C below its first throttling threshold and the battery fell 1.7 °C over the hour, which also argues the microphone is not doing meaningful work — a phone burning 300 mA of CPU does not cool down. Memory drifted up +0.48 MB/h with a 223 KB standard deviation over 87 distinct readings — about 2 MB across a four-hour session, not worth acting on, worth re-checking if a run ever lasts all day.

### What this does not measure

- **The marginal cost of listening.** 177 mAh/h is total device drain with listening on, not the microphone's share. There was no listening-off control hour, so the figure bounds pocket listening from above. An earlier `device-idle-off` step at 8m20s per percent is not a control, because that was the phone in use.
- **The harness's own overhead.** Every 30 s it wakes the phone and runs six or seven `dumpsys` calls over wireless adb, and that cost is inside the 177 mAh. A real pocket hour, unpolled, is cheaper by an unknown amount.
- **Anything about the Pixel 8**, as noted above.
- **An actual pocket.** The thermal null was measured on a phone in open air; insulation is the whole throttling mechanism, so the null should be re-run inside a trouser pocket before it is trusted.

### The harness was measuring three things wrong

Caught before the run, by reading the dumps by hand first. Each would have produced a confident wrong write-up rather than a gap:

- **The microphone check never fired.** It tested for `standby: 0`; this Android writes `Standby: no`. It would have logged `mic CLOSED` for all 112 samples and concluded "listening was reaped, battery number void" — the exact inversion of what happened. It now requires an input thread out of standby with an active record track owned by the app's pid, because the dump always carries hotword threads, and because an app reaped while Assistant held the microphone would otherwise read as listening fine.
- **`cpu_c` read a stale cache** — the first `mType=0` match lands in `Cached temperatures:`, which reported `charging_therm` at 45 °C on a phone unplugged twenty minutes, and pinned `cpu_c` to a constant 58.000004 while the cores were at 31 °C. That column is void for this run; `thermal_sidecar.csv` carries the real series from minute 23, and `run.py` now reads the live HAL block. Its replacement had the same bug one layer down: `CoolingDevice{}` reuses the `mType` numbers, so an unanchored match read the GPU cooling level, 4798000, as a skin temperature.
- **An adb dropout would have been reported as a reaping.** A wifi drop during Doze empties every column including `pidof`, and the loop treated a missing pid as "the app process is gone". There is now an `adb_ok` column and the early exit requires adb to answer first.

`current_now` was also absent from `dumpsys battery` on recent Pixels and now comes from sysfs — which turned out not to matter.

### What it changed

- **No battery warning in the UI; pocket listening ships as armable-and-forgettable.** At 3.7%/h an eight-hour field day costs about 29% of the battery, which is a thing you plan around rather than a thing that needs a dialog.
- **The audioflinger mic check is now trustworthy and reusable.** The rest of the recorder audit can assert "the microphone is genuinely open" instead of trusting `isListening()`, attributed to the app's pid rather than to any open input thread.
- **A control hour is now worth doing, and was not before.** Because the total is low, the interesting question flipped from "is this affordable" to "how much of it is even the microphone". Filed in `FUTURE.txt`.
- **Nothing changed about the thermal design.** The suspected pocket throttling did not appear — but the run did not test an actual pocket, so the null is provisional.
