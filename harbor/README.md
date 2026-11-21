# techieray-harbor

Clean, model-agnostic **Harbor 0.24.0 (`schema_version = "1.3"`)** packaging of all 50 tasks from [`techie-ray/techieray_training_lab`](https://github.com/techie-ray/techieray_training_lab) (`regulatory_research / find_primary_source`), built for fair cross-model containerized evaluation (`terminus-2` and native CLI agents) and RL benchmarking.

## Why Containerized Neutral Search Tools?
Comparing vendor CLI agents out of the box (e.g., Claude Code with `WebSearch + WebFetch` vs. Codex with search snippets only vs. Antigravity CLI with Google search + `curl`) conflates **model capability** with **search backend and tool access**.

To support fair, apples-to-apples comparisons via Harbor's model-agnostic **`terminus-2`** harness, `Dockerfile.base` ships two standardized container CLIs plus `tmux`:

- **`websearch "<query>" [--max 10] [--provider auto|serper|brave|tavily|ddg]`**
  - Uses **`SERPER_API_KEY`** (Google SERP), **`BRAVE_API_KEY`**, or **`TAVILY_API_KEY`** when passed into the container (`--ae`), falling back automatically to a zero-key public meta-search (`ddgs` + browser-TLS HTML fallback) so anyone can smoke-test out of the box.
  - Hard-blocks `techieray.com` queries and strips any `techieray.com` URLs from results.
- **`webfetch "<url>" [--max-chars 12000] [--headers-only]`**
  - Browser-TLS HTTP client (`primp` + stdlib fallback) so government portals behind Akamai/Cloudflare load cleanly.
  - Extracts clean text from both **HTML** (`beautifulsoup4`) and **PDF** (`pypdf`) official gazettes.
  - Hard-blocks `techieray.com` (including redirects) and writes `/workspace/.blocked_domain_seen`, which `tests/verify.py` catches and scores `0.0`.

## Layout
- `tasks/<example_id>/` — All 50 tasks in Harbor 1.3 format (`task.toml`, `instruction.md`, `solution/solve.sh`, `tests/test.sh`, `tests/verify.py`, `tests/item.json`, `tests/lib/`)
- `subset8/` & `subset10/` — Stratified evaluation subsets (portable relative symlinks: no-source traps, US strict, non-US strict, standard international)
- `Dockerfile.base` & `tools/{websearch,webfetch}` — Shared base image (`techieray-harbor-base:latest`) with `tmux`, `curl`, `websearch`, and `webfetch`
- `agents/harbor_agy_neon.py` — Optional Harbor `BaseAgent` adapter for Antigravity CLI (`gemini-4-neon-medium` / `gemini-4-neon-high`) with full `stream-json` trajectory capture
- `EVAL_REPORT.md` — Plain-English benchmark findings, harness comparability notes, exact prompts, and deterministic URL-matcher bug reports

## Quick Start
```bash
# 1. Build shared Harbor Docker base image (includes websearch, webfetch, tmux)
docker build -t techieray-harbor-base:latest -f Dockerfile.base .

# 2. Verify Harbor packaging with Oracle (1.000) and Nop (0.000)
harbor run -p subset10 -a oracle -n 4 -o jobs --job-name oracle_check
harbor run -p subset10 -a nop    -n 4 -o jobs --job-name nop_check

# 3. Fair, apples-to-apples model evaluation with Harbor's terminus-2
#    Pass SERPER_API_KEY (or BRAVE_API_KEY / TAVILY_API_KEY) for a locked commercial SERP,
#    or omit it to use the built-in zero-key fallback.
harbor run -p subset10 -a terminus-2 -m openai/gpt-5.2 \
  --ae SERPER_API_KEY="$SERPER_API_KEY" -n 4 -o jobs --job-name terminus_gpt

harbor run -p subset10 -a terminus-2 -m anthropic/claude-sonnet-4-5 \
  --ae SERPER_API_KEY="$SERPER_API_KEY" -n 4 -o jobs --job-name terminus_claude

harbor run -p subset10 -a terminus-2 -m gemini/gemini-2.5-pro \
  --ae SERPER_API_KEY="$SERPER_API_KEY" -n 4 -o jobs --job-name terminus_gemini

# 4. Optional: Full-stack agent run with Antigravity CLI (Gemini 4 Neon)
PYTHONPATH=agents harbor run -p subset10 -a harbor_agy_neon:AgyNeonAgent -m gemini-4-neon-medium -n 5 -o jobs --job-name neon_med_10
```

## Licence
Code and Harbor packaging: **MIT** (matching upstream `techieray_training_lab`).  
Upstream task data: **CC BY-NC 4.0** (non-commercial research and evaluation; commercial training requires a licence from `info@techieray.com`).
