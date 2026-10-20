#!/usr/bin/env python3
"""One-shot read-only qualification for completed ISU ILCC DataV2 assets."""
import hashlib, importlib.util, json, math, sys, re
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path('/home/yndx/zxk/rul')
REPORT=ROOT/'reports/isu_ilcc_datav2_full_20261020_root'
COHORT=ROOT/'reports/isu_ilcc_capacity_probe_20261020_root/cohort.json'
SCOPE=REPORT/'scope_candidate.json'
FINAL=REPORT/'full_import_final.json'
LEDGER=REPORT/'member_ledger.jsonl'
GO=REPORT/'ROOT_GO.json'
REVIEW=REPORT/'delta_review.json'
OUT=ROOT/'data/processed/ISU_ILCC_DataV2_v1'
MANIFEST=REPORT/'data_manifest.json'
ADAPTER=ROOT/'experiments/isu_irregular_rul_seed42_v1/data_adapter.py'
ADAPTER_SHA='d5effc7ab9aa946feee717e8490983e6ccbebf890492b456091ac49a942763f3'
REPAIR=ROOT/'reports/isu_ilcc_datav2_two_sample_repair_20261020_root'
REPAIR_GO=ROOT/'reports/isu_ilcc_datav2_20261020_root_review/ROOT_GO_REPAIR.json'
OWNER='01a15846-1ade-7623-88ff-98dd7f94f4fd'

def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def parse_dt(x):
    if not isinstance(x,str) or not x or x=='[]': return None
    try:
        text=re.sub(r'(\.\d{6})000(?=$|[+-])',r'\1',x.replace('Z','+00:00'))
        d=datetime.fromisoformat(text)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (ValueError,TypeError): return None
def finite(x): return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def create_only(path,obj):
    with Path(path).open('x',encoding='utf-8') as f: json.dump(obj,f,ensure_ascii=False,indent=2); f.write('\n')
