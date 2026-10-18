from pathlib import Path
import json,hashlib,zlib,base64,argparse
p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();d=json.loads((Path(__file__).resolve().parent/'per_cell_metrics_lossless.json').read_text());raw=zlib.decompress(base64.b64decode(d['zlib_base64']));assert hashlib.sha256(raw).hexdigest()==d['original_sha256']
with Path(a.output).open('xb') as f:f.write(raw)
print(d['original_sha256'])
