#!/usr/bin/env python3
# 中文注释：仅在确认 SHA-256 后，以禁止所有全局类和 persistent ID 的自定义 Unpickler 解析；不训练、不拟合。
import csv, hashlib, io, json, math, os, pickle, zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/home/yndx/zxk/rul')
ARCHIVE = ROOT/'data/raw/HUST/HUST_v9.zip'
EXTRACTED = ROOT/'data/raw/HUST/extracted_v9/HUST'
LABEL_ARCHIVE = ROOT/'data/raw/HUST/Life_labels_v11.zip'
STATIC_AUDIT = ROOT/'data/source_audit/pickletools_full_static_HUST_all.json'
CODE_ROOT = ROOT/'repos/pinned/BatteryLife_3b17bb53202e10711deae0448c91f84144bb3dd9'
BATTERYLIFE_COMMIT = '3b17bb53202e10711deae0448c91f84144bb3dd9'
LABEL_RECORD = '19688272'
NOMINAL_CAPACITY_AH = 1.1 # HUST v9 metadata and official HUST preprocessor
EXPECTED_ARCHIVE_SHA256 = 'eb89ae0c384c62934b333009c1bae47d819e9fce55a98f71f3b27d4814b21b08'
EXPECTED_LABEL_ARCHIVE_SHA256 = '45b3adf3f5ea2819244ac206f204defd4eea0ad1eaa4d38534f0543cab4ac033'

class DenyAllUnpickler(pickle.Unpickler):
    """No imports, no class globals, no extension globals, and no persistent ids."""
    def find_class(self, module, name):
        raise pickle.UnpicklingError('BLOCKED_GLOBAL:%s.%s' % (module, name))
    def persistent_load(self, pid):
        raise pickle.UnpicklingError('BLOCKED_PERSISTENT_ID')

