"""Bounded, gap-driven audit agent (ADR-002, docs/agent-loop-plan.md).

The agent decides *what to investigate next*; deterministic tools (thin wrappers over the
tested engine in audit/) decide *what is true*; deterministic gates decide *what may be written*.
"""
