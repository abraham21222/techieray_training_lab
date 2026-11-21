"""The reward: each outcome, the calibration penalty, the grader, and the shortcut strategies."""
import pytest

from techieray_training_lab.regulatory_research.find_primary_source import CONFIDENT_WRONG_PENALTY, OUTCOMES, find_primary_source_reward
from techieray_training_lab.regulatory_research.find_primary_source.cli import score_rollouts, summarise
from techieray_training_lab.regulatory_research.find_primary_source.reward import key_is_homepage
from techieray_training_lab.regulatory_research.find_primary_source.grader import ClaudeGrader
from techieray_training_lab.regulatory_research.find_primary_source import checks as gaming_check



def _item(fragments=('ico.org.uk/guidance/adm',), no_source=False, example_id='find_primary_source-x'):
    return {'example_id': example_id, 'task': 'find_primary_source',
            'input': {'headline': 'ICO publishes guidance on automated decisions', 'jurisdictions': ['GB']},
            'reference': {'accepted_url_fragments': list(fragments), 'no_official_source': no_source,
                          'canonical_url': 'https://' + fragments[0] if fragments else None}}


def _reward(answer, item=None, grader=None):
    return find_primary_source_reward(item or _item(), answer, grader)


@pytest.mark.parametrize('answer, reward, outcome', [
    ({'url': 'https://www.ico.org.uk/guidance/adm/', 'confidence': 'verified'}, 1.0, 'key'),
    ({'url': 'ico.org.uk/guidance/adm', 'confidence': 'likely'}, 0.9, 'key'),
    ({'url': 'ico.org.uk/guidance/adm', 'confidence': 'unverified'}, 0.8, 'key'),
    ({'url': 'ico.org.uk/guidance/adm'}, 0.8, 'key'),
    ({'url': 'https://ico.org.uk/news/other', 'confidence': 'verified'}, 0.0, 'unlisted'),  # may be right: no penalty
    ({'url': 'https://ico.org.uk/', 'confidence': 'verified'}, -CONFIDENT_WRONG_PENALTY, 'not_a_page'),
    ({'url': 'https://ico.org.uk/en/?lang=en', 'confidence': 'likely'}, 0.0, 'not_a_page'),
    ({'url': 'not a url', 'confidence': 'likely'}, 0.0, 'several_urls'),
    ({'url': 'https://a.gov/x https://ico.org.uk/guidance/adm', 'confidence': 'likely'}, 0.0, 'several_urls'),
    ({'url': ['https://ico.org.uk/guidance/adm'], 'confidence': 'verified'}, -CONFIDENT_WRONG_PENALTY, 'several_urls'),
    ({'url': 'https://www.techieray.com/x', 'confidence': 'verified'}, -CONFIDENT_WRONG_PENALTY, 'blocked'),
    ({'url': 'https://ico.org.uk/guidance/adm', 'no_official_source': True}, 0.0, 'contradictory'),
    ({'url': None, 'no_official_source': True, 'confidence': 'verified'}, -CONFIDENT_WRONG_PENALTY, 'no_source_wrong'),
    ({'url': None, 'no_official_source': True, 'confidence': 'likely'}, 0.0, 'no_source_wrong'),
    ({}, 0.0, 'unanswered'),
    (None, 0.0, 'unanswered'),
])
def test_reward_outcomes(answer, reward, outcome):
    result = _reward(answer)
    assert (result.reward, result.outcome) == (reward, outcome)
    assert result.outcome in OUTCOMES
    assert result.penalised == (reward < 0)


def test_items_with_no_official_source():
    item = _item(fragments=(), no_source=True)
    assert _reward({'url': None, 'no_official_source': True, 'confidence': 'verified'}, item).reward == 1.0
    claimed = _reward({'url': 'https://ico.org.uk/news/x', 'confidence': 'verified'}, item)
    assert (claimed.reward, claimed.outcome) == (-CONFIDENT_WRONG_PENALTY, 'source_claimed')


def test_grader_decides_unlisted_pages_only():
    calls = []

    def grader(item, answer):
        calls.append(answer['url'])
        return 'accept' if 'gov.uk' in answer['url'] else 'reject'

    assert _reward({'url': 'https://www.gov.uk/government/news/adm', 'confidence': 'likely'}, grader=grader).outcome \
        == 'grader_accept'
    rejected = _reward({'url': 'https://ico.org.uk/news/other', 'confidence': 'verified'}, grader=grader)
    assert (rejected.reward, rejected.outcome) == (-CONFIDENT_WRONG_PENALTY, 'grader_reject')
    _reward({'url': 'https://ico.org.uk/guidance/adm'}, grader=grader)  # key match: grader not asked
    _reward({'url': 'https://ico.org.uk/'}, grader=grader)  # homepage: grader not asked
    assert len(calls) == 2


def test_grader_failure_means_no_reward_not_zero():
    result = _reward({'url': 'https://ico.org.uk/news/other', 'confidence': 'verified'}, grader=lambda i, a: None)
    assert (result.reward, result.outcome, result.penalised) == (None, 'grader_error', False)


