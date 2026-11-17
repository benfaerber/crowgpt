"""Things the explainer points at: labels, a phone, a map of the valley, a dog."""

import math
import random

from .kit import Keys, Materials, Palette, Shapes


class CallColors:
    """The five classes, in the colours the app and the promo give them."""

    ALARM = "#f27070"
    FLIGHT = "#6bd28a"
    CALL = "#6ea8fe"
    BEGGING = "#efb057"
    SONG = "#c58af9"


class Chip:
    """A coloured tag with dark lettering, facing the camera."""

    LETTER = 0.52

    def __init__(self, stage, fonts, body, color, location, size=0.4):
        self.root = stage.pivot(f"Chip {body}", location=location)
        width = self.width(body, size)
        plate = Materials.glow(f"Chip {body}", color, 0.9)
        ink = Materials.flat(f"Chip ink {body}", Palette.INK)
        stage.add(f"Chip plate {body}", Shapes.block("chip", (width, 0.08, size * 1.7)),
                  plate, self.root)
        label = stage.text(f"Chip label {body}", body, fonts.display, size, ink,
                           (0.0, -0.05, -size * 0.34), extrude=0.005, align="CENTER")
        label.parent = self.root

    @classmethod
    def width(cls, body, size):
        return size * (cls.LETTER * len(body) + 1.1)

    def pop(self, frame):
        Keys.pop(self.root, frame, frames=10)
        return self

    def single_out(self, frame, hold=60):
        Keys.at(self.root, frame, scale=(1.0, 1.0, 1.0))
        Keys.at(self.root, frame + 10, scale=(1.35, 1.35, 1.35))
        Keys.at(self.root, frame + hold, scale=(1.35, 1.35, 1.35))
        Keys.at(self.root, frame + hold + 12, scale=(1.0, 1.0, 1.0))
        return self


class Sign:
    """Plain glowing lettering standing in the scene."""

    def __init__(self, stage, fonts, body, location, size, color=Palette.CREAM, strength=1.5):
        material = Materials.glow(f"Sign {body}", color, strength)
        self.item = stage.text(f"Sign {body}", body, fonts.display, size, material,
                               location, extrude=size * 0.04, align="CENTER")

    def pop(self, frame):
        Keys.pop(self.item, frame, frames=10)
        return self

    def leave(self, frame):
        Keys.at(self.item, frame - 8, scale=(1.0, 1.0, 1.0))
        Keys.at(self.item, frame, scale=(0.0, 0.0, 0.0))
        return self


class Arrow:
    """Points along +X from its tail."""

    def __init__(self, stage, tail, length, color=Palette.ACCENT):
        material = Materials.glow("Arrow", color, 2.0)
        self.root = stage.pivot("Arrow", location=tail)
        stage.add("Arrow shaft", Shapes.block("shaft", (length - 0.35, 0.07, 0.07)),
                  material, self.root, location=((length - 0.35) / 2.0, 0.0, 0.0))
        stage.add("Arrow head", Shapes.spike("arrowhead", 0.2, 0.38, sides=4),
                  material, self.root, location=(length - 0.38, 0.0, 0.0))

    def pop(self, frame):
        Keys.at(self.root, frame - 1, scale=(0.0, 1.0, 1.0))
        Keys.at(self.root, frame + 10, scale=(1.0, 1.0, 1.0))
        return self


class Person:
    def __init__(self, stage, location, height=1.9):
        material = Materials.glow("Person", "#d9cdbb", 0.8)
        self.root = stage.pivot("Person", location=location)
        stage.add("Person body", Shapes.spike("person body", 0.36, height * 0.68, tip=0.2, sides=8),
                  material, self.root, rotation=(0.0, -math.pi / 2.0, 0.0))
        stage.add("Person head", Shapes.blob("person head", (0.26, 0.26, 0.28)),
                  material, self.root, location=(0.0, 0.0, height * 0.84))

    def pop(self, frame):
        Keys.pop(self.root, frame)
        return self


class Dog:
    """Faces +X, paws on its origin."""

    def __init__(self, stage, location, size=1.0):
        coat = Materials.surface("Dog", "#b98a5a", roughness=0.8)
        dark = Materials.surface("Dog dark", "#3a2a1c", roughness=0.8)
        self.root = stage.pivot("Dog", location=location)
        self.root.scale = (size, size, size)
        parts = [
            ("body", (0.9, 0.34, 0.36), (0.0, 0.0, 0.58), coat),
            ("head", (0.36, 0.3, 0.3), (0.56, 0.0, 0.86), coat),
            ("muzzle", (0.24, 0.18, 0.16), (0.8, 0.0, 0.8), coat),
            ("nose", (0.07, 0.1, 0.08), (0.93, 0.0, 0.84), dark),
        ]
        for x in (-0.34, 0.34):
            for y in (-0.11, 0.11):
                parts.append(("leg", (0.12, 0.1, 0.42), (x, y, 0.21), coat))
        for y in (-0.12, 0.12):
            parts.append(("ear", (0.1, 0.06, 0.2), (0.46, y, 1.06), dark))
        for label, shape, place, material in parts:
            stage.add(f"Dog {label}", Shapes.block(f"dog {label}", shape), material,
                      self.root, location=place)
        self.tail = stage.add("Dog tail", Shapes.block("dog tail", (0.08, 0.08, 0.36), True),
                              coat, self.root, location=(-0.46, 0.0, 0.66),
                              rotation=(0.0, -0.6, 0.0))

    def pop(self, frame):
        Keys.pop(self.root, frame)
        for beat in range(12):
            Keys.axis(self.tail, frame + 14 + beat * 5, "rotation_euler", 0,
                      0.5 if beat % 2 else -0.5)
        return self


