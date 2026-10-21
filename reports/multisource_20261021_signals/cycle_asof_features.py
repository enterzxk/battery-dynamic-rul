#!/usr/bin/env python3
"""As-of alignment for derived ISU-ILCC Cycling signals and RPT features.

No raw data, training, label access, or confirmation-cell access. A cycle is treated
as available at its recorded completion time; network arrival latency is unknown.
"""
import argparse, bisect, gzip, json, math, pathlib, sys
from datetime import datetime, timezone

ROOT=pathlib.Path('/home/yndx/zxk/rul')
OUTDIR=ROOT/'reports/multisource_20261021_signals'

def dt(s):
    if s is None: return None
    if isinstance(s,(int,float)): return datetime.fromtimestamp(float(s),__import__('datetime').timezone.utc).replace(tzinfo=None)
    # Python 3.9 accepts at most microsecond precision; preserve ISO ordering and trim ns only for durations.
    if '.' in s:
        head, tail=s.split('.',1)
        digits=''.join(ch for ch in tail if ch.isdigit())
        suffix=tail[len(digits):]
        s=head+'.'+digits[:6].ljust(6,'0')+suffix
    return datetime.fromisoformat(s)

def _real_iso_dt(value):
    if not isinstance(value,str) or not value.strip() or value.strip()=='[]':
        return None
    try:
        text=value.strip()
        if text.endswith('Z'):
            text=text[:-1]+'+00:00'
        return dt(text)
    except (TypeError,ValueError,OverflowError):
        return None


def safe_cycle_completion(row):
    """Return max(charge.stop, discharge.stop) as UTC epoch, else None.

    Both leg stops must be valid ISO timestamps. Missing/malformed clocks stay unknown.
    """
    charge=row.get('charge') if isinstance(row,dict) else None
    discharge=row.get('discharge') if isinstance(row,dict) else None
    if not isinstance(charge,dict) or not isinstance(discharge,dict):
        return None
    a=_real_iso_dt(charge.get('stop'))
    b=_real_iso_dt(discharge.get('stop'))
    if a is None or b is None:
        return None
    try:
        if a.tzinfo is None:
            a=a.replace(tzinfo=timezone.utc)
        if b.tzinfo is None:
            b=b.replace(tzinfo=timezone.utc)
        return max(float(a.timestamp()),float(b.timestamp()))
    except (ValueError,OverflowError,OSError):
        return None


def _cycle_completion_dt(row):
    epoch=safe_cycle_completion(row)
    return None if epoch is None else datetime.fromtimestamp(epoch,timezone.utc).replace(tzinfo=None)


SAFE_CYCLE_COMPLETION_FIXTURES=(
    ('both_valid',{'charge':{'stop':'2021-01-01T00:00:00'},'discharge':{'stop':'2021-01-01T01:00:00'}},False),
    ('charge_missing',{'charge':{'stop':'[]'},'discharge':{'stop':'2021-01-01T01:00:00'}},True),
    ('discharge_malformed',{'charge':{'stop':'2021-01-01T00:00:00'},'discharge':{'stop':'not-a-time'}},True),
    ('both_missing',{'charge':{'stop':None},'discharge':{'stop':''}},True),
)


def finite_num(x):
    return isinstance(x,(int,float)) and math.isfinite(x)

def duration_seconds(start, stop):
    a,b=_real_iso_dt(start),_real_iso_dt(stop)
    return (b-a).total_seconds() if a is not None and b is not None and b>=a else None

def _capacity(cycle, leg):
    key='capacity_'+leg+'_Ah'
    return cycle.get(key,cycle.get('capacity_'+leg+'_source_units_unknown'))

def _stats(cycle, leg, name):
    return cycle.get(leg,{}).get(name) or {}

def _get(cycle, leg, name, stat):
    return _stats(cycle,leg,name).get(stat)

