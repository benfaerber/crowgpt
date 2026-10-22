"""The fleet vocabulary's seed data, and the design record of why each entry exists.

Data only — every constant here is what a fresh database gets seeded with, and
what `ConfigStore._seed_and_reconcile` reconciles an old database towards. The
store itself lives in config_store.py; this file is the part you read when the
question is "why is there a begging class" rather than "how does the version
bump work". The retirement essays between the entries are the vocabulary's
history and stay with the data they explain.
"""

# Begging is the odd one out: a developmental category (juvenile) rather than a
# functional context. It used to map down to "call", which put 307 acoustically
# distinctive crow-tools segments into the largest, vaguest class — and the
# training side disagreed anyway, dropping begging outright. It is its own class
# now, so the phone, the corpus, and the heads finally mean the same thing by it.
CORE_CLASSES = ["alarm call", "begging", "call", "flight call", "song"]

# One colour per core class. Every label inherits its core's, so a field label
# added later ("mobbing") reads as the alarm it maps to without anyone picking a
# colour for it — and both clients resolve through this rather than each keeping
# a palette of their own.
CORE_COLORS = {
    "alarm call": "#f27070",
    "begging": "#efb057",
    "call": "#6ea8fe",
    "flight call": "#6bd28a",
    "song": "#c58af9",
}

# (key, core_mapping) — the CORE classes themselves plus operator-defined field
# labels that map down to them. Seeded once; the operator adds more at runtime.
# (key, core_mapping) — the CORE classes plus operator-defined field labels that
# map down to them. A label whose core is None trains nothing: it is a judgement
# about the *detection* rather than about the call, and the export skips it by
# construction rather than by a filter someone has to remember.
SEED_LABELS = [
    ("alarm call", "alarm call"),
    ("begging", "begging"),
    ("call", "call"),
    ("flight call", "flight call"),
    ("song", "song"),
    ("mobbing", "alarm call"),
    ("scold", "alarm call"),
    ("contact call", "call"),
    ("rattle", "call"),
    # The model heard a crow here and there was not one. Worth recording rather
    # than retracting: a retraction says "ignore this", while this says "the
    # detector was wrong here", which is exactly what improves precision.
]

# Judgements about a *detection* rather than call types. They are real, storable
# answers — "the model heard a crow and there wasn't one" is precisely what
# improves precision, and retracting throws that information away — but they
# must never become a class the model tries to predict from audio.
#
# A separate flag rather than a null core_mapping: the column is NOT NULL in
# every database already out there, and `CREATE TABLE IF NOT EXISTS` cannot
# change that. A design that cannot migrate is not a design.
NON_TRAINING_LABELS = [
    ("not_a_crow", "Not a crow", "Keine Krähe"),
    ("unsure", "Can't tell", "Unklar"),
]

# What was happening while the bird called — the other axis. A call type is what
# the crow said; a context is what a human witnessed.
#
# Two things are being recorded, and they are independent: what the *world* did
# (a dog appeared, someone put food down) and what the *birds* did (three sat
# still, one flew off). Both can be true at once, so they live in separate
# groups rather than competing for one slot. Collapsing them is how "nothing
# obvious" ends up meaning "the crows didn't move" in one recording and "nothing
# happened" in the next.
#
# Categories are deliberately *descriptive*, never interpretive. An earlier
# version filed "human walks through" under `threat`, which answers the question
# the corpus exists to ask — and got it wrong for a recordist the birds know,
# where a human walking through is a food cue. Record the event; let the
# co-occurrence say what it meant.

# The field guide, in the order somebody meets it.
#
# `using` is about the app and can be learned in a minute. `birds` is what takes
# a season, and is the part worth writing down carefully — a contributor who
# cannot tell a fledgling from an adult will record both and label neither, and
# no amount of audio fixes that afterwards.
SEED_GUIDE = [
    ("what_this_is", "using"),
    ("press_after", "using"),
    ("what_to_record", "using"),
    ("silence_counts", "using"),
    ("say_what_you_saw", "using"),
    ("how_close", "using"),
    ("fledgling_or_adult", "birds"),
    ("begging", "birds"),
    ("alarm_or_scold", "birds"),
    ("families", "birds"),
    ("dont", "birds"),
]

