import pathlib,json,zipfile,hashlib,sys
h=pathlib.Path(__file__).resolve().parent;o=pathlib.Path(sys.argv[1]).resolve();o.mkdir(parents=True,exist_ok=True)
m=json.loads((h/'validation.json').read_text());assert hashlib.sha256((h/'archive.bin').read_bytes()).hexdigest()==m['archive_sha256']
with zipfile.ZipFile(h/'archive.bin') as z:
 for e in m['files']:
  p=(o/e['path']).resolve();assert o in p.parents;b=z.read(e['path']);assert hashlib.sha256(b).hexdigest()==e['sha256'];p.parent.mkdir(parents=True,exist_ok=True)
  with p.open('xb') as f:f.write(b)
print('PASS',len(m['files']))
