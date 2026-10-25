"""Bounded orchestrator: plan -> act -> observe -> replan, then gates, then the case card."""
from __future__ import annotations

from dataclasses import dataclass

from ..config import AGENT_MAX_ITERATIONS, AGENT_MAX_TOOL_CALLS
from ..schema import Decision
from .gates import BLOCKING, run_gates
from .state import CaseState, ToolCallRecord


@dataclass
class Budget:
    max_iterations: int = AGENT_MAX_ITERATIONS
    max_tool_calls: int = AGENT_MAX_TOOL_CALLS


class Orchestrator:
    def __init__(self, ctx, registry: dict, planner, trail, budget: Budget | None = None):
        self.ctx, self.registry, self.planner, self.trail = ctx, registry, planner, trail
        self.budget = budget or Budget()
        self.stats = {"cases": 0, "tool_calls": 0, "effective_calls": 0, "fallbacks": 0,
                      "parity_diffs": 0, "unsupported_claims": 0, "contradictions": 0, "exhausted": 0,
                      "review": 0, "model_calls": 0, "planner_fallbacks": 0}

    def run(self, case) -> tuple[Decision, dict]:
        state = CaseState(case)
        cid = case.case_id
        while True:
            if not state.open_gaps and not state.decision_source and not state.not_applicable \
                    and any(k == "ACCOUNT" for k, _, _, _ in state.closed_gaps):
                # Every investigation gap is closed: the evidence is sufficient to decide.
                state.open("VERIFY")
            if not state.open_gaps:
                state.stop_reason = "sufficient: no open gaps" if state.decision_source else \
                    "no useful action: investigation ended without a decision"
                break
            if state.iterations >= self.budget.max_iterations or len(state.tool_calls) >= self.budget.max_tool_calls:
                state.exhausted, state.stop_reason = True, "budget exhausted"
                break
            remaining = self.budget.max_tool_calls - len(state.tool_calls)
            choice = self.planner.next(state, remaining) if self.planner.name == "gemini" else self.planner.next(state)
            state.iterations += 1
            if choice.planner == "rule_fallback":
                self.stats["planner_fallbacks"] += 1
            if choice.stop:
                state.stop_reason = f"no useful action: {choice.reason}"
                break
            tool = self.registry[choice.tool]
            result = tool.run(self.ctx, state, choice.targets)
            rec = ToolCallRecord(state.iterations, tool.name, list(choice.targets), choice.planner,
                                 choice.reason, result.new_facts, result.closed, result.opened,
                                 result.contradictions)
            state.tool_calls.append(rec)
            self.trail.write("tool_call", case_id=cid, **rec.as_dict())
            if result.stop:
                state.stop_reason = f"stop: {result.stop}"
                break

        if state.not_applicable:
            state.decision_status, state.decision_steps, state.decision_source = "NOT_APPLICABLE", [], "agent"
        elif state.exhausted or state.open_gaps or not state.decision_source:
            state.decision_source = "pending_fallback"

        gates, engine, unsupported = run_gates(self.ctx, state, state.decision_status or "INCOMPLETE",
                                               state.decision_steps, self.registry, self.planner)
        failed = [g for g in BLOCKING if not gates[g].startswith("pass")]
        if state.decision_source == "pending_fallback" or failed:
            if state.decision_source == "pending_fallback":
                # The loop stopped before producing a decision (budget or no applicable tool).
                state.flags.append("AGENT_BUDGET_EXHAUSTED" if state.exhausted else "AGENT_INVESTIGATION_INCOMPLETE")
            else:
                state.flags += [f"AGENT_GATE_FAIL:{g}" for g in failed]
                if "G8_parity" in failed:
                    self.stats["parity_diffs"] += 1
            state.decision_status, state.decision_steps = engine.status, engine.steps
            state.decision_source = "fallback"
            self.stats["fallbacks"] += 1
        state.gates = gates
        self.trail.write("agent_decision", case_id=cid, status=state.decision_status,
                         source=state.decision_source, iterations=state.iterations,
                         tool_calls=len(state.tool_calls), stop_reason=state.stop_reason,
                         gates_failed=failed, contradictions=len(state.contradictions))
        for c in state.contradictions:
            self.trail.write("contradiction", case_id=cid, **c)

        card = state.to_card()
        s = self.stats
        s["cases"] += 1
        s["tool_calls"] += len(state.tool_calls)
        s["effective_calls"] += sum(1 for t in state.tool_calls if t.new_facts or t.closed_gaps)
        s["unsupported_claims"] += unsupported if state.decision_source == "agent" else 0
        s["contradictions"] += len(state.contradictions)
        s["exhausted"] += state.exhausted
        s["review"] += card["review"]["required"]
        s["model_calls"] += state.model_calls
        return Decision(cid, state.decision_status, state.decision_steps, state.flags), card
