#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== 1. Check relative symlinks & portability ==="
python3 - <<'PY'
import pathlib
root = pathlib.Path(".")
tasks = sorted(p for p in (root / "tasks").iterdir() if p.is_dir())
assert len(tasks) == 50, f"Expected 50 tasks, got {len(tasks)}"
for sub in ("subset8", "subset10"):
    for p in sorted((root / sub).iterdir()):
        assert p.is_symlink() and str(p.readlink()).startswith("../tasks/") and p.resolve().is_dir(), f"Bad symlink: {p}"
for pat in ("Dockerfile.base", "README.md", "tools/*", "agents/*.py", "tasks/*/task.toml", "tasks/*/instruction.md", "tasks/*/tests/verify.py"):
    for p in root.glob(pat):
        if p.is_file() and "/Users/" in p.read_text(errors="ignore"):
            raise AssertionError(f"Hardcoded /Users/ path in {p}")
print("[PASS] 50 Harbor tasks, 18 portable symlinks, zero hardcoded host paths")
PY

echo "=== 2. Verify container tools (tmux, websearch, webfetch HTML+PDF, anti-leak) ==="
docker run --rm -i techieray-harbor-base:latest python3 - <<'PY'
import json, pathlib, subprocess

assert subprocess.run(["tmux", "-V"], capture_output=True).returncode == 0
print("[PASS] tmux installed for Harbor terminus-2")

p = subprocess.run(["websearch", "Boletin Oficial Resolucion 710 2024 IA", "--max", "3"], capture_output=True, text=True)
assert p.returncode == 0, p.stderr
d = json.loads(p.stdout)
assert len(d["results"]) >= 1, d
print(f"[PASS] websearch ({d['provider']}): {len(d['results'])} results -> {d['results'][0]['url']}")

url_html = "https://www.canada.ca/en/innovation-science-economic-development/news/2025/12/canada-advances-international-cooperation-on-industry-ai-and-digital-technology-at-the-g7-industry-digital-and-technology-ministers-meeting.html"
ph = subprocess.run(["webfetch", url_html, "--max-chars", "400"], capture_output=True, text=True)
assert ph.returncode == 0, ph.stderr
dh = json.loads(ph.stdout)
assert dh["status"] == 200 and len(dh["text"]) > 100
print(f"[PASS] webfetch HTML: status={dh['status']} title={dh['title'][:60]!r}")

url_pdf = "https://iga.in.gov/pdf-documents/123/2024/house/bills/HB1047/HB1047.06.ENRS.pdf"
pp = subprocess.run(["webfetch", url_pdf, "--max-chars", "400"], capture_output=True, text=True)
assert pp.returncode == 0, pp.stderr
dp = json.loads(pp.stdout)
assert dp["status"] == 200 and len(dp["text"]) > 80 and "PDF extraction error" not in dp["text"], dp
print(f"[PASS] webfetch PDF (live Indiana HB 1047 Enrolled Act PDF): status={dp['status']} extracted={len(dp['text'])} chars")

assert subprocess.run(["websearch", "site:techieray.com ai"], capture_output=True).returncode == 2
assert pathlib.Path("/workspace/.blocked_domain_seen").exists()
pathlib.Path("/workspace/.blocked_domain_seen").unlink()
assert subprocess.run(["webfetch", "https://www.techieray.com/"], capture_output=True).returncode == 2
assert pathlib.Path("/workspace/.blocked_domain_seen").exists()
print("[PASS] anti-leak blocklist enforced on websearch & webfetch")
PY

echo "=== 3. Verify anti-leak verifier guard ==="
docker run --rm \
  -v "$(pwd)/tasks/find_primary_source-19872e77eb80/tests:/tests:ro" \
  -v "$(pwd)/tasks/find_primary_source-19872e77eb80/solution:/solution:ro" \
  techieray-harbor-base:latest sh -c '
    bash /solution/solve.sh >/dev/null
    websearch "site:techieray.com g7" >/dev/null 2>&1 || true
    python3 /tests/verify.py >/dev/null
    grep -qx "0.0" /logs/verifier/reward.txt
  '
echo "[PASS] verifier awards 0.0 when blocked_domain_seen marker exists"