SEED_CONTEXTS = [
    ("dog_visible", "animals"),
    ("cat_visible", "animals"),
    ("raptor_overhead", "animals"),
    ("squirrel", "animals"),
    # ("human_approaching", "people") — retired, and ("human_passing", "people")
    # and ("human_known", "people") with it. They named an action and left the
    # actor out, which is the one thing this vocabulary most needed to record:
    # two people walked a sidewalk past the same birds, and the crows had met
    # exactly one of them. The three tags wrote that identically to one person
    # walking past alone. Replaced by the four below, where the subject is part
    # of the event rather than a chip floating next to it.
    #
    # 41 events still carry them on captures 69, 88, 100, 103, 104 and 105, and
    # they keep meaning what they meant — "a human did this, subject not
    # recorded" — which is a true statement about July 2026. Nothing in analysis
    # joins context_defs, so those rows keep counting under their old names.
    # They are evidence, not mistakes, and rewriting them in SQL would fabricate
    # the flagship variable from a guess.
    #
    # Retired only after the captures worth re-tagging had been re-tagged. A
    # retired key renders no chip at all, so its existing uses go invisible and
    # unremovable from the phone the moment it goes inactive — and the POST route
    # refuses inactive keys, so they cannot be re-added either. Anything that
    # retires a context key inherits that ordering.
    #
    # The subject, carried by the verb rather than floating beside it.
    #
    # `human_known` said *someone* familiar was here and left you to guess who
    # did the walking. On a recording with two people in it that guess is the
    # whole measurement: a woman these birds had never met walked the sidewalk
    # five feet ahead of a recordist they feed weekly, and the crows were angry
    # at her and calm at him. Three unattached tags recorded that identically to
    # the same recordist walking past alone.
    #
    # So the relationship is part of the event, not a chip next to it. Multi-select
    # cannot bind one chip to another — with two humans in frame, "stranger" plus
    # "known" plus "approaching" plus "passing" is four independent booleans and no
    # way to say which adjective went with which verb. `stranger_passing` +
    # `known_approaching` on one span needs no such binding.
    #
    # The subject axis stops at these two verbs, deliberately. It applies where a
    # human's history with these birds changes what the event *is*. A mower is a
    # mower whoever pushes it, so `loud_worker`, `person_shouting` and `vehicle`
    # stay subject-neutral; two verbs times two subjects is four keys and no
    # combinatorial drift.
    #
    # One chip per human in the scene, the recordist included: the chip records
    # an event and when it happened, observer_role records standing. That is why
    # both can be true at once and neither is redundant — on the capture above,
    # `stranger_passing` and `known_passing` on one span say two people walked
    # past and the birds had met one of them, which is the entire observation.
    #
    # What `human_known` was doing instead was restating standing, once per span,
    # nine copies deep on some captures, of a fact the capture row already held —
    # without ever saying which of the two people did the walking.
    #
    # `known_*` is the marked case: tag it when there is positive reason to think
    # these birds have history with that person. "No idea" is a stranger. That
    # collapses a third value on purpose, and it errs the safe way — a familiar
    # human filed as a stranger dilutes the difference and can never invent one.
    ("stranger_approaching", "people"),
    ("known_approaching", "people"),
    ("stranger_passing", "people"),
    ("known_passing", "people"),
    ("vehicle", "people"),
    # A human is not one stimulus. Someone walking past is a moment; someone
    # running a mower is a wall of noise that stays for an hour and disturbs the
    # ground the birds forage on. Experiment 0008 had to infer a lawnmower off
    # the spectrum after the fact because nothing recorded that it was there.
    #
    # Deliberately about the machinery rather than the trade: mowing, blowing,
    # digging and hammering are one thing to a crow, and a tag per job would be
    # four tags with three examples each.
    ("loud_worker", "people"),
    # What a person is doing, never who they are. Shouting and erratic movement
    # are what a crow can perceive and what it reacts to; housing, sobriety and
    # the rest are neither observable from a recording nor anything the bird
    # responds to. A tag naming a kind of person would be recording a judgement
    # about a human as though it were an observation about a bird — and this
    # corpus already keeps inferences out of the columns meant for evidence.
    ("person_shouting", "people"),
    ("human_gives_food", "food"),
    ("foraging", "food"),
    ("feeding_young", "food"),
    ("crow_arrives", "crows"),
    ("crow_departs", "crows"),
    # ("several_birds", "crows") — retired. A head count on the capture says
    # this and says how many, so the tag could only ever disagree with it.
    # The translation below stays: two events were tagged with it before it
    # went, and they are evidence rather than a mistake.
    ("group_gathers", "crows"),
    # ("mobbing_together", "crows") — retired. Interpretive, which is the one
    # thing this vocabulary is not allowed to be: it names the conclusion, and
    # `raptor_overhead` + `group_gathers` + `crows_agitated` record the event it
    # was drawn from. Recording those lets the co-occurrence say it was mobbing;
    # recording this answers the question the corpus exists to ask, which is the
    # `threat` mistake described below in a different costume. Retired while it
    # was still free — nothing had been tagged with it, so unlike several_birds
    # there is no evidence to keep readable. The translation stays anyway:
    # deleting it from the databases out there would need its own migration for
    # no benefit. `mobbing` remains a *call type*, which is a different axis and
    # a real acoustic class (experiments/0012).
    ("juvenile_present", "crows"),
    # What the birds did, as opposed to what happened to them.
    ("crows_still", "crows"),
    ("crows_agitated", "crows"),
    # The caller, as opposed to everyone else. Context already hangs off a
    # label, so the calling bird is identified — what was missing is what *it*
    # did while the others moved. A bird that holds position while the group
    # leaves is doing something different from one that leaves with them, and
    # `crow_departs` + `crows_still` could only ever say "some left, some
    # stayed", losing the half that matters.
    #
    # Named for the caller and not for a receiver or a listener on purpose:
    # you can see a bird react, you cannot see that it heard, and a tag that
    # records an inference as an observation is the mistake this project
    # already avoids between detections and labels.
    ("caller_stays", "crows"),
    ("caller_leaves", "crows"),
    ("nothing_obvious", "quiet"),
]

