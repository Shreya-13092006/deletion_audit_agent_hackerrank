import csv,json,os,re,glob
root='.'
blob=[]
for p in glob.glob('evidence/**/*',recursive=True):
    if os.path.isfile(p) and not p.endswith(('.pdf','.png')):
        blob.append(open(p,encoding='utf-8',errors='ignore').read())
for f in ['system_activity.csv','user_audit_log.csv','../code/cache/pdf_text.json','../code/cache/image_facts.json']:
    blob.append(open(f,encoding='utf-8',errors='ignore').read())
for p in glob.glob('../code/cache/ocr_raw/*.json'): blob.append(open(p,encoding='utf-8',errors='ignore').read())
B='\n'.join(blob)
for r in csv.DictReader(open('sample_output.csv',encoding='utf-8')):
    miss=[]
    for s in json.loads(r['steps_json']):
        rid=s['resource_id']
        if not re.search(re.escape(rid)+r'(?!\d)',B): miss.append((s['phase'],rid,s['operation'],s['evidence_id']))
    print(r['case_id'],r['deletion_status'],miss)
