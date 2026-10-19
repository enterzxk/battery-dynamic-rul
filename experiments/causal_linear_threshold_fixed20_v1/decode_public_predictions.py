import pathlib,json,zlib,base64,hashlib,sys
p=pathlib.Path(__file__).resolve().parent
j=json.loads((p/'public_predictions_lossless.json').read_text());b=zlib.decompress(base64.b64decode(j['zlib_base64']))
assert len(b)==j['bytes'] and hashlib.sha256(b).hexdigest()==j['sha256']
with pathlib.Path(sys.argv[1]).open('xb') as f:f.write(b)
