"""Text/AST/stat-only official CALB gap inventory. No archive reads or data/model execution."""
from pathlib import Path
import ast,json,hashlib,datetime,shutil
R=Path('/home/yndx/zxk/rul');P=R/'repos/pinned/BatteryLife_3b17bb53202e10711deae0448c91f84144bb3dd9';O=R/'reports/p1_calb_reproduction_gap_20261018_root'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
sources=[P/'train_eval_scripts/CPMLP.sh',P/'data_provider/data_split_recorder.py',P/'data_provider/data_loader.py',P/'run_main.py',P/'README.md',R/'data/source_audit/zenodo_19688272.json',R/'data/source_audit/data_source_manifest.json']
split={}
tree=ast.parse((P/'data_provider/data_split_recorder.py').read_text())
for n in ast.walk(tree):
 if isinstance(n,ast.Assign):
  for target in n.targets:
   if isinstance(target,ast.Name) and target.id in ['CALB_train_files','CALB_val_files','CALB_test_files']:
    v=ast.literal_eval(n.value);assert isinstance(v,list) and all(isinstance(x,str) for x in v)
    split[target.id]=dict(count=len(v),unique_count=len(set(v)),line=n.lineno,file_names=v)
assert [split[k]['count'] for k in ['CALB_train_files','CALB_val_files','CALB_test_files']]==[17,5,5]
overlaps={a+'__'+b:sorted(set(split[a]['file_names'])&set(split[b]['file_names'])) for a in split for b in split if a<b};assert not any(overlaps.values())
api=json.loads((R/'data/source_audit/zenodo_19688272.json').read_text())
entry=next(x for x in api['files'] if x['key']=='CALB.zip')
assert entry['size']==12671967 and entry['checksum']=='md5:2b1006e96e0ca42765a732060f964687'
existing=[str(p.relative_to(R)) for p in (R/'data').rglob('*CALB*')]
assert not existing
label_archive=R/'data/raw/HUST/Life_labels_v11.zip'
stats={}
for rel in ['data/raw/CALB','data/source_audit/stage_v11_hust_v11_labels/CALB','data/source_audit/stage_v11_hust_v11_labels/Life labels/CALB_labels.json','data/raw/HUST/Life_labels_v11.zip']:
 p=R/rel;stats[rel]=dict(exists=p.exists(),bytes=p.stat().st_size if p.is_file() else None)
assert label_archive.is_file() and label_archive.stat().st_size==12586
script=(P/'train_eval_scripts/CPMLP.sh').read_text().splitlines()
args={}
for l in script:
 if '=' in l and not l.lstrip().startswith('#'):
  key,value=l.split('=',1)
  if key in ['model_name','dataset','train_epochs','early_cycle_threshold','learning_rate','num_process','batch_size','seed','seq_len','charge_discharge_length','patience','lradj']:args[key]=value.split('#')[0].strip()
