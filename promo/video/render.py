"""Render the CrowGPT film: prepare audio and font, run Blender, encode with sound.

    python3 promo/video/render.py --quality draft
    python3 promo/video/render.py --quality final
    python3 promo/video/render.py --stills 1,60,120,250,300,480

Frames and the mp4 land in data/video/ (gitignored). The render reports through
crowgpt.progress.Run, so it has a card on the dashboard's Training panel.
"""

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ASSETS = REPO / "promo" / "src" / "assets"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "crowgpt" / "src"))

from crowgpt.progress import Run  # noqa: E402
from film.timeline import FILMS  # noqa: E402


class Workspace:
    NAMES = {"short": "film", "explainer": "explainer"}

    def __init__(self, film, quality, shape="wide"):
        data = os.environ.get("DATA_DIR")
        name = self.NAMES[film]
        self.shape = shape
        cut = quality if shape == "wide" else f"{quality}-{shape}"
        self.root = (Path(data).expanduser() if data else REPO / "data") / "video"
        self.work = self.root / "work"
        self.frames = self.root / ("" if film == "short" else name) / quality / "frames"
        self.stills = self.root / "stills"
        self.soundtrack = self.work / ("soundtrack.wav" if film == "short"
                                       else f"soundtrack-{name}.wav")
        self.film = self.root / f"crowgpt-{name}-{cut}.mp4"
        self.clock = FILMS[film]
        self.name = film
        for folder in (self.work, self.frames, self.stills):
            folder.mkdir(parents=True, exist_ok=True)

    def rendered(self):
        return len(list(self.frames.glob("[0-9][0-9][0-9][0-9].png")))

    def clear_frames(self):
        shutil.rmtree(self.frames)
        self.frames.mkdir(parents=True)


class Ingredients:
    """The two calls as 16-bit mono for the scene, and the brand font as a TTF."""

    CALLS = {"real": "real-alarm-call.wav", "generated": "crowgpt2-preview.wav"}
    FONT = ASSETS / "fonts" / "fredoka-latin.woff2"
    WEIGHT = 600

    def __init__(self, workspace):
        self.workspace = workspace

    def prepare(self):
        for name, source in self.CALLS.items():
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", str(ASSETS / source),
                 "-ac", "1", "-ar", "22050", "-c:a", "pcm_s16le",
                 str(self.workspace.work / f"{name}.wav")], check=True)
        self._font()

    def _font(self):
        from fontTools.ttLib import TTFont
        font = TTFont(self.FONT)
        if "fvar" in font:
            from fontTools.varLib import instancer
            axes = {axis.axisTag: axis.defaultValue for axis in font["fvar"].axes}
            weight = next(axis for axis in font["fvar"].axes if axis.axisTag == "wght")
            axes["wght"] = min(max(self.WEIGHT, weight.minValue), weight.maxValue)
            font = instancer.instantiateVariableFont(font, axes)
        font.flavor = None
        font.save(self.workspace.work / "fredoka.ttf")


class Soundtrack:
    """Both calls at the frames the picture plays them, over a quiet bed."""

    BED = [
        "anoisesrc=color=brown:amplitude=0.4:duration={d},lowpass=f=380,volume=0.10[wind]",
        "sine=frequency=110:duration={d},volume=0.045[low]",
        "sine=frequency=164.81:duration={d},volume=0.03[fifth]",
        "sine=frequency=220.7:duration={d},volume=0.018[high]",
    ]

    def __init__(self, workspace, bed=True, narration=None):
        self.workspace = workspace
        self.bed = bed
        self.narration = narration

    def mix(self):
        clock = self.workspace.clock
        duration = clock.duration()
        real_ms = round(clock.seconds(clock.CUES["real"]) * 1000)
        generated_ms = round(clock.seconds(clock.CUES["generated"]) * 1000)
        graph = [f"[0:a]aresample=48000,adelay={real_ms}:all=1[real]",
                 f"[1:a]aresample=48000,adelay={generated_ms}:all=1[generated]"]
        voices = ["[real]", "[generated]"]
        if self.bed:
            graph += [part.format(d=duration) for part in self.BED]
            voices += ["[wind]", "[low]", "[fifth]", "[high]"]
        spoken = []
        if self.narration:
            graph.append("[2:a]aresample=48000[narration]")
            voices.append("[narration]")
            spoken = ["-i", str(self.narration)]
        graph.append(
            f"{''.join(voices)}amix=inputs={len(voices)}:duration=longest:normalize=0,"
            f"alimiter=limit=0.95,apad,atrim=duration={duration},afade=t=in:d=0.4,"
            f"afade=t=out:st={duration - 2.0}:d=2.0[out]")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-i", str(ASSETS / Ingredients.CALLS["real"]),
             "-i", str(ASSETS / Ingredients.CALLS["generated"]), *spoken,
             "-filter_complex", ";".join(graph), "-map", "[out]",
             "-ar", "48000", "-ac", "2", str(self.workspace.soundtrack)], check=True)


