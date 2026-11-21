"""The regulatory research training set: find the official source behind news of a legal or regulatory development.

  from techieray_training_lab.regulatory_research.find_primary_source import find_primary_source_reward, load_tasks
"""
from pathlib import Path

from techieray_training_lab.common import jsonl
from techieray_training_lab.regulatory_research.find_primary_source.reward import (CONFIDENT_WRONG_PENALTY, CORRECT_REWARD, OUTCOMES,
                                                              RewardResult, find_primary_source_reward)

DATA = Path(__file__).resolve().parents[4] / 'sets' / 'regulatory_research' / 'find_primary_source' / 'data'


def load_tasks(path=None):
    """The set's tasks as a dict keyed by example_id (from this repository's data folder by default)."""
    return {t['example_id']: t for t in jsonl.read(path or DATA / 'tasks.jsonl')}


__all__ = ['CONFIDENT_WRONG_PENALTY', 'CORRECT_REWARD', 'OUTCOMES', 'RewardResult', 'find_primary_source_reward', 'load_tasks']
