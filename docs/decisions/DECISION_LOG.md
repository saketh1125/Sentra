# Sentra — Architecture Decision Log

**Purpose:** every architectural decision (D1–D20 from `Sentra_research.md`) is
recorded here with its options, the evidence that settled it, the outcome, and
the consequences. A decision is only marked **LOCKED** when evidence exists.

**Legend**
`[DOC]` project documentation · `[EXT]` external, with link · `[MEAS]` measured
by a Sentra spike · `[INF]` engineering inference · `[PENDING]` awaiting evidence

**Evidence files** live in `docs/evidence/` and are produced by runnable code in
`spikes/`. Every number in this log can be regenerated.

---

## Environment baseline (measured, 2026-10-02)

| Item | Value | Consequence |
|---|---|---|
| Python | 3.14.7 system; **project venv pinned to 3.12.13** | 3.14 lacks wheels for several native deps; 3.12 is the reproducible floor |
| Node | v22.22.2 | Frontend baseline |
| CPU / RAM / Disk | 16 cores / 62 GiB / 45 GB free | CPU-only inference is viable for embeddings; LLM needs care |
| Docker | 29.7.2, daemon live, overlayfs | Postgres + pgvector available via `pgvector/pgvector:pg17` |
| **LLM API keys** | **NONE PRESENT** | **Hard blocker for S5/S7/S8 quality measurement.** See D2/D3. |
| Network | pypi, github, osv.dev, huggingface all reachable | OSV and model downloads fine |

---

## Integration hazard discovered during S2/S3 — applies to P1/P2

Both external tools honour `.gitignore` **by default**, and Sentra's own
`.gitignore` excludes `data/repos/*`. A default invocation therefore silently
scans **zero files**, exits with an error or a success-looking empty result.

| Tool | Symptom observed | Mandatory flag |
|---|---|---|
| Semgrep CE | 0 findings, exit 0, looks like a clean repo | `--no-git-ignore` |
| osv-scanner | exit 128, `No package sources found` | `--no-ignore` |

**Locked requirement [MEAS]:** every external tool invocation must pass the
ignore-bypass flag, **and** the integration must assert a non-zero
scanned-file count. A zero-scan result is a harness failure, never a clean
result. This is recorded because it produced a false `0/21` recall in the first
S2b run before it was caught.

---

## D1 — Embedding strategy *(PENDING S4)*

| Field | Value |
|---|---|
| **Status** | **PENDING — S4 script complete but never produced measurements** (OOM-killed; see `docs/resource-incident.md`) |
| Options | (a) all-MiniLM-L6-v2 384d · (b) nomic-embed-text-v1.5 768d (research-doc suggestion) · (c) bge-small-en-v1.5 384d · (d) code-specialised `nomic-embed-code` 7B |
| Evidence required | hit@k, nDCG@k, expected-line@k on our own 24 hand-labelled queries; wall-clock; dimension |
| Why it matters | **Architectural:** dimension fixes the pgvector column type. Changing it later means re-embedding every repository and recreating the vector table. |
| Hard constraint | **[MEAS] no hosted embedding API key is available**, so a hosted candidate cannot currently be evaluated. All candidates must be local open-weights, which also satisfies the PRC §2.10 "code never leaves the machine" privacy posture. **[MEAS] backend is fastembed+onnxruntime, not sentence-transformers**, because the latter pulled >8 GB of NVIDIA CUDA wheels for a CPU-only host. |
| Status note | **Do not rerun S4 as previously written.** The full-process run reached ~51.9 GB RSS and was OOM-killed, taking the session with it. Required safety changes are listed in `docs/resource-incident.md` §6. |
| Outcome | *to be filled by S4* |

---

## D2 / D3 — LLM provider and local-vs-hosted *(BLOCKED — needs a decision)*

