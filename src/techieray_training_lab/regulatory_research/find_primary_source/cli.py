"""Command line for the regulatory research set.

  python -m techieray_training_lab.regulatory_research.find_primary_source score --items TASKS --rollouts ROLLOUTS [--out REWARDS]
  python -m techieray_training_lab.regulatory_research.find_primary_source score ... --grader claude   # needs the [grader] extra
  python -m techieray_training_lab.regulatory_research.find_primary_source check --items TASKS         # rerun the shortcut checks

`--items` defaults to the set's own tasks when the package runs from this repository.

Rollouts are JSON Lines, one answer per line: {"example_id", "url", "no_official_source", "confidence"}, plus an
optional "rollout_id" (several rollouts per example are fine). Each output line is the rollout's ids with its
reward, outcome and penalised flag. The summary says which grader mode produced the rewards.
"""
import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from techieray_training_lab.common import jsonl
from techieray_training_lab.regulatory_research.find_primary_source.reward import find_primary_source_reward


def grader_mode(grader):
    return 'Claude grader for unlisted URLs' if grader == 'claude' else 'key only; unlisted URLs score 0'


def score_rollouts(items, rollouts, grader=None, workers=8):
    by_id = {r['example_id']: r for r in items}

    def one(rollout):
        item = by_id.get(rollout.get('example_id'))
        if item is None:
            return {'example_id': rollout.get('example_id'), 'rollout_id': rollout.get('rollout_id'),
                    'reward': None, 'outcome': 'unknown_example', 'penalised': False, 'correct': None}
        result = find_primary_source_reward(item, rollout, grader)
        return {'example_id': item['example_id'], 'rollout_id': rollout.get('rollout_id'), **result.to_dict()}

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return list(pool.map(one, rollouts))


def summarise(rows, mode):
    scored = [r['reward'] for r in rows if r['reward'] is not None]
    return {'rollouts': len(rows), 'scored': len(scored),
            'mean_reward': round(sum(scored) / len(scored), 4) if scored else None,
            'solved': sum(bool(r['correct']) for r in rows), 'penalised': sum(r['penalised'] for r in rows),
            'outcomes': dict(Counter(r['outcome'] for r in rows).most_common()), 'grader_mode': mode}


TASKS = Path(__file__).resolve().parents[4] / 'sets' / 'regulatory_research' / 'find_primary_source' / 'data' / 'tasks.jsonl'


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = p.add_subparsers(dest='cmd', required=True)
    ps = sub.add_parser('score', help='score a file of rollouts')
    ps.add_argument('--items', type=Path, default=TASKS)
    ps.add_argument('--rollouts', required=True, type=Path)
    ps.add_argument('--out', type=Path)
    ps.add_argument('--grader', choices=['none', 'claude'], default='none')
    ps.add_argument('--workers', type=int, default=8)
    pc = sub.add_parser('check', help='run the shortcut strategies against the reward')
    pc.add_argument('--items', type=Path, nargs='+', default=[TASKS])
    a = p.parse_args(argv)
    if a.cmd == 'check':
        from techieray_training_lab.regulatory_research.find_primary_source.checks import main as check
        return check([str(f) for f in a.items])
    grader = None
    if a.grader == 'claude':
        from techieray_training_lab.regulatory_research.find_primary_source.grader import ClaudeGrader
        grader = ClaudeGrader()
    rows = score_rollouts(jsonl.read(a.items), jsonl.read(a.rollouts), grader, a.workers)
    if a.out:
        jsonl.write(a.out, rows)
    print(json.dumps(summarise(rows, grader_mode(a.grader)), indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
