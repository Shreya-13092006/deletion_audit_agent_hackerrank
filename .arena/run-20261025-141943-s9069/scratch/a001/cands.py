import sys, json
from pathlib import Path
ROOT=Path(r"C:/Users/shoer/hackerrank-orchestrate-october26")
sys.path.insert(0,str(ROOT/"code"))
from audit.config import DATASET_DIR
from audit.pipeline import Auditor, load_cases
class T:
    def __init__(s): s.rows=[]
    def write(s,*a,**k): s.rows.append((a,k))
    def flush(s): pass
tr=T()
a=Auditor(DATASET_DIR,tr)
allc=load_cases(DATASET_DIR/"deletion_requests.csv")+load_cases(DATASET_DIR/"sample_deletion_requests.csv")
a.assign_workflow_resources(allc)
by={c.case_id:c for c in allc}
for cid in sys.argv[1:]:
    c=by[cid]; ident,fl=a.identity_for(c); linked,_=a.links_for(ident,c.audit_at)
    print(cid,c.email,c.reported_status,'req',c.requested_at,'rep',c.reported_at,'audit',c.audit_at,ident.user_id,fl)
    print('   linked',sorted(linked)); print('   attributed',sorted(a.workflow_resources.get(cid,())),'rivals',a.ambiguous_accounts.get(cid),'tied',sorted(a.tied_resources.get(cid,())))
    print('   text:',c.request_text[:120])
for args,k in tr.rows:
    if k.get('kind')=='account' and k.get('case_id') in sys.argv[1:]: print(k)
