# fieldserver

The Cawtalker **field server** — the command-and-control + ingest API for the
crowdsourced recordist fleet. Field devices pull their config (labels,
instructions, taxonomy, translations) from here and push captures, media, and
human labels back. Pairs with a separate inference worker (runs in the BirdNET
venv) that analyzes uploaded audio.

One SQLite file, one store per table, assembled by a Flask app factory
pattern. See `../phases/` for the plan, `../phases/data-collection.md` in
particular.

```bash
make field                # from the repo root: dashboard build + server + worker
make dev                  # from this directory: the same server + worker
uv run fieldserver        # server only, loopback (FIELD_HOST/FIELD_PORT override)
```

`make field` binds all interfaces and prints the LAN address, so phones reach it
over Wi-Fi rather than only over USB via `adb reverse`. That address goes in the
app's Settings. There is still no TLS, so keep it to a network you trust, or set
`FIELD_HOST=127.0.0.1` for loopback only.

## Two secrets

They grant different things, so they are deliberately not the same string:

| Variable | Default | Grants |
| --- | --- | --- |
| `FIELD_ENROLL_TOKEN` | `dev-enroll` | join the fleet; push and read **your own** captures |
| `FIELD_OPERATOR_TOKEN` | `dev-operator` | additionally `/api/fleet/*` — **every** device's captures |

The defaults are for loopback, where you already have to be on this machine.
**The server refuses to bind anything else while either is still at its
default** — off loopback they are published constants, and anyone who can read
this repo could otherwise enroll as an operator and pull the whole corpus.

`make field` mints real ones for you on first run and stores them in
`instance/secrets.env` (gitignored). They persist across runs deliberately: the
enrollment token is typed into the phone's Settings by hand, and one that
changed per run would mean re-enrolling before every session. To see them again:

```bash
make -C fieldserver secrets
```

- `GET /api/health` — liveness + current config version.
- `GET /api/config?locale=de&since=<v>` — the versioned, localized config the
  fleet pulls (304 when `since` is current). The C2 seam: publishing a label
  bumps the version and the whole fleet picks it up on next fetch.

`api.rest` is a chained smoke test of the whole flow (enroll → capture → upload →
analyze → label → annotate); run it against a live server.

## Operator dashboard

`http://127.0.0.1:5100/` — fleet overview, capture list, and a per-capture detail
panel with playback, detected calls, human labels, and observations. Rows are
linkable (`/#capture-12`).

Sign in with the **operator token** on the dashboard's own sign-in screen —
`POST /api/operator/session` exchanges it for a bearer token behind the
scenes. (This replaced the old advice to mint a device with curl and paste
its `device_token`, which was a trap people actually fell into; the exchange
exists so nobody has to.)

The `/api/fleet/*` endpoints behind it are read-only and operator-gated (403 for a
normal contributor device). Without a matching `operator_token`, asking for
`is_operator` is a 403 — the flag is granted, not claimed.

## Two kinds of ground truth

Captures carry both, and they are deliberately not the same field:

- **Labels** (`/api/captures/<id>/labels`) — a call region tagged from the
  server-driven preset vocabulary. A closed set, tappable one-handed in the
  field, and the *only* thing `export_manifest.py` feeds to training.
- **Observations** (`/api/captures/<id>/observations`) — unconstrained prose
  written after the fact ("Edgar is alone, cawing and searching — I think he's
  calling the other four home"). Editable, several per capture, optionally
  transcribed from a voice memo (`"source": "voice"`).

Observations don't train anything directly. They exist to explain a confusing
prediction after the fact, and to surface which situations recur often enough to
deserve a preset — at which point promoting one is a config push, not an app
release.

Since then the evidence has grown three more shapes, each with its own store
and routes: **context events** (what a human witnessed during a specific
call), **sightings** (crows seen but not necessarily recorded, offset in time
from the capture), and **capture merges** (which captures were folded into
which — both copies kept so a merge stays reversible).

## Environment

| Variable | Default | Meaning |
| --- | --- | --- |
| `FIELD_DB` | `instance/field.db` | the SQLite file to serve |
| `FIELD_HOST` / `FIELD_PORT` | `127.0.0.1` / `5100` | where to bind (`make dev` binds `0.0.0.0`) |
| `FIELD_ENROLL_TOKEN` / `FIELD_OPERATOR_TOKEN` | dev defaults | the two secrets above |
| `FIELD_MAX_UPLOAD_MB` |  `16` | per-request upload ceiling |
| `FIELD_LAT` / `FIELD_LON` | unset | fleet home ground, for analyzing captures with no GPS of their own (browser uploads); unset means no occurrence filter rather than a guess |
| `WORKER_POLL` | `2` | worker poll interval, seconds |

Data (the fleet DB and uploaded media) lives under `instance/` and is gitignored.
