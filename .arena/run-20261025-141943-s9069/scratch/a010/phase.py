import sys, collections
sys.path.insert(0,'.')
from audit.config import DATASET_DIR, WORKFLOW_WINDOWS
from audit.pipeline import Auditor, load_cases, _ts
class T:
    def write(self,*a,**k): pass
    def flush(self): pass
a=Auditor(DATASET_DIR,T(),None)
allc=load_cases(DATASET_DIR/'deletion_requests.csv')+load_cases(DATASET_DIR/'sample_deletion_requests.csv')
a.assign_workflow_resources(allc)
act=a.store.activity
res=collections.defaultdict(list)
lo,hi=WORKFLOW_WINDOWS['account']
for c in allc:
    ident,_=a.identity_for(c)
    linked,_=a.links_for(ident,c.audit_at)
    rep=_ts(c.reported_at)
    accs=[]
    for r in linked:
        if r.startswith('account_'):
            for row in act.by_resource.get(r,[]):
                if row['event_type']=='DELETE_RECORD' and lo<=(_ts(row['event_time'])-rep).total_seconds()/3600<=hi:
                    accs.append(row)
    if len(accs)!=1: continue
    t0=_ts(accs[0]['event_time'])
    for r in linked:
        if r.startswith('account_'): continue
        for row in act.by_resource.get(r,[]):
            if row['source_system']!='deletion_worker' and not row['event_type'].startswith('CHECK_'): continue
            d=(_ts(row['event_time'])-t0).total_seconds()
            if abs(d)>4*3600: continue
            res[(row['event_type'],row['reported_result']=='SUCCESS')].append((int(d)%60, int(d)//60, c.case_id, r))
for k,v in sorted(res.items()):
    print(k, len(v), collections.Counter(x[0] for x in v).most_common(8))
