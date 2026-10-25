# Dataset Observations — Ghost Data Still Exists

_Captured 2026-10-24 from participant-facing files under `dataset/` only. Each item names the file or query it came from._

## 1. Inventory

| File | Rows | Notes |
|---|---|---|
| `deletion_requests.csv` | 518 | `audit_at` from 2026-01-29 to 2026-10-01. Reported statuses: COMPLETE 254, PARTIALLY_COMPLETE 152, NOT_STARTED 112 |
| `sample_deletion_requests.csv` / `sample_output.csv` | 32 | 22 INCOMPLETE, 10 COMPLETE, **0 NOT_APPLICABLE**. Cases have 1–14 steps |
| `user_identities.csv` | 850 users | No duplicate emails. **`email_hash` = sha256(lowercased email)** for all 850 |
| `user_audit_log.csv` | 306 changes | Fields: email 107, email_hash 107, phone 92. Each email change comes with a hash change. Most users have 1–2 changes |
| `system_activity.csv` | 4,011 events | 2026-01-04 to 2026-10-01. Results: SUCCESS 2914, FAILED 721, PARTIAL 376 |
| `deletion_rules.csv` | 15 rules | See §6 |
| `evidence_files.csv` | 94 files | 24 SQL, 26 logs, 28 JSON, 1 TXT, 11 PNG, 4 PDF |

**Request emails:** 418 match a current email and 100 match only a **historical** email. 20 are UPPER/mixed case, so normalize by lowercasing.

## 2. SQL snapshots (24 files, all load cleanly with stdlib `sqlite3`)

There are four schema families:

1. **Typed inventory** (`customer_data_inventory_*.sql`, 12 files). Tables: `snapshot_scope(origin_system, captured_at)`, `customer_profiles`, `customer_search_documents`, `customer_analytics_profiles`, `support_records`, `customer_exports`, `connector_subscriptions(enabled)`, `backup_restore_entries(restore_allowed)` and `security_audit_records(subject_reference, retention_until)`.
   - `snapshot_scope` lists which systems the snapshot actually covers. A missing row only proves absence for systems in scope. `customer_data_inventory_20260905.sql` covers only `account_service` and has 0 rows.
   - Rows link by `customer_reference` (user_id) and/or email. Many rows are partly nulled, e.g. a profile with only an email and status `DELETION_PENDING`.
2. **Generic replica pairs** (`*_read_replica_*`, `*_regional_replicas_*`, `*_reporting_replica_*`, `customer_data_failover_replica_20260920`). Each has `customer_data_primary` plus one or two replica tables `(resource_id, origin_system, collection_name, record_json, updated_at)`. The payload is in `record_json`.
   - **Replica drift is real.** In `read_replica_20260921`, `account_994` (Diya Kapoor, ACTIVE) is missing from the primary but present in the replica. Sample case_16 reports it as REMAINING with evidence_05. **Treat a record in any replica as present.**
3. **Account failover** (`customer_accounts_failover_replica_20260902.sql`): `customer_profiles_primary` vs `customer_profiles_failover_replica`. `account_005` exists only in the failover table, which is case_05 (INCOMPLETE). An account absent from both tables is case_01, case_02 and case_04 (COMPLETE, citing evidence_54).
4. **Search primary** (`customer_search_primary_20260910.sql`): `search_documents_primary(display_name, email, source_resource_id)`. It contains near-miss decoys: Jonas Berg, Jonas Berglund and Joana Berg.

## 3. JSON / TXT records (29 files)

- **Snapshot bundles** (`customer_data_snapshot_bundle_*.json`, 12 files): `snapshots[]`, each with `data_store`, `collection`, its own `captured_at` (it can be earlier than the manifest time) and `records[]`. Collections seen:
  - account profiles, analytics reports, backup_catalog (`restore_allowed`), export jobs, connector_configurations (`enabled`, `mode`, `subject_selector`), search documents, security_audit_events, support `ticket_attachments` and `support_conversations` (`message_text` with embedded emails)
  - **legal_service.retained_order_records** (legal holds), **identity_service.deleted_customer_references** (tombstones with name, email, phone and email_hash fields)
  - `operational_record_history` (generic rows with record_type, result and lookup_value)
