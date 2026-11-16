"""0095, second half: an audio-language model asked the question Ben answers.

Zero-shot, so no pool is training data: every graded trial is a test. The
model hears the real reference and both clips and its answer is read from
the next-token odds of "A" against "B". Each trial is asked in both orders
and the two readings are halved, which removes any taste for a position.
"""
import html
import json
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "crowgpt" / "src"))

import librosa
import numpy as np
import torch
from transformers import AutoProcessor, BitsAndBytesConfig, Qwen2AudioForConditionalGeneration

from crowgpt.progress import Run
from judging import DB, OPEN_POOLS, POOLS_DIR, TRAIN_POOLS, Scorer, Trials

MODEL = "Qwen/Qwen2-Audio-7B-Instruct"
SCORES = HERE / "alm_scores.json"


class Questions:
    """Each pool's own question, as Ben read it, without the markup."""

    def __init__(self, db=DB):
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            self.by_pool = {name: self.plain(question) for name, question in
                            conn.execute("SELECT name, question FROM listening_pools")}
        finally:
            conn.close()

    @staticmethod
    def plain(question):
        return html.unescape(re.sub(r"<[^>]+>", "", question)).strip()


class AudioJudge:
    def __init__(self):
        self.processor = AutoProcessor.from_pretrained(MODEL)
        self.model = Qwen2AudioForConditionalGeneration.from_pretrained(
            MODEL, device_map="cuda",
            quantization_config=BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_quant_type="nf4")).eval()
        self.rate = self.processor.feature_extractor.sampling_rate
        tokenizer = self.processor.tokenizer
        self.a, self.b = (tokenizer.encode(letter, add_special_tokens=False)[0] for letter in "AB")
        self.clips = {}

    def clip(self, pool, name):
        key = (pool, name)
        if key not in self.clips:
            self.clips[key] = librosa.load(POOLS_DIR / pool / name, sr=self.rate)[0]
        return self.clips[key]

    def prefers_a(self, question, reference, a, b):
        """Log odds that the answer is A."""
        conversation = [{"role": "user", "content": [
            {"type": "text", "text": "You are judging synthetic crow calls against real ones. "
                                     "Reference, a real recording of a crow:"},
            {"type": "audio", "audio_url": "reference"},
            {"type": "text", "text": "Clip A:"},
            {"type": "audio", "audio_url": "a"},
            {"type": "text", "text": "Clip B:"},
            {"type": "audio", "audio_url": "b"},
            {"type": "text", "text": f"{question}\nAnswer with one letter, A or B."},
        ]}]
        text = self.processor.apply_chat_template(
            conversation, add_generation_prompt=True, tokenize=False)
        audio = [reference, a, b]
        try:
            inputs = self.processor(text=text, audio=audio, sampling_rate=self.rate,
                                    return_tensors="pt", padding=True)
        except TypeError:
            inputs = self.processor(text=text, audios=audio, sampling_rate=self.rate,
                                    return_tensors="pt", padding=True)
        inputs = {k: v.to("cuda") for k, v in inputs.items()}
        with torch.no_grad():
            logits = self.model(**inputs).logits[0, -1].float()
        return float(logits[self.a] - logits[self.b])

    def toward_first(self, question, trial):
        pool = trial["pool"]
        reference = self.clip(pool, trial["anchor_clip"])
        first = self.clip(pool, trial["first_clip"])
        second = self.clip(pool, trial["second_clip"])
        forward = self.prefers_a(question, reference, first, second)
        backward = self.prefers_a(question, reference, second, first)
        return {"toward_first": (forward - backward) / 2, "position_bias": (forward + backward) / 2}


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run = Run("0095 — AN AUDIO-LANGUAGE JUDGE", ["load", "judge", "score"])
    trials = Trials()
    questions = Questions()
    everything = [t for pool in TRAIN_POOLS + OPEN_POOLS for t in trials.of(pool)]
    if limit:
        everything = everything[:limit]
    scores = json.loads(SCORES.read_text()) if SCORES.exists() and not limit else {}

    with run.stage("load") as stage:
        judge = AudioJudge()
        stage.update(1, 1)

    with run.stage("judge") as stage:
        for n, trial in enumerate(everything):
            key = str(trial["id"])
            if key not in scores:
                scores[key] = judge.toward_first(questions.by_pool[trial["pool"]], trial)
                if not limit and n % 10 == 0:
                    SCORES.write_text(json.dumps(scores, indent=1) + "\n")
            stage.update(n + 1, len(everything), extra=trial["pool"])
        if not limit:
            SCORES.write_text(json.dumps(scores, indent=1) + "\n")

    with run.stage("score") as stage:
        report = {"model": MODEL, "quantization": "4-bit nf4", "pools": {}}
        for pool in TRAIN_POOLS + OPEN_POOLS:
            graded = [t for t in everything if t["pool"] == pool and t["grade"] is not None]
            if graded:
                predictions = np.asarray([scores[str(t["id"])]["toward_first"] for t in graded])
                report["pools"][pool] = Scorer.fold(predictions, graded)
        done = [report["pools"][p] for p in TRAIN_POOLS if p in report["pools"]]
        if done:
            report["mean_spearman_completed_pools"] = round(
                float(np.mean([f["spearman"] for f in done])), 3)
        report["mean_abs_position_bias"] = round(float(np.mean(
            [abs(s["position_bias"]) for s in scores.values()])), 3)
        report["mean_abs_toward_first"] = round(float(np.mean(
            [abs(s["toward_first"]) for s in scores.values()])), 3)
        stage.update(1, 1)

    if not limit:
        (HERE / "alm_results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
