## Validation verdict: APPROVE
Sandbox: 20261025-linker-index   Isolation: OK (verify run before and after measurement)
Validator-measured in WORK: 80/80 tests, 6/6 custom, samples 1.000 / 0.971 (P/R 0.995/0.948) / 0.688, evidence 1.000,
output.csv sha256 7a9683fd5215f5693e906d0af105a16430df90e621686a26be15b16755e3ea50 on 5 runs (byte-identical to baseline),
518 rows / 0 validation problems / 0 model calls.
Key checks: matches()/visible()/_no_conflict()/propagation byte-identical; index keys (email, hash, user_id) cover every
condition under which matches() can be true, so no match can be missed; candidate order reproduces the original stable sort;
memo key (user_id, emails, hashes, audit_at) complete; no scope creep; no expected answers or dataset touched.
Files safe to adopt: code/audit/linker.py, code/audit/pipeline.py, code/tests/test_linker_index.py
Notes: index not invalidated by in-place mutation of an observation's identifier sets (no code does this); memo assumes
store fixed per Auditor. Speed-up (1.67 s -> ~1.2-1.5 s) consistent but not independently timed against BASE.
Deviation disclosed by validator: wrote scratch diff files in the system temp dir (outside project and sandbox).
(Full verdict text returned to the parent session; summarized here by the parent.)
