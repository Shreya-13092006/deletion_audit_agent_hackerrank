import sys
sys.path.insert(0, r'C:\Users\shoer\hackerrank-orchestrate-october26\code')
from audit.config import CACHE_DIR, DATASET_DIR, WORKFLOW_WINDOWS, workflow_kind
from audit.llm import LLM
from audit.pipeline import Auditor, load_cases, _ts
from audit.trail import AuditTrail
from audit.parsers.common import *  # noqa
import audit.pipeline as P
trail = AuditTrail(r'C:\Users\shoer\hackerrank-orchestrate-october26\.arena\run-20261025-141943-s9069\scratch\a002\trail.jsonl')
llm = LLM(CACHE_DIR / "intent_cache.json", enabled=False, trail=trail)
a = Auditor(DATASET_DIR, trail, llm)
cases = load_cases(DATASET_DIR/'deletion_requests.csv') + load_cases(DATASET_DIR/'sample_deletion_requests.csv')
a.assign_workflow_resources(cases)
targets = sys.argv[1:]
case_linked={}
for c in cases:
    ident,_=a.identity_for(c); l,_=a.links_for(ident,c.audit_at); case_linked[c.case_id]=l
for row in a.store.activity.rows:
    if row['resource_id'] not in targets: continue
    kind=workflow_kind(row); lo,hi=WORKFLOW_WINDOWS[kind]; t=_ts(row['event_time'])
    sysid=P.system_for(row['resource_id'])
    print(row['activity_id'],row['resource_id'],row['event_time'],kind)
    for c in cases:
        gap=(t-_ts(c.reported_at)).total_seconds()/3600
        if lo<=gap<=hi and row['event_time']<=c.audit_at:
            ident,_=a.identity_for(c)
            auth,_,_=a.intent_for(c,case_linked[c.case_id])
            has=[r for r in case_linked[c.case_id] if P.system_for(r)==sysid]
            print('   ',c.case_id,c.reported_status,'auth' if auth else 'NA',round(gap,2),'own-system:',has)
print('--- cooccurrence')
from audit.state import visible
def co(c,rid):
    files={o.evidence_id for o in a.by_resource.get(rid,[]) if o.evidence_id in a.store.manifest and visible(o,c.audit_at)}
    mine={o.evidence_id for r in case_linked[c.case_id] for o in a.by_resource.get(r,[]) if o.evidence_id in a.store.manifest and visible(o,c.audit_at)}
    return sorted(files&mine)
byid={c.case_id:c for c in cases}
for rid,cs in [('analytics_9406',['case_03','case_44']),('analytics_5589',['case_03','case_44']),('analytics_5335',['case_21','case_23','case_546','case_547','case_548']),('analytics_1895',['case_24','case_25','case_26','case_549','case_550']),('analytics_4566',['case_24','case_25','case_26','case_549','case_550']),('analytics_4574',['case_27','case_28']),('analytics_6077',['case_27','case_28'])]:
    print(rid,{c:co(byid[c],rid) for c in cs})
for c in ['case_03','case_44','case_21','case_23','case_546','case_547','case_548','case_24','case_25','case_26','case_549','case_550','case_27','case_28']:
    print(c, byid[c].email, sorted(case_linked[c]))
