import sys, csv, json
from pathlib import Path
ROOT=Path(r"C:/Users/shoer/hackerrank-orchestrate-october26")
sys.path.insert(0,str(ROOT/"code"))
from audit.config import DATASET_DIR, WORKFLOW_WINDOWS, workflow_kind
from audit.pipeline import Auditor, load_cases, _ts
class T:
    def write(self,*a,**k): pass
    def flush(self): pass
a=Auditor(DATASET_DIR,T())
ev=load_cases(DATASET_DIR/"deletion_requests.csv"); sm=load_cases(DATASET_DIR/"sample_deletion_requests.csv")
allc=ev+sm
a.assign_workflow_resources(allc)
gold={r['case_id']:json.loads(r['steps_json']) for r in csv.DictReader(open(DATASET_DIR/"sample_output.csv",encoding="utf-8"))}
bycase={c.case_id:c for c in allc}
# per tied resource -> cases
tied={}
for cid,rs in a.tied_resources.items():
    for r in rs: tied.setdefault(r,[]).append(cid)
acts={r['resource_id']:r for r in a.store.activity.rows}
def acct(cid): return sorted(x for x in a.workflow_resources.get(cid,()) if x.startswith('account_'))
def goldown(rid):
    return [c for c,s in gold.items() if any(x['resource_id']==rid for x in s)]
out=[]
for rid,cids in sorted(tied.items(), key=lambda kv: acts[kv[0]]['event_time']):
    row=acts[rid]
    print(row['activity_id'],row['event_time'],row['event_type'],rid,'gold:',goldown(rid))
    for cid in sorted(cids, key=lambda c: bycase[c].reported_at):
        c=bycase[cid]; ac=acct(cid)
        ar=[acts[x]['activity_id'] if x in acts else '-' for x in ac]
        print('    ',cid,c.reported_status,c.reported_at,ac,ar)
