import csv, json, re
from pathlib import Path
root=Path('.')
targets=['account_004','audit_record_6645','audit_record_5569','analytics_9406','analytics_5335','analytics_1895','analytics_4566','analytics_4574','analytics_6077','account_410','account_9155']
roots=[root/'dataset',root/'code/cache']
for target in targets:
    hits=[]
    for base in roots:
      for p in base.rglob('*'):
        if not p.is_file() or p.name=='sample_output.csv': continue
        try: s=p.read_text(encoding='utf-8',errors='ignore')
        except Exception: continue
        for n,line in enumerate(s.splitlines(),1):
          if target in line: hits.append(f'{p}:{n}:{line[:300]}')
    print(f'## {target}: {len(hits)} hits')
    print('\n'.join(hits[:20]) or 'NONE')
print('## case requester details and related activity')
req=list(csv.DictReader(open(root/'dataset/sample_deletion_requests.csv',encoding='utf-8-sig')))
aud=list(csv.DictReader(open(root/'dataset/user_audit_log.csv',encoding='utf-8-sig')))
act=list(csv.DictReader(open(root/'dataset/system_activity.csv',encoding='utf-8-sig')))
for num in [3,4,18,20,21,23,25,26,27,28]:
 c=next(x for x in req if x['case_id']==f'case_{num:02d}')
 print('\n',c)
 matching=[]
 for row in act:
  if row.get('resource_id') in targets or (c['case_id']=='case_23' and row.get('resource_id') in ('account_410','account_9155')):
   if row.get('event_time','')<=c['audit_at']: matching.append(row)
 print('target activities <= cutoff:',matching)
print('## analytics file rows')
for p in [root/'dataset/evidence/records/customer_data_snapshot_bundle_20260917.json',root/'dataset/evidence/records/service_resource_export_20260915_114455.json']:
 d=json.loads(p.read_text(encoding='utf-8'))
 print('FILE',p)
 print(json.dumps(d,indent=2)[:18000])
