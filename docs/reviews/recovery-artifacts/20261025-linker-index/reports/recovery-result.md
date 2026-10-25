## Recovery result
Sandbox: 20261025-linker-index   Work dir: C:\Users\shoer\hackerrank-orchestrate-october26\.claude\sandboxes\20261025-linker-index\work   Source HEAD/branch (from manifest): acb3dfca6e94e4803a26e72c49074a488de93c93/solution-baseline   Adopt: yes

### Metrics
| Metric | Baseline | After | Delta |
|---|---|---|---|
| sample status / step F1 / sequence | 1.000 / 0.971 (P/R 0.995/0.948) / 0.688; evidence 1.000 | 1.000 / 0.971 (P/R 0.995/0.948) / 0.688; evidence 1.000 | 0 |
| tests passed / custom cases passed | 76/76 / 6/6 | 80/80 / 6/6 | +4 tests (new file), 0 failures |
| eval output.csv sha256 | 7a9683fd5215f5693e906d0af105a16430df90e621686a26be15b16755e3ea50 (5 timed runs) | 7a9683fd5215f5693e906d0af105a16430df90e621686a26be15b16755e3ea50 (6 runs: 5 timed + 1 more); byte-identical to the baseline copy | none |
| `python code/main.py` wall time, median of 5 | 1.671 s (1.683/1.905/1.671/1.611/1.611) | 1.212 s (1.255/1.238/1.201/1.212/1.137) | -0.459 s (about -27%) |
| eval rows / validation problems / model calls | 518 / 0 / 0 | 518 / 0 / 0 | 0 |

### Failures
| id | class | severity | certainty | stage | outcome | test added | eval rows changed |
|---|---|---|---|---|---|---|---|
| F1 | performance (link stage full scan, run twice per case) | minor | reproduced (baseline timing) | link | fixed | code/tests/test_linker_index.py (4 tests) | 0 |

### Changes to adopt
- code/audit/linker.py: adds `_identifier_index(store)`, a lazily built index from (email/hash/user_id) to store positions, cached on the store and rebuilt if the observation list is replaced or grows. `link_resources` now checks `matches()` only on the candidate positions, sorted by `(not visible, position)`. That is exactly the order of the original stable sort, so the first match per resource, its reason and evidence_id, and the provenance order are all unchanged. The decoy guard and the propagation loop are untouched.
- code/audit/pipeline.py: adds `Auditor.links_for(ident, audit_at)`, which memoizes `link_resources` per (user_id, emails, hashes, audit_at) and returns fresh set/list copies, because `audit()` mutates `linked` with `|=`. Both callers (`assign_workflow_resources`, `audit`) use it. It uses `self.__dict__.setdefault`, so Auditors built via `__new__` (custom cases) still work.
- code/tests/test_linker_index.py: adds the original full-scan algorithm as a reference oracle. Tests check that indexed `link_resources` and `links_for` equal the oracle (linked set and ordered provenance) for all 550 eval+sample cases. Fixture tests cover visible-first provenance and the decoy guard, index rebuild when observations grow, and memo copy independence.

### Limitations to document
- The index assumes an observation's `emails`/`hashes`/`users` sets are not mutated in place after the first `link_resources` call on a store. The parsers never do this. Replacing or appending to `store.observations` triggers a rebuild, but editing an existing observation's identifiers in place would not.
- The memo is scoped to one Auditor and assumes `store` and `by_resource` are fixed after `__init__`, which is true for every current caller.
- The propagation loop still scans all `store.links` and `recreation_links` on each pass. It was left unchanged to keep semantics and scope minimal.
