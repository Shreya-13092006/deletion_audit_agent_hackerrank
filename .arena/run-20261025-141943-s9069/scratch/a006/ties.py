import sys; sys.path.insert(0,'code')
from pathlib import Path
from audit import config
from audit.pipeline import Auditor, load_cases
class T:
    def write(self,*a,**k): pass
a=Auditor(config.DATASET_DIR, T())
allc=load_cases(config.DATASET_DIR/'deletion_requests.csv')+load_cases(config.DATASET_DIR/'sample_deletion_requests.csv')
a.assign_workflow_resources(allc)
import pickle
by={c.case_id:c for c in allc}
for cid in ['case_03','case_21','case_25','case_26','case_27','case_28','case_04','case_23']:
    print(cid,'wf=',sorted(a.workflow_resources.get(cid,())),'tied=',sorted(a.tied_resources.get(cid,())), 'amb=',a.ambiguous_accounts.get(cid))
inv={}
for c,rs in a.tied_resources.items():
    for r in rs: inv.setdefault(r,[]).append(c)
for r in ['analytics_9406','analytics_5335','analytics_1895','analytics_4566','analytics_4574','analytics_6077']:
    owners=sorted(inv.get(r,[]))
    print(r,[(o,by[o].reported_status,by[o].audit_at[5:10],sorted(x for x in a.links_for(a.identity_for(by[o])[0],by[o].audit_at)[0] if x.split('_')[0] in('analytics','account'))) for o in owners])
