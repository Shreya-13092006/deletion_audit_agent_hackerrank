import sys, io, contextlib
from pathlib import Path
ROOT = Path(r"C:\Users\shoer\hackerrank-orchestrate-october26")
sys.path.insert(0, str(ROOT / "code"))
from audit.config import DATASET_DIR, CACHE_DIR, WORKFLOW_WINDOWS, workflow_kind
from audit.pipeline import Auditor, load_cases, _ts
from audit.aliases import system_for
class T:
    def write(self, *a, **k): pass
    def flush(self): pass
A = Auditor(DATASET_DIR, T(), None)
allc = load_cases(DATASET_DIR/"deletion_requests.csv") + load_cases(DATASET_DIR/"sample_deletion_requests.csv")
A.assign_workflow_resources(allc)
byid = {c.case_id: c for c in allc}
targets = sys.argv[1:]
for row in A.store.activity.rows:
    if row["resource_id"] not in targets: continue
    kind = workflow_kind(row)
    print(row["activity_id"], row["event_time"], row["event_type"], row["resource_id"], row["reported_result"], "kind", kind)
    lo, hi = WORKFLOW_WINDOWS[kind or "account"]
    t = _ts(row["event_time"])
    for c in allc:
        g = (t - _ts(c.reported_at)).total_seconds()/3600
        if -2 <= g <= 2:
            ident, _ = A.identity_for(c)
            linked, _ = A.links_for(ident, c.audit_at)
            sysl = sorted(r for r in linked if system_for(r) == system_for(row["resource_id"]))
            inwin = lo <= g <= hi and row["event_time"] <= c.audit_at
            print(f"   {c.case_id:10s} rep={c.reported_status:18s} gap={g:+.2f} inwin={inwin} audit={c.audit_at} same_sys_linked={sysl} wf={sorted(A.workflow_resources.get(c.case_id,()))} tied={sorted(A.tied_resources.get(c.case_id,()))}")
