import json,pickle,sys
from pathlib import Path
owner,gown=pickle.load(open(Path(__file__).parent/'owners.pkl','rb'))
d=json.load(open(sys.argv[1]))
out=[]
def walk(x,path):
    if isinstance(x,dict):
        if 'resource_id' in x:
            out.append((x.get('observed_at',''),x['resource_id'],path,{k:v for k,v in x.items() if k not in('resource_id','observed_at') and v is not None}))
        for k,v in x.items(): walk(v,path+'/'+k)
    elif isinstance(x,list):
        for v in x: walk(v,path)
walk(d,'')
for o in sorted(out):
    print(o[0],o[1],'own=',owner.get(o[1]),'gold=',gown.get(o[1]),str(o[3])[:90])
