"""The cast: a perched crow that caws in time with a real clip, and a flock."""

import math
from dataclasses import dataclass

import bpy

from .kit import Keys, Materials, Palette, Shapes


@dataclass
class Plumage:
    feather: bpy.types.Material
    beak: bpy.types.Material
    eye: bpy.types.Material
    glint: bpy.types.Material
    leg: bpy.types.Material

    @classmethod
    def living(cls):
        feather = Materials.surface("Feather", Palette.FEATHER, roughness=0.32, metallic=0.35)
        return cls(
            feather=feather,
            beak=Materials.surface("Beak", Palette.BEAK, roughness=0.25),
            eye=Materials.surface("Eye", "#050505", roughness=0.05),
            glint=Materials.glow("Glint", Palette.CREAM, 3.0),
            leg=Materials.surface("Leg", "#1b1a1f", roughness=0.7),
        )

    @classmethod
    def generated(cls):
        light = Materials.hologram("Generated feather", Palette.ACCENT, 4.0)
        bright = Materials.glow("Generated eye", Palette.CREAM, 6.0)
        return cls(feather=light, beak=light, eye=bright, glint=bright, leg=light)


class PerchedCrow:
    """Faces +X with its feet at the origin."""

    BEAK_TIP = (0.39, 0.0, 0.35)
    JAW_OPEN = 0.62
    HEAD_LIFT = 0.26
    LEAN = 0.16

    def __init__(self, stage, name, plumage):
        self.stage = stage
        self.name = name
        self.plumage = plumage
        self.root = stage.pivot(name)
        self.torso = stage.pivot(f"{name} torso", self.root, (0.0, 0.0, 0.12))
        self.neck = stage.pivot(f"{name} neck", self.torso, (0.15, 0.0, 0.19))
        self.jaw = None
        self._build_body()
        self._build_head()
        self._build_legs()

    def _part(self, label, mesh, material, parent, **placement):
        return self.stage.add(f"{self.name} {label}", mesh, material, parent, **placement)

    def _build_body(self):
        feather = self.plumage.feather
        self._part("body", Shapes.blob("body", (0.20, 0.105, 0.115)), feather, self.torso,
                   location=(0.0, 0.0, 0.07), rotation=(0.0, math.radians(-35), 0.0))
        for side in (-1, 1):
            self._part("wing", Shapes.blob("wing", (0.19, 0.028, 0.085)), feather, self.torso,
                       location=(-0.045, side * 0.095, 0.075),
                       rotation=(0.0, math.radians(-44), 0.0))
        self.tail = self._part(
            "tail", Shapes.spike("tail", 0.045, 0.27, tip=0.075, flatten=0.22),
            feather, self.torso,
            location=(-0.14, 0.0, -0.02), rotation=(0.0, math.radians(142), 0.0))

    def _build_head(self):
        head = self._part("head", Shapes.blob("head", (0.085, 0.07, 0.072)),
                          self.plumage.feather, self.neck, location=(0.045, 0.0, 0.05))
        self._part("upper beak", Shapes.spike("upper beak", 0.032, 0.13, flatten=0.8),
                   self.plumage.beak, head,
                   location=(0.062, 0.0, 0.004), rotation=(0.0, math.radians(7), 0.0))
        self.jaw = self.stage.pivot(f"{self.name} jaw", head, (0.058, 0.0, -0.014))
        self._part("lower beak", Shapes.spike("lower beak", 0.024, 0.105, flatten=0.5),
                   self.plumage.beak, self.jaw, rotation=(0.0, math.radians(7), 0.0))
        for side in (-1, 1):
            self._part("eye", Shapes.blob("eye", (0.014, 0.014, 0.014), detail=1),
                       self.plumage.eye, head, location=(0.042, side * 0.056, 0.02))
            self._part("glint", Shapes.blob("glint", (0.004, 0.004, 0.004), detail=1),
                       self.plumage.glint, head, location=(0.05, side * 0.066, 0.027))

    def _build_legs(self):
        for side in (-1, 1):
            self._part("leg", Shapes.post("leg", 0.008, 0.13, sides=5), self.plumage.leg,
                       self.root, location=(0.02, side * 0.04, 0.0))
            self._part("foot", Shapes.blob("foot", (0.03, 0.014, 0.016), detail=1),
                       self.plumage.leg, self.root, location=(0.02, side * 0.04, 0.004))

    def place(self, location, heading=0.0):
        self.root.location = location
        self.root.rotation_euler = (0.0, 0.0, heading)
        return self

    def beak_tip(self):
        facing = math.cos(self.root.rotation_euler.z)
        x, y, z = self.root.location
        return (x + facing * self.BEAK_TIP[0], y, z + self.BEAK_TIP[2])

    def caw(self, start, envelope):
        """Open the beak by the clip's own loudness, one key per frame."""
        body = 0.0
        for offset, level in enumerate(envelope):
            frame = start + offset
            body += (level - body) * 0.35
            Keys.axis(self.jaw, frame, "rotation_euler", 1, level * self.JAW_OPEN)
            Keys.axis(self.neck, frame, "rotation_euler", 1, -level * self.HEAD_LIFT)
            Keys.axis(self.torso, frame, "rotation_euler", 1, body * self.LEAN)
            Keys.axis(self.tail, frame, "rotation_euler", 1,
                      math.radians(142) - body * 0.22)
        rest = start + len(envelope) + 3
        Keys.axis(self.jaw, rest, "rotation_euler", 1, 0.0)
        Keys.axis(self.neck, rest, "rotation_euler", 1, 0.0)
        Keys.axis(self.torso, rest, "rotation_euler", 1, 0.0)
        Keys.axis(self.tail, rest, "rotation_euler", 1, math.radians(142))

    def look(self, frame, yaw=0.0, tilt=0.0):
        Keys.axis(self.neck, frame, "rotation_euler", 2, yaw)
        Keys.axis(self.neck, frame, "rotation_euler", 0, tilt)