class Phone:
    """The field app: a waveform, a keep star, and the tags a recordist adds."""

    def __init__(self, stage, fonts, location, envelope):
        self.stage, self.fonts = stage, fonts
        self.root = stage.pivot("Phone", location=location)
        shell = Materials.surface("Phone shell", "#0f0e14", roughness=0.25, metallic=0.7)
        screen = Materials.flat("Phone screen", "#221c2e")
        stage.add("Phone shell", Shapes.block("phone", (1.5, 0.14, 3.0)), shell, self.root)
        stage.add("Phone screen", Shapes.block("screen", (1.34, 0.02, 2.78)), screen,
                  self.root, location=(0.0, -0.075, 0.0))
        self.bars = self._waveform(envelope)
        self.star = stage.add("Keep star", self._star(0.2),
                              Materials.glow("Keep star", "#ffd76a", 3.0), self.root,
                              location=(0.42, -0.1, 1.05))
        self.button = stage.add("Record", Shapes.disc("record", 0.17, sides=24),
                                Materials.glow("Record", CallColors.ALARM, 2.5), self.root,
                                location=(0.0, -0.1, -1.05),
                                rotation=(math.pi / 2.0, 0.0, 0.0))

    def _waveform(self, envelope):
        material = Materials.glow("Waveform", Palette.ACCENT, 2.2)
        mesh = Shapes.block("wave bar", (1.0, 1.0, 1.0))
        count = 30
        bars = []
        for index in range(count):
            level = float(envelope[int(index / count * len(envelope))])
            bar = self.stage.add("Wave bar", mesh, material, self.root,
                                 location=(-0.56 + index * 1.12 / (count - 1), -0.1, 0.15),
                                 scale=(0.022, 0.02, 0.02))
            bars.append((bar, 0.06 + level * 0.8))
        return bars

    @staticmethod
    def _star(radius):
        points = []
        for index in range(10):
            reach = radius if index % 2 == 0 else radius * 0.42
            angle = math.pi / 2.0 + index * math.pi / 5.0
            points.append((reach * math.cos(angle), 0.0, reach * math.sin(angle)))
        return Shapes.outline("star", points)

    def record(self, start, frames):
        for index, (bar, height) in enumerate(self.bars):
            frame = start + frames * index / len(self.bars)
            Keys.at(bar, frame - 1, scale=(0.022, 0.02, 0.02))
            Keys.at(bar, frame + 3, scale=(0.022, 0.02, height))
        for beat in range(0, frames, 12):
            Keys.at(self.button, start + beat, scale=(1.0, 1.0, 1.0))
            Keys.at(self.button, start + beat + 6, scale=(0.7, 0.7, 0.7))
        Keys.at(self.button, start + frames + 6, scale=(1.0, 1.0, 1.0))
        return self

    def keep(self, frame):
        Keys.pop(self.star, frame, frames=12)
        return self


class Pin:
    def __init__(self, stage, fonts, number, location):
        material = Materials.glow("Pin", Palette.CREAM, 2.0)
        self.root = stage.pivot(f"Pin {number}", location=location)
        stage.add("Pin point", Shapes.spike("pin point", 0.16, 0.5, sides=6), material,
                  self.root, location=(0.0, 0.0, 0.55), rotation=(0.0, math.pi / 2.0, 0.0))
        stage.add("Pin head", Shapes.blob("pin head", (0.26, 0.26, 0.26), detail=1), material,
                  self.root, location=(0.0, 0.0, 0.72))
        label = stage.text(f"Pin label {number}", str(number), fonts.display, 0.5,
                           Materials.glow("Pin number", Palette.CREAM, 2.0),
                           (0.0, 0.0, 1.15), extrude=0.02, align="CENTER")
        label.parent = self.root

    def drop(self, frame):
        x, y, z = self.root.location
        Keys.at(self.root, frame - 1, scale=(0.0, 0.0, 0.0), location=(x, y, z + 2.5))
        Keys.at(self.root, frame, scale=(1.0, 1.0, 1.0))
        Keys.at(self.root, frame + 10, location=(x, y, z))
        return self


