import csv
from pathlib import Path
R=Path('dataset')
cases={r['case_id']:r for r in csv.DictReader(open(R/'deletion_requests.csv',encoding='utf-8-sig'))}
for id in ['case_23','case_536','case_547','case_548']:
 print(id, cases[id])
print('\nfailed account deletes')
for r in csv.DictReader(open(R/'system_activity.csv',encoding='utf-8-sig')):
 if r['event_type']=='DELETE_RECORD' and r['target_system']=='account_service' and r['reported_result']=='FAILED':
  if '2026-09-05' in r['event_time'] or r['resource_id'] in ['account_410','account_9155','account_7015']:
   print(r)
print('\nall 2026-09-05 account deletion activity 10:00-12:00')
for r in csv.DictReader(open(R/'system_activity.csv',encoding='utf-8-sig')):
 if r['event_type']=='DELETE_RECORD' and r['target_system']=='account_service' and '2026-09-05T10:'<=r['event_time']<='2026-09-05T12:': print(r)
