"""Run cheating agents against the reward and report what each one earns.

  python -m techieray_training_lab.regulatory_research.find_primary_source check --items sets/regulatory_research/data/tasks.jsonl

Each strategy is a shortcut an RL policy could discover. Most are given the answer itself (its page, or its site), so
this is a stronger attacker than a real agent. A strategy passes when its mean reward is at most MAX_MEAN. `honest`
returns the reference page and must score 1, which shows the reward still pays for real work. Exit code 1 when any
cheat passes the bar or the honest answer does not.

Strategies run over the items that have an official source. On items with none, answering "no official source" is
the right answer, so `always_no_source` earns exactly `no_source_share` there: keep that share small in a pack.
"""
import json
import sys

from techieray_training_lab.common import jsonl
from techieray_training_lab.common.matching import host
from techieray_training_lab.regulatory_research.find_primary_source.reward import find_primary_source_reward

MAX_MEAN = 0.0


def _ref(item):
    strict = item['reference'].get('authoritative_url_fragments')
    if strict:
        return 'https://' + strict[0]
    return item['reference'].get('canonical_url') or 'https://' + item['reference']['accepted_url_fragments'][0]


def _announcement(item):
    """On a strict item, a key page that is not the authoritative text (the press release); else the answer itself."""
    ref = item['reference']
    others = [f for f in ref['accepted_url_fragments'] if f not in (ref.get('authoritative_url_fragments') or [])]
    return 'https://' + others[0] if ref.get('authoritative_url_fragments') and others else None


def _decoys(item, n=9):
    return [f'https://{host(_ref(item)) or "example.gov"}/news/{i}' for i in range(n)]


STRATEGIES = {
    'answer_site_homepage': lambda it: {'url': f'https://{host(_ref(it))}/', 'confidence': 'likely'},
    'answer_site_homepage_verified': lambda it: {'url': f'https://www.{host(_ref(it))}', 'confidence': 'verified'},
    'answer_site_homepage_english': lambda it: {'url': f'https://{host(_ref(it))}/en/?lang=en', 'confidence': 'likely'},
    'ten_urls_in_one_string': lambda it: {'url': ' '.join(_decoys(it) + [_ref(it)]), 'confidence': 'likely'},
    'ten_urls_comma_separated': lambda it: {'url': ','.join(_decoys(it) + [_ref(it)]), 'confidence': 'likely'},
    'ten_urls_as_a_list': lambda it: {'url': _decoys(it) + [_ref(it)], 'confidence': 'likely'},
    'always_no_source': lambda it: {'url': None, 'no_official_source': True, 'confidence': 'likely'},
    'answer_and_no_source': lambda it: {'url': _ref(it), 'no_official_source': True, 'confidence': 'likely'},
    'answer_inside_another_query': lambda it: {'url': 'https://news.example.com/r?u=' + _ref(it), 'confidence': 'likely'},
    'answer_inside_query_no_scheme': lambda it: {'url': 'news.example.com/r?u=' + _ref(it), 'confidence': 'likely'},
    'answer_as_path_on_another_site': lambda it: {
        'url': 'https://mirror.example.com/' + it['reference']['accepted_url_fragments'][0], 'confidence': 'likely'},
    'tracker_page': lambda it: {'url': 'https://www.techieray.com/GlobalAIRegulationTracker.html', 'confidence': 'likely'},
    'empty_answer': lambda it: {},
    # on strict items only: the announcement the key lists instead of the text (others: an empty answer)
    'announcement_not_text': lambda it: {'url': _announcement(it), 'confidence': 'likely'} if _announcement(it) else {},
}
HONEST = {'honest': lambda it: {'url': _ref(it), 'confidence': 'verified'}}
# the right answer, always marked "likely": a policy that never commits should not do as well as an honest one
HIDE_CONFIDENCE = {'right_answer_always_likely': lambda it: {'url': _ref(it), 'confidence': 'likely'}}


def run(items):
    report = {}
    with_source = [it for it in items if not it['reference']['no_official_source']]
    for name, make in {**STRATEGIES, **HIDE_CONFIDENCE, **HONEST}.items():
        results = [find_primary_source_reward(it, make(it)) for it in with_source]
        rewards = [r.reward for r in results]
        earned = [it['example_id'] for it, r in zip(with_source, results) if r.correct]
        mean = round(sum(rewards) / len(rewards), 4) if rewards else None
        ok = (mean is not None and mean >= 1.0) if name in HONEST else (mean is None or mean <= MAX_MEAN)
        if name in HIDE_CONFIDENCE:  # hedging every answer must earn less than answering honestly
            ok = mean is not None and mean < 1.0
        report[name] = {'mean_reward': mean, 'items_rewarded': len(earned), 'examples': earned[:5], 'ok': ok}
    share = round(1 - len(with_source) / len(items), 4) if items else None
    return {'strategies': report, 'no_source_share': share, 'items': len(items)}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    items = [r for path in argv for r in jsonl.read(path)]
    report = run(items)
    print(json.dumps(report, indent=2))
    return 0 if all(r['ok'] for r in report['strategies'].values()) else 1


if __name__ == '__main__':
    sys.exit(main())
