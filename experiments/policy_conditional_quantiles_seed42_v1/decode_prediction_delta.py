from pathlib import Path
import argparse,json,csv,zlib,base64,hashlib,struct
p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--output',required=True);a=p.parse_args();O=Path(__file__).resolve().parent;d=json.loads((O/'prediction_delta.json').read_text());base=Path(a.base);assert hashlib.sha256(base.read_bytes()).hexdigest()==d['base_sha256'];rows=list(csv.DictReader(base.open()));raw=zlib.decompress(base64.b64decode(d['zlib_base64']));flat=struct.unpack('<'+str(d['rows']*2)+'d',raw);assert len(rows)==d['rows']
with Path(a.output).open('x',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0])+d['columns']);w.writeheader();w.writerows(dict(r,**{d['columns'][0]:flat[2*i],d['columns'][1]:flat[2*i+1]}) for i,r in enumerate(rows))
assert hashlib.sha256(Path(a.output).read_bytes()).hexdigest()==d['prediction_sha256'];print(d['prediction_sha256'])