class ValleyMap:
    """CawScout: a scored grid, a predator that subtracts, and a ranked target list."""

    CELL = 0.5
    SIZE = (18, 12)
    HOTSPOTS = [(4.0, 8.0, 2.4, 2.2), (9.5, 3.5, 2.0, 2.6), (14.0, 8.5, 1.7, 2.0),
                (13.0, 3.0, 2.1, 1.5)]
    OWL = 3

    def __init__(self, stage, fonts, origin):
        self.stage, self.fonts, self.origin = stage, fonts, origin
        self.random = random.Random(19)
        self.columns = {}
        columns, rows = self.SIZE
        x0, y0, z0 = origin
        stage.add("Valley plate",
                  Shapes.block("valley", (columns * self.CELL + 0.6, rows * self.CELL + 0.6, 0.1)),
                  Materials.surface("Valley plate", "#15121c", roughness=0.35, metallic=0.5),
                  location=(x0 + columns * self.CELL / 2.0, y0 + rows * self.CELL / 2.0,
                            z0 - 0.05))
        material = Materials.per_object("Valley cell", 0.6)
        mesh = Shapes.block("valley cell", (1.0, 1.0, 1.0), grounded=True)
        for i in range(columns):
            for j in range(rows):
                cell = stage.add("Valley cell", mesh, material, location=self.spot(i, j),
                                 scale=(self.CELL * 0.82, self.CELL * 0.82, 0.001))
                self.columns[(i, j)] = cell

    def spot(self, i, j, lift=0.0):
        x0, y0, z0 = self.origin
        return (x0 + (i + 0.5) * self.CELL, y0 + (j + 0.5) * self.CELL, z0 + lift)

    def _score(self, i, j, without_owl=True):
        total = 0.06 + 0.05 * self.random.random()
        for index, (cx, cy, spread, peak) in enumerate(self.HOTSPOTS):
            if index == self.OWL and not without_owl:
                continue
            total += peak * math.exp(-((i - cx) ** 2 + (j - cy) ** 2) / (2.0 * spread ** 2))
        return total

    def _set(self, cell, frame, height):
        flat = self.CELL * 0.82
        Keys.at(cell, frame, scale=(flat, flat, max(height, 0.001)),
                color=Palette.heat(min(height / 2.6, 1.0)))

    def score(self, start):
        """Raise the grid west to east."""
        self.first = {}
        for (i, j), cell in self.columns.items():
            height = self._score(i, j)
            self.first[(i, j)] = height
            self._set(cell, start + i * 3 - 1, 0.0)
            self._set(cell, start + i * 3 + 8, height)
        return self

    def subtract_predator(self, frame):
        cx, cy, spread, _ = self.HOTSPOTS[self.OWL]
        for (i, j), cell in self.columns.items():
            if (i - cx) ** 2 + (j - cy) ** 2 > (2.6 * spread) ** 2:
                continue
            self._set(cell, frame, self.first[(i, j)])
            self._set(cell, frame + 16, self._score(i, j, without_owl=False))
        Chip(self.stage, self.fonts, "owl", CallColors.ALARM,
             self.spot(int(cx), int(cy), 2.9), size=0.36).pop(frame - 10)
        return self

    def rank(self, frame):
        for number, (cx, cy, _, peak) in enumerate(self.HOTSPOTS[:3], start=1):
            Pin(self.stage, self.fonts, number,
                self.spot(int(cx), int(cy), peak + 0.15)).drop(frame + (number - 1) * 12)
        return self


class Emitter:
    """Where tokens start when there is no spectrogram behind them: a prompt."""

    columns = 1

    def __init__(self, location):
        self.origin = location

    def column_x(self, column):
        return self.origin[0]

    def crest(self, column):
        return self.origin[2]


class Subtitles:
    """Captions pinned to the lens, on a dark strip so they read over anything."""

    DISTANCE = 0.4

    def __init__(self, stage, fonts):
        self.stage, self.fonts = stage, fonts
        self.ink = Materials.glow("Subtitle", Palette.CREAM, 1.0)
        self.strip = Materials.surface("Subtitle strip", "#000000", roughness=1.0)
        self.strip.node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = 0.6

    def show(self, camera, body, start, end):
        half_width = self.DISTANCE * 18.0 / camera.body.data.lens
        half_height = half_width * 9.0 / 16.0
        size = half_width * 0.07
        lines = body.split("\n")
        top = -half_height * 0.6
        text = self.stage.text(f"Subtitle {start}", body, self.fonts.display, size, self.ink,
                               (0.0, top, -self.DISTANCE), extrude=0.0, align="CENTER")
        text.rotation_euler = (0.0, 0.0, 0.0)
        text.parent = camera.body
        ceiling = top + size * 0.95
        floor = top - (len(lines) - 1) * size * 1.2 - size * 0.45
        width = size * (0.56 * max(len(line) for line in lines) + 1.6)
        strip = self.stage.add(
            f"Subtitle strip {start}", Shapes.block("strip", (width, ceiling - floor, 0.001)),
            self.strip, camera.body, location=(0.0, (ceiling + floor) / 2.0,
                                               -self.DISTANCE - 0.01))
        for item in (text, strip):
            Keys.at(item, start - 1, scale=(0.0, 0.0, 0.0))
            Keys.at(item, start, scale=(1.0, 1.0, 1.0))
            Keys.at(item, end, scale=(1.0, 1.0, 1.0))
            Keys.at(item, end + 1, scale=(0.0, 0.0, 0.0))
            Keys.straighten(item)
