#!/usr/bin/env python3
# 仅做官方模型导入与张量shape/zero-mask预检；不读取真实PKL、不fit、不创建optimizer。
import json, sys
from pathlib import Path
from types import SimpleNamespace
import torch
ROOT=Path("/home/yndx/zxk/rul")
CODE=ROOT/"repos/pinned/BatteryLife_3b17bb53202e10711deae0448c91f84144bb3dd9"
sys.path.insert(0,str(CODE))
torch.set_num_threads(2)
from models.CPMLP import Model as CPMLP
from models.CPTransformer import Model as CPTransformer
from data_provider.data_loader import Dataset_original, my_collate_fn_baseline
cfg=SimpleNamespace(d_ff=256,d_model=128,charge_discharge_length=300,early_cycle_threshold=100,dropout=0.0,e_layers=4,d_layers=2,n_heads=8,factor=3,activation="gelu",output_num=1)
x=torch.ones(2,100,300,3)
mask=torch.zeros(2,100); mask[0,:10]=1; mask[1,:100]=1
samples=[{"cycle_curve_data":x[i],"curve_attn_mask":mask[i],"labels":1200.,"life_class":1,"scaled_life_class":0,"weight":1.,"dataset_id":2,"seen_unseen_id":1} for i in range(2)]
batch=my_collate_fn_baseline(samples)
if tuple(batch[0].shape)!=(2,100,300,3) or tuple(batch[1].shape)!=(2,100): raise RuntimeError("collate shape mismatch")
if float(batch[0][0,10:].abs().sum())!=0.: raise RuntimeError("zero mask failed")
results={}
for name,cls in [("CPMLP",CPMLP),("CPTransformer",CPTransformer)]:
 model=cls(cfg).eval()
 with torch.no_grad(): pred=model(batch[0],batch[1])
 if tuple(pred.shape)!=(2,1): raise RuntimeError(name+" output shape mismatch")
 results[name]={"input_shape":list(batch[0].shape),"mask_shape":list(batch[1].shape),"output_shape":list(pred.shape),"finite":bool(torch.isfinite(pred).all())}
 del model,pred
out={"status":"PASS","torch":torch.__version__,"device":"CPU","threads":torch.get_num_threads(),"uses_real_data":False,"data_loader_instantiated":False,"custom_collate_zero_mask_verified":True,"optimizer_created":False,"backward_called":False,"training":False,"results":results}
p=ROOT/"reports/data_same_version_staging/model_shape_preflight.json"
p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(out,ensure_ascii=False,indent=2))
print("REPORT="+str(p))
