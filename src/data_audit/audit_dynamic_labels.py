#!/usr/bin/env python3
"""从已审计的周期诊断CSV构造标签审计；不生成模型训练集。"""
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path('/home/yndx/zxk/rul')
sys.path.insert(0,str(ROOT/'src'))
from rul_benchmark.queries import EOLRule, build_queries

def main():
    source=ROOT/'data/processed/audit_only/run_20261015T164049_918837Z/hust_v9_cycle_diagnostics.csv'
    h=hashlib.sha256()
    with source.open('rb') as inp:
        for buf in iter(lambda:inp.read(4*1024*1024),b''):h.update(buf)
    sha=h.hexdigest()
    expected='f6201620d22635062354d46fbf45f55d7f63cf3a1008c5df5760fed4a634c3d4'
    if sha!=expected:raise RuntimeError('Audited CSV source changed')
    cells={}
    with source.open() as inp:
        for row in csv.DictReader(inp):
            key=(row['file_name'],row['cell_id'])
            cells.setdefault(key,[]).append({'row_position_1based':int(row['cycle_index_1based']),
                'actual_cycle_number':int(row['cycle_number']),'capacity_Ah':float(row['max_discharge_capacity_Ah'])})
    run=ROOT/'reports/dynamic_label_audit'/dt.datetime.now(dt.timezone.utc).strftime('run_%Y%m%dT%H%M%S%fZ')
    run.mkdir(parents=True,exist_ok=False)
    # 这里只是审计grid；不是已冻结的训练/验证/测试协议。
    grid=[10,25,50,75,100,150,200,300,500,750,1000]
    summaries=[];query_count=0
    with (run/'query_audit_only.jsonl').open('x',encoding='utf-8') as out:
        for (file_name,cell_id),rows in sorted(cells.items()):
            results={}
            for kind in ['nominal','first_observed_cycle']:
                rule=EOLRule('nominal',1.1) if kind=='nominal' else EOLRule('first_observed_cycle')
                result=build_queries(rows,grid,rule=rule,cycle_index_space='actual_cycle_number',
                    label_source_sha256=sha,future_policy_id='realized_HUST_lab_discharge_protocol_no_future_oracle')
                results[kind]={'definition_id':result['eol_definition_id'],'label_status':result['label_status'],
                    'observed_eol_cycle':result['observed_eol_cycle'],'last_observed_cycle':result['last_observed_cycle'],
                    'n_queries':len(result['queries']),'n_omitted_queries':len(result['omitted_queries'])}
                for query in result['queries']:
                    # 身份仅为源文件声明，未发布physical identity verified manifest。
                    out.write(json.dumps({'scope':'AUDIT_ONLY_NOT_TRAINING_INPUT','source_file':file_name,'source_cell_id':cell_id,
                        'denominator_diagnostic':kind,**query},ensure_ascii=False,separators=(',',':'))+'\n')
                    query_count+=1
            summaries.append({'file_name':file_name,'source_cell_id':cell_id,'definitions':results})
    result={'status':'LABEL_AUDIT_ONLY','source':str(source),'source_sha256':sha,'cells':len(cells),
        'cycles':sum(len(v) for v in cells.values()),'query_grid_audit_only':grid,'query_grid_frozen_for_training':False,
        'query_records':query_count,'nominal_observed_cells':sum(x['definitions']['nominal']['label_status']=='observed_crossing' for x in summaries),
        'nominal_censored_cells':sum(x['definitions']['nominal']['label_status']=='right_censored' for x in summaries),
        'first_cycle_observed_cells_diagnostic_only':sum(x['definitions']['first_observed_cycle']['label_status']=='observed_crossing' for x in summaries),
        'per_cell':summaries,'new_fits':0,'optimizer_steps':0,
        'limits':['v9 source and v11 author-label version chain remains separate','First-cycle denominator is a separate diagnostic, never silently substituted','No verified physical-identity role manifest or model-ready training set was generated','No prediction or performance evaluation was run']}
    with (run/'summary.json').open('x',encoding='utf-8') as out:json.dump(result,out,ensure_ascii=False,indent=2);out.write('\n')
    qsha=hashlib.sha256((run/'query_audit_only.jsonl').read_bytes()).hexdigest()
    receipt={'summary_path':str(run/'summary.json'),'queries_path':str(run/'query_audit_only.jsonl'),'queries_sha256':qsha,
        'query_generator_sha256':hashlib.sha256((ROOT/'src/rul_benchmark/queries.py').read_bytes()).hexdigest(),
        'source_csv_sha256':sha,'new_fits':0,'optimizer_steps':0}
    with (run/'receipt.json').open('x',encoding='utf-8') as out:json.dump(receipt,out,indent=2);out.write('\n')
    print(json.dumps({k:result[k] for k in ['status','cells','cycles','query_records','nominal_observed_cells','nominal_censored_cells','first_cycle_observed_cells_diagnostic_only']}))
    print(json.dumps(receipt))
if __name__=='__main__':main()
