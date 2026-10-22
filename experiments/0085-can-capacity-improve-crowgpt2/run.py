"""Bounded overnight candidate build; run with crowgpt/.venv/bin/python."""
import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / 'crowgpt/src'))
from crowgpt.progress import Run
from crowgpt.train import Trainer
import torch

DATA = Path(os.environ.get('DATA_DIR', REPO / 'data'))
MODEL = REPO / 'crowgpt/results/model-crowgpt3-candidate-0085'
RECIPE = dict(steps=30000, batch_size=4, accumulate=2, n_embd=512,
              n_layer=12, n_head=4, dropout=0.0, seed=0,
              learning_rate=3e-4, warmup=200, eval_every=1000,
              eval_batches=20, patience_steps=8000)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    run = Run('0085 CrowGPT3 candidate' + (' preflight' if args.preflight_only else ''),
              ['preflight'] if args.preflight_only else ['preflight', 'train', 'validate'])
    with run.stage('preflight') as stage:
        if (MODEL / 'model.pt').exists():
            raise RuntimeError('Candidate checkpoint already exists; refusing overwrite')
        trainer = Trainer(DATA / 'crowgpt/tokens-6s', MODEL, **RECIPE)
        assert trainer.effective_batch == 8
        assert not trainer.vocabulary.call_types
        assert len(trainer.train_batcher.usable) == len(trainer.train_set)
        # Force the longest sequences through forward, backward, and Adam state
        # allocation: random short batches cannot establish the memory ceiling.
        longest = max(trainer.train_batcher.usable,
                      key=lambda i: trainer.train_set.records[i]['length'])
        seq = trainer.train_batcher.sequence(longest)
        x = torch.tensor(seq[:-1].copy(), device='cuda', dtype=torch.long).repeat(4, 1)
        y = torch.tensor(seq[1:].copy(), device='cuda', dtype=torch.long).repeat(4, 1)
        opt = trainer.model.optimiser(trainer.learning_rate)
        for i in range(3):
            opt.zero_grad(set_to_none=True)
            for _ in range(2):
                loss = trainer._loss(x, y) / 2
                assert torch.isfinite(loss)
                loss.backward()
            opt.step()
            stage.update(i + 1, 3)
        peak = torch.cuda.max_memory_allocated() / 2**30
        metadata = {'recipe': RECIPE, 'config': trainer.config.as_dict(),
                    'parameters': trainer.model.n_params(), 'peak_preflight_gib': peak,
                    'token_manifest_sha256': hashlib.sha256(
                        (DATA / 'crowgpt/tokens-6s/manifest.json').read_bytes()).hexdigest(),
                    'parent_release': 'crowgpt2', 'decoder_state': 'finetuned',
                    'sampling': {'temperature': 1.1, 'top_k': 200, 'max_frames': 460},
                    'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()}
        MODEL.mkdir(parents=True, exist_ok=True)
        (MODEL / 'recipe.json').write_text(json.dumps(metadata, indent=2) + '\n')
        run.note(f"{metadata['parameters']:,} parameters; longest-batch peak {peak:.2f} GiB")
        del trainer, opt, x, y, loss
        gc.collect()
        torch.cuda.empty_cache()
    if args.preflight_only:
        return
    with run.stage('train') as stage:
        # Fresh initialization: preflight updates must not enter the experiment.
        trainer = Trainer(DATA / 'crowgpt/tokens-6s', MODEL, **RECIPE)
        stage.update(0, RECIPE['steps'])
        history = trainer.run(on_step=lambda step, total: stage.update(step, total),
                              on_eval=lambda step, val: run.note(f'step {step}: val {val:.4f}'))
        stage.say(f"best validation loss {history['best_val']:.4f}")
        del trainer
        gc.collect()
        torch.cuda.empty_cache()
    with run.stage('validate') as stage:
        process = subprocess.Popen([sys.executable, str(OUT / 'validate.py')], cwd=REPO)
        while True:
            try:
                code = process.wait(timeout=30)
                break
            except subprocess.TimeoutExpired:
                stage.say('Matched generation gate running; see 0085 capacity gate card')
        if code:
            raise RuntimeError(f'Validation exited {code}')
        stage.say('Results and diagnostic audio saved; candidate awaits listening decision')


if __name__ == '__main__':
    main()
