from pathlib import Path
import json,zlib,base64,hashlib,sys
O=Path(__file__).resolve().parent
p=Path(sys.argv[1]);r=json.loads((O/'predictions_lossless.json').read_text())
b=zlib.decompress(base64.b64decode(r['zlib_base64']));assert len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256']
with p.open('xb') as f:f.write(b)
print('Original CSV bytes SHA256 verified')
