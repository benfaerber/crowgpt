"""0118 step 0a: fetch Google Research's pretrained BirdMixIT 4-source checkpoint
(gs://gresearch/sound_separation/bird_mixit_model_checkpoints/output_sources4/model.ckpt-3223090)
over HTTPS into data/models/bird_mixit/output_sources4/ and verify inference on a 3s 22.05 kHz tensor.

    pipelines/representation/perch/.venv/bin/python \
        experiments/0118-demixing-overlapping-mobs/download_birdmixit.py
"""

from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA_DIR = Path(os.environ.get("DATA_DIR", REPO / "data"))
OUT_DIR = DATA_DIR / "models" / "bird_mixit" / "output_sources4"

BASE_URL = "https://storage.googleapis.com/gresearch/sound_separation/bird_mixit_model_checkpoints/output_sources4"
FILES = (
    "inference.meta",
    "model.ckpt-3223090.index",
    "model.ckpt-3223090.data-00000-of-00001",
)

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
from crowgpt.progress import Run  # noqa: E402


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run = Run("0118 BirdMixIT checkpoint download", ["download", "verify"])

    with run.stage("download") as st:
        st.update(0, len(FILES))
        for i, fname in enumerate(FILES, 1):
            dest = OUT_DIR / fname
            if not dest.exists() or dest.stat().st_size == 0:
                part = OUT_DIR / f"{fname}.part"
                req = urllib.request.Request(f"{BASE_URL}/{fname}", headers={"User-Agent": "CrowGPT-Research/0.1"})
                with urllib.request.urlopen(req, timeout=180) as resp, open(part, "wb") as f:
                    while True:
                        chunk = resp.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                part.replace(dest)
            st.update(i, len(FILES), extra=f"{fname} ({dest.stat().st_size // 1024} KB)")

    with run.stage("verify") as st:
        os.environ.setdefault("TF_FORCE_GPU_ALLOW_GROWTH", "true")
        os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
        import tensorflow.compat.v1 as tf1
        tf1.disable_v2_behavior()
        graph = tf1.Graph()
        with graph.as_default():
            saver = tf1.train.import_meta_graph(str(OUT_DIR / "inference.meta"))
            in_t = graph.get_tensor_by_name("input_audio/receiver_audio:0")
            out_t = graph.get_tensor_by_name("denoised_waveforms:0")
            with tf1.Session(graph=graph) as sess:
                saver.restore(sess, str(OUT_DIR / "model.ckpt-3223090"))
                dummy = np.random.default_rng(0).standard_normal((1, 1, 3 * 22050)).astype(np.float32) * 0.05
                pred1 = sess.run(out_t, feed_dict={in_t: dummy})
                try:
                    dummy_b = np.repeat(dummy, 4, axis=0)
                    pred_b = sess.run(out_t, feed_dict={in_t: dummy_b})
                    batch_shape = pred_b.shape
                except Exception as exc:  # noqa: BLE001
                    batch_shape = f"no-batch ({str(exc)[:60]})"
                sum_err = float(np.max(np.abs(pred1.sum(axis=1, keepdims=True) - dummy)))
        st.update(1, 1)

    msg = f"Verified BirdMixIT 4-source: in={in_t.shape}, out1={pred1.shape}, out_batch4={batch_shape}, mixture_consistency_max_err={sum_err:.2e}"
    run.note(msg)
    print(msg)


if __name__ == "__main__":
    main()
