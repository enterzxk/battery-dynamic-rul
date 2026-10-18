from pathlib import Path
import json,zlib,base64,csv,io,hashlib
O=Path(__file__).parent;d=json.loads((O/'capacity_prediction_delta.json').read_text());a=json.loads((O/d['source_archive']).read_text());raw=zlib.decompress(base64.b64decode(a['payload']));assert hashlib.sha256(raw).hexdigest()==d['source_CSV_sha256'];rows=list(csv.DictReader(io.StringIO(raw.decode(),newline='')));v=json.loads(zlib.decompress(base64.b64decode(d['payload'])));assert len(rows)==len(v)==d['rows']
for r,x in zip(rows,v):r[d['column']]=float(x)
s=io.StringIO(newline='');w=csv.DictWriter(s,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows);b=s.getvalue().encode();assert len(b)==d['restored_bytes'] and hashlib.sha256(b).hexdigest()==d['restored_sha256'];p=O/d['restored_file']
if p.exists():assert p.read_bytes()==b
else:p.open('xb').write(b)
print('Exact original capacity-v2 prediction CSV verified')
