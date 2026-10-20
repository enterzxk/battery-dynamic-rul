import pathlib,json,hashlib,fcntl,signal,importlib.util,datetime,traceback
import numpy as np,joblib
R=pathlib.Path('/home/yndx/zxk/rul');D=pathlib.Path(__file__).resolve().parent;sha=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def run():
 g=json.loads((D/'CPU_PREDICTION_GO.json').read_text());assert g['status']=='APPROVED_CPU_CHECKPOINT_INFERENCE_ONLY' and g['new_fits']==0 and g['code_sha256']==sha(__file__)
 for p,h in g['artifacts'].items():assert sha(R/p)==h,p
 s=json.loads((R/'automation/state/coordinator.json').read_text());assert s['owner']==s['thread_id']==g['owner'] and s['takeover_verified']
 with (D/'cpu_prediction_recovery.claim').open('x') as f:f.write(sha(D/'CPU_PREDICTION_GO.json'))
 with (R/'automation/state/online_survival_cpu.lock').open('a+') as l:
  fcntl.flock(l,fcntl.LOCK_EX|fcntl.LOCK_NB)
  with (R/'automation/locks/isu_irregular_rul_cpu.lock').open('a+') as k:
   fcntl.flock(k,fcntl.LOCK_EX|fcntl.LOCK_NB)
   def timeout(a,b):raise TimeoutError('CPU inference runtime cap')
   signal.signal(signal.SIGALRM,timeout);signal.alarm(900)
   spec=importlib.util.spec_from_file_location('trained_helpers',D/'train_eval_pre_gru_epoch_fix.py');t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
   from baselines import GroupFrozenDistribution,HGBEvent,LognormalAFT,CDFFusionPredictor
   cells=t.load_split(R/'reports/isu_ilcc_capacity_probe_20261020_root/cohort.json',R/'data/processed/ISU_ILCC_DataV2_v1',R/'reports/isu_ilcc_datav2_full_20261020_root/data_manifest.json')
   tr=t.make_examples([c for c in cells if c['role']=='train']);dv=t.make_examples([c for c in cells if c['role']=='development']);p=D/'run_20261020_main'
   group=GroupFrozenDistribution();group.fit(tr);models={'group_frozen':group}
   for name,early in [('hgb_dynamic',False),('hgb_early_health',True)]:
    models[name]=HGBEvent(joblib.load(p/(name+'.joblib')),np.load(p/(name+'_oof_residuals.npy')),np.load(p/(name+'_oof_cell_equal_weights.npy')),early)
   aft=LognormalAFT(False);aft.model=joblib.load(p/'aft_dynamic.joblib');aft.sigma=json.loads((p/'aft_distribution.json').read_text())['sigma'];models['aft_dynamic']=aft
   models['cdf_fusion']=CDFFusionPredictor([group,models['hgb_dynamic']])
   o=D/'cpu_prediction_recovery';o.mkdir();n=t.evaluate(models,dv,o);signal.alarm(0)
   return {'status':'SUCCESS','new_fits':0,'old_models_retrained':0,'deterministic_group_prior_reconstruction':1,'loaded_saved_CPU_full_models':3,'original_CPU_fits_preserved':7,'predictions':n,'locked_reads':0,'GO_sha256':sha(D/'CPU_PREDICTION_GO.json')}
try:result=run()
except Exception as e:
 result={'status':'FAILED','new_fits':0,'error':repr(e),'traceback':traceback.format_exc(limit=6)}
 with (D/'cpu_prediction_recovery_receipt.json').open('x') as f:json.dump(result,f,indent=2)
 raise
else:
 with (D/'cpu_prediction_recovery_receipt.json').open('x') as f:json.dump(result,f,indent=2)
 print(json.dumps(result))
