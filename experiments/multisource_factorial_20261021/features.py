#!/usr/bin/env python3
"""Formal 2x2 multi-source feature adapter. No fitting or label access."""
from __future__ import annotations
import math
import pathlib
import sys
from typing import Dict, Mapping, Sequence

import numpy as np

ROOT=pathlib.Path('/home/yndx/zxk/rul')
OLD=ROOT/'experiments/isu_irregular_rul_seed42_v1'
SIGNALS=ROOT/'reports/multisource_20261021_signals'
sys.path.insert(0,str(OLD))
sys.path.insert(0,str(SIGNALS))
import baselines
import data_adapter
import cycle_asof_features as cycle_asof

RPT_SCALARS=[
    'src_capacity_charge_C_2','src_capacity_discharge_C_2',
    'src_capacity_charge_C_5','src_capacity_discharge_C_5'
]
RPT_CURVES=[
    f'C{rate}_{leg}_{kind}_at_V{v:.2f}'
    for rate in (2,5)
    for leg in ('charge','discharge')
    for kind in ('Q','dQdV')
    for v in np.linspace(3.0,4.2,25)
]
RPT_FULL=RPT_SCALARS+RPT_CURVES
RPT_SUFFIXES=('latest','delta_from_first','past_slope_per_week')
WEEK_SECONDS=604800.0

def f0_names(group_id):
    g=str(group_id)
    return [
        'origin_age_weeks','last_capacity_over_nominal','last_rpt_gap_weeks',
        'last_capacity_slope_ah_per_week','visible_rpt_count',
        'last_rpt_calendar_age_weeks','query_gap_from_last_rpt_weeks',
        'first_capacity_over_nominal','recent_theilsen_slope_over_nominal_per_week',
        'last_capacity_trend_residual_over_nominal'
    ]+[f'group_{i+1}_onehot' for i in range(64)]

