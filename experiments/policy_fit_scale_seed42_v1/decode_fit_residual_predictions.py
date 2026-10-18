from pathlib import Path
import json,hashlib,zlib,base64,argparse
p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();here=Path(__file__).resolve().parent;d=json.loads((here/'fit_residual_predictions_lossless.json').read_text());raw=zlib.decompress(base64.b64decode(d['zlib_base64']));assert hashlib.sha256(raw).hexdigest()==d['decoded_sha256']
with Path(a.output).open('xb') as f:f.write(raw)
print(d['decoded_sha256'])