def test_claude_grader_caches_and_survives_errors():
    replies = []

    def grade(system, prompt):
        replies.append(prompt)
        return '```json\n{"verdict": "accept", "reason": "same notice"}\n```'

    g = ClaudeGrader(grade=grade)
    answer = {'url': 'https://www.gov.uk/news/adm/', 'confidence': 'likely'}
    assert g(_item(), answer) == 'accept'
    assert g(_item(), {'url': 'https://gov.uk/news/adm'}) == 'accept'  # same page, cached
    assert len(replies) == 1 and 'gov.uk/news/adm' in replies[0] and 'ico.org.uk/guidance/adm' in replies[0]

    def broken(system, prompt):
        raise TimeoutError('slow')
    assert ClaudeGrader(grade=broken)(_item(), answer) is None
    assert ClaudeGrader(grade=lambda s, p: 'no json here')(_item(), answer) is None


def test_score_rollouts_summary():
    items = [_item()]
    rollouts = [{'example_id': 'find_primary_source-x', 'rollout_id': 1, 'url': 'https://ico.org.uk/guidance/adm',
                 'confidence': 'verified'},
                {'example_id': 'find_primary_source-x', 'rollout_id': 2, 'url': 'https://ico.org.uk/', 'confidence': 'verified'},
                {'example_id': 'find_primary_source-nope', 'url': 'https://ico.org.uk/guidance/adm'}]
    rows = score_rollouts(items, rollouts)
    s = summarise(rows, 'key only')
    assert [r['reward'] for r in rows] == [1.0, -CONFIDENT_WRONG_PENALTY, None]
    assert (s['scored'], s['mean_reward'], s['solved'], s['penalised']) == (2, 0.375, 1, 1)
    assert s['outcomes']['unknown_example'] == 1


def test_homepage_keys_are_detected():
    assert key_is_homepage(_item(fragments=('statehouse.gov.ng',)))
    assert key_is_homepage(_item(fragments=('nsb.gov.tw/en',)))
    assert not key_is_homepage(_item())
    assert not key_is_homepage(_item(fragments=('pib.gov.in/PressReleasePage.aspx?PRID=2142786',)))


def test_no_cheat_earns_reward_on_fixture_items():
    items = [_item(), _item(fragments=('congress.gov/bill/119th-congress/house-bill/45',), example_id='find_primary_source-y')]
    report = gaming_check.run(items)['strategies']
    assert all(r['ok'] for r in report.values()), {k: v for k, v in report.items() if not v['ok']}


def _strict_item():
    item = _item(fragments=('gov.uk/government/news/ai-bill-introduced', 'bills.parliament.uk/bills/4035'))
    item['reference'].update(authoritative_url_fragments=['bills.parliament.uk/bills/4035'],
                             authoritative_hosts=['bills.parliament.uk', 'legislation.gov.uk'])
    return item


def test_strict_items_pay_only_for_the_text():
    item = _strict_item()
    assert _reward({'url': 'https://bills.parliament.uk/bills/4035/publications'}, item).outcome == 'key'
    release = _reward({'url': 'https://www.gov.uk/government/news/ai-bill-introduced', 'confidence': 'verified'}, item)
    assert (release.reward, release.outcome) == (-CONFIDENT_WRONG_PENALTY, 'announcement_only')
    elsewhere = _reward({'url': 'https://www.gov.uk/guidance/other', 'confidence': 'verified'}, item)
    assert (elsewhere.reward, elsewhere.outcome, elsewhere.penalised) == (0.0, 'not_authoritative', False)
    asked = []
    grader = lambda i, a: asked.append(a['url']) or 'accept'
    on_register = _reward({'url': 'https://www.legislation.gov.uk/ukpga/2026/1'}, item, grader)
    assert on_register.outcome == 'grader_accept' and asked == ['https://www.legislation.gov.uk/ukpga/2026/1']
    _reward({'url': 'https://www.gov.uk/guidance/other'}, item, grader)
    assert len(asked) == 1  # off-register pages never reach the grader on strict items


def test_strict_grader_prompt_asks_for_the_text():
    prompts = []
    g = ClaudeGrader(grade=lambda s, p: prompts.append(p) or '```json\n{"verdict": "reject", "reason": "x"}\n```')
    g(_strict_item(), {'url': 'https://www.legislation.gov.uk/ukpga/2026/1'})
    g(_item(), {'url': 'https://www.gov.uk/x'})
    assert 'authoritative document itself' in prompts[0] and 'authoritative document itself' not in prompts[1]


def test_no_cheat_earns_reward_on_strict_items():
    report = gaming_check.run([_strict_item()])['strategies']
    assert report['announcement_not_text']['mean_reward'] == 0.0
    assert all(r['ok'] for r in report.values()), {k: v for k, v in report.items() if not v['ok']}


def test_honest_confidence_pays():
    from techieray_training_lab.regulatory_research.find_primary_source import CORRECT_REWARD
    right, wrong = {'url': 'https://ico.org.uk/guidance/adm'}, {'url': 'https://ico.org.uk/'}
    reward = lambda a, c: _reward({**a, 'confidence': c}).reward
    assert [reward(right, c) for c in ('verified', 'likely', 'unverified')] == [1.0, 0.9, 0.8]
    assert [reward(wrong, c) for c in ('verified', 'likely', 'unverified')] == [-CONFIDENT_WRONG_PENALTY, 0.0, 0.0]
    # "verified" pays off exactly when the agent is more than about 71% sure
    ev = lambda p, c: p * CORRECT_REWARD[c] + (1 - p) * (-CONFIDENT_WRONG_PENALTY if c == 'verified' else 0.0)
    assert ev(0.75, 'verified') > ev(0.75, 'likely') and ev(0.65, 'verified') < ev(0.65, 'likely')
    report = gaming_check.run([_item()])['strategies']
    assert report['right_answer_always_likely']['mean_reward'] == 0.9 and report['right_answer_always_likely']['ok']
