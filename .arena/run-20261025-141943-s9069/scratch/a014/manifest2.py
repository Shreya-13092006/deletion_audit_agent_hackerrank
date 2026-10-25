import csv
for r in csv.DictReader(open('dataset/evidence_files.csv',encoding='utf-8-sig')):
 if '20260917' in r['file_path'] or '20260915_114455' in r['file_path']:
  print(r)
