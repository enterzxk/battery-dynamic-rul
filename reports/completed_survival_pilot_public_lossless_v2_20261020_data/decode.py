from pathlib import Path
import hashlib,json,zlib
ROOT=Path('/home/yndx/zxk/rul')
HERE=Path(__file__).resolve().parent
FILES=[{'original_path': 'experiments/online_survival_observed_pilot_seed42_v1/published_prediction_csvs_part1.json', 'original_bytes': 906458, 'original_sha256': 'ea7c3d57be45cc1322251ca627f5a757eb6d9951a20a12fefe47876b3b77ff42', 'offset': 0, 'compressed_bytes': 685440, 'compressed_sha256': '76b2ba87a0e58825c4cd5a1ad24175795306b2bca6a0ac81c05d3d97d05ae6f5'}, {'original_path': 'experiments/online_survival_observed_pilot_seed42_v1/published_prediction_csvs_part2.json', 'original_bytes': 1615202, 'original_sha256': '57e56b4db561605d8b33bb8e20b3f75e084e9ce51348edb8a01892545b321514', 'offset': 685440, 'compressed_bytes': 1219985, 'compressed_sha256': 'bdcce8befd0a7b235ea475cab304a5aff9efdf4233e36beb205ac4ad5d868c46'}]
blob=(HERE/'archive.bin').read_bytes()
for e in FILES:
 start=e['offset']; comp=blob[start:start+e['compressed_bytes']]
 if hashlib.sha256(comp).hexdigest()!=e['compressed_sha256']:
  raise RuntimeError('ARCHIVE_SEGMENT_HASH_FAILURE:'+e['original_path'])
 raw=zlib.decompress(comp)
 if len(raw)!=e['original_bytes'] or hashlib.sha256(raw).hexdigest()!=e['original_sha256']:
  raise RuntimeError('RESTORED_FILE_HASH_FAILURE:'+e['original_path'])
 dst=ROOT/e['original_path']; dst.parent.mkdir(parents=True,exist_ok=True)
 with dst.open('xb') as f:f.write(raw)
print(json.dumps({'status':'DECODED_BYTE_EXACT','files':len(FILES)}))
