import csv, json, re
from pathlib import Path
root=Path('.')
ids=['account_004','audit_record_6645','audit_record_5569','analytics_9406','analytics_5335','analytics_1895','analytics_4566','analytics_4574','analytics_6077','account_410','account_9155']
exclude={'sample_output.csv'}
for rid in ids:
 hits=[]
 for base in [root/'dataset',root/'code/cache']:
  for p in base.rglob('*'):
   if not p.is_file() or p.name in exclude: continue
   try: text=p.read_text(encoding='utf-8',errors='ignore')
   except: continue
   if re.search(r'(?<![A-Za-z0-9_])'+re.escape(rid)+r'(?![A-Za-z0-9_])',text): hits.append(str(p))
 print(rid, len(hits), sorted(set(hits)))
print('\nmanifest evidence 92/94')
for r in csv.DictReader(open(root/'dataset/evidence_files.csv',encoding='utf-8-sig')):
 if r['file_id'] in ('evidence_92','evidence_94'): print(r)
print('\nanalytics records: snapshot + export')
for fn in ['customer_data_snapshot_bundle_20260917.json','service_resource_export_20260915_114455.json']:
 p=root/'dataset/evidence/records'/fn; data=json.loads(p.read_text(encoding='utf-8'))
 print(fn)
 def walk(x):
  if isinstance(x,dict):
   if x.get('resource_id','') in ids and str(x.get('resource_id','')).startswith('analytics_'): print(json.dumps(x,sort_keys=True))
   for v in x.values(): walk(v)
  elif isinstance(x,list):
   for v in x: walk(v)
 walk(data)
