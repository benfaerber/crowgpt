"""The places the film happens: a dusk skyline, a power line, and the machine."""

import math
import random

import bpy

from .kit import Keys, Materials, Palette, Shapes


class Dusk:
    """Sky gradient, low sun, flat ridgelines and a town, lit from behind."""

    def __init__(self, stage):
        self.stage = stage
        self.random = random.Random(7)
        self._sky()
        self._ground_and_sun()
        self._ridge("Far ridge", 760.0, 45.0, 120.0, Palette.RIDGE_FAR)
        self._ridge("Near ridge", 520.0, 18.0, 55.0, Palette.RIDGE_NEAR)
        self._town()
        self._lights()

    def _sky(self):
        world = bpy.data.worlds.new("Dusk")
        world.use_nodes = True
        self.stage.scene.world = world
        nodes, links = world.node_tree.nodes, world.node_tree.links
        direction = nodes.new("ShaderNodeTexCoord")
        split = nodes.new("ShaderNodeSeparateXYZ")
        height = nodes.new("ShaderNodeMapRange")
        height.inputs["From Min"].default_value = -0.12
        height.inputs["From Max"].default_value = 1.0
        ramp = nodes.new("ShaderNodeValToRGB")
        stops = [(0.0, Palette.GROUND), (0.1, Palette.SKY_LOW),
                 (0.3, Palette.SKY_MID), (0.75, Palette.SKY_TOP)]
        elements = ramp.color_ramp.elements
        while len(elements) < len(stops):
            elements.new(0.5)
        for element, (position, color) in zip(elements, stops):
            element.position, element.color = position, Palette.linear(color)
        links.new(direction.outputs["Generated"], split.inputs["Vector"])
        links.new(split.outputs["Z"], height.inputs["Value"])
        links.new(height.outputs["Result"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], nodes["Background"].inputs["Color"])
        nodes["Background"].inputs["Strength"].default_value = 1.0

    def _ground_and_sun(self):
        self.stage.add("Ground", Shapes.block("ground", (6000.0, 6000.0, 1.0)),
                       Materials.flat("Ground", Palette.GROUND), location=(0.0, 0.0, -0.5))
        self.stage.add("Sun disc", Shapes.disc("sun", 34.0),
                       Materials.glow("Sun", "#ffc98a", 5.0),
                       location=(-70.0, 900.0, 118.0), rotation=(math.pi / 2.0, 0.0, 0.0))

    def _ridge(self, name, distance, low, high, color):
        peaks, span, step = [], 2600.0, 26.0
        count = int(span / step)
        for i in range(count + 1):
            x = -span / 2.0 + i * step
            swell = 0.5 + 0.5 * math.sin(x / 190.0 + distance) * math.sin(x / 71.0)
            peaks.append((x, low + (high - low) * (0.65 * swell + 0.35 * self.random.random())))
        outline = [(-span / 2.0, 0.0, 0.0)] + [(x, 0.0, z) for x, z in peaks]
        outline.append((span / 2.0, 0.0, 0.0))
        self.stage.add(name, Shapes.outline(name, outline), Materials.flat(name, color),
                       location=(0.0, distance, 0.0))

    def _town(self):
        dark = Materials.flat("Town", "#1a1524")
        lit = Materials.glow("Window", "#ffb866", 4.0)
        for _ in range(110):
            x = self.random.uniform(-420.0, 480.0)
            y = self.random.uniform(260.0, 430.0)
            width = self.random.uniform(8.0, 22.0)
            height = self.random.uniform(4.0, 15.0)
            self.stage.add("Building", Shapes.block("building", (width, 10.0, height), True),
                           dark, location=(x, y, 0.0))
            for _ in range(self.random.randint(0, 3)):
                self.stage.add(
                    "Window", Shapes.block("window", (0.9, 0.3, 0.9)), lit,
                    location=(x + self.random.uniform(-0.4, 0.4) * width, y - 5.2,
                              self.random.uniform(0.2, 0.9) * height))

    def _lights(self):
        self.lamp("Sunset", "SUN", (0.0, 0.0, 30.0), (math.radians(-84), 0.0, math.radians(-8)),
                   "#ff9a55", 4.0)
        key = self.lamp("Sky fill", "AREA", (-3.0, -7.0, 9.5),
                         (math.radians(62), 0.0, math.radians(-22)), "#8fa6ff", 2600.0)
        key.data.size = 6.0

    def lamp(self, name, kind, location, rotation, color, energy):
        data = bpy.data.lights.new(name, kind)
        data.color = Palette.linear(color)[:3]
        data.energy = energy
        lamp = bpy.data.objects.new(name, data)
        self.stage.collection.objects.link(lamp)
        lamp.location, lamp.rotation_euler = location, rotation
        return lamp


