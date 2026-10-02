# Sentra — Resource / Execution Incident Note

**Incident date:** 2026-10-02
**Severity:** Session-terminating (the OpenCode development session was killed)
**Status:** Root cause of the OOM **established**; precise in-process cause **not established**

This note exists so that a future session does **not** blindly repeat the operation that caused
the failure.

---

## 1. What was being executed

The **S4 — Repository retrieval / embedding comparison spike**:

```
.venv/bin/python spikes/s4_retrieval/spike.py
```

Launched after the script's import-scoping bug had been fixed and the module-level import
verified. The spike iterates **5 candidate embedding models × 2 chunk-render modes** in a single
process, and for each combination:

- loads an ONNX embedding model via `fastembed.TextEmbedding`,
- embeds **807 chunks** with `model.passage_embed(...)`,
- embeds 24 queries with `model.query_embed(...)`,
- converts both matrices with `.tolist()`,
- for each of the 24 queries, re-normalises the full document matrix and re-computes the
  dot product (`_search_matrix`).

## 2. Symptoms observed

1. The command produced **no output** and never returned.
2. The OpenCode session terminated.
3. On the next session, the command could not be re-run (server restarted).

## 3. Evidence (kernel log, captured after restart)

From `dmesg -T`:

```
Oct 02 21:17:33 sakeths-fedora kernel: Out of memory: Killed process 63235 (python)
    total-vm:76059836kB, anon-rss:51940076kB, file-rss:16kB, shmem-rss:0kB,
    UID=1000 pgtables:108944kB oom_score_adj:200
Oct 02 21:17:35 sakeths-fedora kernel: oom_reaper: reaped process 63235 (python), now anon-rss:0kB
```

From `journalctl` (same timestamp):

```
Oct 02 21:18:18 ... ptyxis-spawn-0c348cc6-...scope: Killing process 72099 (opencode) with signal SIGKILL.
Oct 02 21:18:18 ... ptyxis-spawn-0c348cc6-...scope: Killing process 72108 (opencode) with signal SIGKILL.
Oct 02 21:18:18 ... ptyxis-spawn-0c348cc6-...scope: Failed with result 'oom-kill'.
Oct 02 21:19:47 ... app.slice: The kernel OOM killer killed some processes in this unit.
```

Host memory at time of inspection: **62 GiB total**, 8 GiB swap.

## 4. What is established

- A `python` process (PID 63235) reached **≈51.9 GB resident set size** (`anon-rss:51940076kB`).
- The kernel **OOM killer terminated it** (`constraint=CONSTRAINT_NONE`, `global_oom`).
- The kernel then **OOM-killed the `opencode` processes**, which is why the session ended.
- The system did not merely swap; a single process consumed the majority of physical RAM.
- The only resource-intensive command in flight at that time was the S4 spike.
- Supporting circumstantial evidence: `data/cache/fastembed` had grown to **674 MB**, and
  partial model files were present, confirming the spike was mid-model-load/embed at the time.

## 5. What is NOT established

- **The specific line of code responsible is unknown.** The OOM record identifies the process,
  not the allocation site.
- **Which of the five candidates** was being processed at the moment of the kill is unknown.
- **Whether the growth was in model loading, ONNX arena allocation, or the scoring loop is
  unknown.**

Prime suspects, none proven:

1. **Unbounded embedding input.** `passage_embed` was called on all 807 chunks as a single
   call, with no batch slicing.
2. **ONNX Runtime arena growth.** Multiple large models loaded in one process can accumulate
   allocator arenas that are not returned to the OS.
3. **`.tolist()` on embedding matrices.** Converts numpy arrays into Python float objects
   (~32 bytes each). A 807×768 matrix is ~20 MB per conversion, but this was repeated per
   candidate/render-mode combination and per query inside the scoring loop.
4. **Thread oversubscription.** ONNX Runtime defaults may spawn one arena per core across a
   16-core host.

> **Status: Unknown / needs verification.** Do not state a cause as fact.

## 6. Should the operation be rerun?

**Not as previously written.** The task itself is legitimate and necessary — it decides
embedding model and vector dimension (**D1**), which fixes the pgvector column type in P2. It
must simply be made memory-bounded first.

### Mandatory safety changes before any rerun

| # | Change | Rationale |
|---|---|---|
| 1 | **One candidate per process**; loop over candidates from the shell | Isolates peak memory and gives a clear failure point |
| 2 | `del model; gc.collect()` after each candidate | Releases ONNX arenas between models |
| 3 | **Batch the corpus in fixed slices** (e.g. 64 chunks) with progress output | Bounds peak allocation regardless of corpus size |
| 4 | **Remove `.tolist()`**; score with numpy, keep one normalised matrix | Removes Python-object materialisation |
| 5 | Cap threads: `OMP_NUM_THREADS=4`, `OMP_THREAD_LIMIT`, ONNX intra-op limit | Prevents per-core arena multiplication |
| 6 | Wrap in `ulimit -v` (e.g. 8 GB) so a regression **fails fast** instead of OOM-killing the session | Turns a session-killing failure into a visible error |
| 7 | Always run under `timeout` | Bounds wall-clock |
| 8 | Reuse already-cached models; do not re-download | Saves time and bandwidth |
| 9 | Log RSS after each stage so growth is observable | Makes the next diagnosis evidence-based |

### Standing resource rules for this project

- Prefer small test inputs; validate on a 100-chunk subset before a full run.
- Never load an entire repository or dataset into memory when incremental processing is possible.
- Use bounded batches everywhere.
- Reuse previously generated artifacts rather than recomputing them.
- Do not repeat a completed experiment.
- **If an operation looks likely to exceed memory, redesign and bound it before running it.**

## 7. Collateral impact on project state

- `docs/evidence/S4_retrieval.json` was **not** overwritten by the killed run. It still holds
  the earlier all-`load_failed` records. **It contains no valid measurement** and must not be
  cited as a result. See `docs/development-status.md` §4.
- All S1, S2, S2b, S2c and S3 evidence is unaffected and valid.
- No source files were lost. No work needs to be redone.