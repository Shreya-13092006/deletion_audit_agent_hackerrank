"""Measure the sub-minute phase between a case's primary-account DELETE_RECORD and its other workflow rows."""
import json,csv,collections,sys
from datetime import datetime
R='C:/Users/shoer/hackerrank-orchestrate-october26/'
ts=lambda s:datetime.fromisoformat(s.replace('Z','+00:00'))
acts=list(csv.DictReader(open(R+'dataset/system_activity.csv',encoding='utf-8')))
byr=collections.defaultdict(list)
for a in acts: byr[a['resource_id']].append(a)
cases={}
for f in ['deletion_requests.csv','sample_deletion_requests.csv']:
    for r in csv.DictReader(open(R+'dataset/'+f,encoding='utf-8')): cases[r['case_id']]=r
dec={}
for f in ['audit_trail.jsonl','audit_trail_sample.jsonl']:
    for l in open(R+'code/cache/'+f,encoding='utf-8'):
        r=json.loads(l)
        if r.get('event')=='decision': dec[r['case_id']]=r
ties={}
for f in ['audit_trail.jsonl']:
    for l in open(R+'code/cache/'+f,encoding='utf-8'):
        r=json.loads(l)
        if r.get('event')=='workflow_attribution' and r['kind']=='account' and r.get('time_only_tie_with'): ties[r['case_id']]=1
dist=collections.Counter(); n=0
for cid,d in dec.items():
    if cid in ties: continue
    c=cases[cid]; rep=ts(c['reported_at'])
    accrows=[a for rid in d['resources'] if rid.startswith('account_') for a in byr[rid]
             if a['event_type']=='DELETE_RECORD' and -1.4<=(ts(a['event_time'])-rep).total_seconds()/3600<=0.25]
    if len(accrows)!=1: continue
    ta=ts(accrows[0]['event_time']); n+=1
    for rid in d['resources']:
        if rid.startswith('account_'): continue
        for a in byr[rid]:
            h=(ts(a['event_time'])-rep).total_seconds()/3600
            if -0.6<=h<=2.0 and (a['source_system']=='deletion_worker' or a['event_type'].startswith('CHECK_')):
                kind='succ' if (a['reported_result']=='SUCCESS' and a['event_type'] in ('REDACT_RECORD','ANONYMIZE_RECORD','DISABLE_DATA_FLOW','BLOCK_RESTORE')) else 'follow'
                dist[(kind,int((ts(a['event_time'])-ta).total_seconds())%60)]+=1
print('cases with one in-window account row',n)
for k,v in sorted(dist.items()): print(k,v)