def cycle_feature_vector(past):
    names=[
        'cycle_count_observed','cycle_throughput_cumulative_Ah','cycle_throughput_valid_count',
        'cycle_hours_since_last_completion',
        'cycle_latest_charge_capacity_Ah','cycle_latest_discharge_capacity_Ah',
        'cycle_latest_charge_duration_s','cycle_latest_discharge_duration_s',
        'cycle_latest_charge_Q_end_Ah','cycle_latest_discharge_Q_end_Ah',
        'cycle_latest_charge_voltage_mean_V','cycle_latest_charge_voltage_min_V','cycle_latest_charge_voltage_max_V',
        'cycle_latest_discharge_voltage_mean_V','cycle_latest_discharge_voltage_min_V','cycle_latest_discharge_voltage_max_V',
        'cycle_latest_charge_current_mean_A','cycle_latest_charge_current_min_A','cycle_latest_charge_current_max_A',
        'cycle_latest_discharge_current_mean_A','cycle_latest_discharge_current_min_A','cycle_latest_discharge_current_max_A',
        'cycle_latest_charge_energy_end_Wh','cycle_latest_discharge_energy_end_Wh'
    ]
    past=[(t,c) for c in past if (t:=_cycle_completion_dt(c)) is not None]
    if not past:
        return names,[0,None,0,None]+[None]*(len(names)-4)
    past.sort(key=lambda x:(x[0],x[1].get('source_cycle_index',-1)))
    past=[c for _,c in past]
    latest=past[-1]
    qsum=0.0; nvalid=0
    for c in past:
        a,b=_capacity(c,'charge'),_capacity(c,'discharge')
        if finite_num(a) and finite_num(b):
            qsum+=a+b; nvalid+=1
    vals=[
        len(past),qsum if nvalid else None,nvalid,0.0,
        _capacity(latest,'charge'),_capacity(latest,'discharge'),
        duration_seconds(latest.get('charge',{}).get('start'),latest.get('charge',{}).get('stop')),
        duration_seconds(latest.get('discharge',{}).get('start'),latest.get('discharge',{}).get('stop')),
        _get(latest,'charge','Q_sample_stats','last'),_get(latest,'discharge','Q_sample_stats','last'),
        _get(latest,'charge','V_V_sample_stats','mean'),_get(latest,'charge','V_V_sample_stats','min'),_get(latest,'charge','V_V_sample_stats','max'),
        _get(latest,'discharge','V_V_sample_stats','mean'),_get(latest,'discharge','V_V_sample_stats','min'),_get(latest,'discharge','V_V_sample_stats','max'),
        _get(latest,'charge','I_A_sample_stats','mean'),_get(latest,'charge','I_A_sample_stats','min'),_get(latest,'charge','I_A_sample_stats','max'),
        _get(latest,'discharge','I_A_sample_stats','mean'),_get(latest,'discharge','I_A_sample_stats','min'),_get(latest,'discharge','I_A_sample_stats','max'),
        _get(latest,'charge','E_sample_stats','last'),_get(latest,'discharge','E_sample_stats','last')
    ]
    return names,vals


