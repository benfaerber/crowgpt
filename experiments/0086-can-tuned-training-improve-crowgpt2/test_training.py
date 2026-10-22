"""Test actual training continuation and fixed-score weighting on tiny data."""
import json
from pathlib import Path
import sys

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'crowgpt/src'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from crowgpt.tokens import Vocabulary
from training import ControlledTrainer, fixed_panel, score


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    monkeypatch.setenv('CROWGPT_ALLOW_CPU', '1')
    torch.set_num_threads(1)
    root = tmp_path / 'tokens'
    root.mkdir()
    vocab = Vocabulary(1, ['american-crow'])
    (root / 'manifest.json').write_text(json.dumps({'n_codebooks': 1, 'species': ['american-crow']}))
    for split in ['train', 'val']:
        rows, stream = [], []
        for i in range(9):
            seq = [vocab.species_base, vocab.duration_base] + list(range(i+2)) + [vocab.eos]
            rows.append({'start': len(stream), 'length': len(seq), 'species': 'american-crow',
                         'canonical': i != 8, 'group_key': f'{split}-{i//2}'})
            stream.extend(seq)
        (root / f'{split}.jsonl').write_text('\n'.join(map(json.dumps, rows)))
        np.array(stream, dtype=np.uint16).tofile(root / f'{split}.u16')
    return root


def make(corpus, output, lr=0.0003):
    return ControlledTrainer(corpus, output, steps=6, batch_size=2,
                             learning_rate=lr, warmup=1, n_embd=8, n_layer=1,
                             n_head=2, dropout=0.2, eval_every=2, panel_size=4,
                             checkpoint_every=2)


def test_resume_matches_uninterrupted_updates_and_optimizer(corpus, tmp_path):
    full = make(corpus, tmp_path / 'full')
    expected = full.run()
    partial = make(corpus, tmp_path / 'partial')
    partial.run(stop_after=3)
    resumed = make(corpus, tmp_path / 'partial')
    actual = resumed.run()
    assert actual == expected
    for key, value in full.model.state_dict().items():
        assert torch.equal(value, resumed.model.state_dict()[key]), key
    a = torch.load(tmp_path / 'full/resume.pt', weights_only=False)
    b = torch.load(tmp_path / 'partial/resume.pt', weights_only=False)
    for k, state in a['optimizer']['state'].items():
        for name, value in state.items():
            assert torch.equal(value, b['optimizer']['state'][k][name])
    assert (tmp_path / 'partial/step-00006.pt').exists()


def test_fixed_eval_repeats_without_consuming_training_rng(corpus, tmp_path):
    t = make(corpus, tmp_path / 'model')
    before = json.dumps(t.train_batcher.rng.bit_generator.state)
    first = t.evaluate()
    t.val_batcher.batch()  # evaluation must not depend on this moving stream
    assert t.evaluate() == first
    assert json.dumps(t.train_batcher.rng.bit_generator.state) == before
    assert t.model.training
    panel = t.panels['val']
    assert len({t.val_set.records[i]['group_key'] for i in panel}) == len(panel)
    assert all(t.val_set.records[i]['canonical'] for i in panel)


def test_eval_weights_tokens_not_padded_batches(corpus, tmp_path):
    t = make(corpus, tmp_path / 'model')
    indices = list(range(8))
    one = score(t.model, t.legal, t.val_set, indices, 'cpu', 1)
    many = score(t.model, t.legal, t.val_set, indices, 'cpu', 3)
    assert one == pytest.approx(many, abs=1e-6)


def test_resume_refuses_changed_recipe(corpus, tmp_path):
    t = make(corpus, tmp_path / 'model')
    t.run(stop_after=2)
    changed = make(corpus, tmp_path / 'model', lr=0.0001)
    with pytest.raises(ValueError, match='Resume recipe'):
        changed.run()
