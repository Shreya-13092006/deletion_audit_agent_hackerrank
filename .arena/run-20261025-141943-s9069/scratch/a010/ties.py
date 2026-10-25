import sys
sys.path.insert(0,'.')
from audit.config import DATASET_DIR
from audit.pipeline import Auditor, load_cases
class T:
    def write(self,*a,**k): pass
    def flush(self): pass
a=Auditor(DATASET_DIR,T(),None)
allc=load_cases(DATASET_DIR/'deletion_requests.csv')+load_cases(DATASET_DIR/'sample_deletion_requests.csv')
a.assign_workflow_resources(allc)
byid={c.case_id:c for c in allc}
import collections
groups=collections.defaultdict(set)
for cid,rs in a.tied_resources.items():
    for r in rs: groups[r].add(cid)
# cluster
seen=set()
for r,cs in sorted(groups.items()):
    print(r, sorted(cs))
print(len(groups))
