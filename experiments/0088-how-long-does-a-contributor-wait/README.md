# 0088 — how long does a contributor wait?

2026-10-30. Asked while planning a hosted field server on a CPU VPS: from the
moment a contributor taps Sync, how long until BirdNET's verdict is on the
phone, and how long is a Crow Chat bout? 0087 answered the generation half;
this measures the analysis half on real kept captures and writes the whole
walkthrough down with numbers.

## Method

`run.py [capture_id ...]` runs the analysis worker's own four steps
(envelope, ffmpeg decode, BirdNET + call-type heads, quality) on the
capture's audio, resolved by server id through the database, with CPU
threads capped at four to stand in for a small VPS. Defaults to kept
captures 197, 158 and 153: a short, a medium and a long field recording.

```bash
CUDA_VISIBLE_DEVICES="" pipelines/representation/.venv-birdnet/bin/python \
  experiments/0088-how-long-does-a-contributor-wait/run.py
```

## Results, 2026-10-30, Ryzen laptop, 4 threads

Model load once per worker start: 0.7 s.

| capture | audio | FLAC on disk | envelope | decode | BirdNET | quality | total |
|---|---|---|---|---|---|---|---|
| 197 | 28 s | 0.63 MB | 0.1 s | 0.1 s | 1.9 s | 0.1 s | 2.1 s |
| 158 | 76 s | 2.01 MB | 0.1 s | 0.1 s | 2.9 s | 0.2 s | 3.2 s |
| 153 | 172 s | 4.56 MB | 0.1 s | 0.1 s | 6.3 s | 0.4 s | 6.9 s |

About one second of CPU per 25 to 30 seconds of audio, plus a second of
fixed cost. The worker polls every 2 s (`WORKER_POLL`).

Upload sizes, from the 29 kept captures: 48 kHz mono FLAC averages 3.5 MB
for 51 s, maximum 11.3 MB for two minutes. Video averages 7.3 MB for 15 s
and the default upload cap is 16 MB. The app uploads in 256 KB chunks,
sequentially, so a typical clip is 14 chunks: a second or two on Wi-Fi,
roughly 5 to 10 s on a middling LTE uplink.

## The walkthrough, with these numbers

1. Record a 30 to 60 s capture, flag it, tap Sync. Upload 1 to 10 s.
2. The server queues an analysis job; the worker claims it within 2 s.
3. BirdNET and the heads take 2 to 3 s. Status flips to analyzed.
4. The app fetches the analysis on its next look at the capture. Verdict on
   the phone 5 to 15 s after Sync, nearly all of it upload.
5. Crow Chat, if offered: 10 to 20 s per bout on CPU (0087), plus a 2 s
   model load when the worker has been idle long enough to drop it.

Throughput: one worker on four cores handles a clip every few seconds, so a
thousand 30 s contributions a day is under an hour of CPU. Video is a
storage and bandwidth question, not a compute one.

## What it changed

Confirms the hosting plan: a CPU VPS gives contributors a verdict within
seconds of upload, and upload itself is the only wait a contributor will
notice. Two cores for the API and worker is enough to start; the first
thing to raise under load is worker count, not GPU.
