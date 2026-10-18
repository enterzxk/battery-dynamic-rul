from pathlib import Path
import json,zlib,base64,hashlib,sys
O=Path(__file__).resolve().parent
for x in json.loads((O/'examples_lossless.json').read_text())['items']:
 raw=zlib.decompress(base64.b64decode(x['zlib_base64']));assert len(raw)==x['bytes'] and hashlib.sha256(raw).hexdigest()==x['sha256']
 if '--output-dir' in sys.argv:
  root=Path(sys.argv[sys.argv.index('--output-dir')+1]).resolve();out=(root/x['original_path']).resolve();assert out.is_relative_to(root);out.parent.mkdir(parents=True,exist_ok=True)
  with out.open('xb') as f:f.write(raw)
 print(x['original_path'],x['sha256'],'EXACT')
