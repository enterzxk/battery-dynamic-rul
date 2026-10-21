"""Exact piecewise-continuous RUL distributions for DART V18."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
EDGES=np.asarray([0,.25,.5,1,2,3,4,6,8,12,16,24,32,48,64,96,128],dtype=np.float64)
TAIL_SCALE=32.0
@dataclass(frozen=True)
class RULDistribution:
    pmf: np.ndarray
    shift_weeks: float=0.0
    def __post_init__(self):
        p=np.asarray(self.pmf,dtype=np.float64)
        if p.shape!=(18,) or not np.all(np.isfinite(p)) or np.any(p<0) or not np.isclose(p.sum(),1,rtol=1e-10,atol=1e-12): raise ValueError("invalid 18-class pmf")
        if not np.isfinite(self.shift_weeks) or self.shift_weeks<0: raise ValueError("invalid shift")
        object.__setattr__(self,"pmf",p.copy())
    @property
    def zero_mass(self): return float(self.cdf(0.))
    def shift(self,delta_weeks):
        d=float(delta_weeks)
        if not np.isfinite(d) or d<0: raise ValueError("invalid shift")
        return RULDistribution(self.pmf,self.shift_weeks+d)
    def cdf(self,x):
        a=np.asarray(x,dtype=np.float64); z=a+self.shift_weeks; out=np.zeros_like(a); mask=z>=0; v=z[mask]
        if v.size:
            y=np.full(v.shape,self.pmf[0])
            for j,(lo,hi) in enumerate(zip(EDGES[:-1],EDGES[1:]),1): y+=self.pmf[j]*np.clip((v-lo)/(hi-lo),0,1)
            y+=self.pmf[-1]*(-np.expm1(-np.maximum(v-128.,0)/TAIL_SCALE)); out[mask]=y
        out=np.where(a>=0,out,0); out=np.where(np.isposinf(a),1.,out)
        return float(out) if a.ndim==0 else out
    def mean(self):
        d=self.shift_weeks; s=0.
        for j,(lo,hi) in enumerate(zip(EDGES[:-1],EDGES[1:]),1):
            a=max(d,float(lo))
            if a<hi: s+=float(self.pmf[j+1:].sum())*(hi-a)+float(self.pmf[j])*(hi-a)**2/(2*(hi-lo))
        a=max(d,128.); s+=float(self.pmf[-1])*32*np.exp(-(a-128.)/32)
        return float(s)
    def quantile(self,p):
        q=float(p)
        if not np.isfinite(q) or q<0 or q>1: raise ValueError("p outside [0,1]")
        if q<=self.zero_mass: return 0.
        c=float(self.pmf[0])
        for j,(lo,hi) in enumerate(zip(EDGES[:-1],EDGES[1:]),1):
            m=float(self.pmf[j])
            if q<=c+m: return max(float(lo+(q-c)/m*(hi-lo))-self.shift_weeks,0.) if m>0 else max(float(lo)-self.shift_weeks,0.)
            c+=m
        m=float(self.pmf[-1])
        if m<=0: return max(128.-self.shift_weeks,0.)
        if q>=1: return float("inf")
        return max(float(128-32*np.log1p(-(q-c)/m))-self.shift_weeks,0.)
def torch_logcdf(logits,x):
    import torch
    e=torch.as_tensor(EDGES,dtype=logits.dtype,device=logits.device); z=torch.as_tensor(x,dtype=logits.dtype,device=logits.device)
    if z.ndim==0: z=z.expand(logits.shape[:-1])
    z=z.expand(logits.shape[:-1]); w=torch.zeros_like(logits); w[...,0]=(z>=0).to(logits.dtype)
    for j in range(16): w[...,j+1]=((z-e[j])/(e[j+1]-e[j])).clamp(0,1)
    w[...,-1]=torch.where(z>128.,-torch.expm1(-(z-128.).clamp_min(0)/32),torch.zeros_like(z))
    lw=torch.where(w>0,w.log(),torch.full_like(w,-torch.inf))
    return torch.logsumexp(torch.log_softmax(logits,dim=-1)+lw,dim=-1)
def torch_log_survival(logits,x):
    import torch
    e=torch.as_tensor(EDGES,dtype=logits.dtype,device=logits.device); z=torch.as_tensor(x,dtype=logits.dtype,device=logits.device)
    if z.ndim==0: z=z.expand(logits.shape[:-1])
    z=z.expand(logits.shape[:-1]); w=torch.ones_like(logits); w[...,0]=(z<0).to(logits.dtype)
    for j in range(16): w[...,j+1]=(1-(z-e[j])/(e[j+1]-e[j])).clamp(0,1)
    w[...,-1]=torch.where(z<128.,torch.ones_like(z),torch.exp(-(z-128.).clamp_min(0)/32))
    lw=torch.where(w>0,w.log(),torch.full_like(w,-torch.inf))
    return torch.logsumexp(torch.log_softmax(logits,dim=-1)+lw,dim=-1)
def torch_log_density(logits,x):
    import torch
    e=torch.as_tensor(EDGES,dtype=logits.dtype,device=logits.device); z=torch.as_tensor(x,dtype=logits.dtype,device=logits.device)
    if z.ndim==0: z=z.expand(logits.shape[:-1])
    z=z.expand(logits.shape[:-1]); idx=(torch.bucketize(z.contiguous(),e[1:-1],right=True)+1).clamp(1,17)
    widths=torch.as_tensor(np.diff(EDGES),dtype=logits.dtype,device=logits.device); lp=torch.log_softmax(logits,dim=-1)
    f=lp.gather(-1,idx.unsqueeze(-1)).squeeze(-1)-torch.log(widths[(idx-1).clamp(0,15)])
    t=lp[...,-1]-np.log(32.)-(z-128.).clamp_min(0)/32.
    return torch.where(z>=128.,t,f)
def torch_hazards_to_logits(h):
    import torch
    a=torch.nn.functional.logsigmoid(h); b=torch.nn.functional.logsigmoid(-h); out=[a[...,0]]; surv=b[...,0]
    for j in range(1,17): out.append(surv+a[...,j]); surv=surv+b[...,j]
    out.append(surv); return torch.stack(out,dim=-1)
