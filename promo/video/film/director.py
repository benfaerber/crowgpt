"""The shot list: who is where, when the camera cuts, and what the audio drives."""

import math
import random
from pathlib import Path

import bpy

from .audio import Clip
from .crow import FlyingCrow, PerchedCrow, Plumage
from .kit import Keys, Materials, Stage
from .sets import Caption, Dusk, Lattice, Lockup, PowerLine, SoundRings, Spectrogram, TokenStream
from .timeline import Timeline


class Fonts:
    def __init__(self, folder):
        self.display = bpy.data.fonts.load(str(Path(folder) / "fredoka.ttf"))


class Camera:
    """A camera that always looks at its own target."""

    def __init__(self, stage, name, lens, focus_stop=None):
        data = bpy.data.cameras.new(name)
        data.lens = lens
        data.clip_end = 6000.0
        self.body = bpy.data.objects.new(name, data)
        stage.collection.objects.link(self.body)
        self.target = stage.pivot(f"{name} target")
        aim = self.body.constraints.new("TRACK_TO")
        aim.target = self.target
        aim.track_axis, aim.up_axis = "TRACK_NEGATIVE_Z", "UP_Y"
        if focus_stop:
            data.dof.use_dof = True
            data.dof.focus_object = self.target
            data.dof.aperture_fstop = focus_stop

    def move(self, frame, position, looking_at):
        Keys.at(self.body, frame, location=position)
        Keys.at(self.target, frame, location=looking_at)
        return self


