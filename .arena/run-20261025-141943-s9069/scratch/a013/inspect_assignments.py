import sys
from pathlib import Path
sys.path.insert(0, str(Path('code').resolve()))
from audit.pipeline import Auditor, load_cases
from audit.trail import AuditTrail
from audit.config import CACHE_DIR, DATASET_DIR
from audit.llm import LLM

a=Auditor(DATASET_DIR, AuditTrail(Path('.arena/run-20261025-141943-s9069/scratch/a013/candidates.jsonl')), llm=LLM(CACHE_DIR/'intent_cache.json', enabled=False))
a.assign_workflow_resources(load_cases(DATASET_DIR/'deletion_requests.csv')+load_cases(DATASET_DIR/'sample_deletion_requests.csv'))
for cid in ['case_23','case_536','case_547','case_548']:
 print(cid, 'selected', sorted(a.workflow_resources.get(cid,set())), 'rivals', a.ambiguous_accounts.get(cid))
