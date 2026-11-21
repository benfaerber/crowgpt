"""Say each line of a script in the voice of a reference recording, with Chatterbox.

    python clone.py reference.wav lines.json out/

Run by render.py inside Chatterbox's own environment, never imported: the model
needs a torch build the rest of the film's tooling does not carry. One wav per
line, numbered in order, 16-bit mono.
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

    def say(self, text, target):
        spoken = self.model.generate(text, cfg_weight=0.4)
        torchaudio.save(str(target), spoken.cpu(), self.model.sr, encoding="PCM_S",
                        bits_per_sample=16)


def main():
    reference, lines, folder = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    cloner = Cloner(reference)
    for index, text in enumerate(json.loads(lines.read_text())):
        cloner.say(text, folder / f"line-{index:03d}.wav")


if __name__ == "__main__":
    main()
