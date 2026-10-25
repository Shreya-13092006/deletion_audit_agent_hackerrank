import csv
from pathlib import Path
for p in [Path('dataset/sample_deletion_requests.csv')]:
 rows=list(csv.DictReader(open(p,encoding='utf-8-sig')))
 for r in rows:
  if r['case_id'] in ['case_03','case_04','case_18','case_20','case_21','case_23','case_25','case_26','case_27','case_28']:
   print(r['case_id'],r['email'],r['requested_at'],r['reported_at'],r['audit_at'])
print('Relevant activity')
for r in csv.DictReader(open('dataset/system_activity.csv',encoding='utf-8-sig')):
 if r['resource_id'] in ['analytics_9406','analytics_5335','analytics_1895','analytics_4566','analytics_4574','analytics_6077','account_410','account_9155']:
  print(r['activity_id'],r['event_time'],r['event_type'],r['resource_id'],r['reported_result'])
