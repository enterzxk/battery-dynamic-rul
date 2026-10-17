import pickle,zipfile,hashlib,io,json,math,collections
from pathlib import Path
R=Path("/home/yndx/zxk/rul")
class Deny(pickle.Unpickler):
 def find_class(self,m,n): raise pickle.UnpicklingError("BLOCKED_GLOBAL")
 def persistent_load(self,p): raise pickle.UnpicklingError("BLOCKED_PERSISTENT_ID")
def gettimes(o):
 return [[float(x) for x in c["time_in_s"]] for c in o["cycle_data"]]
v9bytes=(R/"data/raw/HUST/extracted_v9/HUST/HUST_1-8.pkl").read_bytes()
if hashlib.sha256(v9bytes).hexdigest()!="4eddc389fd9991acd24370616216bc234aa33665c9a1565e2e7b2184cd432908": raise SystemExit("v9 SHA mismatch")
o=Deny(io.BytesIO(v9bytes)).load(); a=gettimes(o); del o,v9bytes
with zipfile.ZipFile(R/"data/raw/HUST/HUST_v11.zip") as z: bbytes=z.read("HUST/HUST_1-8.pkl")
if hashlib.sha256(bbytes).hexdigest()!="5e952df3d8f00e32c8d11591e97fbdf79866f54d196618c88050aa0b407105e2": raise SystemExit("v11 SHA mismatch")
o=Deny(io.BytesIO(bbytes)).load(); b=gettimes(o); del o,bbytes
per=[]
for i,(x,y) in enumerate(zip(a,b),1):
 if len(x)!=len(y): per.append({"row":i,"unequal_lengths":[len(x),len(y)]}); continue
 ds=[u-v for u,v in zip(y,x)]
 cnt=collections.Counter(ds)
 per.append({"row":i,"length":len(x),"all_pairwise_equal":all(d==0 for d in ds),"delta_min":min(ds) if ds else None,"delta_max":max(ds) if ds else None,"delta_distinct":len(cnt),"dominant_delta_s":cnt.most_common(1)[0][0] if cnt else None,"dominant_delta_fraction":cnt.most_common(1)[0][1]/len(ds) if ds else None,"first_nonzero_pair":next((j+1 for j,d in enumerate(ds) if d!=0),None),"last_nonzero_pair":next((j+1 for j in range(len(ds)-1,-1,-1) if ds[j]!=0),None)})
ranges=[]
for row in per:
 ranges.append(row)
out={"cell":"HUST_1-8","restricted_unpickle_policy":"all globals and persistent IDs rejected; each object released before reading next","cycle_count":len(per),"all_curve_lengths_equal":all("unequal_lengths" not in r for r in per),"rows_1_167_exact":all(per[i-1]["all_pairwise_equal"] for i in range(1,168)),"rows_169_2285_constant_minus_36922s":all(per[i-1]["delta_min"]==per[i-1]["delta_max"]==-36922.0 for i in range(169,2286)),"row168_delta":per[167],"row169_delta":per[168],"row2285_delta":per[-1],"all_rows_with_constant_delta":sum(r.get("delta_distinct")==1 for r in per),"nonuniform_rows":[r for r in per if r.get("delta_distinct",0)>1],"per_cycle_summaries":per}
p=R/"reports/data_same_version_staging/hust_1-8_time_pairwise_delta_audit.json"
p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({k:v for k,v in out.items() if k=="cell" or k not in ("per_cycle_summaries","nonuniform_rows")},ensure_ascii=False,indent=2))
print("nonuniform_rows",json.dumps(out["nonuniform_rows"],ensure_ascii=False))
print("OUT="+str(p))
