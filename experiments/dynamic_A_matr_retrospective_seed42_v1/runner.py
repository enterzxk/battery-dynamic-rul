"""MATR已存文本轨道的信息增量诊断；不是strict在线资格证明。"""
from pathlib import Path
import csv,datetime,hashlib,json,os,time
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
ROOT=Path('/home/yndx/zxk/rul')
OUT=ROOT/'experiments/dynamic_A_matr_retrospective_seed42_v1'
INPUT=ROOT/'reports/dynamic_A_eligible_20261017_root/candidate_features.csv'
PROTOCOL=ROOT/'reports/dynamic_A_eligible_20261017_root/protocol_candidate.json'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,obj):
    with (OUT/name).open('x') as f:json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n')

def main():
    go=json.loads((OUT/'ROOT_GO.json').read_text())
    if not (go.get('status')=='GO_RETROSPECTIVE_PROCESSED_RECORD_DIAGNOSTIC_ONLY' and
        go.get('runner_sha256')==sha(Path(__file__)) and go.get('input_sha256')==sha(INPUT) and
        go.get('protocol_sha256')==sha(PROTOCOL) and go.get('strict_online_claim') is False and go.get('test_access') is False):
        raise RuntimeError('Missing exact narrow diagnostic GO')
    # 一次性claim必须先于模型fit；失败保留原记录，不覆盖重跑。
    with (OUT/'invocation.claim').open('x') as f:
        f.write(json.dumps({'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'go_sha256':sha(OUT/'ROOT_GO.json')}));f.flush();os.fsync(f.fileno())
    started=time.monotonic();fits=0
    try:
        import numpy as np
        from sklearn.linear_model import Ridge
        from sklearn.preprocessing import StandardScaler
        from sklearn.model_selection import GroupKFold
        from sklearn.ensemble import HistGradientBoostingRegressor
        rows=list(csv.DictReader(INPUT.open()))
        if any(x['split'] not in ['train','val'] for x in rows):raise ValueError('test role forbidden')
        if any(float(x['author_EOL'])<float(x['k']) for x in rows):raise ValueError('author label contradicts observed risk set; STOP')
        train=[x for x in rows if x['split']=='train'];val=[x for x in rows if x['split']=='val']
        assert not ({x['cell_id'] for x in train}&{x['cell_id'] for x in val})
        a1=['age','soh','cumulative_discharge_Ah','batch2','batch3','batch4']
        a2=a1+['capacity_slope_last20_Ah_per_cycle']
        preds=[];selections={}
        def fitmodel(model,X,y,w):
            nonlocal fits
            if fits>=41:raise RuntimeError('predictive_fit_budget')
            fits+=1
            with (OUT/'fit_ledger.jsonl').open('a') as f:
                f.write(json.dumps({'event':'fit_started','fit_number':fits,'model':type(model).__name__})+'\n');f.flush();os.fsync(f.fileno())
            model.fit(X,y,sample_weight=w)
            with (OUT/'fit_ledger.jsonl').open('a') as f:f.write(json.dumps({'event':'fit_completed','fit_number':fits})+'\n')
            return model
        def weights(rr):
            counts={c:sum(x['cell_id']==c for x in rr) for c in {x['cell_id'] for x in rr}}
            return np.array([1/counts[x['cell_id']] for x in rr])
        def macro(rr,values):
            return float(np.mean([np.mean([values[i] for i,x in enumerate(rr) if x['cell_id']==c]) for c in sorted({x['cell_id'] for x in rr})]))
        def ridge_arm(name,cols,tt,vv):
            X=np.array([[float(x[c]) for c in cols] for x in tt]);Y=np.array([float(x['author_EOL']) for x in tt])
            V=np.array([[float(x[c]) for c in cols] for x in vv]);groups=np.array([x['cell_id'] for x in tt]);w=weights(tt)
            scores={}
            for alpha in [.1,1.,10.,100.]:
                errors=[]
                for ti,vi in GroupKFold(3).split(X,Y,groups):
                    tr=[tt[i] for i in ti];vr=[tt[i] for i in vi];sc=StandardScaler().fit(X[ti],sample_weight=weights(tr))
                    m=fitmodel(Ridge(alpha=alpha),sc.transform(X[ti]),Y[ti],weights(tr))
                    pred=np.maximum(0,m.predict(sc.transform(X[vi]))-np.array([float(x['k']) for x in vr]))
                    errors.append(macro(vr,np.abs(pred-(Y[vi]-np.array([float(x['k']) for x in vr])))))
                scores[str(alpha)]=float(np.mean(errors))
            best=min([.1,1.,10.,100.],key=lambda a:(scores[str(a)],a))
            sc=StandardScaler().fit(X,sample_weight=w);m=fitmodel(Ridge(alpha=best),sc.transform(X),Y,w)
            selections[name]={'alpha':best,'train_only_group_cv_MAE_cycles':scores,'features':cols}
            return m.predict(sc.transform(V))
        t0=[x for x in train if int(x['k'])==50];v0=[x for x in val if int(x['k'])==50]
        e0=dict(zip([x['cell_id'] for x in v0],ridge_arm('A0',a1,t0,v0)))
        e1=ridge_arm('A1',a1,train,val);e2=ridge_arm('A2',a2,train,val)
        arrays={'A0':np.array([e0[x['cell_id']] for x in val]),'A1':e1,'A2':e2}
        def score_arrays():
            result={}
            for name,est in arrays.items():
                for lane in ['author_EOL_all_validation','observed_crossing_validation_only']:
                    ids=[i for i,x in enumerate(val) if lane.startswith('author') or x['event_status']=='observed']
                    rr=[val[i] for i in ids];targets=np.array([float(x['author_EOL'] if lane.startswith('author') else x['observed_EOL'])-float(x['k']) for x in rr])
                    pp=np.maximum(0,est[ids]-np.array([float(x['k']) for x in rr]));err=pp-targets
                    result[name+'|'+lane]={'cell_macro_Time_MAE_cycles':macro(rr,np.abs(err)),'cell_macro_signed_bias_cycles':macro(rr,err),
                        'cells':len({x['cell_id'] for x in rr}),'origins':len(rr)}
            return result
        ridge_scores=score_arrays()
        gain=1-ridge_scores['A2|author_EOL_all_validation']['cell_macro_Time_MAE_cycles']/ridge_scores['A1|author_EOL_all_validation']['cell_macro_Time_MAE_cycles']
        if gain<.05:
            # 仅用于排查线性模型未利用信息；固定参数，不以验证集调参。
            for name,cols in [('GBDT_A1',a1),('GBDT_A2',a2)]:
                X=np.array([[float(x[c]) for c in cols] for x in train]);V=np.array([[float(x[c]) for c in cols] for x in val])
                m=fitmodel(HistGradientBoostingRegressor(max_iter=100,max_leaf_nodes=7,max_depth=3,l2_regularization=1,early_stopping=False,random_state=42),X,np.array([float(x['author_EOL']) for x in train]),weights(train))
                arrays[name]=m.predict(V);selections[name]={'features':cols,'fixed_hyperparameters':True}
        scores=score_arrays()
        for name,est in arrays.items():
            for i,x in enumerate(val):
                pp=max(0,float(est[i])-float(x['k']))
                preds.append({'model':name,'cell_id':x['cell_id'],'split':'validation','k':int(x['k']),'predicted_EOL':float(est[i]),'predicted_RUL':pp,
                    'author_EOL':float(x['author_EOL']),'observed_EOL':x['observed_EOL'],'event_status':x['event_status'],
                    'author_RUL':float(x['author_EOL'])-float(x['k']),'signed_error_author_cycles':pp-(float(x['author_EOL'])-float(x['k']))})
        with (OUT/'validation_predictions.csv').open('x',newline='') as f:
            wcsv=csv.DictWriter(f,fieldnames=list(preds[0]));wcsv.writeheader();wcsv.writerows(preds)
        deltas=[]
        for c in sorted({x['cell_id'] for x in val}):
            mm={name:float(np.mean([abs(p['signed_error_author_cycles']) for p in preds if p['cell_id']==c and p['model']==name])) for name in arrays}
            deltas.append({'cell_id':c,'A1_MAE':mm['A1'],'A2_MAE':mm['A2'],'A1_minus_A2_improvement':mm['A1']-mm['A2'],'all_model_MAE':mm})
        write('per_cell_paired_deltas.json',deltas)
        write('selection.json',selections)
        receipt={'status':'COMPLETE_RETROSPECTIVE_PROCESSED_RECORD_DIAGNOSTIC','scores':scores,'seed':42,'new_predictive_fits':fits,'optimizer_steps':0,
            'ridge_relative_Time_MAE_reduction':gain,'ridge_improved_validation_cells':sum(x['A1_minus_A2_improvement']>0 for x in deltas),
            'validation_cells':len(deltas),'elapsed_seconds':time.monotonic()-started,'test_access':False,'strict_online_claim':False,
            'physical_identity_and_generator_limits':'Known aliases split safe; other serial identity and actual v11 generator unverified',
            'input_permission':'complete-cycle measured capacity; no deployable I/V-only claim','training_labels':'author total EOL including extrapolated; observed subset scored separately',
            'code_sha256':sha(Path(__file__)),'input_sha256':sha(INPUT),'protocol_sha256':sha(PROTOCOL),'predictions_sha256':sha(OUT/'validation_predictions.csv')}
        write('completion_receipt.json',receipt);print(json.dumps(receipt,ensure_ascii=False))
    except BaseException as e:
        write('failure_receipt.json',{'status':'FAILED_STOP','error_type':type(e).__name__,'error':str(e),'predictive_fit_attempts':fits,'optimizer_steps':0,'elapsed_seconds':time.monotonic()-started})
        raise

if __name__=='__main__':main()
