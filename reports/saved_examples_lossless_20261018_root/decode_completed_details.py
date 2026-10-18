from pathlib import Path
import json,zlib,base64,hashlib,sys
O=Path(__file__).resolve().parent;items=json.loads(zlib.decompress(base64.b64decode(json.loads((O/'completed_details_lossless.json').read_text())['payload'])))
for x in items:
 raw=x['content_utf8'].encode('utf-8');assert len(raw)==x['bytes'] and hashlib.sha256(raw).hexdigest()==x['sha256']
 if '--output-dir' in sys.argv:
  root=Path(sys.argv[sys.argv.index('--output-dir')+1]).resolve();out=(root/x['original_path']).resolve();assert out.is_relative_to(root);out.parent.mkdir(parents=True,exist_ok=True)
  with out.open('xb') as f:f.write(raw)
print('EXACT_FILES',len(items))