assert args['dataset']=='CALB' and args['seed']=='2021' and args['num_process']=='2'
loader=(P/'data_provider/data_loader.py').read_text().splitlines();run=(P/'run_main.py').read_text().splitlines()
assert "CALB/{file_name}" in loader[412] and "Life labels/{prefix}_labels.json" in loader[424]
assert "data_provider_func(args, 'test'" in run[210] and 'vali_baseline' in run[369] and 'test_data, test_loader' in run[369]
source_base='https://github.com/Ruifeng-Tan/BatteryLife/blob/3b17bb53202e10711deae0448c91f84144bb3dd9/'
res=dict(status='STOP_CALB_PROCESSED_DATA_AND_LABEL_STAGE_MISSING',at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),scope='Pinned official source and existing project text/stat only; no archive/data decode, test sample reads, model/inference/fit',official_recipe=args,official_split=split,filename_pairwise_overlaps=overlaps,physical_identity_verified=False,existing_CALB_paths_in_project_data=existing,path_stats=stats,saved_v11_archive_metadata=entry,metadata_freshness='Saved official API snapshot only; no live endpoint verification this round',existing_labels_archive_reusable_candidate=dict(path=str(label_archive),bytes=12586,archive_contents_not_rechecked=True),first_blocker='CALB processed archive not acquired/staged in project data; CALB_labels.json not staged. Existing Life_labels_v11.zip may supply labels but its relevant member/coverage has not been opened in this action.',additional_execution_constraints=['new_fits_allowed=false; consumed HUST/PBT budgets not reusable','Official script requests seed2021,2 GPU processes x16 batch,100epochs,constant5e-5; actual two-process CALB runtime readiness not verified','Pinned run_main.py constructs test_data/test_loader at line211 and calls test evaluation at line370; direct official entry conflicts with current test lock','Filename disjointness is not verified physical-cell independence; no data/label/asof audit for CALB yet'],source_claims=[dict(claim='Official CPMLP defaults CALB/seed2021/two processes',url=source_base+'train_eval_scripts/CPMLP.sh#L2-L31',local_lines='CPMLP.sh:2-31'),dict(claim='CALB fixed filename splits17/5/5',url=source_base+'data_provider/data_split_recorder.py#L59-L61',local_lines='data_split_recorder.py:59-61'),dict(claim='Loader requires CALB files and CALB_labels.json',url=source_base+'data_provider/data_loader.py#L374-L425',local_lines='data_loader.py:379,412-413,425'),dict(claim='Official test loader and evaluation',url=source_base+'run_main.py#L210-L211',second_url=source_base+'run_main.py#L369-L371',local_lines='run_main.py:211,370'),dict(claim='Pinned README processed-data source',url=source_base+'README.md#L38-L39',local_lines='README.md:38-39')],next_action='One bounded acquisition of saved-v11 CALB.zip candidate to independent project directory, after live public metadata/header/checksum confirmation and current transfer-budget accounting; preserve receipt. Reuse existing label archive; inspect member names/CRC and exact17train+5val filename coverage under fixed bound, with test contents locked. No unpickle/model/fit.',new_fits=0,optimizer_steps=0,new_inference=0,model_loads=0,archive_reads=0,test_access=False,bindings={str(p.relative_to(R)):sha(p) for p in sources+[Path(__file__)]})
with (O/'gap_inventory.json').open('x',encoding='utf-8') as f:json.dump(res,f,ensure_ascii=False,indent=2);f.write('\n')
md=['# P1：官方CPMLP CALB忠实复现的首个缺口','','结论：STOP_CALB_PROCESSED_DATA_AND_LABEL_STAGE_MISSING。代码与脚本存在，但项目data树没有CALB路径，两个现有HUST stage未含CALB或CALB_labels.json；不能进入模型/训练。此结论只描述已检查项目路径，不声称服务器其他项目不存在数据。','',
'官方固定commit：3b17bb53202e10711deae0448c91f84144bb3dd9。CPMLP.sh第2–31行：CALB、seed2021、100epochs、首100cycle、LR5e-5 constant、2进程×batch16。HUST/seed42/singleGPU配方适配不等于此入口的忠实复现。','',
'data_split_recorder.py第59–61行静态列表：17 train / 5 validation / 5 test；各列表内部唯一且两两无交集。这只证明文件名隔离，物理电池身份仍unverified，未读取任何test样本或标签。','',
'data_loader.py第379、412–413、425行要求root/CALB/*.pkl与root/Life labels/CALB_labels.json。当前未获得/展开CALB。已保存v11 API JSON列CALB.zip大小12,671,967 bytes，MD5 2b1006e96e0ca42765a732060f964687，URL '+entry['links']['self']+'。这是现有官方元数据快照，本轮未在线复核，不把旧快照当当前网络可用性。','',
'标签压缩包data/raw/HUST/Life_labels_v11.zip已存在，stat=12,586 bytes；不重复下载。当前未打开该压缩包，不推断CALB成员、标签覆盖或版本语义已通过。','',
'另一个执行门：run_main.py第211行构造test数据，第370行每epoch评估test。当前test锁定，不能直接执行官方入口；未来若仅做train/val适配，须如实报告偏离。官方双进程runtime本轮未检查，不能把单GPU HUST成功当双GPU忠实复现成功。','',
'最小验证：AST literal_eval只解析三个CALB静态拆分列表；核脚本关键参数/loader路径/test调用具体行，定向stat项目data与已有stage。没有解压、pickle/torch.load、数据读取、模型构造、训练或test访问。new_fits=0、optimizer_steps=0。源SHA和URL/行号见gap_inventory.json。','',
'下一条具体行动：先实时核公开v11 CALB元数据/响应头与当前传输预算，单次有界获取约12.7MB CALB.zip到独立目录并核官方checksum；复用已有标签包，只核归档成员名/CRC及固定17train+5val的覆盖，不打开test内容。数据/标签/asof合法性仍须后续最小检查，不能因获取成功自动训练。']
with (O/'GAP_REVIEW_ZH.md').open('x',encoding='utf-8') as f:f.write('\n'.join(md)+'\n')
print(json.dumps({k:v for k,v in res.items() if k in ['status','official_recipe','existing_CALB_paths_in_project_data','path_stats','first_blocker','new_fits','optimizer_steps','archive_reads','test_access']},ensure_ascii=True))
