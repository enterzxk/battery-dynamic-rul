import pathlib,json,base64,zlib,hashlib,sys
p=pathlib.Path(__file__).resolve().parent
out=pathlib.Path(sys.argv[1])
for e in json.loads((p/'archive.json').read_text())['files']:
 b=zlib.decompress(base64.b64decode(e['zlib_base64']));assert len(b)==e['bytes'] and hashlib.sha256(b).hexdigest()==e['sha256']
 f=out/e['path'];f.parent.mkdir(parents=True,exist_ok=True)
 with f.open('xb') as w:w.write(b)
