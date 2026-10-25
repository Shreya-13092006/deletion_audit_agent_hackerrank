import sys
from pathlib import Path
ROOT=Path(r'C:\Users\shoer\hackerrank-orchestrate-october26')
sys.path.insert(0,str(ROOT/'code'))
from audit.config import DATASET_DIR
from audit.pipeline import Auditor, load_cases
class T:
    def __init__(s): s.ev=[]
    def write(s,_ev,**k): s.ev.append((_ev,k))
    def flush(s): pass
t=T(); a=Auditor(DATASET_DIR,t,None)
cases=load_cases(DATASET_DIR/'deletion_requests.csv')+load_cases(DATASET_DIR/'sample_deletion_requests.csv')
a.assign_workflow_resources(cases)
want={'analytics_9406','analytics_5589','analytics_5335','analytics_1895','analytics_4566','analytics_4574','analytics_6077'}
inv={}
for c,s in a.tied_resources.items():
    for r in s: inv.setdefault(r,[]).append(c)
for r in sorted(want): print(r,'tied between',sorted(inv.get(r,[])), 'assigned', [c for c,s in a.workflow_resources.items() if r in s])
for cid in ['case_21','case_23','case_536','case_547','case_548','case_03','case_25','case_26','case_27','case_28']:
    print(cid,'workflow',sorted(a.workflow_resources.get(cid,[])),'amb',a.ambiguous_accounts.get(cid))
for ev,k in t.ev:
    if ev=="workflow_attribution" and k.get('kind')=='account' and k['case_id'] in ('case_23','case_536','case_547','case_548','case_21'): print(k)
