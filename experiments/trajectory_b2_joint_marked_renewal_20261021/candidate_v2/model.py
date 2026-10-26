"""Small conditional marked-renewal density; import performs no data I/O or fitting."""
from __future__ import annotations
import math
import torch
from torch import nn

N_COMPONENTS=3
DELTA_K_SUPPORT=(1,2,3)
HIDDEN=64
DYNAMIC_DIM=6

class JointMarkedMixtureNet(nn.Module):
    """Joint (log-gap, signed dCapacity, delta-index) conditional density.

    The fixed input is the as-of anchor embedding and never changes during a
    forecast. The dynamic state updates only from sampled/observed renewal marks.
    `independent` is the product-of-marginals control using the identical head.
    """
    def __init__(self,fixed_dim:int,n_components:int=N_COMPONENTS,hidden:int=HIDDEN):
        super().__init__()
        if n_components!=3 or hidden!=64 or fixed_dim<=0:
            raise ValueError("frozen B2-v2 config is 3 components, MLP64")
        self.fixed_dim=int(fixed_dim)
        # Train-only weighted standardization lives in buffers so a checkpoint is
        # self-contained. Constant features keep scale 1 rather than 0/eps blow-up.
        self.register_buffer("fixed_mean",torch.zeros(self.fixed_dim,dtype=torch.float32))
        self.register_buffer("fixed_scale",torch.ones(self.fixed_dim,dtype=torch.float32))
        self.register_buffer("dynamic_mean",torch.zeros(DYNAMIC_DIM,dtype=torch.float32))
        self.register_buffer("dynamic_scale",torch.ones(DYNAMIC_DIM,dtype=torch.float32))
        self.normalization_source=None
        self.net=nn.Sequential(nn.Linear(self.fixed_dim+DYNAMIC_DIM,hidden),nn.SiLU(),
                               nn.Linear(hidden,hidden),nn.SiLU(),
                               nn.Linear(hidden,n_components*9))

    def set_normalization(self,fixed_mean,fixed_scale,dynamic_mean,dynamic_scale,source=None):
        """Install train-only statistics; scale<=1e-8 is replaced by 1 (constant feature)."""
        fm=torch.as_tensor(fixed_mean,dtype=torch.float32);fs=torch.as_tensor(fixed_scale,dtype=torch.float32)
        dm=torch.as_tensor(dynamic_mean,dtype=torch.float32);ds=torch.as_tensor(dynamic_scale,dtype=torch.float32)
        if fm.shape!=(self.fixed_dim,) or fs.shape!=(self.fixed_dim,) or dm.shape!=(DYNAMIC_DIM,) or ds.shape!=(DYNAMIC_DIM,):
            raise ValueError("normalization shape mismatch")
        if not torch.isfinite(fm).all() or not torch.isfinite(fs).all() or not torch.isfinite(dm).all() or not torch.isfinite(ds).all():
            raise ValueError("nonfinite normalization statistics")
        self.fixed_mean.copy_(fm);self.fixed_scale.copy_(torch.where(fs>1e-8,fs,torch.ones_like(fs)))
        self.dynamic_mean.copy_(dm);self.dynamic_scale.copy_(torch.where(ds>1e-8,ds,torch.ones_like(ds)))
        self.normalization_source=source

    def forward(self,fixed,dynamic):
        if fixed.ndim!=2 or dynamic.ndim!=2 or len(fixed)!=len(dynamic):
            raise ValueError("batch shape mismatch")
        if fixed.shape[1]!=self.fixed_dim or dynamic.shape[1]!=DYNAMIC_DIM:
            raise ValueError("feature shape mismatch")
        zf=(fixed-self.fixed_mean)/self.fixed_scale
        zd=(dynamic-self.dynamic_mean)/self.dynamic_scale
        return self.net(torch.cat([zf,zd],dim=1)).view(-1,3,9)


