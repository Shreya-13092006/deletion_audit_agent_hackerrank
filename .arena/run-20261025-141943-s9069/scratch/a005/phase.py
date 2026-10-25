import sys, collections, pickle
from pathlib import Path
from datetime import datetime
ROOT=Path(r'C:\Users\shoer\hackerrank-orchestrate-october26')
sys.path.insert(0,str(ROOT/'code'))
from audit.config import DATASET_DIR, CACHE_DIR
from audit.pipeline import Auditor
class T:
    def write(self,*a,**k): pass
    def flush(self): pass
a=Auditor(DATASET_DIR,T(),None)
g=a.graph
owner=collections.defaultdict(set)
for o in a.store.observations:
    if o.state=='LINK': continue
    us=set(g.users_for(o.emails,o.hashes,o.users)) if (o.emails or o.hashes or o.users) else set()
    owner[o.resource_id]|=us
ts=lambda s: datetime.fromisoformat(s.replace('Z','+00:00'))
rows=a.store.activity.rows
dels=[r for r in rows if r['event_type']=='DELETE_RECORD' and r['resource_id'].startswith('account_') and r['source_system']=='deletion_worker']
ops=[r for r in rows if r['source_system']=='deletion_worker' and r['event_type'] in ('ANONYMIZE_RECORD','REDACT_RECORD','DISABLE_DATA_FLOW','BLOCK_RESTORE') and not r['resource_id'].startswith('account_')]
stat=collections.defaultdict(collections.Counter); rival=collections.defaultdict(collections.Counter)
n=0
for w in ops:
    wu=owner.get(w['resource_id']) or set()
    if len(wu)!=1: continue
    cands=[d for d in dels if 0 < (ts(w['event_time'])-ts(d['event_time'])).total_seconds() <= 3*3600]
    true=[d for d in cands if owner.get(d['resource_id'])==wu]
    if len(true)!=1: continue
    n+=1
    ph=lambda d: int((ts(w['event_time'])-ts(d['event_time'])).total_seconds())%60
    stat[w['event_type']][ph(true[0])]+=1
    for d in cands:
        if d is not true[0]: rival[w['event_type']][ph(d)]+=1
print('pairs',n)
for k in stat: print(k,'TRUE',sorted(stat[k].items()),' RIVAL',sorted(rival[k].items())[:40])
pickle.dump(None,open(ROOT/'.arena/run-20261025-141943-s9069/scratch/a005/ok','wb'))
