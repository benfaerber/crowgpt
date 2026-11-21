"""Say each line of a script in the voice of a reference recording, with Chatterbox.

    python clone.py reference.wav lines.json out/

Run by render.py inside Chatterbox's own environment, never imported: the model
needs a torch build the rest of the film's tooling does not carry. One wav per
line, numbered in order, 16-bit mono. lines.json is a list of [text, seconds
allowed] pairs.
"""

import json
import sys
from pathlib import Path

import torch
import torchaudio
from chatterbox.tts import ChatterboxTTS


class Cloner:
    def __init__(self, reference):
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = ChatterboxTTS.from_pretrained(device=device)
        self.model.prepare_conditionals(str(reference))

    TAKES = 5

    def say(self, text, allowed, target):
        """The first take that fits its slot, or the shortest: the model sometimes rambles on."""
        spoken = None
        for _ in range(self.TAKES):
            take = self.model.generate(text, cfg_weight=0.4)
            if spoken is None or take.shape[-1] < spoken.shape[-1]:
                spoken = take
            if spoken.shape[-1] / self.model.sr <= allowed:
                break
        torchaudio.save(str(target), spoken.cpu(), self.model.sr, encoding="PCM_S",
                        bits_per_sample=16)


def main():
    reference, lines, folder = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    cloner = Cloner(reference)
    for index, (text, allowed) in enumerate(json.loads(lines.read_text())):
        cloner.say(text, allowed, folder / f"line-{index:03d}.wav")


if __name__ == "__main__":
    main()
