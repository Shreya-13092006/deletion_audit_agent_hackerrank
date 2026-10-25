"""Repository-relative paths, model settings and pipeline constants."""
from __future__ import annotations

import os
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = CODE_DIR.parent
DATASET_DIR = REPO_ROOT / "dataset"
CACHE_DIR = CODE_DIR / "cache"
TRAIL_PATH = CODE_DIR / "cache" / "audit_trail.jsonl"
USAGE_LEDGER = CODE_DIR / "cache" / "llm_usage.json"

# Model settings. The key is read from the environment only (never stored).
API_KEY_ENV = "ANTHROPIC_API_KEY"
GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
# Models are chosen by id prefix (gemini-* -> Gemini, claude-* -> Anthropic); env vars override.
INTENT_MODEL = os.environ.get("AUDIT_INTENT_MODEL", "gemini-3.5-flash-lite")
VISION_MODEL = os.environ.get("AUDIT_VISION_MODEL", "gemini-3.8-flash")
# Gemini thinking levels: 3.5 Flash-Lite supports minimal/low/medium/high (default minimal);
# 3.8 Flash supports low/medium/high (default medium). Source: ai.google.dev thinking docs, 2026-10-25.
INTENT_THINKING = os.environ.get("AUDIT_INTENT_THINKING", "minimal")
VISION_THINKING = os.environ.get("AUDIT_VISION_THINKING", "medium")
# USD per million tokens (input, output); output rate also applies to thinking tokens.
# Claude: claude-api model table cached 2026-10-06. Gemini: ai.google.dev pricing, 2026-10-25
# (3.8 Flash at its promotional rate until 2026-12-31, then 1.50 / 7.50).
MODEL_PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.8-flash": (0.75, 3.75),
}

# Workflow attribution: hours relative to reported_at in which the deletion workflow that
# produced the report performs each kind of operation (measured on the 32 public samples;
# see docs/dataset-observations.md). Used only for resources no evidence ties to a person.
WORKFLOW_WINDOWS = {
    "account": (-1.4, 0.25),        # primary-profile DELETE_RECORD, just before the report
    "succeeded": (-0.6, 0.05),      # REDACT/ANONYMIZE/DISABLE/BLOCK that completed before it
    "followup": (0.0, 2.0),         # failed/partial operations and state checks after it
}
# reported_status is derived from the primary-profile operation result (preferred first).
STATUS_RESULTS = {"COMPLETE": ("SUCCESS",), "PARTIALLY_COMPLETE": ("PARTIAL", "SUCCESS"),
                  "NOT_STARTED": ("FAILED",)}


def workflow_kind(row: dict) -> str | None:
    """Classify a system_activity row as a deletion-workflow operation kind, or None."""
    et, result = row["event_type"], row["reported_result"]
    if et.startswith("CHECK_"):
        return "followup"
    if row["source_system"] != "deletion_worker":
        return None
    if result == "SUCCESS" and et in ("REDACT_RECORD", "ANONYMIZE_RECORD", "DISABLE_DATA_FLOW",
                                      "BLOCK_RESTORE"):
        return "succeeded"
    return "followup"

# Freshness of state evidence: a reading older than this (relative to audit_at) does not
# establish the state at audit_at; ownership links are not limited. Every evidence file the
# public sample answers cite is at most 5.6 days older than its audit_at.
STATE_MAX_AGE_DAYS = float(os.environ.get("AUDIT_STATE_MAX_AGE_DAYS", "14"))

# ---- Agent loop (code/agent_main.py, audit/agent/) ------------------------------------------
# Hard per-case and per-run budgets. Batched tools close every open gap of one kind per call, so
# a 14-resource case needs ~10 calls; the limits leave headroom without allowing runaway loops.
AGENT_MAX_ITERATIONS = int(os.environ.get("AGENT_MAX_ITERATIONS", "24"))
AGENT_MAX_TOOL_CALLS = int(os.environ.get("AGENT_MAX_TOOL_CALLS", "40"))
AGENT_MAX_MODEL_CALLS_PER_CASE = int(os.environ.get("AGENT_MAX_MODEL_CALLS_PER_CASE", "8"))
AGENT_MAX_MODEL_CALLS_PER_RUN = int(os.environ.get("AGENT_MAX_MODEL_CALLS_PER_RUN", "400"))
# A COMPLETE answer that fails a proof gate (G2/G3/G4/G9) becomes INCOMPLETE with post-remediation
# checks. 0 keeps the answer and only flags it (reproduces the pre-gate baseline output).
AGENT_PROOF_DOWNGRADE = os.environ.get("AGENT_PROOF_DOWNGRADE", "1") != "0"
PLANNER_MODEL = os.environ.get("AUDIT_PLANNER_MODEL", "gemini-3.5-flash-lite")
PLANNER_THINKING = os.environ.get("AUDIT_PLANNER_THINKING", "minimal")
EVIDENCE_CARDS_PATH = CACHE_DIR / "evidence_cards.json"
CARD_SCHEMA_VERSION = 1

# Output ordering contract (problem_statement.md "Allowed Operations" table order).
PHASES = ["FINDING", "REMEDIATION", "VERIFICATION"]
OPERATION_ORDER = [
    "REPORT_REMAINING_RECORD", "REPORT_EXPOSED_PII", "REPORT_ACTIVE_DATA_FLOW", "REPORT_RESTORE_RISK",
    "DISABLE_DATA_FLOW", "BLOCK_RESTORE", "DELETE_RECORD", "REDACT_RECORD", "ANONYMIZE_RECORD",
    "VERIFY_RECORD_ABSENT", "VERIFY_RECORD_PRESENT", "VERIFY_RECORD_REDACTED", "VERIFY_RECORD_ANONYMIZED",
    "VERIFY_DATA_FLOW_DISABLED", "VERIFY_RESTORE_BLOCKED",
]
OPERATION_STATE = {
    "REPORT_REMAINING_RECORD": "PRESENT", "REPORT_EXPOSED_PII": "PRESENT",
    "REPORT_ACTIVE_DATA_FLOW": "ACTIVE", "REPORT_RESTORE_RISK": "ACTIVE",
    "DISABLE_DATA_FLOW": "DISABLED", "BLOCK_RESTORE": "BLOCKED", "DELETE_RECORD": "ABSENT",
    "REDACT_RECORD": "REDACTED", "ANONYMIZE_RECORD": "ANONYMIZED",
    "VERIFY_RECORD_ABSENT": "ABSENT", "VERIFY_RECORD_PRESENT": "PRESENT",
    "VERIFY_RECORD_REDACTED": "REDACTED", "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED",
    "VERIFY_DATA_FLOW_DISABLED": "DISABLED", "VERIFY_RESTORE_BLOCKED": "BLOCKED",
}
OPERATION_PHASE = {op: ("FINDING" if op.startswith("REPORT_") else
                        "VERIFICATION" if op.startswith("VERIFY_") else "REMEDIATION")
                   for op in OPERATION_ORDER}
