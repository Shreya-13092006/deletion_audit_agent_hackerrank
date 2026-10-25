import sys
from pathlib import Path
sys.path.insert(0, str(Path('code').resolve()))
import main
from audit.pipeline import Auditor as BaseAuditor

class RefuseTiedAccountAuditor(BaseAuditor):
    def assign_workflow_resources(self, cases):
        super().assign_workflow_resources(cases)
        for cid in self.ambiguous_accounts:
            self.workflow_resources[cid] = {r for r in self.workflow_resources.get(cid, set())
                                             if not r.startswith('account_')}

main.Auditor = RefuseTiedAccountAuditor
main.run('sample', Path('.arena/run-20261025-141943-s9069/scratch/a013/tie_refusal.csv'), False)
