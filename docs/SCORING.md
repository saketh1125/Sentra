# Readiness scoring

The readiness score is deterministic for a fixed set of findings and scoring
configuration. It starts at 100 and subtracts severity penalties, capped by
module. The result is rounded to the nearest integer and clamped to 0–100.

```text
score = clamp(round(100 - sum(module deductions)), 0, 100)
module deduction = min(sum(severity weights for module findings), module cap)
```

## Severity weights and module caps

| Severity | Penalty per finding |
|---|---:|
| Critical | 10 |
| High | 5 |
| Medium | 2 |
| Low | 0.5 |
| Unknown | 0.5 |

| Module | Meaning | Maximum deduction |
|---|---|---:|
| `m2` | Semgrep static analysis | 35 |
| `m4` | OSV dependency vulnerabilities | 30 |
| `m5` | PR risk (reserved scoring module) | 15 |
| `m6` | Documentation drift (reserved scoring module) | 20 |

Findings in any other module are grouped into `other` and are not capped by a
module limit.

The `m5` and `m6` caps are defined in the scoring configuration, but the
current PR analysis and documentation-drift paths do not create `m5`/`m6`
`Finding` rows. As a result, those caps do not affect scores unless such
findings are added to the database by a future implementation.

## Score labels

| Score | Label |
|---|---|
| 85–100 | Ready |
| 60–84 | Needs Attention |
| 0–59 | At Risk |

## Reading the breakdown

The score response contains each module's finding count, raw penalty,
configured cap, applied deduction, and severity counts. A raw penalty above its
cap means the cap reduced the contribution. The UI also shows the per-severity
calculation. `POST /repos/{repo_id}/score` persists a snapshot with its scoring
configuration; `GET /repos/{repo_id}/score` returns the latest snapshot or
computes a live score when no snapshot exists.

Only findings currently stored by the scanner modules contribute. A score
does not claim that the repository has no undiscovered issues; scanner
coverage and false negatives remain relevant limitations.
