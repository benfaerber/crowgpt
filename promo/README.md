# promo/

The public-facing page for the project. A compiled static bundle — no framework,
no API calls — built into `fieldserver/src/fieldserver/static/promo/` and served
by the field server at `/promo`, the same arrangement the dashboard uses. A
running fleet stays one process on one port.

```bash
make -C promo dev     # hot reload on :5174, needs nothing else running
make -C promo build   # into the field server's static/
make field            # builds it if missing, then serves it at :5100/promo
```

## Every number on it comes from `stats.json`

The page reads no store and takes no token, so a visitor never touches the
corpus. A promo page wired to the live database would silently restate itself as
the corpus changed, which is a worse promise than a number with a date attached.

So the numbers are still baked in at build time — but there is exactly one place
they are written down. `stats.json` holds every figure the page prints, and both
halves of the page read it:

- **the copy** carries `{{key}}` tokens, substituted into the HTML by a plugin in
  `vite.config.ts`. Build time, not runtime: the served HTML has real numbers in
  it, so view-source, a JS-less reader and a link preview all agree with the page.
- **the chart** imports it through `src/stats.ts`, where an AUC is a bar length
  as well as a caption.

A token with no matching figure **fails the build**. The thing that guards
against is a literal `{{labels.count}}` reaching cawtalker.org, which nothing
else here would catch.

```bash
make -C promo stats         # recount from the field server and the corpus
make -C promo stats-check   # report what is stale, write nothing, exit 1 if any
make -C promo build         # the numbers only reach the page through a build
```

### Counted, versus measured

`make stats` rewrites the figures marked `"auto"` — labels, context events and
the chip vocabulary, kept captures, species heads, the Xeno-canto tally, the
crow-tools segment count. Each is a query or a file count, in
`tools/build_stats.py`, one method per key.

Most figures are a number. `context.vocabulary` is a list: every active context
chip with its key, category, English label and how often it has been witnessed.
Its `text` is those labels joined, so `{{context.vocabulary}}` still works in
prose; `tags()` in `src/stats.ts` hands back the structure for anything that
wants to lay them out. The English comes from the `translations` table rather
than the seed constants, so an edited chip reads on the page the way it reads on
the phone.

Those event counts are worth more than most counts in this repo: context is
typed by a person watching, and nothing seeded contributes one. `context.tags_used`
is the exception to read carefully — it counts retired keys too, so it is not a
subset of `context.tags`. The vocabulary changed and old events kept their key.

The vocabulary is on the page as a hover, not a section. Three places mention
context chips and none of them showed one, which left "what a human saw" reading
like free text; `src/chip-tip.ts` turns any element with `.chips` into a term
that opens the list. It shows what the phone **offers**, not what has happened —
eight of the 23 have never come up, so those render faded and the panel says so.
Getting that distinction wrong reads `squirrel` as a sighting.

The rest are **typed by hand**, because they are a measurement somebody ran
rather than a row anything can count: the four AUCs, CrowGPT's call types, the
start date. The script never invents a value for one — it prints them with their
`source` every run, so a stale AUC is something you get told about rather than
something you notice on the live site.

A source that is missing is not a source that says zero. Run it on a machine
without the field database and those figures come back `unchecked` with their
existing values untouched.

### If you add a number to the page

Add the figure to `stats.json` first — `about` for what it means, `source` for
where it was measured — then reference it as `{{key}}`. Writing it straight into
the HTML is the failure this replaced: the old copy restated the label count in
three places, and they disagreed.

`captures.total` is in the file and deliberately **not** on the page. The corpus
is mostly seeded archive clips and test uploads, so a count over all captures is
a fact about the pipeline, not about crows — see the root `CLAUDE.md`. Only
`captures.kept` means anything about real recordings.

## What is deliberately *not* on it

**No BirdNET percentage for CrowGPT**, including the 39% / 81% pair that
`crowgpt/README.md` still carries. 0022 found those circular: BirdNET selected
CrowGPT's training corpus and then scored its output, and the model lands *above
real audio*, which is not plausible as realism. Every BirdNET-detection figure in
the project inherits that bias. The page says so in as many words rather than
quietly omitting it, because "here is why there is no number" is a stronger claim
than a number. If a listening test ever runs, that is the figure to put here.

**No ask for contributed recordings.** There is no TLS, enrollment is one shared
secret, and captures carry full-precision GPS — a shared dataset would export
contributors' home addresses to seven decimal places. That ask goes in when the
upload path can honestly carry it.

## Framing

The voice follows the root `README.md`: first person, the origin story
(feeding a murder of local crows), and the actual ambition stated as an
ambition — a crow → human → crow translator, with Crow Translate and CrowGPT as
its two halves. It is not a hedged classifier demo, because that is not what the
project is.

`phases/outreach.md` sets the one rule, and it holds under that voice: *"I'm
trying to decode my crows' calls, here's my first real result"*, never *"I
decoded crow language."* So the goal is described as a goal, and **Where it
actually is** is a section rather than a footnote — overclaiming burns
credibility with the exact community the project needs data from, and they are
the readers who notice first. If you rewrite the copy, keep the pairing: every
ambition on the page has a matching line saying how far off it is.

## Who visited

```bash
make -C promo traffic          # last 7 days, humans split from bots by user agent
make -C promo traffic DAYS=3
```

`tools/traffic.py` reads `CLOUDFLARE_API_TOKEN` from
`fieldserver/instance/secrets.env` and queries Cloudflare's GraphQL analytics a
day at a time. Retention is eight days on the free plan, so pull within a week
of any promo push or the numbers are gone. The token carries a client-IP
filter; when the home IP changes Cloudflare refuses it by location, and the
fix is in the dashboard under the token's settings.

## Order

Demos before explanation. The hero is one paragraph and three buttons, the
stat row sits directly under the photo, and the first two sections a visitor
scrolls into are the CrowGPT players and the app screenshots — then CawScout,
then the AUC figure. The goal, the two-problems split and the CawDex pipeline
come after, once there is something concrete to explain. Before 2026-09-11 the
page opened with three paragraphs and four sections of prose ahead of the first
thing that could be heard or seen. The stats stay up top on purpose: moving the
demos forward is not a reason to bury the numbers.

## Colours

Two series, blue and orange, from the data-viz reference palette — validated
against both the light and dark chart surfaces (lightness band, chroma floor,
CVD separation, normal-vision floor, contrast). Dark is the default theme and
light is a selected set of steps rather than an inversion. Re-validate before
changing either:

```bash
node scripts/validate_palette.js "#3987e5,#d95926" --mode dark --surface "#16181d"
node scripts/validate_palette.js "#2a78d6,#eb6834" --mode light --surface "#fbfaf8"
```
