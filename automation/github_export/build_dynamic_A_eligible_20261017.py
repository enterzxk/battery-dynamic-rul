"""从已有真实文本审计产物构造候选origin；不打开pickle、不训练。"""
from pathlib import Path
import ast,collections,csv,datetime,hashlib,json,math

ROOT=Path('/home/yndx/zxk/rul')
OUT=ROOT/'reports/dynamic_A_eligible_20261017_root'
SOURCE=ROOT/'reports/matr_schema_audit/run_v2_20261016T031830319822Z/cells'
PINNED=ROOT/'repos/pinned/BatteryLife_3b17bb53202e10711deae0448c91f84144bb3dd9'
OUT.mkdir(exist_ok=False)
GRID=[50,100,150,200]
KNOWN_SHIFT={'MATR_b1c0.pkl','MATR_b1c18.pkl','MATR_b2c12.pkl','MATR_b2c44.pkl'}
protocol={'status':'CANDIDATE_NO_MODEL_FIT_AUTHORIZATION','dataset':'MATR_v11_existing_text_summaries',
    'origins':GRID,'k0':50,'slope_window':20,'seed':42,'split':'official train102/validation34; test excluded before summary reads',
    'event':'first capacity_Ah <= 0.8*nominal_capacity_Ah*soc_window_width',
    'cohort':'all train/val source IDs, at-risk by observed prefix; no estimated_EOL>k future selection',
    'label_lanes':['observed_nominal_crossing','author_total_EOL_estimate_or_observed'],
    'physical_identity_status':'source IDs + known continuation aliases; other serial identity unresolved',
    'prefix_scope':'literal processed text rows at actual_cycle<=k, after full cycle',
    'strict_online_safe':False,'generator_v11_provenance':'UNVERIFIED',
    'excluded_entire_cells':sorted(KNOWN_SHIFT),
    'A0':'Ridge trained at k0 once to predict EOL, then max(0,EOL_hat(k0)-k)',
    'A1_features':['age','soh','cumulative_discharge_Ah','batch2','batch3','batch4'],
    'A2_additional_features':['capacity_slope_last20_Ah_per_cycle'],
    'measured_capacity_permission':'laboratory complete-cycle capacity; not deployable I/V-only claim',
    'fit_candidate':'same Ridge family, alpha grid [0.1,1,10,100], grouped train-only 3-fold, fit scaler within folds, per-cell sample weights',
    'primary_metric':'validation per-cell origin mean absolute error then equal-cell mean, cycles',
    'interpretation':'candidate processed-record retrospective diagnostic only; strict online raw-source claim blocked',
    'test_inference':False,'new_fits':0,'optimizer_steps':0}
