import csv
from datetime import datetime
from collections import defaultdict, Counter
ts=lambda s: datetime.fromisoformat(s.replace('Z','+00:00'))
act=list(csv.DictReader(open(r'C:\Users\shoer\hackerrank-orchestrate-october26\dataset\system_activity.csv',encoding='utf-8')))
succ=[a for a in act if a['source_system']=='deletion_worker' and a['reported_result']=='SUCCESS' and a['event_type'] in ('REDACT_RECORD','ANONYMIZE_RECORD','DISABLE_DATA_FLOW','BLOCK_RESTORE')]
print('succeeded policy actions',len(succ))
print(Counter((a['event_type'],a['resource_id'].rsplit('_',1)[0]) for a in succ))
print('minute-of-hour',Counter(ts(a['event_time']).minute for a in succ).most_common(12))
# pairwise gaps within 30 min
gaps=Counter()
for i,x in enumerate(succ):
    for y in succ:
        d=(ts(y['event_time'])-ts(x['event_time'])).total_seconds()
        if 0<d<1800: gaps[int(d)]+=1
print('most common gaps',gaps.most_common(15))