def main():
    if MANIFEST.exists(): raise FileExistsError('DATA_MANIFEST_ALREADY_EXISTS')
    cohort=read(COHORT); scope=read(SCOPE); final=read(FINAL); go=read(GO); review=read(REVIEW)
    rolemap=cohort['roles']; members=scope['members']; frozen={m['cell_id']:m for m in members}
    problems=[]; files={}; inventory={x['cell_id']:x for x in final.get('inventory',[])}
    if final.get('status')!='FULL188_COMPLETE' or final.get('cells')!=188 or final.get('train')!=125 or final.get('development')!=63 or final.get('locked')!=0 or final.get('fits')!=0:
        problems.append({'type':'final_receipt_mismatch','detail':'full_import_final does not attest 188 train/development cells, locked=0, fits=0'})
    if len(members)!=188 or len(frozen)!=188 or len(inventory)!=188: problems.append({'type':'scope_inventory_count_mismatch','detail':f'scope={len(members)} unique={len(frozen)} inventory={len(inventory)}'})
    if sum(r=='train' for r in rolemap.values())!=125 or sum(r=='development' for r in rolemap.values())!=63 or sum(r=='locked' for r in rolemap.values())!=63:
        problems.append({'type':'cohort_role_count_mismatch','detail':'frozen roles are not 125/63/63'})
    spec=importlib.util.spec_from_file_location('isu_data_adapter',ADAPTER); adapter=importlib.util.module_from_spec(spec); spec.loader.exec_module(adapter)
    if sha(ADAPTER)!=ADAPTER_SHA: problems.append({'type':'adapter_hash_mismatch','detail':sha(ADAPTER)})
    role_stats={r:{'valid_observations':0,'missing_observations':0,'cells_with_observed_event':0,'cells_without_observed_event':0,'raw_origins':0,'sparse2rpt_origins':0,'delayed7d_origins':0,'valid_paired_origins':0} for r in ('train','development')}
    cell_failures=[]
    for cid in sorted(frozen):
        m=frozen[cid]; role=m['role']; path=OUT/(cid+'.json')
        if role not in ('train','development') or rolemap.get(cid)!=role:
            problems.append({'type':'scope_role_mismatch','cell_id':cid,'scope_role':role,'cohort_role':rolemap.get(cid)})
            continue
        inv=inventory.get(cid)
        if inv is None or inv.get('role')!=role or inv.get('path')!=str(path.relative_to(ROOT)) or not path.is_file():
            problems.append({'type':'inventory_or_file_mismatch','cell_id':cid}); continue
        digest=sha(path)
        if digest!=inv.get('sha256'):
            problems.append({'type':'cell_hash_mismatch','cell_id':cid,'expected':inv.get('sha256'),'actual':digest}); continue
        files[cid]={'sha256':digest,'path':str(path.relative_to(ROOT)),'role':role}
        x=read(path); local=[]
        if x.get('cell_id')!=cid or x.get('role')!=role or x.get('group_id')!='G'+cid[1:].split('C')[0]:
            local.append('contract_id_role_group_mismatch')
        recs=x.get('records')
        if not isinstance(recs,list) or not recs: local.append('empty_records')
        else:
            inds=[q.get('source_rpt_index') for q in recs]
            if inds!=list(range(len(recs))): local.append('source_rpt_index_not_preserved')
            baseline=parse_dt(x.get('baseline_stop')); last=None; event_indices=[]
            if baseline is None: local.append('empty_or_ambiguous_baseline_stop')
            for q in recs:
                valid=q.get('valid') is True
                stop=parse_dt(q.get('stop')); start=parse_dt(q.get('start')); cap=q.get('capacityAh')
                if q.get('stop') not in (None,'','[]',[]) and stop is None: local.append('ambiguous_stop_timestamp')
                if q.get('start') not in (None,'','[]',[]) and start is None: local.append('ambiguous_start_timestamp')
                if start and stop and start>stop: local.append('start_after_stop')
                if stop:
                    if last and stop<=last: local.append('stop_not_strictly_increasing')
                    last=stop
                    if baseline and abs(q.get('calendar_age_seconds',float('nan'))-(stop-baseline).total_seconds())>1e-5: local.append('calendar_age_mismatch')
                if valid:
                    role_stats[role]['valid_observations']+=1
                    if not (start and stop and start<=stop and finite(cap) and cap>=0): local.append('valid_row_has_invalid_fields')
                    if q.get('capacity_visible_at')!='stop' or stop is None: local.append('capacity_visibility_not_at_stop')
                    if finite(cap) and cap<=0.20:
                        event_indices.append(q.get('source_rpt_index'))
                        if q.get('observed_nominal80_endpoint') is not True: local.append('observed_endpoint_flag_missing')
                    elif q.get('observed_nominal80_endpoint') is True: local.append('false_observed_endpoint_flag')
                else:
                    role_stats[role]['missing_observations']+=1
                    if q.get('observed_nominal80_endpoint') is True: local.append('missing_row_marked_event')
                    if q.get('capacity_visible_at') not in (None,''): local.append('missing_row_capacity_claimed_visible')
            if event_indices and recs[event_indices[0]].get('observed_nominal80_endpoint') is not True:
                local.append('first_observed_endpoint_flag_missing')
            if event_indices: role_stats[role]['cells_with_observed_event']+=1
            else: role_stats[role]['cells_without_observed_event']+=1
            if sum(q.get('valid') is True for q in recs)<2: local.append('fewer_than_two_valid_observations')
        # Exercise the named frozen baseline adapter without fitting or predicting.
        try:
            normalized=adapter.load_reviewed_cell(path,role)
            if normalized['event_observed']:
                arms=[]
                for delay,sparse in ((0,False),(0,True),(7,False)):
                    arms.append(adapter.build_origins(normalized,delay_days=delay,sparse=sparse))
                maps=[{(z['origin_stop_epoch'],z['target_rul_weeks']) for z in arm} for arm in arms]
                if not (maps[0]==maps[1]==maps[2]): local.append('raw_sparse_delay_origins_or_labels_mismatch')
                role_stats[role]['raw_origins']+=len(arms[0]); role_stats[role]['sparse2rpt_origins']+=len(arms[1]); role_stats[role]['delayed7d_origins']+=len(arms[2])
                role_stats[role]['valid_paired_origins']+=len(maps[0]&maps[1]&maps[2])
            else:
                pass  # Non-event records remain legitimate assets; origin eligibility is reported, not a data-quality failure.
        except Exception as e:
            local.append('baseline_adapter_reject:'+type(e).__name__+':'+str(e)[:180])
        if local: cell_failures.append({'cell_id':cid,'role':role,'failures':sorted(set(local))})
    if len(files)!=188: problems.append({'type':'not_all_188_file_entries_verified','verified':len(files)})
    ledger_events=[json.loads(line) for line in LEDGER.read_text(encoding='utf-8').splitlines() if line.strip()]
    done={e['cell_id'] for e in ledger_events if e.get('event') in ('cell_complete','cell_reused')}
    if done!=set(frozen): problems.append({'type':'ledger_cell_set_mismatch','missing':sorted(set(frozen)-done),'extra':sorted(done-set(frozen))})
    provenance={
      'owner':OWNER,'scope_candidate_sha256':sha(SCOPE),'full_go_sha256':sha(GO),'full_review_sha256':sha(REVIEW),
      'full_receiver_sha256':sha(REPORT/'full188_receiver.py'),'full_controller_sha256':sha(REPORT/'full188_controller.py'),
      'full_protocol_sha256':sha(REPORT/'full188_protocol.md'),'full_final_receipt_sha256':sha(FINAL),'ledger_sha256':sha(LEDGER),
      'cohort_json_sha256':sha(COHORT),'two_sample_result_sha256':sha(REPAIR/'two_sample_result.json'),
      'two_sample_repair_go_sha256':sha(REPAIR_GO),'baseline_data_adapter_sha256':sha(ADAPTER),'expected_baseline_data_adapter_sha256':ADAPTER_SHA
    }
    result={'schema':'isu_ilcc_datav2_qualified_asset_v1','status':'PASS' if not problems and not cell_failures else 'FAILED_QUALIFICATION',
      'files':files,'role_counts':{'train':sum(v['role']=='train' for v in files.values()),'development':sum(v['role']=='development' for v in files.values()),'locked':0},
      'role_observation_and_origin_summary':role_stats,'qualification_failures':problems+cell_failures,'provenance':provenance,
      'constraints':{'raw_curves_read':False,'locked_payloads_read':False,'model_fit':False,'inference':False,'removed_cells':0,
      'origin_label_assertion':'same origin_stop_epoch and target_rul_weeks across raw/sparse2rpt/delayed7d; visible inputs may differ','clock':'calendar age from baseline_stop to observed stop; not native cycle/EFC'}}
    create_only(MANIFEST,result)
    print(json.dumps({'status':result['status'],'verified_files':len(files),'qualification_failures':len(result['qualification_failures']),'manifest':str(MANIFEST)},ensure_ascii=False))
    return 0 if result['status']=='PASS' else 2
if __name__=='__main__': sys.exit(main())
