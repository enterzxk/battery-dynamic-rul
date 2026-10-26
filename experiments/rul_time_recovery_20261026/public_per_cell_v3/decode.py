import pathlib,json,zipfile,hashlib,sys
here=pathlib.Path(__file__).resolve().parent
out=pathlib.Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
manifest=json.loads((here/'validation.json').read_text())
assert hashlib.sha256((here/'archive.bin').read_bytes()).hexdigest()==manifest['archive_sha256']
with zipfile.ZipFile(here/'archive.bin') as z:
 for item in manifest['files']:
  p=(out/item['path']).resolve();assert out in p.parents
  b=z.read(item['path']);assert hashlib.sha256(b).hexdigest()==item['sha256']
  p.parent.mkdir(parents=True,exist_ok=True)
  with p.open('xb') as f:f.write(b)
print('PASS: decoded',len(manifest['files']),'byte-identical derived evidence files')