# What the recordist was *to these crows* at the moment of recording.
#
# Per capture, not per person: you are a stranger in a new territory and a
# feeder on your own block on the same morning, and a contributor-level field
# would flatten exactly the variable that matters. A crow that knows you feeds
# it behaves nothing like one meeting you — same bird, same street, different
# recording — so without this the corpus contains two populations filed as one.
#
# Ordered by how much history the birds have with the observer, least to most,
# because that is the axis the behaviour actually moves along.
SEED_OBSERVER_ROLES = [
    "stranger",
    "known_passerby",
    "feeder",
    "feeding_now",
    "handler",
]

# What kind of bird made the call, by what a recordist can see from the ground.
#
# Individuals are not identifiable without bands and there are none, so this is
# standing in the family rather than identity — which is also the variable the
# 2026 León paper found its only social-category-specific calls in. The Poe
# family: two parents, a yearling brood guard (Edgar), two fledglings.
#
# Ordered youngest to oldest, because that is the axis the voice moves along:
# begging calls are developmental precursors whose structure converges on the
# adult call types as the bird ages, so a fledgling and a parent are the two
# ends of a continuum rather than two unrelated categories.
#
# `adult_unsure` is load-bearing. Telling a yearling helper from a breeding
# parent at twenty metres is hard, and a picker with no way to say "an adult,
# but I could not tell which" forces a guess — the exact fabrication 0017 exists
# to prevent, arriving through the UI instead of through memory.
SEED_CALLER_ROLES = [
    "fledgling",
    "brood_guard",
    "parent",
    "adult_unsure",
]

SEED_INSTRUCTIONS = ["hold_still", "one_bird", "note_context"]

