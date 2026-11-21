"""The training reward for one find_primary_source rollout.

  from techieray_training_lab.regulatory_research.find_primary_source import find_primary_source_reward
  result = find_primary_source_reward(item, answer)                  # deterministic, no network
  result = find_primary_source_reward(item, answer, grader=grader)   # unlisted official pages judged by a grader model

`item` is a training record (its `reference` holds the key). `answer` is what the agent returned:
  {"url": str | null, "no_official_source": bool, "confidence": "verified" | "likely" | "unverified"}

Reward, by the answer's stated confidence:

                      verified   likely   unverified (or none)
   correct              1.0       0.9       0.8
   certainly wrong     -0.25      0.0       0.0
   anything else        0.0       0.0       0.0

The gaps make honest confidence pay: claiming "verified" is worth it only when the agent is at least about 70% sure
(p * 1.0 + (1 - p) * -0.25 > p * 0.9 when p > 0.71). Correct means:
         the URL matches the key (common/matching.py); or the answer says no official source exists and none does;
         on a strict item (`reference.authoritative_url_fragments`), only the authoritative text matches, and the
         announcement the key also lists scores 0 (`announcement_only`);
         or, with a grader, the grader accepts an official page for the same development that the key did not list
Certainly wrong means one of DEFINITELY_WRONG (a homepage, several URLs, a blocked site, a page the grader rejected...).
None means the grader failed: drop the rollout rather than train on a reward nobody decided.

Without a grader an unlisted URL scores 0.0 and is never penalised, because it may be a correct page the key missed.
On a strict item an unlisted URL is passed to the grader only when it is on one of `reference.authoritative_hosts`
(the jurisdiction's official registers and publishers); elsewhere it scores 0.0 (`not_authoritative`).
Every result carries an `outcome` that says why it scored what it did (OUTCOMES).
"""
import re
from dataclasses import asdict, dataclass
from typing import Callable, Optional

from techieray_training_lab.common.matching import canonical, host, url_matches
from techieray_training_lab.common.rules import uses_blocked_domain

CONFIDENT_WRONG_PENALTY = 0.25
CORRECT_REWARD = {'verified': 1.0, 'likely': 0.9, 'unverified': 0.8}  # missing or unknown confidence: unverified

OUTCOMES = {
    'key': 'the URL matches the answer key',
    'no_source_correct': 'the answer says no official source exists, and none does',
    'grader_accept': 'the grader accepted an official page the key did not list',
    'grader_reject': 'the grader rejected a page the key did not list',
    'unlisted': 'a page the key did not list, and no grader was used',
    'grader_error': 'the grader gave no verdict',
    'blocked': 'the URL is on a blocked site (the tracker that published the answers)',
    'not_a_page': 'a homepage, or not a web address',
    'several_urls': 'more than one URL in the answer',
    'contradictory': 'the answer gives a URL and also says no official source exists',
    'source_claimed': 'the answer gives a URL, but no official source exists',
    'no_source_wrong': 'the answer says no official source exists, but one does',
    'unanswered': 'no URL and no claim that no source exists',
    'announcement_only': 'an announcement the key lists, where the item requires the authoritative text',
    'not_authoritative': 'an unlisted page off the jurisdiction\'s official registers, where the item requires the text',
}
# outcomes that are certainly wrong, so a "verified" answer with one of them is penalised
DEFINITELY_WRONG = {'grader_reject', 'blocked', 'not_a_page', 'several_urls', 'contradictory', 'source_claimed',
                    'no_source_wrong', 'announcement_only'}

# a Grader takes (item, answer) and returns 'accept', 'reject', or None when it could not decide
Grader = Callable[[dict, dict], Optional[str]]

_SEVERAL = re.compile(r'\s|[,;|]\s*(?:https?://|www\.)', re.I)


@dataclass(frozen=True)
class RewardResult:
    reward: Optional[float]
    outcome: str
    penalised: bool = False
    correct: Optional[bool] = False  # None when the grader failed

    def to_dict(self):
        return asdict(self)


def _is_page(url):
    """A web address with a host and something after it (a path or a query): never a bare homepage."""
    address = url if '://' in url.split('?', 1)[0] else 'https://' + url
    h = host(address)
    if not h or '.' not in h:
        return False
    rest = canonical(url)[len(canonical(h)):]
    return rest.strip('/?') != ''


def _on_hosts(url, hosts):
    h = host(url if '://' in url.split('?', 1)[0] else 'https://' + url)
    return any(h == x or h.endswith('.' + x) for x in hosts)


def key_is_homepage(item):
    """True when an accepted fragment is a bare homepage: any page on that site would match it, so leave it out."""
    return any(not _is_page(f) for f in item['reference']['accepted_url_fragments'])


def find_primary_source_reward(item, answer, grader: Optional[Grader] = None) -> RewardResult:
    ref = item['reference']
    answer = answer if isinstance(answer, dict) else {}
    url = answer.get('url')
    says_none = answer.get('no_official_source') is True
    verified = answer.get('confidence') == 'verified'
    strict = ref.get('authoritative_url_fragments') or []  # strict items: only the authoritative text scores

    if url is not None and not isinstance(url, str):
        outcome = 'several_urls' if isinstance(url, (list, tuple)) else 'not_a_page'
    elif url and url.strip():
        url = url.strip()
        if says_none:
            outcome = 'contradictory'
        elif _SEVERAL.search(url):
            outcome = 'several_urls'
        elif uses_blocked_domain(url if '://' in url else 'https://' + url):
            outcome = 'blocked'
        elif ref['no_official_source']:
            outcome = 'source_claimed'
        elif any(url_matches(url, f) for f in (strict or ref['accepted_url_fragments'])):
            outcome = 'key'
        elif strict and any(url_matches(url, f) for f in ref['accepted_url_fragments']):
            outcome = 'announcement_only'
        elif not _is_page(url):
            outcome = 'not_a_page'
        elif strict and not _on_hosts(url, ref.get('authoritative_hosts') or []):
            outcome = 'not_authoritative'
        elif grader is None:
            outcome = 'unlisted'
        else:
            verdict = grader(item, {**answer, 'url': url})
            outcome = {'accept': 'grader_accept', 'reject': 'grader_reject'}.get(verdict, 'grader_error')
    elif says_none:
        outcome = 'no_source_correct' if ref['no_official_source'] else 'no_source_wrong'
    else:
        outcome = 'unanswered'

    if outcome == 'grader_error':
        return RewardResult(None, outcome, correct=None)
    if outcome in ('key', 'no_source_correct', 'grader_accept'):
        return RewardResult(CORRECT_REWARD.get(answer.get('confidence'), CORRECT_REWARD['unverified']), outcome,
                            correct=True)
    if verified and outcome in DEFINITELY_WRONG:
        return RewardResult(-CONFIDENT_WRONG_PENALTY, outcome, penalised=True)
    return RewardResult(0.0, outcome)
