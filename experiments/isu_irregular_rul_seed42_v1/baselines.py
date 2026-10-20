"""Causal features and distribution-valued baselines for source-observed RPT event time."""
from __future__ import annotations
import math
import numpy as np
from scipy.special import ndtr, ndtri
GROUPS=64
def group_index(x):
 g=str(x["group_id"])
 return min(GROUPS-1,max(0,int(g[1:])-1)) if g.startswith("G") and g[1:].isdigit() else 0
def features(x,use_group=True,group_only=False):
 rs=x["visible_records"]; first=rs[0]; a,b=rs[-2:]
 gap=max(0.,(x["origin_stop_epoch"]-b["stop_epoch"])/604800.)
 dt=max((b["stop_epoch"]-a["stop_epoch"])/604800.,1e-6)
 slope=(b["capacityAh"]-a["capacityAh"])/dt
 win=rs[-5:]; t=np.asarray([r["calendar_age_weeks"] for r in win],float)
 y=np.asarray([r["capacityAh"]/x["nominal_capacity_ah"] for r in win],float)
 pair=[(y[j]-y[i])/(t[j]-t[i]) for i in range(len(t)) for j in range(i+1,len(t)) if t[j]>t[i]]
 ts_slope=float(np.median(pair)) if pair else 0.
 intercept=float(np.median(y-ts_slope*(t-t[-1]))) if len(t) else 0.
 last_residual=float(y[-1]-intercept) if len(t) else 0.
 v=[x["origin_age_weeks"],b["capacityAh"]/x["nominal_capacity_ah"],dt,slope,len(rs),
    b["calendar_age_weeks"],gap,first["capacityAh"]/x["nominal_capacity_ah"],ts_slope,last_residual]
 if group_only:v=[]
 if use_group:v += [float(i==group_index(x)) for i in range(GROUPS)]
 return np.asarray(v,float)
def early_features(x):
 a,b=x["visible_records"][:2]; dt=max((b["stop_epoch"]-a["stop_epoch"])/604800.,1e-6)
 return np.asarray([a["capacityAh"]/x["nominal_capacity_ah"],b["capacityAh"]/x["nominal_capacity_ah"],(b["capacityAh"]-a["capacityAh"])/dt,dt]+[float(i==group_index(x)) for i in range(GROUPS)],float)
def event_time_target(x): return float(x["event_rul_from_anchor"])
class EmpiricalRUL:
 def __init__(self,v,w=None):
  order=np.argsort(np.asarray(v,float)); self.v=np.asarray(v,float)[order]
  self.w=np.ones(len(self.v),float)/len(self.v) if w is None else np.asarray(w,float)[order]
  self.w=self.w/self.w.sum(); self.cum=np.cumsum(self.w); self.cum[-1]=1.0
 def cdf(self,x):
  a=np.asarray(x,float); ix=np.maximum(0,np.searchsorted(self.v,a,side="right")-1)
  return np.where(a<0,0.,np.where(a<self.v[0],0.,self.cum[ix]))
 def mean(self): return float(np.sum(self.v*self.w))
 def quantile(self,p): return float(self.v[min(len(self.v)-1,int(np.searchsorted(self.cum,p,side="left")))])
class EmpiricalEvent:
 def __init__(self,v,w=None): self.v=np.asarray(v,float); self.w=w
 def shifted(self,e): return EmpiricalRUL(np.maximum(0.,self.v-float(e)),self.w)
class LognormalEvent:
 def __init__(self,mu,sigma): self.mu=float(mu); self.s=max(float(sigma),1e-5)
 def shifted(self,e): return ShiftedLognormal(self.mu,self.s,float(e))
class ShiftedLognormal:
 def __init__(self,mu,s,e): self.mu=mu;self.s=s;self.e=max(0.,e)
 def _cdf(self,x):
  a=np.asarray(x,float); z=np.zeros_like(a); m=a>0; z[m]=ndtr((np.log(a[m])-self.mu)/self.s);return z
 def cdf(self,x):
  a=np.asarray(x,float)
  if np.any(a<0): raise ValueError("negative CDF query")
  return self._cdf(a+self.e)
 def quantile(self,p):
  if float(self._cdf(np.asarray([self.e]))[0])>=p:return 0.
  return max(0.,math.exp(self.mu+self.s*float(ndtri(p)))-self.e)
 def mean(self):
  if self.e==0:return math.exp(self.mu+.5*self.s**2)
  z=(math.log(self.e)-self.mu)/self.s; z2=(math.log(self.e)-self.mu-self.s**2)/self.s
  return max(0.,math.exp(self.mu+.5*self.s**2)*(1-float(ndtr(z2)))-self.e*(1-float(ndtr(z))))
class Mixture:
 def __init__(self,parts):self.parts=parts
 def cdf(self,x):return sum(p.cdf(x) for p in self.parts)/len(self.parts)
 def mean(self):return sum(p.mean() for p in self.parts)/len(self.parts)
 def quantile(self,p):
  if self.cdf(0.)>=p:return 0.
  lo,hi=0.,1.
  while self.cdf(hi)<p:hi*=2.
  for _ in range(80):
   m=(lo+hi)/2
   if self.cdf(m)<p:lo=m
   else:hi=m
  return hi
class GroupFrozenDistribution:
 def fit(self,xs):
  self.groups={};self.all=[];seen=set()
  for x in xs:
   if x["cell_id"] in seen:continue
   y=event_time_target(x);self.groups.setdefault(x["group_id"],[]).append(y);self.all.append(y);seen.add(x["cell_id"])
  if not self.all:raise ValueError("empty group prior")
 def predict(self,x):return EmpiricalEvent(self.groups.get(x["group_id"],self.all)).shifted(x["origin_age_weeks"]-x["anchor_age_weeks"])
class HGBEvent:
 def __init__(self,model,residuals,residual_weights=None,early=False):
  self.model=model;self.r=np.asarray(residuals);self.w=residual_weights;self.early=early
 def predict(self,x):
  mu=float(self.model.predict((early_features(x) if self.early else features(x))[None,:])[0])
  return EmpiricalEvent(np.exp(mu+self.r),self.w).shifted(x["origin_age_weeks"]-x["anchor_age_weeks"])
class CDFFusionPredictor:
 def __init__(self,predictors):self.predictors=predictors
 def predict(self,x):return Mixture([m.predict(x) for m in self.predictors])
class LognormalAFT:
 def __init__(self,use_group=False):self.use_group=use_group
 def fit(self,xs,w):
  from sklearn.linear_model import LinearRegression
  X=np.stack([features(x,self.use_group) for x in xs]);y=np.log([event_time_target(x) for x in xs])
  self.model=LinearRegression().fit(X,y,sample_weight=w);r=y-self.model.predict(X)
  self.sigma=max(float(np.sqrt(np.average(r*r,weights=w))),1e-4)
 def predict(self,x):
  mu=float(self.model.predict(features(x,self.use_group)[None,:])[0])
  return LognormalEvent(mu,self.sigma).shifted(x["origin_age_weeks"]-x["anchor_age_weeks"])
def make_gru(input_size=GROUPS+7,hidden=16):
 import torch
 from torch import nn
 class TinyGRU(nn.Module):
  def __init__(self):super().__init__();self.gru=nn.GRU(input_size,hidden,batch_first=True);self.head=nn.Linear(hidden,2)
  def forward(self,x):out,_=self.gru(x);return self.head(out[:,-1])
 return TinyGRU()

