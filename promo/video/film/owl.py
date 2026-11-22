"""The owl film: do crows mobbing an owl and a hawk say which, and what the tests found.

It stands alone, and it borrows the feature's narration plumbing, so any of its
scenes can later move into the feature unchanged. Every scene reads its frames
from the owl screenplay.
"""

import math
import random
from pathlib import Path

from .audio import Clip
from .crow import FlyingCrow, PerchedCrow, Plumage
from .director import Camera
from .explainer import Figures
from .feature import Feature
from .kit import Keys, Materials, Palette, Shapes
from .props import CallColors, CaptionLayout, Chip, ScoreBars, Sign, Subtitles
from .sets import Dusk, Lockup, PowerLine, SoundRings
from .timeline import OwlTimeline as T


class Owl:
    """A perched owl facing the camera (-Y), talons at its origin."""

    def __init__(self, stage, location, size=1.0):
        coat = Materials.surface("Owl", "#6b5440", roughness=0.85)
        face = Materials.surface("Owl face", "#a88a66", roughness=0.9)
        eye = Materials.glow("Owl eye", "#f2b03a", 2.5)
        pupil = Materials.surface("Owl pupil", "#050505", roughness=0.1)
        beak = Materials.surface("Owl beak", "#2a2420", roughness=0.4)
        facing = (math.pi / 2.0, 0.0, 0.0)
        self.root = stage.pivot("Owl", location=location)
        self.root.scale = (size, size, size)
        stage.add("Owl body", Shapes.blob("owl body", (0.3, 0.26, 0.36)), coat, self.root,
                  location=(0.0, 0.0, 0.36))
        stage.add("Owl head", Shapes.blob("owl head", (0.25, 0.22, 0.21)), coat, self.root,
                  location=(0.0, 0.0, 0.84))
        for side in (-1, 1):
            stage.add("Owl face", Shapes.disc("owl face", 0.12), face, self.root,
                      location=(side * 0.095, -0.2, 0.86), rotation=facing)
            stage.add("Owl eye", Shapes.disc("owl eye", 0.05), eye, self.root,
                      location=(side * 0.095, -0.215, 0.87), rotation=facing)
            stage.add("Owl pupil", Shapes.disc("owl pupil", 0.022), pupil, self.root,
                      location=(side * 0.095, -0.222, 0.87), rotation=facing)
            stage.add("Owl tuft", Shapes.spike("owl tuft", 0.05, 0.2, sides=5), coat, self.root,
                      location=(side * 0.15, 0.0, 0.98),
                      rotation=(0.0, -math.pi / 2.0 + side * 0.35, 0.0))
        stage.add("Owl beak", Shapes.spike("owl beak", 0.03, 0.09, sides=4), beak, self.root,
                  location=(0.0, -0.2, 0.79), rotation=(0.0, 0.5, -math.pi / 2.0))

    def pop(self, frame):
        Keys.pop(self.root, frame)
        return self

    def leave(self, frame):
        size = tuple(self.root.scale)
        Keys.at(self.root, frame, scale=size)
        Keys.at(self.root, frame + 10, scale=(0.0, 0.0, 0.0))
        return self


