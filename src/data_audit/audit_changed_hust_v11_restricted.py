#!/usr/bin/env python3
# v11 仅变更文件的安全受限结构审计；find_class/persistent_load 对一切目标均拒绝。
import hashlib,io,json,pickle,zipfile,math
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path("/home/yndx/zxk/rul")
MEMBER="HUST/HUST_1-8.pkl"
V11=ROOT/"data/raw/HUST/HUST_v11.zip"
V9=ROOT/"data/raw/HUST/extracted_v9/HUST/HUST_1-8.pkl"
LABELS=ROOT/"data/raw/HUST/life_labels_v11/Life labels/HUST_labels.json"
OUT=ROOT/"reports/data_same_version_staging/hust_1-8_v11_changed_restricted_audit.json"
EXPECTED="5e952df3d8f00e32c8d11591e97fbdf79866f54d196618c88050aa0b407105e2"
def digest(b): return hashlib.sha256(b).hexdigest()
def finite(x): return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(float(x))
def primitive(x):
    todo=[x]; n=0
    while todo:
        v=todo.pop(); n+=1
        if isinstance(v,(str,bytes,int,float,bool,type(None))): continue
        if isinstance(v,dict):
            for k,y in v.items():
                if not isinstance(k,(str,int,float,bool,bytes,type(None))): return False,n,"bad_key:"+type(k).__name__
                todo.append(y)
        elif isinstance(v,(list,tuple,set,frozenset)): todo.extend(v)
        else: return False,n,"bad_value:"+type(v).__name__
    return True,n,None
class DenyAll(pickle.Unpickler):
    def find_class(self,module,name): raise pickle.UnpicklingError("BLOCKED_GLOBAL:%s.%s"%(module,name))
    def persistent_load(self,pid): raise pickle.UnpicklingError("BLOCKED_PERSISTENT_ID")
with zipfile.ZipFile(V11) as z:
    payload=z.read(MEMBER)
sha=digest(payload)
if sha!=EXPECTED: raise SystemExit("V11_SHA_MISMATCH:"+sha)
obj=DenyAll(io.BytesIO(payload)).load()
ok,n,issue=primitive(obj)
if not ok: raise SystemExit("NON_PRIMITIVE:"+str(issue))
if not isinstance(obj,dict) or not isinstance(obj.get("cycle_data"),list): raise SystemExit("UNEXPECTED_SCHEMA")
cycles=obj["cycle_data"]
nums=[c.get("cycle_number") for c in cycles if isinstance(c,dict) and isinstance(c.get("cycle_number"),int)]
gaps=sorted(set(range(min(nums),max(nums)+1))-set(nums)) if nums else []
nom=obj.get("nominal_capacity_in_Ah"); soc=obj.get("SOC_interval")
frac=(float(soc[1])-float(soc[0])) if isinstance(soc,(list,tuple)) and len(soc)==2 and all(finite(x) for x in soc) else None
threshold=0.8*float(nom)*frac if finite(nom) and frac is not None else None
first=first_nom=first_firstcycle=None; rows=[]
for i,c in enumerate(cycles,1):
    if not isinstance(c,dict): raise SystemExit("CYCLE_NOT_DICT:"+str(i))
    discharge=c.get("discharge_capacity_in_Ah")
    vals=[float(v) for v in discharge if finite(v)] if isinstance(discharge,(list,tuple)) else []
    m=max(vals) if vals else None
    if first is None and threshold is not None and m is not None and m<=threshold: first=i
    rows.append({"row_index_1based":i,"cycle_number":c.get("cycle_number"),"max_discharge_capacity_Ah":m,
      "curve_lengths":{k:(len(c[k]) if isinstance(c.get(k),(list,tuple)) else None) for k in ("current_in_A","voltage_in_V","charge_capacity_in_Ah","discharge_capacity_in_Ah","time_in_s","temperature_in_C","internal_resistance_in_ohm")}})
if rows:
    cap0=rows[0]["max_discharge_capacity_Ah"]
    if cap0 is not None:
        t=0.8*cap0
        first_firstcycle=next((r["row_index_1based"] for r in rows if r["max_discharge_capacity_Ah"] is not None and r["max_discharge_capacity_Ah"]<=t),None)
with zipfile.ZipFile(ROOT/"data/raw/HUST/Life_labels_v11.zip") as z:
    label=json.loads(z.read("Life labels/HUST_labels.json").decode("utf-8")).get("HUST_1-8.pkl")
v9sha=digest(V9.read_bytes())
result={"created_utc":datetime.now(timezone.utc).isoformat(),"member":MEMBER,"v11_sha256":sha,"expected_v11_sha256":EXPECTED,"v9_extracted_sha256":v9sha,"same_bytes_as_v9":sha==v9sha,"restricted_decode":"PASS","custom_unpickler":"find_class and persistent_load always raise; no globals allowlist","primitive_tree_only":ok,"primitive_nodes":n,"top_level_schema":{k:{"type":type(v).__name__,"length":len(v) if isinstance(v,(str,bytes,list,tuple,dict)) else None} for k,v in obj.items()},"cycle_count":len(cycles),"actual_cycle_number":{"count":len(nums),"min":min(nums) if nums else None,"max":max(nums) if nums else None,"gaps":gaps},"nominal_capacity_Ah":nom,"SOC_interval":soc,"threshold_0.8_nominal_Ah":threshold,"first_row_crossing_0.8_nominal":first,"first_row_crossing_0.8_first_cycle_capacity":first_firstcycle,"v11_life_label":label,"cycle_rows":rows,"fit_or_optimizer_steps":0}
OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({k:v for k,v in result.items() if k!="cycle_rows"},ensure_ascii=False,indent=2))
print("OUT="+str(OUT))