class CycleFeatureIndex:
    def __init__(self, cellpayload):
        if isinstance(cellpayload,(str,pathlib.Path)):
            cellpayload=load_cycle_payload(cellpayload)
        if not isinstance(cellpayload,dict) or not isinstance(cellpayload.get('cycles'),list):
            raise ValueError('cycle_payload_must_contain_cycles')
        self.cell_id=cellpayload.get('cell_id')
        self.role=cellpayload.get('role')
        if self.role not in ('train','development') or (self.cell_id and self.cell_id.endswith('C4')):
            raise ValueError('locked_or_unapproved_cell_role')
        source_cycles=cellpayload['cycles']
        self.source_cycle_count=len(source_cycles)
        indexed=[];excluded=[]
        for c in source_cycles:
            t=_cycle_completion_dt(c)
            if t is None:
                excluded.append(c.get('source_cycle_index'))
            else:
                indexed.append((t,c))
        indexed.sort(key=lambda x:(x[0],x[1].get('source_cycle_index',-1)))
        self.times=[x[0] for x in indexed]
        self.rows=[x[1] for x in indexed]
        self.excluded_clock_cycle_indices=excluded
        self.excluded_clock_count=len(excluded)
        self.units=cellpayload.get('units','units documented in external source contract')

    def features_at(self, query_epoch, subset='full'):
        q=dt(query_epoch)
        if q is None: raise ValueError('query_epoch_required')
        n=bisect.bisect_right(self.times,q)
        names,values=cycle_feature_vector(self.rows[:n])
        if n:
            values[3]=(q-self.times[n-1]).total_seconds()/3600.0
        full_names=names
        if subset=='vi_e_time':
            keep=[i for i,k in enumerate(names) if k in VI_E_TIME_FEATURES]
            names=[names[i] for i in keep]; values=[values[i] for i in keep]
        elif subset!='full':
            raise ValueError('unknown_cycle_feature_subset')
        return {'cell_id':self.cell_id,'role':self.role,'query_end':query_epoch,
                'feature_names':names,'values':values,'subset':subset,
                'cycle_source_asof_count':n,
                'cycle_last_source_index':self.rows[n-1].get('source_cycle_index') if n else None,
                'source_arrival_time_observed':False,
                'source_arrival_time_assumption':'assumed available at max(charge.stop, discharge.stop); arrival time is unobserved',
                'cycle_arrival_rule':'same-completion availability assumption; no arrival timestamp observed'}

    def visible_records_at(self, query_epoch):
        q=dt(query_epoch)
        if q is None: raise ValueError('query_epoch_required')
        return self.rows[:bisect.bisect_right(self.times,q)]

VI_E_TIME_FEATURES={
    'cycle_count_observed','cycle_hours_since_last_completion',
    'cycle_latest_charge_duration_s','cycle_latest_discharge_duration_s',
    'cycle_latest_charge_voltage_mean_V','cycle_latest_charge_voltage_min_V','cycle_latest_charge_voltage_max_V',
    'cycle_latest_discharge_voltage_mean_V','cycle_latest_discharge_voltage_min_V','cycle_latest_discharge_voltage_max_V',
    'cycle_latest_charge_current_mean_A','cycle_latest_charge_current_min_A','cycle_latest_charge_current_max_A',
    'cycle_latest_discharge_current_mean_A','cycle_latest_discharge_current_min_A','cycle_latest_discharge_current_max_A',
    'cycle_latest_charge_energy_end_Wh','cycle_latest_discharge_energy_end_Wh'
}

def load_cycle_payload(path):
    path=pathlib.Path(path)
    stem=path.name[:-8] if path.name.endswith('.json.gz') else path.stem
    if stem.endswith('C4'):
        raise ValueError('locked_C4_payload_refused')
    opener=gzip.open if str(path).endswith('.gz') else open
    with opener(path,'rt',encoding='utf-8') as f: return json.load(f)

def build_cycle_index(cellpayload):
    return CycleFeatureIndex(cellpayload)