class FlyingCrow:
    """A silhouette for the distance; faces +X."""

    WING = [(0.10, 0.0, 0.0), (-0.12, 0.0, 0.0), (-0.17, 0.56, 0.0),
            (0.0, 0.64, 0.0), (0.09, 0.3, 0.0)]
    FLAP_FRAMES = 10

    def __init__(self, stage, name, material, size=1.0):
        self.root = stage.pivot(name)
        self.root.scale = (size, size, size)
        stage.add(f"{name} body", Shapes.blob("flyer body", (0.22, 0.065, 0.07), detail=1),
                  material, self.root)
        stage.add(f"{name} head", Shapes.blob("flyer head", (0.075, 0.06, 0.06), detail=1),
                  material, self.root, location=(0.22, 0.0, 0.02))
        stage.add(f"{name} beak", Shapes.spike("flyer beak", 0.025, 0.11, sides=4),
                  material, self.root, location=(0.28, 0.0, 0.015))
        stage.add(f"{name} tail", Shapes.outline("flyer tail", [
            (-0.15, 0.03, 0.0), (-0.42, 0.09, 0.0), (-0.42, -0.09, 0.0), (-0.15, -0.03, 0.0)]),
                  material, self.root)
        self.wings = []
        for side in (-1, 1):
            shape = [(x, side * y, z) for x, y, z in self.WING]
            wing = stage.add(f"{name} wing", Shapes.outline("flyer wing", shape),
                             material, self.root, location=(0.0, side * 0.045, 0.03))
            self.wings.append((side, wing))

    def flap(self, phase):
        for side, wing in self.wings:
            for step, lift in enumerate((0.75, -0.5, 0.75)):
                frame = phase + step * self.FLAP_FRAMES / 2.0
                Keys.axis(wing, frame, "rotation_euler", 0, side * lift)
            Keys.repeat(wing)
        return self

    def cross(self, start, end, origin, destination, bob=0.4):
        steps = 6
        for step in range(steps + 1):
            mix = step / steps
            point = [origin[i] + (destination[i] - origin[i]) * mix for i in range(3)]
            point[2] += bob * math.sin(mix * math.pi * 3.0)
            Keys.at(self.root, start + (end - start) * mix, location=tuple(point))
        return self
