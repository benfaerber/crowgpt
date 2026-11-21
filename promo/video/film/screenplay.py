"""The feature's narration, and the clock that follows from it.

Every line is said aloud by a narrator, so the film's length is not chosen: a
line lasts as long as it takes to say, plus a breath, plus whatever silence the
picture needs after it. Scenes read their frames from here, so rewriting a line
moves the picture and the soundtrack with it. No Blender in this file: the
renderer reads it too.
"""


class Line:
    """One thing the narrator says, or a silence when there is no text."""

    WORDS_PER_SECOND = 2.5
    BREATH = 0.55
    SHORTEST = 1.3
    FULL_STOP = 0.3
    FIGURE = 4

    def __init__(self, text="", key=None, after=0.0, clip=None, gain=1.0, under=False):
        self.text, self.key = text, key
        self.after, self.clip, self.gain, self.under = after, clip, gain, under
        self.start = self.spoken = self.end = 0

    @property
    def words(self):
        """Words as they are said: a figure is several, however short it is written."""
        return sum(self.FIGURE if word.startswith("{") else 1 for word in self.text.split())

    @property
    def speaking(self):
        if not self.text:
            return 0.0
        stops = sum(self.text.count(mark) for mark in ".?:") - 1
        return max(self.SHORTEST,
                   self.words / self.WORDS_PER_SECOND + max(0, stops) * self.FULL_STOP)

    @property
    def seconds(self):
        return self.speaking + (self.BREATH if self.text else 0.0) + self.after

    @property
    def cue(self):
        """The frame its clip starts: under the words, or in the silence after them."""
        return self.start + 2 if self.under or not self.text else self.spoken + 4


class Scene:
    def __init__(self, name, *lines):
        self.name, self.lines = name, lines
        self.start = self.end = 0

    def at(self, key):
        return self.line(key).start

    def line(self, key):
        return next(line for line in self.lines if line.key == key)


class Screenplay:
    def __init__(self, fps, *scenes):
        self.fps = fps
        self.scenes = {scene.name: scene for scene in scenes}
        clock = 0.0
        for scene in scenes:
            scene.start = self._frame(clock)
            for line in scene.lines:
                line.start = self._frame(clock)
                line.spoken = self._frame(clock + line.speaking)
                clock += line.seconds
                line.end = self._frame(clock)
            scene.end = self._frame(clock)
        self.end = self._frame(clock) - 1

    def _frame(self, seconds):
        return 1 + round(seconds * self.fps)

    def scene(self, name):
        return self.scenes[name]

    def lines(self):
        return [line for scene in self.scenes.values() for line in scene.lines]

    def cues(self):
        return [(line.clip, line.cue, line.gain) for line in self.lines() if line.clip]

    def script(self):
        """The narration as a page to read from, with the time each line starts."""
        page = []
        for scene in self.scenes.values():
            page.append(f"\n[{scene.name}]")
            for line in scene.lines:
                seconds = (line.start - 1) / self.fps
                stamp = f"{int(seconds // 60)}:{seconds % 60:04.1f}"
                listening = f"(listen: {line.clip})" if line.clip else "(quiet)"
                body = " ".join(line.text.split()) if line.text else listening
                if line.text and line.clip and not line.under:
                    body += f"  (then listen: {line.clip})"
                page.append(f"{stamp}  {body}")
        return "\n".join(page)


L = Line
LISTEN = 3.9

