import sys, csv
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
act=a.store.activity.rows
succ=[r for r in act if r['source_system']=='deletion_worker' and r['reported_result']=='SUCCESS' and r['event_type'] in ('REDACT_RECORD','ANONYMIZE_RECORD','DISABLE_DATA_FLOW','BLOCK_RESTORE')]
TOL=2
res=Counter(); amb=0
for x in succ:
    m=[y for y in succ if abs((ts(y['event_time'])-ts(x['event_time'])).total_seconds()-839)<=TOL]
    if len(m)>1: amb+=1
    for y in m:
        ox,oy=owners.get(x['resource_id'],set()),owners.get(y['resource_id'],set())
        k=('both' if ox and oy else 'one' if (ox or oy) else 'none')
        if k=='both': k+=('_same' if ox&oy else '_DIFF')
        res[k]+=1
        if k=='both_DIFF': print('CONFLICT',x['resource_id'],ox,y['resource_id'],oy)
print('839 pairs by ownership',res,'ambiguous anchors',amb)
# adjacent gaps
res2=Counter()
for x in succ:
    for y in succ:
        d=(ts(y['event_time'])-ts(x['event_time'])).total_seconds()
        for g in (390,449,1229,1288):
            if abs(d-g)<=TOL:
                ox,oy=owners.get(x['resource_id'],set()),owners.get(y['resource_id'],set())
                if ox and oy: res2[(g,'same' if ox&oy else 'DIFF')]+=1
print('other gaps both-owned',sorted(res2.items()))
