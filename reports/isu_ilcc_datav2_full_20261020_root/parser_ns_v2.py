#!/usr/bin/env python3
"""Remote-only bounded decoder and DataV2 contract writer; no network access."""
import argparse, base64, hashlib, json, math, os, struct, time, zlib, fcntl, re
from datetime import datetime
from pathlib import Path

ROOT=Path('/home/yndx/zxk/rul')
REPORT=ROOT/'reports/isu_ilcc_datav2_two_sample_repair_20261020_root'
SCOPE=ROOT/'reports/isu_ilcc_clock_source_20261020_root/next_clock_recovery_scope.json'
COHORT=ROOT/'reports/isu_ilcc_capacity_probe_20261020_root/cohort.json'
CENTRAL=ROOT/'reports/isu_ilcc_clock_source_20261020_root/central_directory_receipt.json'
STATE=ROOT/'automation/state/coordinator.json'; LOCK=ROOT/'automation/state/coordinator.lock'
GO=ROOT/'reports/isu_ilcc_datav2_20261020_root_review/ROOT_GO_REPAIR.json'
REVIEW=ROOT/'reports/isu_ilcc_datav2_20261020_root_review/delta_review_repair.json'
OUT=ROOT/'data/processed/ISU_ILCC_DataV2_v1'
RAW=OUT/'.raw_members'
OWNER='01a15846-1ade-7623-88ff-98dd7f94f4fd'
MAX_NET=12_500_000; MAX_UNCOMP=134_217_728

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def jload(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def create(path,data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as f: f.write(data)
def expected():
    scope=jload(SCOPE); cohort=jload(COHORT); central=jload(CENTRAL)
    entries={e['name']:e for e in central['entries']}
    return scope,cohort,entries
def _gate_and_claim_locked(controller_sha256):
    scope,cohort,entries=expected(); go=jload(GO); review=jload(REVIEW)
    if review.get('status')!='PASS_DELTA': raise RuntimeError('DELTA_REVIEW_NOT_PASS')
    if go.get('status')!='GO_TWO_TRAIN_RPT_RANGE_RECEIVE': raise RuntimeError('FRESH_GO_MISSING')
    src=jload(ROOT/'reports/isu_ilcc_clock_source_20261020_root/central_directory_scope.json')
    want={'owner':OWNER,'protocol_sha256':sha(REPORT/'protocol.md'),'runner_sha256':sha(REPORT/'prepare_datav2.py'),'receiver_sha256':sha(REPORT/'receive_datav2.py'),'cohort_sha256':sha(COHORT),'source_receipt_sha256':sha(CENTRAL),'scope_sha256':sha(SCOPE),'archive_scope_sha256':sha(ROOT/'reports/isu_ilcc_clock_source_20261020_root/central_directory_scope.json'),'review_sha256':sha(REVIEW),'source_etag':'"36331bf80f21d00e19a9a45095f542e8"','source_archive_id':43756491,'source_archive_bytes':929406930,'max_logical_get':4,'max_network_body_bytes':MAX_NET,'max_uncompressed_total_bytes':MAX_UNCOMP,'members':[x['name'] for x in scope['members']],'new_fits':0,'locked_reads':0,'training_allowed':False,'controller_sha256':controller_sha256}
    for k,v in want.items():
        if go.get(k)!=v: raise RuntimeError('GO_BINDING_MISMATCH:'+k)
    issued=datetime.fromisoformat(go['issued_utc'].replace('Z','+00:00'))
    from datetime import timezone
    age=(datetime.now(timezone.utc)-issued).total_seconds()
    if age<0 or age>600: raise RuntimeError('GO_NOT_FRESH')
    state=jload(STATE)
    if state.get('state')!='ACTIVE' or state.get('owner')!=OWNER or state.get('thread_id')!=OWNER or state.get('actual_cwd')!='/home/yndx/zxk/rul' or state.get('takeover_verified') is not True: raise RuntimeError('CURRENT_OWNER_MISMATCH')
    hb=datetime.fromisoformat(state['heartbeat_utc'].replace('Z','+00:00'))
    if (datetime.now(timezone.utc)-hb).total_seconds()>1800: raise RuntimeError('OWNER_HEARTBEAT_STALE')
    if not LOCK.exists(): raise RuntimeError('COORDINATOR_LOCK_MISSING')
    lockhash=sha(LOCK)
    if go.get('coordinator_lock_sha256')!=lockhash: raise RuntimeError('LOCK_HASH_MISMATCH')
    claim={'status':'CLAIMED','issued_utc':go['issued_utc'],'go_sha256':sha(GO),'go_bindings':want,'network_body_bytes':0,'logical_gets':0,'members':{}}
    create(REPORT/'two_train_once.claim.json',json.dumps(claim,indent=2).encode())
    return claim
def gate_and_claim(controller_sha256):
    with LOCK.open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return _gate_and_claim_locked(controller_sha256)
def verify_active_claim():
    claim=jload(REPORT/'two_train_once.claim.json'); state=jload(STATE)
    if claim['go_sha256']!=sha(GO) or state.get('owner')!=OWNER or state.get('thread_id')!=OWNER or state.get('takeover_verified') is not True:
        raise RuntimeError('ACTIVE_CLAIM_OWNER_OR_GO_MISMATCH')
    return claim
def missing_time(v):
    return v is None or v==[] or v in ('','[]')
def store_chunk(kind,member):

    claim=verify_active_claim(); scope,cohort,entries=expected()
    if claim.get('status')!='CLAIMED': raise RuntimeError('CLAIM_NOT_ACTIVE')
    if member not in [m['name'] for m in scope['members']]: raise RuntimeError('MEMBER_OUT_OF_SCOPE')
    payload=__import__('sys').stdin.buffer.read(17_000_001)
    if len(payload)>17_000_000: raise RuntimeError('RECEIVER_INPUT_OVER_LIMIT')
    val=json.loads(payload.decode('utf-8')); b=base64.b64decode(val['base64'],validate=True)
    if kind=='header' and len(b)!=30: raise RuntimeError('HEADER_SIZE_MISMATCH')
    if kind=='range2':
        m=next(x for x in scope['members'] if x['name']==member); meta=entries[member]
        if len(b)>m['compressed_bytes']+1024: raise RuntimeError('RANGE2_SIZE_OVER_CAP')
        if len(b)<m['compressed_bytes']: raise RuntimeError('RANGE2_TOO_SHORT')
        if len(b)-m['compressed_bytes']>1024: raise RuntimeError('LOCAL_NAME_EXTRA_TOO_LARGE')
    dest=RAW/(member.rsplit('/',1)[-1]+'.'+kind+'.bin')
    create(dest,b)
    return {'status':'CHUNK_STORED','member':member,'kind':kind,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def finite_num(v): return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
def parse_dt(v):
    if not isinstance(v,str): return None
    try:
        text=v.replace('Z','+00:00')
        text=re.sub(r'(\.\d{6})000(?=$|[+-])',r'\1',text)
        return datetime.fromisoformat(text)
    except ValueError: return None
def list_field(v,name):
    if not isinstance(v,list): raise ValueError(name+'_NOT_OFFICIAL_LIST_SHAPE')
    return v
def extract(member,raw,role):
    value=json.loads(raw.decode('utf-8-sig'))
    if isinstance(value,str): value=json.loads(value)
    if not isinstance(value,dict): raise ValueError('JSON_TOP_LEVEL_NOT_OBJECT')
    st=value.get('start_stop_time'); cap=value.get('capacity_discharge_C_5')
    if not isinstance(st,dict) or not isinstance(cap,list): raise ValueError('OFFICIAL_FIELD_SHAPE_MISMATCH')
    starts=list_field(st.get('start'),'start'); stops=list_field(st.get('stop'),'stop')
    n=max(len(starts),len(stops),len(cap)); records=[]; last=None
    for i in range(n):
        start=starts[i] if i<len(starts) else None; stop=stops[i] if i<len(stops) else None
        c=cap[i] if i<len(cap) else None
        if isinstance(c,list): c=None
        if not finite_num(c) or c<0: c=None
        ds,dt=parse_dt(start),parse_dt(stop)
        if not missing_time(start) and ds is None: raise ValueError('UNPARSEABLE_SOURCE_START_TIMESTAMP')
        if not missing_time(stop) and dt is None: raise ValueError('UNPARSEABLE_SOURCE_STOP_TIMESTAMP')
        valid=bool(ds and dt and ds<=dt and c is not None)
        if dt:
            if last is not None and dt<=last: raise ValueError('STOP_TIME_NOT_STRICTLY_INCREASING')
            last=dt
        if ds and dt and ds>dt: raise ValueError('START_AFTER_STOP')
        records.append({'source_rpt_index':i,'start':start,'stop':stop,'capacityAh':c,'valid':valid})
    first_stop=next((parse_dt(r['stop']) for r in records if parse_dt(r['stop']) is not None),None)
    group='G'+member.rsplit('/',1)[-1][1:].split('C',1)[0]
    for r in records:
        dt=parse_dt(r['stop']); r['calendar_age_seconds']=((dt-first_stop).total_seconds() if dt and first_stop else None)
        r['capacity_visible_at']='stop' if dt and r['capacityAh'] is not None else None
        r['observed_nominal80_endpoint']=bool(r['valid'] and r['capacityAh']<=0.2)
    top=[str(k) for k in value.keys()]
    cycle_keys=[k for k in top if 'cycle' in k.lower() or 'efc' in k.lower()]
    return {'cell_id':member.rsplit('/',1)[-1][:-5],'group_id':group,'role':role,'nominal_capacity_ah':0.25,'baseline_stop':next((r['stop'] for r in records if parse_dt(r['stop']) is not None),None),'source_top_level_keys':top,'native_cycle_or_efc_status':('TOP_LEVEL_KEY_PRESENT:'+','.join(cycle_keys) if cycle_keys else 'UNKNOWN_NOT_PRESENT_AT_TOP_LEVEL'),'records':records,'eol_or_censoring_claim':None}
def decode_all():
    verify_active_claim()
    start=time.monotonic(); scope,cohort,entries=expected(); members=scope['members']; rolemap=cohort['roles']; results=[]; total=0; net=0
    for m in members:
        name=m['name']; base=name.rsplit('/',1)[-1]; h=(RAW/(base+'.header.bin')).read_bytes(); pair=(RAW/(base+'.range2.bin')).read_bytes()
        if h[:4]!=b'PK\x03\x04': raise RuntimeError('LOCAL_HEADER_SIGNATURE_STOP')
        sig,ver,flags,method,mtime,mdate,crc,csize,usize,nlen,xlen=struct.unpack('<4s5H3I2H',h)
        meta=entries[name]
        if flags!=meta['flags'] or method!=meta['method'] or method!=8 or nlen+xlen+meta['compressed_bytes']!=len(pair): raise RuntimeError('HEADER_OR_RANGE_LENGTH_MISMATCH')
        fname=pair[:nlen].decode('utf-8' if flags&2048 else 'cp437')
        if fname!=name: raise RuntimeError('LOCAL_NAME_MISMATCH')
        comp=pair[nlen+xlen:]
        if len(comp)!=meta['compressed_bytes']: raise RuntimeError('CENTRAL_COMPRESSED_LENGTH_MISMATCH')
        dec=zlib.decompressobj(-15); raw=dec.decompress(comp,meta['bytes']+1)
        if len(raw)>meta['bytes'] or dec.unconsumed_tail: raise RuntimeError('DECOMPRESS_OUTPUT_OVER_MEMBER_BOUND')
        raw+=dec.flush(meta['bytes']+1-len(raw))
        if not dec.eof or len(raw)!=meta['bytes'] or (zlib.crc32(raw)&0xffffffff)!=int(meta['crc32'],16): raise RuntimeError('CENTRAL_SIZE_OR_CRC_MISMATCH')
        total+=len(raw); net+=len(h)+len(pair)
        if total>MAX_UNCOMP or net>MAX_NET: raise RuntimeError('TOTAL_BUDGET_EXCEEDED')
        role=rolemap.get(base[:-5]);
        if role!='train': raise RuntimeError('ROLE_MISMATCH')
        contract=extract(name,raw,role); results.append((contract,hashlib.sha256(raw).hexdigest(),len(comp),len(raw),meta['crc32']))
        if time.monotonic()-start>120: raise RuntimeError('TIME_LIMIT_EXCEEDED')
    # Create-only writes. Outputs remain absent on any prior parse/validation failure.
    targets=[OUT/(contract['cell_id']+'.json') for contract,*_ in results]
    if any(p.exists() for p in targets) or (REPORT/'two_sample_result.json').exists(): raise FileExistsError('OUTPUT_ALREADY_EXISTS_STOP')
    for contract,*_ in results:
        create(OUT/(contract['cell_id']+'.json'),(json.dumps(contract,ensure_ascii=False,indent=2)+'\n').encode())
    summary={'status':'TWO_TRAIN_MEMBERS_DECODED','members':[{'cell_id':x[0]['cell_id'],'role':x[0]['role'],'raw_json_sha256':x[1],'compressed_bytes':x[2],'uncompressed_bytes':x[3],'crc32':x[4],'records':len(x[0]['records']),'source_top_level_keys':x[0]['source_top_level_keys'],'native_cycle_or_efc_status':x[0]['native_cycle_or_efc_status']} for x in results],'network_body_bytes':net,'uncompressed_bytes':total,'locked_decodes':0,'fits':0}
    create(REPORT/'two_sample_result.json',(json.dumps(summary,indent=2)+'\n').encode())
    return summary
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('mode',choices=['claim','store-header','store-range2','decode','failure']); ap.add_argument('--member'); ap.add_argument('--controller-sha256'); a=ap.parse_args()
    try:
        if a.mode=='failure':
            v=json.loads(__import__('sys').stdin.read()); create(REPORT/'two_sample_failure.json',(json.dumps(v,indent=2)+'\n').encode()); r=v
        elif a.mode=='claim': r=gate_and_claim(a.controller_sha256)
        elif a.mode=='decode': r=decode_all()
        else:
            if not a.member: raise ValueError('MEMBER_REQUIRED')
            r=store_chunk('header' if a.mode=='store-header' else 'range2',a.member)
        print(json.dumps(r))
    except Exception as e:
        receipt={'status':'FAILED_STOP_NO_RETRY','error_type':type(e).__name__,'error':str(e),'fits':0}
        try: create(REPORT/'two_sample_failure.json',(json.dumps(receipt,indent=2)+'\n').encode())
        except FileExistsError: pass
        raise
if __name__=='__main__': main()
