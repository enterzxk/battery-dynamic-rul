from pathlib import Path
import json,zlib,base64,hashlib
p=Path(__file__).resolve().parent
a=json.loads((p/'archive.json').read_text());b=zlib.decompress(base64.b64decode(a['payload']));assert hashlib.sha256(b).hexdigest()==a['sha256']
with (p/'decoded_predictions.csv').open('xb') as f:f.write(b)