def build_asof(cycles, query_end, rpt_records=()):
    q=dt(query_end)
    if q is None: raise ValueError('query_end_required')
    visible=[]
    for c in cycles:
        end=_cycle_completion_dt(c)
        if end is not None and end<=q:
            visible.append(c)
    cycle_names,cycle_values=cycle_feature_vector(visible)
    if visible:
        last=max((_cycle_completion_dt(c) for c in visible))
        cycle_values[3]=(q-last).total_seconds()/3600
    valid_rpt=[]
    for r in rpt_records:
        stop=dt(r.get('stop'))
        if r.get('data_v2_valid') is True and stop is not None and stop<=q:
            valid_rpt.append(r)
    visible.sort(key=lambda c: (_cycle_completion_dt(c),c.get('source_cycle_index',-1)))
    latest_rpt=max(valid_rpt,key=lambda r:(dt(r['stop']),r.get('source_rpt_index',-1))) if valid_rpt else None
    curve_names=list(latest_rpt.get('feature_names',[])) if latest_rpt else []
    curve_values=list(latest_rpt.get('values',[])) if latest_rpt else []
    if len(curve_names)!=len(curve_values):
        raise ValueError('rpt_feature_name_value_length_mismatch')
    if len(curve_names)!=len(set(curve_names)):
        raise ValueError('duplicate_rpt_feature_name')
    return {
        'query_end':query_end,
        'cycle_source_arrival_time_observed':False,
        'cycle_source_arrival_time_assumption':'assumed available at max(charge.stop, discharge.stop); source arrival/transport latency was not measured',
        'cycle_latest_assumed_arrival_time':_cycle_completion_dt(visible[-1]).isoformat() if visible else None,
        'cycle_source_record_count':len(cycles),
        'cycle_clock_excluded_count':sum(safe_cycle_completion(c) is None for c in cycles),
        'cycle_clock_excluded_source_indices':[c.get('source_cycle_index') for c in cycles if safe_cycle_completion(c) is None],
        'cycle_availability_rule':'assume source cycle signals are available at max(charge.stop, discharge.stop); actual data-arrival latency is unknown',
        'rpt_source_arrival_time_observed':False,
        'rpt_visibility_basis':'valid RPT features become measurement-visible at source stop; actual data delivery latency was not measured in this asset',
        'cycle_source_asof_count':len(visible),
        'cycle_last_source_index':visible[-1].get('source_cycle_index') if visible else None,
        'cycle_feature_names':cycle_names,
        'cycle_feature_values':cycle_values,
        'rpt_availability_rule':'RPT features visible at their source DataV2 stop timestamp; only valid records with stop <= query_end',
        'rpt_latest_source_index':latest_rpt.get('source_rpt_index') if latest_rpt else None,
        'rpt_latest_stop':latest_rpt.get('stop') if latest_rpt else None,
        'rpt_feature_names':curve_names,
        'rpt_feature_values':curve_values,
        'F2_increment_feature_names':cycle_names,
        'F2_increment_values':cycle_values,
        'F3_increment_feature_names':cycle_names+curve_names,
        'F3_increment_values':cycle_values+curve_values,
        'panel_note':'These are the cycle and latest-RPT increments only; append the identical F0 baseline vector to obtain full F2/F3 panels.'
    }

def validate_prefix(records, queries):
    for q in queries:
        z=build_asof(records['cycles'],q,records['rpt'])
        assert all(_cycle_completion_dt(c)<=dt(q) for c in records['cycles'] if _cycle_completion_dt(c) is not None and _cycle_completion_dt(c)<=dt(q))
        if z['rpt_latest_stop']: assert dt(z['rpt_latest_stop'])<=dt(q)
        assert 'cycle_last_source_index' not in z['F2_increment_feature_names']
        assert len(z['F2_increment_feature_names'])==len(z['F2_increment_values'])
        assert len(z['F3_increment_feature_names'])==len(z['F3_increment_values'])
    return True

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--cycles',required=True); ap.add_argument('--rpt',required=True)
    ap.add_argument('--cell-id',required=True); ap.add_argument('--out',required=True)
    a=ap.parse_args()
    cy=json.load(open(a.cycles)); rp=json.load(open(a.rpt))
    assert cy['cell_id']==a.cell_id and rp['cell_id']==a.cell_id
    assert cy['role'] in ('train','development') and rp['role']==cy['role']
    queries=[r['stop'] for r in rp['records'] if r.get('data_v2_valid') is True]
    rows=[build_asof(cy['cycles'],q,rp['records']) for q in queries]
    for q,row in zip(queries,rows):
        assert row['query_end']==q
        assert row['rpt_latest_stop'] is None or dt(row['rpt_latest_stop'])<=dt(q)
    out={'cell_id':a.cell_id,'role':cy['role'],'source_cycle_count':cy['cycle_count'],
         'query_count':len(rows),'units':'Ah, Wh, V, A per ISU-ILCC V2.0 readme_text page 5',
         'arrival_limitation':'Cycle arrival time is unobserved; same-as-completion availability is an explicit assumption, not measured transport latency. RPT source features are visible at measurement stop; transport arrival is unobserved here.',
         'rows':rows}
    with open(a.out,'x') as f: json.dump(out,f,separators=(',',':'),allow_nan=False)
    print(json.dumps({'status':'SUCCESS','cell_id':a.cell_id,'queries':len(rows),'output':a.out}))
if __name__=='__main__': main()
