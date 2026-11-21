#!/usr/bin/env python3
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
from techieray_training_lab.regulatory_research.find_primary_source.reward import find_primary_source_reward

item = json.loads((pathlib.Path(__file__).resolve().parent / "item.json").read_text())
ans_path = pathlib.Path("/workspace/answer.json")
logs = pathlib.Path("/logs/verifier")
logs.mkdir(parents=True, exist_ok=True)

if not ans_path.exists():
    out = {"reward": 0.0, "outcome": "missing_answer_file", "correct": False, "penalised": False}
else:
    try:
        raw = json.loads(ans_path.read_text())
    except Exception as e:
        raw = {}
    blocked_marker = pathlib.Path("/workspace/.blocked_domain_seen")
    if blocked_marker.exists() or (isinstance(raw, dict) and raw.get("blocked_domain_seen")):
        out = {"reward": 0.0, "outcome": "blocked_domain_seen_in_transcript", "correct": False, "penalised": False, "answer": raw}
    else:
        res = find_primary_source_reward(item, raw)
        out = res.to_dict()
        out["answer"] = raw

reward = 0.0 if out.get("reward") is None else float(out["reward"])
(logs / "reward.txt").write_text(f"{reward}\n")
(logs / "reward.json").write_text(json.dumps({"reward": reward}, indent=2) + "\n")
(logs / "detail.json").write_text(json.dumps(out, indent=2) + "\n")
print(json.dumps(out, indent=2))
