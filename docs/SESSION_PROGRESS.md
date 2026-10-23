# Session Progress — P0 Spike Verification (2026-10-22 → 2026-10-23)

Long orchestrator-led session: all 8 spike modules individually tested/verified,
evidence regenerated and committed per milestone. Work was done by subagents
(orchestrator-only); this file is the durable record. Current date: 2026-10-23.

## Status at a glance

| # | Module | State | Evidence |
|---|--------|-------|----------|
| S1 | tree-sitter parse/chunk | **PASS** | `docs/evidence/S1_tree_sitter.json` |
| S2 | semgrep CE (main) | **PASS w/ caveats** | `S2_semgrep.json` |
| S2b | semgrep probe (recall) | **PASS w/ bug found** | `S2b_semgrep_probe.json` |
| S2c | ruleset sweep (D9) | **PASS w/ bug** | `S2c_ruleset_sweep.json` |
| S3 | OSV / osv-scanner | **PASS w/ bug found** | `S3_osv.json` |
| S4 | retrieval (D1) | **PASS — decision made** | `S4_<candidate>.json` ×5 |
| S5 | docgen cost | **AUTHORED + PILOTED; full run BLOCKED** | `S5_docgen.json` (pilot), `S5_docgen_blocked*.json` |
| S6 | drift detection | **CODE READY, NEVER RUN** | `spikes/s6_drift/spike.py` (477 lines) |
| S7 | LLM review | **AUTHORED; deterministic half measured; LLM BLOCKED** | `S7_llm_review_blocked.json`, `S7_llm_review_partial_pre_block.json` |
| S8 | PR risk / M5 join | **JOIN PROVEN (LLM-free); LLM stage BLOCKED** | `S8_pr_risk.json`, `S8_pr_risk_blocked_llm.json` |

Decisions closed this session: **D1 = bge-small-en-v1.5, 384 dims** (S4);
**D9 = p/default ruleset** (S2c). D2/D3 (LLM provider) NOT closable yet — see §LLM.

## Verified results

### S1 — tree-sitter (PASS)
408/408 files parsed; 7,570 chunks; parse rate 100%; line-range accuracy 100%
(7,570 checks, 0 failures); 0 duplicate chunk ranges; 0 self-nested qualified
names; throughput 1.3–1.5 MB/s; 60 oversized chunks (>200 lines, informational).
Caveats: `spike.py` always exits 0 — the four `verdict` booleans are the truth;
timing fields are non-deterministic (counts are stable across runs).

### S2 / S2b / S2c — semgrep CE 1.179.0
- S2: determinism true (per repo); JSON contract OK; source-location fidelity
  13/13; 13 repo findings (all WARNING); cross-file limitation experiment did
  **NOT** reproduce (case A and B both failed to fire) — the evidence file's
  `limitations_honest_summary` still claims the opposite; treat as unproven.
- **ALL findings carry `extra.fingerprint == "requires login"` and
  `extra.lines == "requires login"`** (stock CE behavior; binary sha256 matches
  the official PyPI wheel). Consequences: the contract check only tests field
  presence; D17 finding-identity by fingerprint is dead; D9 severity mapping
  remains manual.
- S2b: 21 vulnerable + 4 safe controls; reported recall 0.429, control
  specificity 1.0, precision 1.0.
- **S2b/S2c attribution bug (unfixed):** findings are attributed to truth
  patterns by ±6-line nearest-match from the snippet's *first* line, which
  mislabels same-CWE siblings. Corrected truth: recall ≈ 0.476 (10/21);
  `md5_for_password` and `subprocess_shell_true` are falsely "missed",
  `os_system` falsely "detected". All S2c per-ruleset numbers inherit this bias
  (corrected column recorded in the tester report; ranking unchanged).
- S2c: **`p/default` wins D9** — probe recall 0.619 (vs 0.429 for the current
  trio) at equal wall-clock (~7 s on flask); cost is real-repo noise (16 vs 3
  findings). `p/secrets`/`p/ci` additions bought nothing.
  `p/greatest-per-language-effort` = **registry HTTP 404 artifact**, not a 0%
  capability — exclude that row from D9 comparisons. `ruleset_sweep.score()`
  has no zero-findings guard (silent 0-file scans possible).

### S3 — OSV / osv-scanner 2.6.0 (PASS)
Normalization chain = CVSS vector → database_specific → `unknown`; 0%
unresolvable. **O4 agreement 1.0** (4/4 packages, exact set match; independently
re-verified with a from-scratch extractor). CVE dedup 1.65× (38 raw → 23 unique).
Determinism: byte-identical raw output across runs. Offline mode genuine
(re-verified inside a network-blocked namespace: same 23 CVEs; both
`--offline-vulnerabilities --download-offline-databases` flags required).
Real-repo cost: requests 10.2 s (4→3 unique), axios 3.6 s (71→40 unique).
Bugs/caveats (unfixed, documented):
- `normalizer.py affected_range_text` keeps only the LAST range pair of a
  multi-range advisory (urllib3/CVE-2024-37891 displays the wrong range;
  presentation-only, counts unaffected).
