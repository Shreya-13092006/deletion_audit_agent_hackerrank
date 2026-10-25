import sys, csv, json, pickle
from pathlib import Path
ROOT=Path(r"C:/Users/shoer/hackerrank-orchestrate-october26")
sys.path.insert(0,str(ROOT/"code"))
from audit.config import DATASET_DIR
from audit.pipeline import Auditor, load_cases, _ts
class T:
    def write(self,*a,**k): pass
    def flush(self): pass
a=Auditor(DATASET_DIR,T())
ev=load_cases(DATASET_DIR/"deletion_requests.csv"); sm=load_cases(DATASET_DIR/"sample_deletion_requests.csv")
allc=ev+sm
a.assign_workflow_resources(allc)
owner={}
for c in allc:
    ident,_=a.identity_for(c)
    linked,_=a.links_for(ident,c.audit_at)
    att=a.workflow_resources.get(c.case_id,set())
    for r in linked: owner.setdefault(r,[]).append(c.case_id)
    for r in att-linked: owner.setdefault(r,[]).append(c.case_id+'*')
gold={r['case_id']:json.loads(r['steps_json']) for r in csv.DictReader(open(DATASET_DIR/"sample_output.csv",encoding="utf-8"))}
gown={}
for cid,s in gold.items():
    for x in s: gown.setdefault(x['resource_id'],set()).add(cid)
pickle.dump((owner,{k:sorted(v) for k,v in gown.items()}),open(Path(__file__).parent/'owners.pkl','wb'))
rows=a.store.activity.rows
import sys
for rep in sys.argv[1:]:
    t=_ts(rep)
    print('=== reported_at',rep, [ (c.case_id,c.reported_status,c.requested_at[:16]) for c in allc if c.reported_at==rep])
    for r in rows:
        g=(_ts(r['event_time'])-t).total_seconds()/3600
        if -1.6<=g<=2.1 and r['source_system'] in('deletion_worker',) or (-1.6<=g<=2.1 and r['event_type'].startswith('CHECK')):
            print('  ',r['activity_id'],r['event_time'][11:19],r['event_type'],r['resource_id'],r['reported_result'],'own=',owner.get(r['resource_id']),'gold=',sorted(gown.get(r['resource_id'],[])))
