"""Read exact public validation predictions without models or raw battery data."""
from pathlib import Path
import json,base64,zlib,hashlib,struct,csv,sys
p=Path(sys.argv[1] if len(sys.argv)>1 else "published_predictions_columnar.json")
d=json.loads(p.read_text())
for cid,c in d["cells"].items():
 raw=zlib.decompress(base64.b64decode(c["zlib_base64"]))
 assert hashlib.sha256(raw).hexdigest()==c["values_sha256"] and len(raw)==c["rows"]*40
 with Path(cid+".decoded.csv").open("x",newline="") as f:
  w=csv.writer(f);w.writerow(["cell_id","origin","observed_event","true_RUL","arm"]+d["columns"])
  for i,v in enumerate(struct.iter_unpack("<5d",raw)):
   t=c["origin_start"]+i;w.writerow([cid,t,c["event_cycle"],c["event_cycle"]-t,d["arm"]]+list(v))
