"""Render the CrowGPT film: prepare audio and font, run Blender, encode with sound.

    python3 promo/video/render.py --quality draft
    python3 promo/video/render.py --quality final
    python3 promo/video/render.py --stills 1,60,120,250,300,480

Frames and the mp4 land in data/video/ (gitignored). The render reports through
crowgpt.progress.Run, so it has a card on the dashboard's Training panel.
"""

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ASSETS = REPO / "promo" / "src" / "assets"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "crowgpt" / "src"))

from crowgpt.progress import Run  # noqa: E402
from film.timeline import FILMS  # noqa: E402


class Workspace:
    NAMES = {"short": "film", "explainer": "explainer", "feature": "feature"}

    def __init__(self, film, quality, shape="wide"):
        data = os.environ.get("DATA_DIR")
        name = self.NAMES[film]
        self.shape = shape
        cut = quality if shape == "wide" else f"{quality}-{shape}"
        self.root = (Path(data).expanduser() if data else REPO / "data") / "video"
        self.work = self.root / "work"
        self.frames = self.root / ("" if film == "short" else name) / cut / "frames"
        self.stills = self.root / "stills"
        self.soundtrack = self.work / ("soundtrack.wav" if film == "short"
                                       else f"soundtrack-{name}.wav")
        self.film = self.root / f"crowgpt-{name}-{cut}.mp4"
        self.blend = self.root / f"crowgpt-{name}.blend"
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
    """The film's calls as 16-bit mono for the scene, and the brand font as a TTF."""

    FONT = ASSETS / "fonts" / "fredoka-latin.woff2"
    WEIGHT = 600

    def __init__(self, workspace):
        self.workspace = workspace

    def prepare(self):
        for name, (source, seconds) in self.workspace.clock.SOUNDS.items():
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", str(ASSETS / source),
                 *(["-t", str(seconds)] if seconds else []),
                 "-ac", "1", "-ar", "22050", "-c:a", "pcm_s16le",
                 str(self.workspace.work / f"{name}.wav")], check=True)
        self._photos()
        self._font()

    def _photos(self):
        from PIL import Image
        for name, (source, box) in self.workspace.clock.PHOTOS.items():
            photo = Image.open(ASSETS / source).convert("RGB")
            wide, tall = photo.size
            left, top, right, bottom = box
            photo.crop((round(left * wide), round(top * tall), round(right * wide),
                        round(bottom * tall))).resize((720, 720), Image.LANCZOS).save(
                self.workspace.work / f"photo-{name}.jpg", quality=92)

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
    """Every call at the moment the picture plays it, over a quiet bed."""

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
        graph, voices, heard = [], [], []
        for index, (name, at, gain) in enumerate(clock.cues()):
            source, seconds = clock.SOUNDS[name]
            heard += ["-i", str(ASSETS / source)]
            trim = (f"atrim=duration={seconds},afade=t=out:st={seconds - 0.25}:d=0.25,"
                    if seconds else "")
            graph.append(f"[{index}:a]{trim}aresample=48000,volume={gain},"
                         f"adelay={round(at * 1000)}:all=1[call{index}]")
            voices.append(f"[call{index}]")
        if self.bed:
            graph += [part.format(d=duration) for part in self.BED]
            voices += ["[wind]", "[low]", "[fifth]", "[high]"]
        spoken = []
        if self.narration:
            graph.append(f"[{len(heard) // 2}:a]aresample=48000[narration]")
            voices.append("[narration]")
            spoken = ["-i", str(self.narration)]
        graph.append(
            f"{''.join(voices)}amix=inputs={len(voices)}:duration=longest:normalize=0,"
            f"alimiter=limit=0.95,apad,atrim=duration={duration},afade=t=in:d=0.4,"
            f"afade=t=out:st={duration - 2.0}:d=2.0[out]")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", *heard, *spoken,
             "-filter_complex", ";".join(graph), "-map", "[out]",
             "-ar", "48000", "-ac", "2", str(self.workspace.soundtrack)], check=True)


