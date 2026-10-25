"""Shared fixtures for the agent tests: one real engine + evidence-card store per test run."""
from __future__ import annotations

import tempfile
from functools import lru_cache
from pathlib import Path

import helpers  # noqa: F401  (puts code/ on sys.path)

from audit import config
from audit.agent.cards import load_or_build
from audit.agent.loop import Budget, Orchestrator
from audit.agent.planner import RulePlanner
from audit.agent.tools import ToolContext, build_registry
from audit.pipeline import Auditor, load_cases
from audit.trail import AuditTrail

CARDS_TMP = Path(tempfile.mkdtemp()) / "evidence_cards.json"     # never touches code/cache


@lru_cache(maxsize=1)
def env():
    cards = load_or_build(config.DATASET_DIR, config.CACHE_DIR / "image_facts.json", CARDS_TMP)
    auditor = Auditor(config.DATASET_DIR, AuditTrail(None), None, store=cards.store)
    cases = load_cases(config.DATASET_DIR / "deletion_requests.csv") + \
        load_cases(config.DATASET_DIR / "sample_deletion_requests.csv")
    auditor.assign_workflow_resources(cases)
    ctx = ToolContext.build(auditor, config.DATASET_DIR, cards)
    return cards, auditor, ctx, {c.case_id: c for c in cases}


def orchestrator(planner=None, budget=None, registry=None, trail=None):
    cards, auditor, ctx, _ = env()
    registry = registry or build_registry()
    return Orchestrator(ctx, registry, planner or RulePlanner(registry), trail or AuditTrail(None),
                        budget or Budget())
