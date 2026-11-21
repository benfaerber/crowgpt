"""The feature: six minutes on why the project exists, what it found and how to help.

Told in the first person along the same power line as the other two films.
Nothing here holds a frame number: every scene asks the screenplay when its
lines are spoken, so the picture follows the narration.
"""

import math
import random
import re
from pathlib import Path

from .audio import Clip
from .crow import FlyingCrow, PerchedCrow, Plumage
from .director import Camera, Film
from .explainer import Figures
from .kit import Keys, Materials, Palette, Shapes
from .props import (Arrow, CallColors, CallGlyph, CaptionLayout, Chip, ContextColors, Dog,
                    Emitter, Mask, Peanut, Person, Phone, ScoreBars, Sign, Subtitles, TagTest,
                    Website)
from .sets import Dusk, Lattice, Lockup, PowerLine, SoundRings, Spectrogram, TokenStream
from .timeline import FeatureTimeline as T


class Feature(Film):
    CLOCK = T
    FAMILY = [("Thrasher", -1.5, 1.0), ("Ripjaw", -0.75, 1.0), ("Edgar", 0.0, 0.95),
              ("Killer", 0.75, 0.85), ("Shredder", 1.5, 0.85)]
    FLOOR = 9.0
    TYPES = [("alarm", "alarm call", CallColors.ALARM, None),
             ("flight", "flight call", CallColors.FLIGHT,
              "XC172878 · Paul Marvin · CC BY-NC-SA 4.0"),
             ("call", "call", CallColors.CALL, None),
             ("begging", "begging", CallColors.BEGGING, None),
             ("song", "song", CallColors.SONG, "XC807484 · Barry Edmonston · CC BY-NC-SA 4.0")]
    TYPES_X, TYPES_STEP = 200.0, 30.0
    PLACEHOLDER = re.compile(r"\{([a-z_.]+)\}")

    def build(self):
        self.play = T.PLAY
        self.figures = Figures(self.stats)
        self.subtitles = Subtitles(self.stage, self.fonts, CaptionLayout.of(self.shape))
        self.clips = {name: Clip(Path(self.work) / f"{name}.wav", T.FPS) for name in T.SOUNDS}
        self.family = {}
        self.dusk = Dusk(self.stage)
        PowerLine(self.stage)
        self.rings = SoundRings(self.stage)
        self._open()
        self._the_murder()
        self._the_mask()
        self._the_types()
        self._cawdex()
        self._the_precedent()
        self._the_hypothesis()
        self._the_app()
        self._crowgpt()
        self._the_website()
        self._finale()
        return self.scene

    def _light(self, location, energy=2500.0):
        lamp = self.dusk.lamp("Set light", "POINT", location, (0.0, 0.0, 0.0), "#dfe4ff", energy)
        lamp.data.shadow_soft_size = 1.5

    def _worded(self, line):
        return self.PLACEHOLDER.sub(lambda found: self.figures.text(found.group(1)), line.text)

    def _narrate(self, camera, scene, since=0, until=None):
        """Caption every line of the scene that starts while this camera is live."""
        for line in scene.lines:
            if line.text and since <= line.start and (until is None or line.start < until):
                self.subtitles.show(camera, self._worded(line), line.start + 2, line.spoken + 8)

    def _title(self, body, location, frame, size=0.62):
        return Sign(self.stage, self.fonts, body, location, size).pop(frame)

    def _open(self):
        scene = self.play.scene("open")
        murder = self.play.scene("murder")
        dice = random.Random(2)
        plumage = Plumage.living()
        for name, x, size in self.FAMILY:
            crow = PerchedCrow(self.stage, name, plumage).place(PowerLine.perch(x))
            crow.root.scale = (size, size, size)
            self.family[name] = crow
            if name == "Edgar":
                continue
            for frame in range(1, murder.end, 34):
                crow.look(frame + dice.randint(0, 12), yaw=dice.uniform(-0.9, 0.4),
                          tilt=dice.uniform(-0.2, 0.2))
        edgar = self.family["Edgar"]
        caw = scene.line("caw")
        edgar.look(1, yaw=-0.5)
        edgar.look(caw.cue - 2, yaw=0.0)
        self._call_out(edgar, self.clips["edgar"], caw.cue, 1.0)
        edgar.look(scene.at("promise"), yaw=0.0)
        edgar.look(scene.at("promise") + 14, yaw=-0.7, tilt=0.2)
        for frame in range(scene.at("promise") + 40, murder.end, 34):
            edgar.look(frame + dice.randint(0, 12), yaw=dice.uniform(-0.9, 0.4),
                       tilt=dice.uniform(-0.2, 0.2))
        camera = Camera(self.stage, "Open camera", 40.0)
        camera.move(1, (1.5, -3.0, 5.05), (0.3, 0.0, 5.34))
        camera.move(scene.at("promise"), (1.0, -1.9, 5.12), (0.3, 0.0, 5.34))
        camera.move(scene.end, (2.0, -7.6, 4.4), (0.15, 0.0, 5.42))
        self._cut(1, camera)
        self._narrate(camera, scene)

    def _the_murder(self):
        scene = self.play.scene("murder")
        for index, (name, x, _) in enumerate(self.FAMILY):
            Peanut(self.stage, (x + 0.24, 0.0, PowerLine.HEIGHT + 0.045)).toss(
                scene.at("peanuts") + 14 + index * 6)
            self.family[name].look(scene.at("peanuts") + 40 + index * 6, yaw=-0.2, tilt=0.0)
        for key, names in (("parents", ("Thrasher", "Ripjaw")),
                           ("fledglings", ("Killer", "Shredder")), ("edgar", ("Edgar",))):
            for index, name in enumerate(names):
                x = self.family[name].root.location.x
                Sign(self.stage, self.fonts, name, (x, 0.0, PowerLine.HEIGHT + 0.62), 0.15).pop(
                    scene.at(key) + 6 + index * 14).leave(scene.end)
        killer = self.family["Killer"]
        reply = scene.line("killer").spoken - 22
        killer.look(reply - 14, yaw=-0.9, tilt=0.0)
        for beat in range(3):
            Keys.axis(killer.jaw, reply + beat * 9, "rotation_euler", 1, 0.0)
            Keys.axis(killer.jaw, reply + beat * 9 + 4, "rotation_euler", 1, 0.5)
            Keys.axis(killer.jaw, reply + beat * 9 + 8, "rotation_euler", 1, 0.0)
        camera = Camera(self.stage, "Murder camera", 40.0)
        camera.move(scene.start, (2.2, -8.5, 4.3), (0.1, 0.0, 5.45))
        camera.move(scene.at("killer"), (1.4, -6.0, 4.55), (0.2, 0.0, 5.42))
        camera.move(scene.end, (1.6, -4.4, 4.8), (0.55, 0.0, 5.4))
        self._cut(scene.start, camera)
        self._narrate(camera, scene)

    def _the_mask(self):
        scene, z = self.play.scene("mask"), self.FLOOR
        perch = Materials.glow("Mask perch", Palette.SKY_MID, 1.5)
        self._light((-35.5, -4.5, z + 2.0), 6000.0)
        self._light((-30.0, -4.0, z + 2.5), 2500.0)
        person = Person(self.stage, (-29.4, 0.0, z - 0.3))
        person.root.scale = (1.5, 1.5, 1.5)
        Mask(self.stage, person)
        person.pop(scene.at("mask") + 8)
        scold = scene.line("scold")
        clip = self.clips["real"]
        plumage = Plumage.living()
        rows = [((-36.4, -34.6), 0.0, z, 2.8, scene.start + 6, 0),
                ((-37.6, -36.1, -34.6, -33.1), 1.6, z + 2.4, 2.0, scene.at("others") + 10, 14)]
        for xs, y, height, size, arrive, lag in rows:
            rail = self.stage.add(
                "Mask perch", Shapes.block("mask perch", (xs[-1] - xs[0] + 1.6, 0.1, 0.1)),
                perch, location=((xs[0] + xs[-1]) / 2.0, y, height - 0.05))
            Keys.pop(rail, arrive - 4)
            for index, x in enumerate(xs):
                crow = PerchedCrow(self.stage, "Scolder", plumage).place((x, y, height))
                crow.root.scale = (size, size, size)
                Keys.pop(crow.root, arrive + index * 7)
                start = max(scold.cue, arrive + index * 7 + 16) + lag + index * 5
                crow.caw(start, clip.envelope())
                tip = (x + 0.39 * size, y, height + 0.35 * size)
                for onset in clip.onsets():
                    self.rings.emit(start + onset, tip, 1.0, reach=4.5)
        self._title("years later", (-33.5, 0.0, z + 4.1), scold.start + 10)
        camera = Camera(self.stage, "Mask camera", 35.0)
        camera.move(scene.start, (-31.6, -14.5, z + 0.9), (-33.0, 0.0, z + 1.1))
        camera.move(scene.end, (-34.2, -13.0, z + 0.9), (-33.0, 0.0, z + 1.1))
        self._cut(scene.start, camera)
        self._narrate(camera, scene)

    def _the_types(self):
        scene, z = self.play.scene("types"), self.FLOOR
        camera = Camera(self.stage, "Types camera", 28.0)
        left = self.TYPES_X + 0.4
        for index, (key, body, color, credit) in enumerate(self.TYPES):
            width = Chip.width(body, 0.36)
            Chip(self.stage, self.fonts, body, color, (left + width / 2.0, 1.0, z + 4.75),
                 size=0.36).pop(scene.at("chips") + 30 + index * 9)
            left += width + 0.3
            line, clip = scene.line(key), self.clips[key]
            x = self.TYPES_X + index * self.TYPES_STEP
            heard = Spectrogram(self.stage, f"Type {key}", clip.spectrogram(48, 14),
                                (x, 0.0, z))
            heard.rise(line.cue, clip.frames)
            Chip(self.stage, self.fonts, body, color, (x + 6.0, 1.0, z + 3.5),
                 size=0.5).pop(line.start + 8)
            if credit:
                Sign(self.stage, self.fonts, credit, (x + 6.0, -2.9, z - 0.75), 0.24,
                     strength=0.9).pop(line.start + 8)
            arrive = scene.start if index == 0 else line.start + 10
            for frame, drift in ((arrive, -0.5), (line.end - 14, 0.5)):
                camera.move(frame, (x + 3.0 + drift, -13.0, z + 2.6),
                            (x + 6.0 + drift, 0.0, z + 0.5))
        self._cut(scene.start, camera)
        self._narrate(camera, scene)

    def _cawdex(self):
        scene, z = self.play.scene("cawdex"), self.FLOOR
        x = 360.0
        self._light((x, -6.0, z + 4.0))
        self._title("CawDex", (x, 0.0, z + 4.4), scene.start + 12, size=0.9)
        strip = self.stage.add("Reading", Shapes.block("reading", (9.0, 0.05, 0.1)),
                               Materials.glow("Reading", Palette.SKY_MID, 1.5),
                               location=(x, 0.0, z + 2.4))
        Keys.at(strip, scene.at("name") + 20, scale=(0.0, 1.0, 1.0))
        Keys.at(strip, scene.at("name") + 40, scale=(1.0, 1.0, 1.0))
        found = [("alarm call", CallColors.ALARM, -3.3), ("call", CallColors.CALL, -1.0),
                 ("alarm call", CallColors.ALARM, 1.2), ("flight call", CallColors.FLIGHT, 3.4)]
        for index, (body, color, offset) in enumerate(found):
            Chip(self.stage, self.fonts, body, color, (x + offset, -0.1, z + 3.05),
                 size=0.3).pop(scene.at("name") + 46 + index * 10)
        archive = scene.at("archive")
        Sign(self.stage, self.fonts, f"{self.figures.text('credits.recordings')} recordings",
             (x, 0.0, z + 0.9), 0.7, color=Palette.ACCENT, strength=2.0).pop(archive + 10)
        Sign(self.stage, self.fonts,
             f"{self.figures.text('credits.recordists')} recordists · Xeno-canto",
             (x, 0.0, z + 0.1), 0.4).pop(archive + 34)

        board = (x + 26.0, 0.0, z + 1.4)
        self._light((board[0], -6.0, z + 4.0))
        bars = ScoreBars(self.stage, self.fonts, board)
        self._title("telling alarm calls apart", (board[0], 0.0, z + 6.3), scene.at("weak"))
        bars.bar(scene.at("weak") + 16, -1.7, self.figures.text("auc.alarm.weak"),
                 "archive tags", CallColors.ALARM)
        bars.bar(scene.at("clean") + 30, 1.7, self.figures.text("auc.alarm.clean"),
                 "checked by hand", CallColors.FLIGHT)

        camera = Camera(self.stage, "CawDex camera", 28.0)
        camera.move(scene.start, (x - 1.5, -15.0, z + 2.4), (x, 0.0, z + 2.3))
        camera.move(scene.at("weak") - 16, (x + 1.0, -14.0, z + 2.4), (x, 0.0, z + 2.3))
        camera.move(scene.at("weak") + 8, (board[0] - 1.6, -15.5, z + 2.9), (board[0] - 0.6, 0.0, z + 2.9))
        camera.move(scene.end, (board[0] + 0.4, -14.5, z + 2.9), (board[0] - 0.6, 0.0, z + 2.9))
        self._cut(scene.start, camera)
        self._narrate(camera, scene)

    def _the_precedent(self):
        scene, z = self.play.scene("precedent"), self.FLOOR
        stops = {"question": -120.0, "vervet": -150.0, "chickadee": -180.0, "jay": -210.0}
        for x in stops.values():
            self._light((x, -6.0, z + 4.0))

        x = stops["question"]
        Chip(self.stage, self.fonts, "alarm call", CallColors.ALARM, (x - 2.6, 0.0, z + 2.2),
             size=0.6).pop(scene.start + 8)
        Arrow(self.stage, (x - 0.1, 0.0, z + 2.2), 1.9).pop(scene.start + 40)
        Sign(self.stage, self.fonts, "?", (x + 3.1, 0.0, z + 1.5), 2.0, color=Palette.ACCENT,
             strength=2.5).pop(scene.start + 52)

        x = stops["vervet"]
        self._title("vervet monkeys", (x, 0.0, z + 5.2), scene.at("vervet"))
        threats = [("leopard", "#efb057", "up a tree", (0.9, 0.7, 0.9, 0.6, 0.8, 0.5)),
                   ("eagle", "#6ea8fe", "into the bushes", (0.3, 1.0, 0.2, 0.25, 0.9, 0.2)),
                   ("snake", "#7bd88f", "stand and look", (0.5, 0.55, 0.6, 0.65, 0.7, 0.75))]
        for index, (threat, color, action, pattern) in enumerate(threats):
            column = x + (index - 1) * 5.0
            frame = scene.at("vervet") + 30 + index * 26
            Chip(self.stage, self.fonts, threat, color, (column, 0.0, z + 3.9), size=0.46).pop(frame)
            CallGlyph(self.stage, (column, 0.0, z + 2.3), pattern, color).pop(frame + 8)
            act = scene.at("actions") + 40 + index * 30
            arrow = Arrow(self.stage, (column, 0.0, z + 2.0), 1.1)
            arrow.root.rotation_euler = (0.0, math.pi / 2.0, 0.0)
            arrow.pop(act)
            Sign(self.stage, self.fonts, action, (column, 0.0, z + 0.2), 0.36,
                 color=Palette.ACCENT).pop(act + 8)

        x = stops["chickadee"]
        self._title("chickadees", (x, 0.0, z + 5.2), scene.at("chickadee"))
        rows = [("a big owl", "chick-a-dee dee", "#6ea8fe", 3.4, 30),
                ("a small owl, more dangerous", "chick-a-dee dee dee dee dee", "#f27070", 1.2, 86)]
        for threat, song, color, height, delay in rows:
            frame = scene.at("chickadee") + delay
            Chip(self.stage, self.fonts, threat, color, (x - 4.4, 0.0, z + height),
                 size=0.32).pop(frame)
            Sign(self.stage, self.fonts, song, (x + 3.0, 0.0, z + height - 0.14), 0.38).pop(
                frame + 14)

        x = stops["jay"]
        self._title("Siberian jays", (x, 0.0, z + 5.2), scene.at("jay"))
        jay = PerchedCrow(self.stage, "Jay", Plumage.tinted("Jay", "#8d6a52")).place(
            (x - 5.4, 0.0, z + 1.4))
        jay.root.scale = (3.2, 3.2, 3.2)
        self.stage.add("Jay perch", Shapes.block("jay perch", (2.0, 0.1, 0.1)),
                       Materials.glow("Jay perch", Palette.SKY_MID, 1.5),
                       location=(x - 5.4, 0.0, z + 1.35))
        hawks = [("hawk perched", (0.5, 0.5, 0.0, 0.5, 0.5, 0.0, 0.5, 0.5)),
                 ("hawk searching", (0.3, 0.6, 0.9, 0.6, 0.3, 0.6, 0.9, 0.6)),
                 ("hawk attacking", (1.0, 0.9, 1.0, 0.9, 1.0, 0.9, 1.0, 0.9))]
        for index, (state, pattern) in enumerate(hawks):
            height = z + 3.6 - index * 1.5
            frame = scene.at("jay") + 60 + index * 26
            Chip(self.stage, self.fonts, state, ContextColors.AIR, (x - 0.4, 0.0, height),
                 size=0.36).pop(frame)
            CallGlyph(self.stage, (x + 4.6, 0.0, height - 0.3), pattern, Palette.ACCENT,
                      height=0.9).pop(frame + 8)

        camera = Camera(self.stage, "Precedent camera", 28.0)
        moves = [(scene.start, "question", -0.8), (scene.at("vervet") - 14, "question", 0.8),
                 (scene.at("vervet") + 10, "vervet", -0.8), (scene.at("chickadee") - 14, "vervet", 0.8),
                 (scene.at("chickadee") + 10, "chickadee", -0.8), (scene.at("jay") - 14, "chickadee", 0.8),
                 (scene.at("jay") + 10, "jay", -0.8), (scene.end, "jay", 0.8)]
        for frame, stop, drift in moves:
            camera.move(frame, (stops[stop] + drift, -16.0, z + 2.6), (stops[stop], 0.0, z + 2.4))
        self._cut(scene.start, camera)
        self._narrate(camera, scene)

    def _the_hypothesis(self):
        scene, z = self.play.scene("hypothesis"), self.FLOOR
        ground, air = (151.2, 0.0, z), (164.8, 0.0, z + 2.0)
        self.stage.add("Ground plate", Shapes.block("ground plate", (3.0, 2.4, 0.1)),
                       Materials.surface("Ground plate", "#15121c", 0.35, 0.5),
                       location=(151.2, 0.0, z - 0.05))
        self._light((150.0, -5.0, z + 4.0))
        self._light((165.0, -5.0, z + 5.0))
        Dog(self.stage, ground, size=1.7).pop(scene.at("threats") + 20)
        hawk = FlyingCrow(self.stage, "Hawk", Materials.surface("Hawk", "#b0764a", 0.7), size=3.4)
        hawk.root.rotation_euler = (0.5, 0.0, 0.0)
        hawk.flap(scene.start)
        for step in range(0, scene.end - scene.start + 30, 30):
            lift = 0.25 if (step // 30) % 2 else -0.25
            hawk.root.location = (air[0], air[1], air[2] + lift)
            hawk.root.keyframe_insert("location", frame=scene.start + step)
        Keys.at(hawk.root, scene.at("threats") + 70, scale=(0.0, 0.0, 0.0))
        Keys.at(hawk.root, scene.at("threats") + 82, scale=(3.4, 3.4, 3.4))
        Chip(self.stage, self.fonts, "dog visible", ContextColors.GROUND,
             (151.4, 0.0, z + 4.3), size=0.5).pop(scene.at("tags") + 40)
        Chip(self.stage, self.fonts, "raptor overhead", ContextColors.AIR,
             (164.0, 0.0, z + 5.3), size=0.5).pop(scene.at("tags") + 60)

        test = TagTest(self.stage, (158.0, 0.0, z + 2.1))
        collect = scene.at("collect")
        self._title("do the calls differ?", (158.0, 0.0, z + 5.0), collect)
        test.collect(collect + 12, (151.6, -0.4, z + 1.6), ContextColors.GROUND, (-1.9, -0.75))
        test.collect(collect + 20, (164.4, -0.4, z + 2.2), ContextColors.AIR, (1.9, 0.75))
        test.circle(scene.at("circle") + 8, ContextColors.GROUND, (-1.9, -0.75))
        test.circle(scene.at("circle") + 16, ContextColors.AIR, (1.9, 0.75))
        later = zip(ContextColors.LATER, (152.5, 158.0, 163.5),
                    ((-1.9, 1.2), (0.0, 0.0), (1.9, -1.2)))
        for index, ((tag, color), x, landing) in enumerate(later):
            frame = scene.at("later") + 44 + index * 22
            Chip(self.stage, self.fonts, tag, color, (x, 0.0, z + 6.5), size=0.42).pop(frame)
            test.collect(frame + 10, (x, -0.4, z + 6.2), color, landing, count=9, spread=0.4)

        camera = Camera(self.stage, "Hypothesis camera", 28.0)
        camera.move(scene.start, (156.8, -18.0, z + 2.9), (158.0, 0.0, z + 2.5))
        camera.move(scene.end, (159.2, -17.4, z + 2.9), (158.0, 0.0, z + 2.5))
        self._cut(scene.start, camera)
        self._narrate(camera, scene)

    def _the_app(self):
        scene, z = self.play.scene("app"), self.FLOOR + 1.3
        self._light((70.5, -5.0, z + 2.5), 1500.0)
        record = scene.at("record")
        phone = Phone(self.stage, self.fonts, (72.0, 0.0, z), self.clips["real"].envelope())
        phone.record(record + 10, 60).keep(record + 78)
        Chip(self.stage, self.fonts, "alarm call", CallColors.ALARM, (74.5, 0.0, z + 0.9),
             size=0.3).pop(record + 92)
        Chip(self.stage, self.fonts, "dog visible", ContextColors.GROUND, (74.55, 0.0, z + 0.2),
             size=0.3).pop(record + 106)
        Sign(self.stage, self.fonts, f"{self.figures.text('labels.minutes')} minutes",
             (74.6, 0.0, z + 1.7), 0.52, color=Palette.ACCENT, strength=2.0).pop(
            scene.at("minutes") + 20)
        camera = Camera(self.stage, "App camera", 35.0)
        camera.move(scene.start, (71.4, -9.0, z + 0.2), (72.6, 0.0, z))
        camera.move(scene.end, (74.0, -7.8, z + 0.2), (73.0, 0.0, z))
        self._cut(scene.start, camera)
        self._narrate(camera, scene)

    def _crowgpt(self):
        scene, z = self.play.scene("crowgpt"), self.FLOOR
        first, second = scene.line("v1"), scene.line("v2")
        crowbot, generated = self.clips["crowbot"], self.clips["generated"]
        prompt = (104.0, 0.0, z + 1.6)
        Chip(self.stage, self.fonts, "call type", Palette.CREAM, prompt, size=0.36).pop(
            scene.at("prompt") + 50)
        lattice = Lattice(self.stage, (110.0, 0.0, z + 1.6))
        self._title("CrowGPT", (110.0, 0.0, z + 3.5), scene.at("prompt") + 10, size=0.6)
        Sign(self.stage, self.fonts, "version one", (110.0, 0.0, z - 0.9), 0.4,
             color=Palette.ACCENT).pop(first.start + 4).leave(second.start)
        Sign(self.stage, self.fonts, "version two", (110.0, 0.0, z - 0.9), 0.4,
             color=Palette.ACCENT).pop(second.start + 4)
        lattice.think(first.cue, first.cue + crowbot.frames)
        for onset in crowbot.onsets():
            self.rings.emit(first.cue + onset, (lattice.exit_x + 0.8, 0.0, z + 1.6), 1.0)
        said = Spectrogram(self.stage, "Said", generated.spectrogram(self.COLUMNS, self.BANDS),
                           (116.0, 0.0, z))
        said.rise(second.cue, generated.frames)
        tokens = TokenStream(self.stage, Emitter(prompt), lattice, said)
        tokens.flow(second.cue - 2, generated.frames)
        lattice.think(second.start, second.cue + generated.frames)

        camera = Camera(self.stage, "CrowGPT camera", 28.0)
        for frame, x in ((scene.start, 105.5), (scene.at("prompt") + 60, 108.5),
                         (second.start, 110.5), (second.cue + 30, 119.5)):
            camera.move(frame, (x - 2.5, -13.0, z + 1.9), (x + 0.5, 0.0, z + 1.2))
        self._cut(scene.start, camera)

        cut = second.cue + 46
        reply = PerchedCrow(self.stage, "Generated crow", Plumage.generated())
        reply.place(PowerLine.perch(134.0), heading=math.pi)
        self._call_out(reply, generated, second.cue, -1.0, not_before=cut - 12)
        close = Camera(self.stage, "Reply camera", 55.0)
        close.move(cut, (132.85, -1.7, 5.5), (133.82, 0.0, 5.32))
        close.move(scene.end, (133.5, -1.25, 5.42), (133.82, 0.0, 5.32))
        self._cut(cut, close)
        self._narrate(camera, scene, until=cut)
        self._narrate(close, scene, since=cut)

    def _the_website(self):
        scene = self.play.scene("website")
        centre = (-60.0, 0.0, self.FLOOR + 2.0)
        self._light((-61.5, -6.0, centre[2] + 2.0), 1800.0)
        drop = scene.at("drop")
        Website(self.stage, self.fonts, centre).drop(drop + 20).results(drop + 80).keep(
            scene.at("keep") + 30)
        camera = Camera(self.stage, "Website camera", 35.0)
        camera.move(scene.start, (-61.0, -13.0, centre[2] + 0.2), (-60.0, 0.0, centre[2] - 0.9))
        camera.move(scene.end, (-59.2, -12.0, centre[2] + 0.2), (-60.0, 0.0, centre[2] - 0.9))
        self._cut(scene.start, camera)
        self._narrate(camera, scene)

    def _finale(self):
        scene = self.play.scene("finale")
        dice = random.Random(8)
        for crow in self.family.values():
            crow.look(scene.start - 1, yaw=0.0)
            for frame in range(scene.start + 10, scene.at("title"), 40):
                crow.look(frame + dice.randint(0, 14), yaw=dice.uniform(-0.9, 0.3),
                          tilt=dice.uniform(-0.25, 0.25))
            crow.look(T.END, yaw=dice.uniform(-0.9, -0.5), tilt=0.0)
        Lockup(self.stage, self.fonts, self.logo, (-1.9, 2.0, 7.45), size=0.8).reveal(
            scene.at("title") + 30)
        self._flock(scene.at("title"))
        camera = Camera(self.stage, "Finale camera", 32.0)
        camera.move(scene.start, (0.9, -4.6, 4.9), (0.3, 0.0, 5.5))
        camera.move(scene.at("title"), (0.4, -6.2, 4.7), (0.7, 0.0, 5.8))
        camera.move(scene.end, (0.8, -7.4, 4.7), (0.8, 0.0, 5.85))
        self._cut(scene.start, camera)
        self._narrate(camera, scene)
