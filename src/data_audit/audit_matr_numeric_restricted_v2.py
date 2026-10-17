#!/usr/bin/env python3
"""MATR v11 的受限结构/EOL审计；一次只解码一个电芯，不训练。
重启时使用相同 --run-dir，复用已验证的逐电芯审计文件。
"""
import argparse
import copyreg
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import pickle
import re
import sys
import uuid
import zipfile
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')
import numpy as np

from primitive_pickle import load_numeric_scalars
ROOT=Path('/home/yndx/zxk/rul')
ARCHIVE=ROOT/'data/raw/MATR/MATR_v11.zip'
ARCHIVE_SHA='2b7403134c05bef02fd5b4ee20badf00ea9db6e7fd1445b9630e56cf69e95091'
CORE=['current_in_A','voltage_in_V','charge_capacity_in_Ah','discharge_capacity_in_Ah','time_in_s']
class PrimitiveUnpickler(pickle.Unpickler):
    def find_class(self,module,name):
        raise pickle.UnpicklingError('All globals/classes prohibited: '+module+'.'+name)
    def persistent_load(self,pid):
        raise pickle.UnpicklingError('All persistent IDs prohibited')
def sha_file(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for buf in iter(lambda:f.read(8*1024*1024),b''):h.update(buf)
    return h.hexdigest()
def write_new(path,data):
    with path.open('x',encoding='utf-8') as f:
        json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run-dir');args=ap.parse_args()
    run=Path(args.run_dir).resolve() if args.run_dir else ROOT/'reports/matr_schema_audit'/dt.datetime.now(dt.timezone.utc).strftime('run_%Y%m%dT%H%M%S%fZ')
    if ROOT not in run.parents:raise ValueError('Run path outside project')
    run.mkdir(parents=True,exist_ok=True);(run/'cells').mkdir(exist_ok=True)
    import fcntl
    lock=(run/'run.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if sha_file(ARCHIVE)!=ARCHIVE_SHA:raise ValueError('Source archive SHA mismatch')
    source_receipt=json.loads((ROOT/'data/raw/MATR/MATR_v11.receipt.json').read_text())
    if source_receipt.get('zip_crc')!='PASS':raise ValueError('Archive CRC receipt missing')
    if not (run/'source.json').exists():
        write_new(run/'source.json',{'archive':str(ARCHIVE),'sha256':ARCHIVE_SHA,'zenodo_record':'19688272',
            'script_sha256':sha_file(Path(__file__)),'no_training':True,'started_at':dt.datetime.now(dt.timezone.utc).isoformat()})
    labels_zip=ROOT/'data/raw/HUST/Life_labels_v11.zip'
    with zipfile.ZipFile(labels_zip) as z:
        label_data=z.read('Life labels/MATR_labels.json')
        labels=json.loads(label_data)
    records=[]
    with zipfile.ZipFile(ARCHIVE) as z:
        entries=[info for info in z.infolist() if not info.is_dir()]
        if len(entries)!=169:raise ValueError('Expected 169 MATR cells')
        if sum(info.file_size for info in entries)>20*1024**3:raise ValueError('Uncompressed budget exceeded')
        for i,info in enumerate(entries,1):
            if not re.fullmatch(r'MATR/MATR_[A-Za-z0-9_-]+[.]pkl',info.filename) or info.file_size>512*1024**2:
                raise ValueError('Unsafe/unexpected member: '+info.filename)
            name=Path(info.filename).name
            out=run/'cells'/(name+'.json')
            if out.exists():
                record=json.loads(out.read_text())
                series=Path(record['cycle_summary_path'])
                if (record['archive_sha256']!=ARCHIVE_SHA or record['zip_member']!=info.filename
                    or record['zip_crc32']!='%08x'%info.CRC or sha_file(series)!=record['cycle_summary_sha256']):
                    raise ValueError('Existing cell receipt differs; preserve and inspect')
                records.append(record);continue
            raw=z.read(info.filename)
            raw_sha=hashlib.sha256(raw).hexdigest()
            # EXT缓存清空在本进程内进行，所有构造器和persistent-id仍全部拒绝。
            copyreg._extension_cache.clear()
            obj,scalar_receipt=load_numeric_scalars(raw);del raw
            if not isinstance(obj,dict) or not isinstance(obj.get('cycle_data'),list):
                raise ValueError('Expected primitive cell dict and cycle list')
            cycles=obj['cycle_data'];cell_id=obj.get('cell_id')
            if cell_id!=name[:-4]:raise ValueError('cell_id/filename identity mismatch')
            nominal=float(obj['nominal_capacity_in_Ah']);soc=obj['SOC_interval']
            width=float(soc[1])-float(soc[0])
            if not np.isfinite(nominal) or nominal<=0 or not 0<width<=1:raise ValueError('Invalid nominal/SOC metadata')
            threshold=.8*nominal*width
            missing=length_mismatch=nonfinite=non_numeric=time_backward=time_repeat=0
            temperature_null=internal_resistance_null=0
            field_sets=set();numbers=[];capacity=[];series=[]
            for position,c in enumerate(cycles,1):
                if not isinstance(c,dict):raise ValueError('Expected primitive cycle dict')
                field_sets.add(tuple(sorted(c)))
                actual=c.get('cycle_number')
                if isinstance(actual,bool) or not isinstance(actual,(int,float)) or not np.isfinite(actual) or int(actual)!=actual or actual<=0:
                    raise ValueError('Invalid actual cycle number')
                numbers.append(int(actual));arrays={};lengths={}
                for field in CORE:
                    v=c.get(field)
                    if not isinstance(v,(list,tuple)) or not v:
                        missing+=1;continue
                    a=np.asarray(v)
                    lengths[field]=len(a)
                    if a.ndim!=1 or a.dtype.kind not in 'ifu':
                        non_numeric+=1;continue
                    nonfinite+=int((~np.isfinite(a)).sum());arrays[field]=a
                if len(set(lengths.values()))>1:length_mismatch+=1
                q=arrays.get('discharge_capacity_in_Ah')
                qmax=float(q.max()) if q is not None and np.isfinite(q).all() else None
                capacity.append(qmax)
                t=arrays.get('time_in_s')
                back=repeat=0
                if t is not None and np.isfinite(t).all():
                    delta=np.diff(t);back=int((delta<0).sum());repeat=int((delta==0).sum())
                    time_backward+=back;time_repeat+=repeat
                temperature_null+=int(c.get('temperature_in_C') is None)
                internal_resistance_null+=int(c.get('internal_resistance_in_ohm') is None)
                series.append({'row_position_1based':position,'actual_cycle_number':int(actual),'capacity_Ah':qmax,
                               'time_backward_pairs':back,'time_repeat_pairs':repeat})
            if any(b<=a for a,b in zip(numbers,numbers[1:])):raise ValueError('Actual cycle numbers not strictly increasing')
            first=next((k for k,q in enumerate(capacity) if q is not None and q<=threshold),None)
            first_ref=capacity[0] if capacity else None
            first_initial=next((k for k,q in enumerate(capacity) if q is not None and first_ref is not None and q<=.8*first_ref),None)
            label=labels.get(name)
            cycle_path=run/'cells'/(name+'.cycles.json')
            if cycle_path.exists():cycle_path=run/'cells'/(name+'.cycles.'+uuid.uuid4().hex+'.json')
            write_new(cycle_path,series)
            record={'archive_sha256':ARCHIVE_SHA,'zip_member':info.filename,'zip_crc32':'%08x'%info.CRC,
                'source_bytes':info.file_size,'source_sha256':raw_sha,'numeric_scalar_decoding':scalar_receipt,'source_cell_id':cell_id,'cycle_rows':len(cycles),
                'actual_cycle_min':min(numbers),'actual_cycle_max':max(numbers),'actual_equals_row':all(k==n for k,n in enumerate(numbers,1)),
                'nominal_capacity_Ah':nominal,'soc_interval':soc,'nominal_threshold_80pct_Ah':threshold,
                'observed_nominal_crossing_row':first+1 if first is not None else None,
                'observed_nominal_crossing_actual':numbers[first] if first is not None else None,
                'first_capacity_crossing_row_diagnostic_only':first_initial+1 if first_initial is not None else None,
                'first_capacity_Ah':first_ref,'last_capacity_Ah':capacity[-1],
                'v11_author_label':label,'author_label_generator_version':'UNVERIFIED',
                'label_equals_nominal_observed_row':label==first+1 if first is not None else None,
                'missing_core_fields':missing,'length_mismatch_cycles':length_mismatch,'nonfinite_core_values':nonfinite,
                'nonnumeric_core_curves':non_numeric,'within_cycle_time_backward_pairs':time_backward,'within_cycle_time_duplicate_pairs':time_repeat,
                'temperature_null_cycles':temperature_null,'internal_resistance_null_cycles':internal_resistance_null,
                'cycle_field_sets':[list(x) for x in sorted(field_sets)],
                'cycle_summary_path':str(cycle_path),'cycle_summary_sha256':sha_file(cycle_path),
                'new_fits':0,'optimizer_steps':0,'identity_limit':'official filename/cell_id only; raw source continuity mapping requires code audit'}
            write_new(out,record);records.append(record)
            del cycles,obj,series,arrays
            print(json.dumps({'event':'cell_audited','index':i,'total':len(entries),'cell':cell_id,
                              'cycles':record['cycle_rows'],'observed_nominal_crossing':first is not None}),flush=True)
    summary={'status':'RESTRICTED_SCHEMA_EOL_AUDIT_ONLY','archive_sha256':ARCHIVE_SHA,'cells':len(records),
        'cycles':sum(x['cycle_rows'] for x in records),
        'observed_nominal_crossing_cells':sum(x['observed_nominal_crossing_row'] is not None for x in records),
        'unobserved_nominal_eol_cells':sum(x['observed_nominal_crossing_row'] is None for x in records),
        'label_equals_observed_nominal_crossing_row_cells':sum(x['label_equals_nominal_observed_row'] is True for x in records),
        'sum_missing_core_fields':sum(x['missing_core_fields'] for x in records),
        'sum_length_mismatch_cycles':sum(x['length_mismatch_cycles'] for x in records),
        'sum_nonfinite_core_values':sum(x['nonfinite_core_values'] for x in records),
        'sum_nonnumeric_core_curves':sum(x['nonnumeric_core_curves'] for x in records),
        'distinct_source_sha256':len({x['source_sha256'] for x in records}),
        'new_fits':0,'optimizer_steps':0,'completed_at':dt.datetime.now(dt.timezone.utc).isoformat(),
        'limits':['Observed crossing definition is nominal fraction 0.8 at first at-or-below; not yet a frozen predictive protocol',
                  'Author EOL generation chain and raw physical identity are not proven by numeric agreement',
                  'No official-loader model tensors, predictions or training results were created']}
    if not (run/'summary.json').exists():write_new(run/'summary.json',summary)
    print(json.dumps({'run_dir':str(run),**summary}),flush=True)
if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'status':'FAILED_PRESERVE_PARTIAL_AUDITS','error':str(exc)}),flush=True)
        raise
