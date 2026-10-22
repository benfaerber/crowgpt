"""Select on validation only, compare outputs, and register a fresh blinded pool."""
import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / 'crowgpt/src'))
sys.path.insert(0, str(REPO / 'experiments'))

import numpy as np
import soundfile as sf
import torch
from crowgpt.codec import SAMPLE_RATE, normalise
from crowgpt.demo import MIN_GRADEABLE_SECONDS
from crowgpt.model import Config, CrowGPT, LegalMask
from crowgpt.progress import Run
from crowgpt.sample import Sampler
from crowgpt.segment import Segmenter
from crowgpt.tokens import BoutStore, TokenDataset, Vocabulary
from crowgpt.train import require_device
from lib.dustprobe import DUST_THRESHOLD, bursts_of, pitch_strength
from training import atomic_json, score
from run import ARMS, DATA, OUTPUT, TOKENS, cleanup

INCUMBENT = REPO / 'crowgpt/results/model-longctx/model.pt'
PREVIOUS = REPO / 'crowgpt/results/model-crowgpt3-candidate-0085/model.pt'
POOL_NAME = 'capacity-0086'
CLIP_DIR = REPO / 'crowgpt/results/listening-pools' / POOL_NAME
DB = Path(os.environ.get('FIELD_DB', REPO / 'fieldserver/instance/field.db'))
SAMPLING = dict(temperature=1.1, top_k=200, max_frames=460)
QUESTION = ('Which clip sounds more like a real crow? Judge the voice and the '
            'sequence of calls. They are the same is a valid answer. '
            'Notes about each clip are useful, especially hoarseness, overlapping '
            'voices, metallic sounds, or unnatural rhythm.')


def pool_specs():
    # Read specifications only, never partial answers or their rankings.
    with sqlite3.connect(f'file:{DB}?mode=ro', uri=True) as conn:
        return [(n, json.loads(s) if s else {})
                for n, s in conn.execute('SELECT name, spec FROM listening_pools')]


def select_reals(store, n=56, min_seconds=2, extra_excluded=()):
    """Reserve new test groups, excluding the old pools' recorded real anchors."""
    excluded = set(extra_excluded)
    for name, spec in pool_specs():
        if name == POOL_NAME:
            continue
        if 'anchor_groups' in spec:
            excluded.update(spec['anchor_groups'])
        indices = spec.get('anchor_bouts', [])
        if name.startswith(('longctx-', 'dust-', 'voice-', 'capacity-')):
            source = store
        elif name == 'scrape-v3-0064':
            source = BoutStore(DATA / 'crowgpt/bouts')
        elif name == 'churn-spread-0053':
            source = BoutStore(DATA / 'crowgpt/bouts')
            indices = list(spec.get('bout_of', {}).values())
        elif indices:
            raise RuntimeError(f'Unknown pool corpus for {name}; resolve before reusing anchors')
        else:
            continue
        for i in indices:
            if isinstance(i, int) and 0 <= i < len(source.index):
                excluded.add(source.index[i]['group_key'])
    candidates = list(store.split(seed=0)['test'])
    np.random.default_rng(8600).shuffle(candidates)
    selected = []
    for i in candidates:
        r = store.index[i]
        if r['species'] != 'american-crow' or r['n_samples'] < min_seconds*SAMPLE_RATE:
            continue
        if r['group_key'] in excluded:
            continue
        selected.append(int(i))
        excluded.add(r['group_key'])
        if len(selected) == n:
            return selected
    raise RuntimeError(f'Only {len(selected)} fresh test groups; need {n}')


