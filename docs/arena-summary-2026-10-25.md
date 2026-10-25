# /arena --quick summary: "improve the 10 unresolved sample cases" (2026-10-25)

**Result: none.** The run was stopped during the spawn phase, before any competitor finished. There is no winning solution, and no rounds, attacks, judging or final check took place.

| Item | State |
|---|---|
| Run | `.arena/run-20261025-141943-s9069` (seed 9069, 16 agents, 4 rounds planned, 92 sub-agent calls) |
| Spawned | wave 1 (a001–a010) was launched and stopped by the user; wave 2 (a011–a016) was never launched |
| Solutions written | 0 |
| Leftovers | scratch files only. a008–a010 made sample predictions (`pred.csv`); a009 has an activity-order ownership probe; a010 has tie and phase probes; a007 copied `dataset/` into its scratch folder (about 0.9 M words) |
| Project changes | none; `output.csv` is still `bf634e2c…0e37` |

**What still stands:** the earlier investigation (`.arena/baseline.md`, `docs/reviews/evaluation-2026-10-25.md`):
- 3 cases are not discoverable: case_04, 18 and 20. Their IDs appear only in the gold file.
- 7 are ties between people with equal evidence: case_03, 21, 23 and 25–28.
- No evidence-backed, generalizable fix exists for any of them.

**Next options:**
- resume with `python3 .claude/skills/arena/bracket.py next`
- or delete `.arena/` (which also frees the scratch copy of the dataset) and keep it out of `code.zip`
