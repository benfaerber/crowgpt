"""Claim CUDA before anything else can take it away.

THE BUG THIS EXISTS FOR, because it cost a night and was invisible.

Importing birdnetlib (and through it tflite_runtime) BEFORE torch leaves torch
permanently unable to see the GPU in that process — `torch.cuda.is_available()`
returns False and `device_count()` returns 0, with no error anywhere. The
reverse order is fine, and CUDA survives BirdNET loading afterwards:

    torch first  -> cuda True,  still True after BirdNET loads
    BirdNET first -> cuda False, device_count 0, forever

Every stage of this project touches BirdNET, and extract touches it first. So
the overnight run tokenised and trained on the CPU, roughly 240x slower,
reaching 1,500 steps of 40,000 in ten hours while looking merely slow. The fork
in extract was blamed first and was innocent.

CLAIMING FIRST HELPS AND IS NOT RELIABLE. Initialising CUDA before BirdNET
loads does survive in a small script, and reproducibly does NOT survive in the
real one — same order, same claim, device_count back to 0 once the analyzer is
built. Whatever tflite does to the process, winning the race is not a guarantee.

THE REAL FIX IS TO STOP SHARING A PROCESS, and this module is the evidence for
it rather than the solution. crowgpt was given one venv holding torch AND
birdnetlib, to avoid handing off between interpreters — and that decision is
what created this. The rest of the repo already does it the other way:
.venv-birdnet has no torch in it, so analyzer/ and the pipelines have never had
this failure and cannot.

So treat claim() as a seatbelt, not a design. The GPU stages and the BirdNET
stages belong in separate processes, talking through files, exactly as
build_dataset.py and gpu_mlp.py already do.
"""


def claim():
    """Initialise CUDA now. Returns whether a GPU is present.

    Allocating is the point — merely calling is_available() does not create the
    context, and it is the context that BirdNET's arrival must not prevent.

    Raises if birdnetlib is already here, because at that point the GPU is
    already gone and every later symptom is slowness rather than an error.
    """
    import sys

    if "birdnetlib" in sys.modules:
        raise RuntimeError(
            "birdnetlib is imported in this process. torch cannot see the GPU "
            "once that has happened, and the only symptom is a run ~240x slower.\n"
            "  Reach BirdNET through crowgpt.birdnet (a subprocess) instead."
        )
    import torch

    if not torch.cuda.is_available():
        return False
    torch.zeros(1, device="cuda")
    return True
