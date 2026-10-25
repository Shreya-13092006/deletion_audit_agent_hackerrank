"""Bounded orchestrator: plan -> act -> observe -> replan, then gates, then the case card."""
from __future__ import annotations

from dataclasses import dataclass

from ..config import AGENT_MAX_ITERATIONS, AGENT_MAX_TOOL_CALLS, AGENT_PROOF_DOWNGRADE
from ..schema import Decision
from .gates import FALLBACK_GATES, PROOF_GATES, downgrade, proof_gates, run_gates
from .ownership import (attribution_conflicts, evidence_gaps, failed_claim_conflicts, g10_ownership,
                        omission_scope_flags, policy_category_conflicts, step_audit)
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
                      "review": 0, "model_calls": 0, "planner_fallbacks": 0, "proof_downgrades": 0,
                      "unsupported_findings": 0, "unresolved_contradictions": 0, "no_progress": 0,
                      "g10_unproven_findings": 0, "omission_scope_flags": 0, "ownership_tiers": {},
                      "evidence_gaps": {}}

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
            if not (result.closed or result.opened or result.new_facts):
                # A call that changed nothing would be repeated forever: stop, fall back safely.
                state.stop_reason, state.no_progress = f"no progress: {tool.name}", True
                break

        if state.not_applicable:
            state.decision_status, state.decision_steps, state.decision_source = "NOT_APPLICABLE", [], "agent"
        elif state.exhausted or state.open_gaps or not state.decision_source or state.no_progress:
            state.decision_source = "pending_fallback"

        gates, engine, unsupported, engine_basis, accounting = run_gates(
            self.ctx, state, state.decision_status or "INCOMPLETE", state.decision_steps, self.registry,
            self.planner)
        failed = [g for g in FALLBACK_GATES if not gates[g].startswith("pass")]
        linked, primary, items = set(state.linked), state.primary, state.plan_items
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
            # The engine answer is not trusted blindly: its proof gates are re-run below.
            linked, primary, items = engine_basis
            proof, unsupported, accounting, _ = proof_gates(self.ctx, state, engine.status, engine.steps,
                                                            linked, primary)
            gates.update({f"{g}": v for g, v in proof.items()})
        proof_failed = [g for g in PROOF_GATES if not gates[g].startswith("pass")]
        if proof_failed and state.decision_status == "COMPLETE" and not AGENT_PROOF_DOWNGRADE:
            state.flags += [f"AGENT_UNSUPPORTED_COMPLETE:{g}" for g in proof_failed]
            self.stats["unsupported_findings"] += 1
        elif proof_failed and state.decision_status == "COMPLETE":
            failures = state.proof_failures
            state.decision_status = "INCOMPLETE"
            state.decision_steps = downgrade(self.ctx, state, items, failures, linked)
            state.decision_source += "+proof_downgrade"
            state.flags += [f"AGENT_PROOF_DOWNGRADE:{g}" for g in proof_failed]
            gates["downgrade"] = "COMPLETE->INCOMPLETE: " + "; ".join(failures[:8])
            self.stats["proof_downgrades"] += 1
        elif proof_failed and state.decision_status == "INCOMPLETE":
            # Cannot be made safer automatically: keep the answer, send it to a human.
            state.flags += [f"AGENT_UNSUPPORTED_CLAIM:{g}" for g in proof_failed]
            self.stats["unsupported_findings"] += 1
        state.proof_accounting = accounting
        # Two separate questions per final step (ownership, state); annotation only - G10 and the
        # omission-scope check flag for review / report, they never change the decision.
        state.step_audit = step_audit(self.ctx, state, state.decision_steps)
        unproven = g10_ownership(state.step_audit)
        gates["G10_finding_ownership"] = "pass" if not unproven else "fail:" + "; ".join(unproven[:5])
        if unproven:
            state.flags.append("AGENT_OWNERSHIP_UNPROVEN_FINDING")
        scope = omission_scope_flags(state.step_audit)
        gates["G11_omission_scope"] = "pass" if not scope else "flag:" + "; ".join(scope[:5])
        state.flags += [f"OMISSION_SCOPE_REVIEW:{x}" for x in scope]
        conflicts = failed_claim_conflicts(self.ctx.auditor, state, state.step_audit)
        state.contradictions += conflicts
        state.flags += sorted({f"FAILED_CLAIM_VS_OMISSION:{c['resource_id']}" for c in conflicts})
        state.evidence_gaps = evidence_gaps(self.ctx, state)
        attribution = attribution_conflicts(self.ctx.auditor, state, conflicts)
        state.evidence_gaps += attribution
        state.flags += [f"ACCOUNT_ATTRIBUTION_REVIEW:{x['resource_id']}" for x in attribution]
        category_conflicts = policy_category_conflicts(self.ctx.auditor, state.linked, state.case.audit_at)
        state.evidence_gaps += category_conflicts
        state.flags += [f"RECORD_CATEGORY_CONFLICT:{x['resource_id']}" for x in category_conflicts]
        state.gates = gates
        self.trail.write("agent_decision", case_id=cid, status=state.decision_status,
                         source=state.decision_source, iterations=state.iterations,
                         tool_calls=len(state.tool_calls), stop_reason=state.stop_reason,
                         gates_failed=failed, proof_failed=proof_failed,
                         contradictions=len(state.contradictions))
        for c in state.contradictions:
            self.trail.write("contradiction", case_id=cid, **c)

        card = state.to_card()
        s = self.stats
        s["cases"] += 1
        s["tool_calls"] += len(state.tool_calls)
        s["effective_calls"] += sum(1 for t in state.tool_calls if t.new_facts or t.closed_gaps)
        s["unsupported_claims"] += unsupported if isinstance(unsupported, int) else len(unsupported)
        s["contradictions"] += len(state.contradictions)
        s["exhausted"] += state.exhausted
        s["review"] += card["review"]["required"]
        s["model_calls"] += state.model_calls
        s["no_progress"] += state.no_progress
        s["g10_unproven_findings"] += len(unproven)
        s["omission_scope_flags"] += len(scope)
        s["failed_claim_vs_omission"] = s.get("failed_claim_vs_omission", 0) + bool(conflicts)
        for x in state.step_audit:
            t = x["ownership"]["tier"]
            s["ownership_tiers"][t] = s["ownership_tiers"].get(t, 0) + 1
        for gap in state.evidence_gaps:
            s["evidence_gaps"][gap["kind"]] = s["evidence_gaps"].get(gap["kind"], 0) + 1
        s["unresolved_contradictions"] += sum(1 for c in state.contradictions if c["resolution"] == "unresolved")
        return Decision(cid, state.decision_status, state.decision_steps, state.flags), card