def _as_float(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else np.nan
    except (TypeError,ValueError):
        return np.nan

def _feature_dict(record):
    names=record.get('feature_names',[])
    vals=record.get('values',[])
    if len(set(names))!=len(names):
        raise ValueError('RPT feature name/value schema mismatch')
    if isinstance(vals,Mapping):
        if set(names)!=set(vals): raise ValueError('RPT feature name/value keys mismatch')
        return {k:_as_float(vals.get(k)) for k in names}
    if len(names)!=len(vals): raise ValueError('RPT feature name/value schema mismatch')
    return {k:_as_float(v) for k,v in zip(names,vals)}

def _visible_rpt(example, rpt_cache):
    cid=str(example['cell_id']);q=float(example['query_epoch'])
    visible=example.get('visible_records',[])
    out=[]
    ids=set()
    for r in visible:
        idx=int(r['source_rpt_index'])
        if idx in ids: raise ValueError('duplicate visible source_rpt_index')
        ids.add(idx)
        arrival=float(r['arrival_epoch']);stop=float(r['stop_epoch'])
        if not (stop<=arrival<=q):
            raise ValueError('RPT stop/arrival/query visibility barrier failed')
        try: feature_record=rpt_cache[cid][idx]
        except KeyError: raise ValueError(f'missing RPT feature cache entry: {cid}/{idx}')
        if int(feature_record['source_rpt_index'])!=idx:
            raise ValueError('RPT feature cache source index mismatch')
        if feature_record.get('data_v2_valid') is not True:
            raise ValueError('invalid RPT feature record entered visible history')
        d=data_adapter._dt(feature_record['stop'])
        if abs(d.timestamp()-stop)>1e-3:
            raise ValueError('RPT feature cache stop timestamp mismatch')
        if feature_record.get('features_visible_at')!='stop':
            raise ValueError('unexpected RPT source visibility marker')
        out.append((r,feature_record,_feature_dict(feature_record)))
    return out

def _rpt_full_vector(example, rpt_cache):
    visible=_visible_rpt(example,rpt_cache)
    names=[f'rpt_{k}_{s}' for s in RPT_SUFFIXES for k in RPT_FULL]
    if not visible: return names,np.full(len(names),np.nan)
    first,last=visible[0],visible[-1]
    q=float(example['query_epoch'])
    if last[0]['arrival_epoch']>q: raise ValueError('last RPT arrival exceeds query')
    a=np.asarray([last[2].get(k,np.nan) for k in RPT_FULL],float)
    b=np.asarray([first[2].get(k,np.nan) for k in RPT_FULL],float)
    nominal=float(example.get('nominal_capacity_ah',.25))
    if not math.isfinite(nominal) or nominal<=0: raise ValueError('invalid nominal capacity')
    a=a/nominal;b=b/nominal
    dt=(float(last[0]['stop_epoch'])-float(first[0]['stop_epoch']))/WEEK_SECONDS
    slope=(a-b)/max(dt,1e-6)
    return names,np.r_[a,a-b,slope]

def _rpt_scalar_vector(example,rpt_cache):
    visible=_visible_rpt(example,rpt_cache)
    names=[f'rpt_scalar_{k}_{s}' for s in RPT_SUFFIXES for k in RPT_SCALARS]
    if not visible: return names,np.full(len(names),np.nan)
    a=np.asarray([visible[-1][2].get(k,np.nan) for k in RPT_SCALARS],float)
    b=np.asarray([visible[0][2].get(k,np.nan) for k in RPT_SCALARS],float)
    nominal=float(example.get('nominal_capacity_ah',.25))
    a=a/nominal;b=b/nominal
    dt=(float(visible[-1][0]['stop_epoch'])-float(visible[0][0]['stop_epoch']))/WEEK_SECONDS
    return names,np.r_[a,a-b,(a-b)/max(dt,1e-6)]

def _shape_vector(example,rpt_cache):
    visible=_visible_rpt(example,rpt_cache)
    curve_keys=RPT_CURVES
    names=[f'rpt_shape_{k}_{s}' for s in RPT_SUFFIXES for k in curve_keys]
    if not visible: return names,np.full(len(names),np.nan)
    def normalized(item):
        f=item[2];out=[]
        for k in curve_keys:
            parts=k.split('_');rate=int(parts[0][1:]);leg=parts[1]
            cap=f.get(f'src_capacity_{leg}_C_{rate}',np.nan)
            val=f.get(k,np.nan)
            out.append(val/cap if math.isfinite(val) and math.isfinite(cap) and cap>0 else np.nan)
        return np.asarray(out,float)
    a=normalized(visible[-1]);b=normalized(visible[0])
    dt=(float(visible[-1][0]['stop_epoch'])-float(visible[0][0]['stop_epoch']))/WEEK_SECONDS
    return names,np.r_[a,a-b,(a-b)/max(dt,1e-6)]

def feature_names(group_id):
    base=f0_names(group_id)
    full=[f'rpt_{k}_{s}' for s in RPT_SUFFIXES for k in RPT_FULL]
    cyc,_=cycle_asof.cycle_feature_vector([{'source_visible_at':'2000-01-01T00:00:00',
        'charge':{},'discharge':{},'capacity_charge_Ah':None,'capacity_discharge_Ah':None}])
    vi=[n for n in cyc if n in cycle_asof.VI_E_TIME_FEATURES]
    scalar=[f'rpt_scalar_{k}_{s}' for s in RPT_SUFFIXES for k in RPT_SCALARS]
    shape=[f'rpt_shape_{k}_{s}' for s in RPT_SUFFIXES for k in RPT_CURVES]
    mixed=scalar+shape
    vi=[n for n in cyc if n in cycle_asof.VI_E_TIME_FEATURES]
    return {
        'F0':base,
        'F1':base+full,
        'F2':base+cyc,
        'F3':base+full+cyc,
        'control_rpt_scalar_only':base+scalar,
        'control_capacity_normalized_shape_only':base+shape,
        'control_rpt_scalar_plus_shape':base+mixed,
        'control_rpt_scalar_plus_shape_cycle':base+mixed+cyc,
        'control_rpt_full_vi_e_time':base+full+vi,
        'control_cycle_vi_e_time_only':base+vi
    }

def feature_sets(example, rpt_cache, cycle_index):
    """Return named factor arrays for one V18 causal example/query."""
    if 'x_query' not in example or len(example['x_query'])!=74:
        raise ValueError('F0 must be the frozen V18 74-vector at this same query')
    base=np.asarray(example['x_query'],float)
    if base.shape!=(74,): raise ValueError('F0 dimension mismatch')
    if 'visible_records' in example:
        _visible_rpt(example,rpt_cache)
    rn,rv=_rpt_full_vector(example,rpt_cache)
    sn,sv=_rpt_scalar_vector(example,rpt_cache)
    shn,shv=_shape_vector(example,rpt_cache)
    cyc=cycle_index.features_at(float(example['query_epoch']),subset='full')
    cvi=cycle_index.features_at(float(example['query_epoch']),subset='vi_e_time')
    if len(cyc['values'])!=24 or len(cvi['values'])!=18:
        raise ValueError('cycle signal feature dimension mismatch')
    cv=np.asarray(cyc['values'],float);viv=np.asarray(cvi['values'],float)
    if len(rn)!=612 or len(rv)!=612 or len(sn)!=12 or len(sv)!=12 or len(shn)!=600 or len(shv)!=600:
        raise ValueError('RPT feature dimension mismatch')
    return {
        'F0':base,
        'F1':np.r_[base,rv],
        'F2':np.r_[base,cv],
        'F3':np.r_[base,rv,cv],
        'control_rpt_scalar_only':np.r_[base,sv],
        'control_capacity_normalized_shape_only':np.r_[base,shv],
        'control_rpt_scalar_plus_shape':np.r_[base,sv,shv],
        'control_rpt_scalar_plus_shape_cycle':np.r_[base,sv,shv,cv],
        'control_rpt_full_vi_e_time':np.r_[base,rv,viv],
        'control_cycle_vi_e_time_only':np.r_[base,viv]
    }

def source_end_metadata(example, cycle_index, rpt_cache):
    visible=_visible_rpt(example,rpt_cache)
    cyc=cycle_index.features_at(float(example['query_epoch']))
    return {
        'cell_id':str(example['cell_id']),'role':str(example.get('role','unknown')),
        'arm':str(example.get('arm','raw')),'query_epoch':float(example['query_epoch']),
        'history_key':example.get('history_key'),
        'visible_rpt_source_indices':[int(r[0]['source_rpt_index']) for r in visible],
        'visible_rpt_source_stops':[r[0]['stop'] for r in visible],
        'visible_rpt_arrival_epochs':[float(r[0]['arrival_epoch']) for r in visible],
        'cycle_source_asof_count':cyc['cycle_source_asof_count'],
        'cycle_latest_source_index':cyc['cycle_last_source_index'],
        'cycle_latest_source_visible_at':cycle_index.rows[cyc['cycle_source_asof_count']-1].get('source_visible_at') if cyc['cycle_source_asof_count'] else None,
        'cycle_source_arrival_time_observed':False,
        'cycle_source_arrival_time_assumption':cyc['source_arrival_time_assumption'],
        'RPT_source_arrival_observed':False,
        'visibility_barrier':'RPT sample_stop <= arm arrival <= query; cycle max(charge.stop,discharge.stop) <= query'
    }

def build_factorial_cache(examples, rpt_cache, cycle_indices):
    """Build the seven predeclared panels; all share identical example/query rows."""
    import numpy as np
    out={};names=None;metadata=[]
    for e in examples:
        cid=str(e['cell_id'])
        if cid not in cycle_indices: raise ValueError('missing cycle index '+cid)
        row=feature_sets(e,rpt_cache,cycle_indices[cid])
        rownames=feature_names(e.get('group_id',''))
        if names is None: names=rownames
        elif names!=rownames: raise ValueError('feature-name order changed across rows')
        for k,v in row.items():
            if k not in out: out[k]=[]
            expected=len(names[k])
            if len(v)!=expected: raise ValueError(f'{k} dimension mismatch {len(v)} != {expected}')
            out[k].append(np.asarray(v,float))
        metadata.append(source_end_metadata(e,cycle_indices[cid],rpt_cache))
    return {'feature_names':names,
            'matrices':{k:np.stack(v) if v else np.empty((0,len(names[k]))) for k,v in out.items()},
            'source_end_metadata':metadata}

def save_feature_cache(result, output_prefix):
    """Create-only compact NPZ vectors plus row metadata; no labels."""
    p=pathlib.Path(output_prefix)
    npz=p.with_suffix('.npz');meta=p.with_suffix('.metadata.json')
    arrays={k:np.asarray(v,float) for k,v in result['matrices'].items()}
    with npz.open('xb') as f: np.savez_compressed(f,**arrays)
    payload={'schema':'MULTISOURCE_FACTORIAL_FEATURE_CACHE_V1',
             'rows':len(result['source_end_metadata']),
             'dimensions':{k:len(v) for k,v in result['feature_names'].items()},
             'feature_names':result['feature_names'],
             'source_end_metadata':result['source_end_metadata']}
    with meta.open('x') as f:
        import json
        json.dump(payload,f,separators=(',',':'),allow_nan=False)
    return npz,meta

if __name__=='__main__':
    raise SystemExit('Import the API from the GO-gated parent runner; no implicit data reads.')
def load_safe_v18_cell(path):
    """Read only the source-history fields needed by frozen V18 features; skip endpoint fields."""
    import ijson
    allowed={'cell_id','group_id','role','nominal_capacity_ah','baseline_stop'}
    out={}; records=[]; current=None
    with open(path,'rb') as f:
        for prefix,event,value in ijson.parse(f):
            if prefix in allowed and event in ('string','number'):
                out[prefix]=value
            elif prefix=='records.item' and event=='start_map':
                current={}
            elif current is not None and prefix.startswith('records.item.') and event != 'end_map':
                key=prefix.rsplit('.',1)[-1]
                if key in {'source_rpt_index','start','stop','capacityAh','valid','calendar_age_seconds'} and event in ('string','number','boolean','null'):
                    current[key]=value
            elif current is not None and prefix=='records.item' and event=='end_map':
                if current.get('valid') is True:
                    records.append(current)
                current=None
    if not all(k in out for k in allowed) or not records:
        raise ValueError('safe V18 history fields missing')
    out['records']=records
    return out

def examples_from_query_grid(grid, cell):
    """Build feature-only V18 rows from a pure query grid and source-history records."""
    from datetime import datetime, timezone
    byidx={int(r['source_rpt_index']):r for r in cell['records']}
    baseline=datetime.fromisoformat(str(cell['baseline_stop']).replace('Z','+00:00'))
    if baseline.tzinfo is None: baseline=baseline.replace(tzinfo=timezone.utc)
    examples=[]
    for qrow in grid:
        if str(qrow['cell_id'])!=str(cell['cell_id']): continue
        q=float(qrow['query_epoch']); ids=[int(i) for i in qrow['visible_rpt_source_indices']]
        stops=[float(v) for v in qrow['visible_rpt_source_stop_epochs']]
        arrivals=[float(v) for v in qrow['visible_rpt_arrival_epochs']]
        if not (len(ids)==len(stops)==len(arrivals)) or not ids: raise ValueError('grid source-index alignment mismatch')
        visible=[]
        for idx,stop,arrival in zip(ids,stops,arrivals):
            src=byidx[idx]
            from datetime import datetime
            d=datetime.fromisoformat(str(src['stop']).replace('Z','+00:00'))
            if d.tzinfo is None: d=d.replace(tzinfo=timezone.utc)
            if abs(d.timestamp()-stop)>1e-3 or not stop<=arrival<=q: raise ValueError('grid/source visibility mismatch')
            age=(d-baseline).total_seconds()/WEEK_SECONDS
            visible.append({'source_rpt_index':idx,'start':src['start'],'stop':src['stop'],
                'stop_epoch':stop,'arrival_epoch':arrival,'capacityAh':float(src['capacityAh']),
                'calendar_age_weeks':age})
        latest=visible[-1]
        view={'cell_id':str(cell['cell_id']),'group_id':str(cell['group_id']),'role':str(cell['role']),
              'nominal_capacity_ah':float(cell['nominal_capacity_ah']),
              'origin_stop_epoch':q,'origin_age_weeks':latest['calendar_age_weeks']+(q-latest['stop_epoch'])/WEEK_SECONDS,
              'visible_records':visible}
        examples.append({'cell_id':str(cell['cell_id']),'group_id':str(cell['group_id']),'role':str(cell['role']),
            'nominal_capacity_ah':float(cell['nominal_capacity_ah']),'arm':qrow['arm'],'query_epoch':q,
            'visible_records':visible,'x_query':np.asarray(baselines.features(view),float),
            'history_key':qrow.get('history_key')})
    return examples