class PiperVoice:
    """A stock voice from Piper: small, quick, runs on the CPU, and sounds like a machine."""

    VOICE = "en_US-lessac-medium"
    SOURCE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium"
    #: Piper reads faster than a narrator does; this brings it to the screenplay's pace.
    UNHURRIED = "1.2"

    def __init__(self, folder):
        self.folder = folder

    def _model(self):
        model = self.folder / f"{self.VOICE}.onnx"
        for part in (model, model.with_name(model.name + ".json")):
            if not part.exists() or not part.stat().st_size:
                subprocess.run(["curl", "-sSL", "-o", str(part), f"{self.SOURCE}/{part.name}"],
                               check=True)
        return model

    def say(self, texts):
        model, takes = self._model(), []
        for index, text in enumerate(texts):
            takes.append(self.folder / "lines" / f"line-{index:03d}.wav")
            subprocess.run(
                ["uv", "run", "-q", "--no-project", "--python", "3.11", "--with", "piper-tts",
                 "python", "-m", "piper", "--model", str(model), "--length-scale",
                 self.UNHURRIED, "--output_file", str(takes[-1])],
                input=text.encode(), check=True, capture_output=True)
        return takes


class ClonedVoice:
    """The narrator's own voice, cloned by Chatterbox from a recording of them.

    Needs the GPU for a few minutes, so GPU-CALENDAR.md first. The model lives
    in its own environment under the work folder, built on first use.
    """

    REFERENCE_SECONDS = 20

    def __init__(self, folder, recording):
        self.folder, self.recording = folder, recording

    def _python(self):
        home = self.folder / "chatterbox"
        if not (home / "bin" / "python").exists():
            subprocess.run(["uv", "venv", "-q", str(home), "--python", "3.11"], check=True)
            subprocess.run(["uv", "pip", "install", "-q", "chatterbox-tts", "setuptools<81"], check=True,
                           env={**os.environ, "VIRTUAL_ENV": str(home)})
        return home / "bin" / "python"

    def _reference(self):
        reference = self.folder / "reference.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", "1.0", "-t",
             str(self.REFERENCE_SECONDS), "-i", str(self.recording), "-ac", "1",
             "-af", "highpass=f=70,loudnorm=I=-20", str(reference)], check=True)
        return reference

    def say(self, texts):
        lines = self.folder / "lines.json"
        lines.write_text(json.dumps(texts))
        subprocess.run([str(self._python()), str(HERE / "voice" / "clone.py"),
                        str(self._reference()), str(lines), str(self.folder / "lines")],
                       check=True, capture_output=True)
        return [self.folder / "lines" / f"line-{index:03d}.wav" for index in range(len(texts))]