def select_checkpoint(stage):
    dataset = TokenDataset(TOKENS, 'val')
    indices = [i for i, r in enumerate(dataset.records)
               if r['species'] == 'american-crow' and r.get('canonical', True)]
    paths = [INCUMBENT, PREVIOUS]
    for arm in ARMS:
        paths.extend(sorted((OUTPUT / arm).glob('step-*.pt')))
        paths.append(OUTPUT / arm / 'model.pt')
    results, seen = [], set()
    total = len(paths)*len(indices)
    for n, path in enumerate(paths):
        state = torch.load(path, map_location='cpu', weights_only=False)
        identity = (str(path.parent), state['step'])
        if identity in seen:
            stage.update((n+1)*len(indices), total, extra=f'skip duplicate {path.parent.name} step {state["step"]}')
            continue
        seen.add(identity)
        for key in ('n_codebooks', 'species', 'call_types', 'n_unit_buckets'):
            if state['manifest'].get(key) != dataset.manifest.get(key):
                raise ValueError(f'{path}: incompatible token manifest {key}')
        config = Config(**state['config'])
        if max(dataset.records[i]['length']-1 for i in indices) > config.block_size:
            raise ValueError(f'{path}: validation does not fit its context')
        model = CrowGPT(config).to('cuda')
        model.load_state_dict(state['model'])
        vocab = Vocabulary(state['manifest']['n_codebooks'], state['manifest']['species'],
                           n_unit_buckets=state['manifest'].get('n_unit_buckets', 0))
        legal = LegalMask(vocab, config.block_size+1, 'cuda')
        loss = score(model, legal, dataset, indices, 'cuda', batch_size=8,
                     on_progress=lambda done, _: stage.update(n*len(indices)+done, total,
                                         extra=f'{path.parent.name} step {state["step"]}'))
        row = {'path': str(path), 'step': state['step'], 'full_ac_val': loss,
               'checkpoint_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        results.append(row)
        atomic_json(OUTPUT / 'selection-in-progress.json', results)
        print(row, flush=True)
        del model, state, legal
        cleanup()
    candidates = [r for r in results if Path(r['path']).parent.name in ARMS]
    winner = min(candidates, key=lambda r: r['full_ac_val'])
    result = {'validation_bouts': len(indices), 'split': 'val',
              'metric': 'American Crow canonical token-weighted cross entropy',
              'checkpoints': results, 'winner': winner}
    target = OUTPUT / 'selected'
    target.mkdir(exist_ok=True)
    shutil.copyfile(winner['path'], target / 'model.pt.tmp')
    os.replace(target / 'model.pt.tmp', target / 'model.pt')
    atomic_json(OUTPUT / 'selection.json', result)
    return result


def features(seg, audio):
    db, fps = seg.envelope(audio, SAMPLE_RATE)
    bursts = seg.bursts(db, fps, np.percentile(db, seg.floor_pctl))
    strengths = [pitch_strength(b, SAMPLE_RATE) for b in bursts_of(seg, audio, SAMPLE_RATE)]
    half = len(strengths)//2
    return {'seconds': audio.size/SAMPLE_RATE, 'units': len(bursts),
            'gaps': [(b[0]-a[1])/fps for a, b in zip(bursts, bursts[1:])],
            'pitch_strength': float(np.mean(strengths)) if strengths else None,
            'crescendo': float(np.mean(strengths[half:])-np.mean(strengths[:half]))
                         if half else None}


def describe(rows):
    gaps = [g for r in rows for g in r['gaps']]
    strengths = [r['pitch_strength'] for r in rows if r['pitch_strength'] is not None]
    deltas = [r['crescendo'] for r in rows if r['crescendo'] is not None]
    return {'n': len(rows), 'mean_units': float(np.mean([r['units'] for r in rows])),
            'gaps_per_clip': len(gaps)/len(rows),
            'single_share': float(np.mean([r['units'] <= 1 for r in rows])),
            'median_gap_s': float(np.median(gaps)) if gaps else None,
            'dust_rate': float(np.mean(np.array(strengths) <= DUST_THRESHOLD)) if strengths else None,
            'dust_scored_n': len(strengths),
            'mean_crescendo': float(np.mean(deltas)) if deltas else None,
            'crescendo_scored_n': len(deltas)}


def draw(sampler, stage, seed_base, count, clip_dir=None, prefix=''):
    seg, rows, attempts = Segmenter(), [], []
    for seed in range(seed_base, seed_base+count*10):
        audio = np.asarray(sampler.audio('american-crow', seed=seed, **SAMPLING), dtype=np.float32)
        if not np.isfinite(audio).all():
            raise ValueError(f'Nonfinite audio seed {seed}')
        gradeable = audio.size/SAMPLE_RATE >= MIN_GRADEABLE_SECONDS
        attempts.append({'seed': seed, 'seconds': audio.size/SAMPLE_RATE, 'gradeable': gradeable})
        if gradeable:
            row = features(seg, normalise(audio)) | {'seed': seed}
            if clip_dir:
                filename = f'{prefix}-{len(rows):02d}.wav'
                sf.write(clip_dir / filename, normalise(audio), SAMPLE_RATE, subtype='PCM_16')
                row['file'] = filename
            rows.append(row)
        stage.update(len(rows), count, extra=f'seed {seed}; {len(attempts)} attempts')
        if len(rows) == count:
            return {'rows': rows, 'attempts': attempts, 'summary': describe(rows)}
    raise RuntimeError(f'Only {len(rows)} gradeable clips from {count*10} attempts')


def make_trials(arms, anchors, catch_reals):
    rng = np.random.default_rng(86)
    compares = list(range(40)); rng.shuffle(compares)
    catches = [('candidate', i) for i in range(40, 44)] + [('crowgpt2', i) for i in range(40, 44)]
    rng.shuffle(catches)
    trials, ci, ki = [], 0, 0
    for block, (nc, nk) in enumerate([(14, 2), (14, 2), (12, 4)]):
        # Every dose balances candidate sides and known-real catch sides.
        slots = ['compare']*nc + ['catch']*nk
        rng.shuffle(slots)
        cmp_sides = [True, False]*(nc//2); rng.shuffle(cmp_sides)
        catch_sides = [True, False]*(nk//2); rng.shuffle(catch_sides)
        for kind in slots:
            if kind == 'compare':
                i = compares[ci]; ci += 1
                a, b = ('candidate', 'crowgpt2') if cmp_sides.pop() else ('crowgpt2', 'candidate')
                first, second = arms[a]['rows'][i], arms[b]['rows'][i]
                facts = {a: {'seed': first['seed'], 'seconds': first['seconds']},
                         b: {'seed': second['seed'], 'seconds': second['seconds']}}
            else:
                arm, i = catches[ki]
                gen = arms[arm]['rows'][i]
                real = {'file': catch_reals[ki]}
                ki += 1
                if catch_sides.pop():
                    a, b, first, second = 'real', arm, real, gen
                else:
                    a, b, first, second = arm, 'real', gen, real
                facts = {'generated_seed': gen['seed']}
            trials.append({'block': block, 'kind': kind, 'anchor_clip': anchors[len(trials)],
                           'first_clip': first['file'], 'second_clip': second['file'],
                           'first_arm': a, 'second_arm': b, 'facts': facts})
    return trials


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-reals', action='store_true')
    args = parser.parse_args()
    store = BoutStore(DATA / 'crowgpt/bouts-6s')
    if args.check_reals:
        selected = select_reals(store)
        reference = select_reals(store, 200, 1, [store.index[i]['group_key'] for i in selected])
        print(f'{len(selected)} listening and {len(reference)} reference groups available; disjoint')
        return
    if POOL_NAME in dict(pool_specs()):
        print('Pool capacity-0086 already exists; leaving its clips and answers untouched', flush=True)
        return
    if require_device() != 'cuda':
        raise RuntimeError('GPU required for final evaluation')
    run = Run('0086 results and listening', ['select checkpoints', 'real reference',
              'gate crowgpt2', 'gate candidate', 'pool crowgpt2', 'pool candidate', 'register'])
    with run.stage('select checkpoints') as stage:
        selection = select_checkpoint(stage)
        run.note(f"Selected {Path(selection['winner']['path']).parent.name}, step {selection['winner']['step']}")
    with run.stage('real reference') as stage:
        chosen = select_reals(store)
        reference = select_reals(store, 200, 1, [store.index[i]['group_key'] for i in chosen])
        # Listening anchors >=2 s; instrument reference >=1 s, matching earlier gates.
        seg = Segmenter()
        real_rows = []
        for i in reference:
            real_rows.append(features(seg, normalise(store.audio(store.index[i]))))
            stage.update(len(real_rows), 200)
        gate = {'real': {'bout_indices': reference, 'rows': real_rows, 'summary': describe(real_rows)}}
    models = {'crowgpt2': INCUMBENT, 'candidate': OUTPUT / 'selected/model.pt'}
    for arm, path in models.items():
        with run.stage(f'gate {arm}') as stage:
            sampler = Sampler(path, decoder_state='finetuned', device='cuda')
            gate[arm] = draw(sampler, stage, 86000, 100)
            atomic_json(OUTPUT / 'gate.json', gate)
            del sampler
            cleanup()
    arms = {}
    CLIP_DIR.mkdir(parents=True, exist_ok=True)
    for arm, path in models.items():
        with run.stage(f'pool {arm}') as stage:
            sampler = Sampler(path, decoder_state='finetuned', device='cuda')
            # Separate unseen seed block; no quality-based choice of listening clips.
            arms[arm] = draw(sampler, stage, 88000, 44, CLIP_DIR, arm)
            del sampler
            cleanup()
    with run.stage('register') as stage:
        anchors, catch_reals = [], []
        for n, i in enumerate(chosen[:56]):
            filename = f'real-{n:02d}.wav'
            sf.write(CLIP_DIR / filename, normalise(store.audio(store.index[i])), SAMPLE_RATE, subtype='PCM_16')
            (anchors if n < 48 else catch_reals).append(filename)
        payload = {'name': POOL_NAME, 'question': QUESTION, 'clip_dir': str(CLIP_DIR),
                   'dose_size': 16, 'reveal_at': 48, 'trials': make_trials(arms, anchors, catch_reals),
                   'spec': {'experiment': '0086', 'sampling': SAMPLING, 'decoder': 'finetuned',
                            'selection': selection, 'draws': arms,
                            'anchor_bouts': chosen[:56],
                            'anchor_groups': [store.index[i]['group_key'] for i in chosen[:56]]}}
        atomic_json(OUTPUT / 'pool.json', payload)
        existing = dict(pool_specs()).get(POOL_NAME)
        if existing is not None:
            if existing != payload['spec']:
                raise RuntimeError('Existing pool specification differs; refusing replace')
            run.note('Identical pool already registered')
        else:
            completed = subprocess.run([str(REPO / 'fieldserver/.venv/bin/python'),
                  str(REPO / 'fieldserver/tools/register_pool.py'), str(OUTPUT / 'pool.json'),
                  '--dose-size', '16', '--cooldown', '30'], text=True, capture_output=True)
            if completed.returncode:
                raise RuntimeError(completed.stdout + completed.stderr)
            run.note(completed.stdout.strip())
        summaries = {name: arm['summary'] for name, arm in gate.items()}
        result = {'selection': selection, 'gate': summaries, 'pool': POOL_NAME,
                  'trials': 48, 'release': 'CrowGPT2 unchanged; listening pending'}
        atomic_json(HERE / 'results.json', result)
        run.note(json.dumps(summaries))
        stage.update(1, 1, extra='48 trials registered; three doses of 16, 30-minute cooldown')


if __name__ == '__main__':
    main()
