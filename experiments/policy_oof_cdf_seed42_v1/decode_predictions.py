from pathlib import Path
import json,zlib,base64,hashlib,sys
O=Path(__file__).resolve().parent
dest=Path(sys.argv[1]).resolve();dest.mkdir(exist_ok=False)
for rec in json.loads((O/'predictions_lossless.json').read_text())['files']:
 b=zlib.decompress(base64.b64decode(rec['zlib_base64']));assert len(b)==rec['bytes'] and hashlib.sha256(b).hexdigest()==rec['sha256']
 with (dest/rec['path']).open('xb') as f:f.write(b)
print('Original OOF and calibration CSV bytes verified. Reconstruct CDF from protocol and OOF residuals.')