def compute_weighted_normalization(fixed,dynamic,weights):
    """Weighted mean/scale from TRAIN rows only (float64 accumulation, float32 output)."""
    import numpy as np
    f=np.asarray(fixed,dtype=np.float64);d=np.asarray(dynamic,dtype=np.float64);w=np.asarray(weights,dtype=np.float64)
    if f.ndim!=2 or d.ndim!=2 or len(f)!=len(d) or len(w)!=len(f) or len(f)==0:
        raise ValueError("normalization inputs must be nonempty aligned 2-D arrays")
    if not (np.isfinite(f).all() and np.isfinite(d).all() and np.isfinite(w).all()) or (w<0).any() or w.sum()<=0:
        raise ValueError("invalid normalization inputs/weights")
    w=w/w.sum()
    def _stats(a):
        mean=(a*w[:,None]).sum(0)
        var=((a-mean)**2*w[:,None]).sum(0)
        scale=np.sqrt(np.maximum(var,0.0))
        scale=np.where(scale>1e-8,scale,1.0)
        return mean.astype(np.float32),scale.astype(np.float32)
    fm,fs=_stats(f);dm,ds=_stats(d)
    return fm,fs,dm,ds


def _parts(p):
    logits=p[:,:,0]
    mu_g=p[:,:,1]; mu_c=p[:,:,2]
    sd_g=torch.nn.functional.softplus(p[:,:,3])+1e-4
    sd_c=torch.nn.functional.softplus(p[:,:,4])+1e-4
    rho=0.995*torch.tanh(p[:,:,5])
    mark_logp=torch.log_softmax(p[:,:,6:9],dim=-1)
    return logits,mu_g,mu_c,sd_g,sd_c,rho,mark_logp


def log_prob(params,log_gap,delta_capacity,delta_k,variant="joint"):
    """Per-row density for (log gap, signed Δlog-capacity, ΔK)."""
    if variant not in ("joint","independent"): raise ValueError("unknown density variant")
    logits,mg,mc,sg,sc,rho,marklp=_parts(params)
    yg=log_gap.reshape(-1,1); yc=delta_capacity.reshape(-1,1)
    dk=delta_k.long().reshape(-1)
    if torch.any((dk<1)|(dk>3)): raise ValueError("deltaK outside frozen support 1..3")
    cat=dk-1
    logmix=torch.log_softmax(logits,dim=-1)
    zg=(yg-mg)/sg
    zc=(yc-mc)/sc
    logpg=-0.5*zg.square()-torch.log(sg)-0.5*math.log(2*math.pi)
    logpc=-0.5*zc.square()-torch.log(sc)-0.5*math.log(2*math.pi)
    if variant=="joint":
        one=(zg.square()-2*rho*zg*zc+zc.square())/(1-rho.square())
        logp2=-0.5*one-torch.log(sg)-torch.log(sc)-math.log(2*math.pi)-0.5*torch.log(1-rho.square())
        mark=marklp.gather(2,cat[:,None,None].expand(-1,3,1)).squeeze(-1)
        return torch.logsumexp(logmix+logp2+mark,dim=1)
    lp_g=torch.logsumexp(logmix+logpg,dim=1)
    lp_c=torch.logsumexp(logmix+logpc,dim=1)
    marginal_k=torch.logsumexp(logmix[:,:,None]+marklp,dim=1)
    lp_k=marginal_k.gather(1,cat[:,None]).squeeze(1)
    return lp_g+lp_c+lp_k


def _checked_weights(logits,where=""):
    """Finite mixture weights; raises a catchable error instead of a CUDA assert."""
    if not torch.isfinite(logits).all(): raise FloatingPointError(f"nonfinite mixture logits {where}")
    w=torch.softmax(logits,dim=-1)
    if not torch.isfinite(w).all(): raise FloatingPointError(f"nonfinite mixture weights {where}")
    if torch.any(w.sum(dim=-1)<=0): raise FloatingPointError(f"degenerate mixture weights {where}")
    return w


