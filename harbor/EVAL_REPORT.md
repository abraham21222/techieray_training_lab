# Plain-English Walkthrough & Harbor Evaluation Report: `techieray_training_lab` (`find_primary_source`)

**Date:** November 21, 2026  
**Upstream Repo:** [`techie-ray/techieray_training_lab`](https://github.com/techie-ray/techieray_training_lab) (50-task preview)  
**What This Branch Adds:** Complete **Harbor 0.24.0 (`schema_version = "1.3"`)** container packaging of all 50 tasks, neutral containerized `websearch` + `webfetch` tools for fair cross-model evaluation (`terminus-2` / containerized CLI agents), tool- and verifier-layer anti-leak guards, empirical `3 × 10` Docker baselines, and an automated `harbor analyze` fairness audit.

---

## 0. Plain-English "Aircraft Manual" (Step-by-Step Walkthrough of Everything We Did)

If you want to understand (or reproduce) the whole project in 2 minutes with zero jargon:

1. **Step 1 — Understand what Techie Ray's task actually tests:**
   - You give an AI a 1-sentence news alert (e.g., *"Indiana enacts bill criminalizing AI deepfake intimate images"* + date + jurisdiction).
   - The AI has to search the web and return a 3-field JSON object with the **official government primary-source URL** (not news, not a law-firm blog) — OR recognize when **no official source exists** (5 of the 50 tasks are deliberate "wrong-jurisdiction" traps).
2. **Step 2 — Put all 50 tasks into Harbor Docker containers (`harbor/tasks/`):**
   - Each of the 50 tasks now lives in its own isolated Harbor 1.3 folder (`task.toml`, `instruction.md`, `solution/solve.sh`, `tests/verify.py`, `tests/item.json`) running Techie Ray's exact upstream reward function unchanged.
   - We sanity-checked the containers with Harbor's `oracle` (**10/10 = `1.000`**) and `nop` (**10/10 = `0.000`**).
3. **Step 3 — Fix the uneven tool playing field inside Docker (`websearch` + `webfetch`):**
   - In Techie Ray's original runner, Claude got search + page fetch, while Codex only got search snippets (zero page fetches). Comparing models on different tools isn't fair.
   - We built two neutral command-line tools directly into the shared Docker image (`Dockerfile.base`): `websearch` (supports `SERPER_API_KEY`, `BRAVE_API_KEY`, `TAVILY_API_KEY`, or zero-key DuckDuckGo fallback) and `webfetch` (browser-TLS HTML + PDF reader so Akamai/Cloudflare government sites like `canada.ca` don't block it). Both tools + `verify.py` block `techieray.com` to prevent answer leakage.
4. **Step 4 — Run 30 real inside-Docker trials (`3 × 10` stratified tasks):**
   - We ran `gpt-6.1-sol` **strictly inside Docker** with OpenAI's built-in search turned **OFF**, forcing it to use **only** our container's neutral `websearch` and `webfetch` tools across 10 diverse tasks × 3 attempts each (`30` trials, `0` crashes).
   - **Result:** Raw mean **`0.490`**, but audited true accuracy was **`87.5%` (`21/24`) on real official sources** and **`0.0%` (`0/6`) on the 2 fabricated traps** (4 hallucination penalties of `-0.25`).
5. **Step 5 — Run Harbor's built-in fairness auditor (`harbor analyze`) on all 17 non-1.0 trials:**
   - Every single trial scoring `< 1.0` was audited inside Docker against 3 checks: `reward_hacking` (17/17 PASS), `task_specification` (11/17 PASS, 6/17 FAIL), and `grader_fairness` (10/17 PASS, 7/17 FAIL).
   - We then manually reviewed every single one of those 7 flags to separate **true grader bugs** (5/7) from **our own tool bug** (1/7, fixed) and **over-literal auditing** (1/7, see Section 4.1 below).
6. **Step 6 — Reproduce in 3 commands:**
   ```bash
   cd harbor
   docker build -t techieray-harbor-base:latest -f Dockerfile.base .
   ./scripts/verify_packaging.sh
   harbor run -p subset10 -a terminus-2 -m openai/gpt-5.2 --ae SERPER_API_KEY="$SERPER_API_KEY" -k 3 -n 5
   ```

---

## 1. Plain-English Overview: What We Built & Why

Your repo already had two strong ingredients that most open legal benchmarks miss:
1. **A clean deterministic reward function (`reward.py`)** with negative penalties (`-0.25`) for hallucinating official sources on fabricated cases.
2. **Genuine cross-border, non-English coverage** (29 jurisdictions) plus **wrong-jurisdiction "no official source" traps**.

What was missing for labs and RL teams to plug it straight into modern agentic eval pipelines:
1. **Harbor Container Packaging (`harbor/tasks/`):** All 50 tasks are now standalone Harbor `1.3` containers (`task.toml`, `instruction.md`, `solution/solve.sh`, `tests/test.sh`, `tests/verify.py`, `tests/item.json`) using your exact upstream `find_primary_source_reward()` logic unchanged.
2. **Fair, Neutral Search + Fetch Inside Docker (`harbor/tools/websearch` & `webfetch`):**
   - In your current `agents.py`, Claude gets `WebSearch + WebFetch` while Codex only gets `web_search` snippets (zero page fetches). That makes head-to-head model comparisons and `"verified"` confidence calibration apples-to-oranges.
   - Inside `Dockerfile.base`, we bundled two standardized CLIs (`/usr/local/bin/websearch` and `/usr/local/bin/webfetch`) plus `tmux` so **any model** can be evaluated identically inside Docker via Harbor's model-agnostic **`terminus-2`** harness (or a containerized CLI with vendor search disabled).
   - `websearch` supports **`SERPER_API_KEY`** (Google SERP), **`BRAVE_API_KEY`**, or **`TAVILY_API_KEY`** via `--ae`, with a built-in zero-key fallback (`ddgs` + browser-TLS HTML) so anyone can reproduce immediately.
   - `webfetch` uses browser-TLS HTTP (`primp` + stdlib fallback) because raw `curl`/`urllib` get tarpitted by Akamai/Cloudflare on government sites like `canada.ca`, and extracts clean text from **both HTML and PDF** official gazettes.
   - Both tools + `verify.py` enforce a hard `techieray.com` anti-leak blocklist at the container layer.

---

## 2. Empirical Results: 30 Inside-Docker Harbor Runs (`3 × 10`) + Cross-Harness Runs

We selected a **10-task stratified subset (`harbor/subset10/`)** covering all difficulty strata: international standard (`G7`, `UAE`, `ASEAN/CN`), US state strict (`CA`, `NY`, `IN`), non-English strict (`Argentina`, `Brazil`), and **both fabricated wrong-jurisdiction no-source traps** (`South Africa`, `Argentina`).

### Top-Line Scoreboard

| Run | Where Agent Ran | Search / Fetch Setup | Trials | Exceptions | Raw Mean Reward | Audited True Accuracy* | Hallucination Penalties (`-0.25`) |
|---|---|---|---:|---:|---:|---:|---:|
| **Harbor Oracle** | Inside Docker | Gold `solve.sh` | 10 | 0 | **1.000** | 100.0% | 0 |
| **Harbor Nop** | Inside Docker | Empty submission | 10 | 0 | **0.000** | 0.0% | 0 |
| **Codex (`gpt-6.1-sol`) — Upstream Runner** | Host `agents.py` | OpenAI `web_search` snippets only (`0` fetches) | 8 | 0 | **0.425** | 62.5% (`5/8`) | 2 (`ZA`, `AR` traps) |
| **Codex (`gpt-6.1-sol`) — Harbor Docker Neutral (`3 × 10`)** | **Strictly Inside Docker** | **OpenAI search OFF; ONLY container `websearch` + `webfetch`** | **30** | **0** | **0.490** | **70.0%** (`21/30`) — **`87.5%` on real sources, `0.0%` on traps** | **4** (`3/3` ZA trap, `1/3` AR trap) |
| **Gemini 4 Neon (High) — Harbor** | Host `agy` + Docker verifier | `search_web` + `curl` (4m timeout, no search cap) | 8 | 0 | **0.463** | 100% on finished (`5/5`); 3 timed out | 0 |
| **Gemini 4 Neon (Medium) — Harbor** | Host `agy` + Docker verifier | `search_web` + `curl` + 5–6 search budget hint (5m) | 10 | 0 | **0.750** | **100.0%** (`10/10`) — **`8/8` real, `2/2` traps** | 0 |

*\*Audited True Accuracy counts trials where the agent returned a genuinely authoritative official primary-source URL for the exact instrument (e.g., official enrolled act PDF or full-text tab of the exact same bill) that failed only because of narrow deterministic URL-fragment matching.*

> **Methodological Note on Comparing Runs:**  
> The **30-trial `gpt-6.1-sol` Docker run** is a pure inside-Docker test of our neutral `websearch`/`webfetch` stack (zero vendor search, zero prompt modifications). Comparing host-side `agy-neon` (`search_web` + `curl` + search-budget hint) against `codex` is **not** a pure model-to-model comparison—it shows what happens once a frontier model has full search + fetch. For a strict head-to-head model leaderboard, run multiple models through Harbor's **`terminus-2`** with a locked `SERPER_API_KEY` or `BRAVE_API_KEY`.

---

## 3. Detailed Per-Task Results (`3 × 10 = 30` Inside-Docker Runs — `gpt-6.1-sol`, Neutral CLI)

| Task ID | Jurisdiction | Stratum | 3-Run Raw Rewards | Raw Mean | Audited True Pass | What Actually Happened Across the 3 Runs |
|---|---|---|---:|---:|---:|---|
| `19872e77eb80` | G7 (Canada) | Standard | `[1.0, 1.0, 1.0]` | **1.000** | **3/3** | Found & `webfetch`-verified exact `ised-isde.canada.ca` G7 declaration in 1–3 shell calls |
| `1c544f783673` | UAE | Standard | `[1.0, 1.0, 1.0]` | **1.000** | **3/3** | Found & `webfetch`-verified exact `ai.gov.ae` PDF report in 1–4 shell calls |
| `291bfe01383e` | ASEAN / CN | Standard | `[0.9, 0.9, 0.9]` | **0.900** | **3/3** | Found exact `asean.org` release all 3 times (`likely` because portal blocked fetch) |
| `44317a47ecb0` | US-NY | Strict | `[1.0, 1.0, 1.0]` | **1.000** | **3/3** | Found & verified exact `nysenate.gov/legislation/bills/2023/S7543/amendment/B` all 3 times |
| `7307095c7864` | Argentina | Strict (ES) | `[1.0, 1.0, 1.0]` | **1.000** | **3/3** | Searched in Spanish → verified exact `boletinoficial.gob.ar` `Resolución 710/2024` in 3 calls |
| `3c4534e4800c` | US-CA | Strict | `[1.0, 0.0, 0.0]` | **0.333** | **3/3** (*2 URL-bug misses*) | Run 1 gave `billNavClient.xhtml` (`+1.0`); Runs 2 & 3 gave `billTextClient.xhtml` for the **exact same `bill_id=202520260AB723`** (`0.0` `unlisted`) |
| `741577743871` | US-IN | Strict | `[0.0, 0.0, 0.0]` | **0.000** | **2/3** (*2 URL-bug misses*) | Runs 1 & 2 found & verified the **official Enrolled Act PDF** (`iga.in.gov/.../HB1047.06.ENRS.pdf`) → `0.0` `unlisted`! Run 3 cited a court blog (true miss) |
| `3979ac328815` | Brazil | Strict (PT) | `[0.0, 0.0, 0.0]` | **0.000** | **1/3** (*1 URL-bug miss*) | Run 1 found newer official `camara.leg.br` `Avulso` PDF (`codteor=3104780`) → `0.0` `unlisted`; Runs 2 & 3 drifted to Senate PL 2338/2023 (true misses) |
| `408cc4c1f197` | South Africa | **No-Source Trap** | `[-0.25, -0.25, -0.25]` | **-0.250** | **0/3** | Fell for the fabricated trap **3/3 times**: cited DR Congo's `.gouv.cd` digital code as `"verified"` (Run 2 even cited a spam-hacked page on `budget.gouv.cd`) |
| `55488895e866` | Argentina | **No-Source Trap** | `[0.0, 0.0, -0.25]` | **-0.083** | **0/3** | Cited China's `gov.cn` May 2026 plan in Runs 1 & 3 (Run 1 hit `-site:techieray.com` filter bug—now fixed); Run 2 abstained with `no_official_source=false` (`unanswered`) |

---

## 4. What Worked Great vs. What Needs Fixing (Concrete Points for Techie Ray)

### What's Genuinely Strong
1. **The fabricated wrong-jurisdiction traps (`no_official_source: true`) are gold.**
   - Look at the split in our 30 Docker runs: `gpt-6.1-sol` hit **`87.5%` (`21/24`) true accuracy** on real primary sources, yet went **`0/6` (`0.0%`)** on the two fabricated traps (taking `-0.25` hallucination penalties repeatedly by confidently citing DR Congo `.gouv.cd` and China `gov.cn` URLs for South Africa / Argentina prompts!).
   - Meanwhile, Gemini 4 Neon Medium caught **both traps (`2/2`)** cleanly.
   - **Takeaway:** Right now, 45 of 50 tasks (single-URL lookup) are close to saturated for frontier models with search + fetch, while the **5 of 50 negative-existence traps** are doing almost all the real discriminative work. Scaling trap ratio from `10%` → `25%–35%` (including subtler traps: draft/withdrawn bills, superseded guidance, wrong year/amendment) would immediately sharpen the benchmark's frontier signal.
2. **Non-English regulatory discovery works cleanly even on a zero-key search engine** — `gpt-6.1-sol` solved Argentina's `Boletín Oficial` (`3/3 = 1.000`) in 3 shell calls strictly inside Docker.

### 3 Verified Deterministic URL-Matcher Bugs + 1 Prompt/Strict-Mode Spec Gap (Confirmed by `harbor analyze`)
We ran Harbor's built-in **`harbor analyze`** across all **17 non-1.0 trials** from our `3 × 10` Docker run (`rubrics/fairness_rubric.toml` — grading `reward_hacking`, `task_specification`, and `grader_fairness`; full JSON saved at `harbor/results/harbor_analyze_fairness_3x10.json`):
- **`reward_hacking`: `17/17` PASS** (`0` hacks).
- **`task_specification`: `11/17` PASS, `6/17` FAIL** | **`grader_fairness`: `10/17` PASS, `7/17` FAIL**.
- Every true agent failure (all 3 South Africa trap failures, 2 Argentina trap failures, and 2 Brazil wrong-bill drifts) passed fairness cleanly (`SPEC=pass, FAIR=pass`), while `harbor analyze` independently confirmed **4 concrete fairness/spec bugs**:

1. **California Legislature (`3c4534e4800c` — AB 723) — `2/2` failing runs flagged (`SPEC=fail, FAIR=fail`):**
   - Gold fragment: `leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202520260AB723`
   - Submitted (Neon + Sol 2/3 runs): `leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=202520260AB723`
   - **Fix:** Normalize `leginfo.legislature.ca.gov` bill URLs by `bill_id=` across `billNavClient.xhtml`, `billTextClient.xhtml`, `billVersionsClient.xhtml`, and `billStatusClient.xhtml`.
2. **Indiana General Assembly (`741577743871` — HB 1047) — `2/3` runs flagged (`SPEC=fail, FAIR=fail`):**
   - Gold fragment: `iga.in.gov/legislative/2024/bills/house/1047/details`
   - Submitted (Sol 2/3 runs): `https://iga.in.gov/pdf-documents/123/2024/house/bills/HB1047/HB1047.06.ENRS.pdf` (literally the official Enrolled Act PDF on `iga.in.gov`!)
   - **Fix:** Accept both the bill details page and `iga.in.gov/pdf-documents/.../HB1047/...` enrolled/bill PDFs on `iga.in.gov`.
3. **Brazil Câmara dos Deputados (`3979ac328815` — PL 6237/2025) — `1/3` run flagged (`SPEC=fail, FAIR=fail`):**
   - Gold fragment: `camara.leg.br/proposicoesWeb/prop_mostrarintegra?codteor=3063060&filename=PL%206237/2025`
   - Submitted: Neon gave `prop_mostrarintegra?codteor=3063060` (missing cosmetic `&filename=`); Sol gave `prop_mostrarintegra?codteor=3104780&filename=Avulso+PL...` (updated official `Avulso` revision PDF).
   - **Fix:** Strip cosmetic `&filename=` query params in `common/matching.py` and accept the Câmara ficha page (`fichadetramitacao?idProposicao=...`) + official `Avulso` PDFs of the same bill.
4. **Silent `strict` Mode vs. `task_prompt.txt` Spec Mismatch (`741577743871` Run 3 — newly caught by `harbor analyze`!):**
   - `task_prompt.txt` explicitly tells every agent that *"the instrument itself, or that body's own announcement of it (...or a government portal's own report of the decision also count)"* — without ever telling the agent which items are marked `strict` (`authoritative_url_fragments` only, where announcements and government portal reports score `0.0`).
   - In Run 3 of `741577743871`, Sol submitted an official Indiana Office of Court Services legislative update (`legislativeupdate.courts.in.gov`) summarizing H.E.A. 1047 (`P.L. 79`), which scored `0.0` (`not_authoritative`).
   - **Fix:** Tell the agent explicitly on `strict` items (*"Return the authoritative statutory/regulatory text itself; announcements or portal summaries do not count"*), or accept official government-portal reports as the prompt currently promises.

*(Note: the 7th `grader_fairness` fail caught by `harbor analyze` was our initial `-site:techieray.com` exclusion false positive on `55488895e866` Run 1 — now fixed in `harbor/tools/websearch`.)*

### 4.1 Our Honest Verdict on `harbor analyze`: Where We Agree vs. Where We Push Back
Automated fairness auditors are super helpful for surfacing bugs quickly, **but they are not infallible**—sometimes they demand overly spoon-fed instructions where a real-world benchmark *should* expect professional judgment. Here is our plain-English call on all **7** flags:

- **5 / 7 flags — 100% AGREE (Real Grader Bugs — Fix in `common/matching.py` / `item.json`):**
  - California `billTextClient.xhtml` vs `billNavClient.xhtml` (2 runs), Indiana Enrolled Act PDF vs HTML details page (2 runs), and Brazil newer `Avulso` PDF (1 run).
  - *Why:* You should **never** "fix" these by telling the agent which tab to click in the prompt. The prompt is fine—the deterministic URL matcher just needs normalizers for state and foreign bills (just like Techie Ray already built for `congress.gov`, `federalregister.gov`, `admin.ch`, and `EUR-Lex`).
- **1 / 7 flag — 100% AGREE (Our Own Harness Bug — Already Fixed):**
  - Argentina trap Run 1 (`55488895e866`): the agent tried to *follow* the rule by searching `-site:techieray.com`, and our first regex flagged it as a leak. Fixed in `harbor/tools/websearch`.
- **1 / 7 flag — PARTIAL PUSHBACK (`741577743871` Run 3 — Indiana `legislativeupdate.courts.in.gov`):**
  - `harbor analyze` failed this trial on both `task_specification` and `grader_fairness` because `task_prompt.txt` says *"a government portal's own report of the decision also count"*, yet the item is silently marked `strict`.
  - *Our pushback:* You do **not** need to hand-hold the agent with a `strict: true` label! In real legal practice, when an enacted statute (`HB 1047`) is publicly posted on the legislature's own website (`iga.in.gov`), citing a court-staff summary newsletter (`legislativeupdate.courts.in.gov`) instead of the statute *should* lose credit.
  - *The clean 1-sentence fix (keeps the task realistic and hard):* Instead of saying *"the instrument itself, OR an announcement / government portal report also count"* as if they are equal, state the real-world lawyer priority rule in `task_prompt.txt`:  
    > *"Always return the primary instrument itself (statute, bill text, decree, regulation, or official gazette) whenever it is publicly posted. Only fall back to an issuing body's official announcement or government-portal report if the primary text itself is not published online."*

### 3 Additional Practical Findings
1. **Pretraining Memorization Check:** During an early smoke test where shell execution failed (`0` tool calls), `gpt-6.1-sol` still produced the exact California AB 723 URL (`billNavClient.xhtml?bill_id=202520260AB723`, `+0.90`) from memory alone. Weighting newer post-cutoff instruments (and pairing retrieval with fresh document analysis) prevents pure-memorization inflation.
2. **Anti-Leak Filter Subtlety (`-site:techieray.com`):** In Run 1 of `55488895e866`, `gpt-6.1-sol` tried to *obey* the anti-leak rule by adding `-site:techieray.com` to its search query, which tripped our initial regex! We fixed `tools/websearch` to strip polite negative `-site:techieray.com` clauses while still hard-blocking positive `techieray.com` queries/fetches and stripping any `techieray.com` URLs from results.
3. **How to Raise the Ceiling for Frontier RL Buyers:** Single-URL discovery is a great *Level 1* skill, but frontier labs will pay far more once each task pairs primary-source retrieval with **a verifiable downstream legal task grounded in the retrieved document** and runs inside **Harbor** with reproducible search.

---

## 5. Concrete, Realistic Roadmap to Make This Richer & Harder (Built Straight Off Your Existing Tracker)

All four ideas below build directly on the regulatory-tracking work you are already doing—no artificial puzzles, just the harder parts of real global AI regulatory practice that frontier models still fail on:

1. **Expand the "Regulatory Skepticism" Traps (Your Highest-Signal Feature Today)**
   - In our 30 Docker runs, `gpt-6.1-sol` hit **`87.5%`** on real primary sources yet went **`0/6` (`0%`)** on the two fabricated wrong-jurisdiction traps.
   - Realistic trap types you can generate directly from your tracker workflow:
     - **Wrong-jurisdiction traps** (already proven to crush overconfident models).
     - **Superseded / amended instrument traps:** the alert references an earlier draft bill or consultation that was replaced by an enacted statute or amended decree—agent must locate the *operative* text and flag the draft as superseded.
     - **Binding vs. non-binding status traps:** press coverage calls a regulator's voluntary guidance, consultation paper, or committee draft a "new AI law"—agent must inspect the primary document and classify binding force accurately.
     - **Unpublished / secondary-only traps:** widely reported by news outlets or law-firm alerts, where no official government text was ever published.
   - Raising the trap mix from `10%` to **`25%–35%`** immediately shifts the benchmark from "mostly easy search" into a tough precision/calibration test.

2. **Pair Primary-Source Discovery With Structured Legal Extraction (What a Tracker Editor Does Next)**
   - After finding the official PDF/statute, require the agent to extract verifiable fields directly from the primary text into a typed JSON schema:
     - Official citation / instrument number & enacting body
     - Legal status (`proposed`, `enacted`, `in_force`, `non_binding_guidance`, `repealed`)
     - Phased effective / compliance dates (often buried in the final section of a statute or gazette!)
     - Scope thresholds (revenue, user count, compute/FLOPs, or sector carve-outs) and maximum statutory penalties
     - Exact verbatim supporting quote / section reference from the primary document
   - This stays **100% deterministically (or cheaply) gradable** while preventing models from passing on search snippets or memorized URLs alone.

3. **Multi-Jurisdiction Compliance Matrix & Legislative Diff Tasks (Real In-House Counsel Work)**
   - **Legislative Diff:** Given a prior tracker entry (e.g., introduced bill text) and a new update (enrolled act / final decree), identify the exact substantive changes added or dropped before enactment.
   - **Cross-Border Product Check:** Given a realistic product scenario (e.g., *"launching an AI real-estate photo-editing feature across California, New York, EU, and Brazil"*), find the 3–4 operative primary sources and produce a structured compliance matrix (disclosure trigger, effective date, exemptions, statutory citation).
   - Multi-hop tasks like these naturally land in the **`40%–75%` frontier RL sweet spot**—hard enough to provide real training gradient, yet 100% grounded in real lawyer deliverables.

4. **Two-Tier Reproducible Harbor Setup for RL Buyers**
   - **Tier 1 (Live Neutral Harbor — shipped in this branch):** Standardized container `websearch` (`SERPER_API_KEY` / `BRAVE_API_KEY` / `TAVILY_API_KEY`) + `webfetch` (browser-TLS HTML/PDF) so any lab can run `harbor run -a terminus-2 -m <model>` apples-to-apples today.
   - **Tier 2 (Cached / Snapshotted Search Proxy for Large-Scale RL):** For 10,000-rollout RL training (GRPO/PPO), live government portals flake, rate-limit, and change URLs. Recording a local cached proxy (BrowseComp-Plus style) of search responses + fetched official HTML/PDFs pinned to each task's `as_of_date` turns the exact same Harbor tasks into a fast, zero-flake, 100% reproducible RL environment.
