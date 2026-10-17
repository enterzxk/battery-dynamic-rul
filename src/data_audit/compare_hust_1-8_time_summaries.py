import pickle,zipfile,hashlib,io,json,math
from pathlib import Path
ROOT=Path("/home/yndx/zxk/rul")
class Deny(pickle.Unpickler):
 def find_class(self,m,n): raise pickle.UnpicklingError("BLOCKED_GLOBAL")
 def persistent_load(self,p): raise pickle.UnpicklingError("BLOCKED_PERSISTENT_ID")
def digest(b): return hashlib.sha256(b).hexdigest()
def time_summary(obj):
 out=[]
 for idx,c in enumerate(obj["cycle_data"],1):
  a=c.get("time_in_s")
  vals=[float(x) for x in a if isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(float(x))] if isinstance(a,(list,tuple)) else []
  mono=sum(1 for x,y in zip(vals,vals[1:]) if y<x)
  dup=sum(1 for x,y in zip(vals,vals[1:]) if y==x)
  out.append({"row":idx,"cycle_number":c.get("cycle_number"),"length":len(a) if isinstance(a,(list,tuple)) else None,"finite_n":len(vals),"first":vals[0] if vals else None,"last":vals[-1] if vals else None,"min":min(vals) if vals else None,"max":max(vals) if vals else None,"backward_pairs":mono,"duplicate_pairs":dup})
 return out
v9path=ROOT/"data/raw/HUST/extracted_v9/HUST/HUST_1-8.pkl"
v11zip=ROOT/"data/raw/HUST/HUST_v11.zip"
v9bytes=v9path.read_bytes()
if digest(v9bytes)!="4eddc389fd9991acd24370616216bc234aa33665c9a1565e2e7b2184cd432908": raise SystemExit("v9 sha mismatch")
o=Deny(io.BytesIO(v9bytes)).load(); a=time_summary(o); del o,v9bytes
with zipfile.ZipFile(v11zip) as z: bbytes=z.read("HUST/HUST_1-8.pkl")
if digest(bbytes)!="5e952df3d8f00e32c8d11591e97fbdf79866f54d196618c88050aa0b407105e2": raise SystemExit("v11 sha mismatch")
o=Deny(io.BytesIO(bbytes)).load(); b=time_summary(o); del o,bbytes
changed=[(x,y) for x,y in zip(a,b) if x!=y]
offsets=[]
for x,y in zip(a,b):
 if x["length"] and x["length"]==y["length"] and x["first"] is not None and y["first"] is not None:
  offsets.append((y["first"]-x["first"], y["last"]-x["last"]))
deltas=[(u,v) for u,v in offsets]
constant=[p for p in deltas if p[0]==p[1]]
result={"cell":"HUST_1-8","v9_sha256":digest(v9path.read_bytes()),"v11_sha256":"5e952df3d8f00e32c8d11591e97fbdf79866f54d196618c88050aa0b407105e2","cycle_rows":len(a),"different_time_summary_rows":len(changed),"first_changed_cycle":next((x["row"] for x,y in zip(a,b) if x!=y),None),"last_changed_cycle":next((x["row"] for x,y in zip(reversed(a),reversed(b)) if x!=y),None),"summary_diff_row_indices":[x["row"] for x,y in changed],"same_time_length_rows":sum(x["length"]==y["length"] for x,y in zip(a,b)),"first_sample_delta_stats":{"n":len(deltas),"min_s":min(x[0] for x in deltas),"max_s":max(x[0] for x in deltas),"distinct_rounded_6dp":len(set(round(x[0],6) for x in deltas))},"last_sample_delta_stats":{"min_s":min(x[1] for x in deltas),"max_s":max(x[1] for x in deltas),"distinct_rounded_6dp":len(set(round(x[1],6) for x in deltas))},"constant_start_end_offset_cycles":len(constant),"examples":[{"cycle_number":x["cycle_number"],"v9_first_last":[x["first"],x["last"]],"v11_first_last":[y["first"],y["last"]],"lengths":[x["length"],y["length"]],"backward_pairs":[x["backward_pairs"],y["backward_pairs"]]} for x,y in zip(a,b) if x["row"] in [1,167,168,169,500,1000,1500,2000,2285]],"method":"restricted custom Unpickler; archive/extracted SHA checked; per-cycle time summaries only"}
out=ROOT/"reports/data_same_version_staging/hust_1-8_v9_v11_time_summary_diff.json"
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(result,ensure_ascii=False,indent=2)); print("OUT="+str(out))
