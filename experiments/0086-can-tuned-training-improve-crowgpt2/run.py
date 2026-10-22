"""Three sequential 30k-step learning-rate arms, then selection and a pool."""
import argparse
import gc
import hashlib
import os
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / 'crowgpt/src'))
from crowgpt.progress import Run
from crowgpt.train import require_device
from training import ControlledTrainer, atomic_json, pack
import torch

DATA = Path(os.environ.get('DATA_DIR', REPO / 'data'))
TOKENS = DATA / 'crowgpt/tokens-6s'
OUTPUT = REPO / 'crowgpt/results/tuning-0086'
ARMS = {'lr-1e-4': 1e-4, 'lr-2e-4': 2e-4, 'lr-3e-4': 3e-4}
COMMON = dict(steps=30000, batch_size=8, accumulate=1, n_embd=512,
              n_layer=12, n_head=4, dropout=0.0, seed=0, warmup=200,
              eval_every=1000, panel_size=256, checkpoint_every=5000)


def trainer(name, lr):
    return ControlledTrainer(TOKENS, OUTPUT / name, learning_rate=lr, **COMMON)


def cleanup():
    gc.collect()
    torch.cuda.empty_cache()


def preflight(stage):
    if require_device() != 'cuda':
        raise RuntimeError('0086 requires GPU; clear CROWGPT_ALLOW_CPU')
    t = trainer('preflight', 1e-4)
    assert t.effective_batch == t.micro_batch == 8
    assert len(t.train_batcher.usable) == len(t.train_set)
    assert not t.vocabulary.call_types
    longest = max(t.train_batcher.usable, key=lambda i: t.train_set.records[i]['length'])
    x, y = pack(t.train_set, [longest]*8, 'cuda')
    optimizer = t.model.optimiser(t.learning_rate)
    for i in range(3):
        optimizer.zero_grad(set_to_none=True)
        loss = t._loss(x, y)
        if not torch.isfinite(loss):
            raise RuntimeError('Nonfinite preflight loss')
        loss.backward()
        optimizer.step()
        stage.update(i+1, 3)
    peak = torch.cuda.max_memory_allocated() / 2**30
    # Repeat fixed validation to establish reproducibility on the actual GPU.
    first, second = t.evaluate(), t.evaluate()
    if first != second:
        raise RuntimeError(f'Fixed evaluation is not repeatable: {first}, {second}')
    report = {'parameters': t.model.n_params(), 'peak_gib': peak,
              'fixed_panel_repeat': first, 'panels': t.panels,
              'recipe': COMMON, 'rates': ARMS,
              'git_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    atomic_json(OUTPUT / 'preflight.json', report)
    print(f'Preflight: {peak:.2f} GiB, true batch 8; fixed evaluation repeats exactly', flush=True)
    del t, x, y, loss, optimizer
    cleanup()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    stages = ['preflight'] if args.preflight_only else ['preflight', *ARMS, 'select and listen']
    run = Run('0086 tuned CrowGPT3' + (' preflight' if args.preflight_only else ''), stages)
    with run.stage('preflight') as stage:
        preflight(stage)
    if args.preflight_only:
        return
    for name, lr in ARMS.items():
        with run.stage(name) as stage:
            t = trainer(name, lr)
            result = t.run(on_step=lambda done, total: stage.update(done, total),
                           on_eval=lambda step, val: run.note(f'{name} step {step}: fixed val {val:.4f}'))
            stage.say(f"30k schedule complete; best fixed-panel val {result['best_val']:.4f}")
            del t
            cleanup()
    with run.stage('select and listen') as stage:
        child = subprocess.Popen([sys.executable, str(HERE / 'finish.py')], cwd=REPO)
        while True:
            try:
                code = child.wait(timeout=30)
                break
            except subprocess.TimeoutExpired:
                stage.say('Full validation, generated comparison and listening-pool build; see 0086 results card')
        if code:
            raise RuntimeError(f'Final evaluation/pool build exited {code}')
        stage.say('Comparison complete; blinded pool registered in Listening')


if __name__ == '__main__':
    main()
