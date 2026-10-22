# mobile

The Cawtalker field app (React Native + Expo SDK 57, dev client). **Work in
progress.**

Phase 0 — *will React Native give us real control of the mic?* — is answered and
recorded under [Verified on device](#verified-on-device-pixel-10-pro--android-16-and-pixel-8--android-16).
The screen you get on launch is still the Phase 0 rig; the real app is being
built underneath it.

## Where the app is

| Layer | State |
|-------|-------|
| Capture (`modules/raw-audio`) | Working. 48 kHz mono 16-bit WAV, correct headers, BirdNET detects crows from it. |
| Local store + sync (`src/`) | **Built and tested** — `make test`, no device needed. |
| UI (`src/ui/`, `src/app/`) | **Built.** Capture list + record button, explicit Sync, detail with detected calls, settings. Typechecks; not yet seen on a device. |
| Native adapters (SQLite, file reads, GPS) | Not started. Each is a thin class behind an existing interface. |

The app root is `src/app/CawtalkerApp.tsx`. It is **not yet wired into
`App.tsx`**, which still renders the Phase 0 rig — switching over is a one-line
change once the mic investigation is finished with that file:

```tsx
export { CawtalkerApp as default } from "./src/app/CawtalkerApp";
```

Until the `expo-sqlite` adapter lands, `AppServices` builds an in-memory store,
so **captures do not survive an app restart**. The composition root is the only
place that knows this; nothing above it changes when the real adapters arrive.

### Local-first, sync on demand

The phone is the source of truth. A capture is written to the local store the
moment recording stops and is complete there — GPS, duration, the lot — whether
or not the field server has ever heard of it. Syncing is a *projection* of that
record onto the API, never the reverse.

Nothing runs on a timer or in the background: a sync happens when the user asks
for one. That makes interruption the normal case rather than the exceptional
one, so every step is resumable and safe to repeat:

1. create the capture — idempotent on a device-generated `client_uuid`
2. create the media slot — idempotent too, and it reports the byte count the
   server already holds
3. PUT the remaining bytes, ranged, chunk by chunk
4. optionally request analysis

Server ids and the confirmed byte offset are written back locally as they are
learned, so a sync that dies halfway resumes from the last confirmed chunk
rather than starting the file over. **The server's byte count always wins over
the local one** — after a lost response the phone can believe it sent bytes the
server never committed, and only the server knows what actually landed.

```
src/
  domain/types.ts             CaptureRecord, SyncState, client uuids
  data/CaptureRepository.ts   the store contract  (SQLite adapter goes here)
  net/HttpClient.ts           transport seam, retryable vs permanent errors
  net/FieldServerClient.ts    typed client for the fieldserver API
  sync/MediaSource.ts         ranged file reads    (file adapter goes here)
  sync/SyncEngine.ts          the on-demand sync
```

Storage, HTTP and file reads sit behind interfaces so the whole path runs under
plain node with no device attached:

```sh
make test     # 27 checks: resume-from-offset, no-duplicate-on-retry,
              # stale-local-offset correction, permanent vs transient failures
```

Those tests fake the *server* at the HTTP boundary rather than mocking the
client, so request building — URLs, bearer headers, `Content-Range` arithmetic —
is under test too.

## `modules/raw-audio` — unprocessed audio capture

An Expo local native module (Kotlin primary, Swift secondary). The whole reason it
exists: phones apply AGC / noise-suppression tuned for speech, which mangles faint
or structured bird calls. This module asks for a mic feed with none of that:

- **Android:** `AudioRecord` on the first source that opens — `UNPROCESSED`, else
  `VOICE_RECOGNITION`, which also carries no AGC/NS. Note the gate is *opening the
  source*, not the capability property: our Pixels decline to certify `UNPROCESSED`
  and hand it over anyway. See
  [the mic-path finding](#does-the-fleet-actually-get-an-unprocessed-mic).
- **iOS:** **a stub.** Every entry point throws. There was an
  `AVAudioSession(.measurement)` + `AVAudioEngine` implementation, but it had never
  been compiled and it hardcoded `unprocessed: true` — asserting the very thing
  this module exists to establish. It's in `git log` when someone has an iPhone to
  verify it on.

Capture never *assumes* which of the two it got. Each recording reads its own
record path back from the audio policy while it runs, so `stopRecording()` reports
the source that was actually selected and the effects that were actually attached.

Output is lossless 48 kHz mono 16-bit WAV — exactly what BirdNET's `to_wav()`
consumes, so the field server ingests it with no transcode.

### JS API (`import RawAudio from "./modules/raw-audio"`)

```ts
RawAudio.isUnprocessedSupported(): boolean        // does the device *certify* UNPROCESSED?
RawAudio.startRecording({ sampleRate?: 48000 }): Promise<string>   // -> WAV path
RawAudio.stopRecording(): Promise<RecordingResult> // {path,durationMs,sampleRate,bytes,
                                                   //  source,effects,unprocessed,...}
RawAudio.addAudioLevelListener(cb)                 // 0..1 RMS meter while recording
RawAudio.probeAudioSources(opts?): Promise<SourceProbeReport>      // Android diagnostic
```

`unprocessed` on the result is a **measurement** — no capture effects were attached
to the record path — and is `null` if the path couldn't be read back.
`isUnprocessedSupported()` is a different, weaker claim: whether the device
certifies the `UNPROCESSED` source at all. Don't read the second as the first.

The app requests `RECORD_AUDIO` from JS before `startRecording` (see `App.tsx`).

## Seeding test captures

`make seed` puts captures made from **real** corvid audio on the attached phone —
recordings drawn from the archive corpus in `data/`, transcoded to the same
48 kHz mono 16-bit WAV the recorder produces and written straight into the app's
local store, since the app is push-only and cannot be filled from the server.

They land in the `local` state, so tapping Sync afterwards is a real end-to-end
run: the files upload, the worker analyzes them, and actual detected calls come
back. Silence recorded off a desk cannot exercise that.

```sh
make seed                                      # 12 captures
make seed SEED_ARGS="--count 30 --radius 800"  # more, spread wider
make -C mobile seed-clear                      # remove seeded ones only
```

The scatter center comes from `MAP_CENTER_LAT` / `MAP_CENTER_LNG` — the same
variables the backend uses — read from the environment or from `mobile/.env`,
which is gitignored. Copy `mobile/.env.example` and fill it in. There is no
built-in location: the tool refuses to run rather than defaulting to somewhere,
because a home address is not something to bake into source.

## Toolchain

The Android SDK and a JDK 17+ are both needed, and neither is on `PATH` by
default here. Android Studio bundles a JDK 21, so:

```sh
export JAVA_HOME="$HOME/.local/share/android-studio/jbr"
export ANDROID_HOME="$HOME/Android/Sdk"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"
```

Worth putting in `~/.zshrc` — the system `java` is 11, which AGP 8 rejects.

`android/` and `ios/` are **generated** (`expo prebuild`) and gitignored; the
source of truth is `app.json` + `modules/`. Don't hand-edit them.

## Running it

Two different builds, and the difference matters:

```sh
make install      # STANDALONE release build — what you take into the field
make android      # dev client — needs Metro running on this machine
```

**Use `make install` before going out.** `make android` builds a dev client,
which fetches its JavaScript from Metro over USB or Wi-Fi; away from the laptop
it cannot start at all, which is how a recording session gets lost. The release
build has the bundle compiled in and needs no laptop, no Metro and no network.

Re-running `make install` updates in place — captures already on the phone and
the device's enrollment token both survive, because the package and signing key
don't change.

```sh
make devices                     # list attached phones
make install DEVICE=<serial>     # pick one when several are plugged in
```

It is signed with the debug keystore (the generated project already points the
release build type at it), which is fine for sideloading onto your own phones and
not fine for distribution.

```sh
npm install
```

Verified working: `assembleDebug` succeeds and `raw-audio` compiles clean against
Expo SDK 57 / RN 0.86.

### Testing capture

- **Your Android phone:** the real test. Enable USB debugging, plug it in, confirm
  `adb devices` lists it, then `npm run android`. *Probe mic sources* tells you what
  the OS actually gave you — which source was selected and what was attached to it.
  `isUnprocessedSupported()` only tells you whether the device certifies
  `UNPROCESSED`, which is a much weaker statement.
- **Emulator:** in AVD settings enable **"Virtual microphone uses host audio
  input"**. Fine for iterating on UI — but it says *nothing* about `UNPROCESSED`,
  which is a property of real mic hardware/HAL. Don't treat an emulator result as
  the go/no-go.

### Confirm the capture survives BirdNET

The Phase 0 screen has an **analyzer base URL** field and a *Send to BirdNET*
button, so the round trip can be done from the phone. Point it at the demo
analyzer and forward the port to the device:

```sh
adb reverse tcp:5002 tcp:5002     # demo analyzer
adb reverse tcp:5100 tcp:5100     # field server
```

Then `http://127.0.0.1:5002` resolves from the phone. Equivalent from a shell:

```sh
curl -F "audio=@capture.wav" http://127.0.0.1:5002/api/analyze
# or the full field-server flow (register -> capture -> PUT media -> analyze):
#   see ../fieldserver/api.rest
```

If your calls come back detected/typed, raw capture is validated and the framework
risk is retired — the rest is app.

## Verified on device (Pixel 10 Pro / Android 16, and Pixel 8 / Android 16)

- **`isUnprocessedSupported()` returns `false` on both phones** — and it turned out
  that this never meant what we read into it. `UNPROCESSED` opens fine on both and
  is now what capture actually runs on. See the next section.
- Capture is correct: 48 kHz mono 16-bit, byte count consistent with duration.
- `onAudioLevel` events are delivered, ~2×/sec, and the meter tracks them.
- The in-app *Send to BirdNET* round trip works and returns detections.

Two things the earlier Phase 0 write-up recorded as passing were in fact untested,
and both were broken when first executed — see git log for the fixes:

- The analyzer client threw `Unsupported FormDataPart implementation`. Expo's
  WinterCG `fetch` (SDK 54+) rejects React Native's `{uri, name, type}` part; the
  client now posts over `XMLHttpRequest`.
- The level meter never moved. It was linear over RMS, and field audio lives near
  the bottom of that range — a crow at -14 dBFS peak has a half-second RMS of
  ~0.01, i.e. a 1% bar. It is now scaled -60..0 dBFS.

The App.tsx "header check" line is **not** a check: `durationMs` is derived from
the same `totalPcmBytes` the byte count comes from, so the two can only ever
agree. The WAV header patch was validated externally (RIFF size = filesize-8,
data = filesize-44), not by that line.

## Does the fleet actually get an unprocessed mic?

**Not a *certified* one — but it gets the real thing, and capture now runs on it.**
The property and the source turned out to be two different questions, and only the
first one is a "no". Measured on a **Pixel 8 / Android 16** with
*Probe mic sources*; the Pixel 10 Pro has not been re-tested with the probe and
should be. All we know there is that `isUnprocessedSupported()` returned `false`,
which collapses `null` and `"false"` — so its raw property value is still unknown.

**1. The property is a real "no", not a misread.**
`getProperty(PROPERTY_SUPPORT_AUDIO_SOURCE_UNPROCESSED)` returns the string
`"false"` — not `null`. So `== "true"` is not quietly collapsing "unknown" into
"no" here; the device is explicitly declining. (That collapse is still a real
hazard in general — the CDD says a device *without* support must return `null` —
but it is not what is happening on this fleet.) The earlier note that the Pixel 8's
audio config never mentions `unprocessed` was wrong: `/vendor/etc/mixer_paths_aidl.xml`
defines dedicated `microphones (UNPROCESSED)` and `back-microphones (UNPROCESSED)`
paths. The original grep failed, it didn't come back empty.

**2. `UNPROCESSED` opens anyway, and the policy honours it.** `AudioRecord` reaches
`STATE_INITIALIZED` and `RECORDSTATE_RECORDING`, and the live
`AudioRecordingConfiguration` reports `audioSource=9` on `BUILTIN_MIC`. **Our gate,
not the device, is why that branch never ran.** This is expected: the property
advertises *certification* (CDD 5.11 — flat ±10 dB 100 Hz–7 kHz, calibrated
sensitivity), not existence. Declining to certify a response curve is not the same
as not having the source.

**3. Nothing is attached to our record path — measured, not inferred.**
`AudioRecordingConfiguration.getEffects()` / `getClientEffects()` come back **empty**
for `UNPROCESSED`, `VOICE_RECOGNITION`, `MIC` and `CAMCORDER`. The method is not
blind: on the same device `VOICE_COMMUNICATION` reports **AEC + NS** (`Fortemedia`,
`Pre Processing`) attached and enabled. That is the positive control — the read
detects effects when effects are there, and reports none on the path we record on.

**4. `UNPROCESSED` and `VOICE_RECOGNITION` are the same signal at different gains.**
Identical looping chirp (200 Hz→12 kHz, 300 ms on / 300 ms off) played to all five
sources, `mobile/tools/`:

| source | burst | gap (noise floor) | contrast | per-cycle drift |
|---|---|---|---|---|
| `UNPROCESSED` | −46.3 | −72.0 | **25.8** | 0.7 dB |
| `VOICE_RECOGNITION` | −29.1 | −55.0 | **25.9** | 0.8 dB |
| `MIC` | −15.9 | −45.3 | 29.4 | 0.9 dB |
| `CAMCORDER` | −73.7 | −93.2 | 19.5 | **9.3 dB** |
| `VOICE_COMMUNICATION` | −18.3 | −44.4 | 26.0 | 2.5 dB |

`UNPROCESSED` and `VOICE_RECOGNITION` have the **same burst-to-gap contrast** —
i.e. the same SNR — and frequency responses within ~1.5 dB of each other across
200 Hz–12 kHz. The whole difference between them is ~17 dB of gain. Both hold level
to ±0.2 dB cycle to cycle, which is what "no AGC" looks like; `CAMCORDER`, by
contrast, ramps 9 dB over its first two seconds, and `MIC` rolls off the top octave
harder (−25.7 vs −17.8 dB at 9.6–12 kHz).

The 17 dB gap also confirms the HAL isn't silently aliasing `UNPROCESSED` onto the
same path — it routes it differently, just at lower, uncompensated gain.

**Is that 17 dB costing us anything?** No. Shifting each source's *noise floor*
spectrum by its own gain offset makes `UNPROCESSED` and `VOICE_RECOGNITION` overlay
within ~1 dB in every band from 200 Hz to 23 kHz — same acoustic noise, same front
end, different gain. If `UNPROCESSED` were limited by its own electronics its
normalised floor would sit above; it doesn't. (`MIC`'s does diverge above 6.4 kHz,
by 3–9 dB, which is the shaped path showing itself.) So the 17 dB is free headroom,
not lost signal.

**5. AGC/NS can be disabled explicitly if a device ever attaches them.**
`AutomaticGainControl.isAvailable()` is `false` on this device — there is no AGC
implementation to attach. `NoiseSuppressor` and `AcousticEchoCanceler` are
available, and on a live session both can be created with `hasControl()` and
`setEnabled(false)` succeeding — including on `VOICE_COMMUNICATION`, where they
attach enabled and can be turned off. So the fallback mechanism exists and works;
we just don't currently need it.

### What changed, and what deliberately didn't

- `isUnprocessedSupported()` is **kept, and narrowed**. It was answering "is the
  capture unprocessed?" when it can only answer "does the device certify
  `UNPROCESSED`?". Worth keeping as an opportunistic upgrade — certification also
  buys a calibrated flat response, which is exactly what bioacoustics wants — but
  it is no longer what we report as the provenance of a recording.
- `stopRecording()` now reports `source`, `effects` and a measured `unprocessed`,
  read back from the audio policy *during* the capture. Corpus provenance is a
  measurement per file rather than a global assumption.
- **Capture now runs on `UNPROCESSED`**, with `VOICE_RECOGNITION` as the fallback,
  and the gate is whether the source *opens* rather than what the property claims.
  With no corpus collected yet there is nothing to stay level-consistent with, so
  the choice comes down to the measurements: same SNR, same response, flatter top
  octave, and **17 dB more clipping headroom**. That last one is the reason. Field
  peaks on `VOICE_RECOGNITION` measured −14 to −29 dBFS — a bird twice as close, or
  a louder call type, clips. Clipping is unrecoverable and silently poisons a
  training sample; the quantisation cost of the quieter path is nil, since its
  noise floor still sits ~29 dB above the 16-bit floor.
  Confirmed in the platform's own audio log (`dumpsys audio`):
  `rec start … src:UNPROCESSED pack:com.cawtalker.field`.
- The level meter's floor moved −60 → −80 dBFS to match. Left alone, the meter
  would have gone nearly dead again — the exact bug that was just fixed.

Two caveats worth keeping in mind:

- `getEffects()` reports *framework* effects, so processing done inside the HAL or
  DSP would not appear there. The A/B bounds that — a HAL-side AGC or gate would
  show up as moving gain or inflated burst-to-gap contrast, and neither source
  shows either.
- Preferring an **uncertified** `UNPROCESSED` is only as good as the device. Android
  is explicit that when the property isn't set there is *no guarantee* the signal is
  unprocessed — we verified it on this hardware, and other handsets could hand back
  something shaped. That is precisely why every capture measures its own path, and
  why an unfamiliar phone should be run through *Probe mic sources* below before it
  collects anything that matters.

To re-run this on new hardware (non-Pixel is still worth testing):

```sh
python3 tools/make_stimulus.py /tmp/stimulus.wav
paplay /tmp/stimulus.wav &            # any loudspeaker, moderate level
# Settings -> Diagnostics -> "Probe mic sources"; raise PROBE_MS for a longer window
adb exec-out run-as com.cawtalker.field cat cache/probe_report.json > /tmp/probe/report.json
for s in UNPROCESSED VOICE_RECOGNITION MIC CAMCORDER VOICE_COMMUNICATION; do
  adb exec-out run-as com.cawtalker.field cat cache/probe_$s.wav > /tmp/probe/probe_$s.wav
done
python3 tools/compare_sources.py /tmp/probe
```

## Notes

- `minSdkVersion 24` (UNPROCESSED needs API 24+); confirmed in the merged manifest.
- **iOS is a stub and has never been compiled** — Android is the only supported
  platform. The stub imports nothing but `ExpoModulesCore`, so there is little to
  be wrong, but it is still unverified: no Xcode on Linux. Whoever picks iOS up
  should expect to *write* it, not to fix it.

  Two things to carry over when they do. There is no iOS equivalent of
  `AudioRecordingConfiguration.getEffects()` — nothing reads back what is attached
  to the input chain — so `unprocessed` has to be established empirically with the
  chirp A/B in `tools/`, which is platform-independent. And an iOS Simulator cannot
  answer the question at all: `.measurement` mode's whole job is to change the
  processing chain on real hardware, exactly as the Android emulator says nothing
  about `UNPROCESSED`.
