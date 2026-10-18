from pathlib import Path
import csv,json,struct,zlib,base64,hashlib,io,sys
O=Path(__file__).resolve().parent;d=json.loads((O/'prediction_delta.json').read_text());bp=O.parent/'matr_raw_heldout_calibration_seed42_v1/calibration_predictions.csv';assert hashlib.sha256(bp.read_bytes()).hexdigest()==d['base_sha256'];rr=list(csv.DictReader(bp.open()));b=zlib.decompress(base64.b64decode(d['payload']));assert len(b)==len(rr)*16==d['rows']*16;v=struct.unpack('<'+'d'*(len(rr)*2),b);s=io.StringIO(newline='');w=csv.DictWriter(s,fieldnames=list(rr[0])+['context_RUL_raw_log','context_RUL_prediction']);w.writeheader();w.writerows(dict(r,context_RUL_raw_log=v[2*i],context_RUL_prediction=v[2*i+1]) for i,r in enumerate(rr));out=s.getvalue().encode();assert hashlib.sha256(out).hexdigest()==d['reconstructed_csv_sha256']
if '--write' in sys.argv:
 with (O/'calibration_predictions.csv').open('xb') as f:f.write(out)
print('EXACT',d['reconstructed_csv_sha256'])
