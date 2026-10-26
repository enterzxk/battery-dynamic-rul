import json,zlib,sys,hashlib
from pathlib import Path
d=Path(__file__).resolve().parent
x=json.loads(zlib.decompress((d/"archive.bin").read_bytes()))
if len(sys.argv)==1: print("\n".join(x))
else:
 p=sys.argv[1];b=x[p].encode("utf-8");v=json.loads((d/"validation.json").read_text());q=next(q for q in v["files"] if q["path"]==p);assert hashlib.sha256(b).hexdigest()==q["sha256"];sys.stdout.buffer.write(b)