def sample_mark_batch(params,generator,variant="joint"):
    """Vectorized one-step marks; returns log-gap, ΔK, and Δlog-capacity."""
    if variant not in ("joint","independent"): raise ValueError("unknown density variant")
    if params.ndim!=3 or params.shape[1:]!=(3,9): raise ValueError("expected Bx3x9 density parameters")
    if not torch.isfinite(params).all(): raise FloatingPointError("nonfinite density parameters")
    logits,mg,mc,sg,sc,rho,marklp=_parts(params)
    weights=_checked_weights(logits,"sample_mark_batch")
    b=params.shape[0]
    if variant=="joint":
        comp=torch.multinomial(weights,1,generator=generator).squeeze(1)
        gather=comp[:,None]
        gmu=mg.gather(1,gather).squeeze(1);cmu=mc.gather(1,gather).squeeze(1)
        gsd=sg.gather(1,gather).squeeze(1);csd=sc.gather(1,gather).squeeze(1)
        corr=rho.gather(1,gather).squeeze(1)
        z1=torch.randn((b,),generator=generator,device=params.device,dtype=params.dtype)
        z2=torch.randn((b,),generator=generator,device=params.device,dtype=params.dtype)
        log_gap=gmu+gsd*z1
        delta_logc=cmu+csd*(corr*z1+torch.sqrt(1-corr.square())*z2)
        selected=marklp.gather(1,comp[:,None,None].expand(-1,1,3)).squeeze(1)
        dk=torch.multinomial(torch.softmax(selected,dim=-1),1,generator=generator).squeeze(1)+1
    else:
        cg=torch.multinomial(weights,1,generator=generator).squeeze(1)
        cc=torch.multinomial(weights,1,generator=generator).squeeze(1)
        log_gap=mg.gather(1,cg[:,None]).squeeze(1)+sg.gather(1,cg[:,None]).squeeze(1)*torch.randn((b,),generator=generator,device=params.device,dtype=params.dtype)
        delta_logc=mc.gather(1,cc[:,None]).squeeze(1)+sc.gather(1,cc[:,None]).squeeze(1)*torch.randn((b,),generator=generator,device=params.device,dtype=params.dtype)
        pk=torch.sum(weights[:,:,None]*torch.exp(marklp),dim=1)
        dk=torch.multinomial(pk,1,generator=generator).squeeze(1)+1
    if torch.any(~torch.isfinite(log_gap)) or torch.any(~torch.isfinite(delta_logc)):
        raise FloatingPointError("nonfinite sampled renewal mark")
    return log_gap,dk,delta_logc


def sample_mark_at_gap(params,gap_weeks,generator,variant="joint"):
    """One-step marks at a PRE-FIXED gap: joint capacity increment uses the mixture
    posterior p(component|gap) and the bivariate conditional mean/sd; the fixed gap is
    never overwritten by an unconditional draw."""
    if not (math.isfinite(float(gap_weeks)) and float(gap_weeks)>0):
        raise ValueError("fixed gap must be positive finite")
    if params.ndim!=3 or params.shape[1:]!=(3,9): raise ValueError("expected Bx3x9 density parameters")
    if variant not in ("joint","independent"): raise ValueError("unknown density variant")
    if not torch.isfinite(params).all(): raise FloatingPointError("nonfinite density parameters")
    logits,mg,mc,sg,sc,rho,marklp=_parts(params)
    b=params.shape[0]
    lgap=math.log(float(gap_weeks))
    if variant=="joint":
        zg=(lgap-mg)/sg
        post=torch.log_softmax(logits,dim=-1)-0.5*zg.square()-torch.log(sg)
        w=_checked_weights(post,"sample_mark_at_gap")
        comp=torch.multinomial(w,1,generator=generator).squeeze(1)
        g=comp[:,None]
        gmu=mg.gather(1,g).squeeze(1);cmu=mc.gather(1,g).squeeze(1)
        gsd=sg.gather(1,g).squeeze(1);csd=sc.gather(1,g).squeeze(1)
        corr=rho.gather(1,g).squeeze(1)
        mean=cmu+corr*(csd/gsd)*(lgap-gmu)
        sd=csd*torch.sqrt(1.0-corr.square())
        delta_logc=mean+sd*torch.randn((b,),generator=generator,device=params.device,dtype=params.dtype)
        selected=marklp.gather(1,comp[:,None,None].expand(-1,1,3)).squeeze(1)
        dk=torch.multinomial(torch.softmax(selected,dim=-1),1,generator=generator).squeeze(1)+1
    else:
        cc=torch.multinomial(torch.softmax(logits,dim=-1),1,generator=generator).squeeze(1)
        delta_logc=mc.gather(1,cc[:,None]).squeeze(1)+sc.gather(1,cc[:,None]).squeeze(1)*torch.randn((b,),generator=generator,device=params.device,dtype=params.dtype)
        pk=torch.sum(torch.softmax(logits,dim=-1)[:,:,None]*torch.exp(marklp),dim=1)
        dk=torch.multinomial(pk,1,generator=generator).squeeze(1)+1
    log_gap=torch.full((b,),lgap,dtype=params.dtype,device=params.device)
    if torch.any(~torch.isfinite(log_gap)) or torch.any(~torch.isfinite(delta_logc)):
        raise FloatingPointError("nonfinite sampled renewal mark")
    return log_gap,dk,delta_logc


