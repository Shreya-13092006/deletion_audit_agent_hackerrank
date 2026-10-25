import sys
from pathlib import Path
sys.path.insert(0, str(Path('code').resolve()))
from audit.pipeline import Auditor, load_cases
from audit.trail import AuditTrail
from audit.config import CACHE_DIR, DATASET_DIR
from audit.llm import LLM

a=Auditor(DATASET_DIR, AuditTrail(Path('.arena/run-20261025-141943-s9069/scratch/a013/check.jsonl')), llm=LLM(CACHE_DIR/'intent_cache.json', enabled=False))
all_cases=load_cases(DATASET_DIR/'deletion_requests.csv')+load_cases(DATASET_DIR/'sample_deletion_requests.csv')
a.assign_workflow_resources(all_cases)
print('ambiguous accounts', a.ambiguous_accounts)
for c in load_cases(DATASET_DIR/'sample_deletion_requests.csv'):
    if c.case_id in a.ambiguous_accounts:
        d=a.audit(c)
        print(c.case_id, c.email, c.reported_at, c.reported_status, 'selected',a.workflow_resources.get(c.case_id), 'rivals',a.ambiguous_accounts[c.case_id], 'flags',d.flags)
