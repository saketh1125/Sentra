# Sentra — Technical Research Report

**Project:** Sentra — Engineering Trust Platform
**Document:** `Sentra_research`
**Purpose:** Research consolidation, feasibility assessment, milestone roadmap and implementation planning for the Sentra final-year major project.
**Author context:** B.Tech CSE (AI & ML), CMR College of Engineering & Technology, A.Y. 2026–27.
**Status of this document:** Planning and research phase. **No implementation code has been written.**

---

## How to read this document

Source tags are used throughout:

- **[DOC]** — established directly by our two authoritative documents (`Sentra_Project_Specification(1).docx`, `PRC2_Review_Content.docx`). Treated as fixed constraints.
- **[EXT]** — external research, with a link. Facts verified during this research pass.
- **[INF]** — my architectural inference or recommendation. Not established by the documents; offered for decision.

Anything that could not be verified is marked **UNVERIFIED** in place, or collected in Section 3.9 / Section 4.

Terminology note: our **modules** keep their documented numbers (M1, M2, M4, M5, M6, M7). Project **phases** are numbered **P0–P9** to avoid collision.

### Table of contents

1. [Existing Project Definition](#1-existing-project-definition-what-our-documents-already-settle)
2. [Research Gaps](#2-research-gaps--what-our-documents-do-not-sufficiently-establish)
3. [External Research Findings](#3-external-research-findings)
4. [Dataset / Data Source Inventory](#4-dataset--data-source-inventory)
5. [Research Paper Inventory](#5-research-paper-inventory-focused)
6. [Existing Tools / Systems](#6-existing-tools--systems)
7. [Project Roadmap — milestone-driven](#7-project-roadmap--milestone-driven)
8. [Architecture Decisions To Be Made](#8-architecture-decisions-to-be-made)
9. [Feasibility Spikes](#9-feasibility-spikes)
10. [Project Milestone Graph](#10-project-milestone-graph)
11. [Four-Month Implementation Plan](#11-four-month-implementation-plan-refined)
12. [Sentra Data Strategy](#12-sentra-data-strategy)
13. [Sentra — Master Development Blueprint](#13-sentra--master-development-blueprint)

---

# 1. Existing Project Definition (what our documents already settle)

These items need **no further research** and are treated as fixed constraints.

| Area | Established by our documents | Source |
|---|---|---|
| Purpose | Engineering-trust platform for a single developer answering "is this codebase healthy and safe to release?" | [DOC] Spec §1.1 |
| Boundaries | No code generation, no auto-fixes, no automated PRs, no execution of analyzed code, no runtime monitoring, no CI/CD execution, no training/fine-tuning, no multi-user/enterprise | [DOC] Spec §1.1, §2; PRC §1.6 |
| Architecture | One shared ingestion/knowledge core → 6 independent modules → one aggregation layer (readiness score) → one dashboard | [DOC] Spec §3; PRC §2.1 |
| Module IDs | 1, 2, 4, 5, 6, 7. Module 3 (ownership/bus-factor) removed to protect the 4-month timeline; multi-user/org feature, natural future extension | [DOC] Spec §2; PRC §1.6 |
| Stack | Tree-sitter · Postgres+pgvector · LightRAG (custom fallback pre-approved) · Semgrep CE · OSV-Scanner/OSV.dev · FastAPI · React · GitHub REST | [DOC] Spec §5, PRC §2.9 |
| Backend language | FastAPI (Python). Spec §5 allowed "FastAPI **or** Go"; PRC §2.9 fixes FastAPI | [DOC] |
| Data model | 8 tables: repositories, files, chunks, embeddings, documents, findings, pr_analyses, score_snapshots | [DOC] PRC §2.4 |
| Findings schema | module · severity · location · source · explanation · status | [DOC] PRC §2.5 |
| Score model | Transparent capped weighted deduction. Severity 10/5/2/0.5; caps M2=35, M4=30, M5=15, M6=20; labels Ready ≥85 / Needs Attention 60–84 / At Risk <60 | [DOC] PRC §2.6 |
| Cut order | M6 first, then M5. M1/M2/M4/M7 non-negotiable and form a complete story alone | [DOC] Spec §2, §6 |
| Evaluation targets | O1 ≥80% cited-correct Q&A · O2 ≥95% docs coverage · O3 recall ≥80% seeded / precision ≥70% reviewed · O4 100% agreement with direct OSV-Scanner · O5 ≥80% PR summary accuracy · O6 ≥90% injected drift · O7 deterministic + complete breakdown | [DOC] PRC §1.8 |
| Status | Requirements, architecture, data model, tool selection, evaluation plan, schedule complete. **Implementation not started** | [DOC] PRC preamble, Q10 |
| Differentiation | vs Copilot: persistent whole-codebase + decision-focused, not in-editor completion. vs Argus: Argus generates fixes, Sentra explains and scores | [DOC] Spec §1.3, §1.4 |

**Verification note [INF]:** I independently confirmed the PRC's two bibliographic anchors are accurate — RepoCoder really is EMNLP 2023, pp. 2471–2484 (<https://aclanthology.org/2023.emnlp-main.151/>), and the LLM-integrated static analysis paper really is *Proc. ACM Program. Lang.* 8, OOPSLA1, Art. 111, pp. 474–499, 2024, DOI 10.1145/3649828 (<https://dl.acm.org/doi/10.1145/3649828>). Good news for the report.

---

# 2. Research Gaps — what our documents do NOT sufficiently establish

| # | Gap | Why it matters | Research that closes it |
|---|---|---|---|
| G1 | **Semgrep CE's real detection ceiling.** Doc says Semgrep is "precise, deterministic" and sets O3 recall ≥80%. Semgrep's own docs warn CE "will miss many true positives … it can only analyze code within the boundaries of a single function or file." | Directly threatens the recall target and jury framing | [EXT] Semgrep CE language support (<https://docs.semgrep.dev/semgrep-ce-languages>); PrimeVul/VulnAgent-R2 recall data (§3.4) |
| G2 | **LightRAG's true cost and operational profile.** Doc treats it as "a lightweight knowledge graph." Upstream docs say LightRAG "has higher capability requirements for LLMs than traditional RAG because it requires LLMs to perform complex entity-relation extraction," uses **four LLM roles**, needs **four storage backends**, fixes vector dimension at table creation, and has **no re-embedding tool**. | Could invalidate the Month-1 critical path and the LLM budget | [EXT] [HKUDS/LightRAG README](https://github.com/HKUDS/LightRAG) |
| G3 | **Ground truth for Python/JS/TS vulnerability detection.** Nearly every public vuln dataset is C/C++. Doc proposes "seeded bugs" but doesn't say against what taxonomy or how many. | Seeded set design is the whole basis of O3 | [EXT] Juliet (C/C++ only), BigVul/DiverseVul/PrimeVul (C/C++), BugsInPy (Python, but bug-*fix* oriented) |
| G4 | **Doc-drift has no benchmark at all.** Doc sets "≥90% on injected drift cases" with no construction protocol. | Jury will ask how validity was established | [EXT] Drift literature is surveys + small tools only (§3.6) |
| G5 | **No PR-review dataset measures Sentra's actual M5 output** (summary + cross-referenced risk flags). Doc sets ≥80% "rated accurate" with no rubric. | Rubric must be defined or the metric is unfalsifiable | [EXT] CodeReviewer, SWRBench, AACR-Bench, ContextCRBench (§3.7) |
| G6 | **Citation correctness is underspecified.** Doc requires "citations to files and line ranges" and a combined 80% target. | Citation *correctness* and citation *faithfulness* are different metrics with very different failure rates | [EXT] arXiv 2412.18004 — up to 57% of citations are "post-rationalized" |
| G7 | **Retrieval quality is never measured separately from answer quality.** | Masks which half of M1 is failing | [EXT] RepoBench-R, CrossCodeEval-retrieval, RAGAS |
| G8 | **No repo source list.** Doc names candidates (Abhaya-Netra, PramanaGST, "one well-known OSS") without URLs, sizes, licenses, or verification that they contain findings worth showing. | A demo repo with no vulnerabilities makes the demo fall flat | [EXT] SWE-QA / SWE-bench Verified / BugsInPy / CrossCodeEval repo lists |
| G9 | **OSV severity normalization is undefined.** Doc requires `severity: critical/high/medium/low` for M4, but OSV severity is heterogeneous. | Blocks reproducible scores | [EXT] osv.dev records (§3.5) |
| G10 | **Drift's reference vector is missing from the data model.** Doc §2.3 requires comparing today's embedding to "the embedding at the time the documentation was generated," but `documents` stores only `source_hash`. | M6's similarity branch is unimplementable as specified | [INF] + [EXT] hash/similarity drift tools (§3.6) |
| G11 | **Findings schema cannot hold what M4/M5 must report** (package, version, affected range, fixed version, PR number, line *range*). | Blocks FR7/FR8 as specified | [DOC] internal contradiction |
| G12 | **Reproducibility NFR vs LLM nondeterminism** is never reconciled. | Score must be a pure function of state per FR10 | [INF] + [DOC] NFR §1.5 |
| G13 | **Semgrep Rules License v1.0** restricts Semgrep-maintained rules to "internal business use" and forbids resale/competing products. | Affects what may be shipped or redistributed | [EXT] <https://semgrep.dev/legal/rules-license> |
| G14 | **Evaluation targets are "proposed"** and pending guide sign-off. | Milestone acceptance criteria depend on them | [DOC] PRC §1.8 |

---

# 3. External Research Findings

## 3.1 Repository understanding & code RAG

**Finding 1 — Repository-level retrieval beats in-file context, consistently and measurably. [EXT]**
RepoCoder (EMNLP 2023) shows retrieval-augmented repository-level completion improves over in-file baseline by **>10% in all settings**, and iterative retrieval–generation beats single-shot RAG. Its companion RepoEval covers line / API / function-body completion on real repositories. → *Supports M1's retrieval-first design.* <https://arxiv.org/abs/2303.12570>

**Finding 2 — Cross-file retrieval is the hard part, and it is measurable. [EXT]**
CrossCodeEval was built by replacing import statements with empty classes and running **static analysis** to find code that genuinely requires cross-file context. It is also usable as a **code-retrieval benchmark** independent of generation. → *Two uses for Sentra: (a) a proven method to construct a retrieval test set without hand-labelling everything; (b) a permissively-licensed repo pool in Python/Java/TypeScript/C#.* <https://crosscodeeval.github.io/>

**Finding 3 — Graph-based retrieval helps, but the gain is modest and domain-specific. [EXT]**
GraphCoder replaces sequence similarity with a **code context graph** (control-flow + data/control dependence) and coarse-to-fine retrieval: **+6.06 code match, +6.23 identifier match** over retrieval baselines, with less time and space, across 8,000 tasks from 20 repositories. → *This is the strongest published evidence for the graph idea behind LightRAG — and it also shows the gain is single-digit points, not transformative.* <https://arxiv.org/abs/2406.07003>

**Finding 4 — ⚠️ LightRAG is significantly heavier than our documents imply. [EXT]**
Verified from the upstream README: four storage backends (KV, vector, graph, doc-status); default stores are in-memory and explicitly "not suitable for production"; **PostgreSQL recommended**; **four LLM roles** (EXTRACT, QUERY, KEYWORDS, VLM) configurable separately; "higher capability requirements for LLMs … because it requires LLMs to perform complex entity-relation extraction from documents"; **vector dimension is fixed at table creation and there is no re-embedding tool**; citation support added 2025.03; MIT license; ~39k stars. → *Implication for Sentra: M1's per-chunk LLM cost is not "one summary call per chunk" — the graph layer adds LLM extraction calls per chunk. This must be measured in Spike S5 before it is committed to.* <https://github.com/HKUDS/LightRAG>

**Finding 5 — Long-context is a real alternative, but weak for code. [EXT]**
RepoQA: 500 code-search tasks over 50 repositories in 5 languages. Its headline result is that models still struggle; and the SWE-QA paper reports GPT-4 achieving only a **1.31% pass rate with retrieval** on the original SWE-bench retrieval setup, versus better results with agent frameworks. → *Reinforces our documented argument (PRC Q3) that retrieval is the right call, and gives us the exact citation to make it credibly.* <https://arxiv.org/abs/2406.06025>

**Finding 6 — A repository-level QA benchmark that fits M1 evaluation almost exactly exists. [EXT]**
**SWE-QA** (ACL 2026 Findings): 720 question–answer pairs over **15 Python repositories** (astropy, conan, django, flask, matplotlib, pylint, pytest, reflex, requests, scikit-learn, sphinx, sqlfluff, streamlink, sympy, xarray), 48 per repo; those repos total **13,300 files / 22,522 classes / 142,404 functions / >3.4M LOC**. It ships RAG baselines (`rag_function_chunk`, `rag_sliding_window`) and agent baselines, pinned commits, and an LLM-as-a-judge scorer. Apache-2.0 on Hugging Face. → *This is the single most valuable external asset for Sentra: it gives a validated question set, reference answers, pinned repos, and a scoring harness — and 15 free, real, Python repository sources.* <https://arxiv.org/pdf/2509.14635> · <https://github.com/peng-weihan/SWE-QA-Bench>

**Finding 7 — Code embedding models are available and cheap to compare. [EXT]**
`nomic-embed-text-v1.5` — Apache-2.0, 137M, 768-dim, requires `search_query:`/`search_document:` prefixes, has a 547MB safetensors build. `nomic-embed-code` — Apache-2.0, 7B, reports beating Voyage Code 3 and OpenAI Embed 3 Large on CodeSearchNet across 6 languages. LightRAG itself recommends a **low-dimensional, fast** embedding model and names `BAAI/bge-m3` as a solid local choice, noting retrieval quality "has limited dependency on the Embedding model." → *Model choice is genuinely a spike question, not a foregone conclusion — and comparing candidates is cheap because retrieval can be scored on CodeSearchNet's 99 annotated queries or a small hand set.* <https://huggingface.co/nomic-ai/nomic-embed-text-v1.5> · <https://huggingface.co/nomic-ai/nomic-embed-code>

**Finding 8 — A relevant field survey now exists. [EXT]**
*Retrieval-Augmented Code Generation: A Survey with Focus on Repository-Level Approaches* (arXiv 2510.04905, CC BY 4.0, 152 papers reviewed) organizes the field by retrieval substrate / control regime / evaluation setting, and covers datasets, benchmarks, scalability, and the necessity boundary between RACG and long-context LLMs. → *Use as the framing citation in Section 3 of our report — it is current and lets us position ourselves without writing a novel survey.* <https://arxiv.org/abs/2510.04905>

## 3.2 Static analysis & rule engines

**Finding 9 — ⚠️ Semgrep CE's own documentation sets a low ceiling, and our documents do not acknowledge it. [EXT]**
Verified: CE engine is **LGPL-2.1**; **Semgrep-maintained rules are under Semgrep Rules License v1.0 — "available only for internal business use," cannot be resold or used in competing products**; third-party registry rules keep their own licenses (e.g. Trail of Bits AGPL-3.0). CE covers **30+ languages** with **2,000+ community rules** — but CE analysis is **limited to single-function, single-file** with no cross-file/interfile dataflow, and the project states plainly: *"In security contexts, Semgrep Community Edition will miss many true positives as it can only analyze code within the boundaries of a single function or file."* → *For an academic project running the CLI locally, the license is acceptable. But the recall ceiling is a first-class honesty item that must appear in our report and in the demo framing.* <https://docs.semgrep.dev/licensing> · <https://docs.semgrep.dev/semgrep-ce-languages>

**Finding 10 — CodeQL is strong but has a build dependency our architecture forbids. [EXT]**
`github/codeql` libraries/queries are **MIT**; the **CLI/engine is licensed separately** and is free only for research and open source. It requires **compilation databases** for C/C++, Java and C#. Supported: C/C++, C#, Go, Java, JS/TS, Python, Ruby, Rust, Swift. → *CodeQL would force building the analyzed repo, which violates the "read/parsed, never executed or built" boundary. Confirms the doc's rejection reason was correct and gives us a citable reason.* <https://github.com/github/codeql> · <https://codeql.github.com/>

**Finding 11 — SonarQube now crosses our product boundary. [EXT]**
SonarQube Advanced Security is a commercial add-on combining SAST, SCA, cross-file taint analysis (tracing taint *across* code and third-party library boundaries), IaC scanning and secrets detection. **AI CodeFix generates LLM fixes** for a set of rules in Java/JS/TS/Python/HTML/CSS/C#/C++, available only in Enterprise/Data Center editions. → *Sonar is a useful comparison target (it is the "unified code security platform" a jury will think of), but its auto-fix direction is precisely what Sentra must not become.* <https://docs.sonarsource.com/sonarqube-server/project-administration/ai-features/enable-ai-codefix>

**Finding 12 — GitHub's own stack has the same coverage profile we have. [EXT]**
GitHub Advanced Security = code scanning (CodeQL or third-party), secret scanning (default on public repos), dependency review, Dependabot. Free on public repositories; paid features require Team/Enterprise. → *Confirms a market gap we can state honestly: the free tier already excludes many teams, and there is still no free, explainable, whole-codebase trust view for an individual.* <http://docs.github.com/en/get-started/learning-about-github/about-github-advanced-security>

## 3.3 Hybrid static analysis + LLM (M2's justification)

**Finding 13 — ⚠️ The PRC's cited LLift paper supports a *different* architecture than M2's. This needs honest framing. [EXT]**
*Enhancing Static Analysis for Practical Bug Detection: An LLM-Integrated Approach* (OOPSLA 2024) introduces **LLift**, which **enhances static analysis** for use-before-initialization bugs in the Linux kernel by combining **post-constraint guided path pruning** with LLM natural-language reasoning. It found 4 previously undiscovered bugs acknowledged by the Linux community. → *LLift is not "LLM reviews arbitrary risky chunks." It is LLM-augmented path-sensitive analysis. Our M2 design is a **sibling, not a reproduction**. We should cite it as evidence that static analysis + LLM beats either alone — which is exactly what the paper concludes — while stating our pipeline differs (we use Semgrep as the deterministic base rather than a path-sensitive analyzer). Saying otherwise would be a jury risk.* <https://dl.acm.org/doi/10.1145/3649828>

**Finding 14 — The LLM's most reliable role in this pipeline is *triage*, not *discovery*. [EXT]**
- **Llm4sa** (ACM TKDD, DOI 10.1145/3653718): an LLM inspects large volumes of static bug warnings, reducing manual review effort; explicitly described as complementary to static analysis and easily integrated because it "solely operates on the outputs."
- **LLM4PFA** (arXiv 2506.10322): LLM-driven constraint reasoning filters **72–96% of static-analysis false positives** while missing only **3 of 45** true positives.
- **KNighter** (arXiv 2503.09002): generates checkers *from historical patch commits*; found 70 previously unknown bugs in the Linux kernel (56 confirmed, 41 fixed, 11 assigned CVEs).
- **Reducing FPs in Static Bug Detection with LLMs: An Empirical Study in Industry** (arXiv 2601.18844) reports manual inspection of ~10–20 minutes per warning in industry and that hybrid SAST+LLM achieves the best effectiveness.

→ **Implication for Sentra's M2 [INF]:** the evidence base is much stronger for *LLM filtering/triage of tool findings* than for *LLM finding bugs from raw code*. If we want our M2 to be defensible, the LLM layer should be positioned primarily as **risk triage + plain-English explanation + confidence filtering**, with "finding novel bugs" as a secondary, honestly-caveated capability. This also matches how a jury can verify it.

## 3.4 Vulnerability datasets — suitability analysis

The instruction was explicit: do not assume a dataset is suitable because it exists. Here is the assessment.

| Dataset | Contains | Langs | Scale | Labels | Access / License | Suitability for Sentra | Supports |
|---|---|---|---|---|---|---|---|
| **Juliet C/C++ 1.3** (NIST SARD #112) | Synthetic test cases, 118 CWEs, each with flawed **and** near-miss non-flawed variants to test discrimination | **C/C++ only** (1.1 also had Java) | **64,099** cases, 146 MB | Known CWE per case | Download from NIST; **public domain / CC0 1.0** | **Partially useful — as a Semgrep-engine sanity benchmark only.** Wrong language for our proposed Python/JS/TS scope. Would require adding C/C++ to scope. The paired good/bad variants make it a genuinely good *discrimination* test, which is exactly what our precision metric needs | M2 tool validation (optional) |
| **BigVul** | Vulnerability-fixing commits, C/C++ | C/C++ | Large | **Automatic** labeling | Public | **Not suitable.** Label accuracy measured at **~25%** | — |
| **Devign / CodeXGLUE Defect** | Pre-fix functions from FFmpeg + qemu | C/C++ | 2 projects, 26,037 functions / 11,888 vulnerable | Manual (≈600 person-hours) | Public | **Not suitable.** Highest-quality labels but only 2 projects and measured accuracy **24%** per PrimeVul; also a training-set artifact, not a detection benchmark | — |
| **DiverseVul** (RAID 2023) | 18,945 vulnerable + 330,492 benign functions, 150 CWEs, 795 projects (295 new) | C/C++ | Large | Automatic | Public, arXiv 2304.00409 | **Not suitable** (C/C++, accuracy ~60%). Valuable only as a *citation* on label noise | — |
| **PrimeVul** (ICSE 2025) | 6,968 vulnerable + 228,800 benign functions, 140+ CWEs, paired vulnerable/patched samples, **chronological splits** | C/C++ | Medium, high quality | Hybrid labeling, **86% (OneFunc) / 92% (NVDCheck)** | Public, **MIT** (<https://github.com/DLVulDet/PrimeVul>) | **Not usable as data (wrong language, and we don't train).** **Essential as evidence.** Its headline result — a 7B model scoring **68.26% F1 on BigVul but 3.09% F1 on PrimeVul** — is the single best citation for "why we do not claim high detection rates" and for why our seeded-recall number must be framed as *injected-pattern recall, not field recall* | Evaluation honesty, M2 reporting |
| **Out of Distribution, Out of Luck** (arXiv 2507.21817) | Cross-dataset duplication + CWE-distribution analysis of 7 public datasets | C/C++ | Meta-study | n/a | arXiv | **Essential as evidence.** Documents that **71.1% of PrimeVul appears in DiverseVul**, PrimeVul overlaps CVEfixes 28.4%, and NVD CWE match rates are only 43–75% (PrimeVul 74.83%, DiverseVul 43.01%, BigVul 70.97%) | Evaluation honesty |
| **BugsInPy** (ESEC/FSE 2020) | 493 real bugs in 17 real Python projects (>10k stars each), hand-curated, buggy+fixed versions retrievable | **Python** | 493 bugs / 17 projects | Real, reproducible (with caveats) | Public; ≈831 person-hours of curation | **Highly useful, with a documented caveat:** an independent reproduction study found only **67% of bugs reproducible** in the unmodified dataset. Best used as (a) a free pool of real Python repos with pinned bug/fix commits, and (b) a source of realistic seeded-bug patterns | M2 seeded bugs, M6 drift scenarios, repo sources |
| **Defects4J** (ISSTA 2014) | 854 active bugs across 9 Java projects, each with a triggering test | **Java** | 854 bugs | Real, reproducible | Public; needs Perl/Java toolchain | **Useful only if Java is in scope.** Java is our documented stretch goal. Requires heavy build tooling — conflicts with "never build" only if we execute; static reading is fine | M2 (stretch) |
| **OSS-Fuzz + oss-fuzz-vulns** | 13,000+ vulns / 50,000 bugs across 1,000 projects; `oss-fuzz-vulns` records **precise introduced/fixed commit ranges** | C/C++, Rust, Go, Python, Java/JVM, JS, Lua | Large | Real, verified; **CC-BY-4.0** for the vulns repo | Public; already **ingested into OSV** | **Two uses: (1) real bug-fix commit pairs for drift/PR/regression scenarios; (2) a cross-check that M4's OSV data is complete. Note the MSR 2021 study found only 98 of 20,000+ OSS-Fuzz bugs ever received a CVE** (<https://www.computer.org/csdl/proceedings-article/msr/2021/871000a131/1tB7jeDBsQM>) | M4, M6, M5 |
| **dfbench** (Depth First) | 253 examples / 910 vulnerabilities from real disclosed vulns, expert-reviewed | C/C++ heavy (from OSS-Fuzz lineage) | Small | Expert | **Scored examples are private** | **Unusable.** Verified to exist, but deliberately withheld to prevent contamination | — |
| **DepBench** (⚠️ name collision) | Two unrelated benchmarks share this name: (a) 95 dependency-breaking-update instances (Maven 38, npm 33, Cargo 15, PyPI 9) with Docker oracles — arXiv 2607.17957; (b) 203 dependency-upgrade tasks over 5 ecosystems (Maven 65, npm 68, Go 40, Cargo 20, Python 10) — arXiv 2608.30300 (Monash/Microsoft) | multi | Small | Real PRs | arXiv | **Neither is suitable for M4.** Both measure *repair* of dependency upgrades, not *vulnerability detection*. Citing "DepBench" without disambiguation would be an error. Record the collision so it isn't repeated | — |
| **DepDec-Bench** (arXiv 2601.00205) | Preliminary study of 117,062 dependency changes in agent- vs human-authored PRs | 7 ecosystems | Very large | Real | arXiv | **Useful as evidence, not data.** Agent-authored PRs introduced vulnerable deps **924 times (2.5%)** vs humans **659 (1.6%)**; 86.6% / 83.3% had a safe version available. This is a *published argument that PR-time dependency risk is real and worth a module* — a strong citation for M5's existence | M5 justification |

**Bottom line for Sentra's data strategy [INF]:** there is **no high-quality public vulnerability-detection ground truth for Python/JS/TS**. The PRC's seeded-bug plan is therefore not a compromise — it is the correct design. We should say so explicitly in the report, cite PrimeVul + OOD-Out-of-Luck for the label-noise argument, and use BugsInPy/OSS-Fuzz for *realistic patterns and fix commits* rather than as ground-truth test sets.

## 3.5 Dependency vulnerability analysis

**Finding 15 — OSV needs no key and covers the ecosystems we need. [EXT]**
Verified from osv.dev's live database listing: npm **229,015** entries, PyPI **25,220**, Ubuntu 65,637, Wolfi 290,650, Debian, Red Hat, Rocky, SUSE, openEuler, RubyGems 5,326, Packagist 7,100, plus OSS-Fuzz 4,014 and SwiftURL. API at `api.osv.dev/v1/vulns/{id}`. → *Confirms the doc's "open, free, no API key" claim is currently true.* <https://osv.dev/list>

**Finding 16 — ⚠️ OSV severity is real but heterogeneous; a normalization rule is genuinely required. [EXT]**
Inspected live records:
- `GHSA-g9cg-prrw-2r8q` → CVSS_V4 **8.7 (High)**, aliases CVE-2026-102996, fix available
- `DEBIAN-CVE-2026-87491` → CVSS_V3 **8.8 (High)**
- `BIT-python-2026-15310` → CVSS_V4 2.1, plus `database_specific: {"severity": "Low"}` and a CPE
- `CGA-6vvh-8vg7-j5cr` (Chainguard) → CVSS_V4 2.0 (Low)
- Several Wolfi/Ubuntu entries show **no fix available** and no summary

→ *Findings:* (a) severity is usually present as a CVSS v3/v4 base score; (b) some records carry only a `database_specific.severity` string; (c) some carry neither; (d) ranges are `SEMVER`/`ECOSYSTEM` typed with `introduced`/`fixed` events. A deterministic band-mapping plus an explicit unknown-severity policy is required for FR7 + reproducible scoring. This is now a well-evidenced item in the decisions table. <https://osv.dev/vulnerability/GHSA-g9cg-prrw-2r8q>

**Finding 17 — OSV-Scanner v2 has features that materially help Sentra's constraints. [EXT]**
Verified: **Apache-2.0**, Google; current v2.6.0 (Sep 2026). `osv-scanner scan source -r DIR` recursively scans supported manifests. **11+ ecosystems, 19+ lockfile types.** Optional **call analysis** for reachability-based noise reduction. **Offline mode** (`--offline --download-offline-databases`) for scanning against a local DB. **License scanning** via deps.dev with SPDX allowlists. **Guided remediation (`fix`) is experimental and explicitly warned as risky** because it can make the package manager execute scripts.

→ *Three consequences: (a) offline mode makes the viva demo bulletproof and removes an API dependency; (b) license scanning is a free bonus we can mention as a documented extension; (c) **`fix` must stay firmly out of scope — it is automatic remediation, i.e. our prohibited behaviour.* <https://github.com/google/osv-scanner>

**Finding 18 — The doc's rejection of NVD is quantitatively justified. [EXT]**
NVD API 2.0 rate limits: **5 requests per rolling 30 seconds without an API key; 50 per 30 seconds with a key** (key passed in a request header). → *For a single-developer tool processing a few hundred dependencies, unauthenticated NVD would be painfully slow and is exactly the "rate limits accepted" risk the doc already flags. OSV is the right primary source. This is now a citable, quantitative justification rather than a preference.* <https://nvd.nist.gov/developers/start-here>

**Finding 19 — SCA accuracy limitations are documented in the literature. [EXT]**
*A comparative study of vulnerability reporting by software composition analysis tools* (ESEM 2021, DOI 10.1145/3475716.3475769) compares how tools report vulnerabilities and where they diverge. → *Supports the PRC §3.3 statement that we "state these limits." The PRC's third cited paper ("Software Composition Analysis for Vulnerability Detection: An Empirical Study on Java Projects", ESEC/FSE 2023) is consistent with this body of work, but I could not open and verify its bibliographic record in this session — see the unverified list.* <https://dl.acm.org/doi/10.1145/3475716.3475769>

**Finding 20 — "100% agreement" with the scanner must be scoped. [INF]**
Since we wrap OSV-Scanner, agreement is true by construction for the *set of affected package@version pairs* — but **not** for: severity (we derive it), affected-range and fixed-version rendering (we reshape it), or reachability filtering (optional in the scanner). → *Define O4's metric precisely as "identical affected package@version set vs a direct OSV-Scanner run on the same lockfiles at the same OSV database snapshot."* OSV-Scanner's offline mode makes a pinned, reproducible comparison possible.

## 3.6 Documentation drift

**Finding 21 — Drift is prevalent; this is our strongest motivation citation. [EXT]**
Tan, Wagner & Treude found that **more than a quarter of the 1000 most popular GitHub projects contained at least one outdated code-element reference in their documentation.** → *Use this in Report §1 (Motivation) instead of asserting the problem.* <https://arxiv.org/abs/2212.01479>

**Finding 22 — Prior tool exists as a GitHub Action built on that work. [EXT]**
*Wait, wasn't that code here before? Detecting Outdated Software Documentation* (arXiv 2307.04291) packages the same approach into a PR-triggered GitHub Action. → *Cite it so we are not accused of reinventing it.* <https://arxiv.org/abs/2307.04291>

**Finding 23 — A 2025 survey confirms the field is immature. [EXT]**
*A Review on Detecting and Managing Documentation Drift in Software* (Mohamed, IEEE 2025, doc 11196773) reviews heuristic methods, synchronization algorithms, AI-driven tools, multi-agent systems and ML — and frames consistency as an unsolved lifecycle problem. → *This is our justification for treating M6 as a research contribution and for accepting that M6 carries an evaluation-construction cost.* <https://ieeexplore.ieee.org/document/11196773>

**Finding 24 — ⚠️ There is no benchmark for documentation drift, and our method is not novel. [EXT]**
No dataset, no standard benchmark, no leaderboard. And the method we specify — **git/timestamp comparison + AST-signature hashing to ignore formatting noise + dense-embedding cosine similarity (commonly ~0.75 threshold)** — is independently implemented by several small tools: `nexical/docgap` (two-phase Git + AST-signature hashing), `jbrockSTL/doc-drift` (LLM + GitHub Actions, configurable confidence threshold), the VS Code "Drift" extension (JSDoc signature matching + git blame), and `driftszone/Docs-Drift` (Tree-sitter AST signature matching + embeddings + a documented **0.75 cosine threshold**).

→ **Honest positioning [INF]:** our drift method is *known prior art, competently synthesized*. Our contribution is (a) integrating it onto Module 1's existing embeddings at zero extra ingestion cost, (b) unifying it into the readiness score, and (c) **constructing and publishing an evaluation**, since none exists. Item (c) is the genuinely defensible contribution and should be stated that way.

**Finding 25 — The data model gap is real and must be closed as a decision, not a silent fix. [DOC vs EXT]**
Our `documents` table has `text, source_hash, generated_at` but no stored embedding, while §2.3 requires comparing "the current chunk embedding with the embedding at the time the documentation was generated." → *Decision D11: store a doc-time snapshot vector, or re-embed the stored doc text at comparison time. Either is defensible; the first is faster and more reproducible, the second is cheaper to store.* [DOC] PRC §2.3 vs §2.4.

## 3.7 Pull-request review

**Finding 26 — Review data exists and is usable, but none of it measures our M5 output. [EXT]**

| Resource | Content | Suitability for M5 |
|---|---|---|
| **SWRBench** (`ZZR0/SWRench`, **MIT**) | 1,000 real PRs from 12 popular Python OSS projects (scikit-learn, sympy, matplotlib, astropy…), **balanced 500 with reviewer-confirmed introduced changes / 500 clean**, with commit diffs, reviewer comments, fix commits, plus LLM-as-judge scoring | **Best available fit.** Real repos, balanced labels, permissively-licensed, exposes exactly the discrimination problem (find real issues *and* approve clean PRs) |
| **AACR-Bench** (Alibaba, **Apache-2.0**, arXiv 2601.19494) | 200 PRs / 50 repos / 10 languages, expert-verified comments, with **diff-level / file-level / repo-level context annotations** and an evaluation pipeline | **Good secondary source.** Its context-level annotation directly informs our M5 prompt design |
| **ContextCRBench** (arXiv; **identifier UNVERIFIED — re-check before citing**) | Crawled 153.7k issues/PRs; each sample links a line-level review comment to its change **plus issue text, PR description, and before/after function code** | **Critical design finding:** LLMs "still fall short of the requirements for reliable, automated code review," and enriching prompts helps generally, but **textual context (issue/PR description) helps more than code context**. → M5 must feed the PR title + description + linked issue, not just the diff |
| **CodeReviewer** (ESEC/FSE 2022, arXiv 2203.09095) | Pre-trained on large-scale diff↔comment pairs from GitHub PRs across **9 languages**; dataset on Zenodo; project-level splits to prevent leakage | Foundational reference. **Dataset license not verified this session** |
| **SWE-PRBench** (Mar 2026) | 350 PRs with human-annotated ground truth for AI code-review quality | Promising; bibliographic details not independently verified |
| **PRTiger** (ICSME 2022) / **PRSummarizer** (arXiv 1909.06987) / **T5-PR-desc** (arXiv 2408.00921) | PR *title* / *description* **generation** corpora: 43,816 PRs/495 repos; 41k PRs from 333k; 33,466 PRs | Relevant background for summarization, but these train/evaluate **generation with ROUGE**. Sentra's O5 is *human-rated accuracy*, which is a different and weaker-to-operationalize metric. The rubric must be written down |

**Finding 27 — Synthetic mutation injection is a validated PR-review evaluation technique. [EXT]**
*Bigger Isn't Always Better: A Comparative Evaluation of LLMs for Automated Code Review* (arXiv 2606.15689) builds a 150-sample benchmark from **100 synthetic mutation-injected bugs + 50 real bug-fix PRs** across TypeScript/Python/Go, with a two-pass deterministic-matching + LLM-adjudication framework, and reports logic 54% / security 23% / performance 11% / architecture 9%. → *Validates the PRC's seeded approach for PR review, and gives us a ready category taxonomy for labeling.* <https://arxiv.org/html/2606.15689v1>

## 3.8 Evaluation methodology

**Finding 28 — Separate retrieval from generation, and measure citations two ways. [EXT]**
- RepoBench decomposes into **R** (retrieval), **C** (completion), **P** (pipeline); CrossCodeEval doubles as a retrieval benchmark; CodeSearchNet's leaderboard metric is **NDCG over 99 hand-annotated queries across 6 languages**. → *Retrieval is cheaply, objectively measurable. Measure it separately.* <https://crosscodeeval.github.io/> · <https://github.com/github/CodeSearchNet>
- **RAGAS** (arXiv 2309.15217) gives reference-free *faithfulness*, *answer relevancy*, *context relevance*, and with references *context precision / context recall*; its metrics agreed with human annotators at **0.95 / 0.78 / 0.70**. LightRAG has integrated RAGAS for exactly this reason. → *Adopt the metric definitions; we do not need to run RAGAS as a dependency.* <https://arxiv.org/html/2309.15217>
- **Citation correctness ≠ citation faithfulness.** arXiv 2412.18004 disentangles them and reports **up to 57% of citations are "post-rationalized"** — the answer is right but the citation was attached after the fact rather than causing the claim. → *Define our metric as citation **precision** (does the cited line range support the claim?) and citation **recall/comprehensiveness** (is every claim cited?). Report both.* <https://arxiv.org/pdf/2412.18004>

**Finding 29 — Our O3 target is optimistic as literally written; scope it per layer. [EXT + INF]**
Evidence that zero-/few-shot LLM vulnerability detection is hard: VulnAgent-R2 (arXiv 2603.13384) reports on PrimeVul **F1 0.385 / AUROC 0.781**, with **precision 0.402 / recall 0.370** at default threshold and **precision 0.561 / recall 0.214** at a high-precision threshold — and notes PrimeVul "remain[s] difficult." Combined with Semgrep CE's single-function ceiling [Finding 9], a blended "recall ≥80%" over Semgrep+LLM is not credible without decomposition.

→ *Recommendation: keep O3's stated target but report it decomposed — Semgrep layer and LLM layer separately (PRC §3.6 already asks for this), label it **recall on injected patterns**, and add an explicit statement of the known CE limitation.* Do **not** silently lower the target; take the redefinition to the guide.

**Finding 30 — The PRC evaluation plan is structurally sound. [INF]**
Its strengths, which I recommend keeping verbatim: per-layer precision reporting; comparison against the wrapped tool as ground truth by construction (M4); seeded bugs for recall; injected cases for drift; manual review with stated sample sizes; "report as measured numbers"; and a regression test for score stability. The gaps are G6/G7/G10 above plus: a documented precision-sampling protocol (sample size, rater count, rubric, second-pass check), and a cost metric (LLM calls/tokens per run — already listed in §3.6, keep it).

**Finding 31 — Baselines are what prove "one platform, not six tools." [INF]**
The PRC's narrative promises platform-level value but its evaluation is per-module. Add three ablations: (a) M1 without retrieval (long-context only); (b) M2 Semgrep-only, no LLM layer; (c) M7 with M5/M6 removed. Each directly demonstrates a cross-module claim and directly answers anticipated jury Q2 ("if Semgrep and OSV-Scanner already exist, what is your contribution?").

## 3.9 Unverified items (explicitly flagged, not presented as fact)

| Item | Status |
|---|---|
| "Software Composition Analysis for Vulnerability Detection: An Empirical Study on Java Projects", ESEC/FSE 2023 (PRC ref #3) | Title/venue consistent with the PRC citation and appears in ACM DL reference listings, but **not opened or verified this session** |
| SecVulEval | Seen only as a citation inside arXiv 2603.13384; **not verified directly** |
| CodeFuse-CR-Bench, SWR-Bench | Referenced inside AACR-Bench; **not opened directly** |
| CodeReviewer dataset license on Zenodo | **Not verified** |
| GraphCoder ACM venue (DOI 10.1145/3691620.3695054) | arXiv version verified; **venue name not confirmed** |
| ContextCRBench arXiv identifier | Identifier seen in search output is **not fully confirmed — re-check before citing** |
| SWE-PRBench, Martian Code Review Benchmark, Bigger Isn't Always Better | **Titles/abstracts seen; full bibliographic records not verified** |
| BigQuery GitHub dataset, GH Archive | Known to exist; **not investigated**. Recommended against regardless (see §4) |
| A vendor-blog claim that `nomic-embed-text` beat Jina v3 and BGE-M3 | Found, but **vendor-published and on a 451-chunk corpus — treated as low-confidence and not used** |

---

---

# 4. Dataset / Data Source Inventory

Types are labelled honestly: **DS** dataset · **VDB** vulnerability database · **BM** benchmark · **RS** repository source · **API** · **TOOL**.

| Dataset / Source | Type | Purpose | Language | Size | Labels | Access | License | Sentra Module | Recommended Usage |
|---|---|---|---|---|---|---|---|---|---|
| **OSV.dev** | **VDB** | Vulnerability data for M4 | npm 229k, PyPI 25k, Ubuntu 66k, Wolfi 291k, Debian/RHEL/SUSE/Rocky, RubyGems 5k, Packagist 7k, OSS-Fuzz 4k | ~600k+ live entries | CVE/GHSA/OSV ids, CVSS v3/v4 severity, affected ranges, fixed versions | API, **no key** | Open (per-source) | **M4, M5, M7** | **Primary dependency source. Query in bulk, snapshot for reproducibility** |
| **OSV-Scanner v2.6.0** | **TOOL** | Lockfile scanning | 11+ ecosystems, 19+ lockfile types | n/a | n/a (produces OSV findings) | Binary / `go install`, **Apache-2.0** | Apache-2.0 | **M4** | **Wrap as subprocess. Use `--offline` + downloaded DB for demos and reproducible evaluation** |
| **github/advisory-database (GHSA)** | **VDB** | Reviewed advisories incl. PyPI/npm | Python, JS/TS, Go, Java… | Large | GHSA + CVE aliases + CVSS | Public repo | Open | M4 | Cross-reference; source of `fix` commits for drift scenarios |
| **NVD API 2.0** | **API** | Vulnerability data | Universal | ~300k CVEs | CPE-matched | **Key required for usable rate: 5 req/30 s bare, 50 req/30 s keyed** | US Gov (public domain) | M4 (optional) | **Do not use as primary.** Cite the rate limits as the justification |
| **SWE-QA** | **BM + RS** | Repository-level code QA; 15 pinned Python repos (13.3k files / 142k funcs / 3.4M LOC) | **Python** | 720 QA pairs, 48/repo | Human-curated questions; reviewed reference answers | HF `swe-qa/SWE-QA-Benchmark`, <https://github.com/peng-weihan/SWE-QA-Bench> | **Apache-2.0** | **M1, M9** | **Highest-value external asset.** Use as a *validation set* for retrieval + answer quality, and its 15 repos as an evaluation repository pool |
| **SWE-bench Verified** | **BM + RS** | 500 human-validated tasks over 12 popular Python repos, with `base_commit`, `patch`, `test_patch` | **Python** | 500 tasks / 12 repos | Human-validated | HF / GitHub mirror | MIT | **RS**, M2, M5, M6 | **Repository source with pinned commits and real fix diffs.** Task type (patch generation) is out of scope — do not present as a Sentra benchmark |
| **BugsInPy** | **BM + RS** | 493 real Python bugs, 17 projects >10k stars; buggy+fixed versions | **Python** | 493 bugs / 17 repos | Real, reproducible (67% unmodified per independent study) | <https://github.com/soarsmu/bugsinpy> | Project-specific (OSS) | **M2, M6, RS** | **Source of realistic bug-fix commit pairs and 17 real Python repos.** Never as a detection ground truth (it is repair-oriented) |
| **Defects4J** | **BM + RS** | 854 active bugs, 9 Java projects, triggering tests | **Java** | 854 bugs | Real, reproducible | <https://github.com/rjust/defects4j> | Project-specific | M2 (stretch) | Only if Java enters scope |
| **Juliet C/C++ 1.3** | **BM** | Static-analyzer discrimination test, 118 CWEs, flawed + non-flawed variants | **C/C++** | **64,099** cases | Exact CWE | NIST SARD #112 | **Public domain / CC0 1.0** | M2 (tool validation) | Optional Semgrep-engine sanity benchmark. **Requires adding C/C++ to scope — not recommended** |
| **PrimeVul** | **DS + BM** | Vulnerability-detection labels with **86–92% accuracy**, chronological splits | **C/C++** | 6,968 vuln / 228,800 benign, 140+ CWE | High-quality hybrid | <https://github.com/DLVulDet/PrimeVul> | **MIT** | **M2, M9 (evidence)** | **Do not use as data. Cite as the label-noise / overestimation reference** |
| **DiverseVul / BigVul / Devign / CVEfixes / CrossVul / ReVeal / CleanVul / SafeCoder** | **DS** | Function-level vuln datasets | **C/C++** | Various | Automatic, 25–60% accurate | Public | Mixed | Citation only | **Do not adopt.** Cite OOD-Out-of-Luck for duplication and NVD-CWE-match rates |
| **OSS-Fuzz / oss-fuzz-vulns** | **VDB + RS** | 13,000+ vulns / 50,000 bugs / 1,000 projects; **precise introduced/fixed commit ranges**; already in OSV | C/C++, Rust, Go, Python, Java, JS, Lua | Large | Real, verified | <https://github.com/google/oss-fuzz-vulns> | **CC-BY-4.0** | M4, M5, M6 | **Real fix commits for drift/PR scenarios; OSV completeness cross-check** |
| **CrossCodeEval** | **BM + RS** | Cross-file code completion **and** a code-retrieval benchmark; repos are **permissively licensed** | Python, Java, TS, C# | Multi-repo | Static-analysis-derived cross-file needs | <https://crosscodeeval.github.io/> | Repo-permissive | **M1, M2, M9** | **Repo pool (licensing matters for redistribution); its static-analysis cross-file-detection trick can generate retrieval test cases cheaply** |
| **RepoQA** | **BM** | Long-context code search; 500 tasks, 50 repos, 5 langs | py/cpp/rs/java/ts | 500 tasks | Known needle function | <https://github.com/evalplus/repoqa> | **Apache-2.0** | M1, M9 | Retrieval ablation; repo source; long-context-vs-RAG contrast |
| **RepoBench / RepoEval** | **BM + RS** | Repo-level retrieval & completion; 20-repo list published | Python, Java | 3 tasks (R/C/P) | Unit-test-validated | <https://github.com/Leolty/repobench> | CC-BY-4.0 (repo) | M1, M9 | Retrieval metrics (EM/ES/CodeBLEU); GraphCoder's repo list is a useful source pool |
| **CodeSearchNet** | **DS** | 2M (docstring, function) pairs; **99 hand-annotated queries** for NDCG | Python, JS, Go, Java, PHP, Ruby | 2M pairs; **~20 GB** processed | Function comments | S3 / Zenodo (10.5281/zenodo.7908468) | **MIT for code; per-repo licenses in `licenses.pkl`; HF mirror states example-wise license info is NOT included** | M1 (D1 evidence) | **Use only the 99-query annotated set for cheap embedding comparison. Do NOT download the 20 GB corpus — we do not train models** |
| **SWRBench** | **BM** | 1,000 real PRs, 12 popular Python repos, **500 issue / 500 clean** | **Python** | 1,000 PRs | Reviewer-confirmed + clean | <https://github.com/ZZR0/SWRench> | **MIT** | **M5, M9** | **Primary external PR-review benchmark.** Also a source of 12 permissively-licensed Python repos |
| **AACR-Bench** | **BM** | 200 PRs / 50 repos / 10 langs, expert-verified, context-level annotations | 10 languages | 200 PRs (README lists 2,145 comments; paper HTML says 1,505 — **discrepancy, cite cautiously**) | Expert-augmented | <https://github.com/alibaba/aacr-bench> | **Apache-2.0** | M5 | Secondary cross-language comparison; prompt-design guidance |
| **ContextCRBench** | **BM** | Fine-grained review with issue text + PR description + before/after code | Multi | 153.7k crawled | Real | arXiv (**identifier to re-verify**) | Unknown | M5 (design) | **Use its finding, not its data:** textual context matters more than code context |
| **CodeReviewer** | **DS** | Diff↔comment pairs, 9 languages | 9 langs | Large | Real comments | Zenodo (**license unverified**) | Unverified | M5 (background) | Background citation only |
| **PRTiger / PRSummarizer / T5-PR-desc** | **DS** | PR title/description **generation** corpora | Multi / Java | 43,816 / 41k / 33,466 | Real | Public | Mixed | M5 (background) | Background for summarization; **ROUGE is not our metric** |
| **BigQuery GitHub dataset / GH Archive** | **DS** | Bulk GitHub code/events | All | Very large | None | Google Cloud (billed) | GitHub ToS | — | **Recommended against.** Volume, cost, ToS risk, and zero benefit — we need *curated repos*, not a corpus. **Not investigated this session** |
| **dfbench** | **BM** | Expert-reviewed real vulnerabilities | C/C++ lineage | 253 examples | Expert | **Scored examples private** | Proprietary | — | **Unusable** — verified to exist, deliberately withheld |

**Explicit recommendation [INF]:** Sentra should download **no large dataset.** It needs (1) 2–3 demo repos, (2) 3–5 evaluation repos, (3) 1–2 development repos — **6 to 10 repositories total** — plus four small hand-built artifact sets (questions, seeded bugs, injected drift, labeled PRs). The 20 GB CodeSearchNet corpus and BigQuery-scale sources would cost time and buy nothing, because Sentra trains nothing.

---

# 5. Research Paper Inventory (focused)

Ordered by Sentra relevance. Verification status noted.

| # | Title | Authors | Year | Venue | Problem addressed | What Sentra learns | Module | Link |
|---|---|---|---|---|---|---|---|---|
| 1 | RepoCoder: Repository-Level Code Completion Through Iterative Retrieval and Generation | Zhang, Chen, Zhang, Keung, Liu, Zan, Mao, Lou, Chen | 2023 | **EMNLP 2023**, pp. 2471–2484 | Repository context is scattered across files; in-file completion misses it | Retrieval-augmented repo-level context beats in-file by >10%; iterative retrieve→generate beats one-shot RAG. Our cited anchor | **M1** | [aclanthology](https://aclanthology.org/2023.emnlp-main.151/) · [arXiv 2303.12570](https://arxiv.org/abs/2303.12570) |
| 2 | Enhancing Static Analysis for Practical Bug Detection: An LLM-Integrated Approach (**LLift**) | Li, Hao, Zhai, Qian | 2024 | **PACMPL 8, OOPSLA1, Art. 111**, 474–499 | Static analysis precision degrades on large, intricate codebases | Static analysis + LLM > either alone; found 4 novel Linux-kernel bugs. **But it augments *path-sensitive* analysis — a sibling of our M2, not the same design. State the difference.** | **M2** | [doi 10.1145/3649828](https://dl.acm.org/doi/10.1145/3649828) · [PDF](https://www.cs.ucr.edu/~zhiyunq/pub/oopsla24_llift.pdf) |
| 3 | Software Composition Analysis for Vulnerability Detection: An Empirical Study on Java Projects | — | 2023 | **ESEC/FSE 2023** | SCA accuracy depends on dependency resolution and data source; tools FP and FN | Supports using an authoritative DB and **stating scanner limits**. **Bibliographic record UNVERIFIED this session** | **M4** | *Verify before citing* |
| 4 | GraphCoder: Enhancing Repository-Level Code Completion via Code Context Graph-based Retrieval | Liu, Yu, Zan, Shen, Zhang, Zhao, Jin, Wang | 2024 | arXiv (ACM DOI 10.1145/3691620.3695054; venue unconfirmed) | Sequence-based retrieval misses structurally relevant context | Code context graph + coarse-to-fine retrieval: +6.06 code match, +6.23 identifier match on 8,000 tasks / 20 repos. **Also calibrates expectations: graph gains are single-digit points** | **M1** | [arXiv 2406.07003](https://arxiv.org/abs/2406.07003) |
| 5 | RepoBench: Benchmarking Repository-Level Code Auto-Completion Systems | Liu, Xu, McAuley | 2024 | **ICLR 2024** | Benchmarks are single-file; no repo-level retrieval measurement | Decompose into **R**etrieval / **C**ompletion / **P**ipeline → measure retrieval separately. Ships 20-repo list | **M1, M9** | [arXiv 2306.03091](https://arxiv.org/abs/2306.03091) · [github](https://github.com/Leolty/repobench) |
| 6 | CrossCodeEval: A Multilingual Cross-File Code Completion Benchmark | Ding et al. | 2023 | **NeurIPS 2023** | Cross-file context is required but unmeasured | Static-analysis trick (blank imports → find undefined names) **cheaply generates cross-file retrieval test cases**; permissively-licensed repo pool; doubles as retrieval benchmark | **M1, M2, M9** | [crosscodeeval.github.io](https://crosscodeeval.github.io/) |
| 7 | RepoQA: Evaluating Long Context Code Understanding | Liu, Tian, Daita, Wei, Ding, Wang, Yang, Zhang | 2024 | arXiv | Long-context code understanding is unevaluated | Models still fail code search in long contexts; use as the **long-context baseline** in our M1 ablation | **M1, M9** | [arXiv 2406.06025](https://arxiv.org/abs/2406.06025) |
| 8 | SWE-QA: Can Language Models Answer Repository-level Code Questions? | Peng, Shi, Wang, Zhang, Shen, Gu | 2026 | **ACL 2026 Findings** | No benchmark for realistic repo-level QA | 720 QA pairs / 15 pinned Python repos / 3.4M LOC, with RAG + agent baselines and a judge scorer → **directly reusable M1 evaluation harness and repo pool** | **M1, M9** | [arXiv 2509.14635](https://arxiv.org/pdf/2509.14635) · [github](https://github.com/peng-weihan/SWE-QA-Bench) |
| 9 | Vulnerability Detection with Code Language Models: How Far Are We? (**PrimeVul**) | Wang et al. | 2025 | **ICSE 2025** (DOI 10.1109/ICSE55347.2025.00038) | Existing benchmarks wildly overestimate vulnerability detection | Label accuracy table (SVEN 94%, CodeXGLUE 24%, BigVul 25%, DiverseVul 60%, PrimeVul 86–92%); a 7B model scores **68.26% F1 on BigVul but 3.09% on PrimeVul**. **The central honesty citation for our O3 reporting** | **M2, M9** | [github DLVulDet/PrimeVul](https://github.com/DLVulDet/PrimeVul) · [ACM](https://dl.acm.org/doi/10.1109/ICSE55347.2025.00038) |
| 10 | DiverseVul: A New Vulnerable Source Code Dataset | Chen, Ding, Alowain, Chen, Wagner | 2023 | **RAID 2023** | Prior datasets are narrow; label noise is high | 18,945 vuln / 330,492 benign, 795 projects, 150 CWEs; also concludes deep learning "is still not ready for vulnerability detection" | **M2 (context)** | [arXiv 2304.00409](https://arxiv.org/abs/2304.00409) |
| 11 | Out of Distribution, Out of Luck: How Well Can LLMs Trained on Vulnerability Datasets Detect Top 25 CWE Weaknesses? | — | 2026 | arXiv | Cross-dataset duplication and distribution bias | 71.1% of PrimeVul ⊂ DiverseVul; PrimeVul∩CVEfixes 28.4%; NVD CWE match only 43–75%. Proves dataset selection is not trivial | **M2, M9** | [arXiv 2507.21817](https://arxiv.org/pdf/2507.21817) |
| 12 | BugsInPy: a database of existing bugs in Python programs | Widyasari, Hager, Kamei, Stewart, Pradel, Scott, Monperrus | 2020 | **ESEC/FSE 2020** | No Defects4J-class Python bug benchmark | 493 real bugs / 17 >10k-star projects, hand-curated, 831 person-hours. **Independent study: only 67% reproducible unmodified** — report this | **M2, M6, RS** | [arXiv 2401.15481](https://arxiv.org/abs/2401.15481) · [github](https://github.com/soarsmu/bugsinpy) |
| 13 | Defects4J: A Database of Existing Faults | Ernst, Holmes, Fraser | 2014 | **ISSTA 2014** | Java fault benchmark | 854 active bugs / 9 projects with triggering tests — the quality bar BugsInPy aimed at | **M2 (stretch)** | [github](https://github.com/rjust/defects4j) |
| 14 | Ragas: Automated Evaluation of Retrieval Augmented Generation | Es, James, Espinosa-Anke, Schockaert | 2023 | arXiv (EACL 2024 Demo) | RAG lacks reproducible, ground-truth-free metrics | Definitions for faithfulness / answer relevancy / context relevancy; human agreement **0.95 / 0.78 / 0.70**. Adopt as our metric vocabulary | **M1, M9** | [arXiv 2309.15217](https://arxiv.org/html/2309.15217) |
| 15 | Correctness is not Faithfulness in RAG Attributions | — | 2024 | arXiv | Citation correctness and citation faithfulness are conflated | **Up to 57% of citations are post-rationalized.** Requires two separate citation metrics. **Directly shapes FR3/O1** | **M1, M9** | [arXiv 2412.18004](https://arxiv.org/pdf/2412.18004) |
| 16 | CodeReviewer: Pre-Training for Automating Code Review Activities | Li, Lu, Sun, Jiang, Liu, Zhang | 2022 | **ESEC/FSE 2022** | Review automation lacked a large pretrained model | 9-language diff↔comment corpus with **project-level splits to prevent leakage** — a leakage-avoidance precedent we should copy | **M5, M9** | [arXiv 2203.09095](https://arxiv.org/pdf/2203.09095) · [github](https://github.com/microsoft/CodeBERT/tree/master/CodeReviewer) |
| 17 | Benchmarking LLMs for Fine-Grained Code Review with Enriched Context in Practice (**ContextCRBench**) | — | 2025 | arXiv (**identifier to re-verify**) | Review benchmarks lack issue/PR semantic context | Current LLMs fall short of reliable automated review; **textual context helps more than code context** → M5 must read the PR description and linked issue | **M5** | arXiv (verify id before citing) |
| 18 | AACR-Bench: Evaluating Automatic Code Review with Holistic Repository-Level Context | Alibaba | 2026 | arXiv 2601.19494 | Review benchmarks are single-diff and single-language | 200 PRs / 50 repos / 10 langs, expert-verified, diff/file/repo **context-level annotations** | **M5** | [arXiv 2601.19494](https://arxiv.org/html/2601.19494v1) · [github](https://github.com/alibaba/aacr-bench) |
| 19 | Detecting Outdated Code Element References in Software Projects | Tan, Wagner, Treude | 2022 | arXiv | Docs reference code elements that no longer exist | **>25% of the top-1000 GitHub projects contain ≥1 outdated code reference** → our strongest motivation evidence | **M6** | [arXiv 2212.01479](https://arxiv.org/abs/2212.01479) |
| 20 | Wait, wasn't that code here before? Detecting Outdated Software Documentation | Tan, Wagner, Treude | 2023 | arXiv | Detecting drift must be routine, not manual | Same approach as a PR-triggered GitHub Action — cite as prior art | **M6** | [arXiv 2307.04291](https://arxiv.org/abs/2307.04291) |
| 21 | A Review on Detecting and Managing Documentation Drift in Software | Mohamed | 2025 | IEEE (doc 11196773) | Fragmented literature on drift | Confirms no dominant method or benchmark exists → justifies treating M6 as research and **constructing its evaluation** | **M6, M9** | [ieeexplore](https://ieeexplore.ieee.org/document/11196773) |
| 22 | Automatically Inspecting Thousands of Static Bug Warnings with LLM (**Llm4sa**) | — | 2024 | **ACM TKDD** (DOI 10.1145/3653718) | Human triage of static warnings does not scale | LLM consumes **only the analyzer's output** — complementary by construction, low integration risk | **M2** | [dl.acm.org](https://dl.acm.org/doi/10.1145/3653718) |
| 23 | Minimizing False Positives in Static Bug Detection via LLM-Enhanced Path Feasibility Analysis (**LLM4PFA**) | Du, Yu, Wang, Zou, Deng, Ou, Peng, Zhang, Lou | 2025 | arXiv | Static analyzers FP heavily on infeasible paths | Filters **72–96% of FPs**, misses **3 of 45** TPs. Concrete evidence that the LLM layer's measurable value is **noise reduction** | **M2** | [arXiv 2506.10322](https://arxiv.org/abs/2506.10322) |
| 24 | KNighter: Transforming Static Analysis with LLM-Synthesized Checkers | — | 2025 | arXiv | Scaling LLM static analysis to whole codebases | Generate checkers from **historical patch commits**; 70 novel kernel bugs, 56 confirmed, 11 CVEs. A credible future extension for us | **M2 (future)** | [arXiv 2503.09002](https://arxiv.org/html/2503.09002v1) |
| 25 | Retrieval-Augmented Code Generation: A Survey with Focus on Repository-Level Approaches | Tao, Li, Qin, Liu | 2025–26 | arXiv 2510.04905 (CC BY 4.0) | Field needed a unifying taxonomy | Frames retrieval substrate / control regime / evaluation setting; catalogues benchmarks and the RACG-vs-long-context boundary → **our Section 3 framing citation** | **All** | [arXiv 2510.04905](https://arxiv.org/abs/2510.04905) |
| 26 | An Empirical Study of OSS-Fuzz Bugs | Ding, Le Goues | 2021 | **MSR 2021** (DOI 10.1109/MSR52588.2021.00026) | Characterize 23,907 fuzzer-found bugs / 316 projects | Fuzzer bugs are often unfixed/timeout-dominated; only **98 of 20,000+ ever got a CVE** → why CVE-only ground truth is incomplete | **M2, M4** | [computer.org](https://www.computer.org/csdl/proceedings-article/msr/2021/871000a131/1tB7jeDBsQM) |
| 27 | A comparative study of vulnerability reporting by software composition analysis tools | — | 2021 | **ESEM 2021** (DOI 10.1145/3475716.3475769) | Tools report the same vulnerability differently | Justifies stating SCA limits rather than claiming superiority | **M4, M9** | [dl.acm.org](https://dl.acm.org/doi/10.1145/3475716.3475769) |
| 28 | Towards a Benchmark for Dependency Decision-Making (**DepDec-Bench**) | — | 2026 | arXiv 2601.00205 | Dependency risk introduced by PRs is unmeasured | 117,062 dependency changes; agents introduce vulnerable deps at **2.5%** vs humans **1.6%** → published evidence that **M5's dependency cross-reference is worth building** | **M5** | [arXiv 2601.00205](https://arxiv.org/pdf/2601.00205) |

---

# 6. Existing Tools / Systems — what Sentra reuses, combines, and deliberately does not attempt

No ranking. Organised by role.

| System | What it does | What Sentra reuses | What Sentra combines | What Sentra deliberately does **not** attempt |
|---|---|---|---|---|
| **AI coding assistants** (GitHub Copilot; also Cursor / Claude Code class) | In-editor, stateless, context-window-bounded code completion and chat for one developer | The framing contrast from Spec §1.3: *Copilot helps write the next line; Sentra tells you whether the codebase is trustworthy* | Nothing technically — Sentra **sits beside** them | Code generation, autocomplete, inline edits, agentic refactors. This is the project's defining boundary |
| **Semgrep CE** | Pattern-matching static analysis, 30+ languages, 2,000+ registry rules, LGPL-2.1 engine, **single-function scope** | The **entire deterministic layer of M2**, run as a subprocess; normalized into the findings schema | Its findings feed (a) the LLM review layer, (b) the findings store, (c) M5 cross-reference, (d) M7 score | Cross-file/interfile dataflow (CE cannot), and the Pro rule set. **We must state the single-function ceiling** |
| **Semgrep Rules License v1.0** | Semgrep-maintained rules are internal-business-use only; third-party rules carry their own licenses | The right to *run* Semgrep locally for a research project | — | **Redistributing Semgrep-maintained rules, or shipping a hosted scanning service built on them.** Record which rulesets we use and their licenses |
| **CodeQL** | Semantic query-based analysis; deep cross-file reasoning; libraries/queries MIT, CLI separately licensed; **requires compilation databases** | Nothing in the current scope | — | Adopting it would require **building** analyzed code → violates "read/parsed, never executed or built." Its build requirement is the correct, citable rejection reason |
| **SonarQube / Advanced Security** | Commercial unified code-security platform: SAST + SCA + cross-file taint + IaC + secrets; **AI CodeFix generates fixes** (Enterprise/DC only) | The **market/UX reference point** a jury will name. Their cross-file taint approach shows the ceiling we are not reaching | — | Its auto-fix direction is exactly our prohibited behaviour. Also its commercial licensing is out of scope for an academic project |
| **GitHub Advanced Security / Dependabot** | Code scanning (CodeQL or third-party), secret scanning (free on public repos), dependency review | The prior art for "one place for code security" — and the free tier is narrow | — | Hosting, org/team policy, billing tiers, CI enforcement gates |
| **OSV.dev** | Open vulnerability DB aggregating many ecosystems; **no API key**; CVSS v3/v4 severity, affected ranges, fixed versions | **All of M4's vulnerability data.** No custom dataset needed | OSV data → findings schema → M7 caps; plus OSS-Fuzz ranges for drift scenarios | Authoring our own vulnerability corpus — the doc is right that an authoritative source already solves this |
| **OSV-Scanner** | Official CLI over OSV; 11+ ecosystems / 19+ lockfile types; optional reachability call analysis; **offline mode**; deps.dev license scanning | **M4's implementation.** Wrapped as a subprocess; also the **ground-truth oracle** for O4 | Its output → our findings schema; its offline DB → reproducible demos | The experimental `fix` (guided remediation) — automatic remediation is prohibited |
| **Tree-sitter** | Incremental parser generator; MIT; official grammars incl. Python, JavaScript, TypeScript, Java, Go, C/C++…; Python/Rust/Node bindings | **The whole chunking layer** of the shared core, as the documents specify | Its parse trees → chunks → embeddings → retrieval for *all* modules | Language-specific AST libraries (rejected in the doc), regex splitting, fixed-size chunks (both worse for citations) |
| **LightRAG** (HKUDS) | Graph-augmented RAG; MIT; EMNLP 2025; **4 storage backends, 4 LLM roles, LLM-heavy entity-relation extraction, vector dim fixed at table creation, no re-embedding tool** | The **candidate** retrieval framework for M1, with a **pre-approved custom-retrieval fallback** | Its graph layer with our chunks; its citation support (added 2025.03) | We do **not** adopt it blindly — Spike S4/S5 must show the graph layer earns its LLM cost. **Must decide whether its store becomes a second source of truth alongside our `chunks`** |
| **pgvector / Postgres** | Vector similarity in Postgres; one DB for vectors + metadata + findings | The **single-database** decision from PRC §2.9 | Vectors, chunks, findings, score history in one place → simple joins and transactions | A dedicated vector DB or graph DB — unnecessary at single-developer scale, adds operational cost |
| **Hybrid SAST+LLM research systems** (LLift, Llm4sa, LLM4PFA, KNighter) | LLM integrated into static analysis: path-feasibility filtering, warning triage, checker synthesis | The **published justification** for M2's two-layer design, cited honestly with the architectural difference stated | Semgrep as the deterministic base instead of a path-sensitive analyzer | Checker synthesis (KNighter) and path-sensitive analysis (LLift) are **future work** |
| **Drift tools** (docgap, doc-drift, VS Code Drift, Docs-Drift) | Hash/timestamp + AST-signature + embedding-similarity drift detection; one uses a documented **0.75 cosine threshold** | **Honest prior art citation** — our method is a competent synthesis of known techniques | Their signals on top of Module 1's existing embeddings, unified into the score | Claiming novelty. **Our M6 contribution is integration + the first published evaluation, not the method** |
| **Review benchmarks** (SWRBench, AACR-Bench, CodeReviewer) | PR review datasets with real labels | A labelled PR sample and mature evaluation designs for M5 | Their labels + our cross-reference logic | Fine-tuning on them (prohibited) |

---

# 7. Project Roadmap — milestone-driven

## Naming note [INF]
The project brief sketched phases as `M0…M9` while our modules are `M1, M2, M4, M5, M6, M7`. I rename phases **P0…P9** to eliminate collision. Modules keep their documented numbers.

## Deviations from the documented four-month plan — declared for approval

| # | Documented plan | Refined plan | Reason | Risk if rejected |
|---|---|---|---|---|
| DV1 | Month 2 = M2 + M4 | **M4 lands in Month 2, M2 moves to Month 3** | M4 is deterministic, needs no LLM, and is the cheapest way to harden the *common findings schema* before two LLM modules depend on it. Research confirms OSV/Scanner risk is low [EXT §3.5] | Low — sequence changes, scope identical |
| DV2 | Month 1 = core + M1 complete | **Month 1 = core complete; M1 completes in Month 2 W7–W8** | Research shows the core has real unknowns (LightRAG cost, embedding choice, chunking granularity). Finishing the core properly before M1 avoids rework | Medium — a 2-week shift of the M1 milestone |
| DV3 | Month 3 = M5 then M6 | **Month 3 = M5; M6 first in Month 4** | Preserves the documented cut order: M6 is the first cut, so scheduling it last makes cutting it cheapest | Low |
| DV4 | Month 4 = M7 + dashboard polish + demo | **Month 4 = M6 → M7 → dashboard completion → full evaluation → demo + docs** | Evaluation, report writing and rehearsal need dedicated days; "polish" is not a plan | Medium — but this is the honest requirement |
| DV5 | 4 months | **18-week plan with P0 (research + 8 spikes) as a real phase** | The PRC §4.3 already prescribes a feasibility spike because no code exists. Treating that as day one is faithful to the documents | Low — it *is* the documented plan, made explicit |

---

## Phase P0 — Research, Feasibility & Decision Lock

**Goal** — Convert the document's assumptions into measured evidence, and lock every decision in §8 with a deadline. Produce the feasibility evidence pack the PRC §4.3 already requires.

**Problem solved** — Prevents weeks of architecture built on an untested assumption.

**Inputs** — `Sentra_Project_Specification(1).docx`, `PRC2_Review_Content.docx`; demo/eval repo candidates; tool installs (Tree-sitter, Semgrep CE, OSV-Scanner, Postgres+pgvector, Ollama or API access, GitHub PAT).

**Outputs** — Feasibility evidence pack (8 spike outputs + saved screenshots/outputs); static mockup of the readiness overview; demo repo shortlist with URLs/commits/licenses/LOC; decision log with every §8 decision resolved or explicitly deferred.

**Technical components** — Spike scripts only. **No application code.**

**Research dependencies** — None. Everything in P0 *is* the research.

**Datasets / test data** — 1–2 candidate demo repos + 1 known-lockfile repo with real vulnerabilities.

**Depends on** — Nothing.

**Acceptance criteria**
1. Tree-sitter extracts chunks with real line ranges from a real repo, and line ranges verified by hand on 10 samples.
2. Semgrep CE runs on a real repo and produces parseable, reproducible JSON output; false-positive rate observed on a 50-finding hand sample.
3. OSV-Scanner finds ≥1 real known-vulnerable dependency in a real lockfile; offline mode verified; output matches a direct OSV API query.
4. Retrieval over a real repo returns semantically correct top-k on a 20-query hand-labeled set for ≥2 candidate embedding models; a winner and a dimension are recorded.
5. LLM calls-per-chunk measured for M1 docs **with and without** the graph layer; cost/latency recorded.
6. Drift: ≥5 injected drift cases detected; hash-only vs hash+embedding compared; threshold proposed with data.
7. LLM bug review: ≥30 findings hand-labeled; precision measured per layer; threshold proposed.
8. PR: one real PR fetched, summarized, and cross-referenced; rubric drafted.
9. Every decision in §8 has an owner, an evidence link, and a deadline.

**Demo artifact** — The feasibility evidence pack and the readiness-overview mockup (exactly what PRC §4.3 asks for). **This alone can carry a review meeting.**

**Evaluation** — Pass/fail per criterion above; measured numbers recorded in the evidence pack.

**Risks** — Spikes eat time (mitigation: hard cap of ~10 working days); a demo repo lacks findings (mitigation: shortlist 5, pick the one with the richest findings).

**Fallback** — If LightRAG is too costly in spike 5, fall back to custom vector retrieval — **already pre-approved in the documents** — and record the substitution honestly.

---

## Phase P1 — Ingestion Foundation

**Goal** — A repository can be registered, cloned, change-detected and stored; ingestion is incremental; the platform is configurable and secret-safe.

**Problem solved** — "I have no single coherent model of this repository."

**Inputs** — GitHub URL or local path; a GitHub PAT; the decisions locked in P0.

**Outputs** — Repo registration; commit recorded; per-file content hashes; incremental re-ingest that reprocesses **only** changed files and prunes deleted ones; config file for thresholds/weights/providers; env-based secrets; minimal API (`POST /repos`, `GET /repos/{id}/status`) and a minimal repo-list + status screen.

**Technical components** — Git client, intake worker, change detector, configuration layer, migration/DB bootstrap, baseline API + thin UI.

**Research dependencies** — P0 spikes 1–3 (chunking + change-detection feasibility).

**Datasets / test data** — A throwaway development repo with 2 branches so a commit can be simulated.

**Depends on** — P0.

**Acceptance criteria**
- (1) Register a repo → status shows last indexed commit.
- (2) Make a commit that changes 1 of 400 files → re-ingest touches exactly that file and its chunks.
- (3) Delete a file → its chunks are removed.
- (4) No secret appears in the DB or repo; validated by inspection.
- (5) Ingestion progress is observable.
- (6) **No analyzed code is executed or built at any point** — verified by inspection.

**Demo artifact** — Register a repo, watch the status update, see incremental behaviour.

**Evaluation** — Count of files reprocessed per commit; wall-clock for full vs incremental ingest.

**Risks** — Ingestion strategy (in-process vs worker) is undecided → resolve in P0; long runs with no progress UI.

**Fallback** — Synchronous ingest with a progress endpoint instead of a background queue.

---

## Phase P2 — Repository Knowledge Core

**Goal** — Parse → chunk → embed → store → retrieve working end to end, with citations pointing at real lines. **No LLM yet.**

**Problem solved** — "Can I find the right code in this repository?"

**Inputs** — Stored files from P1.

**Outputs** — Chunks with `kind/name/start_line/end_line/content_hash/commit_hash/language`; embeddings with `model_name`; pgvector index; a top-k retrieval API returning file + line range; retrieval quality measured.

**Technical components** — Tree-sitter walker, chunker (incl. oversized/nested-chunk policy), embedder abstraction, vector store + index, retrieval service.

**Research dependencies** — P0 spike 4 (embedding comparison).

**Datasets / test data** — 20 hand-labeled natural-language → expected file/line queries; optionally RepoQA (Apache-2.0) for an external check.

**Depends on** — P1.

**Acceptance criteria**
- (1) Every chunk's `start_line`/`end_line` match the actual source, verified on 50 samples.
- (2) Top-k retrieval returns a chunk containing the expected line for ≥80% of the 20 hand-labeled queries; **and we report Recall@k and nDCG@k separately.**
- (3) An embedding model + dimension is recorded in config and stamped on every embedding row.
- (4) Deleting/renaming a function removes or updates its chunk.

**Demo artifact** — "Here are the top-5 relevant code regions for *your question*, with file:line." (No answers yet — deliberately.)

**Evaluation** — Recall@k, MRR/nDCG@k on the hand set; optionally corroborated on RepoQA.

**Risks** — Chunk granularity choice (function vs class vs hybrid) materially changes retrieval and citation quality; oversized functions need splitting.

**Fallback** — Config-driven chunker with both function-level and hybrid strategies so we can switch without a rewrite.

---

## Phase P3 — Dependency Risk Analysis (Module 4)

**Goal** — Real dependency risk, from an authoritative database, normalized into the common findings schema.

**Problem solved** — "Is there a known CVE in my third-party packages, and is it fixed?"

**Inputs** — Lockfiles from P1; OSV network or offline DB; OSV-Scanner binary.

**Outputs** — Findings with identifier (CVE/GHSA/OSV), derived severity, affected range, fixed version, ecosystem, lockfile path; a dependency risk view; **the hardened common findings schema**.

**Technical components** — OSV-Scanner subprocess wrapper (JSON output), OSV API client, severity normalizer, affected-range/fixed-version resolver, findings writer, dependency screen.

**Research dependencies** — P0 spike 3.

**Datasets / test data** — Lockfiles from the candidate repos; a lockfile with a *deliberately pinned* known-vulnerable version (from an OSV advisory) to guarantee a finding in the demo.

**Depends on** — P1 (for files/commits). Independent of P2's retrieval.

**Acceptance criteria**
- (1) Module output's affected package@version set is **identical** to a direct `osv-scanner scan source -r` run on the same lockfiles at the same DB snapshot, on all candidate repos.
- (2) Every finding carries identifier, derived severity, affected range, fixed version.
- (3) Severity derivation is a documented, deterministic function of CVSS (or `database_specific.severity`), with an explicit policy for records carrying neither.
- (4) Offline mode reproduces identical output with no network.
- (5) `findings` rows are byte-identical across two consecutive runs (reproducibility).

**Demo artifact** — A dependency table with a real CVE, the fixed version, and a link to the public advisory. **Zero persuasion needed** — the single most credible module.

**Evaluation** — The O4 agreement metric (precisely scoped, §3.5 Finding 20); plus offline-vs-online output equality.

**Risks** — Severity semantics differ per source; OSV "fix_not_planned" or no-fix cases must be represented honestly.

**Fallback** — Direct OSV API only, if subprocess integration proves brittle.

---

## Phase P4 — Codebase Understanding (Module 1)

**Goal** — Grounded Q&A **with citations**, plus auto-generated living documentation refreshed only for changed code.

**Problem solved** — "I don't understand this codebase" and "the docs are missing/outdated."

**Inputs** — Chunks + embeddings + retriever from P2; the retrieval-framework decision from P0.

**Outputs** — `POST /repos/{id}/ask` returning an answer plus file:line citations; a documentation tree generated per module/function; regeneration triggered by `content_hash` change; chat UI with citation rendering; drift-relevant `documents` rows with `source_hash` + `generated_at` + **the doc-time reference vector decided in D11**.

**Technical components** — Grounded-answer prompt + LLM client abstraction, citation assembly, doc generator, hash-triggered regeneration, chat UI, docs browser.

**Research dependencies** — P0 spike 5 (LLM cost, with/without graph layer); retrieval-framework decision.

**Datasets / test data** — **30 questions per demo repo** with an expected answer *and* expected file:line (PRC §1.8). SWE-QA (Apache-2.0) available as an external cross-check.

**Depends on** — P2.

**Acceptance criteria**
- (1) ≥80% of the 30 questions answered correctly **and** cited correctly, with correctness and citation precision/recall reported **separately** (Finding 28).
- (2) Every citation resolves to an existing line range in the current commit.
- (3) ≥95% of modules/functions have a generated summary after one ingestion run.
- (4) Changing one file regenerates **only** that file's docs.
- (5) Docs coverage and a human-rated usefulness sample (30 docs) both reported — Finding 30 notes 95% coverage alone is nearly trivially satisfiable.
- (6) LLM calls and tokens per ingestion run recorded.
- (7) Long-context-only ablation run for comparison.

**Demo artifact** — **The most memorable beat: the jury asks the codebase a question themselves and watches a cited answer appear.**

**Evaluation** — Answer correctness, citation precision, citation recall/comprehensiveness, docs coverage, docs usefulness rating, LLM cost, long-context ablation.

**Risks** — **Highest-risk module after M2.** LightRAG's LLM extraction cost may exceed budget; hallucination in answers; citation correctness degrading (up to 57% post-rationalization per Finding 28).

**Fallback** — Custom vector retrieval + prompt template (**pre-approved**); if quality is short of target, report the measured number honestly rather than overclaiming.

---

## Phase P5 — Bug & Security Analysis (Module 2)

**Goal** — Two-layer findings with plain-English explanations, deterministic where possible, AI-generated clearly labelled.

**Problem solved** — "Bugs and security issues exist that a casual read will not catch."

**Inputs** — Chunks from P2; the repo working tree; Semgrep CE; an LLM; the severity-mapping decision.

**Outputs** — Normalized Semgrep findings; LLM review findings above threshold with explanations, confidence, and an `AI-generated` label; dedupe between layers; per-layer precision reporting; findings list + detail UI; **Semgrep CE's single-function limitation documented in the UI/report**.

**Technical components** — Semgrep runner + JSON normalizer, severity mapper, risky-chunk selector, structured review prompt, confidence filter, dedupe, precision-sampling tool, findings UI.

**Research dependencies** — P0 spike 7.

**Datasets / test data** — Seeded bug set: **20–40 injected patterns in Python and JS/TS** covering (a) single-function classes Semgrep CE *can* catch and (b) a smaller set of cross-file/logic classes for the LLM layer. Pattern sources: BugsInPy fix commits (realistic), ContextCRBench categories (logic/security/performance/architecture). **Do not import BigVul/DiverseVul/PrimeVul patterns — C/C++ and noisy.**

**Depends on** — P2. **Independent of P4.**

**Acceptance criteria**
- (1) Recall ≥80% on the seeded set, **reported per layer**, with the label "recall on injected patterns" stated explicitly.
- (2) Precision ≥70% on the hand-reviewed sample, reported per layer, with the sample size, rubric and rater protocol stated.
- (3) Every finding has file, line, severity, plain-English explanation and source (rule ID or `llm-review`).
- (4) LLM findings are visibly labelled AI-generated.
- (5) Semgrep-only vs Semgrep+LLM ablation reported (Finding 31).
- (6) **No claim of cross-file bug detection is made anywhere** — CE cannot do it (Finding 9).

**Demo artifact** — **One specific flagged snippet with a plain-English explanation.** Never an abstract accuracy percentage. Then explicitly state the CE limitation — a jury will respect that far more than silence.

**Evaluation** — Seeded recall; per-layer precision on a stratified hand sample; ablation; LLM calls + tokens.

**Risks** — **The highest-risk module in the project.** PrimeVul's 68%→3% F1 collapse and VulnAgent-R2's ~0.40/0.37 P/R show zero-shot LLM detection is weak. Judge risk if we overclaim.

**Fallback** — Ship Semgrep-only as a complete, honest module and add the LLM layer as **triage + explanation** (well-supported by Llm4sa and LLM4PFA). This is a *stronger* fallback than pretending to detect novel bugs.

---

## Phase P6 — Pull Request Risk Analysis (Module 5)

**Goal** — A plain-English PR summary plus risk flags grounded in facts already in the database.

**Problem solved** — "Large pull requests are slow and tiring to review."

**Inputs** — PR URL; GitHub API; M2 findings; M4 findings; M6 documentation state.

**Outputs** — Plain-English summary; cross-referenced risk flags (touches a file with an open finding / adds a dependency with a known CVE / changes code whose docs are stale); `pr_analyses` rows; a PR view. **No webhooks, no comment posting, no auto-approval.**

**Technical components** — GitHub API client, diff fetcher, summarizer, cross-reference join, PR cache, PR view.

**Research dependencies** — P0 spike 8; ContextCRBench's finding that **PR description/issue text matters more than the diff** (Finding 26).

**Datasets / test data** — 20–30 real merged PRs from the demo repos, hand-labeled for (a) summary accuracy and (b) whether the risk flags are correct. SWRBench (MIT) as an external check if desired.

**Depends on** — **M2 (P5) and M4 (P3)** for findings to join against. M6 is optional input.

**Acceptance criteria**
- (1) ≥80% of sampled summaries rated accurate against a **written rubric** (Rubric must exist before measurement).
- (2) Every risk flag traces to a stored finding ID.
- (3) Zero false cross-references on the hand-labeled sample — or the measured rate reported.
- (4) Cached PR data lets the demo run with no live API call.
- (5) GitHub rate-limit budget respected; PAT in env only.
- (6) Explicit confirmation that **no PR comment is ever posted and no fix is ever generated.**

**Demo artifact** — Paste a PR URL → one screen: summary + three-or-fewer concrete risk flags.

**Evaluation** — Summary accuracy (rubric-based, N=20–30); cross-reference precision/recall; LLM cost per PR.

**Risks** — GitHub API rate limits during the viva (**mitigation already in the documents: cache everything**); risk flags that feel thin because upstream findings are sparse; judge perceiving PR analysis as "Copilot for reviews."

**Fallback** — **Documented cut candidate #2.** Its cross-referencing folds into M7, which still works.

---

## Phase P7 — Documentation Drift (Module 6)

**Goal** — Detect documentation that has silently gone stale relative to its code.

**Problem solved** — "Docs quietly go stale as code changes underneath them."

**Inputs** — `documents` rows (text, `source_hash`, `generated_at`, doc-time reference vector) from P4; current chunk hashes and embeddings from P2.

**Outputs** — Drift findings with reason (`code_changed_no_doc_update` vs `similarity_below_threshold`) and the triggering change; a docs browser showing drift flags; a drift-flagged docs surface in M5.

**Technical components** — Hash/timestamp comparator, AST-signature normaliser (to ignore formatting/comment churn), embedding-similarity comparator, threshold config, drift writer.

**Research dependencies** — P0 spike 6.

**Datasets / test data** — **15–25 injected drift cases**: signature change, renamed symbol, changed return type, removed function, changed parameter count, rewritten logic, plus **negative cases** (reformatted code, comment-only edits) that must *not* be flagged.

**Depends on** — P4 (docs state) and P2 (embeddings).

**Acceptance criteria**
- (1) ≥90% of injected drift cases detected.
- (2) Negative cases correctly not flagged (**report the false-positive rate on negatives — this is what makes the 90% credible**).
- (3) Every drift finding names the code change that triggered it.
- (4) The similarity threshold is chosen **from measured data**, not guessed.
- (5) **The construction procedure for the drift set is documented** so a reviewer could rebuild it.

**Demo artifact** — Docs browser with stale entries flagged, each linked to the code change that invalidated it.

**Evaluation** — Detection rate on injected cases; false-positive rate on negatives; per-reason breakdown (hash vs similarity).

**Risks** — **First cut candidate.** No external benchmark exists (Finding 24); the method is prior art, so the jury may question novelty; hash-only is trivially gamed by a formatting commit unless AST-signature normalisation is added.

**Fallback** — **Documented cut candidate #1.** Hash + timestamp only (drop embedding similarity) — still useful, removes the D11 storage decision entirely.

---

## Phase P8 — Release Readiness Score (Module 7)

**Goal** — One transparent, deterministic, explainable score with a complete breakdown.

**Problem solved** — "Is this codebase safe to release right now?"

**Inputs** — All open findings from M2, M4, M5, M6; the weight/cap configuration; the reproducibility mechanism from D16.

**Outputs** — `score_snapshots` rows with score, label, breakdown JSON linking to contributing finding IDs, **and the config used**; a history series; a breakdown panel; the readiness overview screen.

**Technical components** — Score engine (pure function), category-cap logic, label bands, snapshot + config persistence, breakdown UI with drill-through links.

**Research dependencies** — None. Pure logic over stored data.

**Datasets / test data** — The PRC's worked example (1 high + 3 medium code, 2 high deps, 4 drifted docs → 71, "Needs Attention") as a unit test.

**Depends on** — P3 (M4), P5 (M2), P6 (M5), P7 (M6). **P7 is optional** — with M6 cut, its category simply contributes 0.

**Acceptance criteria**
- (1) The PRC worked example reproduces exactly.
- (2) Same repository state + same config → **byte-identical** score, run 3×.
- (3) Category caps hold: 50 critical M2 findings deduct exactly 35, not more.
- (4) Every deduction links to the findings that caused it.
- (5) The score changes **only** via the structured findings — no free text, no model inference anywhere in the engine.
- (6) Ablation: score with M5/M6 removed, to show their contribution.

**Demo artifact** — **The hero screen.** One number, one label, a breakdown showing exactly which module dragged it down, each line clickable to its findings.

**Evaluation** — Unit tests for the formula and caps; a 3× repeat-stability regression test; the ablation.

**Risks** — If upstream modules are sparse, the score looks arbitrary → mitigate by demoing on a repo with genuine findings; weight tuning could be seen as fitting to the demo (**mitigate: declare the tuning repos and freeze weights before the final run**).

**Fallback** — Reduce to M2 + M4 categories only.

---

## Phase P9 — Dashboard, Integration, Evaluation & Demonstration

**Goal** — One polished shell, a complete measured evaluation, and a rehearsed demo.

**Problem solved** — "I cannot reach any result without reading logs."

**Inputs** — All modules; all evaluation artifacts; 2–3 demo repos.

**Outputs** — All seven documented screens (FR12); finalized API contract; the evaluation report with measured numbers and sample sizes; the project report; the presentation; the rehearsed demo script; the demo repos pre-indexed and offline-capable.

**Technical components** — Screen completion, findings detail + status mutation (acknowledge/resolve), dependency view, PR view, chart rendering for the breakdown, citation rendering in chat, regression test suite, docs/report.

**Research dependencies** — All prior.

**Datasets / test data** — The full evaluation battery (§12).

**Depends on** — P1–P8.

**Acceptance criteria**
- (1) All FR1–FR12 demonstrable end to end.
- (2) Every result reachable in ≤3 clicks.
- (3) Full evaluation executed on 2–3 repos with sample sizes reported.
- (4) Three ablation/baseline comparisons included (Finding 31).
- (5) Score-stability regression test passes.
- (6) Full demo rehearsed ≥2× with no live API dependency.
- (7) Report states the known limitations: Semgrep CE scope, detection bounded by underlying tools, no cross-file bug detection.

**Demo artifact** — The full narrative from Spec §7.2.

**Evaluation** — FR coverage checklist; measured results table; rehearsal log.

**Risks** — Evaluation time overruns; doc-writing underestimation (**mitigate: write sections as results land, not at the end**); scope creep into polish.

**Fallback** — Ship the core story (P1–P5, P8, P9-minimal) and cut P6/P7.

---

# 8. Architecture Decisions To Be Made

**None of these are decided here.** Each has options, the evidence needed, the spike that settles it, a deadline anchored to the phase where it must be settled, and the risk of getting it wrong.

| # | Decision | Options | Evidence Needed | Experiment / Spike | Deadline | Risk |
|---|---|---|---|---|---|---|
| **D1** | **Embedding strategy** — model, dimension, local vs API | (a) `nomic-embed-text-v1.5` 768d local · (b) `bge-m3` local (LightRAG's own recommendation) · (c) hosted API embedding · (d) code-specific (`nomic-embed-code`, 7B) | Retrieval quality on our own repos; cost; CPU feasibility; license | **S4** — score ≥2 candidates on a 20-query hand set; optionally corroborate on CodeSearchNet's 99 annotated queries or RepoQA | End of **P0** | Wrong choice forces re-embedding of every repo. Note: LightRAG fixes vector dimension at table creation and has no re-embedding tool |
| **D2** | **LLM provider strategy** | (a) single hosted API · (b) local (Ollama) · (c) both, config-switchable | Answer/finding quality, cost per run, latency, code-privacy posture | **S5, S7** — run one representative task per candidate | End of **P0** | The NFR demands both quality *and* the option of local inference. Locking one removes a documented privacy capability |
| **D3** | **Local vs hosted inference as the default** | local / hosted / per-module | Hardware available; whether a demo can run fully offline | **S5** | End of **P0** | Getting this wrong either breaks the offline demo or exposes code |
| **D4** | **Retrieval framework** | (a) LightRAG · (b) custom vector retrieval + prompt · (c) hybrid (LightRAG graph for multi-hop, vector for the rest) | Retrieval quality vs LLM calls-per-chunk | **S4 + S5** | End of **P0**, re-check end of **P4** | **LightRAG's LLM extraction cost per chunk is unknown and may be prohibitive.** Fallback is pre-approved — using it is not a failure |
| **D5** | **LightRAG storage topology** | (a) LightRAG owns its four stores, our `chunks` remain the retrieval index for other modules · (b) one shared schema | Can LightRAG read our tables? Write amplification? Deletion behaviour | **S4** | End of **P0** | Two sources of truth breaks FR11's incremental guarantee and G10's drift logic |
| **D6** | **Vector storage** — index and parameters | pgvector exact vs HNSW/IVFFlat; distance op; dimension | Recall/latency at our scale | **S4** | End of **P2** | Low — but pgvector itself is already decided (PRC §2.9), so this is only tuning |
| **D7** | **Supported languages** | Python + JS/TS (lock) · + Java (stretch) · + C/C++ (only if Juliet is wanted) | Languages of the demo/eval repos; Semgrep rule availability per language | **S1, S2** | End of **P0** | Over-expanding breaks the PRC's "fixed language set" and multiplies chunking/rule/doc work |
| **D8** | **Parser / chunker strategy** | function-level · class-level · hybrid · include imports/decorators · oversized-chunk splitting · nested-function handling | Retrieval + citation quality (P2 acceptance) | **S1, S4** | End of **P2** | Chosen granularity constrains M1 citations, M2 chunk selection and M6 "documented unit" definition |
| **D9** | **Semgrep rule configuration** | which rulesets (`p/security-audit`, `p/python`, `p/javascript`, correctness …) · severity mapping · per-language sets · suppression | Precision on a hand-labeled 50-finding sample | **S2, S7** | End of **P5** start | Too many rules → unmanageable false positives in front of a jury. Record each ruleset's license (Rules License v1.0 / AGPL third-party) |
| **D10** | **OSV acquisition + severity normalization** | (a) subprocess only · (b) API only · (c) both · severity: CVSS band map + explicit unknown policy · fixed-version extraction | Agreement with direct OSV-Scanner; DB-snapshot reproducibility; offline parity | **S3** | End of **P3** | Severity drives M7's weights, so a non-deterministic rule breaks reproducibility. OSV records without CVSS exist (Finding 16) |
| **D11** | **Doc-time reference vector (closes G10)** | (a) snapshot embedding column on `documents` · (b) re-embed stored doc text at comparison time | Storage cost vs reproducibility; index-rebuild cost | **S6** | End of **P7** (or P0 if M6 is at risk) | Without it, M6's similarity branch is unimplementable as specified |
| **D12** | **LLM review strategy** | chunk selection heuristic · prompt · confidence definition · dedupe rule · per-run budget | Precision ≥70% per layer; LLM calls per run | **S7** | End of **P5** | Over-budget on a large repo; or too aggressive a threshold → precision collapses (PrimeVul's lesson) |
| **D13** | **Documentation drift methodology** | (a) hash + timestamp only · (b) + AST signature · (c) + embedding similarity · similarity threshold | Detection rate on injected cases **and FP rate on negatives** | **S6** | End of **P7** | Threshold guessed rather than measured → the 90% target becomes unfalsifiable |
| **D14** | **PR analysis methodology** | inputs (diff vs diff+description+issue) · summary rubric · cross-reference rules · caching | Rubric-based accuracy; cross-reference precision | **S8** | End of **P6** | ContextCRBench says description text matters more than the diff — a diff-only design will underperform |
| **D15** | **Background job architecture** | (a) in-process asyncio · (b) worker process + DB queue · (c) external queue (Celery/RQ/arq) | Ingestion duration on a 50k-LOC repo; restart-safety; progress reporting | **S1/S3 scale test** | End of **P1** | A 50k-LOC ingest that dies halfway with no resume wastes a demo |
| **D16** | **Reproducibility mechanism** | cache LLM outputs keyed by `content_hash + model_id + prompt_version` · record config in `score_snapshots` · pin model versions | Two identical runs → identical score, 3× | **S5, S7** | End of **P8** | The NFR is unachievable without this; without it, "deterministic score" is an unsupported claim |
| **D17** | **Findings schema detail fields + fingerprint** (closes G11) | dedicated columns vs `details_jsonb` · deterministic fingerprint key · line start/end | Dedupe across layers; status preservation across re-ingests | **S2, S3** | End of **P3** | FR7/FR8 cannot be satisfied without package/version/range/fix-version/PR-number fields |
| **D18** | **Frontend architecture** | build tool · TypeScript? · routing · data fetching · chart library · citation renderer | NFR Usability ("any result in a few clicks") | Prototype only | End of **P2** (minimal) / **P9** (final) | Low technical risk, high demo risk if chosen late |
| **D19** | **Deployment approach** | docker-compose (app + Postgres+pgvector) vs bare local | Reproducibility on a jury machine | **P1** | End of **P1** | A demo that won't start on the viva machine is a total loss |
| **D20** | **Evaluation protocol** | rubric definitions · sample sizes · rater count · inter-rater check · aggregation | All metrics in §12 | Drafted in **P0**, executed in **P9** | Draft end of **P0** | Undefined rubrics make every accuracy number unfalsifiable — the single easiest thing for a jury to attack |

---

# 9. Feasibility Spikes

Eight spikes, **~10 working days total**, ordered by information-per-hour. These are the same four the PRC §4.3 already prescribes, extended to cover the decisions that research flagged as risky.

| # | Spike | Objective | Input | Experiment | Expected output | Success criterion | Effort | Informs |
|---|---|---|---|---|---|---|---|---|
| **S1** | Tree-sitter parsing + chunking | Prove real function/class boundaries with correct line ranges | 2 candidate demo repos | Parse; extract chunks; **hand-verify 10 line ranges**; measure parse time; inspect error recovery on broken files | Chunk dump + verified line ranges + parse-rate % + timing | ≥95% line-range accuracy on 10 samples; parse rate ≥99% on the fixed language set | **0.5 d** | D7, D8, D15 |
| **S2** | Semgrep CE on a real repo | Measure real finding volume and false-positive rate; capture PRC §4.3 evidence | 1–2 demo repos | Run `semgrep --json`; hand-label 50 findings valid/invalid; record rule ids, severity values, CE scope limits | Saved JSON + 50-row precision table + limitation statement | Command works reproducibly; observed precision recorded (no target — this is measurement) | **0.5 d** | D9, D17; **PRC §4.3 evidence #1** |
| **S3** | OSV-Scanner + OSV API on real lockfiles | Prove authoritative vulnerability detection works; verify offline mode; compare paths | Lockfiles incl. one pinned to a known-vulnerable version | Run `osv-scanner scan source -r`; run direct OSV API queries; download offline DB and re-run; diff outputs | Saved output + agreement table + offline-vs-online diff | Both paths agree on affected package@version; offline output identical; ≥1 real CVE found | **1 d** | D10; **PRC §4.3 evidence #2** |
| **S4** | Repository retrieval + Q&A retrieval layer | Compare embedding candidates; test LightRAG vs custom | Repo from S1; 20 hand-labeled queries | Embed chunks with ≥2 models; compute Recall@k + nDCG@k; run one grounded Q&A; separately test LightRAG's graph layer and its storage behaviour | Retrieval metrics table + winner + dimension + a working retrieval API | ≥80% top-k contains the expected line for the best candidate; LightRAG integration blocker identified | **2 d** | D1, D4, D5, D6; **PRC §4.3 evidence #3 & #4** |
| **S5** | Documentation generation + cost | Measure coverage, quality, and **LLM calls per chunk** — with and without the graph layer | 200–500 chunks | Generate summaries for changed chunks only; count calls/tokens/time; hand-rate 30 summaries; run the graph variant and re-count | Cost table (calls/chunk, tokens/chunk, latency) + coverage % + 30-doc quality sample | Coverage ≥95%; cost within a stated budget; graph-layer cost quantified | **1 d** | D2, D3, D4, D16 |
| **S6** | Documentation drift | Determine whether hash-only suffices, and pick a threshold from data | Generated docs from S5 | Inject 5–10 drift cases + 3 negative cases (reformat/comment-only); compare hash vs hash+AST-signature vs hash+similarity; sweep the threshold | Detection/FP table per method + proposed threshold + construction recipe | Hash-only or hash+AST detects all positives; FP rate on negatives recorded; threshold chosen from the sweep | **1.5 d** | D11, D13 |
| **S7** | LLM-assisted bug review | Measure precision per layer; choose a confidence threshold | Semgrep output from S2 | Send Semgrep-flagged + heuristic-risky chunks to the LLM with a structured prompt; hand-label ≥30 findings; sweep the threshold | Per-layer precision table + threshold proposal + cost per finding | Precision ≥70% achievable at some threshold; the operating point is recorded with its cost | **2 d** | D2, D9, D12, D16 |
| **S8** | PR diff + risk analysis | Prove the M5 join works and draft the summary rubric | 5–10 real merged PRs from a demo repo | Fetch diff + title + description + linked issue; summarize; join changed files against a hand-made findings set; rubric-test 5 summaries | Sample summaries + draft rubric + join-accuracy note | Summaries usable by a human reviewer; the join never produces a wrong file→finding link | **1 d** | D14, D20 |

**Total ≈ 9.5–10 working days.** Outputs of S1–S4 *are* the PRC §4.3 feasibility evidence pack.

---

# 10. Project Milestone Graph

```
                        P0  Research · Feasibility · Decision Lock
                        │  (8 spikes, evidence pack, repo shortlist)
                        ▼
        ┌───────────────P1  Ingestion Foundation ───────────────┐
        │        intake · change detection · config · secrets      │
        │                     minimal API + UI shell               │
        └───────────────────────────┬──────────────────────────────┘
                                    ▼
                       P2  Repository Knowledge Core
                       parse → chunk → embed → store → retrieve
                       (citations resolve to real lines; NO LLM yet)
                                    │
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                     ▼
      P3  M4 Dependency P4  M1 Understanding   P9a  Evaluation
      Risk  (findings        Q&A + living docs      harness build
      FR7    schema         FR3 · FR4               (parallel track)
              │                      │
              │                      ▼
              │             P7  M6 Drift  ←──── CUT #1
              │                      FR9
              ▼                      │
 P5  M2 Bug & Vuln ──────────────────┤
       FR5 · FR6                      │
              │                       │
              └───────────┬───────────┘
                          ▼
              P6  M5 PR Risk  ←──── CUT #2
              FR8
                          │
                          ▼
              P8  M7 Readiness Score
              FR10  (reads P3 + P5 + P6 + P7)
                          │
                          ▼
              P9  Dashboard · Integration · Evaluation · Demo
              FR12 · full report · rehearsal
```

**Critical path** — `P0 → P1 → P2 → P3 → P5 → P6 → P8 → P9`. (P3 is on it because P5 and P6 both need the findings schema it hardens; P7 is *not* on it.)

**Parallelizable work**
- **P3 (M4) and P4 (M1) are independent** once P2 lands. They only share the findings schema and the LLM client abstraction. In practice a single developer sequences them, but the *design* must not couple them.
- **P3 and P5 share the findings schema and severity vocabulary.** Build the schema once, in P3.
- **The evaluation harness (P9a) is a parallel track from P2 onward.** Question sets, seeded bugs, drift cases and PR labels should be authored *while modules are being built*, not at the end. This is the single biggest schedule saver available.
- **Report writing is a parallel track too.** Every week a measured number exists, it goes into the report.

**Blockers (must clear before dependent work)**
1. **LightRAG cost profile** blocks P4's design commitment (D4) — cleared by S5.
2. **Findings schema + fingerprint + severity mapping** block P3, P5, P6, P8 — cleared by D17/D10 in P3.
3. **Doc-time reference vector** blocks P7 — cleared by D11.
4. **Reproducibility mechanism** blocks P8's NFR claim — cleared by D16, retrofitted from P4.
5. **Embedding dimension** blocks the pgvector schema — cleared by D1 in P0. *Do not create the vector column before D1 is decided.*

**Optional features (safe to defer indefinitely)**
- LightRAG graph layer (M1 works without it) · dependency license scanning via deps.dev (OSV-Scanner offers it free) · score history chart · Markdown export of generated docs · Java stretch language · reachability/call analysis in M4.

**Cut order — preserved exactly as the documents specify**
1. **P7 / M6 — Documentation Drift.** First cut. It is the least standalone-valuable, depends entirely on P4 being solid, and carries the heaviest evaluation-construction cost (no external benchmark exists). With M6 cut, M7's M6 category contributes 0 and the story stays coherent.
2. **P6 / M5 — PR Risk.** Second cut. Its cross-referencing logic folds directly into P8/P7.

**Non-negotiable core:** **P1, P2, P3 (M4), P5 (M2), P8 (M7)** — ingestion, knowledge core, dependency risk, bug/security analysis, readiness score. Together these already deliver repository understanding, cited Q&A, living docs, rule-based findings, authoritative dependency risk and one explainable release decision. **This is the coherence guarantee the documents require.**

**A note on what cutting M6 costs conceptually [INF]:** M7's formula includes a drift category. With M6 absent, the category should read **"not evaluated"** rather than "0". Decide at P8 whether to show it as `n/a` (honest) or drop the category (cleaner). My recommendation is `n/a` — it preserves the formula's auditability and tells the developer exactly what is not being measured.

---

# 11. Four-Month Implementation Plan (refined)

18 weeks. **Dates must be anchored to your actual submission deadline** — both documents instruct you to substitute real calendar dates. Weeks W1–W3 are P0.

## Month 1 — Research, Feasibility & Foundation

| Week | Milestones | Deliverables | Research | Feasibility | Demoable result |
|---|---|---|---|---|---|
| **W1** | P0 (a) · P1 start | Research report consolidated into this document; decision log created with owners + deadlines; demo/eval repo shortlist (5 candidates with URL, commit, license, LOC, dependency count); tool availability verified (Tree-sitter, Semgrep CE, OSV-Scanner, Postgres+pgvector, LLM access, GitHub PAT) | Finish papers 22–28; verify the three UNVERIFIED bibliographic items | — | Repo shortlist + decision log |
| **W2** | P0 (b) | **S1, S2, S3, S4** executed and written up | Read LightRAG storage/cost docs in full | Tree-sitter chunks (✓ PRC §4.3 #3), Semgrep output (#1), OSV-Scanner output (#2), retrieval + one query (#4) | **Feasibility evidence pack v1** |
| **W3** | P0 (c) → P1 (a) | **S5, S6, S7, S8**; **all D1–D20 decided or explicitly deferred**; readiness-overview mockup | — | Doc-gen cost, drift threshold, LLM-review threshold, PR rubric | Evidence pack complete; decisions locked |
| **W4** | **P1** | Repo registration, clone/pull, commit recording, per-file hashes, incremental re-ingest, deleted-file pruning, config + secrets, DB bootstrap, minimal `POST /repos` + `GET /repos/{id}/status` + repo-list UI | — | — | Register a repo; see status; **watch incremental behaviour on a commit** |

**Month 1 exit:** core ingests a repo and updates incrementally; 8 spikes documented; decisions locked; evidence pack ready for the review.

## Month 2 — Knowledge Core, Dependency Risk, Codebase Understanding

| Week | Milestones | Deliverables | Research | Feasibility | Demoable result |
|---|---|---|---|---|---|
| **W5** | **P2** | Tree-sitter chunker (per D8); embedder (per D1); pgvector store + index; retrieval API returning file:line; retrieval metrics harness | — | — | **"Here are the relevant code regions for your question, with file:line"** |
| **W6** | **P3 (M4)** | OSV-Scanner wrapper + OSV API client; severity normalization (per D10); affected-range/fixed-version resolution; **hardened findings schema + fingerprint**; dependency view | — | — | Dependency table with a real CVE + fixed version |
| **W7** | **P4 (M1a)** | Grounded Q&A with citations; chat UI; citation assembly | ContextCRBench finding applied to M5 design | — | **Ask the codebase a question → cited answer** |
| **W8** | **P4 (M1b)** | Doc generation per module/function; hash-triggered regeneration; docs browser; docs-coverage + 30-doc quality measurement; **start the 30-question set for repo 1** | — | — | **Browsable auto-generated documentation** |

**Month 2 exit:** FR1, FR2, FR3, FR4, FR7, FR11 demonstrable. Findings schema is real and used by two modules.

## Month 3 — Bug/Security Analysis & PR Risk

| Week | Milestones | Deliverables | Research | Feasibility | Demoable result |
|---|---|---|---|---|---|
| **W9** | **P5 (a)** | Semgrep CE integration; output normalization; severity mapping per D9; findings list + detail UI; CE scope limitation documented in-product | — | — | Deterministic findings list with real rule IDs |
| **W10** | **P5 (b)** | LLM review layer per D12; risky-chunk selector; confidence threshold; dedupe vs Semgrep; AI-generated labelling; findings filtering | — | — | LLM findings with plain-English reasoning, labelled AI |
| **W11** | **P5 (c)** | Seeded bug set (20–40 cases, patterns from BugsInPy + ContextCRBench categories); recall measured **per layer**; precision on a hand-reviewed stratified sample; **Semgrep-only ablation**; hand-verify every finding used in the demo | — | — | Measured recall/precision with sample sizes; ablation table |
| **W12** | **P6 (M5)** | PR fetch (diff + title + description + linked issue); summarizer with the **written rubric**; cross-reference join against M2/M4 (+M6 if present); PR cache; PR view; label 20–30 PRs | — | — | **Paste a PR URL → summary + traceable risk flags** |

**Month 3 exit:** FR5, FR6, FR8 demonstrable. Detection quality is *measured and honestly reported*. Evaluation harness has run once end to end.

## Month 4 — Drift, Score, Dashboard, Evaluation & Demo

| Week | Milestones | Deliverables | Research | Feasibility | Demoable result |
|---|---|---|---|---|---|
| **W13** | **P7 (M6)** — *CUT #1* | Drift comparator (per D13); doc-time reference vector per D11; 15–25 injected cases + negative cases; docs-browser drift flags | — | — | Stale docs flagged, each linked to the change that caused it |
| **W14** | **P8 (M7)** | Score engine + category caps + labels; snapshot + config persistence; breakdown panel with drill-through; score history; PRC worked-example unit test; ablation with M5/M6 removed | — | — | **THE HERO SCREEN: one number, one label, a complete breakdown** |
| **W15** | **P9 (a)** | Findings detail + status mutation (ack/resolve); all 7 screens; finalized API contract; regression suite (score stability, chunker, findings normalization, drift thresholds) | — | — | Full shell navigable; every result ≤3 clicks |
| **W16** | **P9 (b)** | **Full evaluation on 2–3 repos**: Q&A (answer + citation precision/recall), docs coverage + usefulness, detection recall/precision per layer, O4 agreement (scoped), PR accuracy, drift detection + FP rate, performance (full vs incremental ingest, LLM calls/run); three ablations; weights/caps tuned **then frozen** | — | — | Evaluation report with measured numbers and sample sizes |
| **W17** | **P9 (c)** | Demo repos pre-indexed; offline OSV DB cached; PR data cached; **demo rehearsed ≥2×**; presentation + final report; buffer | — | — | **Rehearsed end-to-end demo with zero live-API dependency** |
| **W18** | buffer | Contingency for slippage; final polish; submission | — | — | — |

**Schedule accounting [INF]**
- Research/feasibility: **3 weeks (W1–W3)** — the documents already prescribe this (§4.3); I am only making it explicit.
- Implementation: **10 weeks (W4–W14)**
- Dashboard/integration: **1 week (W15)**
- Evaluation: **1 week (W16)** — *only achievable because the harness is a parallel track from W8 onward*
- Demo prep, docs, presentation: **1 week (W17)** + **1 week buffer (W18)**
- **Non-code time that must not be skipped:** ~1.5 weeks of report writing, spread across all four months.

**Honest warning:** at these estimates, the full scope is **tight but feasible only if** (a) the P0 spikes are genuinely time-boxed to 10 days, (b) the evaluation harness is built in parallel from W8, (c) report sections are written as results land, and (d) M6 is cut without hesitation if W13 looks threatened. **If you cut M6 at W13, you gain roughly a week of slack for evaluation** — which is the whole point of scheduling it there.

---

# 12. Sentra Data Strategy

## 1. What data does Sentra actually need?

Only four kinds: (i) **repository source code** (from real git repos, parsed, never executed), (ii) **vulnerability records** (from OSV — never authored by us), (iii) **hand-built evaluation artifacts** (questions, seeded bugs, drift cases, PR labels), and (iv) **human judgements** (validity labels for findings, summary rubric ratings). No training data. No corpora. [INF]

## 2. What can come from real repositories?

Everything structural. Repos supply the code, the lockfiles, the git history (needed for incremental ingest, drift and PR scenarios), and the PRs. Realism and citation accuracy both depend on real repos — synthetic code would undermine the project's core claim.

## 3. What comes from OSV / CVE / GHSA?

**All vulnerability data for M4 — and nothing else.** OSV-Scanner + OSV.dev cover the ecosystem set in scope, are free, key-free, and authoritative. The PRC is right that building a custom dataset here would be wasted effort. Supplement with `oss-fuzz-vulns` (CC-BY-4.0) for real fix-commit pairs in drift/PR scenarios. **Do not use NVD as primary** — 5 req/30 s unauthenticated is impractical. [EXT §3.5]

## 4. What requires manually constructed test cases?

Four sets, and only four:

1. **Question sets** — 30 questions × 3 repos = 90 questions, each with an expected answer *and* an expected file:line. This is the largest manual cost (~8–12 hours per repo).
2. **Seeded bug set** — 20–40 injected patterns per language, each with a known CWE class and location. Patterns sourced from BugsInPy fix commits (realistic) and ContextCRBench categories.
3. **Injected drift cases** — 15–25 positives + 3–5 negatives (reformat-only, comment-only).
4. **Labeled PR set** — 20–30 real merged PRs, hand-labeled for summary accuracy and cross-reference correctness, against a rubric written *before* labeling.

**All four are small enough to hand-build. That is precisely why the PRC's design is sound.** [INF]

## 5. What can use seeded/synthetic vulnerabilities?

M2 recall, M5 review, and M6 drift. Validated by Finding 27 — synthetic mutation injection is an accepted PR-review evaluation technique. **Seeded bugs must be authored by someone who knows the correct answer** (you, reviewing each), never generated by an LLM and then used as ground truth. **Explicitly excluded from ground truth:** BigVul, DiverseVul, Devign, CVEfixes, PrimeVul and friends — C/C++, and measured label accuracy of 25–60%. [EXT §3.4]

## 6. What datasets are useful for research/evaluation?

| Use | Dataset | How |
|---|---|---|
| M1 external validation | **SWE-QA** (Apache-2.0, 720 QA pairs, 15 pinned Python repos) | Cross-check retrieval + answer quality against a published reference |
| M1 repo pool + retrieval ablation | CrossCodeEval, RepoQA, RepoBench, BugsInPy projects | Permissively-licensed, pinned real repos |
| M1 embedding comparison | **CodeSearchNet's 99 annotated queries** only | Cheap NDCG reference. **Do not download the ~20 GB corpus** |
| M2 realistic patterns | **BugsInPy** fix commits | Seed realistic-but-controlled bug patterns |
| M2/M5 repo pool | **SWRBench** (MIT, 12 Python repos), SWE-bench Verified repos (12) | Permissively-licensed real repos with pinned commits |
| M5 external check | SWRBench, AACR-Bench | Optional cross-check against published labels |
| M4/M6 real fix commits | OSS-Fuzz `oss-fuzz-vulns` (CC-BY-4.0) | Real introduced/fixed pairs |
| **Citation only — never data** | PrimeVul, DiverseVul, BigVul, Devign, Juliet, Defects4J, DepDec-Bench, dfbench | Evidence and prior art. Do not adopt |

## 7. What data should NOT be collected?

- **No training corpora.** Fine-tuning is prohibited. BigQuery GitHub datasets, GH Archive, and The Stack are unnecessary and ToS-risky.
- **No CodeSearchNet 20 GB download** — we train nothing, so its only value is 99 annotated queries.
- **No other people's private repositories.** Only public repos or the author's own projects.
- **No user code retention** beyond local analysis; no uploaded code to any third-party service other than the configured LLM provider, and the dashboard must state the active mode.
- **No secrets in the repository or database** — env only.
- **No posting to GitHub.** M5 reads; it never comments, labels, approves or opens PRs.
- **No executing analyzed code** — which also means no BugsInPy/Defects4J/SWE-bench test execution. We use their *commits and patterns*, not their harnesses. [Important consistency point: PRC §1.6 excludes CI/CD execution, so a test-executing bug benchmark is out of scope even though it would be convenient.]

## 8. What licenses / restrictions matter?

| Asset | License | Consequence for Sentra |
|---|---|---|
| **Semgrep CE engine** | **LGPL-2.1** | Fine — invoked as a separate process |
| **Semgrep-maintained rules** | **Semgrep Rules License v1.0** — internal business use only; no resale/competing product | Acceptable for a local academic tool. **Never redistribute the rules.** Record every ruleset used and its license (third-party registry rules keep their own — e.g. Trail of Bits AGPL-3.0) |
| **CodeQL CLI** | Separately licensed; free for research/OSS only | Do not embed. Not needed anyway (requires building) |
| **OSV-Scanner** | Apache-2.0 | Embed freely |
| **Tree-sitter + grammars** | MIT | Embed freely |
| **LightRAG** | MIT | Embed freely |
| **OSV data** | Open, per-source terms | Query, don't redistribute wholesale |
| **OSS-Fuzz vulns** | CC-BY-4.0 | Attribute if reproduced |
| **SWE-QA / SWRBench / AACR-Bench / RepoQA** | Apache-2.0 / MIT | Use freely with attribution |
| **BugsInPy / Defects4J / CrossCodeEval repos** | Per-project OSS licenses | **Only select permissively-licensed repos for anything we redistribute.** CrossCodeEval's repos are explicitly permissive — a reason to prefer that pool |
| **CodeSearchNet** | MIT for code; **per-repo licenses in `licenses.pkl`; HF mirror states example-wise license info is NOT included** | Use only the 99-query set; **do not redistribute the corpus** |
| **Juliet** | Public domain / CC0 1.0 | Would be fine if we ever added C/C++ |
| **Author's own past projects** (Abhaya-Netra, PramanaGST) | Unknown | **Must confirm their licenses are permissive enough to demo publicly** — this is an open question |
| **SonarQube Advanced Security** | Commercial | Reference only |

## 9. How many repositories are realistically sufficient?

**6–10 total.** [INF]

| Role | Count | Why |
|---|---|---|
| Development | 1–2 | Iteration. Never reported |
| Evaluation | 3–5 | At least one Python, one JS/TS, and **one ≈50k LOC** (the PRC's performance target) |
| Demo | 2–3 | Your past projects + one well-known OSS project, per the PRC |
| Small synthetic fixtures | 2–3 | <20 files, hand-built, for unit tests |

**Precedent:** SWE-QA uses 15 repos / 3.4M LOC for a full paper; BugsInPy uses 17; DepDec-Bench analyses 117k dependency changes but its *tasks* are 203. Ten repositories with 30k–150k LOC each is comfortably in range for a B.Tech final-year project, and **breadth of *labels* matters far more than breadth of repositories** here.

## 10. How will we avoid data leakage between development and evaluation?

Leakage is a **real** threat here because the demo repos are also the repos we develop against. Protocol: [INF]

1. **Distinct roles, distinct repos where possible.** Dev repo ≠ evaluation repos ≠ demo repos. Where a repo must fill two roles (likely for the demo repos), declare it explicitly in the report.
2. **No repository-level split needed within a repo, but project-level splits are the precedent.** CodeReviewer split **by project** specifically to prevent leakage; SWE-QA pins commits. We pin every repo to a commit hash and record it.
3. **Freeze before measuring.** All thresholds and weights (D13 similarity, D12 confidence, D9 rule set, D20 rubrics, and the M7 weights/caps) are **frozen before the final evaluation run**. Any tuning afterwards invalidates the run and forces a re-run.
4. **Declare tuning vs reporting repos.** "Weights were tuned on repos A and B; results are reported on repos A, B, C." Fully acceptable and standard. Hiding it is not.
5. **No threshold may be tuned on the same questions it is then scored against** — a new question set is authored for the final run.
6. **LLM-output caching must not leak**: cache keys include `content_hash + model_id + prompt_version`, so a changed prompt invalidates cached outputs rather than silently reusing stale ones.
7. **Benign-control cases** in the seeded and drift sets (reformat-only commits, clean PRs) prevent a system that flags everything from looking accurate.
8. **Published artifacts**: ship the question sets, seeded-bug manifest and drift-case definitions with the repo so the evaluation is reproducible by a third party.

---

# 13. SENTRA — MASTER DEVELOPMENT BLUEPRINT

**1. Problem** — A developer working alone, or joining an unfamiliar repository, cannot get one coherent, explainable answer to *"is this codebase healthy, and is it safe to release?"* Today that requires several disconnected tools, several separate reports, and manual reconciliation. Documentation goes stale silently, bugs and vulnerable dependencies go unseen until an audit, and large PRs are slow to review.

**2. Proposed solution** — Sentra: a single-developer engineering-trust platform that ingests a repository once through a shared knowledge core, runs six independent analysis modules over it, communicates through one common findings representation, and aggregates everything into one transparent, deterministic release-readiness score with a complete, drill-through breakdown. **It never generates code, never fixes code, never creates pull requests, never executes analyzed code, and never takes the decision away from the developer.**

**3. Target user** — One developer working with one repository at a time (single-user, local-first). Adjacent users: a semi-technical reviewer or jury member who needs to understand a repository's health without reading logs. The primary interactive beat is the user asking the codebase a question themselves.

**4. Core architecture** — Three layers. *(a)* A **shared ingestion and knowledge core**: clone/pull → record commit → Tree-sitter parse → chunk at function/class/module with path and line range → embed → store in Postgres+pgvector → incremental by commit, changed files only. *(b)* **Six independent modules** reading that core and writing the common findings schema: M1 Q&A+living docs, M2 bug/vulnerability (Semgrep + LLM review), M4 dependency risk (OSV), M5 PR risk, M6 doc/code drift, M7 readiness score. *(c)* **One dashboard shell.** The shared core is what makes this one platform rather than six tools; the common findings schema is what makes cross-module features and aggregation possible without per-module adapters.

**5. Modules** — M1 grounded Q&A with file:line citations + auto-generated living documentation refreshed only on change · M2 two-layer detection (deterministic Semgrep CE + confidence-thresholded LLM review, deduped, layers reported separately) · M4 authoritative dependency vulnerability data from OSV with identifier, derived severity, affected range and fixed version · M5 on-demand PR summary plus risk flags joined against stored findings · M6 documentation drift via hash/timestamp + AST-signature + embedding similarity · M7 capped weighted deduction with labels, breakdown, history and determinism guarantees. **Module 3 (ownership/bus-factor) was removed** as a multi-user/organization capability that serves no single-developer persona and would have endangered a four-month timeline; it remains a natural future extension.

**6. Research foundation** — 28 focused papers, not a padded list. Anchors: **RepoCoder** (EMNLP 2023) for repository retrieval; **LLift** (OOPSLA 2024) for static-analysis-plus-LLM, cited with its architectural difference stated explicitly; **ESEC/FSE 2023 SCA study** for scanner limits (bibliographic record to be verified). Validation instruments: **SWE-QA** (720 QA pairs / 15 pinned Python repos, Apache-2.0), **SWRBench** (1,000 balanced PRs, MIT), **CrossCodeEval**, **RepoQA**, **BugsInPy**, **OSV.dev/OSV-Scanner**, **OSS-Fuzz**. Reality checks that keep us honest: **PrimeVul** (68.26%→3.09% F1 when benchmarks are cleaned) and **OOD-Out-of-Luck** (71.1% dataset overlap) tell us not to claim detection rates we cannot substantiate. **Tan et al.** (>25% of top-1000 GitHub projects contain outdated code references) is our motivation evidence for drift.

**7. Data strategy** — Real repos only, no corpora. 6–10 repositories total (1–2 dev, 3–5 eval, 2–3 demo, plus tiny hand-built fixtures). Four hand-built artifact sets: 90 questions with expected citations, 20–40 seeded bugs, 15–25 injected drift cases plus negatives, 20–30 labeled PRs. Zero vulnerability data authored — OSV supplies all of it. Strict separation of dev / test / eval / demo data, all repos pinned to commits, all thresholds frozen before the final measurement run, tuning repos declared. Largest available datasets (CodeSearchNet ~20 GB, BigQuery GitHub) are explicitly **not** downloaded.

**8. Milestones** — P0 Research+Feasibility+Decisions · P1 Ingestion Foundation · P2 Repository Knowledge Core · P3 M4 Dependency Risk · P4 M1 Understanding · P5 M2 Bug/Vuln · P6 M5 PR Risk · P7 M6 Drift · P8 M7 Readiness Score · P9 Dashboard + Evaluation + Demo. Acceptance criteria are concrete and measurable at every phase, and **P3/P4 and P6/P7 carry explicit documented fallbacks**.

**9. Architecture decisions** — 20 open decisions (D1–D20), each with options, the evidence required, the spike that settles it, a phase deadline, and the risk. **None is decided in this document.** The highest-consequence ones are D1 (embedding — locks the vector dimension), D4 (LightRAG vs custom — its LLM extraction cost is unknown and could be prohibitive), D10 (OSV severity — drives the score), D16 (reproducibility mechanism — without it the "deterministic score" claim fails), and D17 (findings-schema detail fields — without them FR7/FR8 are unsatisfiable).

**10. Feasibility spikes** — 8 spikes, ~10 working days: Tree-sitter chunking · Semgrep CE · OSV-Scanner + API · retrieval + embedding comparison · documentation generation and cost · drift detection · LLM bug review · PR diff + risk. Spikes 1–4 produce exactly the feasibility evidence pack the PRC §4.3 already prescribes. **Their purpose is to prevent spending weeks building an architecture around an untested assumption** — LightRAG's cost profile being the obvious candidate.

**11. Four-month roadmap** — W1–W3 research + spikes · W4–W5 core · W6–W8 core + M4 + M1 · W9–W12 M2 + M5 · W13 drift · W14 score · W15 dashboard/API/regression · W16 full evaluation · W17 demo + docs · W18 buffer. Five deviations from the documented month plan (DV1–DV5) are declared for approval, each with its reason and its risk.

**12. Evaluation strategy** — Keep the PRC's plan; strengthen it in six specific ways. *(1)* Separate retrieval from generation (Recall@k, nDCG@k) so we know which half of M1 is failing. *(2)* Report **citation precision and citation recall** separately, because up to 57% of citations are "post-rationalized" (arXiv 2412.18004). *(3)* Decompose O3 by layer and label it **recall on injected patterns**, stating Semgrep CE's single-function ceiling explicitly. *(4)* Scope O4's "100% agreement" to the affected package@version set at a pinned OSV snapshot — not to derived severity. *(5)* Report **negative-case false-positive rates** for drift and PR, so the 90%/80% numbers are falsifiable. *(6)* Add three ablations — no-retrieval, Semgrep-only, and score-without-M5/M6 — because these are what convert "one platform, not six tools" from a claim into evidence. All numbers reported with sample sizes; results measured, never assumed.

**13. Risks** — *(documented)* LLM false positives in front of a jury; LightRAG complexity; GitHub rate limits; timeline slip. *(research-discovered, higher priority)* **Semgrep CE cannot analyze across function or file boundaries, so our recall target has a hard ceiling we must state.** **LLM vulnerability detection is far weaker than commonly reported** (PrimeVul; VulnAgent-R2 at ~0.40 precision / 0.37 recall), so M2's honest role is triage and explanation, not discovery. **LightRAG is LLM-heavy with four model roles, four storage backends, a fixed vector dimension and no re-embedding tool** — the largest unknown in the critical path. **There is no public ground truth for Python/JS/TS vulnerabilities** — which validates the seeded approach rather than undermining it. **There is no benchmark at all for documentation drift** — so M6's evaluation must be constructed and its method must be presented as prior art. **LLM nondeterminism conflicts with the reproducibility NFR** unless outputs are cached and config is snapshotted. Also: Semgrep's rules license forbids redistribution; the demo repos' own licenses are unknown; and the "no code generation" boundary can read to a jury as *less* impressive unless framed as the trust-and-decision layer it is.

**14. Cut strategy** — **P7 (M6) first, then P6 (M5)** — exactly as the documents specify. M6 is scheduled at W13 so cutting it costs the least; its cross-referencing folds into M7. The **non-negotiable core is P1 + P2 + P3 + P5 + P8** (ingestion, knowledge core, dependency risk, bug/security analysis, readiness score), which alone delivers repository understanding, cited Q&A, living docs, deterministic findings, authoritative dependency risk and one explainable release decision. With M6 cut, its score category should display as **`n/a`, not `0`** — honest, and it preserves the formula's auditability.

**15. Final demo story** — Unchanged from the documents and still the right order: **open on the readiness score** (one number, immediately understood) → **drill into the breakdown** (exactly which findings caused the deduction) → **one concrete flagged bug** with its plain-English explanation, followed immediately by the honest statement of Semgrep CE's single-function limitation → **one OSV dependency CVE** (needs no persuasion) → **the jury asks the Q&A chat themselves** (the most memorable, interactive beat) → **close back on the score**. Contingency: OSV offline DB and all PR data pre-cached; demo repos pre-indexed; rehearsed at least twice; no live API dependency.

**16. Immediate next step** — **Complete P0, and nothing else.** Concretely: *(a)* confirm the demo and evaluation repository candidates, including the URLs, pinned commits, licenses and LOC of Abhaya-Netra and PramanaGST, plus one permissively-licensed OSS project; *(b)* install and version-pin the toolchain (Tree-sitter, Semgrep CE, OSV-Scanner, Postgres + pgvector, LLM access, GitHub PAT) and run **spikes S1, S2 and S3** — one to three days, and they produce the PRC §4.3 feasibility evidence you need regardless of what happens next; *(c)* draft the readiness-overview mockup; *(d)* answer **D1 and D7** (embedding candidates, language scope) because they must be settled before any vector column or chunker is created; *(e)* get the guide's ruling on the five plan deviations (DV1–DV5) and on re-fixing the O3/O4 definitions in §12.

---

**End of document.** This is a research and planning artifact. No implementation code, application structure, database schema, API implementation, model integration, or Docker configuration has been created. On explicit approval, work begins at **Phase P1**, milestone by milestone.