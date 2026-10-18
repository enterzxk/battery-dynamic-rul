from pathlib import Path
import json,zlib,base64,hashlib,sys
O=Path(__file__).resolve().parent
dest=Path(sys.argv[1]).resolve();dest.mkdir(exist_ok=False)
for r in json.loads((O/'archive.json').read_text())['files']:
 p=(dest/r['path']).resolve();assert p.is_relative_to(dest)
 b=zlib.decompress(base64.b64decode(r['zlib_base64']));assert len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256']
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(b)
print('Original bytes SHA256 verified')
