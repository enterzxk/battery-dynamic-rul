from pathlib import Path
import sys,json,base64,hashlib,fcntl
R=Path('/home/yndx/zxk/rul');O=R/'reports/isu_ilcc_capacity_probe_20261020_root'
p=json.loads((O/'protocol.json').read_text());g=json.loads((O/'ROOT_GO.json').read_text());v=json.load(sys.stdin);b=base64.b64decode(v['base64'],validate=True)
assert g['status']=='GO_ONE_ARCHIVE_AND_TWO_TRAIN_SUMMARIES'
assert len(b)==p['max_archive_bytes'] and hashlib.md5(b).hexdigest()==p['acquisition']['computed_md5']
assert hashlib.sha256(b).hexdigest()==v['sha256'] and v['url']==p['acquisition']['download_url']
with (R/'automation/state/coordinator.lock').open('a+') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);s=json.loads((R/'automation/state/coordinator.json').read_text());assert s['owner']==p['owner'] and s['takeover_verified']
 d=R/'data/raw/ISU_ILCC/official_v2';d.mkdir(parents=True,exist_ok=True)
 with (d/'capacity_fade.zip').open('xb') as f:f.write(b)
 with (O/'acquisition_receipt.json').open('x') as f:json.dump({k:v[k] for k in ['url','sha256','HTTP_status','redirect_hosts']},f,indent=2)
print(json.dumps({'status':'SAVED_ARCHIVE_NO_MEMBER_DECODE','bytes':len(b),'sha256':v['sha256']}))