def conditional_delta_capacity_mixture(params,observed_gap_weeks,variant="joint"):
    """Return weights/means/sds for Δcapacity | known next-valid-RPT gap."""
    if observed_gap_weeks<=0 or not math.isfinite(observed_gap_weeks):
        raise ValueError("known evaluation gap must be positive finite")
    if variant not in ("joint","independent"): raise ValueError("unknown density variant")
    p=params.reshape(3,9)
    logits,mg,mc,sg,sc,rho,_=_parts(p[None,...])
    y=math.log(observed_gap_weeks)
    if variant=="joint":
        lp=logits[0]-0.5*((y-mg[0])/sg[0]).square()-torch.log(sg[0])
        w=torch.softmax(lp,dim=0)
        means=mc[0]+rho[0]*(sc[0]/sg[0])*(y-mg[0])
        sds=sc[0]*torch.sqrt(1-rho[0].square())
    else:
        w=torch.softmax(logits[0],dim=0)
        means=mc[0];sds=sc[0]
    return w,means,sds


def _field(r,*names):
    for name in names:
        if name in r: return r[name]
    raise KeyError(names[0])


def initial_dynamic_state(visible_records,anchor_epoch):
    rows=sorted(visible_records,key=lambda r:(float(_field(r,'source_stop_epoch','stop_epoch')),int(r['source_rpt_index'])))
    if len(rows)<2: raise ValueError("need two arrived valid RPTs for dynamic warmup")
    a,b=rows[-2],rows[-1]
    gap=(float(_field(b,'source_stop_epoch','stop_epoch'))-float(_field(a,'source_stop_epoch','stop_epoch')))/604800.0
    if gap<=0: raise ValueError("nonpositive visible source gap")
    ca=float(_field(a,'capacity_ah','capacityAh'));cb=float(_field(b,'capacity_ah','capacityAh'))
    if ca<=0 or cb<=0: raise ValueError("source capacities must be positive for log-ratio marks")
    dz=math.log(cb/ca)
    return [cb,math.log1p(gap),dz,0.0,0.0,0.0]


def update_dynamic_state(state,gap_weeks,delta_k,delta_log_capacity):
    if gap_weeks<=0 or delta_k not in DELTA_K_SUPPORT: raise ValueError("invalid renewal mark")
    if float(state[0])<=0: raise ValueError("current capacity must be positive")
    try: cap=float(state[0])*math.exp(float(delta_log_capacity))
    except OverflowError as e: raise FloatingPointError("log-capacity increment overflow; do not clip") from e
    if not math.isfinite(cap) or cap<=0: raise FloatingPointError("invalid sampled capacity after log-ratio update")
    elapsed=math.expm1(float(state[3]))+float(gap_weeks)
    steps=math.expm1(float(state[4]))+1.0
    source_progress=math.expm1(float(state[5]))+int(delta_k)
    return [cap,math.log1p(float(gap_weeks)),float(delta_log_capacity),math.log1p(elapsed),
            math.log1p(steps),math.log1p(source_progress)]


def conditional_anchor_transition_capacity_log_prob(params,observed_gap_weeks,capacity_prev_ah,capacity_next_ah,variant="joint"):
    """Log density per Ah of C_next | known gap,C_prev, including change-of-variable Jacobian."""
    if capacity_prev_ah<=0 or capacity_next_ah<=0: raise ValueError("capacity must be positive")
    z=math.log(float(capacity_next_ah)/float(capacity_prev_ah))
    w,m,s=conditional_delta_capacity_mixture(params,observed_gap_weeks,variant)
    y=torch.as_tensor(z,device=m.device,dtype=m.dtype)
    lp=-0.5*((y-m)/s).square()-torch.log(s)-0.5*math.log(2*math.pi)
    logp_z=torch.logsumexp(torch.log(w+1e-30)+lp,dim=0)
    return logp_z-math.log(float(capacity_next_ah))
