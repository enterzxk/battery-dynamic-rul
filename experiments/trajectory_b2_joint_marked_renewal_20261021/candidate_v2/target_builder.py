"""Train-only B2-v2 anchor/suffix builder. Reads data only when called by PREP GO."""
from __future__ import annotations
import hashlib,json,math,sys
from pathlib import Path
from collections import Counter
import numpy as np
ROOT=Path('/home/yndx/zxk/rul')
OLD=ROOT/'experiments/isu_irregular_rul_seed42_v1'
SIGNALS=ROOT/'reports/multisource_20261021_signals'
V18=ROOT/'experiments/dart_rul_v18'
FACTOR=ROOT/'experiments/multisource_factorial_20261021'
for p in (OLD,SIGNALS,V18,FACTOR): sys.path.insert(0,str(p))
import data_adapter
import data_protocol
import features as factor_features

WEEK=604800.0
RPT_WINDOW=3
RPT_DIM=len(factor_features.RPT_FULL)
F0_DIM=74
FIXED_DIM=RPT_WINDOW*RPT_DIM*2+RPT_WINDOW*3+F0_DIM*2


def _sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()


def _manifest(path,expected_type):
    obj=json.loads(Path(path).read_text(encoding='utf-8'))
    if obj.get('manifest_type')!=expected_type or not isinstance(obj.get('assets'),list):
        raise ValueError(f'{expected_type} manifest schema mismatch')
    ids=[str(x.get('cell_id','')) for x in obj['assets']]
    if len(ids)!=125 or len(set(ids))!=125: raise ValueError(f'{expected_type} manifest must have 125 unique cells')
    if any(x.endswith(('C3','C4')) for x in ids): raise ValueError('C3/C4 cell id in train manifest')
    for a in obj['assets']:
        p=Path(a['path'])
        if not p.is_absolute() or not p.is_file(): raise ValueError(f'missing/nonabsolute input asset: {p}')
        if _sha(p)!=a['sha256']: raise ValueError(f'input asset SHA mismatch: {p}')
    return obj


