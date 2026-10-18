from pathlib import Path
import json,zlib,base64,hashlib
root=Path(__file__).resolve().parent
d={'files':sum([json.loads(p.read_text())['files'] for p in sorted(root.glob('published_prediction_csvs_part*.json'))],[])}
assert len(d['files'])==19
for item in d['files']:
 p=root/item['path'];raw=zlib.decompress(base64.b64decode(item['zlib_base64']))
 assert len(raw)==item['bytes'] and hashlib.sha256(raw).hexdigest()==item['sha256']
 p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:p.write_bytes(raw)
print('Verified exact original CSV bytes:',len(d['files']))
