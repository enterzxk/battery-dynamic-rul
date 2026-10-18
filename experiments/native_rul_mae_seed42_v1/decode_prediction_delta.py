"""Recover exact new prediction CSV from prior public CSV and lossless double column."""
from pathlib import Path
import json,csv,struct,zlib,base64,hashlib,io,sys
O=Path(__file__).resolve().parent
D=json.loads((O/'prediction_delta.json').read_text())
B=O.parent/'matr_raw_heldout_calibration_seed42_v1/calibration_predictions.csv'
assert hashlib.sha256(B.read_bytes()).hexdigest()==D['base_sha256']
rr=list(csv.DictReader(B.open()));buf=zlib.decompress(base64.b64decode(D['raw_f64le_zlib_base64']));assert len(buf)==len(rr)*8==D['rows']*8
raw=struct.unpack('<'+'d'*len(rr),buf);s=io.StringIO(newline='');w=csv.DictWriter(s,fieldnames=list(rr[0])+['native_RUL_raw','native_RUL_prediction']);w.writeheader()
w.writerows(dict(r,native_RUL_raw=a,native_RUL_prediction=max(0.,a)) for r,a in zip(rr,raw));out=s.getvalue().encode();assert hashlib.sha256(out).hexdigest()==D['reconstructed_csv_sha256']
if '--verify-only' not in sys.argv:
 with (O/'calibration_predictions.csv').open('xb') as f:f.write(out)
print('EXACT_CSV_SHA256',hashlib.sha256(out).hexdigest())
