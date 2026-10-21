"""B: conditional capacity-path models and first-passage utilities."""
import math
import torch
from torch import nn


class ConditionalCapacityPath(nn.Module):
    """B-full: recurrent Gaussian increments, permitting reversible capacity."""
    def __init__(self, feature_dim=74, hidden=48):
        super().__init__()
        self.context=nn.Sequential(nn.Linear(feature_dim,hidden),nn.SiLU(),nn.Linear(hidden,hidden),nn.SiLU())
        self.cell=nn.GRUCell(2,hidden)
        self.head=nn.Linear(hidden,2)

    def transition(self, h, q, dt):
        h=self.cell(torch.stack([dt,q],dim=-1),h)
        mu,log_sigma=self.head(h).unbind(-1)
        return h,mu,log_sigma.clamp(-8,3)

    def sample(self, features, latest_capacity, hidden_delta, future_gaps,
               inspection_interval_weeks, n_paths=512):
        """Simulate hidden checks to q, then a supplied evaluation or train-only grid."""
        b=features.shape[0]
        if features.ndim!=2 or latest_capacity.shape!=(b,) or hidden_delta.shape!=(b,):
            raise ValueError("expected features [B,F], capacity [B], hidden_delta [B]")
        if future_gaps.ndim==1: future_gaps=future_gaps[None,:].expand(b,-1)
        if future_gaps.ndim!=2 or future_gaps.shape[0]!=b or (future_gaps<0).any():
            raise ValueError("future gaps must be nonnegative [S] or [B,S]")
        if (hidden_delta<0).any() or inspection_interval_weeks<=0 or n_paths<1:
            raise ValueError("invalid interval or path count")
        max_delta=float(hidden_delta.max().item()) if b else 0.
        n_hidden=int(math.ceil(max_delta/inspection_interval_weeks))
        s=future_gaps.shape[1]
        h=self.context(features)[:,None,:].expand(b,n_paths,-1).reshape(b*n_paths,-1)
        q=latest_capacity[:,None].expand(b,n_paths).reshape(-1)
        paths=[];times=[];hidden_mask=[];valid_check=[]
        for j in range(n_hidden):
            end=torch.minimum(hidden_delta,hidden_delta.new_full((b,),(j+1)*inspection_interval_weeks))
            start=hidden_delta.new_full((b,),j*inspection_interval_weeks)
            dt=(end-start).clamp_min(0);active=dt>0
            dtp=dt[:,None].expand(b,n_paths).reshape(-1)
            h1,mu,ls=self.transition(h,q,dtp)
            q1=q+mu+ls.exp()*torch.randn_like(mu)
            activep=active[:,None].expand(b,n_paths).reshape(-1)
            h=torch.where(activep[:,None],h1,h);q=torch.where(activep,q1,q)
            paths.append(q.reshape(b,n_paths));times.append(end-hidden_delta);hidden_mask.append(active);valid_check.append(active)
        elapsed=torch.zeros(b,device=features.device,dtype=features.dtype)
        for j in range(s):
            dt=future_gaps[:,j]
            dtp=dt[:,None].expand(b,n_paths).reshape(-1)
            h,mu,ls=self.transition(h,q,dtp)
            q=q+mu+ls.exp()*torch.randn_like(mu)
            elapsed=elapsed+dt
            paths.append(q.reshape(b,n_paths));times.append(elapsed.clone())
            hidden_mask.append(torch.zeros(b,dtype=torch.bool,device=features.device));valid_check.append(torch.ones(b,dtype=torch.bool,device=features.device))
        if not paths:
            return {"capacity":features.new_empty((b,n_paths,0)),
                    "relative_weeks":features.new_empty((b,0)),
                    "hidden_check":torch.empty((b,0),dtype=torch.bool,device=features.device)}
        return {"capacity":torch.stack(paths,-1),"relative_weeks":torch.stack(times,-1),
                "hidden_check":torch.stack(hidden_mask,-1),"valid_check":torch.stack(valid_check,-1)}

    def masked_increment_nll(self, features, start_capacity, gaps, target_capacity, support_mask):
        b,s=target_capacity.shape
        if gaps.ndim==1:gaps=gaps[None,:].expand(b,-1)
        if gaps.shape!=(b,s) or support_mask.shape!=(b,s):raise ValueError("target/grid/mask mismatch")
        h=self.context(features);q=start_capacity
        prev=torch.cat([start_capacity[:,None],target_capacity[:,:-1]],1)
        inc=target_capacity-prev;terms=[]
        for j in range(s):
            h,mu,ls=self.transition(h,q,gaps[:,j])
            z=(inc[:,j]-mu)/ls.exp()
            terms.append(.5*z.square()+ls+.5*math.log(2*math.pi))
            q=target_capacity[:,j]
        val=torch.stack(terms,1);mask=support_mask.to(val.dtype)
        per_row=(val*mask).sum(1)/mask.sum(1).clamp_min(1)
        return per_row.mean()