class Blender:
    SUPPORTED = ((4, 2), (5, 2))
    FLATPAK = "org.blender.Blender"

    def __init__(self, chosen, device="cpu"):
        self.device = device
        self.launch = self._find(chosen)
        banner = subprocess.run([*self.launch, "--version"], capture_output=True, text=True)
        found = re.search(r"Blender (\d+)\.(\d+)", banner.stdout)
        self.version = tuple(int(part) for part in found.groups()) if found else (0, 0)
        low, high = self.SUPPORTED
        if not low <= self.version <= high:
            sys.exit(f"Blender {'.'.join(map(str, self.version))} found; the scene is tested "
                     f"on {high[0]}.{high[1]} and written to run from {low[0]}.{low[1]}")

    def _find(self, chosen):
        named = chosen or os.environ.get("BLENDER")
        if named:
            return shlex.split(named)
        if shutil.which("blender"):
            return ["blender"]
        flatpak = shutil.which("flatpak")
        if flatpak and subprocess.run([flatpak, "info", self.FLATPAK],
                                      capture_output=True).returncode == 0:
            return [flatpak, "run", self.FLATPAK]
        sys.exit("Blender not found. Install it, or pass --blender '/path/to/blender'")

    def command(self, workspace, quality, threads, frames_folder, extra):
        return [*self.launch, "-b", "--factory-startup", "--python", str(HERE / "scene.py"),
                "--", "--work", str(workspace.work), "--frames", str(frames_folder),
                "--logo", str(REPO / "images" / "crowgpt-logo.svg"),
                "--film", workspace.name, "--device", self.device, "--stats", str(REPO / "promo" / "stats.json"),
                "--quality", quality, "--shape", workspace.shape, "--threads", str(threads), *extra]

    def stills(self, workspace, quality, threads, frames):
        subprocess.run(self.command(workspace, quality, threads, workspace.stills,
                                    ["--stills", frames]), check=True)

    def animation(self, workspace, quality, threads, on_progress):
        log = (workspace.work / "blender.log").open("w")
        job = subprocess.Popen(
            self.command(workspace, quality, threads, workspace.frames, []),
            stdout=log, stderr=subprocess.STDOUT)
        while job.poll() is None:
            time.sleep(5)
            on_progress(workspace.rendered())
        on_progress(workspace.rendered())
        if job.returncode or workspace.rendered() < workspace.clock.length():
            raise RuntimeError(
                f"Blender stopped with {workspace.rendered()}/{workspace.clock.length()} frames; "
                f"see {workspace.work / 'blender.log'}")


class Encoder:
    def __init__(self, workspace):
        self.workspace = workspace

    def encode(self):
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(self.workspace.clock.FPS),
             "-i", str(self.workspace.frames / "%04d.png"), "-i", str(self.workspace.soundtrack),
             "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest",
             str(self.workspace.film)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--film", choices=sorted(FILMS), default="short")
    parser.add_argument("--quality", choices=("preview", "draft", "final"), default="draft")
    parser.add_argument("--shape", choices=("wide", "square"), default="wide",
                        help="square keeps the wide frame's width and adds sky and ground")
    parser.add_argument("--stills", help="comma-separated frames to render instead of the film")
    parser.add_argument("--blender", help="path to the blender executable")
    parser.add_argument("--threads", type=int, default=24)
    parser.add_argument("--device", choices=("cpu", "gpu"), default="cpu",
                        help="gpu only when GPU-CALENDAR.md says the card is free")
    parser.add_argument("--fresh", action="store_true", help="discard frames already rendered")
    parser.add_argument("--no-bed", action="store_true", help="calls only, no ambient bed")
    parser.add_argument("--narration", type=Path,
                        help="a voice recording made against the film, laid in from its first frame")
    options = parser.parse_args()

    workspace = Workspace(options.film, options.quality, options.shape)
    blender = Blender(options.blender, options.device)
    if options.stills:
        Ingredients(workspace).prepare()
        blender.stills(workspace, options.quality, options.threads, options.stills)
        print(f"stills in {workspace.stills}")
        return

    run = Run(f"CrowGPT {Workspace.NAMES[options.film]} ({workspace.film.stem.split('-', 2)[2]})", ["prepare", "render", "encode"])
    with run.stage("prepare"):
        if options.fresh:
            workspace.clear_frames()
        Ingredients(workspace).prepare()
        Soundtrack(workspace, bed=not options.no_bed, narration=options.narration).mix()
    with run.stage("render") as stage:
        blender.animation(workspace, options.quality, options.threads,
                          lambda done: stage.update(done, workspace.clock.length(), "frames"))
    with run.stage("encode"):
        Encoder(workspace).encode()
    run.note(str(workspace.film))
    print(workspace.film)


if __name__ == "__main__":
    main()
