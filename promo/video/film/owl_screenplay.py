"""The owl film's narration: what crows mobbing an owl and a hawk do and do not tell us.

Every figure is a measured one from experiments 0102 to 0113, and the film says
which way each points without promising more than the experiments did. The
closing line asks for the one recording that would settle it. Timed like the
feature: a line lasts as long as it takes to say.

A line whose clip is one of `SHOTS` is filmed as that real footage, full frame,
with its own sound under the words; `REMARKS` are the archive recordings the
narration quotes, heard from the recordist's own file.
"""

from .screenplay import Line as L, Scene, Screenplay

SHOTS = ("owl-roof", "owl-close", "owl-tree", "hawk-tree", "hawk-sky", "owl-sitting",
         "hawk-grapple", "owl-ridge", "hawk-roof", "hawk-still", "family")
REMARKS = ("xc-owl", "xc-hawk")

OWL = Screenplay(
    24,
    Scene(
        "mob",
        L(clip="owl-roof", key="roof", after=5.0),
        L("When crows find a predator, they gang up on it and yell.\nIt is called mobbing.",
          key="mobbing", clip="owl-close", under=True),
        L("Sometimes it is an owl.", key="owl", clip="owl-tree", under=True, after=1.2),
        L("Sometimes it is a hawk.", key="hawk", clip="hawk-tree", under=True, after=1.2),
        L("So here is a question. Do the crows say which?", key="question",
          clip="hawk-sky", under=True, after=1.0),
    ),
    Scene(
        "archive",
        L("Recordists sometimes write down what the crows were mobbing.", key="notes"),
        L("This group of crows was mobbing two great horned owls.", key="owlnote",
          clip="xc-owl", gain=0.8, under=True, after=2.0),
        L("This one was dive-bombing a Cooper's hawk.", key="hawknote",
          clip="xc-hawk", gain=1.0, under=True, after=2.0),
        L("I found 144 recordings like these,\nfrom 114 different people.", key="count"),
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
        L("Two. Posture. Owls are usually sitting still.", key="posture",
          clip="owl-sitting", under=True),
        L("Hawks are often flying.", key="flying", clip="hawk-grapple", under=True,
          after=0.8),
        L("Three. The crowd. A sitting owl\ndraws a bigger mob, for longer.", key="crowd",
          clip="owl-ridge", under=True, after=0.6),
    ),
    Scene(
        "crowd",
        L("Start with the crowd. I measured one plain thing:\n"
          "how much of a recording is crow sound.", key="measure"),
        L("That single number scores 0.71.\nThe model scored 0.78.", key="bars", after=0.5),
        L("So most of the gap could simply be how many crows there are."),
        L("And that number rates a roost, hundreds of crows\n"
          "settling in with no predator at all,\nas high as an owl mob.", key="roost",
          after=0.6),
    ),
    Scene(
        "posture",
        L("Next, posture. I found videos where you can see the predator,", key="videos"),
        L("and kept the ones where it was sitting still.", key="still",
          clip="hawk-roof", under=True, after=0.8),
        L("With both predators perched, the difference vanished.\n0.54. Close to guessing.",
          key="perched", after=0.5),
        L("But only 15 of those videos had a perched hawk.\n"
          "Too few to call it a no.", key="few"),
        L("And the biggest gap in that set was inside the hawks:\n"
          "perched against flying, 0.86.", key="hawks", after=1.0),
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
        L("The test that settles it needs many more of these:\n"
          "a hawk sitting still while the crows mob it.", key="hawk",
          clip="hawk-still", under=True),
        L("These are my crows. If you film yours doing that, I want it.", key="family",
          clip="family", gain=0.7, under=True, after=1.0),
        L("Scan yours at crowgpt.org.", key="title", after=3.5),
    ),
)


if __name__ == "__main__":
    print(OWL.script())
    print(f"\n{OWL.end / OWL.fps / 60:.1f} minutes, {OWL.end} frames")
