"""The listening instrument must be balanced, blind, and free of repeats."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from finish import make_trials


def test_pool_has_complete_balanced_doses_and_unique_clips():
    arms = {name: {'rows': [{'file': f'{name}-{i}.wav', 'seed': 88000+i, 'seconds': 2.0}
                           for i in range(44)]} for name in ['candidate', 'crowgpt2']}
    trials = make_trials(arms, [f'anchor-{i}.wav' for i in range(48)],
                         [f'real-{i}.wav' for i in range(8)])
    assert len(trials) == 48
    assert sum(t['kind'] == 'compare' for t in trials) == 40
    clips = [t[key] for t in trials for key in ['first_clip', 'second_clip', 'anchor_clip']]
    assert len(clips) == len(set(clips))
    for block in range(3):
        dose = [t for t in trials if t['block'] == block]
        assert len(dose) == 16
        compares = [t for t in dose if t['kind'] == 'compare']
        catches = [t for t in dose if t['kind'] == 'catch']
        assert sum(t['first_arm'] == 'candidate' for t in compares) == len(compares)//2
        assert sum(t['first_arm'] == 'real' for t in catches) == len(catches)//2