class ScratchVoice:
    """A synthetic narrator, so the film can be heard before anyone records it.

    Each line of the screenplay is spoken by a model on this machine and laid
    in at the frame the picture expects it. It is a stand-in to judge the
    timing by, never the voice of a finished film. A line that takes longer to
    say than the screenplay allows is reported: a person reading it would be
    squeezed there too.
    """

    SAID_AS = {"CrowGPT": "Crow G P T", "crowgpt.org": "crow G P T dot org", "CawDex": "Caw Dex",
               "Xeno-canto": "Zeeno canto", "AI": "A I"}
    RATE = 48000

    def __init__(self, workspace, figures, kind, recording):
        self.workspace, self.figures = workspace, figures
        folder = workspace.work / "voices"
        (folder / "lines").mkdir(parents=True, exist_ok=True)
        self.voice = ClonedVoice(folder, recording) if kind == "clone" else PiperVoice(folder)
        self.path = workspace.work / f"scratch-voice-{workspace.name}.wav"

    def _spoken(self, text):
        text = re.sub(r"\{([a-z_.]+)\}", lambda found: self.figures[found.group(1)]["text"],
                      " ".join(text.split()))
        for written, said in sorted(self.SAID_AS.items(), key=lambda pair: -len(pair[0])):
            text = re.sub(rf"\b{re.escape(written)}\b", said, text)
        return text.replace('"', "")

    def _heard(self, take):
        """One take as samples at the track's rate, with the silence around it cut."""
        raw = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-i", str(take), "-af",
             "silenceremove=start_periods=1:start_threshold=-45dB", "-ac", "1", "-ar",
             str(self.RATE), "-f", "f32le", "-"], check=True, capture_output=True).stdout
        return np.frombuffer(raw, dtype=np.float32)

    def record(self):
        clock = self.workspace.clock
        lines = [line for line in clock.PLAY.lines() if line.text]
        takes = self.voice.say([self._spoken(line.text) for line in lines])
        track = np.zeros(int((clock.duration() + 1.0) * self.RATE), dtype=np.float32)
        squeezed = []
        for line, take in zip(lines, takes):
            said = self._heard(take)
            start = int(clock.seconds(line.start + 2) * self.RATE)
            said = said[:len(track) - start]
            track[start:start + len(said)] += said
            over = len(said) / self.RATE - (line.speaking + line.BREATH)
            if over > 0.25:
                squeezed.append((over, " ".join(line.text.split())))
        with wave.open(str(self.path), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(self.RATE)
            out.writeframes((np.clip(track, -1.0, 1.0) * 32767).astype(np.int16).tobytes())
        for over, text in sorted(squeezed, reverse=True):
            print(f"scratch voice ran {over:.1f}s over: {text}")
        return self.path


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

    def save(self, workspace, quality, threads):
        """Write the scene as a .blend with its soundtrack, to scrub and play in Blender."""
        subprocess.run(self.command(workspace, quality, threads, workspace.frames,
                                    ["--save", str(workspace.blend),
                                     "--sound", str(workspace.soundtrack)]), check=True)
        return workspace.blend

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
    parser.add_argument("--shape", choices=("wide", "square", "tall"), default="wide",
                        help="square and tall (9:16) keep the wide frame's width and add sky and ground")
    parser.add_argument("--stills", help="comma-separated frames to render instead of the film")
    parser.add_argument("--blender", help="path to the blender executable")
    parser.add_argument("--threads", type=int, default=24)
    parser.add_argument("--device", choices=("cpu", "gpu"), default="cpu",
                        help="gpu only when GPU-CALENDAR.md says the card is free")
    parser.add_argument("--fresh", action="store_true", help="discard frames already rendered")
    parser.add_argument("--script", action="store_true",
                        help="print the narration with the time each line starts, and stop")
    parser.add_argument("--no-bed", action="store_true", help="calls only, no ambient bed")
    parser.add_argument("--blend", action="store_true",
                        help="write the scene and its soundtrack as a .blend to play in Blender, "
                             "and stop")
    parser.add_argument("--scratch-voice", choices=("clone", "piper"), nargs="?", const="clone",
                        help="narrate with a synthetic voice, to preview the timing with sound: "
                             "a clone of --voice-of (needs the GPU), or Piper's stock voice")
    parser.add_argument("--voice-of", type=Path,
                        default=REPO / "data" / "video" / "narration" / "explainer.wav",
                        help="a recording of the narrator for --scratch-voice clone to copy")
    parser.add_argument("--narration", type=Path,
                        help="a voice recording made against the film, laid in from its first frame")
    options = parser.parse_args()

    if options.script:
        figures = json.loads((REPO / "promo" / "stats.json").read_text())["figures"]
        print(re.sub(r"\{([a-z_.]+)\}", lambda found: figures[found.group(1)]["text"],
                     FILMS[options.film].PLAY.script()))
        return
    workspace = Workspace(options.film, options.quality, options.shape)
    blender = Blender(options.blender, options.device)
    if options.stills:
        Ingredients(workspace).prepare()
        blender.stills(workspace, options.quality, options.threads, options.stills)
        print(f"stills in {workspace.stills}")
        return

    if options.blend:
        Ingredients(workspace).prepare()
        narration = options.narration
        if options.scratch_voice:
            figures = json.loads((REPO / "promo" / "stats.json").read_text())["figures"]
            narration = ScratchVoice(workspace, figures, options.scratch_voice,
                                     options.voice_of).record()
        Soundtrack(workspace, bed=not options.no_bed, narration=narration).mix()
        print(blender.save(workspace, options.quality, options.threads))
        return

    run = Run(f"CrowGPT {Workspace.NAMES[options.film]} ({workspace.film.stem.split('-', 2)[2]})", ["prepare", "render", "encode"])
    with run.stage("prepare"):
        if options.fresh:
            workspace.clear_frames()
        Ingredients(workspace).prepare()
        narration = options.narration
        if options.scratch_voice:
            figures = json.loads((REPO / "promo" / "stats.json").read_text())["figures"]
            narration = ScratchVoice(workspace, figures, options.scratch_voice,
                                     options.voice_of).record()
        Soundtrack(workspace, bed=not options.no_bed, narration=narration).mix()
    with run.stage("render") as stage:
        blender.animation(workspace, options.quality, options.threads,
                          lambda done: stage.update(done, workspace.clock.length(), "frames"))
    with run.stage("encode"):
        Encoder(workspace).encode()
    run.note(str(workspace.film))
    print(workspace.film)


if __name__ == "__main__":
    main()
