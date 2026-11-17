"""The explainer: the whole project in eight chapters, told along one power line."""

import json
import math
import random
from pathlib import Path

from .crow import PerchedCrow, Plumage
from .director import Camera, Film
from .kit import Materials, Palette, Shapes
from .props import (Arrow, CallColors, Chip, Dog, Emitter, Person, Phone, Sign, Subtitles,
                    ValleyMap)
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
        self.subtitles = Subtitles(self.stage, self.fonts)
        self.family = {}
        self.dusk = Dusk(self.stage)
        PowerLine(self.stage)
        self.rings = SoundRings(self.stage)
        self._the_murder()
        self._the_goal()
        self._listen()
        self._cawdex_and_meaning()
        self._the_app()
        self._cawscout()
        self._crowgpt()
        self._where_it_is()
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
            ("It started with five backyard crows.", 12, 84),
            ("Obviously smart. Obviously talking.\nAbout what?", 92, T.GOAL - 4),
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
            ("The goal: a translator\nthat runs in both directions.", T.GOAL + 6, T.GOAL + 92),
            ("CawDex reads the calls.\nCrowGPT says them back.", T.GOAL + 98, T.LISTEN - 4),
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
        chips["alarm call"].single_out(T.CAWDEX + 126, hold=90)

        Sign(self.stage, self.fonts, "?", (55.4, 0.0, z + 0.9), 2.2,
             color=Palette.ACCENT, strength=2.5).pop(T.MEANING + 50)
        Arrow(self.stage, (56.6, 0.0, z + 1.7), 1.6).pop(T.MEANING + 118)
        self.stage.add("Witness plate", Shapes.block("witness", (2.2, 2.2, 0.1)),
                       Materials.surface("Witness plate", "#15121c", 0.35, 0.5),
                       location=(59.6, 0.0, z - 0.05))
        self._light((58.5, -5.0, z + 4.0))
        Dog(self.stage, (59.5, 0.0, z), size=1.6).pop(T.MEANING + 124)
        for index, body in enumerate(("dog", "person", "food")):
            Chip(self.stage, self.fonts, body, Palette.CREAM,
                 (62.3, 0.0, z + 2.9 - index * 1.0), size=0.44).pop(
                T.MEANING + 140 + index * 12)

        camera = Camera(self.stage, "CawDex camera", 28.0)
        for frame, x, pull in ((T.CAWDEX, 45.5, 13.0), (T.MEANING + 4, 46.5, 13.0),
                               (T.MEANING + 70, 57.0, 9.5), (T.APP, 58.0, 9.0)):
            camera.move(frame, (x - 2.5, -pull, z + 2.3), (x + 0.5, 0.0, z + 1.6))
        self._cut(T.CAWDEX, camera)
        auc = self.figures.text("auc.alarm.clean")
        self._say(camera, [
            ("CawDex finds every crow call\nand names its type.", T.CAWDEX + 8, T.CAWDEX + 118),
            (f"Alarm calls: {auc} AUC on clean labels.", T.CAWDEX + 126, T.MEANING - 4),
            ("But a type is not a meaning.", T.MEANING + 6, T.MEANING + 104),
            ("Meaning needs a witness: what was\nhappening when the bird called.",
             T.MEANING + 112, T.APP - 4),
        ])

    def _the_app(self):
        z = self.FLOOR + 1.3
        self._light((70.5, -5.0, z + 2.5), 1500.0)
        phone = Phone(self.stage, self.fonts, (72.0, 0.0, z), self.real_call.envelope())
        phone.record(T.APP + 14, 70).keep(T.APP + 96)
        Chip(self.stage, self.fonts, "alarm call", CallColors.ALARM, (74.5, 0.0, z + 0.9),
             size=0.3).pop(T.APP + 112)
        Chip(self.stage, self.fonts, "dog", Palette.CREAM, (74.1, 0.0, z + 0.2),
             size=0.3).pop(T.APP + 126)
        Chip(self.stage, self.fonts, "person", Palette.CREAM, (74.4, 0.0, z - 0.5),
             size=0.3).pop(T.APP + 138)
        camera = Camera(self.stage, "App camera", 35.0)
        camera.move(T.APP, (71.4, -9.0, z + 0.2), (72.6, 0.0, z))
        camera.move(T.SCOUT, (73.6, -7.6, z + 0.2), (72.8, 0.0, z))
        self._cut(T.APP, camera)
        minutes = self.figures.text("labels.minutes")
        self._say(camera, [
            ("So there is a field app: record,\nlabel each call, tag what was happening.",
             T.APP + 6, T.APP + 150),
            (f"{minutes} minutes of human-labelled calls so far.\n"
             "That number is what limits the project.", T.APP + 158, T.SCOUT - 4),
        ])

    def _cawscout(self):
        z = self.FLOOR
        valley = ValleyMap(self.stage, self.fonts, (86.0, -3.0, z))
        valley.score(T.SCOUT + 6).subtract_predator(T.SCOUT + 96).rank(T.SCOUT + 126)
        camera = Camera(self.stage, "Scout camera", 30.0)
        camera.move(T.SCOUT, (88.0, -15.5, z + 6.0), (90.5, 0.0, z + 1.6))
        camera.move(T.CROWGPT, (93.0, -14.0, z + 5.4), (90.5, 0.0, z + 1.6))
        self._cut(T.SCOUT, camera)
        self._say(camera, [
            ("One backyard is one family. CawScout scores\nthe whole valley to find the next.",
             T.SCOUT + 6, T.SCOUT + 90),
            ("Tall trees add. Owls subtract.\nThe best cells become numbered targets.",
             T.SCOUT + 96, T.CROWGPT - 4),
        ])

    def _crowgpt(self):
        z = self.FLOOR
        prompt = (104.0, 0.0, z + 1.6)
        Chip(self.stage, self.fonts, "call type", Palette.CREAM, prompt, size=0.36).pop(
            T.CROWGPT + 6)
        lattice = Lattice(self.stage, (110.0, 0.0, z + 1.6))
        Sign(self.stage, self.fonts, "CrowGPT", (110.0, 0.0, z + 3.6), 0.9).pop(
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
        for frame, x in ((T.CROWGPT, 105.5), (T.CROWGPT + 80, 109.5),
                         (T.GENERATED_CALL + 20, 120.0), (T.REPLY, 121.0)):
            camera.move(frame, (x - 2.5, -13.0, z + 1.9), (x + 0.5, 0.0, z + 1.2))
        self._cut(T.CROWGPT, camera)
        self._say(camera, [
            ("CrowGPT is the speaking half.", T.CROWGPT + 6, T.CROWGPT + 76),
            ("Ask for a call type and it generates\na brand-new crow call.",
             T.CROWGPT + 82, T.REPLY - 4),
        ])

        reply = PerchedCrow(self.stage, "Generated crow", Plumage.generated())
        reply.place(PowerLine.perch(134.0), heading=math.pi)
        self._call_out(reply, self.generated_call, T.GENERATED_CALL, -1.0,
                       not_before=T.REPLY - 12)
        close = Camera(self.stage, "Reply camera", 55.0)
        close.move(T.REPLY, (132.85, -1.7, 5.5), (133.82, 0.0, 5.32))
        close.move(T.FINALE, (133.2, -1.4, 5.44), (133.82, 0.0, 5.32))
        self._cut(T.REPLY, close)
        self._say(close, [
            ("Generated, not a recording of a bird.", T.REPLY + 4, T.REPLY + 58),
            ("And never played to wild crows.", T.REPLY + 64, T.FINALE - 4),
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
            ("No call has been translated yet.\nThat takes many more witnessed calls.",
             T.FINALE + 6, T.TITLE - 10),
            ("Open source. Bring your crows.", T.TITLE + 50, T.END),
        ])
