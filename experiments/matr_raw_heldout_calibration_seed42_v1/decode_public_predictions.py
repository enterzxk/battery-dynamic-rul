import pathlib,json,base64,zlib,hashlib
p=pathlib.Path(__file__).parent
a=json.loads((p/'published_predictions.json').read_text())
for name,v in a['files'].items():
 b=zlib.decompress(base64.b64decode(v['payload']));assert len(b)==v['bytes'] and hashlib.sha256(b).hexdigest()==v['sha256'];f=p/name
 if f.exists():assert f.read_bytes()==b
 else:f.open('xb').write(b)
print('All original prediction CSV bytes verified')
