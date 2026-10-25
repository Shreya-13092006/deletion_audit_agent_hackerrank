import sys
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict
ROOT=Path(r"C:\Users\shoer\hackerrank-orchestrate-october26")
sys.path.insert(0,str(ROOT/"code"))
from audit.config import DATASET_DIR
from audit.pipeline import Auditor
from audit.trail import AuditTrail
a=Auditor(DATASET_DIR,AuditTrail(None),None)
ts=lambda s: datetime.fromisoformat(s.replace('Z','+00:00'))
owners=defaultdict(set)
for o in a.store.observations:
    if o.state!="LINK":
        u=a.graph.users_for(o.emails,o.hashes,o.users)
        if u: owners[o.resource_id]|=set(u)
rows=[r for r in a.store.activity.rows if r['source_system']=='deletion_worker']
acc=[r for r in rows if r['resource_id'].startswith('account_') and r['event_type']=='DELETE_RECORD']
oth=[r for r in rows if not r['resource_id'].startswith('account_')]
same=Counter(); diff=Counter()
for x in acc:
    ox=owners.get(x['resource_id'])
    if not ox: continue
    for y in oth:
        oy=owners.get(y['resource_id'])
        d=(ts(y['event_time'])-ts(x['event_time'])).total_seconds()
        if not oy or not (0<d<4*3600): continue
        (same if ox&oy else diff)[int(d)%60]+=1
print('owned accounts',sum(1 for x in acc if owners.get(x['resource_id'])),'of',len(acc))
print('same-owner gap mod60',sorted(same.items()))
print('diff-owner gap mod60',sorted(diff.items()))
