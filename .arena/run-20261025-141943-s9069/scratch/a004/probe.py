import sys
from pathlib import Path
ROOT=Path(r"C:\Users\shoer\hackerrank-orchestrate-october26")
sys.path.insert(0,str(ROOT/"code"))
from audit.config import DATASET_DIR
from audit.pipeline import Auditor, load_cases
from audit.trail import AuditTrail
t=AuditTrail(None)
a=Auditor(DATASET_DIR,t,None)
allc=load_cases(DATASET_DIR/"deletion_requests.csv")+load_cases(DATASET_DIR/"sample_deletion_requests.csv")
a.assign_workflow_resources(allc)
for cid in sys.argv[1:]:
    print(cid,'wf=',sorted(a.workflow_resources.get(cid,[])),'tied=',sorted(a.tied_resources.get(cid,[])),'amb=',a.ambiguous_accounts.get(cid))
