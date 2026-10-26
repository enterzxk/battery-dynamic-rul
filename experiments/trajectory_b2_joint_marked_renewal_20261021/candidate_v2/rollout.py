"""Vectorized as-of rejection rollout for source-observed first-valid-RPT RUL.

Protocol notes fixed in v2.1:
- Epoch seconds and event times are float64; only model tensor inputs/outputs are float32.
- Accepted proposals are selected in GLOBAL PROPOSAL ORDER (the order proposals were
  generated), never in completion order, so truncation to n_samples cannot bias toward
  fast-finishing paths or the last partial batch.
- Two predeclared zero-fit controls: condition_on_no_arrival=False (no-arrival
  conditioning switched off) and fixed_gap_weeks=... (gaps fixed; capacity marks drawn
  conditional on that gap with the mixture posterior p(component|gap)).
"""
from __future__ import annotations
import math,torch
from model import sample_mark_batch,sample_mark_at_gap,update_dynamic_state,initial_dynamic_state
WEEK=604800.0;THRESHOLD_AH=.20;MAX_RUL_WEEKS=128.0


def _due_tensor(arm,idx,t,q,warmup_idx):
    if arm=='raw': keep=torch.ones_like(idx,dtype=torch.bool);lag=0.0
    elif arm=='delay7d': keep=torch.ones_like(idx,dtype=torch.bool);lag=7*86400.0
    elif arm=='sparse2':
        keep=(idx<=int(warmup_idx))|(((idx-int(warmup_idx))%2)==0);lag=0.0
    else: raise ValueError('unknown arm')
    return keep & (t+lag<=float(q))


def select_in_proposal_order(accepted,n_samples):
    """accepted: mapping proposal_serial -> record. Returns the first n in serial order."""
    n=int(n_samples)
    if n<=0: raise ValueError('n_samples must be positive')
    serials=sorted(accepted)
    if len(serials)<n: raise RuntimeError(f'insufficient accepted paths {len(serials)}/{n}')
    return [accepted[s] for s in serials[:n]]


