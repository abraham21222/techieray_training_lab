"""The regulatory research tasks are well formed, and the reward pays for their answers and nothing else."""
import json
from pathlib import Path

from techieray_training_lab.common import jsonl
from techieray_training_lab.common.matching import url_matches
from techieray_training_lab.regulatory_research.find_primary_source import find_primary_source_reward
from techieray_training_lab.regulatory_research.find_primary_source.cli import score_rollouts, summarise
from techieray_training_lab.regulatory_research.find_primary_source.checks import run

ROOT = Path(__file__).resolve().parent.parent
SET = ROOT / 'sets' / 'regulatory_research' / 'find_primary_source'
TASKS = jsonl.read(SET / 'data' / 'tasks.jsonl')
FIELDS = {'example_id', 'task', 'as_of_date', 'input', 'input_named', 'input_full', 'reference', 'strata'}


def test_tasks_are_well_formed():
    assert len(TASKS) == 50 and len({t['example_id'] for t in TASKS}) == 50
    assert sum(t['reference']['no_official_source'] for t in TASKS) == 5
    for t in TASKS:
        assert set(t) == FIELDS, t['example_id']
        assert t['task'] == 'find_primary_source'
        assert t['input']['headline'] and t['input']['jurisdictions']
        ref = t['reference']
        if ref['no_official_source']:
            assert ref['accepted_url_fragments'] == [] and ref['canonical_url'] is None
            assert t['strata']['question_form'] == 'counterfactual_alert' and not t['strata']['strict']
            continue
        assert ref['accepted_url_fragments']
        assert any(url_matches(ref['canonical_url'], f) for f in ref['accepted_url_fragments'])
        assert t['strata']['strict'] == bool(ref.get('authoritative_url_fragments'))


def test_every_reference_answer_scores_one():
    for t in TASKS:
        if t['reference']['no_official_source']:
            answer = {'url': None, 'no_official_source': True, 'confidence': 'verified'}
        else:
            answer = {'url': t['reference']['canonical_url'], 'confidence': 'verified'}
        assert find_primary_source_reward(t, answer).reward == 1.0, t['example_id']


def test_every_accepted_page_scores_one_unless_the_task_is_strict():
    for t in TASKS:
        ref = t['reference']
        for f in ref['accepted_url_fragments']:
            result = find_primary_source_reward(t, {'url': 'https://' + f, 'confidence': 'verified'})
            strict_text = any(url_matches('https://' + f, a) for a in ref.get('authoritative_url_fragments') or [])
            assert result.correct == (strict_text or not ref.get('authoritative_url_fragments')), (t['example_id'], f)


def test_no_shortcut_earns_reward_on_the_released_tasks():
    report = run(TASKS)['strategies']
    assert all(r['ok'] for r in report.values()), {k: v for k, v in report.items() if not v['ok']}


def test_example_rollouts_score_as_documented():
    rows = score_rollouts(TASKS, jsonl.read(SET / 'examples' / 'rollouts.jsonl'))
    assert [r['outcome'] for r in rows] == ['key', 'unlisted', 'no_source_wrong', 'key', 'no_source_correct', 'source_claimed']
    assert summarise(rows, 'key only')['rollouts'] == len(rows)


def test_shipped_reward_checks_match_a_fresh_run():
    shipped = json.loads((SET / 'results' / 'reward_checks.json').read_text())
    assert {k: v['mean_reward'] for k, v in shipped['strategies'].items()} == \
        {k: v['mean_reward'] for k, v in run(TASKS)['strategies'].items()}


def test_load_tasks_and_cli(capsys):
    from techieray_training_lab.regulatory_research.find_primary_source import load_tasks
    from techieray_training_lab.regulatory_research.find_primary_source.cli import main
    assert len(load_tasks()) == 50
    assert main(['score', '--rollouts', str(SET / 'examples' / 'rollouts.jsonl')]) == 0
    assert json.loads(capsys.readouterr().out)['rollouts'] == 6
    assert main(['check']) == 0
