"""The explainer: the project, its hypothesis and how to help, told along one power line."""

import json
import math
import random
from pathlib import Path

from .crow import FlyingCrow, PerchedCrow, Plumage
from .director import Camera, Film
from .kit import Materials, Pace, Palette, Shapes
from .props import (Arrow, CallColors, Chip, ContextColors, Dog, Emitter, Person, Phone, Sign,
                    CaptionLayout, Subtitles, TagTest, Website)
from .sets import Dusk, Lattice, Lockup, PowerLine, SoundRings, Spectrogram, TokenStream
from .timeline import ExplainerTimeline as T


class Figures:
    """The promo page's own numbers, so the film never states one it does not."""

    def __init__(self, path):
        self.figures = json.loads(Path(path).read_text())["figures"]

    def text(self, key):
        return self.figures[key]["text"]


class Explainer(Film):
    CLOCK = T
    FAMILY = [("Thrasher", -1.5, 1.0), ("Ripjaw", -0.75, 1.0), ("Edgar", 0.0, 0.95),
              ("Killer", 0.75, 0.85), ("Shredder", 1.5, 0.85)]
    CALLER = "Edgar"
    FLOOR = 9.0

    def build(self):
        self.figures = Figures(self.stats)
        self.subtitles = Subtitles(self.stage, self.fonts, CaptionLayout.of(self.shape))
        self.family = {}
        self.dusk = Dusk(self.stage)
        PowerLine(self.stage)
        self.rings = SoundRings(self.stage)
        self._the_murder()
        self._the_goal()
        self._listen()
        self._cawdex_and_meaning()
        self._the_hypothesis()
        self._the_app()
        self._crowgpt()
        self._the_website()
        self._where_it_is()
        Pace(self.CLOCK).apply(self.scene)
        return self.scene

    def _light(self, location, energy=2500.0):
        lamp = self.dusk.lamp("Set light", "POINT", location, (0.0, 0.0, 0.0), "#dfe4ff", energy)
        lamp.data.shadow_soft_size = 1.5

    def _say(self, camera, lines):
        for body, start, end in lines:
            self.subtitles.show(camera, body, start, end)

    def _the_murder(self):
        dice = random.Random(2)
        plumage = Plumage.living()
        for index, (name, x, size) in enumerate(self.FAMILY):
            crow = PerchedCrow(self.stage, name, plumage).place(PowerLine.perch(x))
            crow.root.scale = (size, size, size)
            self.family[name] = crow
            for frame in range(1, T.GOAL, 34):
                crow.look(frame + dice.randint(0, 12), yaw=dice.uniform(-0.9, 0.4),
                          tilt=dice.uniform(-0.2, 0.2))
            Sign(self.stage, self.fonts, name, (x, 0.0, PowerLine.HEIGHT + 0.62), 0.15).pop(
                30 + index * 12).leave(T.GOAL)
        camera = Camera(self.stage, "Murder camera", 40.0)
        camera.move(T.MURDER, (2.2, -8.5, 4.3), (0.1, 0.0, 5.45))
        camera.move(T.GOAL, (1.0, -5.6, 4.6), (0.05, 0.0, 5.4))
        self._cut(T.MURDER, camera)
        self._say(camera, [
            ("It started with five backyard crows.", 12, 78),
            ("Obviously smart. Obviously talking.\nAbout what?", 86, T.GOAL - 4),
        ])

    def _the_goal(self):
        z = self.FLOOR
        perch = Materials.glow("Perch", Palette.SKY_MID, 1.5)
        for x in (-34.0, -26.0):
            self.stage.add("Perch", Shapes.block("perch", (1.8, 0.1, 0.1)), perch,
                           location=(x, 0.0, z - 0.05))
        real = PerchedCrow(self.stage, "Goal crow", Plumage.living()).place((-34.0, 0.0, z))
        real.root.scale = (3.0, 3.0, 3.0)
        answer = PerchedCrow(self.stage, "Goal reply", Plumage.generated()).place(
            (-26.0, 0.0, z), heading=math.pi)
        answer.root.scale = (3.0, 3.0, 3.0)
        self._light((-33.0, -5.0, z + 3.0))
        Person(self.stage, (-30.0, 0.0, z - 0.3)).pop(T.GOAL + 30)
        Arrow(self.stage, (-32.8, 0.0, z + 0.8), 1.9).pop(T.GOAL + 44)
        Arrow(self.stage, (-29.1, 0.0, z + 0.8), 1.9).pop(T.GOAL + 78)
        Sign(self.stage, self.fonts, "CawDex", (-31.85, 0.0, z + 1.25), 0.34).pop(T.GOAL + 50)
        Sign(self.stage, self.fonts, "CrowGPT", (-28.15, 0.0, z + 1.25), 0.34).pop(T.GOAL + 84)
        for body, x in (("crow", -34.0), ("human", -30.0), ("crow", -26.0)):
            Sign(self.stage, self.fonts, body, (x, 0.0, z - 0.75), 0.3,
                 color=Palette.ACCENT).pop(T.GOAL + 16)
        camera = Camera(self.stage, "Goal camera", 35.0)
        camera.move(T.GOAL, (-30.6, -12.5, z + 0.4), (-30.0, 0.0, z + 0.75))
        camera.move(T.LISTEN, (-29.6, -11.0, z + 0.4), (-30.0, 0.0, z + 0.75))
        self._cut(T.GOAL, camera)
        self._say(camera, [
            ("The goal: a translator\nthat runs in both directions.", T.GOAL + 6, T.GOAL + 88),
            ("CawDex reads the calls.\nCrowGPT says them back.", T.GOAL + 94, T.LISTEN - 4),
        ])

    def _listen(self):
        caller = self.family[self.CALLER]
        caller.look(T.LISTEN - 1, yaw=0.0)
        self._call_out(caller, self.real_call, T.REAL_CALL, 1.0)
        x = caller.root.location.x
        camera = Camera(self.stage, "Listen camera", 40.0)
        camera.move(T.LISTEN, (x + 1.3, -2.6, 5.1), (x + 0.3, 0.0, 5.34))
        camera.move(T.CAWDEX, (x + 1.0, -1.9, 5.12), (x + 0.3, 0.0, 5.34))
        self._cut(T.LISTEN, camera)
        self._say(camera, [("First, listen.", T.LISTEN + 3, T.CAWDEX - 2)])

    def _cawdex_and_meaning(self):
        z = self.FLOOR
        heard = Spectrogram(self.stage, "Heard",
                            self.real_call.spectrogram(self.COLUMNS, self.BANDS),
                            (40.0, 0.0, z))
        heard.rise(T.REAL_CALL, self.real_call.frames)
        types = [("alarm call", CallColors.ALARM), ("flight call", CallColors.FLIGHT),
                 ("call", CallColors.CALL), ("begging", CallColors.BEGGING),
                 ("song", CallColors.SONG)]
        chips = {}
        left = 40.2
        for index, (body, color) in enumerate(types):
            width = Chip.width(body, 0.44)
            chips[body] = Chip(self.stage, self.fonts, body, color,
                               (left + width / 2.0, 1.0, z + 3.9), size=0.44).pop(
                T.CAWDEX + 56 + index * 9)
            left += width + 0.35
        chips["alarm call"].single_out(T.CAWDEX + 118, hold=62)
        Sign(self.stage, self.fonts, "?", (55.4, 0.0, z + 0.9), 2.2,
             color=Palette.ACCENT, strength=2.5).pop(T.MEANING + 44)

        camera = Camera(self.stage, "CawDex camera", 28.0)
        for frame, x, pull in ((T.CAWDEX, 45.5, 13.0), (T.MEANING + 4, 46.5, 13.0),
                               (T.MEANING + 64, 54.0, 10.5), (T.HYPOTHESIS, 54.6, 10.0)):
            camera.move(frame, (x - 2.5, -pull, z + 2.3), (x + 0.5, 0.0, z + 1.6))
        self._cut(T.CAWDEX, camera)
        self._say(camera, [
            ("CawDex finds every crow call\nand names its type.", T.CAWDEX + 8, T.CAWDEX + 110),
            ("This one is an alarm call.", T.CAWDEX + 118, T.MEANING - 4),
            ("An alarm at what?\nA type is not a meaning.", T.MEANING + 6, T.HYPOTHESIS - 4),
        ])

    def _the_hypothesis(self):
        z, start = self.FLOOR, T.HYPOTHESIS
        ground, air = (151.2, 0.0, z), (164.8, 0.0, z + 2.0)
        self.stage.add("Ground plate", Shapes.block("ground plate", (3.0, 2.4, 0.1)),
                       Materials.surface("Ground plate", "#15121c", 0.35, 0.5),
                       location=(151.2, 0.0, z - 0.05))
        self._light((150.0, -5.0, z + 4.0))
        self._light((165.0, -5.0, z + 5.0))
        Dog(self.stage, ground, size=1.7).pop(start + 14)
        hawk = FlyingCrow(self.stage, "Hawk", Materials.surface("Hawk", "#b0764a", 0.7),
                          size=3.4)
        hawk.root.rotation_euler = (0.5, 0.0, 0.0)
        hawk.flap(start)
        for step in range(0, T.APP - start + 30, 30):
            lift = 0.25 if (step // 30) % 2 else -0.25
            hawk.root.location = (air[0], air[1], air[2] + lift)
            hawk.root.keyframe_insert("location", frame=start + step)
        Chip(self.stage, self.fonts, "dog visible", ContextColors.GROUND,
             (151.4, 0.0, z + 4.3), size=0.5).pop(start + 150)
        Chip(self.stage, self.fonts, "raptor overhead", ContextColors.AIR,
             (164.0, 0.0, z + 5.3), size=0.5).pop(start + 162)

        test = TagTest(self.stage, (158.0, 0.0, z + 2.1))
        Sign(self.stage, self.fonts, "do the calls differ?", (158.0, 0.0, z + 5.0), 0.62).pop(
            start + 250)
        test.collect(start + 262, (151.6, -0.4, z + 1.6), ContextColors.GROUND, (-1.9, -0.75))
        test.collect(start + 270, (164.4, -0.4, z + 2.2), ContextColors.AIR, (1.9, 0.75))
        test.circle(start + 356, ContextColors.GROUND, (-1.9, -0.75))
        test.circle(start + 364, ContextColors.AIR, (1.9, 0.75))
        later = zip(ContextColors.LATER, (152.5, 158.0, 163.5),
                    ((-1.9, 1.2), (0.0, 0.0), (1.9, -1.2)))
        for index, ((tag, color), x, landing) in enumerate(later):
            frame = T.MORE + 10 + index * 22
            Chip(self.stage, self.fonts, tag, color, (x, 0.0, z + 6.5), size=0.42).pop(frame)
            test.collect(frame + 10, (x, -0.4, z + 6.2), color, landing, count=9, spread=0.4)

        camera = Camera(self.stage, "Hypothesis camera", 28.0)
        camera.move(start, (156.8, -18.0, z + 2.9), (158.0, 0.0, z + 2.5))
        camera.move(T.APP, (159.2, -17.4, z + 2.9), (158.0, 0.0, z + 2.5))
        self._cut(start, camera)
        self._say(camera, [
            ("The hypothesis: crows answer a threat on the ground,\n"
             "like a dog, differently from one in the air, like a hawk.", start + 6, start + 138),
            ("So every labelled call gets a context tag:\n"
             "what was there when the bird called.", start + 146, start + 250),
            ("If dog calls and hawk calls land in separate groups,\n"
             "the hypothesis holds. If they mix, it does not.", start + 258, T.MORE - 4),
            ("That is one hypothesis.\nMore recordings make room for more of them.",
             T.MORE + 4, T.MORE + 80),
            ("One test at a time,\nthe meaning of the calls gets worked out.",
             T.MORE + 86, T.APP - 4),
        ])

    def _the_app(self):
        z = self.FLOOR + 1.3
        self._light((70.5, -5.0, z + 2.5), 1500.0)
        phone = Phone(self.stage, self.fonts, (72.0, 0.0, z), self.real_call.envelope())
        phone.record(T.APP + 14, 70).keep(T.APP + 96)
        Chip(self.stage, self.fonts, "alarm call", CallColors.ALARM, (74.5, 0.0, z + 0.9),
             size=0.3).pop(T.APP + 112)
        Chip(self.stage, self.fonts, "dog visible", ContextColors.GROUND, (74.55, 0.0, z + 0.2),
             size=0.3).pop(T.APP + 126)
        camera = Camera(self.stage, "App camera", 35.0)
        camera.move(T.APP, (71.4, -9.0, z + 0.2), (72.6, 0.0, z))
        camera.move(T.CROWGPT, (73.6, -7.6, z + 0.2), (72.8, 0.0, z))
        self._cut(T.APP, camera)
        minutes = self.figures.text("labels.minutes")
        self._say(camera, [
            ("The field app records the call\nand its tag together, on the spot.",
             T.APP + 6, T.APP + 104),
            (f"{minutes} minutes of human-labelled calls so far.\n"
             "One backyard cannot collect enough.", T.APP + 110, T.CROWGPT - 4),
        ])

    def _crowgpt(self):
        z = self.FLOOR
        prompt = (104.0, 0.0, z + 1.6)
        Chip(self.stage, self.fonts, "call type", Palette.CREAM, prompt, size=0.36).pop(
            T.CROWGPT + 6)
        lattice = Lattice(self.stage, (110.0, 0.0, z + 1.6))
        Sign(self.stage, self.fonts, "CrowGPT", (110.0, 0.0, z + 3.5), 0.6).pop(
            T.CROWGPT + 30)
        said = Spectrogram(self.stage, "Said",
                           self.generated_call.spectrogram(self.COLUMNS, self.BANDS),
                           (116.0, 0.0, z))
        said.rise(T.GENERATED_CALL, self.generated_call.frames)
        tokens = TokenStream(self.stage, Emitter(prompt), lattice, said)
        first = tokens.flow(T.GENERATED_CALL - 2, self.generated_call.frames)
        lattice.think(first + TokenStream.LIFT + TokenStream.APPROACH - 8,
                      T.GENERATED_CALL + self.generated_call.frames)

        camera = Camera(self.stage, "CrowGPT camera", 28.0)
        for frame, x in ((T.CROWGPT, 105.5), (T.CROWGPT + 70, 109.5),
                         (T.GENERATED_CALL + 20, 120.0), (T.REPLY, 121.0)):
            camera.move(frame, (x - 2.5, -13.0, z + 1.9), (x + 0.5, 0.0, z + 1.2))
        self._cut(T.CROWGPT, camera)
        self._say(camera, [
            ("CrowGPT is the speaking half.", T.CROWGPT + 6, T.CROWGPT + 66),
            ("Ask for a call type and it generates\na brand-new crow call.",
             T.CROWGPT + 72, T.REPLY - 4),
        ])

        reply = PerchedCrow(self.stage, "Generated crow", Plumage.generated())
        reply.place(PowerLine.perch(134.0), heading=math.pi)
        self._call_out(reply, self.generated_call, T.GENERATED_CALL, -1.0,
                       not_before=T.REPLY - 12)
        close = Camera(self.stage, "Reply camera", 55.0)
        close.move(T.REPLY, (132.85, -1.7, 5.5), (133.82, 0.0, 5.32))
        close.move(T.WEBSITE, (133.2, -1.4, 5.44), (133.82, 0.0, 5.32))
        self._cut(T.REPLY, close)
        self._say(close, [
            ("Generated, not a recording of a bird.", T.REPLY + 4, T.WEBSITE - 4),
        ])

    def _the_website(self):
        start, centre = T.WEBSITE, (-60.0, 0.0, self.FLOOR + 2.0)
        self._light((-61.5, -6.0, centre[2] + 2.0), 1800.0)
        Website(self.stage, self.fonts, centre).drop(start + 40).results(start + 100).keep(
            start + 178)
        camera = Camera(self.stage, "Website camera", 35.0)
        camera.move(start, (-61.0, -13.0, centre[2] + 0.2), (-60.0, 0.0, centre[2] - 0.9))
        camera.move(T.FINALE, (-59.2, -12.0, centre[2] + 0.2), (-60.0, 0.0, centre[2] - 0.9))
        self._cut(start, camera)
        self._say(camera, [
            ("Try it at crowgpt.org: scan a video or a recording\n"
             "and CawDex reads every call in it.", start + 6, start + 160),
            ("Share the file and say what was happening.\n"
             "That is the data the hypothesis needs.", start + 168, T.FINALE - 4),
        ])

    def _where_it_is(self):
        dice = random.Random(8)
        for crow in self.family.values():
            crow.look(T.FINALE - 1, yaw=0.0)
            crow.look(T.FINALE + dice.randint(10, 40), yaw=dice.uniform(-0.9, -0.3),
                      tilt=dice.uniform(-0.25, 0.25))
            crow.look(T.END, yaw=dice.uniform(-0.9, -0.5), tilt=0.0)
        Lockup(self.stage, self.fonts, self.logo, (-1.9, 2.0, 7.45), size=0.8).reveal(T.TITLE)
        self._flock(T.FINALE + 4)
        camera = Camera(self.stage, "Finale camera", 32.0)
        camera.move(T.FINALE, (0.4, -6.2, 4.7), (0.7, 0.0, 5.8))
        camera.move(T.END, (0.8, -7.4, 4.7), (0.8, 0.0, 5.85))
        self._cut(T.FINALE, camera)
        self._say(camera, [
            ("No call has been translated yet.\nIt takes crows from far more than one backyard.",
             T.FINALE + 6, T.FINALE + 104),
            ("Scan yours at crowgpt.org.", T.FINALE + 112, T.END),
        ])