def forecast_rul(model,fixed,visible_records,q_epoch,warmup_anchor_index,arm,
                 variant,seed=42,max_proposals=50000,n_samples=256,
                 min_accept_rate=.01,max_weeks=MAX_RUL_WEEKS,
                 max_valid_checks=512,proposal_batch_size=64,
                 condition_on_no_arrival=True,fixed_gap_weeks=None):
    """Vectorized rejection sampler conditional on no extra due report by q."""
    visible=sorted(visible_records,key=lambda r:(float(r.get('source_stop_epoch',r.get('stop_epoch'))),int(r['source_rpt_index'])))
    if len(visible)<2: raise ValueError('at least two visible valid RPTs required')
    cap_key=lambda r:float(r.get('capacity_ah',r.get('capacityAh')))
    if any(cap_key(r)<=0 for r in visible): raise ValueError('nonpositive source capacity')
    if fixed_gap_weeks is not None:
        fixed_gap_weeks=float(fixed_gap_weeks)
        if not (math.isfinite(fixed_gap_weeks) and fixed_gap_weeks>0):
            raise ValueError('fixed_gap_weeks must be positive finite')
    if any(cap_key(r)<=THRESHOLD_AH for r in visible):
        return {'samples':[0.0]*int(n_samples),'tail_mass':0.0,'proposals':0,'acceptance_rate':1.0,
                'effective_sample_size':float(n_samples),'known_event_mass_at_zero':1.0,
                'epoch_dtype':'torch.float64','condition_on_no_arrival':bool(condition_on_no_arrival),
                'fixed_gap_weeks':fixed_gap_weeks,'truncation_rule':'global_proposal_order',
                'selected_proposal_serials':[]}
    anchor=visible[-1];t0=float(anchor.get('source_stop_epoch',anchor.get('stop_epoch')))
    q=float(q_epoch);cap0=cap_key(anchor);idx0=int(anchor['source_rpt_index'])
    mparam=next(model.parameters())
    device=mparam.device;mdtype=mparam.dtype
    EP=torch.float64  # epoch seconds must not be cast to float32 (loses minutes at 1.6e9 s)
    fixed_one=torch.as_tensor(fixed,dtype=mdtype,device=device).reshape(1,-1)
    dyn0=torch.as_tensor(initial_dynamic_state(visible,t0),dtype=mdtype,device=device)
    generator=torch.Generator(device=device).manual_seed(int(seed))
    end_epoch=q+float(max_weeks)*WEEK
    accepted={};proposals=0;next_serial=0;numerical_rejections=0
    model.eval()
    while proposals<int(max_proposals) and len(accepted)<int(n_samples):
        b=min(int(proposal_batch_size),int(max_proposals)-proposals)
        proposals+=b
        serial=torch.arange(next_serial,next_serial+b,dtype=torch.long,device=device);next_serial+=b
        t=torch.full((b,),t0,dtype=EP,device=device)
        idx=torch.full((b,),idx0,dtype=torch.long,device=device)
        cap=torch.full((b,),cap0,dtype=mdtype,device=device)
        dyn=dyn0[None,:].expand(b,-1).clone()
        event=torch.full((b,),float('nan'),dtype=EP,device=device)
        active=torch.ones((b,),dtype=torch.bool,device=device)
        for _step in range(int(max_valid_checks)):
            live=torch.nonzero(active,as_tuple=False).squeeze(1)
            if live.numel()==0: break
            remaining=(end_epoch-t[live])/WEEK
            if torch.any(remaining<=0): raise RuntimeError('internal horizon state error')
            params=model(fixed_one.expand(live.numel(),-1),dyn[live])
            if not torch.isfinite(params).all(): raise FloatingPointError('nonfinite density parameters')
            if fixed_gap_weeks is None:
                log_gap,dk,dlogc=sample_mark_batch(params,generator,variant)
            else:
                log_gap,dk,dlogc=sample_mark_at_gap(params,fixed_gap_weeks,generator,variant)
            beyond=log_gap>torch.log(remaining)
            if beyond.any():
                tail_idx=live[beyond];tail_t=t[tail_idx];tail_ser=serial[tail_idx]
                for j,tt,ss in zip(tail_idx.tolist(),tail_t.tolist(),tail_ser.tolist()):
                    accepted[int(ss)]={'rul_weeks':float(max(0.,(end_epoch-q)/WEEK)),'tail_gt_128':True}
                    active[j]=False
            inside=~beyond
            if not inside.any(): continue
            ids=live[inside];lg=log_gap[inside];ks=dk[inside];zs=dlogc[inside]
            gaps=torch.exp(lg)  # exponentiation occurs only after a finite 128-week-tail comparison
            tn=t[ids]+gaps.double()*WEEK
            cn=cap[ids]*torch.exp(zs)
            bad=~torch.isfinite(cn)|(cn<=0)|(cn>1e3)|(cn<1e-6)
            numerical_rejections+=int(bad.sum().item())
            if bad.any():
                # A numerically invalid draw is refused (never clipped, never rescaled);
                # refused proposals count against acceptance, exactly like contradictions.
                active[ids[bad]]=False
            ok_num=~bad
            if not ok_num.any(): continue
            ids=ids[ok_num];gaps=gaps[ok_num];tn=tn[ok_num];cn=cn[ok_num]
            ks=ks[ok_num];zs=zs[ok_num]
            old_event=event[ids]
            crossing=torch.isnan(old_event)&(cn<=THRESHOLD_AH)
            ev_new=torch.where(crossing,tn,old_event)
            contradiction=_due_tensor(arm,idx[ids]+ks,tn,q,warmup_anchor_index)&(tn<=q)
            if contradiction.any():
                if condition_on_no_arrival: active[ids[contradiction]]=False
            okay=torch.ones_like(contradiction) if not condition_on_no_arrival else ~contradiction
            if not okay.any(): continue
            good_ids=ids[okay];good_t=tn[okay];good_c=cn[okay];good_k=ks[okay];good_z=zs[okay];good_gap=gaps[okay];good_ev=ev_new[okay];good_ser=serial[good_ids]
            finished=(good_t>q)&((~torch.isnan(good_ev))|(good_t>=end_epoch))
            if finished.any():
                fi=good_ids[finished]
                for j,ev,ss in zip(fi.tolist(),good_ev[finished].tolist(),good_ser[finished].tolist()):
                    has_event=math.isfinite(float(ev))
                    accepted[int(ss)]={'rul_weeks':float(max(0.,(float(ev)-q)/WEEK)) if has_event else float(max_weeks),'tail_gt_128':not has_event}
                    active[j]=False
            continuing=~finished
            if continuing.any():
                ci=good_ids[continuing];ct=good_t[continuing];cc=good_c[continuing];ck=good_k[continuing];cz=good_z[continuing];cg=good_gap[continuing]
                ce=good_ev[continuing]
                olddyn=dyn[ci]
                elapsed=torch.expm1(olddyn[:,3])+cg
                steps=torch.expm1(olddyn[:,4])+1.0
                progress=torch.expm1(olddyn[:,5])+ck.to(mdtype)
                dyn[ci]=torch.stack([cc,torch.log1p(cg),cz,torch.log1p(elapsed),torch.log1p(steps),torch.log1p(progress)],dim=1)
                t[ci]=ct;idx[ci]+=ck;cap[ci]=cc;event[ci]=ce
        if active.any(): raise RuntimeError(f'path exceeded frozen {max_valid_checks} valid-check cap')
        if proposals>=100 and len(accepted)/proposals<float(min_accept_rate):
            raise RuntimeError(f'no-extra-due-report acceptance below frozen floor: {len(accepted)/proposals:.6g}')
    accepted_total=len(accepted)
    chosen=select_in_proposal_order(accepted,int(n_samples))
    return {'samples':[float(x['rul_weeks']) for x in chosen],
            'tail_mass':float(sum(x['tail_gt_128'] for x in chosen)/len(chosen)),
            'proposals':proposals,'acceptance_rate':accepted_total/proposals,
            'effective_sample_size':float(len(chosen)),'known_event_mass_at_zero':0.0,
            'epoch_dtype':str(t.dtype),'condition_on_no_arrival':bool(condition_on_no_arrival),
            'fixed_gap_weeks':fixed_gap_weeks,'truncation_rule':'global_proposal_order',
            'selected_proposal_serials':[int(s) for s in sorted(accepted)[:int(n_samples)]],
            'numerical_rejections':int(numerical_rejections)}
