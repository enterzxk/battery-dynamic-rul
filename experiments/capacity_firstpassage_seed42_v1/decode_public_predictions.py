import pathlib,json,base64,zlib,hashlib
p=pathlib.Path(__file__).parent;v=json.loads((p/'published_predictions.json').read_text());b=zlib.decompress(base64.b64decode(v['payload']));assert len(b)==v['bytes'] and hashlib.sha256(b).hexdigest()==v['sha256'];f=p/v['file']
if f.exists():assert f.read_bytes()==b
else:f.open('xb').write(b)
print('Exact original forecast prediction CSV verified')
