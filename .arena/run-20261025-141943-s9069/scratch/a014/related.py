import csv
rows=list(csv.DictReader(open('dataset/deletion_requests.csv',encoding='utf-8-sig')))
for r in rows:
 if r['case_id'] in ['case_536','case_547','case_548'] or 'thandiwe.m6866@zoho.com' in r['email']:
  print(r)