def _rpt_index(path,cell_id):
    """Read one manifest-bound RPT feature asset, accepting JSONL or JSON records."""
    text=Path(path).read_text(encoding='utf-8')
    try:
        obj=json.loads(text)
        rows=obj.get('records',obj) if isinstance(obj,dict) else obj
    except json.JSONDecodeError:
        rows=[json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(rows,dict): rows=list(rows.values())
    if not isinstance(rows,list): raise ValueError('RPT asset must contain a records list')
    out={}
    for r in rows:
        if str(r.get('cell_id',cell_id))!=cell_id: raise ValueError('RPT asset cell identity mismatch')
        idx=int(r['source_rpt_index'])
        if idx in out: raise ValueError(f'duplicate RPT asset source index {cell_id}/{idx}')
        out[idx]=r
    if not out: raise ValueError(f'empty RPT asset for {cell_id}')
    return out


def _f0_and_rpt_anchor(cell,visible,anchor_epoch,actual_query_epoch,rpt_cache):
    """Make F0 and latest-3 F1 raw-source curves at a source-clock encoding reference."""
    if any(float(r['arrival_epoch'])>float(actual_query_epoch) for r in visible): raise ValueError('actual query visibility gate failed')
    # The frozen F0 helper is intentionally encoded at the latest arrived source time,
    # while actual query-time arrival eligibility was checked above.
    f0=np.asarray(data_protocol._feature_view(cell,visible,float(anchor_epoch)),dtype=float)
    if f0.shape!=(F0_DIM,): raise ValueError(f'F0 dimension mismatch: {f0.shape}')
    f0_mask=np.isfinite(f0);f0=np.where(f0_mask,f0,0.0)
    recent=visible[-RPT_WINDOW:]
    rpt_vals=np.zeros((RPT_WINDOW,RPT_DIM),float)
    rpt_mask=np.zeros((RPT_WINDOW,RPT_DIM),bool)
    rpt_meta=np.zeros((RPT_WINDOW,3),float) # record-present, weeks-before-anchor, source-index offset
    offset=RPT_WINDOW-len(recent)
    anchor_idx=int(visible[-1]['source_rpt_index'])
    nominal=float(cell['nominal_capacity_ah'])
    if not math.isfinite(nominal) or nominal<=0: raise ValueError('invalid nominal capacity')
    for pos,r in enumerate(recent,start=offset):
        idx=int(r['source_rpt_index']); rec=rpt_cache.get(idx)
        if rec is None: raise ValueError(f'missing RPT source feature {cell["cell_id"]}/{idx}')
        if int(rec['source_rpt_index'])!=idx or rec.get('data_v2_valid') is not True or rec.get('features_visible_at')!='stop':
            raise ValueError(f'RPT cache provenance/validity mismatch {cell["cell_id"]}/{idx}')
        stop=data_adapter._dt(rec['stop']).timestamp()
        if abs(stop-float(r['stop_epoch']))>1e-3: raise ValueError(f'RPT source clock mismatch {cell["cell_id"]}/{idx}')
        values=factor_features._feature_dict(rec)
        raw=np.asarray([values.get(k,np.nan) for k in factor_features.RPT_FULL],float)/nominal
        mask=np.isfinite(raw)
        rpt_vals[pos]=np.where(mask,raw,0.0);rpt_mask[pos]=mask
        rpt_meta[pos]=[1.0,(float(r['stop_epoch'])-float(anchor_epoch))/WEEK,
                       float(idx-anchor_idx)]
    fixed=np.r_[rpt_vals.reshape(-1),rpt_mask.astype(float).reshape(-1),
                rpt_meta.reshape(-1),f0,f0_mask.astype(float)]
    if fixed.shape!=(FIXED_DIM,) or not np.isfinite(fixed).all(): raise ValueError('fixed embedding invalid')
    return fixed


def _dynamic_from_prefix(visible,anchor_epoch):
    rows=sorted(visible,key=lambda r:(float(r['stop_epoch']),int(r['source_rpt_index'])))
    if len(rows)<2: raise ValueError('two arrived valid RPTs required for dynamic warmup')
    a,b=rows[-2:]
    gap=(float(b['stop_epoch'])-float(a['stop_epoch']))/WEEK
    if gap<=0: raise ValueError('nonpositive visible source gap')
    ca=float(a['capacityAh']);cb=float(b['capacityAh'])
    if ca<=0 or cb<=0: raise ValueError('positive source capacity required for log-ratio marks')
    return np.asarray([cb,math.log1p(gap),math.log(cb/ca),0.,0.,0.],float)


def build_train_examples(processed_manifest_path,rpt_manifest_path):
    pm=_manifest(processed_manifest_path,'processed_datav2_train_cells_v1')
    rm=_manifest(rpt_manifest_path,'rpt_feature_assets_train_cells_v1')
    pmap={str(x['cell_id']):x for x in pm['assets']};rmap={str(x['cell_id']):x for x in rm['assets']}
    if set(pmap)!=set(rmap): raise ValueError('processed/RPT manifest cell sets differ')
    all_fixed=[];all_dynamic=[];all_lg=[];all_dlogc=[];all_dk=[];all_weights=[];all_cell=[];all_path=[];all_step=[]
    cell_ids=sorted(pmap);arm_counts=Counter();path_no=0
    for cell_no,cid in enumerate(cell_ids):
        if pmap[cid].get('role')!='train' or rmap[cid].get('role','train')!='train': raise ValueError('non-train asset in preparation')
        cell=data_adapter.load_reviewed_cell(pmap[cid]['path'],expected_role='train')
        if str(cell['cell_id'])!=cid: raise ValueError('processed cell id mismatch')
        rows=sorted(cell['records'],key=lambda r:(float(r['stop_epoch']),int(r['source_rpt_index'])))
        if any(float(r['capacityAh'])<=0 for r in rows):
            raise ValueError(f'nonpositive valid source capacity in {cid}; log-ratio target undefined')
        if len(rows)<4: continue
        rpt_cache=_rpt_index(rmap[cid]['path'],cid)
        arm_paths=[]
        for arm in ('raw','sparse2'):
            policy_rows=data_protocol._arm_records(rows,1,arm)
            seen_anchor=set()
            for qrow in rows:
                q=float(qrow['stop_epoch'])
                if q<float(rows[1]['stop_epoch'])+WEEK: continue
                visible=[dict(r) for r in policy_rows if float(r['arrival_epoch'])<=q]
                if len(visible)<3: continue
                anchor=visible[-1]; anchor_idx=int(anchor['source_rpt_index'])
                if any(float(r['capacityAh'])<=0.20 for r in visible): continue
                # One path per legal source anchor/arm; duplicate queries in a hold interval add no new suffix.
                key=(arm,anchor_idx)
                if key in seen_anchor: continue
                seen_anchor.add(key)
                if any(float(r['arrival_epoch'])>q for r in visible): raise ValueError('actual query arrival gate failed')
                anchor_pos=next(i for i,r in enumerate(rows) if int(r['source_rpt_index'])==anchor_idx)
                # Include the full observed valid-RPT suffix, including post-threshold
                # transitions. Those marks constrain no-extra-arrival paths after
                # a hidden crossing; no administrative-censor likelihood is added.
                end_pos=len(rows)-1
                if end_pos<=anchor_pos: continue
                fixed=_f0_and_rpt_anchor(cell,visible,float(anchor['stop_epoch']),q,rpt_cache)
                dyn=_dynamic_from_prefix(visible,float(anchor['stop_epoch']))
                arm_paths.append((arm,anchor_pos,end_pos,fixed,dyn))
        # Balance path mass within each cell, then each step within its path.
        if not arm_paths: continue
        cell_weight=1.0/len(cell_ids)
        path_weight=cell_weight/len(arm_paths)
        for arm,anchor_pos,end_pos,fixed,dyn0 in arm_paths:
            path_no+=1;arm_counts[arm]+=1
            steps=end_pos-anchor_pos
            dyn=dyn0.copy()
            for j in range(anchor_pos+1,end_pos+1):
                prev=rows[j-1];cur=rows[j]
                gap=(float(cur['stop_epoch'])-float(prev['stop_epoch']))/WEEK
                dk=int(cur['source_rpt_index'])-int(prev['source_rpt_index'])
                ca=float(prev['capacityAh']);cb=float(cur['capacityAh'])
                if ca<=0 or cb<=0: raise ValueError(f'nonpositive source capacity {cid}/{j}')
                dz=math.log(cb/ca)
                if gap<=0 or dk not in (1,2,3): raise ValueError(f'unsupported source transition {cid}/{j}')
                all_fixed.append(fixed);all_dynamic.append(dyn.copy());all_lg.append(math.log(gap))
                all_dlogc.append(dz);all_dk.append(dk);all_weights.append(path_weight/steps)
                all_cell.append(cell_no);all_path.append(path_no);all_step.append(j-anchor_pos)
                # Teacher-forced training state evolves only along the observed suffix.
                elapsed=math.expm1(float(dyn[3]))+gap
                count=math.expm1(float(dyn[4]))+1.
                progress=math.expm1(float(dyn[5]))+dk
                dyn=np.asarray([cb,math.log1p(gap),dz,math.log1p(elapsed),
                                math.log1p(count),math.log1p(progress)],float)
    if not all_fixed: raise ValueError('no legal anchor/suffix transitions prepared')
    weights=np.asarray(all_weights,float);weights/=weights.sum()
    return {'fixed':np.asarray(all_fixed,np.float32),'dynamic':np.asarray(all_dynamic,np.float32),
            'log_gap':np.asarray(all_lg,np.float32),'delta_log_capacity':np.asarray(all_dlogc,np.float32),
            'delta_k':np.asarray(all_dk,np.int64),'weight':weights.astype(np.float32),
            'cell_index':np.asarray(all_cell,np.int16),'path_index':np.asarray(all_path,np.int32),
            'step_index':np.asarray(all_step,np.int16),'cell_ids':cell_ids,
            'arm_path_counts':dict(arm_counts),'path_count':path_no,
            'prepared_cell_count':len(set(all_cell)),
            'processed_manifest_sha256':_sha(processed_manifest_path),
            'rpt_manifest_sha256':_sha(rpt_manifest_path)}