class IndependentIncrementAblation(nn.Module):
    """B-independent: same marginals and input, removes recurrent path state."""
    def __init__(self, feature_dim=74, hidden=48):
        super().__init__()
        self.context=nn.Sequential(nn.Linear(feature_dim,hidden),nn.SiLU(),nn.Linear(hidden,hidden),nn.SiLU())
        self.head=nn.Sequential(nn.Linear(hidden+2,hidden),nn.SiLU(),nn.Linear(hidden,2))

    def transition(self, context, q, dt):
        mu,ls=self.head(torch.cat([context,q[:,None],dt[:,None]],-1)).unbind(-1)
        return mu,ls.clamp(-8,3)

    def masked_increment_nll(self, features,start_capacity,gaps,target_capacity,support_mask):
        b,s=target_capacity.shape
        if gaps.ndim==1:gaps=gaps[None,:].expand(b,-1)
        ctx=self.context(features);q=start_capacity
        prev=torch.cat([start_capacity[:,None],target_capacity[:,:-1]],1)
        inc=target_capacity-prev;terms=[]
        for j in range(s):
            mu,ls=self.transition(ctx,q,gaps[:,j]);z=(inc[:,j]-mu)/ls.exp()
            terms.append(.5*z.square()+ls+.5*math.log(2*math.pi));q=target_capacity[:,j]
        val=torch.stack(terms,1);mask=support_mask.to(val.dtype)
        per_row=(val*mask).sum(1)/mask.sum(1).clamp_min(1)
        return per_row.mean()

    @torch.no_grad()
    def sample(self,features,latest_capacity,hidden_delta,future_gaps,inspection_interval_weeks,n_paths=512):
        b=features.shape[0]
        if future_gaps.ndim==1:future_gaps=future_gaps[None,:].expand(b,-1)
        ctx=self.context(features)[:,None,:].expand(b,n_paths,-1).reshape(b*n_paths,-1)
        q=latest_capacity[:,None].expand(b,n_paths).reshape(-1)
        max_delta=float(hidden_delta.max().item()) if b else 0.
        nh=int(math.ceil(max_delta/inspection_interval_weeks));paths=[];times=[];hm=[];valid=[]
        for j in range(nh):
            end=torch.minimum(hidden_delta,hidden_delta.new_full((b,),(j+1)*inspection_interval_weeks))
            start=hidden_delta.new_full((b,),j*inspection_interval_weeks);dt=(end-start).clamp_min(0)
            dtp=dt[:,None].expand(b,n_paths).reshape(-1)
            mu,ls=self.transition(ctx,q,dtp);q1=q+mu+ls.exp()*torch.randn_like(mu)
            active=dt>0;ap=active[:,None].expand(b,n_paths).reshape(-1);q=torch.where(ap,q1,q)
            paths.append(q.reshape(b,n_paths));times.append(end-hidden_delta);hm.append(active);valid.append(active)
        elapsed=torch.zeros(b,device=features.device,dtype=features.dtype)
        for j in range(future_gaps.shape[1]):
            dt=future_gaps[:,j];dtp=dt[:,None].expand(b,n_paths).reshape(-1)
            mu,ls=self.transition(ctx,q,dtp);q=q+mu+ls.exp()*torch.randn_like(mu)
            elapsed=elapsed+dt;paths.append(q.reshape(b,n_paths));times.append(elapsed.clone())
            hm.append(torch.zeros(b,dtype=torch.bool,device=features.device));valid.append(torch.ones(b,dtype=torch.bool,device=features.device))
        return {"capacity":torch.stack(paths,-1),"relative_weeks":torch.stack(times,-1),
                "hidden_check":torch.stack(hm,-1),"valid_check":torch.stack(valid,-1)}


def summarize_first_passage(sampled,threshold_ah=.20,horizons=(4.,12.)):
    q=sampled["capacity"];times=sampled["relative_weeks"];hidden=sampled["hidden_check"];valid=sampled["valid_check"]
    if q.ndim!=3 or times.shape!=(q.shape[0],q.shape[2]) or hidden.shape!=times.shape or valid.shape!=times.shape:
        raise ValueError("malformed sampled path bundle")
    hit=(q<=float(threshold_ah)) & valid[:,None,:];any_hit=hit.any(-1)
    idx=hit.to(torch.int64).argmax(-1)
    first=times[:,None,:].expand_as(q).gather(-1,idx[...,None]).squeeze(-1)
    hidden_hit=(hit & hidden[:,None,:]).any(-1)
    rul=torch.where(hidden_hit,torch.zeros_like(first),first)
    rul=torch.where(any_hit,rul,torch.full_like(rul,float("nan")))
    result={"current_event_probability":hidden_hit.to(q.dtype).mean(1),"rul_samples_weeks":rul}
    for h in horizons:
        result["event_probability_"+str(h)]=((hit & (times[:,None,:]<=float(h))).any(-1)).to(q.dtype).mean(1)
    return result