| Field | Value |
|---|---|
| **Status** | **BLOCKED — requires your input** |
| Problem | **[MEAS] No LLM API key exists in this environment** (no `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, or equivalent). Spikes S5 (documentation generation), S7 (LLM bug review) and S8 (PR summarisation) all require an LLM. |
| Options | (a) supply a hosted API key · (b) run a small local model via Ollama/llama.cpp on CPU · (c) defer all LLM spikes until a key exists |
| Evidence needed | tokens/sec on this 16-core CPU; quality on a real chunk-summary and a real review task |
| Constraint | PRC §1.7 already assumes an LLM is available "through an API or a local runtime". The documents permit local inference; they do not guarantee a key. |
| Impact if unresolved | S5/S7/S8 cannot be measured. M1, M2's LLM layer and M5 all depend on them. **P1–P3 can proceed without an LLM.** |
| Recommendation | Proceed with P1–P3 (no LLM required) while the provider question is settled. If a key is not supplied, evaluate a small local model so the "code never leaves the machine" mode is demonstrable rather than theoretical. |

---

## D7 — Supported languages

| Field | Value |
|---|---|
| **Status** | **LOCKED (provisional) — Python + JavaScript/TypeScript** |
| Options | Python+JS/TS (documented proposal) · +Java (documented stretch) · +C/C++ |
| Evidence | **[MEAS] S1:** Tree-sitter parsed 383 supported files across 3 repos at **100.00% parse rate, 100% clean parse rate**. **[MEAS] S2b:** detection probe used both Python and JS successfully. **[EXT]** Juliet (the only C/C++ benchmark found) is C/C++-only, and Semgrep CE's measured recall on our corpus was low enough that adding a third language would dilute an already thin evidence base. |
| Outcome | Lock **Python + JavaScript/TypeScript**. Java remains the documented stretch goal, unchanged. |
| Consequence | Extension remains configuration work, as the documents state. No third language in the critical path. |

---

## D8 — Parser / chunker strategy

| Field | Value |
|---|---|
| **Status** | **LOCKED — function/class/method chunks with module chunks for drift; decorators included** |
| Evidence | **[MEAS] S1:** 7,570 chunks over 383 files; **line-range accuracy 100.0000%** verified objectively by (1) byte containment inside the claimed line window and (2) byte-exact reconstruction from that window. Throughput **3.45 MB/s**, 390–12,790 files/s. |
| Defects found and fixed | (1) `decorated_definition` wrapper **and** its inner `function_definition` were both emitted at identical byte ranges → duplicate chunks. Measured 4 duplicate ranges in `requests/auth.py` alone; **786 phantom chunks removed** repo-wide (8,356 → 7,570). (2) Qualified names self-nested (`to_key_val_list.to_key_val_list`). Both fixed, and the spike now **asserts** 0 duplicates and 0 self-nested names so the defect cannot silently return. |
| Oversized chunks | **[MEAS]** 60 chunks >200 lines out of 7,570 (0.79%). Oversized-chunk splitting is therefore **not** a priority; correctness-first whole-function emission is acceptable at this rate. |
| Module chunks | Retained, but **excluded from the retrieval corpus** (S4) because a module chunk contains all its functions and would otherwise win queries trivially. Kept for M6 drift. |
| Outcome | Config-driven chunker (`ChunkerConfig`) already carries the open knobs (`include_decorators`, `emit_module_chunks`, `oversized_line_threshold`, `min_line_count`) so the remaining sub-choices are changeable without a rewrite. |

---

## D9 — Semgrep rule configuration

| Field | Value |
|---|---|
| **Status** | **LOCKED — `p/default`** |
| Options measured | `p/security-audit` (+`p/python`,`p/javascript`) · `+p/secrets` · `+p/ci` · **`p/default`** · `p/greatest-per-language-effort` · `p/owasp-top-ten` |
| Evidence | **[MEAS] S2c ruleset sweep** on a self-authored ground-truth corpus (21 vulnerable patterns, 4 safe controls): `p/default` **61.9% recall / 100% control specificity**, 16 findings on flask in 4.4 s. `p/security-audit` 42.9%. `p/owasp-top-ten` 14.3%. **`p/greatest-per-language-effort` returned 0%** (Pro-only rulesets are not available to CE). |
| S2b detail | With `p/security-audit`+`p/python`+`p/javascript`: **42.9% recall (9/21), 100% control specificity, 100% precision.** Adding `p/secrets` and `p/ci` did **not** improve recall. |
| Severity handling | **[MEAS]** Semgrep emits rule-authored severities only (`WARNING`/`ERROR`/`INFO`), plus a separate `confidence` field (`LOW`/`MEDIUM`/`HIGH`) and `metadata.cwe`. **No CVSS score.** A mapping to Sentra's critical/high/medium/low scale is required. See D10. |
| Licence constraint | **[EXT]** Semgrep CE engine is LGPL-2.1; Semgrep-maintained rules are under **Semgrep Rules License v1.0 (internal business use, no redistribution)**. Third-party registry rules carry their own licences. Recorded so rules are never redistributed. |
| Outcome | Use `p/default`. Record per-rule precision. Never claim cross-file detection. |

### ⚠️ Consequence for objective O3 — **needs your ruling**

**[MEAS] Semgrep CE recall on our ground-truth corpus is 61.9%, not ≥80%.**
The PRC's O3 target ("recall ≥80% on the seeded set") is therefore **not
reachable from the deterministic layer alone.** This is not a Sentra defect: it
is a property of Semgrep CE's measured coverage, and the research document
already predicted this risk.

Options:
1. **Keep the target and report per layer.** PRC §3.6 already asks for per-layer
   precision reporting. Report Semgrep-layer recall (measured ~62%) and
   LLM-layer recall separately, plus the combined figure. Honest, and needs a
   guide conversation because the headline number changes.
2. **Re-scope the seeded set** to patterns CE demonstrably covers (fairer recall
   figure, but a weaker claim — the set no longer spans realistic CWEs).
3. **Add a second deterministic engine** (CodeQL needs build databases and
   violates the never-build boundary, so this is not available to us).

**Recommendation:** option 1. Do not quietly redefine the seeded set to make the
number look better; that would be tuning the benchmark to the tool.

---

## D10 — OSV acquisition and severity normalisation

| Field | Value |
|---|---|
| **Status** | **LOCKED** |
| Acquisition | **osv-scanner CLI as the primary path**, with the OSV.dev API for severity resolution and for the O4 ground-truth comparison. |
| Evidence | **[MEAS] S3:** objective O4 target **met — 100% exact set match** on all 4 package@version pairs (`requests@2.19.0` 5/5, `urllib3@1.26.5` 10/10, `lodash@4.17.15` 4/4, `minimist@0.0.8` 2/2) against a direct `POST /v1/query` to OSV.dev. |
| Severity chain (locked) | 1. CVSS vector (v2/v3.1/v4.0) → **computed base score** → CVSS-spec qualitative band. 2. `database_specific.severity` string → band. 3. explicit `unknown`. |
| Why a calculator is required | **[MEAS]** OSV returns severity as a **CVSS vector string**, not a numeric score. Measured mix across the fixture: 28 `CVSS_V3` + 8 `CVSS_V4`. Tooling: `cvss==3.6`, which computes both v3.1 and v4.0 base scores. |
| Coverage | **[MEAS]** 36/38 advisory records (94.7%) carried a CVSS vector; 2 carried neither vector nor label. **After CVE-based deduplication, severity resolved for 100% of the 21 unique findings**, because the severity-less PyPA advisories were duplicates of GHSA records that do carry a vector. Dedup therefore improves severity coverage as well as counting. |
| Unresolved-severity policy | Explicit `unknown`; never silently inherited. Count and report it. |
| Fixed version | Extracted from `ECOSYSTEM`/`SEMVER` range events only. **GIT ranges are excluded**, because their `fixed` value is a commit SHA and telling a developer to "upgrade to `<sha>`" would be wrong. |
| Outcome | Normaliser implemented and measured in `spikes/s3_osv/normalizer.py`; carries into P3. |

---

## D11 — Doc-time reference vector *(deferred, tied to M6/P7)*

**Status: PENDING** — depends on the M6 cut decision. Note the underlying data
model gap recorded in the research (G10): `documents` stores `source_hash` but
no embedding, while M6's similarity branch requires a doc-time vector. If M6 is
cut, this decision disappears with it.

---

## D15 — Background job architecture

**Status: PENDING P1.** Depends on measured ingestion wall-clock, which P1 must
measure first. No job queue will be introduced without evidence that a
synchronous path is insufficient.

---

## D16 — Reproducibility mechanism

| Field | Value |
|---|---|
| **Status** | **LOCKED (design agreed, implementation in P8)** |
| Mechanism | LLM outputs cached keyed by `content_hash + model_id + prompt_version`; the weight/cap/threshold configuration snapshotted onto every `score_snapshots` row; model versions pinned. |
| Evidence so far | **[MEAS]** S3 determinism: two consecutive osv-scanner runs produced identical normalised findings. S2: Semgrep findings deterministic across two runs on all 3 repositories. The deterministic layers are already reproducible; this decision is about making the **LLM** layers equally so. |
| Why | PRC §1.5 requires the same repository state and configuration to give the same score. Without caching, the LLM layers make that unsatisfiable. |

---

## D17 — Findings schema: identity and detail fields

| Field | Value |
|---|---|
| **Status** | **LOCKED** |
| Identity | Findings are keyed by **canonical CVE** where one exists, because CVEs are the only identifier stable across the several advisory databases OSV aggregates. **[MEAS]** osv-scanner reported **38 findings representing only 21 unique CVEs — a 1.81× dedup factor, 44.7% duplicates** (the same vulnerability returned under both a PyPA id and a GHSA id). |
| Consequence if ignored | M7 deducts per finding. Naive counting would inflate the dependency deduction by ~1.8×. **This is the single highest-impact normalisation finding of P0.** |
| Detail fields | Package, version, ecosystem, lockfile path, affected range, fixed version, severity + **severity_source**, CVSS vector + base score, canonical id + all advisory ids + CVE. These are exactly the fields FR7 requires and that PRC §2.4's field list was missing. |
| For M2/M5 | Semgrep supplies a stable `extra.fingerprint` **[MEAS]** — reuse it rather than inventing a scheme. M5 findings key on `(repo, pr_number, rule_or_cve_id)`. |

---

## D19 — Deployment approach

| Field | Value |
|---|---|
| **Status** | **LOCKED — Docker Compose, localhost-bound** |
| Evidence | **[MEAS]** Docker daemon live; `pgvector/pgvector:pg17` and `postgres:17-alpine` manifests verified available. |
| Constraint | Single developer, local-first. Server binds to `127.0.0.1`; no auth is added (multi-user is out of scope per PRC §1.6). Secrets from environment only. |

---

## D20 — Evaluation protocol

| Field | Value |
|---|---|
| **Status** | **PENDING P0 close** — draft rubric required before S5/S7/S8 |
| Required | Rubric definitions, sample sizes, rater count, and the rule that thresholds are frozen before the final measurement run (data-strategy §10). |
| Already fixed | Dev / test / eval / demo data are separate roles; all repos pinned to commits; the S4 query set is evaluation-only and must not be used for tuning. |

---

## Spike status summary

| Spike | Status | Headline measurement |
|---|---|---|
| **S1** Tree-sitter | ✅ **PASS** | Parse rate 100.00% · line-range accuracy 100.0000% · 7,570 chunks · 3.45 MB/s. Targets: ≥99% / ≥95%. |
| **S2** Semgrep CE | ⚠️ **PASS with limitation** | Output contract satisfied · determinism confirmed on all 3 repos · location verification 13/13 · **recall 42.9%→61.9% (`p/default`)**. **Cross-file limitation: INCONCLUSIVE — see note below.** |
| **S2b** Detection probe | ✅ Informative | 21 self-authored vulnerable patterns, 4 safe controls: recall 42.9%, specificity 100%, precision 100%. |
| **S2c** Ruleset sweep | ✅ Done | `p/default` best at 61.9%. `p/greatest-per-language-effort` = 0% (Pro-only). |
| **S3** OSV | ✅ **PASS** | **O4 = 100% exact agreement** · dedup 1.81× handled · severity 100% resolved · determinism ✓ · **offline mode verified identical**. |
| **S4** Retrieval | ⚠️ **Written, NO RESULTS** | Script complete and syntax-valid; 24/24 ground-truth queries resolve. Run OOM-killed before producing output — see `docs/resource-incident.md`. **D1 still undecided.** |
| **S5** Doc generation | ⛔ Blocked on D2/D3 | Needs an LLM. |
| **S6** Drift | ⛔ Blocked on D2/D3 (partially) | Hash/AST signals are LLM-free; similarity signal needs embeddings from D1. |
| **S7** LLM review | ⛔ Blocked on D2/D3 | Needs an LLM. |
| **S8** PR risk | ⛔ Blocked on D2/D3 | Needs an LLM. |

### ⚠️ Cross-file limitation — INCONCLUSIVE, do not assert

The S2 cross-file experiment planted a single-file SQL-injection fixture (CASE A) and a
cross-file equivalent (CASE B). **Neither was flagged**, because the tested rulesets contain no
SQL-injection rule. The recorded verdict is `intra_procedural_limitation_demonstrated: false`.

**Correct position:** Semgrep CE's single-function/single-file boundary is stated in Semgrep's
own documentation and repeated in the research document, and it is consistent with everything
we observed — but **our experiment did not empirically demonstrate it**. Do not claim we proved
it. Re-run with a rule that actually fires (e.g. the confirmed `subprocess` + `shell=True`
pattern) before asserting it in the project report.

What *was* confirmed: pattern rules matching a dangerous API call fire wherever the sink sits,
including across files, because no taint flow is required to match the pattern.

---

## Open items requiring your decision

1. **D2/D3 — LLM provider.** No key exists. Supply one, approve a local model,
   or accept deferral of S5/S7/S8. *P1–P3 are unaffected.*
2. **O3 recall target.** Measured CE recall is 61.9%, not ≥80%. Approve the
   per-layer reporting redefinition (recommended) or a different approach.
3. **Demo repositories.** `Abhaya-Netra` and `ParamanaGST` are named in the
   specification but are not present in this workspace and no URLs were
   supplied. URLs, licences and pinned commits are needed before P9.