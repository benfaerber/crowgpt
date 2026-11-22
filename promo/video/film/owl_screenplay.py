"""The owl film's narration: what crows mobbing an owl and a hawk do and do not tell us.

Every figure is a measured one from experiments 0102 to 0113, and the film says
which way each points without promising more than the experiments did. The
closing line asks for the one recording that would settle it. Timed like the
feature: a line lasts as long as it takes to say.
"""

from .screenplay import Line as L, Scene, Screenplay

LISTEN = 3.4

OWL = Screenplay(
    24,
    Scene(
        "mob",
        L(after=0.6),
        L(clip="mob", gain=0.9, after=3.2, key="caw"),
        L("When crows find a predator, they gang up on it and yell.\nIt is called mobbing.",
          key="mobbing"),
        L("Sometimes it is an owl.", key="owl"),
        L("Sometimes it is a hawk.", key="hawk"),
        L("So here is a question. Do the crows say which?", key="question", after=0.5),
    ),
    Scene(
        "archive",
        L("Recordists sometimes write down what the crows were mobbing.\n"
          "I went looking for those notes.", key="notes"),
        L("I found 144 recordings of owl and hawk mobs,\nfrom 114 different people.",
          key="count"),
        L("Then I cut out every recording where you can hear\nthe owl or the hawk itself.",
          key="masked"),
        L("Only the crows were left.", key="crows"),
        L("I asked a model to tell owl mobs from hawk mobs,\nfrom the crows alone.",
          key="model"),
        L("On this scale, 0.5 is guessing and 1 is perfect.", key="scale"),
        L("It scored 0.78.", key="score", after=0.6),
    ),
    Scene(
        "replicate",
        L("But a pattern found in one pile of recordings\ncan be a quirk of that pile.",
          key="quirk"),
        L("So I wrote the prediction down first,\nand then went looking for new recordings.",
          key="predict"),
        L("Different people. Mostly phones.\nNone of them heard by the model before.",
          key="new"),
        L("It scored 0.75.", key="score"),
        L("Almost exactly the same. That is what a real difference does.", key="real",
          after=0.6),
    ),
    Scene(
        "suspects",
        L("So an owl mob really does sound different from a hawk mob.\nThe question is why."),
        L("There are three suspects.", key="three"),
        L("One. The crows have a call that means owl.\nThat is the exciting one.",
          key="name"),
        L("Two. Posture. Owls are usually sitting still.\nHawks are often flying.",
          key="posture"),
        L("Three. The crowd. A sitting owl\ndraws a bigger mob, for longer.", key="crowd",
          after=0.6),
    ),
    Scene(
        "crowd",
        L("Start with the crowd. I measured one plain thing:\n"
          "how much of a recording is crow sound.", key="measure"),
        L("That single number scores 0.71.\nThe model scored 0.78.", key="bars"),
        L("So most of the gap could simply be how many crows there are."),
        L("And that number rates a roost, hundreds of crows\n"
          "settling in with no predator at all,\nas high as an owl mob.", key="roost",
          after=0.6),
    ),
    Scene(
        "posture",
        L("Next, posture. I found videos where you can see the predator,\n"
          "and kept the ones where it was sitting still.", key="videos"),
        L("With both predators perched, the difference vanished.\n0.54. Close to guessing.",
          key="perched"),
        L("But only 15 of those videos had a perched hawk.\n"
          "Too few to call it a no.", key="few"),
        L("And the biggest gap in that set was inside the hawks:\n"
          "perched against flying, 0.86.", key="hawks", after=0.6),
    ),
    Scene(
        "single",
        L("Last, one crow at a time.\nOnly the moments when a single bird is calling.",
          key="one", clip="single", gain=0.9, under=True),
        L("Owl against hawk from one bird: 0.61. Weak.", key="score", after=0.6),
    ),
    Scene(
        "verdict",
        L("So here is where it stands."),
        L("Crows mobbing an owl do sound different.\nThat held up in new recordings.",
          key="yes"),
        L("But no test yet shows they are naming the owl.", key="no"),
        L("The simplest story is that an owl sits still,\n"
          "and gathers a bigger crowd for longer.", key="story", after=0.6),
    ),
    Scene(
        "ask",
        L("The test that would settle it needs a hawk\n"
          "that sits still while the crows mob it.", key="hawk"),
        L("If you ever film that, I want it."),
        L("Scan yours at crowgpt.org.", key="title", after=3.5),
    ),
)


if __name__ == "__main__":
    print(OWL.script())
    print(f"\n{OWL.end / OWL.fps / 60:.1f} minutes, {OWL.end} frames")