# namespace -> {key -> {locale -> text}}
SEED_TRANSLATIONS = {
    "label": {
        "alarm call": {"en": "Alarm call", "de": "Alarmruf"},
        "call": {"en": "Call", "de": "Ruf"},
        "flight call": {"en": "Flight call", "de": "Flugruf"},
        "song": {"en": "Song", "de": "Gesang"},
        "mobbing": {"en": "Mobbing", "de": "Hassen"},
        "scold": {"en": "Scold", "de": "Schimpfen"},
        "contact call": {"en": "Contact call", "de": "Kontaktruf"},
        "begging": {"en": "Begging", "de": "Betteln"},
        "rattle": {"en": "Rattle", "de": "Schnarren"},
    },
    "caller_role": {
        "fledgling": {"en": "Fledgling", "de": "Ästling"},
        "brood_guard": {"en": "Brood guard (yearling)", "de": "Brutwächter (einjährig)"},
        "parent": {"en": "Parent", "de": "Elternteil"},
        "adult_unsure": {"en": "An adult, unsure which", "de": "Ein Altvogel, unklar"},
    },
    "observer_role": {
        "stranger": {"en": "Stranger to them", "de": "Fremd"},
        "known_passerby": {"en": "They know me, no food", "de": "Bekannt, ohne Futter"},
        "feeder": {"en": "I've fed these crows", "de": "Schon gefüttert"},
        "feeding_now": {"en": "Feeding them now", "de": "Füttere gerade"},
        "handler": {"en": "They let me close", "de": "Lassen mich nah"},
    },
    "context": {
        "dog_visible": {"en": "Dog visible", "de": "Hund sichtbar"},
        "squirrel": {"en": "Squirrel", "de": "Eichhörnchen"},
        "human_known": {"en": "Someone the birds know", "de": "Bekannte Person"},
        "loud_worker": {"en": "Someone working with machinery",
                        "de": "Person mit lauter Maschine"},
        "person_shouting": {"en": "Someone shouting or agitated",
                            "de": "Person schreit oder ist aufgebracht"},
        "several_birds": {"en": "Several crows present", "de": "Mehrere Krähen"},
        "caller_stays": {"en": "Caller stayed put", "de": "Rufer blieb"},
        "caller_leaves": {"en": "Caller flew off", "de": "Rufer flog weg"},
        "crows_still": {"en": "Crows still, not moving", "de": "Krähen sitzen still"},
        "crows_agitated": {"en": "Crows agitated", "de": "Krähen aufgeregt"},
        "cat_visible": {"en": "Cat visible", "de": "Katze sichtbar"},
        "raptor_overhead": {"en": "Hawk / raptor overhead", "de": "Greifvogel über uns"},
        "human_approaching": {"en": "Human approaching", "de": "Mensch nähert sich"},
        "human_passing": {"en": "Human walks through", "de": "Mensch geht vorbei"},
        # "them" is the crows: the tag is about that person's history with these
        # birds, and saying so on the chip is what keeps it off the recordist.
        "stranger_approaching": {"en": "Stranger approaches them",
                                 "de": "Fremde Person kommt heran"},
        "known_approaching": {"en": "Someone they know approaches",
                              "de": "Bekannte Person kommt heran"},
        "stranger_passing": {"en": "Stranger walks past them",
                             "de": "Fremde Person geht vorbei"},
        "known_passing": {"en": "Someone they know walks past",
                          "de": "Bekannte Person geht vorbei"},
        "vehicle": {"en": "Vehicle", "de": "Fahrzeug"},
        "human_gives_food": {"en": "Human gives food", "de": "Mensch gibt Futter"},
        "foraging": {"en": "Foraging", "de": "Futtersuche"},
        "feeding_young": {"en": "Feeding young", "de": "Füttert Jungvögel"},
        "crow_arrives": {"en": "Another crow arrives", "de": "Weitere Krähe kommt"},
        "crow_departs": {"en": "Crow flies off", "de": "Krähe fliegt weg"},
        "group_gathers": {"en": "Group gathers", "de": "Gruppe versammelt sich"},
        "mobbing_together": {"en": "Mobbing together", "de": "Gemeinsames Hassen"},
        "juvenile_present": {"en": "Juvenile present", "de": "Jungvogel anwesend"},
        "nothing_obvious": {"en": "Nothing else happening", "de": "Sonst nichts"},
    },
    "guide_title": {
        'what_this_is': {
            "en": 'What this is',
            "de": 'Worum es geht',
        },
        'press_after': {
            "en": 'Press Record after you hear it',
            "de": 'Drücke Aufnahme, nachdem du ihn hörst',
        },
        'what_to_record': {
            "en": 'What is worth recording',
            "de": 'Was sich aufzunehmen lohnt',
        },
        'silence_counts': {
            "en": 'Silence counts too',
            "de": 'Stille zählt auch',
        },
        'say_what_you_saw': {
            "en": 'Say what you saw, not what you think it meant',
            "de": 'Sag, was du gesehen hast, nicht, was du glaubst',
        },
        'how_close': {
            "en": 'How close were you?',
            "de": 'Wie nah warst du?',
        },
        'fledgling_or_adult': {
            "en": 'Fledgling or adult?',
            "de": 'Jungvogel oder Altvogel?',
        },
        'begging': {
            "en": 'What begging sounds like',
            "de": 'Wie Betteln klingt',
        },
        'alarm_or_scold': {
            "en": 'Alarm, scold, or just talking',
            "de": 'Alarm, Schimpfen oder nur Reden',
        },
        'families': {
            "en": 'The same birds, again and again',
            "de": 'Immer wieder dieselben Vögel',
        },
        'dont': {
            "en": 'Things not to do',
            "de": 'Was man nicht tun sollte',
        },
    },
    "guide_body": {
        'what_this_is': {
            "en": 'We are collecting crow calls together with what was happening at the moment of the call. Not just “a crow called” but “a crow called while a dog walked under the tree”. Enough of those and it becomes possible to ask whether a crow says something different about a dog than about a hawk.\n\nYour recordings stay on your phone until you press Sync. Nothing is uploaded in the background.',
            "de": 'Wir sammeln Krähenrufe zusammen mit dem, was im Moment des Rufs passiert ist. Nicht nur “eine Krähe hat gerufen”, sondern “eine Krähe rief, während ein Hund unter dem Baum vorbeiging”.\n\nDeine Aufnahmen bleiben auf dem Handy, bis du auf Sync drückst.',
        },
        'press_after': {
            "en": 'The app keeps the last 15 seconds of sound in memory while the record screen is open, so pressing Record captures what you already heard as well as what comes next.\n\nThis changes how to use it. Do not try to anticipate a call — you will miss it, and you will fill the corpus with recordings of nothing. Listen, and press when you hear something worth keeping.\n\nTurn on Pocket mic and it keeps buffering with the phone in your pocket and the screen off. That costs battery and puts a permanent notification in your shade, which is the honest trade for a microphone you cannot see.',
            "de": 'Die App behält die letzten 15 Sekunden im Speicher, solange der Aufnahmebildschirm offen ist. Drücke also erst, nachdem du etwas gehört hast — versuche nicht, den Ruf vorherzusehen.\n\nMit Pocket mic läuft der Puffer auch mit dem Handy in der Tasche weiter.',
        },
        'what_to_record': {
            "en": 'Anything a crow says, and the ten seconds either side of it. Context is worth more than length: a clean twenty seconds with a dog walking past beats two minutes of a bird sitting quietly.\n\nEspecially worth having:\n• a call you can see the reason for — a dog, a hawk, a person with food\n• two birds answering each other\n• a fledgling begging\n• the same bird in the same place on different days\n\nMark the ones you are sure about with the ★ Keep star. Most of what is in the corpus is seeded reference audio; the star is how a real field recording is told apart from it.',
            "de": 'Alles, was eine Krähe sagt, und die zehn Sekunden davor und danach. Kontext ist mehr wert als Länge.\n\nMarkiere sichere Aufnahmen mit dem ★-Stern — so lassen sich echte Feldaufnahmen vom eingespielten Referenzmaterial unterscheiden.',
        },
        'silence_counts': {
            "en": 'A recording of crows present and not calling is real data, and it is the kind nobody thinks to collect.\n\nWithout it, “crows alarm at dogs” is only a count of the times somebody pressed Record near a dog. The times a dog walked past and the crows said nothing are what turn that into a rate.\n\nRecord it as normal, then mark it silent on the labelling screen and tag what was there.',
            "de": 'Eine Aufnahme, in der Krähen anwesend sind und nicht rufen, sind echte Daten — und niemand denkt daran, sie zu sammeln.\n\nNimm sie normal auf und markiere sie danach als still.',
        },
        'say_what_you_saw': {
            "en": 'Context tags are for what you witnessed: a dog walked through, a person offered food, a hawk went over. They attach to a single call, not to the whole recording, because a two-minute file with one dog and one song in it would otherwise claim that crows sing at dogs.\n\nIf you worked out afterwards what it probably was — you saw the hawk five minutes later, a block away — that goes in Seen nearby instead. It is kept apart on purpose. Tagging a guess as an observation makes the result true by construction, and there is no way to undo that a year later.\n\nThere is a separate box for what you think it meant. Guess freely there: it is never used as training data.',
            "de": 'Kontext-Tags sind für das, was du gesehen hast, und hängen an einem einzelnen Ruf. Was du erst später erschlossen hast, gehört unter “In der Nähe gesehen”.\n\nFür Vermutungen gibt es ein eigenes Feld — sie werden nie als Trainingsdaten verwendet.',
        },
        'how_close': {
            "en": 'Distance changes everything about a recording: how loud the call is, how much traffic is mixed into it, and whether you could see the bird well enough to judge anything about it.\n\nIt is one tap and it is worth the tap. Two recordings of the same call type from five metres and fifty metres are not comparable, and nothing in the audio says which is which.',
            "de": 'Entfernung verändert alles an einer Aufnahme — Lautstärke, Störgeräusche und ob du den Vogel überhaupt beurteilen konntest. Ein Tipp, der sich lohnt.',
        },
        'fledgling_or_adult': {
            "en": 'Close up, in good light, a young American Crow is unmistakable once you know what to look at:\n\n• Eyes — blue-grey to muddy grey in a bird of the year, darkening over its first year. An adult eye is dark brown and reads as black.\n• Gape — the corners of the bill are pink or pale red and slightly swollen. An adult has black corners. This is the most reliable mark at close range.\n• Feathers — juvenile plumage is duller, browner and looser, with none of the adult blue-purple gloss. By late summer it looks worn and scruffy.\n• Posture — young birds sit hunched, low and slightly fluffed, and follow adults about rather than moving with purpose.\n\nAll of this needs to be close. Beyond about thirty metres none of it is visible, and a guess written down as an observation is worse than no observation. If you could not see the eye, count the bird as unaged — there is a row for exactly that.',
            "de": 'Aus der Nähe ist ein Jungvogel eindeutig: blaugraue Augen (beim Altvogel dunkelbraun), rosa Schnabelwinkel (beim Altvogel schwarz), stumpferes, bräunliches Gefieder ohne Glanz, geduckte Haltung.\n\nDas alles braucht Nähe. Über etwa dreißig Meter ist nichts davon zu sehen — dann zähle den Vogel als nicht bestimmbar.',
        },
        'begging': {
            "en": 'The easiest young crow to identify is one you never see, because begging is unmistakable: a rasping, nasal, repeated caah — flatter and more grating than an adult call, and it goes on and on. A begging bird usually quivers its wings while it does it.\n\nFledglings beg for weeks after leaving the nest and follow their parents around while doing it, so if you hear it, there is a family group nearby and it is worth staying.\n\nThis is one of the most valuable things you can record, because the age of the bird is not in doubt.',
            "de": 'Betteln ist unverkennbar: ein raues, nasales, wiederholtes kaah, flacher und kratziger als ein Altvogelruf, oft mit zitternden Flügeln.\n\nSolche Aufnahmen sind besonders wertvoll, weil das Alter des Vogels zweifelsfrei ist.',
        },
        'alarm_or_scold': {
            "en": 'You do not have to get this right — labels can be corrected later, and the app will play your earlier examples of any call type so you can compare by ear before deciding.\n\nRoughly:\n• Alarm — harsh, fast, repeated, usually with the bird whole body in it. Something is wrong and other crows are being told.\n• Scold — directed and persistent, often at a specific animal on the ground. Mobbing a cat or an owl sounds like this.\n• Contact — unhurried, spaced out, back and forth between birds. Nothing is happening.\n• Song — quiet, odd, rambling, often to itself. Easy to miss and worth keeping.\n\nWhen you cannot tell, say so rather than guessing. An honest “not sure” is worth more than a confident label that turns out to be wrong.',
            "de": 'Du musst das nicht sofort richtig treffen — Label lassen sich später korrigieren, und die App spielt dir deine früheren Beispiele zum Vergleich vor.\n\nWenn du unsicher bist, sag es lieber, als zu raten.',
        },
        'families': {
            "en": 'Recording the same birds repeatedly is a feature, not a problem — a call you have heard from the same bird twenty times means far more than twenty calls from twenty strangers.\n\nGive a group a family name when you recognise it, even a rough one, and reuse it. Location is a poor substitute: crows move, and two families can share a park.\n\nBe honest about uncertainty. If you are not sure it is the same family, do not say that it is.',
            "de": 'Dieselben Vögel immer wieder aufzunehmen ist erwünscht — zwanzig Rufe desselben Vogels sagen mehr als zwanzig Rufe von Fremden.\n\nVergib einen Familiennamen, wenn du eine Gruppe wiedererkennst, und sei ehrlich bei Unsicherheit.',
        },
        'dont': {
            "en": '• Do not approach or linger at a nest. Crows will mob you, the recording will be of you, and it is a disturbance for nothing.\n• Do not chase birds to get closer. A distant recording of an undisturbed crow is worth more than a close one of an alarmed crow — and you will have changed the very thing you are trying to measure.\n• Do not feed to provoke a reaction you can record. Feeding is fine and the birds may already know you; staging an event to capture it is a different thing and it contaminates the data.\n• Do not record people who have not agreed to it. If a passer-by is audible, say so in the description or trim it out before syncing.',
            "de": '• Nicht ans Nest gehen.\n• Vögeln nicht nachlaufen, um näher zu kommen — eine ferne Aufnahme einer ungestörten Krähe ist mehr wert als eine nahe einer beunruhigten.\n• Nicht füttern, um eine Reaktion zu provozieren.\n• Keine Menschen aufnehmen, die nicht einverstanden sind.',
        },
    },
    "instruction": {
        "hold_still": {"en": "Hold the phone steady, pointed at the bird.",
                       "de": "Halte das Handy ruhig, auf den Vogel gerichtet."},
        "one_bird": {"en": "Record one bird at a time when you can.",
                     "de": "Nimm möglichst einen Vogel nach dem anderen auf."},
        "note_context": {"en": "Note what the bird is reacting to (dog, hawk, human).",
                         "de": "Notiere, worauf der Vogel reagiert (Hund, Greifvogel, Mensch)."},
    },
    "ui": {
        "record.start": {"en": "Start recording", "de": "Aufnahme starten"},
        "record.stop": {"en": "Stop", "de": "Stopp"},
        "capture.label": {"en": "Label calls", "de": "Rufe beschriften"},
        "capture.upload": {"en": "Upload", "de": "Hochladen"},
    },
    "species": {
        "Hooded Crow": {"en": "Hooded Crow", "de": "Nebelkrähe"},
        "Carrion Crow": {"en": "Carrion Crow", "de": "Rabenkrähe"},
        "Common Raven": {"en": "Common Raven", "de": "Kolkrabe"},
        "Rook": {"en": "Rook", "de": "Saatkrähe"},
        "American Crow": {"en": "American Crow", "de": "Amerikanerkrähe"},
    },
}

# (common_name, scientific_name, slug) — slug ties to pipelines/training/models/<slug>
SEED_TAXONOMY = [
    ("American Crow", "Corvus brachyrhynchos", "american-crow"),
    ("Carrion Crow", "Corvus corone", "carrion-crow"),
    ("Common Raven", "Corvus corax", "common-raven"),
    ("Hooded Crow", "Corvus cornix", "hooded-crow"),
    ("Rook", "Corvus frugilegus", "rook"),
]
