"""Colours, materials, low-poly shapes and keyframes: the parts every set is built from."""

import math

import bmesh
import bpy
from mathutils import Matrix, Vector


class Palette:
    """The promo page's dusk theme."""

    SKY_TOP = "#1d2340"
    SKY_MID = "#5a3a5c"
    SKY_LOW = "#c66a32"
    ACCENT = "#e08a3c"
    CREAM = "#f7f0e6"
    INK = "#17130f"
    GROUND = "#120f16"
    RIDGE_FAR = "#4a3557"
    RIDGE_NEAR = "#2a2238"
    FEATHER = "#0b0b12"
    BEAK = "#15141a"

    @staticmethod
    def linear(hex_code, alpha=1.0):
        channels = [int(hex_code[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
        return tuple(
            c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
        ) + (alpha,)

    @classmethod
    def heat(cls, value):
        stops = [(0.0, cls.SKY_MID), (0.55, cls.ACCENT), (1.0, cls.CREAM)]
        for (low, cold), (high, hot) in zip(stops, stops[1:]):
            if value <= high:
                mix = (value - low) / (high - low)
                a, b = cls.linear(cold), cls.linear(hot)
                return tuple(a[i] + (b[i] - a[i]) * mix for i in range(3)) + (value,)
        return cls.linear(cls.CREAM, value)


class Materials:
    @staticmethod
    def _new(name):
        material = bpy.data.materials.new(name)
        material.use_nodes = True
        nodes = material.node_tree.nodes
        return material, nodes, material.node_tree.links, nodes["Principled BSDF"]

    @classmethod
    def surface(cls, name, color, roughness=0.6, metallic=0.0):
        material, _, _, shader = cls._new(name)
        shader.inputs["Base Color"].default_value = Palette.linear(color)
        shader.inputs["Roughness"].default_value = roughness
        shader.inputs["Metallic"].default_value = metallic
        return material

    @classmethod
    def glow(cls, name, color, strength):
        material, _, _, shader = cls._new(name)
        shader.inputs["Base Color"].default_value = Palette.linear(color)
        shader.inputs["Emission Color"].default_value = Palette.linear(color)
        shader.inputs["Emission Strength"].default_value = strength
        return material

    @classmethod
    def flat(cls, name, color):
        material = bpy.data.materials.new(name)
        material.use_nodes = True
        nodes, links = material.node_tree.nodes, material.node_tree.links
        nodes.remove(nodes["Principled BSDF"])
        emission = nodes.new("ShaderNodeEmission")
        emission.inputs["Color"].default_value = Palette.linear(color)
        links.new(emission.outputs["Emission"], nodes["Material Output"].inputs["Surface"])
        return material

    @classmethod
    def per_object(cls, name, strength, fades=False):
        """Colour and brightness come from each object's own colour and alpha."""
        material, nodes, links, shader = cls._new(name)
        info = nodes.new("ShaderNodeObjectInfo")
        gain = nodes.new("ShaderNodeMath")
        gain.operation = "MULTIPLY"
        gain.inputs[1].default_value = strength
        links.new(info.outputs["Alpha"], gain.inputs[0])
        links.new(info.outputs["Color"], shader.inputs["Base Color"])
        links.new(info.outputs["Color"], shader.inputs["Emission Color"])
        links.new(gain.outputs["Value"], shader.inputs["Emission Strength"])
        if fades:
            links.new(info.outputs["Alpha"], shader.inputs["Alpha"])
        return material

    @classmethod
    def hologram(cls, name, color, strength):
        material = bpy.data.materials.new(name)
        material.use_nodes = True
        nodes, links = material.node_tree.nodes, material.node_tree.links
        nodes.remove(nodes["Principled BSDF"])
        edge = nodes.new("ShaderNodeLayerWeight")
        edge.inputs["Blend"].default_value = 0.35
        lift = nodes.new("ShaderNodeMath")
        lift.operation = "ADD"
        lift.inputs[1].default_value = 0.18
        lift.use_clamp = True
        emission = nodes.new("ShaderNodeEmission")
        emission.inputs["Color"].default_value = Palette.linear(color)
        emission.inputs["Strength"].default_value = strength
        clear = nodes.new("ShaderNodeBsdfTransparent")
        mix = nodes.new("ShaderNodeMixShader")
        links.new(edge.outputs["Facing"], lift.inputs[0])
        links.new(lift.outputs["Value"], mix.inputs["Fac"])
        links.new(clear.outputs["BSDF"], mix.inputs[1])
        links.new(emission.outputs["Emission"], mix.inputs[2])
        links.new(mix.outputs["Shader"], nodes["Material Output"].inputs["Surface"])
        return material

    @staticmethod
    def strength_input(material):
        return material.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]


class Shapes:
    """Meshes built with bmesh so nothing depends on operators or a viewport."""

    @staticmethod
    def _mesh(name, build):
        geometry = bmesh.new()
        build(geometry)
        mesh = bpy.data.meshes.new(name)
        geometry.to_mesh(mesh)
        geometry.free()
        return mesh

    @classmethod
    def blob(cls, name, radii, detail=2):
        squash = Matrix.Diagonal((*radii, 1.0))
        return cls._mesh(name, lambda g: bmesh.ops.create_icosphere(
            g, subdivisions=detail, radius=1.0, matrix=squash))

    @classmethod
    def spike(cls, name, radius, length, tip=0.001, sides=6, flatten=1.0):
        """A cone lying along +X with its base at the origin."""
        along_x = (Matrix.Diagonal((1.0, 1.0, flatten, 1.0))
                   @ Matrix.Translation((length / 2.0, 0.0, 0.0))
                   @ Matrix.Rotation(math.pi / 2.0, 4, "Y"))
        return cls._mesh(name, lambda g: bmesh.ops.create_cone(
            g, cap_ends=True, cap_tris=True, segments=sides,
            radius1=radius, radius2=tip, depth=length, matrix=along_x))

    @classmethod
    def post(cls, name, radius, height, sides=8):
        """A cylinder standing on the origin."""
        lifted = Matrix.Translation((0.0, 0.0, height / 2.0))
        return cls._mesh(name, lambda g: bmesh.ops.create_cone(
            g, cap_ends=True, segments=sides,
            radius1=radius, radius2=radius, depth=height, matrix=lifted))

    @classmethod
    def block(cls, name, size, grounded=False):
        shape = Matrix.Diagonal((*size, 1.0))
        if grounded:
            shape = Matrix.Translation((0.0, 0.0, size[2] / 2.0)) @ shape
        return cls._mesh(name, lambda g: bmesh.ops.create_cube(g, size=1.0, matrix=shape))

    @classmethod
    def disc(cls, name, radius, sides=48):
        return cls._mesh(name, lambda g: bmesh.ops.create_circle(
            g, cap_ends=True, segments=sides, radius=radius))

    @classmethod
    def outline(cls, name, points):
        def build(geometry):
            geometry.faces.new([geometry.verts.new(point) for point in points])
        return cls._mesh(name, build)

    @classmethod
    def struts(cls, name, pairs, radius):
        def build(geometry):
            for start, end in pairs:
                start, end = Vector(start), Vector(end)
                span = end - start
                placement = (Matrix.Translation((start + end) / 2.0)
                             @ span.to_track_quat("Z", "Y").to_matrix().to_4x4())
                bmesh.ops.create_cone(
                    geometry, cap_ends=False, segments=5,
                    radius1=radius, radius2=radius, depth=span.length, matrix=placement)
        return cls._mesh(name, build)

    @classmethod
    def ring(cls, name, radius, thickness, around=40, across=6):
        """A torus facing along X."""
        def build(geometry):
            rows = []
            for i in range(around):
                turn = 2.0 * math.pi * i / around
                row = []
                for j in range(across):
                    roll = 2.0 * math.pi * j / across
                    reach = radius + thickness * math.cos(roll)
                    row.append(geometry.verts.new((
                        thickness * math.sin(roll),
                        reach * math.cos(turn),
                        reach * math.sin(turn))))
                rows.append(row)
            for i in range(around):
                here, there = rows[i], rows[(i + 1) % around]
                for j in range(across):
                    k = (j + 1) % across
                    geometry.faces.new((here[j], there[j], there[k], here[k]))
        return cls._mesh(name, build)


class Stage:
    """Puts things into the scene."""

    def __init__(self, scene):
        self.scene = scene
        self.collection = scene.collection

    def add(self, name, mesh, material=None, parent=None, location=(0, 0, 0),
            rotation=(0, 0, 0), scale=(1, 1, 1)):
        item = bpy.data.objects.new(name, mesh)
        self.collection.objects.link(item)
        item.location, item.rotation_euler, item.scale = location, rotation, scale
        if parent is not None:
            item.parent = parent
        if material is not None and mesh is not None:
            mesh.materials.clear()
            mesh.materials.append(material)
        return item

    def pivot(self, name, parent=None, location=(0, 0, 0), rotation=(0, 0, 0)):
        return self.add(name, None, parent=parent, location=location, rotation=rotation)

    def text(self, name, body, font, size, material, location, extrude=0.03, align="LEFT"):
        curve = bpy.data.curves.new(name, "FONT")
        curve.body, curve.font, curve.size = body, font, size
        curve.extrude, curve.align_x = extrude, align
        item = bpy.data.objects.new(name, curve)
        self.collection.objects.link(item)
        item.location, item.rotation_euler = location, (math.pi / 2.0, 0.0, 0.0)
        curve.materials.append(material)
        return item


class Keys:
    @staticmethod
    def at(item, frame, **channels):
        for path, value in channels.items():
            setattr(item, path, value)
            item.keyframe_insert(path, frame=frame)

    @staticmethod
    def axis(item, frame, path, index, value):
        getattr(item, path)[index] = value
        item.keyframe_insert(path, index=index, frame=frame)

    @staticmethod
    def value(socket, frame, value):
        socket.default_value = value
        socket.keyframe_insert("default_value", frame=frame)

    @staticmethod
    def curves(item):
        animation = item.animation_data
        if not (animation and animation.action):
            return []
        if hasattr(animation.action, "fcurves"):
            return list(animation.action.fcurves)
        from bpy_extras import anim_utils
        bag = anim_utils.action_get_channelbag_for_slot(animation.action, animation.action_slot)
        return list(bag.fcurves) if bag else []

    @classmethod
    def straighten(cls, item):
        for curve in cls.curves(item):
            for point in curve.keyframe_points:
                point.interpolation = "LINEAR"

    @classmethod
    def repeat(cls, item):
        for curve in cls.curves(item):
            curve.modifiers.new("CYCLES")

    @classmethod
    def pop(cls, item, frame, size=1.0, frames=14):
        """Grow from nothing with a small overshoot."""
        full = Vector(item.scale) * size
        cls.at(item, frame, scale=(0.0, 0.0, 0.0))
        cls.at(item, frame + frames * 0.6, scale=tuple(full * 1.08))
        cls.at(item, frame + frames, scale=tuple(full))


class Pace:
    """Stretches everything already keyed onto the clock's screen frames."""

    def __init__(self, clock):
        self.clock = clock

    def apply(self, scene):
        if self.clock.PACE == 1.0:
            return
        for action in bpy.data.actions:
            for curve in self._curves(action):
                for point in curve.keyframe_points:
                    moved = self.clock.screen(point.co.x) - point.co.x
                    point.co.x += moved
                    point.handle_left.x += moved
                    point.handle_right.x += moved
                curve.update()
        for marker in scene.timeline_markers:
            marker.frame = self.clock.screen(marker.frame)
        scene.frame_end = self.clock.length()

    @staticmethod
    def _curves(action):
        if hasattr(action, "fcurves"):
            return list(action.fcurves)
        return [curve for layer in action.layers for strip in layer.strips
                for bag in strip.channelbags for curve in bag.fcurves]
