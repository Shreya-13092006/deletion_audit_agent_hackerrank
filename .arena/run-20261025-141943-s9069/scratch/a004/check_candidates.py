import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict
R=Path.cwd(); sys.path.insert(0,str(R/'code'))
from audit.config import DATASET_DIR, WORKFLOW_WINDOWS, STATUS_RESULTS
from audit.pipeline import Auditor, load_cases, _ts
from audit.trail import AuditTrail
a=Auditor(DATASET_DIR,AuditTrail(None),None)
cases=load_cases(DATASET_DIR/'sample_deletion_requests.csv')
# candidate graph for all sample accounts per same rules
claimed=set()
for o in a.store.observations:
 if o.state!='LINK' and a.graph.users_for(o.emails,o.hashes,o.users): claimed.add(o.resource_id)
print('sample cases')
for c in cases:
 if c.case_id in ('case_23','case_536','case_547','case_548') or c.reported_status=='NOT_STARTED':
  vals=[]; rep=_ts(c.reported_at); lo,hi=WORKFLOW_WINDOWS['account']; allow=STATUS_RESULTS[c.reported_status]
  for row in a.store.activity.account_deletes:
   gap=(_ts(row['event_time'])-rep).total_seconds()/3600
   if row['resource_id'] not in claimed and row['event_time']<=c.audit_at and lo<=gap<=hi and row['reported_result'] in allow:
    vals.append((row['resource_id'],row['reported_result'],round(gap,3),row['activity_id']))
  print(c.case_id,c.email,c.reported_at,c.audit_at,c.reported_status, vals)