class Film:
    COLUMNS = 64
    BANDS = 18
    REAL_CROW_X = 0.0
    GENERATED_CROW_X = 84.0
    DECODER_HEIGHT = 9.0
    CLOCK = Timeline

    def __init__(self, work, logo, stats=None):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.scene = bpy.context.scene
        self.scene.render.fps = self.CLOCK.FPS
        self.scene.frame_start, self.scene.frame_end = 1, self.CLOCK.END
        self.stats = stats
        self.stage = Stage(self.scene)
        self.fonts = Fonts(work)
        self.logo = logo
        self.real_call = Clip(Path(work) / "real.wav", Timeline.FPS)
        self.generated_call = Clip(Path(work) / "generated.wav", Timeline.FPS)
        self.rings = None
        self.crow = None

    def build(self):
        Dusk(self.stage)
        PowerLine(self.stage)
        self.rings = SoundRings(self.stage)
        self._the_call()
        self._the_machine()
        self._the_reply()
        self._the_finale()
        return self.scene

    def _cut(self, frame, camera):
        marker = self.scene.timeline_markers.new(camera.body.name, frame=frame)
        marker.camera = camera.body
        if frame <= 1:
            self.scene.camera = camera.body

    def _call_out(self, crow, clip, start, direction, not_before=0):
        crow.caw(start, clip.envelope())
        for onset in clip.onsets():
            if start + onset >= not_before:
                self.rings.emit(start + onset, crow.beak_tip(), direction)

    def _the_call(self):
        self.crow = PerchedCrow(self.stage, "Crow", Plumage.living())
        self.crow.place(PowerLine.perch(self.REAL_CROW_X))
        self.crow.look(1, yaw=-0.55)
        self.crow.look(10, yaw=-0.55)
        self.crow.look(Timeline.REAL_CALL - 2, yaw=0.0)
        self._call_out(self.crow, self.real_call, Timeline.REAL_CALL, 1.0)
        camera = Camera(self.stage, "Call camera", 40.0, focus_stop=2.8)
        camera.move(1, (4.2, -10.0, 4.2), (0.6, 0.0, 5.6))
        camera.move(Timeline.DECODE_CUT, (1.0, -1.9, 5.12), (0.3, 0.0, 5.34))
        self._cut(1, camera)

    def _the_machine(self):
        floor = self.DECODER_HEIGHT
        heard = Spectrogram(self.stage, "Heard",
                            self.real_call.spectrogram(self.COLUMNS, self.BANDS),
                            (40.0, 0.0, floor))
        lattice = Lattice(self.stage, (60.5, 0.0, floor + 1.6))
        said = Spectrogram(self.stage, "Said",
                           self.generated_call.spectrogram(self.COLUMNS, self.BANDS),
                           (68.0, 0.0, floor))
        heard.rise(Timeline.REAL_CALL, self.real_call.frames)
        said.rise(Timeline.GENERATED_CALL, self.generated_call.frames)
        tokens = TokenStream(self.stage, heard, lattice, said)
        first_token = tokens.flow(Timeline.TOKENS_LAND, self.generated_call.frames)
        lattice.think(first_token + TokenStream.LIFT + TokenStream.APPROACH - 8,
                      Timeline.GENERATED_CALL + self.generated_call.frames)

        captions = Caption(self.stage, self.fonts)
        captions.stand("a real crow call", (46.0, -2.8, floor - 0.75), Timeline.DECODE_CUT + 8)
        captions.stand("CrowGPT", (60.5, -2.8, floor - 0.75), first_token + 40)
        captions.stand("a generated call", (74.0, -2.8, floor - 0.75),
                       Timeline.GENERATED_CALL + 4)

        camera = Camera(self.stage, "Machine camera", 28.0)
        for frame, x in ((Timeline.DECODE_CUT, 45.5), (first_token + 4, 46.5),
                         (Timeline.TOKENS_LAND - 14, 60.0), (Timeline.GENERATED_CALL + 30, 72.5),
                         (Timeline.REPLY_CUT, 73.5)):
            camera.move(frame, (x - 2.5, -13.0, floor + 1.9), (x + 0.5, 0.0, floor + 1.2))
        self._cut(Timeline.DECODE_CUT, camera)

    def _the_reply(self):
        reply = PerchedCrow(self.stage, "Generated crow", Plumage.generated())
        reply.place(PowerLine.perch(self.GENERATED_CROW_X), heading=math.pi)
        self._call_out(reply, self.generated_call, Timeline.GENERATED_CALL, -1.0,
                       not_before=Timeline.REPLY_CUT - 12)
        camera = Camera(self.stage, "Reply camera", 55.0, focus_stop=2.8)
        x = self.GENERATED_CROW_X
        camera.move(Timeline.REPLY_CUT, (x - 1.15, -1.7, 5.5), (x - 0.18, 0.0, 5.32))
        camera.move(Timeline.FINALE_CUT, (x - 0.95, -1.5, 5.46), (x - 0.18, 0.0, 5.32))
        self._cut(Timeline.REPLY_CUT, camera)

    def _the_finale(self):
        cut = Timeline.FINALE_CUT
        self.crow.look(cut - 1, yaw=-0.5)
        self.crow.look(cut + 12, yaw=0.15, tilt=0.28)
        self.crow.look(cut + 66, yaw=0.15, tilt=0.28)
        self.crow.look(cut + 82, yaw=-0.9, tilt=0.0)
        self.crow.look(Timeline.END, yaw=-0.95, tilt=-0.12)

        Lockup(self.stage, self.fonts, self.logo, (0.9, 2.0, 7.0), size=0.8).reveal(
            Timeline.TITLE)
        self._flock(cut + 4)

        camera = Camera(self.stage, "Finale camera", 32.0)
        camera.move(cut, (1.3, -5.0, 4.6), (1.9, 0.0, 6.05))
        camera.move(Timeline.END, (1.6, -6.2, 4.6), (2.1, 0.0, 6.1))
        self._cut(cut, camera)

    def _flock(self, start):
        dice = random.Random(5)
        shadow = Materials.flat("Flock", "#0c0a12")
        for index in range(9):
            y = dice.uniform(22.0, 55.0)
            z = dice.uniform(8.5, 16.0)
            bird = FlyingCrow(self.stage, f"Flyer {index}", shadow, size=dice.uniform(1.5, 2.1))
            bird.flap(dice.uniform(0.0, FlyingCrow.FLAP_FRAMES))
            bird.cross(start + dice.uniform(0.0, 30.0), self.CLOCK.END + dice.uniform(0.0, 40.0),
                       (dice.uniform(-52.0, -34.0), y, z),
                       (dice.uniform(48.0, 70.0), y, z + dice.uniform(-1.5, 2.5)))