def sha256_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def finite_number(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(float(v))

def primitive_tree_status(root):
    """Iterative structural check after restricted decoding; never invokes custom methods."""
    stack=[root]; seen=0
    while stack:
        value=stack.pop(); seen+=1
        if isinstance(value,(str,bytes,int,float,bool,type(None))):
            continue
        if isinstance(value,dict):
            for k,v in value.items():
                if not isinstance(k,(str,int,float,bool,bytes,type(None))):
                    return False, seen, 'unsupported_dict_key:'+type(k).__name__
                stack.append(v)
            continue
        if isinstance(value,(list,tuple,set,frozenset)):
            stack.extend(value); continue
        return False, seen, 'unsupported_value:'+type(value).__name__
    return True, seen, None

def type_name(v):
    return type(v).__name__

def list_numeric_summary(values):
    if not isinstance(values,(list,tuple)):
        return {'is_sequence':False,'type':type_name(values),'length':None,'finite_count':0,'nan_count':0,'nonfinite_count':0,'non_numeric_count':0}
    finite=nan=nonfinite=nonnumeric=0
    for x in values:
        if isinstance(x,(int,float)) and not isinstance(x,bool):
            if math.isfinite(float(x)): finite+=1
            elif math.isnan(float(x)): nan+=1
            else: nonfinite+=1
        else: nonnumeric+=1
    return {'is_sequence':True,'type':type_name(values),'length':len(values),'finite_count':finite,'nan_count':nan,'nonfinite_count':nonfinite,'non_numeric_count':nonnumeric}

def run():
    started=datetime.now(timezone.utc).isoformat()
    run_id=datetime.now(timezone.utc).strftime('run_%Y%m%dT%H%M%S_%fZ')
    reports_root=ROOT/'reports/data_schema_audit'
    processed_root=ROOT/'data/processed/audit_only'
    reports_root.mkdir(parents=True,exist_ok=True); processed_root.mkdir(parents=True,exist_ok=True)
    report_dir=reports_root/run_id; processed_dir=processed_root/run_id
    report_dir.mkdir(exist_ok=False); processed_dir.mkdir(exist_ok=False)

    archive_sha=sha256_file(ARCHIVE); label_archive_sha=sha256_file(LABEL_ARCHIVE)
    if archive_sha != EXPECTED_ARCHIVE_SHA256: raise RuntimeError('HUST_ARCHIVE_SHA256_MISMATCH:'+archive_sha)
    if label_archive_sha != EXPECTED_LABEL_ARCHIVE_SHA256: raise RuntimeError('LABEL_ARCHIVE_SHA256_MISMATCH:'+label_archive_sha)
    static=json.loads(STATIC_AUDIT.read_text(encoding='utf-8'))
    static_members={x['member']:x for x in static['per_member']}
    if len(static_members)!=77 or not static.get('all_reached_STOP') or static.get('members_with_global_refs') or static.get('members_with_construction_opcodes'):
        raise RuntimeError('STATIC_OPCODE_AUDIT_PREREQUISITE_MISMATCH')
    with zipfile.ZipFile(LABEL_ARCHIVE) as z:
        labels=json.loads(z.read('Life labels/HUST_labels.json').decode('utf-8'))
    if len(labels)!=77: raise RuntimeError('UNEXPECTED_LABEL_COUNT:'+str(len(labels)))

    # 首次运行逐一核对 ZIP 成员与安全解压件字节并记录 SHA；后续可复用已生成清单，
    # 逐个在解码前校验内存字节，无需重扫 4 GB opcode 或重算全部哈希。
    sha_manifest_env=os.environ.get('AUDIT_SHA_MANIFEST')
    if sha_manifest_env:
        prior=json.loads(Path(sha_manifest_env).read_text(encoding='utf-8'))
        if prior.get('archive_sha256')!=archive_sha: raise RuntimeError('REUSED_SHA_MANIFEST_ARCHIVE_MISMATCH')
        hashes=prior.get('hashes',[])
        if len(hashes)!=77: raise RuntimeError('REUSED_SHA_MANIFEST_COUNT_MISMATCH')
        for h in hashes:
            rec=static_members.get(h.get('member'))
            if not rec or not rec.get('complete_to_STOP') or rec.get('global_references') or rec.get('construction_opcodes') or rec.get('uncompressed_bytes')!=h.get('archive_member_bytes'):
                raise RuntimeError('REUSED_SHA_MANIFEST_STATIC_MISMATCH:'+str(h.get('member')))
        sha_provenance={'reused_from':sha_manifest_env,'rehashed_all_files':False,'note':'Each extracted file is read into one-file memory and SHA-256 checked immediately before restricted decode.'}
    else:
        hashes=[]
        with zipfile.ZipFile(ARCHIVE) as z:
            members=sorted(x for x in z.namelist() if x.endswith('.pkl'))
            if len(members)!=77: raise RuntimeError('UNEXPECTED_PICKLE_COUNT:'+str(len(members)))
            for member in members:
                rec=static_members.get(member)
                if not rec or not rec.get('complete_to_STOP') or rec.get('global_references') or rec.get('construction_opcodes'):
                    raise RuntimeError('STATIC_MEMBER_NOT_CLEAN:'+member)
                extracted=EXTRACTED/Path(member).name
                hz=hashlib.sha256(); hf=hashlib.sha256(); zbytes=fbytes=0
                with z.open(member,'r') as fin:
                    for chunk in iter(lambda:fin.read(8*1024*1024),b''): hz.update(chunk); zbytes+=len(chunk)
                with open(extracted,'rb') as fin:
                    for chunk in iter(lambda:fin.read(8*1024*1024),b''): hf.update(chunk); fbytes+=len(chunk)
                zh,fh=hz.hexdigest(),hf.hexdigest()
                if zh!=fh or zbytes!=fbytes or zbytes!=rec['uncompressed_bytes']:
                    raise RuntimeError('ARCHIVE_EXTRACTED_OR_STATIC_SIZE_MISMATCH:'+member)
                hashes.append({'member':member,'file_name':Path(member).name,'archive_member_bytes':zbytes,'extracted_bytes':fbytes,'sha256':fh,'static_opcode_count':rec['ops_total'],'sha256_verified_before_decode':True})
        sha_provenance={'reused_from':None,'rehashed_all_files':True,'note':'Compared ZIP member SHA with extracted file SHA before decoding.'}
    hashes_path=report_dir/'hust_file_sha256.json'
    hashes_path.write_text(json.dumps({'archive_sha256':archive_sha,'sha_provenance':sha_provenance,'hashes':hashes},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

    cycle_csv_path=processed_dir/'hust_v9_cycle_diagnostics.csv'
    schema_path=report_dir/'per_cell_schema_audit.jsonl'
    error_path=report_dir/'decode_errors.jsonl'
    rows=0; cells=[]; errors=[]
    required_cycle_fields=['cycle_number','current_in_A','voltage_in_V','charge_capacity_in_Ah','discharge_capacity_in_Ah','time_in_s']
    optional_cycle_fields=['temperature_in_C','internal_resistance_in_ohm']
    with open(cycle_csv_path,'x',newline='',encoding='utf-8') as cf, open(schema_path,'x',encoding='utf-8') as sf, open(error_path,'x',encoding='utf-8') as ef:
        writer=csv.DictWriter(cf,fieldnames=['file_name','cell_id','cycle_index_1based','cycle_number','cycle_number_type','cycle_fields','missing_required_fields','curve_lengths_json','finite_stats_json','max_discharge_capacity_Ah','time_nonmonotonic_pairs','time_backward_pairs','time_duplicate_pairs','time_first_s','time_last_s','time_delta_min_s','time_delta_max_s','discharge_capacity_monotonic_violations','cycle_number_duplicate','cycle_number_nonmonotonic','cross_cycle_time_backward','v11_life_label_cycle','capacity_threshold_80pct_Ah','first_80pct_capacity_crossing_cycle','label_minus_first_crossing_cycles','label_crossing_match','diagnostic_note'])
        writer.writeheader()
        for idx,hashrec in enumerate(hashes,1):
            member=hashrec['member']; file_name=hashrec['file_name']; path=EXTRACTED/file_name
            try:
                payload=path.read_bytes()
                observed=hashlib.sha256(payload).hexdigest()
                if observed!=hashrec['sha256']: raise RuntimeError('SHA256_CHANGED_AFTER_HASH_PASS')
                obj=DenyAllUnpickler(io.BytesIO(payload)).load()
                is_primitive,primitive_nodes,primitive_issue=primitive_tree_status(obj)
                if not is_primitive:
                    raise RuntimeError('NON_PRIMITIVE_TREE:'+str(primitive_issue))
                if not isinstance(obj,dict): raise RuntimeError('TOP_LEVEL_NOT_DICT:'+type_name(obj))
                cycles=obj.get('cycle_data')
                if not isinstance(cycles,list): raise RuntimeError('CYCLE_DATA_NOT_LIST:'+type_name(cycles))
                cell_id=obj.get('cell_id')
                top_schema={k:{'type':type_name(v),'length':len(v) if isinstance(v,(str,bytes,list,tuple,dict)) else None} for k,v in obj.items()}
                cell_cycle_numbers=[]; cell_time_last=None; first_crossing=None; cycle_records=[]; missing_top=[]
                if not isinstance(cell_id,str): missing_top.append('cell_id:not_string')
                nominal=obj.get('nominal_capacity_in_Ah')
                soc=obj.get('SOC_interval')
                soc_fraction=None
                if isinstance(soc,(list,tuple)) and len(soc)==2 and all(finite_number(x) for x in soc): soc_fraction=float(soc[1])-float(soc[0])
                if not finite_number(nominal) or not finite_number(soc_fraction) or soc_fraction==0:
                    threshold=None
                else: threshold=0.8*float(nominal)*float(soc_fraction)
                v11_label=labels.get(file_name)
                for ci,cy in enumerate(cycles,1):
                    if not isinstance(cy,dict): raise RuntimeError('CYCLE_NOT_DICT:index=%d type=%s'%(ci,type_name(cy)))
                    missing=[k for k in required_cycle_fields if k not in cy]
                    curve_lengths={k:(len(cy[k]) if isinstance(cy.get(k),(list,tuple)) else None) for k in ['current_in_A','voltage_in_V','charge_capacity_in_Ah','discharge_capacity_in_Ah','time_in_s','temperature_in_C','internal_resistance_in_ohm']}
                    stats={k:list_numeric_summary(cy[k]) for k in required_cycle_fields[1:] if k in cy}
                    cn=cy.get('cycle_number'); cell_cycle_numbers.append(cn)
                    discharge=cy.get('discharge_capacity_in_Ah')
                    capvals=[float(v) for v in discharge if finite_number(v)] if isinstance(discharge,(list,tuple)) else []
                    max_cap=max(capvals) if capvals else None
                    if first_crossing is None and threshold is not None and max_cap is not None and max_cap<=threshold: first_crossing=ci
                    times=cy.get('time_in_s')
                    timevals=[float(v) for v in times if finite_number(v)] if isinstance(times,(list,tuple)) else []
                    nonmono=backward=duplicate=0; dmin=dmax=None
                    if isinstance(times,(list,tuple)) and len(times)>1:
                        diffs=[]
                        for a,b in zip(times,times[1:]):
                            if finite_number(a) and finite_number(b):
                                delta=float(b)-float(a); diffs.append(delta)
                                if delta<=0: nonmono+=1
                                if delta<0: backward+=1
                                if delta==0: duplicate+=1
                        if diffs: dmin=min(diffs); dmax=max(diffs)
                    cap_violations=0
                    if isinstance(discharge,(list,tuple)):
                        finite_dis=[float(v) for v in discharge if finite_number(v)]
                        cap_violations=sum(1 for a,b in zip(finite_dis,finite_dis[1:]) if b<a)
                    cn_duplicate=any(cn==prior for prior in cell_cycle_numbers[:-1]) if isinstance(cn,(int,float,str)) else False
                    numeric_cns=[x for x in cell_cycle_numbers if isinstance(x,(int,float)) and not isinstance(x,bool)]
                    cn_nonmono=len(numeric_cns)>1 and numeric_cns[-1]<=numeric_cns[-2]
                    first_time=timevals[0] if timevals else None; last_time=timevals[-1] if timevals else None
                    cross_backward=(cell_time_last is not None and first_time is not None and first_time<cell_time_last)
                    if last_time is not None: cell_time_last=last_time
                    record={'file_name':file_name,'cell_id':cell_id,'cycle_index_1based':ci,'cycle_number':cn,'cycle_number_type':type_name(cn),'cycle_fields':sorted(cy.keys()),'missing_required_fields':missing,'curve_lengths':curve_lengths,'finite_stats':stats,'max_discharge_capacity_Ah':max_cap,'time_nonmonotonic_pairs':nonmono,'time_backward_pairs':backward,'time_duplicate_pairs':duplicate,'time_first_s':first_time,'time_last_s':last_time,'time_delta_min_s':dmin,'time_delta_max_s':dmax,'discharge_capacity_monotonic_violations':cap_violations,'cycle_number_duplicate':cn_duplicate,'cycle_number_nonmonotonic':cn_nonmono,'cross_cycle_time_backward':cross_backward,'v11_life_label_cycle':v11_label,'capacity_threshold_80pct_Ah':threshold,'first_80pct_capacity_crossing_cycle':first_crossing,'label_minus_first_crossing_cycles':(int(v11_label)-first_crossing if isinstance(v11_label,int) and first_crossing is not None else None),'label_crossing_match':(v11_label==first_crossing if isinstance(v11_label,int) and first_crossing is not None else None),'diagnostic_note':'Diagnostic only. v9 processed HUST + v11 labels are cross-release; no automatic label acceptance or correction.'}
                    row=dict(record); row['curve_lengths_json']=json.dumps(row.pop('curve_lengths'),ensure_ascii=False,separators=(',',':')); row['finite_stats_json']=json.dumps(row.pop('finite_stats'),ensure_ascii=False,separators=(',',':')); writer.writerow({k:(json.dumps(v,ensure_ascii=False,separators=(',',':')) if isinstance(v,(dict,list)) else v) for k,v in row.items()})
                    cycle_records.append(record); rows+=1
                schema={'file_name':file_name,'cell_id':cell_id,'sha256':hashrec['sha256'],'archive_member_bytes':hashrec['archive_member_bytes'],'restricted_decode':'PASS','custom_unpickler':'find_class raises for all globals; persistent_load raises for all IDs','primitive_tree_only':is_primitive,'primitive_node_count':primitive_nodes,'top_level_type':'dict','top_level_fields':top_schema,'cycle_data_type':'list','cycle_count':len(cycles),'first_cycle_fields':cycle_records[0]['cycle_fields'] if cycle_records else [],'cycle_field_union':sorted({k for r in cycle_records for k in r['cycle_fields']}),'missing_required_top_fields':missing_top,'nominal_capacity_in_Ah':nominal if finite_number(nominal) else None,'SOC_interval':soc if isinstance(soc,(list,tuple)) else None,'capacity_threshold_80pct_Ah':threshold,'first_80pct_capacity_crossing_cycle':first_crossing,'v11_life_label_cycle':v11_label,'label_minus_first_crossing_cycles':(int(v11_label)-first_crossing if isinstance(v11_label,int) and first_crossing is not None else None),'label_crossing_match':(v11_label==first_crossing if isinstance(v11_label,int) and first_crossing is not None else None),'diagnostic_note':'Diagnostic only; cross-release labels cannot be auto-accepted or rewritten.'}
                sf.write(json.dumps(schema,ensure_ascii=False)+'\n'); sf.flush(); cf.flush()
                cells.append({'file_name':file_name,'cell_id':cell_id,'cycle_count':len(cycles),'first_80pct_capacity_crossing_cycle':first_crossing,'v11_life_label_cycle':v11_label,'label_crossing_match':schema['label_crossing_match'],'restricted_decode':'PASS'})
                del obj,payload,cycles,cycle_records
            except Exception as exc:
                e={'file_name':file_name,'sha256':hashrec['sha256'],'restricted_decode':'STOPPED','error_type':type(exc).__name__,'error':str(exc),'policy':'do not widen class/global allowlist'}
                ef.write(json.dumps(e,ensure_ascii=False)+'\n'); ef.flush(); errors.append(e)
                if 'payload' in locals(): del payload
                if 'obj' in locals(): del obj

    summary={'created_at_utc':started,'run_id':run_id,'mode':'restricted non-training schema/data diagnostics','battery_life_commit':BATTERYLIFE_COMMIT,'official_hust_archive_sha256':archive_sha,'official_labels_archive_sha256':label_archive_sha,'labels_record':'Zenodo v11 record '+LABEL_RECORD,'dataset_release':'BatteryLife v9 HUST with cross-release BatteryLife v11 labels; not same-version reproduction','pickle_load_called':False,'custom_unpickler_policy':'find_class always raises; persistent_load always raises; no global allowlist','static_audit':'77/77 complete through STOP; zero GLOBAL/STACK_GLOBAL and zero object-construction opcodes','per_file_hashes_path':str(hashes_path),'per_cell_schema_path':str(schema_path),'per_cycle_csv_path':str(cycle_csv_path),'decode_errors_path':str(error_path),'cells_decoded':len(cells),'cells_stopped':len(errors),'cycle_rows_written':rows,'cells':cells,'errors':errors,'fit_or_optimizer_steps':0,'training_data_exported':False,'labels_interpretation':'first per-cycle max discharge capacity crossing at <= 0.8*nominal_capacity*SOC_interval, matching the threshold form used in pinned Extract_life_labels.py; diagnostic comparison only'}
    (report_dir/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report_lines=['# HUST 安全解码与数据结构审计','',f'- Run: `{run_id}`',f'- BatteryLife commit: `{BATTERYLIFE_COMMIT}`',f'- 数据：BatteryLife v9 HUST；标签：BatteryLife v11（跨版本，仅诊断）',f'- 校验：官方 HUST archive SHA-256 `{archive_sha}`；标签 archive SHA-256 `{label_archive_sha}`',f'- 受限解码：自定义 Unpickler 的 `find_class` 与 `persistent_load` 全部拒绝；未启用 globals 白名单。',f'- 完成：{len(cells)}/77 cells；停止：{len(errors)}；cycle rows={rows}。', '- 标签比较定义：每循环 `max(discharge_capacity_in_Ah)` 第一次小于等于 `0.8 * nominal_capacity_in_Ah * SOC_interval宽度` 的 cycle index，与 v11 文件标签逐一比较；按官方 `Extract_life_labels.py` 的字段与阈值形式；只作诊断，不重标、不自动匹配。', '- 训练集：未生成；拟合与 optimizer steps：0。', '', '每电芯字段、数组长度、有限值、容量阈值穿越和标签差异见 `per_cell_schema_audit.jsonl`；每循环曲线长度、有限值、时间单调性、容量单调性及 cycle_number 检查见 `data/processed/audit_only` 下 CSV。']
    (report_dir/'report_zh.md').write_text('\n'.join(report_lines)+'\n',encoding='utf-8')
    # 完成凭据：校验 manifest 输出路径和实际脚本/审计文件 SHA-256。
    file_hashes={}
    for p in [Path(__file__),hashes_path,schema_path,cycle_csv_path,report_dir/'summary.json',report_dir/'report_zh.md']:
        file_hashes[str(p)]=sha256_file(p)
    (report_dir/'artifact_sha256.json').write_text(json.dumps(file_hashes,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'run_id':run_id,'summary':str(report_dir/'summary.json'),'report':str(report_dir/'report_zh.md'),'cells_decoded':len(cells),'cells_stopped':len(errors),'cycle_rows':rows,'hashes':file_hashes,'errors':errors},ensure_ascii=False,indent=2))

if __name__=='__main__': run()
