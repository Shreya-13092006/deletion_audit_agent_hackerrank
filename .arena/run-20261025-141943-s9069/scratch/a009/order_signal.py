"""Does activity order inside a workflow batch carry ownership information?
Uses only evidence-proven ownership (case cards, link reason != workflow_attribution)."""
import json, csv, itertools, collections, re
from datetime import datetime
R = 'C:/Users/shoer/hackerrank-orchestrate-october26/'
def ts(s): return datetime.fromisoformat(s.replace('Z', '+00:00'))
reqs = {}
for f in ['dataset/sample_deletion_requests.csv', 'dataset/deletion_requests.csv']:
    for r in csv.DictReader(open(R+f, encoding='utf-8')): reqs[r['case_id']] = r
WF = {'DELETE_RECORD','ANONYMIZE_RECORD','REDACT_RECORD','DISABLE_DATA_FLOW','BLOCK_RESTORE'}
act = collections.defaultdict(list)
for r in csv.DictReader(open(R+'dataset/system_activity.csv', encoding='utf-8')):
    if r['event_type'] in WF and r['source_system']=='deletion_worker': act[r['resource_id']].append(r)
own = []   # (case, rid, kind, event_time, reported_at)
for f in ['code/cache/case_cards.json', 'code/cache/case_cards_sample.json']:
    for cid, c in json.load(open(R+f, encoding='utf-8'))['cases'].items():
        rep = ts(reqs[cid]['reported_at'])
        for rid, v in c['resources'].items():
            if v['link']['reason'] == 'workflow_attribution': continue
            for a in act.get(rid, []):
                gap = (ts(a['event_time']) - rep).total_seconds()/3600
                if -1.5 <= gap <= 2.0:
                    own.append((cid, rid, rid.rsplit('_',1)[0], a['event_time'], reqs[cid]['reported_at']))
batches = collections.defaultdict(list)
for o in own: batches[(o[4], o[2])].append(o)
num = lambda s: int(re.findall(r'\d+', s)[-1])
feats = {'case_number': lambda o: num(o[0]), 'requested_at': lambda o: reqs[o[0]]['requested_at'],
         'resource_number': lambda o: num(o[1])}
for kind in sorted({k for _, k in batches}):
    tally = collections.Counter(); n = 0
    for (rep, k), lst in batches.items():
        if k != kind: continue
        for a, b in itertools.combinations(lst, 2):
            if a[0] == b[0] or a[3] == b[3]: continue
            first, second = (a, b) if a[3] < b[3] else (b, a)
            n += 1
            for name, f in feats.items():
                if f(first) == f(second): tally[name+'_tie'] += 1
                elif f(first) < f(second): tally[name] += 1
    print(f'{kind:10s} pairs={n:4d}', {k: f'{v}/{n}' for k, v in sorted(tally.items())})

import sys
if len(sys.argv) > 1:
    for (rep, k), lst in sorted(batches.items()):
        if k == sys.argv[1] and len({o[0] for o in lst}) > 1:
            print(rep, [(o[0], o[1], o[3][11:19], reqs[o[0]]['requested_at'][:10], reqs[o[0]]['reported_status'],
                         [a['reported_result'] for a in act[o[1]]]) for o in sorted(lst, key=lambda o: o[3])])
