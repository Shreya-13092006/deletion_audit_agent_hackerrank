## Recovery result
Sandbox: 20261025-validate-speedup   Work dir: C:\Users\shoer\hackerrank-orchestrate-october26\.claude\sandboxes\20261025-validate-speedup\work   Source HEAD/branch (from manifest): acb3dfca6e94e4803a26e72c49074a488de93c93/solution-baseline   Adopt: yes

### Metrics
| Metric | Baseline | After | Delta |
|---|---|---|---|
| sample status / step P/R/F1 / evidence / sequence | 1.000 / 0.995/0.948/0.971 / 1.000 / 0.688 | 1.000 / 0.995/0.948/0.971 / 1.000 / 0.688 | 0 |
| tests passed / custom cases passed | 187/187 OK / 6/6 | 192/192 OK (+5 new) / 6/6 | +5 tests |
| agent eval output sha256 (agent_main --no-llm) | bf634e2c1472cc4b2c699fb4b941ea335c7e9d8042c7fe490cad1ac54c8c0e37 | bf634e2c1472cc4b2c699fb4b941ea335c7e9d8042c7fe490cad1ac54c8c0e37 (2 runs identical) | none |
| engine eval output sha256 (main.py --no-llm) | 1bbba042d47fef1a8fb9fd2eae5182b113c3f8a91394ecb544f9aa4410b4b095 | 1bbba042d47fef1a8fb9fd2eae5182b113c3f8a91394ecb544f9aa4410b4b095 (2 runs identical) | none |
| sample predictions sha256 | 85d29f4b3062a64bd481c427d4d2224dab3b4d6e593bdfc9d94b3c96d5e38844 | 85d29f4b3062a64bd481c427d4d2224dab3b4d6e593bdfc9d94b3c96d5e38844 | none |
| agent cards.json | - | byte-identical to baseline (cmp) | none |
| validate_rows under cProfile (518-case agent run) | 1037 calls, cumtime 0.500 s, of which the per-call dictcomp took 0.440 s | 1037 calls, cumtime 0.044 s; map built once (dictcomp 1 call, 0.001 s) | -0.456 s (-91%) |
| agent run wall time (self-reported, unprofiled) | 1.6 s | 1.0 s | -0.6 s |

### Failures
| id | class | severity | certainty | stage | outcome | test added | eval rows changed |
|---|---|---|---|---|---|---|---|
| F1 | performance (validation/contract stage, no behavior defect) | minor | reproduced (cProfile: 1037 dict rebuilds over 4,011 rows, 0.440 s) | validate | fixed | code/tests/test_validate_activity_cache.py (5 tests) | 0 |

The fix: `activity_time_map(activity)` in code/audit/validate.py memoizes the activity_id -> event_time map
on the activity index (attribute `_validate_activity_time` = (rows list, len, map)). The cached map is reused only
while `activity.rows` is the same list object with the same length. A replaced or resized list rebuilds it, and
objects that reject attributes (slots/frozen) get a fresh map on every call. The comprehension is the same as
before (duplicate ids still resolve last-wins), the falsy-activity fallback is still `{}`, and the
manifest-first lookup in validate_rows is unchanged.

Regression test: `test_map_built_once_per_index` counts row-list iterations over 50 calls. It gets 1 after the fix.
Against BASE's validate.py the same harness counted 50, and the module has no `activity_time_map`, so the test
fails before the fix. Other tests check parity with the original per-call implementation for in-time, late,
manifest and unknown evidence, plus None activity, cache invalidation, a slotted object, and the real
ActivityIndex map.

Sandbox note: the copy excludes the generated root `output.csv`, so test_submitted_output_has_no_hard_failures
errored at first (FileNotFoundError). I put WORK/output.csv in place from the WORK agent run (sha bf634e2c...,
the same as the main project's output.csv). It is a generated file and the diff excludes it.

### Changes to adopt
- code/audit/validate.py: build the activity_id -> event_time map once per activity index (memoized, invalidated by list identity/length); same validation results.
- code/tests/test_validate_activity_cache.py: regression test for identical results and no per-call map rebuild.

### Limitations to document
- The memo cannot see in-place edits to existing activity rows' `activity_id`/`event_time` values that keep the list object and length the same. Nothing in the codebase does this, since ActivityIndex.rows is loaded once from system_activity.csv and then only read. If future code changes rows in place, it must assign a new list.