class PowerLine:
    HEIGHT = 5.0
    WIRE = 0.012
    WIRES = [(0.0, 0.0), (0.9, 0.05), (1.8, -0.04)]
    POLES = range(-43, 160, 40)

    def __init__(self, stage):
        metal = Materials.surface("Wire", "#0d0c10", roughness=0.4, metallic=0.6)
        timber = Materials.surface("Pole", "#1c1612", roughness=0.9)
        for y, lift in self.WIRES:
            stage.add("Wire", Shapes.post("wire", self.WIRE, 260.0), metal,
                      location=(-80.0, y, self.HEIGHT + lift),
                      rotation=(0.0, math.pi / 2.0, 0.0))
        for x in self.POLES:
            stage.add("Pole", Shapes.post("pole", 0.14, self.HEIGHT + 1.1), timber,
                      location=(x + 0.4, 0.9, 0.0))
            stage.add("Crossarm", Shapes.block("crossarm", (0.12, 2.7, 0.14)), timber,
                      location=(x + 0.4, 0.9, self.HEIGHT - 0.25))
            for y, lift in self.WIRES:
                stage.add("Insulator", Shapes.post("insulator", 0.045, 0.2), metal,
                          location=(x + 0.4, y, self.HEIGHT - 0.2 + lift))

    @classmethod
    def perch(cls, x):
        return (x, 0.0, cls.HEIGHT + cls.WIRE)


class SoundRings:
    """Hoops that leave the beak on each caw and fade as they travel."""

    def __init__(self, stage):
        self.stage = stage
        self.material = Materials.per_object("Sound ring", 3.0, fades=True)
        self.mesh = Shapes.ring("sound ring", 0.1, 0.004)
        self.color = Palette.linear(Palette.ACCENT)[:3]

    def emit(self, frame, source, direction, reach=7.0, life=44, count=3, spacing=4):
        for index in range(count):
            start = frame + index * spacing
            ring = self.stage.add("Sound ring", self.mesh, self.material, location=source)
            Keys.at(ring, start - 1, scale=(0.0, 0.0, 0.0), color=(*self.color, 0.0))
            Keys.at(ring, start, scale=(1.0, 1.0, 1.0), color=(*self.color, 1.0),
                    location=source)
            Keys.at(ring, start + life, scale=(1.0, 10.0, 10.0), color=(*self.color, 0.0),
                    location=(source[0] + direction * reach, source[1], source[2]))
            Keys.at(ring, start + life + 1, scale=(0.0, 0.0, 0.0))


class Spectrogram:
    """A call as a field of bars: time along X, pitch into the picture, level up."""

    def __init__(self, stage, name, grid, origin, width=12.0, depth=4.4, height=2.4):
        self.stage = stage
        self.name = name
        self.grid = grid
        self.origin = origin
        self.width, self.depth, self.height = width, depth, height
        self.columns, self.bands = grid.shape
        self.bars = []
        self._build()

    def _build(self):
        material = Materials.per_object(f"{self.name} bar", 1.1)
        mesh = Shapes.block(f"{self.name} bar", (1.0, 1.0, 1.0), grounded=True)
        cell_x, cell_y = self.width / self.columns, self.depth / self.bands
        x0, y0, z0 = self.origin
        plate = Materials.surface(f"{self.name} plate", "#15121c", roughness=0.35, metallic=0.5)
        self.stage.add(f"{self.name} plate",
                       Shapes.block("plate", (self.width + 0.7, self.depth + 0.7, 0.1)),
                       plate, location=(x0 + self.width / 2.0, y0, z0 - 0.05))
        for column in range(self.columns):
            row = []
            for band in range(self.bands):
                level = float(self.grid[column, band])
                bar = self.stage.add(
                    f"{self.name} bar", mesh, material,
                    location=(x0 + (column + 0.5) * cell_x,
                              y0 - self.depth / 2.0 + (band + 0.5) * cell_y, z0),
                    scale=(cell_x * 0.8, cell_y * 0.8, 0.001))
                bar.color = Palette.heat(level)
                row.append((bar, 0.04 + level * self.height))
            self.bars.append(row)

    def column_x(self, column):
        return self.origin[0] + (column + 0.5) * self.width / self.columns

    def column_frame(self, column, start, frames):
        return start + frames * column / self.columns

    def crest(self, column):
        return self.origin[2] + max(height for _, height in self.bars[column])

    def rise(self, start, frames):
        """Raise each column as the playhead reaches it."""
        for column, row in enumerate(self.bars):
            frame = self.column_frame(column, start, frames)
            for bar, height in row:
                flat = (bar.scale[0], bar.scale[1], 0.001)
                Keys.at(bar, frame - 1, scale=flat)
                Keys.at(bar, frame + 3, scale=(flat[0], flat[1], height))
        self._playhead(start, frames)

    def _playhead(self, start, frames):
        x0, y0, z0 = self.origin
        beam = self.stage.add(
            f"{self.name} playhead",
            Shapes.block("playhead", (0.02, self.depth + 0.3, self.height * 0.6), True),
            Materials.glow(f"{self.name} playhead", Palette.ACCENT, 1.6), location=(x0, y0, z0))
        Keys.at(beam, start - 1, scale=(0.0, 0.0, 0.0), location=(x0, y0, z0))
        Keys.at(beam, start, scale=(1.0, 1.0, 1.0))
        Keys.at(beam, start + frames, scale=(1.0, 1.0, 1.0),
                location=(x0 + self.width, y0, z0))
        Keys.at(beam, start + frames + 6, scale=(0.0, 0.0, 0.0))
        Keys.straighten(beam)