class OwlFilm(Feature):
    CLOCK = T
    MOBBERS = [(-1.6, 0.9), (-0.85, 1.0), (-0.1, 0.95), (2.2, 0.9), (2.9, 1.0)]
    OWL_X = 1.05
    HAWK = "#8a5a36"
    YES, NO = CallColors.FLIGHT, CallColors.ALARM
    BOARD_LENS = 28.0

    def build(self):
        self.play = T.PLAY
        self.figures = Figures(self.stats)
        self.subtitles = Subtitles(self.stage, self.fonts, CaptionLayout.of(self.shape))
        self.clips = {name: Clip(Path(self.work) / f"{name}.wav", T.FPS) for name in T.SOUNDS}
        self.dusk = Dusk(self.stage)
        PowerLine(self.stage)
        self.rings = SoundRings(self.stage)
        self.mobbers = []
        self._the_mob()
        self._the_archive()
        self._the_replication()
        self._the_suspects()
        self._the_crowd()
        self._the_roost()
        self._posture()
        self._one_bird()
        self._the_verdict()
        self._the_ask()
        return self.scene

    def _board(self, scene, x, title, title_at):
        """A score board on the floor, filmed square on, with its title above."""
        z = self.FLOOR
        self._light((x, -6.0, z + 4.0))
        self._title(title, (x, 0.0, z + 6.3), title_at)
        return ScoreBars(self.stage, self.fonts, (x, 0.0, z + 1.4))

    def _board_camera(self, name, x, start, end):
        z = self.FLOOR
        camera = Camera(self.stage, name, self.BOARD_LENS)
        camera.move(start, (x - 1.6, -15.5, z + 2.9), (x - 0.6, 0.0, z + 2.9))
        camera.move(end, (x + 0.4, -14.8, z + 2.9), (x - 0.4, 0.0, z + 2.9))
        return camera

    def _hawk(self, name, size):
        return FlyingCrow(self.stage, name, Materials.surface(name, "#b0764a", 0.7), size=size)

    def _mob_call(self, crow, start, direction):
        clip = self.clips["mob"]
        crow.caw(start, clip.envelope())
        for onset in clip.onsets()[::2]:
            self.rings.emit(start + onset, crow.beak_tip(), direction, reach=3.5, count=2)

    def _the_mob(self):
        scene = self.play.scene("mob")
        dice = random.Random(4)
        plumage = Plumage.living()
        caw = scene.line("caw")
        owl = Owl(self.stage, PowerLine.perch(self.OWL_X), size=0.72)
        owl.leave(scene.at("hawk") - 4)
        for index, (x, size) in enumerate(self.MOBBERS):
            crow = PerchedCrow(self.stage, "Mobber", plumage)
            crow.place(PowerLine.perch(x), heading=0.0 if x < self.OWL_X else math.pi)
            crow.root.scale = (size, size, size)
            crow.look(1, yaw=dice.uniform(-0.4, 0.4))
            direction = 1.0 if x < self.OWL_X else -1.0
            self._mob_call(crow, caw.cue + index * 5, direction)
            self._mob_call(crow, scene.at("owl") + dice.randint(0, 20), direction)
            self.mobbers.append(crow)
        hawk = self._hawk("Hawk overhead", 2.6)
        hawk.flap(0)
        hawk.cross(scene.at("hawk") + 2, scene.at("question") + 30,
                   (-9.0, 3.0, 7.6), (11.0, 3.0, 7.9))
        self._title("owl or hawk?", (0.65, 1.0, 6.55), scene.at("question") + 10,
                    size=0.32).leave(scene.end)
        camera = Camera(self.stage, "Mob camera", 40.0)
        camera.move(1, (1.6, -4.2, 4.9), (0.6, 0.0, 5.4))
        camera.move(scene.at("hawk"), (0.8, -6.8, 4.9), (0.6, 0.0, 5.75))
        camera.move(scene.end, (0.5, -7.6, 4.8), (0.6, 0.0, 5.8))
        self._cut(1, camera)
        self._narrate(camera, scene)

    def _the_archive(self):
        scene, z, x = self.play.scene("archive"), self.FLOOR, 200.0
        self._light((x, -6.0, z + 4.0))
        self._title("written down by the recordist", (x, 0.0, z + 5.9), scene.start + 10)
        dice = random.Random(9)
        cards = Materials.glow("Recording card", Palette.SKY_MID, 1.6)
        heard = Materials.glow("Raptor heard", self.HAWK, 2.0)
        for row in range(3):
            for column in range(8):
                loud = dice.random() < 0.3
                card = self.stage.add(
                    "Recording", Shapes.block("recording", (0.7, 0.08, 0.42)),
                    heard if loud else cards,
                    location=(x - 3.5 + column, 0.0, z + 4.6 - row * 0.65))
                Keys.pop(card, scene.at("count") + 6 + row * 8 + column * 2)
                if loud:
                    Keys.at(card, scene.at("masked") + 30, scale=(1.0, 1.0, 1.0))
                    Keys.at(card, scene.at("masked") + 44, scale=(0.0, 0.0, 0.0))
        Sign(self.stage, self.fonts, "144 recordings · 114 recordists", (x, 0.0, z + 2.5), 0.5,
             color=Palette.ACCENT, strength=2.0).pop(scene.at("count") + 30)
        Sign(self.stage, self.fonts, "owl or hawk audible: removed", (x, 0.0, z + 1.8), 0.38,
             color=self.HAWK, strength=2.0).pop(scene.at("masked") + 20)
        Sign(self.stage, self.fonts, "only the crows left", (x, 0.0, z + 1.1), 0.42).pop(
            scene.at("crows") + 4)

        board = x + 26.0
        bars = self._board(scene, board, "owl mob or hawk mob?", scene.at("model"))
        bars.bar(scene.at("score") + 4, 0.0, "0.78", "the archive", CallColors.CALL)

        camera = Camera(self.stage, "Archive camera", self.BOARD_LENS)
        camera.move(scene.start, (x - 1.2, -15.0, z + 2.0), (x, 0.0, z + 2.0))
        camera.move(scene.at("model") - 12, (x + 1.0, -14.2, z + 2.0), (x, 0.0, z + 2.0))
        camera.move(scene.at("model") + 8, (board - 1.6, -15.5, z + 2.9), (board - 0.6, 0.0, z + 2.9))
        camera.move(scene.end, (board + 0.4, -14.8, z + 2.9), (board - 0.4, 0.0, z + 2.9))
        self._cut(scene.start, camera)
        self._narrate(camera, scene)

    def _the_replication(self):
        scene, z, x = self.play.scene("replicate"), self.FLOOR, 260.0
        bars = self._board(scene, x, "a second test, predicted first", scene.at("predict"))
        bars.bar(scene.start + 10, -1.7, "0.78", "the archive", CallColors.CALL)
        Sign(self.stage, self.fonts, "different people · mostly phones", (x, 0.0, z + 5.7), 0.32,
             color=Palette.ACCENT, strength=2.0).pop(scene.at("new") + 6)
        bars.bar(scene.at("score") + 2, 1.7, "0.75", "new recordings", CallColors.FLIGHT)
        camera = self._board_camera("Replication camera", x, scene.start, scene.end)
        self._cut(scene.start, camera)
        self._narrate(camera, scene)

    def _the_suspects(self):
        scene, z, x = self.play.scene("suspects"), self.FLOOR, 300.0
        self._light((x, -6.0, z + 4.0), 4000.0)
        self._title("three suspects", (x, 0.0, z + 5.6), scene.at("three"))
        perch = Materials.glow("Suspect perch", Palette.SKY_MID, 1.5)
        for offset in (-5.0, 0.0):
            self.stage.add("Suspect perch", Shapes.block("suspect perch", (2.4, 0.1, 0.1)),
                           perch, location=(x + offset, 0.0, z + 1.0))

        Owl(self.stage, (x - 5.0, 0.0, z + 1.05), size=2.6).pop(scene.at("name") + 8)
        Chip(self.stage, self.fonts, "a call that means owl", CallColors.ALARM,
             (x - 5.0, 0.0, z + 4.4), size=0.4).pop(scene.at("name") + 20)

        sitting = PerchedCrow(self.stage, "Perched hawk", Plumage.tinted("Hawk", self.HAWK))
        sitting.place((x - 0.6, 0.0, z + 1.05))
        sitting.root.scale = (3.4, 3.4, 3.4)
        Keys.pop(sitting.root, scene.at("posture") + 8, size=1.0)
        flying = self._hawk("Flying hawk", 3.0)
        flying.flap(0)
        flying.root.location = (x + 1.1, 0.0, z + 3.4)
        Keys.pop(flying.root, scene.at("posture") + 30, size=1.0)
        Chip(self.stage, self.fonts, "posture", CallColors.BEGGING, (x, 0.0, z + 4.4),
             size=0.4).pop(scene.at("posture") + 20)

        plumage = Plumage.living()
        dice = random.Random(11)
        for index in range(9):
            crow = PerchedCrow(self.stage, "Crowd crow", plumage)
            crow.place((x + 3.7 + (index % 3) * 0.95 + dice.uniform(-0.2, 0.2), 0.0,
                        z + 0.6 + (index // 3) * 1.0), heading=dice.uniform(-0.5, 0.5))
            crow.root.scale = (1.9, 1.9, 1.9)
            Keys.pop(crow.root, scene.at("crowd") + 6 + index * 4, size=1.0)
        Chip(self.stage, self.fonts, "the crowd", CallColors.CALL, (x + 5.0, 0.0, z + 4.4),
             size=0.4).pop(scene.at("crowd") + 20)

        camera = Camera(self.stage, "Suspects camera", self.BOARD_LENS)
        camera.move(scene.start, (x - 0.6, -16.0, z + 2.4), (x, 0.0, z + 2.6))
        camera.move(scene.end, (x + 0.6, -15.2, z + 2.4), (x, 0.0, z + 2.6))
        self._cut(scene.start, camera)
        self._narrate(camera, scene)

    def _the_crowd(self):
        scene, x = self.play.scene("crowd"), 340.0
        bars = self._board(scene, x, "how much of it is crow sound", scene.at("measure") + 30)
        bars.bar(scene.at("bars") + 4, 1.7, "0.71", "crow sound alone", CallColors.BEGGING)
        bars.bar(scene.at("bars") + 40, -1.7, "0.78", "the model", CallColors.CALL)
        camera = self._board_camera("Crowd camera", x, scene.start, scene.at("roost"))
        self._cut(scene.start, camera)
        self._narrate(camera, scene, until=scene.at("roost"))

    def _the_roost(self):
        scene = self.play.scene("crowd")
        cut = scene.at("roost")
        dice = random.Random(13)
        plumage = Plumage.living()
        centre = 62.0
        for index in range(36):
            y, lift = PowerLine.WIRES[index % 3]
            crow = PerchedCrow(self.stage, "Roosting", plumage)
            crow.place((centre - 6.0 + dice.uniform(0.0, 12.0), y,
                        PowerLine.HEIGHT + lift + PowerLine.WIRE),
                       heading=0.0 if dice.random() < 0.5 else math.pi)
            crow.root.scale = (0.9, 0.9, 0.9)
            Keys.pop(crow.root, cut - 20 + index * 2, size=1.0)
            for frame in range(cut, scene.end, 30):
                crow.look(frame + dice.randint(0, 20), yaw=dice.uniform(-0.6, 0.6))
        Sign(self.stage, self.fonts, "a roost: no predator", (centre - 1.2, 1.0, 7.1), 0.34,
             color=Palette.ACCENT, strength=2.0).pop(cut + 30)
        Sign(self.stage, self.fonts, "scores like an owl mob", (centre - 1.2, 1.0, 6.65), 0.26).pop(
            scene.line("roost").spoken - 20)
        camera = Camera(self.stage, "Roost camera", 32.0)
        camera.move(cut, (centre - 2.0, -9.0, 4.6), (centre - 1.0, 0.0, 5.8))
        camera.move(scene.end, (centre + 0.5, -10.0, 4.5), (centre - 0.6, 0.0, 5.85))
        self._cut(cut, camera)
        self._narrate(camera, scene, since=cut)

    def _posture(self):
        scene, x = self.play.scene("posture"), 380.0
        z = self.FLOOR
        bars = self._board(scene, x, "with the predator sitting still", scene.start + 30)
        bars.bar(scene.at("perched") + 20, -1.7, "0.54", "both perched",
                 CallColors.CALL)
        Sign(self.stage, self.fonts, "only 15 perched hawks", (x - 1.7, 0.0, z + 3.4), 0.3,
             color=self.NO, strength=2.0).pop(scene.at("few") + 10)
        bars.bar(scene.at("hawks") + 40, 1.7, "0.86", "hawk: still vs flying",
                 CallColors.BEGGING)
        camera = self._board_camera("Posture camera", x, scene.start, scene.end)
        self._cut(scene.start, camera)
        self._narrate(camera, scene)

    def _one_bird(self):
        scene, z, x = self.play.scene("single"), self.FLOOR, 420.0
        self._light((x - 5.0, -5.0, z + 4.0))
        crow = PerchedCrow(self.stage, "Single", Plumage.living())
        crow.place((x - 5.6, 0.0, z + 1.05))
        crow.root.scale = (4.0, 4.0, 4.0)
        self.stage.add("Single perch", Shapes.block("single perch", (2.4, 0.1, 0.1)),
                       Materials.glow("Single perch", Palette.SKY_MID, 1.5),
                       location=(x - 5.6, 0.0, z + 1.0))
        clip = self.clips["single"]
        start = scene.line("one").cue
        crow.caw(start, clip.envelope())
        tip = (x - 5.6 + 0.39 * 4.0, 0.0, z + 1.05 + 0.47 * 4.0)
        for onset in clip.onsets():
            self.rings.emit(start + onset, tip, 1.0, reach=4.0)
        bars = ScoreBars(self.stage, self.fonts, (x + 2.0, 0.0, z + 1.4))
        bars.bar(scene.at("score") + 10, 0.0, "0.61", "one crow, owl vs hawk", CallColors.CALL)
        camera = Camera(self.stage, "Single camera", self.BOARD_LENS)
        camera.move(scene.start, (x - 3.0, -15.5, z + 2.6), (x - 2.0, 0.0, z + 2.6))
        camera.move(scene.end, (x - 1.2, -15.0, z + 2.6), (x - 1.0, 0.0, z + 2.6))
        self._cut(scene.start, camera)
        self._narrate(camera, scene)

    def _the_verdict(self):
        scene, z, x = self.play.scene("verdict"), self.FLOOR, 480.0
        self._light((x, -6.0, z + 4.0))
        self._title("where it stands", (x, 0.0, z + 5.0), scene.start + 10)
        Chip(self.stage, self.fonts, "owl mobs sound different: yes", self.YES,
             (x, 0.0, z + 3.3), size=0.5).pop(scene.at("yes") + 8)
        Sign(self.stage, self.fonts, "held up in new recordings", (x, 0.0, z + 2.5), 0.34).pop(
            scene.at("yes") + 40)
        Chip(self.stage, self.fonts, "a call that means owl: not shown", self.NO,
             (x, 0.0, z + 1.3), size=0.5).pop(scene.at("no") + 8)
        Sign(self.stage, self.fonts, "likeliest: a still owl draws a bigger crowd",
             (x, 0.0, z + 0.2), 0.36, color=Palette.ACCENT, strength=2.0).pop(
            scene.at("story") + 30)
        camera = Camera(self.stage, "Verdict camera", self.BOARD_LENS)
        camera.move(scene.start, (x - 0.8, -16.0, z + 2.6), (x, 0.0, z + 2.6))
        camera.move(scene.end, (x + 0.8, -15.2, z + 2.6), (x, 0.0, z + 2.6))
        self._cut(scene.start, camera)
        self._narrate(camera, scene)

    def _the_ask(self):
        scene = self.play.scene("ask")
        hawk = PerchedCrow(self.stage, "Sitting hawk", Plumage.tinted("Hawk", self.HAWK))
        hawk.place(PowerLine.perch(self.OWL_X))
        hawk.root.scale = (1.15, 1.15, 1.15)
        Keys.pop(hawk.root, scene.start - 2, size=1.0)
        hawk.look(scene.start, yaw=-0.6)
        for index, crow in enumerate(self.mobbers):
            direction = 1.0 if crow.root.location.x < self.OWL_X else -1.0
            self._mob_call(crow, scene.at("hawk") + 30 + index * 6, direction)
        Lockup(self.stage, self.fonts, self.logo, (-1.4, 2.0, 7.45), size=0.8).reveal(
            scene.at("title") + 20)
        self._flock(scene.at("title"))
        camera = Camera(self.stage, "Ask camera", 32.0)
        camera.move(scene.start, (0.9, -5.4, 4.9), (0.7, 0.0, 5.5))
        camera.move(scene.at("title"), (0.6, -6.8, 4.7), (0.8, 0.0, 5.9))
        camera.move(scene.end, (0.8, -7.6, 4.7), (0.9, 0.0, 5.95))
        self._cut(scene.start, camera)
        self._narrate(camera, scene)