FEATURE = Screenplay(
    24,
    Scene(
        "open",
        L(after=0.9),
        L(clip="edgar", after=3.4, key="caw"),
        L("That was Edgar. He lives on the power line\noutside my house."),
        L("He just said something.\nI have no idea what."),
        L("So I am building an AI to find out.", key="promise"),
        L("This is how far it has got, what went wrong,\nand how your crows can help."),
    ),
    Scene(
        "murder",
        L("It started with peanuts.", key="peanuts"),
        L("I began feeding the crows in my yard in Salt Lake City.\n"
          "Five of them kept coming back."),
        L("Thrasher and Ripjaw are the parents.", key="parents"),
        L("Killer and Shredder hatched this year.", key="fledglings"),
        L("And Edgar is a yearling, who stayed on\nto help guard the new brood.", key="edgar"),
        L("When I leave I say \"bye, buddies.\"\nOne day, Killer called back.", key="killer"),
        L("That is not science. It is why I started.", after=0.4),
    ),
    Scene(
        "mask",
        L("Crows are worth the trouble."),
        L("In Seattle, researchers wore a rubber mask\nwhile they trapped a few crows.",
          key="mask"),
        L("For years afterwards, crows scolded that mask on sight.", key="scold",
          clip="real", gain=0.3, under=True),
        L("Including crows that were never trapped,\nand young ones hatched after it happened.",
          key="others"),
        L("They had learned the face from each other."),
        L("So crows pass information around.\n"
          "The question is how much of it travels in their calls.", after=0.4),
    ),
    Scene(
        "types",
        L("Nobody has a crow dictionary. Not me, not science."),
        L("What there is, is rougher. Calls come in types.\nHere are five.", key="chips"),
        L("The alarm call. Harsh, fast, repeated.\nSomething is wrong.",
          key="alarm", clip="alarm", after=LISTEN),
        L("The flight call. Spaced and carrying.\nHere I am, this way.",
          key="flight", clip="flight", after=LISTEN),
        L("The ordinary call. Unhurried, back and forth.\nNothing much is happening.",
          key="call", clip="call", after=LISTEN),
        L("Begging. A fledgling that wants feeding\nand will not stop asking.",
          key="begging", clip="begging", after=LISTEN),
        L("And song. Quiet, rambling, often to itself.\nNobody knows what it is for.",
          key="song", clip="song", after=LISTEN),
    ),
    Scene(
        "cawdex",
        L("Step one was teaching a computer to hear those types."),
        L("I call it CawDex. Give it a recording, and it finds\n"
          "every crow call and names its type.", key="name"),
        L("It learned from {credits.recordings} recordings shared by\n"
          "{credits.recordists} recordists on Xeno-canto.", key="archive"),
        L("In all, about four hundred hours of crows.", key="hours"),
        L("At first it was poor at alarm calls.\nNot much better than guessing.", key="weak"),
        L("I assumed it needed a bigger model. It did not."),
        L("It needed better labels. Trained on labels checked by hand,\n"
          "the same model became reliable.", key="clean"),
        L("That is the lesson of the whole project.\n"
          "The scarce thing is not computing. It is careful listening.", after=0.4),
    ),
    Scene(
        "precedent",
        L("But a type is not a meaning. An alarm call says\n"
          "something is wrong. It does not say what.", key="question"),
        L("Some animals do say what."),
        L("Vervet monkeys have one alarm call for leopards,\n"
          "another for eagles, and another for snakes.", key="vervet"),
        L("And each one sends the troop a different way:\n"
          "up a tree, into the bushes, or up on two legs to look.", key="actions"),
        L("Chickadees add more \"dee\" notes to their call\n"
          "the more dangerous the predator.", key="chickadee"),
        L("And Siberian jays, cousins of the crow, call differently\n"
          "for a hawk that is perched, searching or attacking.", key="jay", after=0.4),
    ),
    Scene(
        "hypothesis",
        L("So my first hypothesis is a modest one."),
        L("Crows answer a threat on the ground, like a dog,\n"
          "differently from one in the air, like a hawk.", key="threats"),
        L("To test it, every call needs a second label:\n"
          "what was there when the bird called.", key="tags"),
        L("If calls under those two tags land in separate groups,\n"
          "the hypothesis holds. If they mix, it does not.", key="collect", after=0.8),
        L("This picture is what a yes would look like.\nI do not have the answer yet.",
          key="circle"),
        L("And it is only the first question.\n"
          "Cat. Food. A stranger. Every tag is another test.", key="later", after=0.6),
    ),
    Scene(
        "app",
        L("So I go out and collect exactly that."),
        L("My field kit is a shotgun microphone, a furry windshield,\n"
          "and a bag that fits in one hand.", key="kit"),
        L("Crows notice equipment. So it stays small."),
        L("And I built a phone app to go with it.", key="phone"),
        L("It records the crows, finds the calls,\nand asks what was going on.", key="record"),
        L("Labelling by hand is slow, and I am one person\n"
          "with one family of crows, on one street."),
        L("One backyard cannot collect enough.", after=0.4),
    ),
    Scene(
        "crowgpt",
        L("There is a second half to this. Talking back."),
        L("CrowGPT is a small model trained on crow calls.\n"
          "Ask it for a type, and it makes a new one.", key="prompt"),
        L("Version one sounded like this.", key="v1", clip="crowbot", after=3.5),
        L("Version two sounds like this.", key="v2", clip="generated", after=4.5),
        L("No bird ever made that call.", key="reply"),
        L("I do not play these to the crows.\n"
          "A fake alarm could scare real birds for nothing."),
        L("First the meaning. Then the conversation.", after=0.4),
    ),
    Scene(
        "website",
        L("Which is where you come in."),
        L("You probably have crows nearby. Or ravens, or rooks."),
        L("Go to crowgpt.org and drop in a video or a recording.\n"
          "CawDex reads every call in it.", key="drop"),
        L("If you let the project keep the file, you can label it:\n"
          "what the birds were doing, and what was around.", key="keep"),
        L("Every labelled call is one more dot on that chart.", after=0.4),
    ),
    Scene(
        "finale",
        L("No call has been translated yet.\nI want to be plain about that."),
        L("But the tools work, the question is real, and the crows\n"
          "are right there on the wire, talking.", key="title"),
        L("Help me find out what about."),
        L("Scan yours at crowgpt.org.", key="ask", after=3.5),
    ),
)


if __name__ == "__main__":
    print(FEATURE.script())
    print(f"\n{FEATURE.end / FEATURE.fps / 60:.1f} minutes, {FEATURE.end} frames")