- **Service resource exports** (`service_resource_export_*.json`, 12 files): per-system lookups with `observed_at`, e.g. account `status_code` 200/404, analytics `profiles` with the remaining PII fields, `restore_entries`, `connectors`, `index_queries.hits`, `audit_records` and support `tickets`. Sample COMPLETE cases often cite these.
- **Generic "record_lookup" ledgers**: `connector_configurations_20260812.json`, `customer_export_manifest_20260409.json`, `security_audit_ledger_20261001.json` and `customer_account_handover_20261001.txt`. These all share one row shape: `system | resource_id | record_type | result | subject_reference`. **The file names don't describe the contents**, so parse by content, not by name.
- **Result vocabulary:** FOUND, NOT_FOUND, IDENTIFIABLE, ANONYMIZED, ACTIVE, DISABLED, BLOCKED, REDACTED.
- **Small focused files:** `customer_analytics_report_20260907.json` (analytics with nulled identifiers, i.e. ANONYMIZED proof), `customer_export_jobs_20260914.json` (`download_available`).

## 4. Logs (26 files), five formats needing one parser each

`key=value` (logfmt), JSON-after-timestamp, syslog RFC5424 with quoted kv, bracketed `[LEVEL] [service] [trace] event: kv`, and plain `record_lookup seq=N` lines.

- **Multi-line traces.** The lookup key (email, `user_N` or hash) appears on the `*_started` line and the `resource_id` with its outcome on the `*_completed` line, joined by `trace_id`. Joining by trace_id is required.
- **Noise lines** (dns_cache, secret_agent, queue_consumer, webhook_delivery, feature_flags, circuit_breaker) should be ignored.
- **PII signals:** `message_pii_scan`/`attachment_pii_scan` with `matched_value` and `detector=direct_identifier`; `deletion_marker_check marker_found=false`; connector reads with `enabled=`; restore policy reads with `restore_allowed=`.
- **Hash linkage.** case_12 links through `correlation_key=<sha256 of the OLD email>` on `analytics_9914`. **Precompute sha256 of every current and historical email.**
- **Order matters within a file.** `search_index_diagnostic_20260906.log` shows `account_8473` FOUND on 08-31 and NOT_FOUND on 09-06. Take the latest observation at or before `audit_at`.
- No log line is later than its file's `captured_at`. Still apply the per-line time filter as well as the per-file one.

## 5. PDFs and images