- Severity fallback branches (database_specific, `unknown`) never exercised —
  `unresolvable_measured_pct: 0.0` reflects unexercised code, not a validated
  policy.
- Results time-drift with the live OSV DB (not date-reproducible).
- `--no-ignore` mandatory (same .gitignore trap as semgrep); exit 1 = vulns
  found, 128 = no sources.

### S4 — retrieval (PASS; D1 decided)
Corpus: requests@611c6162 → 807 chunks, 24 queries (24/24 resolved).
`name_and_content` beat `content_only` on every metric for both working models.

| candidate | dim | hit@10 | MRR | nDCG@10 | line@10 | peak RSS | verdict |
|---|---|---|---|---|---|---|---|
| **bge-small-en-v1.5** | 384 | 91.7% | 0.546 | 0.637 | 95.8% | 2508 MB | **D1 winner** |
| all-MiniLM-L6-v2 | 384 | 91.7% | 0.501 | 0.600 | 91.7% | 1276 MB | 2nd |
| potion-retrieval-32M | 512 | 66.7% | 0.314 | 0.398 | 66.7% | 613 MB | disqualified (quality) |
| nomic-embed-text-v1.5 | 768 | — | — | — | — | ~1 GB @ load | **embed failed** (3.3 GiB single buffer) |
| jina-embeddings-v2-base-code | 768 | — | — | — | — | 4088 MB | **embed failed** (0.93 GiB on top of 4.1 GB resident) |

- Both 768-dim candidates fail-fast under the project's 8 GiB bounded contract
  at slice 64 (per `docs/resource-incident.md`); 768 is not viable for P2 on
  this host. Effective quality ceiling: 22/24 (2 queries missed by all models).
- Script flaw: `peak_rss_mb` is printed after `del model; gc.collect()` — jina's
  true peak (4088 MB) was 5.6× the logged 730 MB. Use external sampling for RSS.
- Legacy `S4_retrieval.json` (INVALID, all `load_failed`) untouched; superseded
  by the 5 per-candidate files.

### S5 — docgen (authored; pilot measured; full run BLOCKED)
Pilot (10 chunks): **1.30 calls/chunk** (3 retries), ~9.2 s/chunk, 240 prompt +
266 completion tokens per chunk of which **74.4% were chain-of-thought**;
projection ~9,250 s per 1,000 chunks; coverage 90% (pilot); quality sample 9/9.
Graph/LightRAG variant not measured (not installed) — D4 stays open.
**Blocked from completing by the provider outage (see §LLM).** Note: the S5 cost
table still expects token counts; the CLI transport reports `chars_in/chars_out`
instead — adapt before rerun.

### S6 — drift (CODE READY, NEVER RUN)
`spikes/s6_drift/spike.py` is complete: doc↔chunk linkage via S5's own sampler
(exact `chunk_id` match against `S5_sample_docs.json`, not name-guessed);
detectors hash / hash+AST / hash+similarity; mutation classes M1 (rename),
M2 (literal), M3 (structure); FP controls incl. cosmetic negatives; similarity
threshold sweep {0.50–0.95}; memory contract per `resource-incident.md`.
Run (LLM-free, no dependency on the quota):
```bash
cd /home/saketh/Sentra && ulimit -v 8388608 && OMP_NUM_THREADS=4 \
  .venv/bin/python spikes/s6_drift/spike.py     # writes docs/evidence/S6_drift.json
```

### S7 — LLM review (authored; deterministic half measured; LLM BLOCKED)
Measured without an LLM: probe corpus re-scanned (18 files, 10 findings),
**10/10 exact attributions, 0 ambiguous** (the cwe_78.py L4/L7 and cwe_327.py L4
traps resolve correctly under file+vulnerable-line matching). A pre-block partial
run left real L1/L2 verdicts for 8/10 findings (precision 1.0 — **partial, not
an answer**), preserved as `S7_llm_review_partial_pre_block.json` /
`S7_sample_partial_pre_block.json`. `S7_llm_review.json` / `S7_sample.json`
deliberately absent until a full run lands.

### S8 — PR risk / M5 join (JOIN PROVEN; LLM stage BLOCKED)
- Corpus: **9 merged PRs from psf/requests** via unauthenticated GitHub REST
  (28 calls, 6 rate-limit remaining recorded; fetch stops at floor of 5). The
  spec's demo repos (`Abhaya-Netra` 200-but-0-PRs, `PramanaGST`) have **zero
  merged PRs** — unusable; source substitution documented in the evidence.
  Local clones are depth-1 (0 merge commits), so PR head state comes from
  `raw.githubusercontent.com` at each PR's head sha.
