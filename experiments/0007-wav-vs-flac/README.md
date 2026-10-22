# 0007 — WAV vs FLAC

**Question.** Storage is the only cost in this project that grows. Would
storing FLAC instead of WAV be lossless on *this* audio, and how much would it
actually save?

Two questions in that order, because the second only matters if the first is
yes. A corpus is a measurement instrument: 0004 showed detection confidence
collapsing from 0.98 to 0.07 as street noise rose, so a format that altered the
waveform even slightly would move numbers nobody would think to re-check.

**Method.** Every complete audio file in the corpus — 77 files, 118 MB —
encoded with ffmpeg at compression levels 5, 8 and 12. Losslessness checked by
decoding both the original and the FLAC to raw signed 16-bit PCM through the
same tool and comparing SHA-256 of the samples, so a WAV header differing by a
LIST chunk is not mistaken for a loss. `run.py`, resolved through the database.

## Answers

**Lossless: 77 of 77 files decode to bit-identical samples.** Not "sounds the
same" — the same numbers. Every measurement downstream is unchanged by
construction, which is the only standard worth accepting here.

**It saves far more than the brochure says, because this audio is quiet.**

| | share of WAV | saved |
|---|---|---|
| Kept — real field recordings (n=4) | **22.4%** | 77.6% |
| Seeded archive clips and test uploads (n=73) | 40.2% | 59.8% |
| Everything | 38.2% | 61.8% |

Published FLAC ratios are measured on music, which is loud and dense. A crow
ten metres up peaks around -30 dBFS with long quiet stretches between calls,
and quiet audio carries fewer bits of entropy per sample. The seeded clips are
the control and they behave like ordinary recordings; the field recordings
compress nearly twice as hard.

**Level 8 is the setting.** Level 12 costs 3.5× the CPU (189 ms vs 54 ms per
file) to save another half a percentage point.

| level | share of WAV | encode |
|---|---|---|
| 5 | 38.9% | 42 ms |
| 8 | **38.2%** | 54 ms |
| 12 | 37.7% | 189 ms |

**Decoding is slightly faster than WAV** — 0.0018 vs 0.0020 seconds per
audio-second. Less to read off the disk more than pays for the decompression,
so the analyzer gets marginally cheaper rather than more expensive.

**Caveat worth stating plainly:** four kept captures is four. The 22.4% is a
real measurement of real field audio and the mechanism is not in doubt, but the
precision is not there yet. Re-run this once there are thirty of them; the
number to watch is whether recordings made closer to the birds — or with a
directional mic — drift toward the seeded clips' 40%.

## What it changed

**The corpus is now stored as FLAC** (applied the same day). It is free in every direction measured:
identical samples, faster decode, one ffmpeg flag. There is no trade-off to
weigh, which is rare enough to be worth saying.

**Per contributor per year, at two captures a day: 2.39 GB → 0.54 GB.** That is
the number the whole hosting question turns on.

**It postpones the NAS by years.** 0008 in TODO.txt put the threshold for
tiering audio to a home NAS at about 1 TB, on the grounds that below that,
object storage is cheaper than the electricity. At 0.54 GB per contributor-year
that threshold is now roughly 1,850 contributor-years away — a thousand people
recording for eighteen months. The NAS is no longer a thing to plan for; it is a
thing to revisit if this ever gets big, and the plan can be deleted if it does
not.

**It changes the per-user cost estimate by 4.4×:** roughly $0.007 → $0.0016 per
contributor per month on object storage in year one. The fixed ~$5 VPS now
dominates until well past a thousand users.

**One thing to get right when implementing it:** `media.sha256` currently hashes
the stored file. Re-containering the same audio changes that hash while
changing nothing about the recording, so the integrity check that a VPS→NAS
mover would depend on needs to be a hash of the *samples*, not of the file.
This experiment's `pcm_digest` is that hash, and it is four lines.

**Not measured, and deliberately not:** lossy formats. Opus at 64 kbps would be
twenty times smaller and is the obvious question, but a training corpus that has
been through a psychoacoustic model is one where nobody can ever separate what
the crow did from what the codec discarded. FLAC being free makes the question
moot anyway.

**Also worth a look later:** encoding on the phone before upload would cut field
data use by the same 4.4×, which matters on mobile data. Android has a FLAC
encoder in MediaCodec. Not needed yet — the recorder writes WAV and the phone
has room — but it is the same win applied to bandwidth.

## Afterwards

Applied to the live corpus the same day: 77 files, **118 MB → 45 MB, 62%
saved**, every original moved to `instance/media-originals/` rather than
deleted. The stronger end-to-end check came after: BirdNET run over capture 88
as FLAC and as its original WAV returns **byte-identical JSON** — same
detections, same species, same confidences to the last decimal. Bit-exact
samples imply that, but it is worth having seen rather than argued.
