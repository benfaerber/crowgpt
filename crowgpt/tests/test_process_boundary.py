"""torch and birdnetlib must never meet, and the check must be enforced.

Importing birdnetlib before torch leaves torch permanently unable to see the
GPU — is_available() False, device_count() 0, no error raised anywhere. It cost
a night of training at roughly 1/240th speed, and the only symptom was that the
run looked slow.

Claiming CUDA first is not a fix: it survives in a small script and reproducibly
does not in a real one. The fix is that the two live in different processes, and
these are the checks that the boundary is guarded from both sides rather than
merely documented.
"""

import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
PYTHON = HERE / ".venv" / "bin" / "python"


def in_fresh_process(code):
    return subprocess.run(
        [str(PYTHON), "-c", code], cwd=str(HERE),
        env={"PYTHONPATH": str(HERE / "src"), "PATH": "/usr/bin:/bin", "HOME": str(Path.home())},
        capture_output=True, text=True, timeout=300,
    )


class TestTheHazardIsReal:
    def test_birdnet_before_torch_costs_the_gpu(self):
        """The bug itself, pinned. If this ever stops failing, the guards can go."""
        result = in_fresh_process(
            "import birdnetlib.analyzer as a, contextlib, os, sys\n"
            "with open(os.devnull,'w') as n, contextlib.redirect_stdout(n): a.Analyzer()\n"
            "import torch; print(torch.cuda.device_count())"
        )
        assert result.stdout.strip().splitlines()[-1] == "0"


class TestTheGuards:
    def test_the_gpu_side_refuses_a_poisoned_process(self):
        result = in_fresh_process(
            "import birdnetlib\n"
            "from crowgpt.gpu import claim\n"
            "try:\n"
            "    claim(); print('NO GUARD')\n"
            "except RuntimeError as e: print('REFUSED')"
        )
        assert "REFUSED" in result.stdout

    def test_the_worker_refuses_a_process_holding_torch(self):
        result = in_fresh_process(
            "import torch, sys\n"
            "sys.argv = ['x', 'confidence', '--dir', '/tmp']\n"
            "try:\n"
            "    import crowgpt.birdnet_worker; print('NO GUARD')\n"
            "except SystemExit as e: print('REFUSED')"
        )
        assert "REFUSED" in result.stdout

    def test_assert_clean_notices_birdnetlib(self):
        from crowgpt.birdnet import BirdNetError, assert_clean

        assert_clean()  # this process is clean
        sys.modules["birdnetlib"] = object()
        try:
            with pytest.raises(BirdNetError, match="GPU side"):
                assert_clean()
        finally:
            del sys.modules["birdnetlib"]


class TestTheBoundaryWorks:
    @pytest.mark.skipif(not PYTHON.exists(), reason="needs the crowgpt venv")
    def test_scoring_through_the_subprocess_leaves_cuda_alone(self):
        """The whole design, end to end: BirdNET runs, the GPU survives."""
        result = in_fresh_process(
            "import numpy as np, torch\n"
            "from crowgpt.gpu import claim\n"
            "from crowgpt.birdnet import BirdNet\n"
            "before = claim() and torch.cuda.device_count()\n"
            "BirdNet().confidence([np.zeros(24000, dtype='float32')])\n"
            "print(before, torch.cuda.device_count())"
        )
        before, after = result.stdout.strip().splitlines()[-1].split()
        assert before == after, "the GPU did not survive a BirdNET call"

    def test_the_gpu_process_never_imports_birdnetlib(self):
        result = in_fresh_process(
            "import numpy as np\n"
            "from crowgpt.birdnet import BirdNet\n"
            "BirdNet().confidence([np.zeros(24000, dtype='float32')])\n"
            "import sys; print('birdnetlib' in sys.modules)"
        )
        assert result.stdout.strip().splitlines()[-1] == "False"
