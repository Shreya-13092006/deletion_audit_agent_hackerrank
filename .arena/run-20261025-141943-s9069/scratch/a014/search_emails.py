import csv
from pathlib import Path
reqs=list(csv.DictReader(open('dataset/sample_deletion_requests.csv',encoding='utf-8-sig')))
for c in [x for x in reqs if x['case_id'] in ['case_18','case_20']]:
 print('\n',c['case_id'],c['email'])
 for p in Path('dataset').rglob('*'):
  if not p.is_file() or p.name=='sample_output.csv': continue
  try: s=p.read_text(encoding='utf-8',errors='ignore')
  except: continue
  hits=[(i,line.strip()[:250]) for i,line in enumerate(s.splitlines(),1) if c['email'] in line.lower()]
  if hits: print(p, hits[:10])