- **The 4 PDFs have a text layer** (`pdftotext` works, `/mingw64/bin/pdftotext` is available; `pypdf` isn't installed). No OCR is needed.
  - `delivery_correction_attachment.pdf` → support_001 belongs only to Priya Raman (case_07: DELETE attachment).
  - `security_retention_extract.pdf` → audit_record_003 for user_03 is retained until 2027-08-25.
  - `legal_retention_register_20260529.pdf` → disputed orders for user_08/12/17/21/24/29, retained until 2033.
  - `account_history_report_20260718.pdf` → statement NST-2026-0718-1842 for user_18.
- **The 11 PNGs are realistic admin-console screenshots** (backup vault, customer reference registry, connector console, search inspector, analytics profile, support ticket, export console, object storage, security explorer, marketing profile, account admin). The facts are in table cells and side panels (e.g. `backup_9287 → areed1433@gmail.com`, `user_17` retained reference). **They need a vision model or OCR. Extract all 11 once and cache the results as structured JSON.**

## 6. Policy (`deletion_rules.csv`) mapped to sample behavior

| Category | Action | Seen in samples as |
|---|---|---|
| USER_PROFILE, SECONDARY_IDENTIFIER, SEARCH_INDEX_ENTRY, CACHE_ENTRY, USER_EXPORT, MARKETING_PROFILE | DELETE | REPORT_REMAINING_RECORD, then DELETE_RECORD, then VERIFY_RECORD_ABSENT |
| SUPPORT_ATTACHMENT (subject-only) | DELETE | case_07 |
| SUPPORT_MESSAGE (shared context) | REDACT | REPORT_EXPOSED_PII, then REDACT_RECORD, then VERIFY_RECORD_REDACTED |
| EMAIL_DELIVERY_LOG (contains email) | REDACT | not in samples |
| ANALYTICS_PROFILE, PRODUCT_TELEMETRY (attributable) | ANONYMIZE | REPORT_EXPOSED_PII, then ANONYMIZE_RECORD, then VERIFY_RECORD_ANONYMIZED |
| SECURITY_AUDIT_LOG (in retention) | RETAIN | VERIFY_RECORD_PRESENT (always, if one exists for the user) |
| LEGAL_HOLD_RECORD (active) | RETAIN | VERIFY_RECORD_PRESENT (not in samples) |
| BACKUP_ARCHIVE (restore blockable) | RETAIN + block | REPORT_RESTORE_RISK, then BLOCK_RESTORE, then VERIFY_RESTORE_BLOCKED |
| Active connector | — | REPORT_ACTIVE_DATA_FLOW, then DISABLE_DATA_FLOW, then VERIFY_DATA_FLOW_DISABLED |
| ACCOUNT_TOMBSTONE | REDACT | REPORT_EXPOSED_PII (identity_service), then REDACT_RECORD, then VERIFY_RECORD_REDACTED (case_31, case_32) |

**Exception to note:** case_12 `analytics_9914` (a contact-lookup record keyed by the hash of the old email, with `email_opt_in=true`) is **DELETE**, not ANONYMIZE. It looks like it's treated as a marketing or secondary-identifier record. Category is decided per record, not per system.

## 7. Patterns in the gold answers (`sample_output.csv`)

- **Every authorized deletion verifies the primary account ABSENT**, and the **security audit record PRESENT** when one exists for the user. This holds even in INCOMPLETE cases where neither had a finding.
- **COMPLETE output = verification of every relevant resource in its compliant state.** Account absent, security present, plus redacted, anonymized, flow-disabled and restore-blocked where they apply. Each step cites evidence, typically **one comprehensive file** (evidence_92, evidence_94, evidence_51, evidence_54).
- **INCOMPLETE output:**
  - Findings cite one evidence file (often the latest bundle before `audit_at`).
  - Remediation covers only the violating resources.
  - Verification covers account, violating resources and retained records.
  - Remediation and verification steps have `evidence_id: ""`.
- **Sort order is confirmed by the samples:** phase, then operation-table order, then system_id, then resource_id. Example remediation order: DISABLE_DATA_FLOW, BLOCK_RESTORE, DELETE, REDACT, ANONYMIZE. So within findings, `REPORT_EXPOSED_PII analytics` comes before `support` alphabetically.
- **reported_status is uncorrelated with truth.** NOT_STARTED cases come out COMPLETE (case_25–28), and COMPLETE claims come out INCOMPLETE (case_05, 07, 10, …).
- **Evidence choice:** when several files prove the same fact, the gold cites one specific file. The rule seems to be the latest qualifying file at or before `audit_at` that contains the fact. **This is a scoring risk and needs a tie-break rule tested against the samples.**

## 8. `system_activity.csv` (claims, mostly without identity)

- Only **12 of 4,011** rows mention an email or user_id. Ten are `LINK_RESOURCE_IDENTITY` ("Data catalog linked account_X to email and user_N") and one is an attachment-ownership confirmation. **Activity gives a resource's history; evidence files link resources to people.**
- **Recreation signals:**
  - 31 × "Active connector repopulated downstream resource X"
  - 89 × CHECK_DATA_FLOW "remains enabled"
  - 28 × CHECK_RESTORE_ACCESS "can still be restored"
  - 1 × RESTORE_BACKUP "repopulated search_4882"
  - 55 replication checkpoints
- 721 FAILED and 376 PARTIAL results, plus vague success messages ("completed some internal work but could not confirm"). **Never treat SUCCESS as proof.**
- **10 × CLASSIFY_REQUEST "classified … as non-deletion".** These match the ~10 non-deletion requests below.

## 9. Request intent

There are 375 distinct texts built from 17 deletion templates in English, Spanish, Portuguese, French, Japanese and Korean (some cases repeat at stride 39).

**About 10 one-off non-deletion requests → NOT_APPLICABLE:**
- phone update
- stop promotional emails
- data portability download
- login reset
- surname fix
- **"Please remove me from marketing lists only"** (contains "remove", a trap)
- what data do you hold
- invoice copy
- change email
- copy of my information

A small LLM classifier or a careful rule set handles this. Keyword matching alone would misclassify the marketing-only request.

## 10. Implications for the approach

1. **Mostly deterministic.** Resource state comes from parseable structured evidence: SQL, JSON, five log formats and the TXT file. LLMs are only needed for intent classification (cheap, ~518 short texts, cacheable) and for the 11 screenshots (one-time vision extraction, cached).
2. **Pipeline:**
   1. Normalize all evidence into `Observation(file_id, observed_at, system_id, resource_id, category, state, identifiers{email, user_id, hash, phone, name})`.
   2. Resolve the identity set: current and historical emails, lowercased, their sha256 hashes, user_id, phones, name.
   3. Link observations to the user by any identifier, propagated through resource_id (once a resource is linked, its unlabeled observations follow).
   4. Keep only observations at or before `audit_at` and take the latest state per resource. Any replica showing a record means present.
   5. Apply the policy matrix to get the required treatment and compliance.
   6. Emit steps with the deterministic sort.
3. **The biggest accuracy levers:**
   - identity linking (historical emails and hashes, decoys with similar names)
   - category assignment per record
   - the evidence-ID selection rule
   - the time cutoff
4. **Evaluation:** score the 32 samples with exact-match status, step-set precision/recall/F1, field accuracy and sequence (exact list) accuracy. Hold out the samples as a check and avoid fitting to their IDs.
