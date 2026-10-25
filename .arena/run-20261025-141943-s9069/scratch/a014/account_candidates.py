import csv
for r in csv.DictReader(open('dataset/system_activity.csv',encoding='utf-8-sig')):
 if r['target_system']=='account_service' and r['event_type']=='DELETE_RECORD' and r['event_time'].startswith('2026-09-05'):
  print(r)
print('\nAll related eval requests')
for r in csv.DictReader(open('dataset/deletion_requests.csv',encoding='utf-8-sig')):
 if r['reported_at']=='2026-09-05T12:00:00Z':
  print(r['case_id'],r['email'],r['reported_status'],r['request_text'])