(OUT/'protocol_candidate.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
split_path=PINNED/'data_provider/data_split_recorder.py'
roles={}
for node in ast.walk(ast.parse(split_path.read_text())):
    if isinstance(node,ast.Assign):
        for target in node.targets:
            if isinstance(target,ast.Name) and target.id in ['MATR_train_files','MATR_val_files','MATR_test_files']:
                role=target.id.removeprefix('MATR_').removesuffix('_files')
                for cell in ast.literal_eval(node.value):
                    assert cell not in roles,'Cross split source ID';roles[cell]=role
assert collections.Counter(roles.values())=={'train':102,'val':34,'test':33}
label_path=ROOT/'reports/matr_label_reconstruction_audit/per_cell_with_diff.jsonl'
label_rows={x['cell_file']:x for x in map(json.loads,label_path.read_text().splitlines())}
rows=[];features=[];sources=[];stats=collections.Counter()
for cell,role in sorted(roles.items()):
    if role=='test':continue
    meta_path=SOURCE/(cell+'.json');meta=json.loads(meta_path.read_text())
    cyc_path=SOURCE/(cell+'.cycles.json');raw=cyc_path.read_bytes()
    digest=hashlib.sha256(raw).hexdigest()
    assert digest==meta['cycle_summary_sha256'],cell+' text source changed'
    cycles=json.loads(raw);actual=[x['actual_cycle_number'] for x in cycles]
    assert actual==list(range(1,len(cycles)+1)) and meta['actual_equals_row'],cell+' coordinate mismatch'
    caps=[float(x['capacity_Ah']) for x in cycles];assert all(math.isfinite(q) for q in caps)
    nominal=meta['nominal_capacity_Ah']*(meta['soc_interval'][1]-meta['soc_interval'][0])
    crossing=next((i+1 for i,q in enumerate(caps) if q<=0.8*nominal),None)
    assert crossing==meta['observed_nominal_crossing_actual']
    label=label_rows[cell];assert label['author_v11_label']==meta['v11_author_label']
    sources.append({'cell_id':cell[:-4],'split':role,'metadata_path':str(meta_path.relative_to(ROOT)),
        'metadata_sha256':hashlib.sha256(meta_path.read_bytes()).hexdigest(),'cycle_summary_path':str(cyc_path.relative_to(ROOT)),
        'cycle_summary_sha256':digest,'declared_binary_sha256_not_reread':meta['source_sha256']})
    stats[(role,'observed' if crossing is not None else 'censored')]+=1
    for k in GRID:
        covered=len(cycles)>=k
        alive=covered and (crossing is None or crossing>k)
        risk=cell in KNOWN_SHIFT
        reason='known_conditional_next_cycle_mapping_risk' if risk else ('followup_not_to_k' if not covered else ('event_at_or_before_k' if not alive else ''))
        eligible=covered and alive and not risk
        row={'cell_id':cell[:-4],'dataset':'MATR_v11','split':role,'physical_identity_status':'SOURCE_ID_KNOWN_ALIASES_MERGED_OTHER_UNVERIFIED',
             'k':k,'actual_cycle_number':k if covered else '', 'observed_alive_at_k':alive,
             'event_status':'observed' if crossing is not None else 'right_censored',
             'label_type':'observed_nominal80' if crossing is not None else 'author_tail_extrapolated',
             'prefix_safe':'CONDITIONAL_PROCESSED_ROWS_ONLY' if eligible else False,'strict_online_eligible':False,
             'engineering_candidate_eligible':eligible,'exclusion_reason':reason,
             'strict_blocker':'v11_generator_and_full_physical_identity_unverified',
             'observed_EOL':crossing or '', 'author_EOL':meta['v11_author_label']}
        rows.append(row)
        if not eligible:continue
        # 仅读取<=k的容量；事件/标签字段绝不进入输入列。
        prefix=caps[:k];window=prefix[-20:];mean_x=9.5;den=sum((i-mean_x)**2 for i in range(20))
        slope=sum((i-mean_x)*q for i,q in enumerate(window))/den
        batch=int(cell.split('_b')[1].split('c')[0])
        features.append({'cell_id':cell[:-4],'split':role,'k':k,'age':k,'soh':prefix[-1]/nominal,
            'cumulative_discharge_Ah':sum(prefix),'batch2':int(batch==2),'batch3':int(batch==3),'batch4':int(batch==4),
            'capacity_slope_last20_Ah_per_cycle':slope,'author_EOL':meta['v11_author_label'],
            'observed_EOL':crossing or '', 'event_status':row['event_status'],'label_type':row['label_type']})
for name,items in [('eligible_origins.csv',rows),('candidate_features.csv',features)]:
    with (OUT/name).open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(items[0]));writer.writeheader();writer.writerows(items)
summary={'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'source_role_cells':{f'{a}_{b}':v for (a,b),v in stats.items()},'grid':GRID,'origins_considered':len(rows),
    'engineering_candidate_origins':len(features),'engineering_candidate_cells_by_split':{role:len({x['cell_id'] for x in features if x['split']==role}) for role in ['train','val']},
    'eligible_event_cells_by_split':{role:len({x['cell_id'] for x in features if x['split']==role and x['event_status']=='observed'}) for role in ['train','val']},
    'strict_online_eligible_origins':0,'exclusion_reasons':dict(collections.Counter(x['exclusion_reason'] for x in rows if x['exclusion_reason'])),
    'sources':sources,'split_source_sha256':hashlib.sha256(split_path.read_bytes()).hexdigest(),
    'label_reconstruction_source_sha256':hashlib.sha256(label_path.read_bytes()).hexdigest(),
    'raw_binary_opened':0,'test_cell_summary_reads':0,'new_fits':0,'optimizer_steps':0,
    'warning':'No population selected by future EOL; observed-only evaluation is event-observed conditional, not all cells. Candidate features need narrow root GO before fitting.'}
(OUT/'cohort_receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='sources'},ensure_ascii=False))
