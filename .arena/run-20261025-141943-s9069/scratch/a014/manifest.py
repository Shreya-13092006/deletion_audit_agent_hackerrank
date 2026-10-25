import csv
for r in csv.DictReader(open('dataset/evidence_files.csv',encoding='utf-8-sig')):
 if r['file_id'] in ['evidence_54','evidence_92','evidence_93','evidence_94','evidence_51']:
  print(r)