- **M5 file→finding join: PR-scope 7/7 findings = 100% coverage, 0 findings on
  unchanged files.** Repo-scope join 7/9 = 77.8% (the honest "what a reviewer
  would see" number). Determinism verified; `join_selfcheck` PASS (positive
  control 9/9, basename-only negative control 0).
- Finding identity: fingerprint is the constant `"requires login"` on all 12
  checked findings → **M5 must key on (repo, path, rule_id, line range)**.
- Stage 3 (LLM PR summaries + rubric draft) blocked; 1 pre-block summary kept in
  `S8_pr_risk_summaries.json` (not rubric-rated — D20 needs a human rater).

## LLM provider situation (the hard blocker — updates D2/D3)

`docs/decisions/DECISION_LOG.md` D2/D3 says "no LLM API key exists". **That is
stale.** Measured truth (2026-10-23):

| Path | Result |
|---|---|
| OpenRouter free (`nvidia/nemotron-...:free`) | worked, then **quota exhausted: used 51/50**; the quota error arrives **disguised as HTTP 200 with `error.code: 502`** in the body — status-code checks report fake success |
| opencode HTTP endpoint (`https://opencode.ai/inference/openai/v1`) | **403 `FreeTierError`** — free tier is gated to the official client |
| `opencode run` CLI (official client) | **works when quota remains**; clean stdout, JSON-parsable, 10.5 KB prompts OK, 3.5–18 s/call; no usage/tokens — cost = calls + chars + wall seconds |
| opencode free tier overall | **account-wide daily cap hit ("Free usage limit reached")** — blocks spike LLM calls AND opencode/* subagent spawns alike; resets ~00:00 UTC |
| tokenrouter / tokenouter (config'd free models) | 403 token-has-no-model-access / 503 no channel |
| NVIDIA direct key | lists 83 models, every call 404 "function not found for account"; occasional 60 s timeouts |
| Local inference | dead end today: no ollama binary, no llama.cpp, no GGUF weights on disk |

Consequence: S5 full run, S7 LLM verdicts, S8 `--stage summarize` all wait for
the 00:00 UTC reset or a paid/SENTRA_LLM_* credential. All three harnesses
already resolve credentials via env override (`SENTRA_LLM_API_KEY` /
`SENTRA_LLM_BASE_URL` / `SENTRA_LLM_MODEL` / `SENTRA_LLM_PROVIDER=opencode` /
`SENTRA_LLM_TRANSPORT=cli|http`) in `spikes/_llm.py` — no hardcoded secrets.

## Commits (pushed to github.com/saketh1125/Sentra)

- `cd6b19f` — S1–S4 evidence (10 files)
- `2d480be` — S5/S7/S8 harnesses + S5 pilot evidence + S8 join proof (15 files)

Deviation to know: `data/cache/pr_corpus.json` was **force-added** (`git add -f`)
because `.gitignore:12` ignores `data/cache/*`. Either accept it with an ignore
exception (`!data/cache/pr_corpus.json`) or amend it out — future commits of that
path will silently skip otherwise.

## Remaining work (ordered)

1. **Run S6** (minutes, LLM-free — command in §S6 above), write `S6_drift.json`,
   commit as milestone.
2. **On quota reset or paid credential**, in this order:
   - S5 full: `SENTRA_LLM_MODEL=opencode/glm-5.3-flash-free .venv/bin/python spikes/s5_docgen/spike.py --limit-chunks 300` (after adapting its cost table to chars-based usage)
   - S7 full: rerun `spikes/s7_llm_review/spike.py` (same env)
   - S8 summaries: `.venv/bin/python spikes/s8_pr_risk/spike.py --stage summarize`
   Commit each as its own milestone.
3. Optional evidence-quality fixes (all documented above, none applied):
   S2b/S2c ±6 attribution bug (corrects recall to ~0.476); S3
   `affected_range_text`; S4 `peak_rss_mb` reporting; `ruleset_sweep.score()`
   zero-findings guard; S5 cost-table chars adaptation.
4. Update `docs/decisions/DECISION_LOG.md` (D2/D3 no longer "no key") and
   `docs/development-status.md` with this session's results.
5. Housekeeping: rotate the plaintext tokens in `~/.git-credentials` (flagged
   live); decide the `pr_corpus.json` gitignore question.

## Risks / things not to cite

- `S7_llm_review_partial_pre_block.json` numbers (8/10, precision 1.0) are a
  **partial run** — not S7's answer.
- S5's cost table is a **10-chunk pilot** — real but 1/30 of the required sample.
- S3 evidence is date-coupled to the live OSV DB.
- `S4_retrieval.json` is INVALID (pre-fix load failures) — superseded.
- The opencode free-tier cap is account-wide: anything spawning opencode/*
  models (harness or spikes) shares it.
