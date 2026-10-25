32/32 can't be reached from the participant data without inventing IDs or guessing between people. The investigation found no fix for any of the 10 samples, but it did find one real parser bug that affects one eval case.

## 1. Gold vs predicted, per case

In all 10 cases the status matches, every shared step has the same evidence ID, and the order is correct. Each case misses exactly one step; case_23 has one wrong account instead.

## 2. Where each gold ID appears

| ID | Where it appears in participant data |
|---|---|
| `account_004`, `audit_record_6645`, `audit_record_5569` | **Nowhere.** Searched: every evidence file, SQL and JSON, decompressed PDF streams, PDF metadata, PNG text chunks (none exist), raw and parsed OCR, activity, and identity files. Also tried separator, number-only and OCR-misread variants. They exist only in `sample_output.csv`. |
| The 6 tied analytics records | In the snapshot bundle and in export `evidence_92`, with every identifier null. Each also has one anonymize activity row in a batch shared by 2–6 cases. |
| `account_410`, `account_9155`, `account_7015` | Each appears once, in its own FAILED delete activity row, and nowhere else. |
| Raw-OCR "410" hits | All pixel coordinates (`"y": 410`), not IDs. |

## 3. Hypotheses, ranked by remaining plausibility (none survives)

1. **A per-person feature in the anonymized analytics records.** Tested: lookup timing inside `evidence_92` (records sit next to other people's records); metric fingerprints (none identical); revenue totals (208.28 matches `analytics_514`, which belongs to user_129, a different person; with 8 fixed-price products, matching totals are coincidence); audience cohort (shared across people). Earlier rounds ruled out product names, batch ordering and status (best ordering rule 9/14, at chance). This is timing or content correlation, not ownership evidence.
2. **case_23 assignment.** Four NOT_STARTED cases (23, 536, 547, 548) compete for three FAILED account deletes, and nothing links any of the accounts to any requester. What would justify `account_410 → case_23`: a lookup trace, profile row, link activity or shared evidence file connecting `account_410` to `thandiwe.m6866@zoho.com` or user_23. None exists.
3. **A naming convention for case_04/18/20.** Ruled out: no request text contains a digit, and audit-record numbers never match the case's other IDs (0 of 24). The gold citing `evidence_54` for `account_004` shows the snapshot's scope is valid, not that the ID can be found.
4. **Parser, evaluator, card or alias bugs.** Of 2,060 resource IDs in raw evidence, 2,055 have evidence cards; the other five are link targets or noise, except one real parser omission (`retained_order_loaded`), which affects eval case_220 and none of the 10 samples.

**Not proposed:** any rule that would fill the 10 sample gaps. Each would need an invented ID (case_04/18/20) or a choice between people with equal evidence (7 ties), which would fit the samples and risk the hidden cases.
