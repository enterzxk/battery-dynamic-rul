import pickle,zipfile,hashlib,io,json
from pathlib import Path
ROOT=Path("/home/yndx/zxk/rul")
class Deny(pickle.Unpickler):
 def find_class(self,m,n): raise pickle.UnpicklingError("BLOCKED_GLOBAL")
 def persistent_load(self,p): raise pickle.UnpicklingError("BLOCKED_PERSISTENT_ID")
def canon(x):
 if isinstance(x,dict): return {str(k):canon(v) for k,v in sorted(x.items(),key=lambda kv:str(kv[0]))}
 if isinstance(x,(list,tuple)): return [canon(v) for v in x]
 if isinstance(x,(str,int,float,bool)) or x is None: return x
 if isinstance(x,bytes): return {"bytes_hex":x.hex()}
 raise TypeError(type(x).__name__)
def sig(x):
 return hashlib.sha256(json.dumps(canon(x),sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=True).encode()).hexdigest()
def signatures(payload):
 obj=Deny(io.BytesIO(payload)).load()
 out={"top":{k:sig(v) for k,v in obj.items()},"cycles":[{k:sig(v) for k,v in c.items()} for c in obj["cycle_data"]]}
 del obj
 return out
with open(ROOT/"data/raw/HUST/extracted_v9/HUST/HUST_1-8.pkl","rb") as f: v9=signatures(f.read())
with zipfile.ZipFile(ROOT/"data/raw/HUST/HUST_v11.zip") as z: v11=signatures(z.read("HUST/HUST_1-8.pkl"))
top_changed=[k for k in sorted(set(v9["top"])|set(v11["top"])) if v9["top"].get(k)!=v11["top"].get(k)]
cy=[]
for i,(a,b) in enumerate(zip(v9["cycles"],v11["cycles"]),1):
 keys=[k for k in sorted(set(a)|set(b)) if a.get(k)!=b.get(k)]
 if keys: cy.append({"row":i,"cycle_number":i,"changed_fields":keys})
result={"top_changed_fields":top_changed,"cycle_row_count":len(v9["cycles"]),"changed_cycle_rows":cy,"method":"per-field SHA256 over canonical JSON primitive values; custom Unpickler rejects every global and persistent id; objects loaded one at a time"}
p=ROOT/"reports/data_same_version_staging/hust_1-8_v9_v11_field_diff.json"
p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(result,ensure_ascii=False,indent=2)); print("OUT="+str(p))