class Lattice:
    """The model, drawn as layers of nodes that light in a travelling wave."""

    def __init__(self, stage, centre, layers=6, side=5, spacing=0.7, gap=1.0):
        self.stage = stage
        self.centre = centre
        self.layers, self.side, self.spacing, self.gap = layers, side, spacing, gap
        self.random = random.Random(11)
        self.materials = []
        self.points = []
        self._build()

    @property
    def entry_x(self):
        return self.centre[0] - self.gap * (self.layers - 1) / 2.0

    @property
    def exit_x(self):
        return self.centre[0] + self.gap * (self.layers - 1) / 2.0

    @property
    def reach(self):
        return self.spacing * (self.side - 1) / 2.0

    def _build(self):
        node = Shapes.blob("lattice node", (0.075, 0.075, 0.075), detail=1)
        frame_color = Materials.glow("Lattice frame", Palette.SKY_MID, 1.2)
        _, cy, cz = self.centre
        for layer in range(self.layers):
            material = Materials.glow(f"Lattice layer {layer}", Palette.ACCENT, 0.7)
            self.materials.append(material)
            x = self.entry_x + layer * self.gap
            points = [(x, cy + (i - (self.side - 1) / 2.0) * self.spacing,
                       cz + (j - (self.side - 1) / 2.0) * self.spacing)
                      for i in range(self.side) for j in range(self.side)]
            self.points.append(points)
            layer_mesh = node.copy()
            for point in points:
                self.stage.add("Lattice node", layer_mesh, material, location=point)
            edge = self.reach + 0.3
            corners = [(x, cy + a * edge, cz + b * edge)
                       for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            self.stage.add("Lattice frame",
                           Shapes.struts("frame", list(zip(corners, corners[1:] + corners[:1])),
                                         0.02), frame_color)
        links = [(self.random.choice(near), self.random.choice(far))
                 for near, far in zip(self.points, self.points[1:]) for _ in range(34)]
        self.stage.add("Lattice links", Shapes.struts("links", links, 0.006),
                       Materials.glow("Lattice link", Palette.ACCENT, 0.9))

    def think(self, start, end, rate=1.4, fps=24):
        for layer, material in enumerate(self.materials):
            strength = Materials.strength_input(material)
            Keys.value(strength, start - 6, 0.7)
            for frame in range(start, end + 1, 3):
                wave = math.sin(2.0 * math.pi * (frame / fps * rate - layer / self.layers))
                Keys.value(strength, frame, 0.9 + 7.0 * max(0.0, wave) ** 2)
            Keys.value(strength, end + 8, 0.7)

    def passage(self, lane):
        y = self.centre[1] + lane[0] * self.reach
        z = self.centre[2] + lane[1] * self.reach
        return (self.entry_x - 0.6, y, z), (self.exit_x + 0.6, y, z)


class TokenStream:
    """Cubes that lift off one spectrogram, cross the lattice and seed the next."""

    LIFT, APPROACH, CROSS, DESCEND = 10, 32, 26, 26

    def __init__(self, stage, source, lattice, target, count=40):
        self.stage = stage
        self.source, self.lattice, self.target = source, lattice, target
        self.count = count
        self.random = random.Random(3)
        self.material = Materials.per_object("Token", 6.0)
        self.mesh = Shapes.block("token", (0.16, 0.16, 0.16))

    @property
    def lead(self):
        return self.LIFT + self.APPROACH + self.CROSS + self.DESCEND

    def flow(self, first_landing, landing_frames):
        """Land token k as the target's playhead reaches its column."""
        for index in range(self.count):
            share = index / self.count
            landing = first_landing + landing_frames * share
            self._send(index, share, landing)
        return first_landing - self.lead - 6

    def _send(self, index, share, landing):
        token = self.stage.add("Token", self.mesh, self.material)
        token.color = Palette.heat(self.random.uniform(0.5, 1.0))
        from_column = int(share * self.source.columns)
        to_column = int(share * self.target.columns)
        spot = (self.source.column_x(from_column),
                self.source.origin[1] + self.random.uniform(-1.0, 1.0),
                self.source.crest(from_column))
        entry, leave = self.lattice.passage(
            (self.random.uniform(-0.9, 0.9), self.random.uniform(-0.9, 0.9)))
        drop = (self.target.column_x(to_column),
                self.target.origin[1] + self.random.uniform(-1.0, 1.0),
                self.target.origin[2] + 0.1)
        appear = landing - self.lead
        spin = self.random.uniform(4.0, 9.0)
        Keys.at(token, appear - 6, scale=(0.0, 0.0, 0.0), location=spot,
                rotation_euler=(0.0, 0.0, 0.0))
        Keys.at(token, appear, scale=(1.0, 1.0, 1.0), location=spot)
        Keys.at(token, appear + self.LIFT, location=(spot[0], spot[1], spot[2] + 1.3))
        Keys.at(token, appear + self.LIFT + self.APPROACH, location=entry)
        Keys.at(token, landing - self.DESCEND, location=leave)
        Keys.at(token, landing, location=drop, scale=(1.0, 1.0, 1.0),
                rotation_euler=(spin, spin * 0.7, spin * 0.4))
        Keys.at(token, landing + 4, scale=(0.0, 0.0, 0.0))


class Lockup:
    """The mark and the wordmark, standing in the sky beside the crow."""

    MARK_HEIGHT = 1.35
    DEPTH = 0.06

    def __init__(self, stage, fonts, logo_path, anchor, size=1.0):
        self.stage = stage
        cream = Materials.glow("Wordmark", Palette.CREAM, 1.6)
        accent = Materials.glow("Tagline", Palette.ACCENT, 2.2)
        self.root = stage.pivot("Lockup", location=anchor, rotation=(math.pi / 2.0, 0.0, 0.0))
        self.root.scale = (size, size, size)
        self.mark = self._mark(logo_path, cream)
        text_x = 1.9 if self.mark else 0.0
        self.title = self._line("Wordmark", "CrowGPT", fonts, 1.25, cream, (text_x, 0.0))
        self.tagline = self._line("Tagline", "Decoding crow calls with AI", fonts, 0.36,
                                  accent, (text_x + 0.05, -0.62))
        self.address = self._line("Address", "crowgpt.org", fonts, 0.3, cream,
                                  (text_x + 0.05, -1.12))

    def _line(self, name, body, fonts, size, material, offset):
        line = self.stage.text(name, body, fonts.display, size, material,
                               (offset[0], offset[1], 0.0), extrude=self.DEPTH * size)
        line.parent = self.root
        line.rotation_euler = (0.0, 0.0, 0.0)
        return line

    def _mark(self, logo_path, material):
        try:
            import addon_utils
            addon_utils.enable("io_curve_svg")
            before = set(bpy.data.objects)
            bpy.ops.import_curve.svg(filepath=str(logo_path))
            shapes = [item for item in bpy.data.objects if item not in before]
        except Exception as problem:
            print(f"film: logo not imported ({problem}); the wordmark stands alone")
            return None
        corners = [point.co for shape in shapes for spline in shape.data.splines
                   for point in list(spline.bezier_points) + list(spline.points)]
        if not corners:
            return None
        left = min(corner.x for corner in corners)
        bottom = min(corner.y for corner in corners)
        size = self.MARK_HEIGHT / (max(corner.y for corner in corners) - bottom)
        holder = self.stage.pivot("Mark", self.root, (0.0, -0.08, 0.0))
        holder.scale = (size, size, size)
        for shape in shapes:
            for owner in list(shape.users_collection):
                owner.objects.unlink(shape)
            self.stage.collection.objects.link(shape)
            shape.parent = holder
            shape.location = (-left, -bottom, 0.0)
            shape.data.extrude = self.DEPTH / size
            shape.data.materials.clear()
            shape.data.materials.append(material)
        return holder

    def reveal(self, frame):
        if self.mark:
            Keys.pop(self.mark, frame - 8)
        Keys.pop(self.title, frame)
        Keys.pop(self.tagline, frame + 22, frames=10)
        Keys.pop(self.address, frame + 38, frames=10)


class Caption:
    def __init__(self, stage, fonts):
        self.stage = stage
        self.fonts = fonts
        self.material = Materials.glow("Caption", Palette.CREAM, 1.4)

    def stand(self, body, location, frame, size=0.42):
        label = self.stage.text(f"Caption {body}", body, self.fonts.display, size,
                                self.material, location, extrude=0.01, align="CENTER")
        Keys.pop(label, frame, frames=10)
        return label
