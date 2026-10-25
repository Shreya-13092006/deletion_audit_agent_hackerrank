"""Safety gates: no mutating tools, claim support, evidence time, parity fallback."""
import unittest

import agent_fixtures as af

from audit.agent import tools as T
from audit.agent.gates import claim_support, run_gates
from audit.agent.planner import RulePlanner
from audit.agent.state import CaseState
from audit.schema import Step


class GateTests(unittest.TestCase):
    def setUp(self):
        _, self.auditor, self.ctx, self.cases = af.env()

    def test_registry_refuses_mutating_tool(self):
        class Executor(T.Tool):
            name, gap, permission = "delete_for_real", "VERIFY", "execute_remediation"
        original = T.build_registry
        try:
            T.ResolveIdentity.permission = "execute_remediation"
            with self.assertRaises(PermissionError):
                original()
        finally:
            T.ResolveIdentity.permission = "read_evidence"
        self.assertTrue(all(t.permission == "read_evidence" for t in original().values()))

    def test_claim_support_rejects_evidence_not_about_the_resource(self):
        st = CaseState(self.cases["case_01"])
        st.linked = {"account_001": ("account_001", "identifier", "evidence_54")}
        ok = Step("VERIFICATION", "account_service", "account_001", "VERIFY_RECORD_ABSENT", "ABSENT", "evidence_54")
        wrong_file = Step("VERIFICATION", "account_service", "account_001", "VERIFY_RECORD_ABSENT", "ABSENT", "evidence_02")
        unlinked = Step("VERIFICATION", "account_service", "account_777", "VERIFY_RECORD_ABSENT", "ABSENT", "evidence_54")
        self.assertEqual(claim_support(self.ctx, st, [ok]), [])
        self.assertEqual(len(claim_support(self.ctx, st, [wrong_file, unlinked])), 2)

    def test_time_gate_rejects_citation_after_audit(self):
        case = self.cases["case_01"]
        late = max(self.auditor.store.manifest.values(), key=lambda m: m["captured_at"])["file_id"]
        st = CaseState(case)
        st.linked = {"account_001": ("account_001", "identifier", late)}
        steps = [Step("VERIFICATION", "account_service", "account_001", "VERIFY_RECORD_ABSENT", "ABSENT", late)]
        registry = T.build_registry()
        gates, _, _ = run_gates(self.ctx, st, "COMPLETE", steps, registry, RulePlanner(registry))
        self.assertTrue(gates["G2_time"].startswith("fail"))
        self.assertTrue(gates["G8_parity"].startswith("fail"))

    def test_sabotaged_decision_is_replaced_by_engine(self):
        class DropFirstStep(T.VerifyPlan):
            def run(self, ctx, state, targets):
                res = super().run(ctx, state, targets)
                state.decision_steps = state.decision_steps[1:]
                return res
        registry = T.build_registry()
        registry["verify_plan"] = DropFirstStep()
        orch = af.orchestrator(registry=registry)
        case = self.cases["case_12"]
        decision, card = orch.run(case)
        engine = self.auditor.audit(case)
        self.assertEqual((decision.status, decision.steps), (engine.status, engine.steps))
        self.assertEqual(card["decision"]["source"], "fallback")
        self.assertIn("AGENT_GATE_FAIL:G8_parity", card["flags"])
        self.assertEqual(orch.stats["parity_diffs"], 1)


if __name__ == "__main__":
    unittest.main()
