import sys, collections, itertools
from pathlib import Path
from datetime import datetime
ROOT=Path(r'C:\Users\shoer\hackerrank-orchestrate-october26')
sys.path.insert(0,str(ROOT/'code'))
from audit.config import DATASET_DIR
from audit.pipeline import Auditor, load_cases
class T:
    def write(s,_e,**k): pass
    def flush(s): pass
a=Auditor(DATASET_DIR,T(),None); g=a.graph
cases=load_cases(DATASET_DIR/'deletion_requests.csv')+load_cases(DATASET_DIR/'sample_deletion_requests.csv')
owner=collections.defaultdict(set)
for o in a.store.observations:
    if o.state=='LINK': continue
    if o.emails or o.hashes or o.users: owner[o.resource_id]|=set(g.users_for(o.emails,o.hashes,o.users))
ts=lambda s: datetime.fromisoformat(s.replace('Z','+00:00'))
# user -> cases
ucase=collections.defaultdict(list)
for c in cases:
    us=g.resolve_email(c.email)
    if len(us)==1: ucase[us[0]].append(c)
dels=[r for r in a.store.activity.rows if r['event_type']=='DELETE_RECORD' and r['resource_id'].startswith('account_') and r['source_system']=='deletion_worker']
# attach known (case) to each delete: owner user with a case whose reported_at within window
lab=[]
for d in dels:
    us=owner.get(d['resource_id'],set())
    if len(us)!=1: continue
    u=next(iter(us))
    for c in ucase.get(u,[]):
        gap=(ts(d['event_time'])-ts(c.reported_at)).total_seconds()/3600
        if -1.4<=gap<=0.25: lab.append((d,c))
by=collections.defaultdict(list)
for d,c in lab: by[c.reported_at].append((d,c))
agree=dis=0; ex=[]
for k,v in by.items():
    for (d1,c1),(d2,c2) in itertools.combinations(v,2):
        if c1.requested_at==c2.requested_at: continue
        o1=d1['event_time']<d2['event_time']; o2=c1.requested_at<c2.requested_at
        if o1==o2: agree+=1
        else: dis+=1
print('labelled',len(lab),'batches',len(by),'requested_at order agree',agree,'disagree',dis)
# same for case_id numeric order
agree=dis=0
num=lambda c:int(c.case_id.split('_')[1])
for k,v in by.items():
    for (d1,c1),(d2,c2) in itertools.combinations(v,2):
        if (d1['event_time']<d2['event_time'])==(num(c1)<num(c2)): agree+=1
        else: dis+=1
print('case_id order agree',agree,'disagree',dis)