class Darkroom:
    """Render settings. Cycles on the CPU unless asked: the GPU is usually booked for training."""

    QUALITY = {
        "draft": {"size": (960, 540), "samples": 16},
        "final": {"size": (1920, 1080), "samples": 48},
    }

    def __init__(self, scene, quality, threads, device="cpu"):
        self.scene = scene
        preset = self.QUALITY[quality]
        render = scene.render
        render.engine = "CYCLES"
        render.resolution_x, render.resolution_y = preset["size"]
        render.resolution_percentage = 100
        render.image_settings.file_format = "PNG"
        render.use_overwrite = False
        render.use_persistent_data = True
        render.threads_mode, render.threads = "FIXED", threads
        cycles = scene.cycles
        cycles.device = "GPU" if device == "gpu" and self._claim_gpu() else "CPU"
        cycles.samples = preset["samples"]
        cycles.use_adaptive_sampling = True
        cycles.adaptive_threshold = 0.04
        cycles.use_denoising = True
        cycles.max_bounces = 4
        self._grade()
        self._bloom()

    @staticmethod
    def _claim_gpu():
        settings = bpy.context.preferences.addons["cycles"].preferences
        for backend in ("OPTIX", "CUDA"):
            try:
                settings.compute_device_type = backend
            except TypeError:
                continue
            settings.get_devices()
            cards = [device for device in settings.devices if device.type == backend]
            if cards:
                for device in settings.devices:
                    device.use = device.type == backend
                print(f"film: rendering on {backend}: {cards[0].name}")
                return True
        print("film: no GPU Cycles can use; rendering on the CPU")
        return False

    def _grade(self):
        view = self.scene.view_settings
        for transform in ("AgX", "Filmic"):
            try:
                view.view_transform = transform
                break
            except TypeError:
                continue
        for look in ("AgX - Medium High Contrast", "Medium High Contrast"):
            try:
                view.look = look
                break
            except TypeError:
                continue

    def _bloom(self):
        tree, layers, output = self._compositor()
        glare = tree.nodes.new("CompositorNodeGlare")
        if "Type" in glare.inputs:
            glare.inputs["Type"].default_value = "Bloom"
        else:
            glare.glare_type = "BLOOM"
        for name, value in (("Threshold", 1.2), ("Strength", 0.7), ("Size", 0.6)):
            if name in glare.inputs:
                glare.inputs[name].default_value = value
        tree.links.new(layers.outputs["Image"], glare.inputs["Image"])
        tree.links.new(glare.outputs["Image"], output.inputs["Image"])

    def _compositor(self):
        """Blender 5 keeps the compositor in a node group; 4.x keeps it on the scene."""
        if hasattr(self.scene, "compositing_node_group"):
            tree = bpy.data.node_groups.new("Grade", "CompositorNodeTree")
            tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
            self.scene.compositing_node_group = tree
            return (tree, tree.nodes.new("CompositorNodeRLayers"),
                    tree.nodes.new("NodeGroupOutput"))
        self.scene.use_nodes = True
        tree = self.scene.node_tree
        return (tree, tree.nodes.get("Render Layers") or tree.nodes.new("CompositorNodeRLayers"),
                tree.nodes.get("Composite") or tree.nodes.new("CompositorNodeComposite"))

    def stills(self, frames, folder):
        for frame in frames:
            self.scene.frame_set(frame)
            self.scene.render.filepath = str(Path(folder) / f"still-{frame:04d}.png")
            bpy.ops.render.render(write_still=True)

    def animation(self, folder, start, end):
        self.scene.frame_start, self.scene.frame_end = start, end
        self.scene.render.filepath = f"{folder}/"
        bpy.ops.render.render(animation=True)
