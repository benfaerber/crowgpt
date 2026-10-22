"""0086's fixed panels and atomic, exactly resumable training state.

Uses the existing model/loss/optimizer. No shared Trainer defaults are changed.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import time

import numpy as np
import torch

from crowgpt.train import Trainer


def atomic_json(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    os.replace(tmp, path)


def atomic_torch(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    torch.save(value, tmp)
    os.replace(tmp, path)


def fixed_panel(dataset, size=256, seed=86):
    """One canonical American Crow bout per group, sampled without replacement."""
    groups = {}
    for i, row in enumerate(dataset.records):
        if row['species'] == 'american-crow' and row.get('canonical', True):
            groups.setdefault(row['group_key'], []).append(i)
    rng = np.random.default_rng(seed)
    keys = sorted(groups)
    rng.shuffle(keys)
    return [int(rng.choice(groups[k])) for k in keys[:size]]


def pack(dataset, indices, device):
    sequences = [dataset.sequence(int(i)) for i in indices]
    n = max(map(len, sequences)) - 1
    x = np.zeros((len(sequences), n), dtype=np.int64)
    y = np.full((len(sequences), n), -1, dtype=np.int64)
    for j, s in enumerate(sequences):
        x[j, :len(s)-1] = s[:-1]
        y[j, :len(s)-1] = s[1:]
    return torch.from_numpy(x).to(device), torch.from_numpy(y).to(device)


@torch.no_grad()
def score(model, legal, dataset, indices, device, batch_size=8, on_progress=None):
    """Token-weighted CE on exactly these examples; padding has zero weight."""
    was_training = model.training
    model.eval()
    total_loss, total_tokens = 0.0, 0
    try:
        for start in range(0, len(indices), batch_size):
            x, y = pack(dataset, indices[start:start+batch_size], device)
            with torch.autocast(device, dtype=torch.bfloat16, enabled=device == 'cuda'):
                _, loss = model(x, y, legal.for_batch(x.size(1), shift=1))
            count = int((y != -1).sum())
            if not torch.isfinite(loss):
                raise RuntimeError('Nonfinite evaluation loss')
            total_loss += loss.item() * count
            total_tokens += count
            if on_progress:
                on_progress(min(start + batch_size, len(indices)), len(indices))
    finally:
        model.train(was_training)
    if not total_tokens:
        raise ValueError('Empty evaluation panel')
    return total_loss / total_tokens


class ControlledTrainer(Trainer):
    def __init__(self, *args, panel_size=256, checkpoint_every=5000, **kwargs):
        super().__init__(*args, **kwargs)
        if self.accumulate != 1:
            raise ValueError('0086 uses a true batch, without accumulation')
        self.panels = {'train': fixed_panel(self.train_set, panel_size, 87),
                       'val': fixed_panel(self.val_set, panel_size, 86)}
        if not all(self.panels.values()):
            raise ValueError('No American Crow evaluation data')
        self.checkpoint_every = checkpoint_every
        self.signature = {
            'config': self.config.as_dict(), 'steps': self.steps,
            'learning_rate': self.learning_rate, 'warmup': self.warmup,
            'lr_floor': self.lr_floor, 'eval_every': self.eval_every,
            'batch_size': self.micro_batch, 'accumulate': self.accumulate,
            'panels': self.panels, 'checkpoint_every': self.checkpoint_every,
            'species_weights': self.species_mix,
            'tokens': {name: hashlib.sha256((self.token_dir / name).read_bytes()).hexdigest()
                       for name in ['manifest.json', 'train.jsonl', 'val.jsonl']},
        }
        self.completed_steps = 0

    def evaluate(self):
        return tuple(score(self.model, self.legal, dataset, self.panels[split],
                           self.device, self.micro_batch)
                     for split, dataset in [('train', self.train_set), ('val', self.val_set)])

    def blob(self, step, val):
        return {'model': self.model.state_dict(), 'config': self.config.as_dict(),
                'manifest': dict(self.train_set.manifest), 'step': step, 'val_loss': val}

    def save_resume(self, optimizer, step, best, history):
        state = dict(self.blob(step, history[-1]['val'] if history else None),
                     optimizer=optimizer.state_dict(), best=best, history=history,
                     signature=self.signature, torch_rng=torch.get_rng_state(),
                     cuda_rng=torch.cuda.get_rng_state_all() if self.device == 'cuda' else [],
                     python_rng=random.getstate(), numpy_rng=np.random.get_state(),
                     batch_rng=copy.deepcopy(self.train_batcher.rng.bit_generator.state))
        atomic_torch(self.out_dir / 'resume.pt', state)

    def run(self, on_eval=None, on_step=None, stop_after=None):
        """Full schedule; stop_after exists for interruption/resumption tests."""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        optimizer = self.model.optimiser(self.learning_rate)
        resume_path = self.out_dir / 'resume.pt'
        history, best, start = [], float('inf'), 0
        if resume_path.exists():
            state = torch.load(resume_path, map_location='cpu', weights_only=False)
            if state['signature'] != self.signature:
                raise ValueError('Resume recipe or token index differs; use a new output directory')
            self.model.load_state_dict(state['model'])
            optimizer.load_state_dict(state['optimizer'])
            history, best, start = state['history'], state['best'], state['step']
            torch.set_rng_state(state['torch_rng'])
            if self.device == 'cuda':
                torch.cuda.set_rng_state_all(state['cuda_rng'])
            random.setstate(state['python_rng'])
            np.random.set_state(state['numpy_rng'])
            self.train_batcher.rng.bit_generator.state = state['batch_rng']
            del state
        elif (self.out_dir / 'model.pt').exists():
            raise ValueError('Weights exist without resumable state; refusing overwrite')
        atomic_json(self.out_dir / 'recipe.json', self.signature)
        self.completed_steps = start
        print(f'{self.model.n_params():,} params; true batch {self.micro_batch}; '
              f'LR {self.learning_rate}; {start}/{self.steps}; fixed panels; no early stop', flush=True)
        if on_step:
            on_step(start, self.steps)
        started = time.monotonic()
        end = min(self.steps, stop_after or self.steps)
        for step in range(start, end):
            for group in optimizer.param_groups:
                group['lr'] = self._learning_rate(step)
            optimizer.zero_grad(set_to_none=True)
            x, y = self.train_batcher.batch()
            loss = self._loss(x, y)
            if not torch.isfinite(loss):
                raise RuntimeError(f'Nonfinite loss at step {step+1}')
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0, error_if_nonfinite=True)
            optimizer.step()
            self.completed_steps = step + 1
            if on_step and (step + 1) % 25 == 0:
                on_step(step + 1, self.steps)
            if (step + 1) % self.eval_every == 0 or step + 1 == self.steps:
                train, val = self.evaluate()
                history.append({'step': step+1, 'train': train, 'val': val,
                                'gap': val-train, 'lr': optimizer.param_groups[0]['lr']})
                if val < best:
                    best = val
                    atomic_torch(self.out_dir / 'model.pt', self.blob(step+1, val))
                atomic_torch(self.out_dir / 'last.pt', self.blob(step+1, val))
                if (step + 1) % self.checkpoint_every == 0 or step + 1 == self.steps:
                    atomic_torch(self.out_dir / f'step-{step+1:05d}.pt', self.blob(step+1, val))
                atomic_json(self.out_dir / 'history.json', {'best_val': best, 'history': history})
                self.save_resume(optimizer, step+1, best, history)
                print(f'step {step+1}: train {train:.4f} val {val:.4f} '
                      f'{time.monotonic()-started:.0f}s', flush=True)
                if on_eval:
                    on_eval(step+1, val)
        # A deliberate interruption can fall between evaluations.
        self.save_resume(optimizer, self.completed_steps, best, history)
        return {'best_val': best, 'history': history, 'step': self.completed_steps}
