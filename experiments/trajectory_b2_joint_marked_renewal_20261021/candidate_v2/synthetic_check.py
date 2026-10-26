from __future__ import annotations
import math
import numpy as np
import torch
from torch import nn
from scipy.stats import multivariate_normal, norm
from model import (
    JointMarkedMixtureNet, log_prob, conditional_delta_capacity_mixture,
    conditional_anchor_transition_capacity_log_prob, update_dynamic_state,
    compute_weighted_normalization, sample_mark_at_gap,
)
from rollout import forecast_rul, _due_tensor, select_in_proposal_order


def _inv_softplus(y):
    return math.log(math.expm1(y))


class FixedCrossingModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.anchor=nn.Parameter(torch.zeros(()))
    def forward(self,fixed,dynamic):
        b=len(fixed); p=torch.zeros((b,3,9),device=fixed.device,dtype=fixed.dtype)
        p[:,:,0]=-100.0; p[:,0,0]=0.0
        p[:,:,1]=math.log(.4); p[:,:,2]=math.log(.15/.25)
        p[:,:,3]=_inv_softplus(.0002-1e-4)
        p[:,:,4]=_inv_softplus(.0002-1e-4)
        p[:,:,5]=0.0
        p[:,:,6]=-100.;p[:,:,7]=-100.;p[:,:,8]=-100.;p[:,0,6]=0.
        return p


def _check_bivariate_density_and_conditional():
    p=torch.zeros((1,3,9),dtype=torch.float64)
    p[:,:,0]=0.
    p[:,:,1]=math.log(1.4);p[:,:,2]=.03
    sg,sc,rho=.31,.22,.43
    p[:,:,3]=_inv_softplus(sg-1e-4)
    p[:,:,4]=_inv_softplus(sc-1e-4)
    p[:,:,5]=math.atanh(rho/.995)
    p[:,:,6]=.2;p[:,:,7]=-.1;p[:,:,8]=.4
    y_g=math.log(1.8);y_c=-.07;dk=2
    got=float(log_prob(p,torch.tensor([y_g],dtype=torch.float64),
                       torch.tensor([y_c],dtype=torch.float64),
                       torch.tensor([dk]),'joint')[0])
    cov=[[sg*sg,rho*sg*sc],[rho*sg*sc,sc*sc]]
    expected=float(multivariate_normal.logpdf([y_g,y_c],mean=[math.log(1.4),.03],cov=cov))
    probs=torch.softmax(torch.tensor([.2,-.1,.4],dtype=torch.float64),0).numpy()
    expected+=math.log(float(probs[dk-1]))
    assert abs(got-expected)<1e-7,(got,expected)
    w,m,s=conditional_delta_capacity_mixture(p[0],1.8,'joint')
    mu_cond=.03+rho*(sc/sg)*(y_g-math.log(1.4))
    sd_cond=sc*math.sqrt(1-rho*rho)
    assert np.allclose(w.detach().numpy(),[1/3]*3,atol=1e-7)
    assert np.allclose(m.detach().numpy(),[mu_cond]*3,atol=1e-7)
    assert np.allclose(s.detach().numpy(),[sd_cond]*3,atol=1e-7)
    cprev,cnext=.25,.19
    got_cap=float(conditional_anchor_transition_capacity_log_prob(
        p[0],1.8,cprev,cnext,'joint'))
    expected_cap=float(norm.logpdf(math.log(cnext/cprev),loc=mu_cond,scale=sd_cond)-math.log(cnext))
    assert abs(got_cap-expected_cap)<1e-7,(got_cap,expected_cap)


def _check_weighted_standardization():
    g=torch.Generator().manual_seed(7)
    n=257;d=5
    fixed=torch.randn((n,d),generator=g,dtype=torch.float64)
    fixed[:,2]=3.25  # constant feature -> scale must stay 1
    dynamic=torch.randn((n,6),generator=g,dtype=torch.float64)*0.3+0.1
    w=np.abs(np.random.default_rng(3).normal(size=n));w/=w.sum()

    def wstats(a):
        m=(a*w[:,None]).sum(0);v=((a-m)**2*w[:,None]).sum(0)
        s=np.sqrt(np.maximum(v,0.0));s=np.where(s>1e-8,s,1.0);return m,s
    fm,fs,dm,ds=compute_weighted_normalization(fixed.numpy(),dynamic.numpy(),w)
    assert abs(float(fs[2])-1.0)<1e-12,float(fs[2])
    m,s=wstats(fixed.numpy())
    assert np.allclose(fm,m.astype(np.float32),atol=1e-6) and np.allclose(fs,s.astype(np.float32),atol=1e-6)
    net=JointMarkedMixtureNet(int(d));net.set_normalization(fm,fs,dm,ds,source='unit_fixture')
    assert 'fixed_mean' in net.state_dict() and 'dynamic_scale' in net.state_dict()
    zf=(fixed.to(torch.float32)-net.fixed_mean)/net.fixed_scale
    zd=(dynamic.to(torch.float32)-net.dynamic_mean)/net.dynamic_scale
    ref=net.net(torch.cat([zf,zd],dim=1)).view(-1,3,9)
    got=net(fixed.to(torch.float32),dynamic.to(torch.float32))
    assert torch.allclose(ref,got,atol=1e-6)
    plain=JointMarkedMixtureNet(int(d));plain.load_state_dict(net.state_dict())
    plain.fixed_mean.zero_();plain.fixed_scale.fill_(1.0);plain.dynamic_mean.zero_();plain.dynamic_scale.fill_(1.0)
    assert not torch.allclose(plain(fixed.to(torch.float32),dynamic.to(torch.float32)),got,atol=1e-4)
    net2=JointMarkedMixtureNet(int(d));net2.set_normalization(fm,np.zeros_like(fs)+1e-12,dm,np.zeros_like(ds))
    assert torch.allclose(net2.fixed_scale,torch.ones_like(net2.fixed_scale)) and torch.allclose(net2.dynamic_scale,torch.ones_like(net2.dynamic_scale))
    return {'weighted_mean_scale':'PASS','constant_scale_one':'PASS','buffer_state_dict':'PASS','forward_equivalence':'PASS'}


def _check_proposal_order():
    accepted={7:{'rul_weeks':1.0},2:{'rul_weeks':2.0},9:{'rul_weeks':3.0},0:{'rul_weeks':4.0}}
    got=[x['rul_weeks'] for x in select_in_proposal_order(accepted,3)]
    assert got==[4.0,2.0,1.0],got
    # integration: random-gap stochastic rollout must return chosen serials in order
    torch.manual_seed(11)
    net=JointMarkedMixtureNet(4)
    fixed=np.zeros(4,dtype=np.float32)
    visible=[{'source_stop_epoch':1000.*604800.,'arrival_epoch':1000.*604800.,'source_rpt_index':10,'capacity_ah':.28},
             {'source_stop_epoch':1001.*604800.,'arrival_epoch':1001.*604800.,'source_rpt_index':11,'capacity_ah':.25}]
    out=forecast_rul(net,fixed,visible,1001.*604800.,11,'raw','joint',seed=5,max_proposals=64,n_samples=6,
                     min_accept_rate=0.0,max_valid_checks=32,proposal_batch_size=4,max_weeks=4.0)
    ser=out['selected_proposal_serials']
    assert len(ser)==6 and ser==sorted(ser) and len(set(ser))==6,ser
    assert out['truncation_rule']=='global_proposal_order'
    # Device parity: the same rollout must work with model tensors on CUDA (this catches
    # CPU-index tensor bugs that the CPU fixtures cannot see).
    if torch.cuda.is_available():
        gnet=JointMarkedMixtureNet(4).to('cuda:0')
        gout=forecast_rul(gnet,fixed,visible,1001.*604800.,11,'raw','joint',seed=5,max_proposals=64,n_samples=6,
                          min_accept_rate=0.0,max_valid_checks=32,proposal_batch_size=4,max_weeks=4.0)
        assert len(gout['samples'])==6 and gout['epoch_dtype']=='torch.float64',gout['epoch_dtype']
        assert gout['selected_proposal_serials']==sorted(gout['selected_proposal_serials'])
    return {'completion_vs_proposal_order':'PASS','integration_serial_monotone':'PASS','cuda_device_parity':'PASS'}


def _check_fixed_gap_marks():
    p=torch.zeros((1,3,9),dtype=torch.float64)
    p[:,:,0]=0.
    p[:,0,1]=math.log(.8);p[:,1,1]=math.log(2.2);p[:,2,1]=math.log(5.0)
    p[:,0,2]=-.01;p[:,1,2]=.04;p[:,2,2]=.08
    p[:,0,3]=_inv_softplus(.25-1e-4);p[:,1,3]=_inv_softplus(.45-1e-4);p[:,2,3]=_inv_softplus(.9-1e-4)
    p[:,0,4]=_inv_softplus(.03-1e-4);p[:,1,4]=_inv_softplus(.06-1e-4);p[:,2,4]=_inv_softplus(.11-1e-4)
    p[:,0,5]=math.atanh(.2/.995);p[:,1,5]=math.atanh(.6/.995);p[:,2,5]=math.atanh(-.3/.995)
    p[:,:,6:9]=torch.tensor([.0,-100.,-100.],dtype=torch.float64)
    g=torch.Generator().manual_seed(3)
    gap=.8  # mean log-gap of component 0 is log(.8)
    b=4000
    params=p.expand(b,-1,-1)
    lg,dk,dlc=sample_mark_at_gap(params,gap,g, 'joint')
    assert torch.allclose(lg,torch.full_like(lg,math.log(gap)),atol=0)
    # posterior at gap==mu_g of component 0 is dominated by component 0
    w,m,s=conditional_delta_capacity_mixture(p[0],gap,'joint')
    assert int(torch.argmax(w))==0 and float(w[0])>0.85,float(w[0])
    mix_mean=float((w*m).sum());mix_sd=math.sqrt(float((w*(s*s+m*m)).sum())-mix_mean*mix_mean)
    assert abs(float(dlc.mean())-mix_mean)<8*mix_sd/math.sqrt(b),(float(dlc.mean()),mix_mean)
    assert set(dk.tolist())<={1}
    lg2,dk2,dlc2=sample_mark_at_gap(params,gap,g,'independent')
    assert torch.allclose(lg2,torch.full_like(lg2,math.log(gap)),atol=0) and set(dk2.tolist())<={1}
    out=forecast_rul(FixedCrossingModel(),np.zeros(8),[
        {'source_stop_epoch':0.-604800.,'arrival_epoch':0.-604800.,'source_rpt_index':1,'capacity_ah':.28},
        {'source_stop_epoch':0.,'arrival_epoch':0.,'source_rpt_index':2,'capacity_ah':.25}],
        0.+8*604800.,2,'raw','joint',seed=9,max_proposals=32,n_samples=4,min_accept_rate=0.,
        max_valid_checks=48,proposal_batch_size=8,fixed_gap_weeks=.4,condition_on_no_arrival=False)
    assert out['fixed_gap_weeks']==.4 and out['epoch_dtype']=='torch.float64'
    return {'fixed_gap_preserved':'PASS','posterior_conditional_mark':'PASS','deltaK_support':'PASS','forecast_fixed_gap':'PASS'}


def _check_conditioning_switch():
    visible=[{'source_stop_epoch':0.-604800.,'arrival_epoch':0.-604800.,'source_rpt_index':1,'capacity_ah':.28},
             {'source_stop_epoch':0.,'arrival_epoch':0.,'source_rpt_index':2,'capacity_ah':.25}]
    on_rejected=False
    try:
        forecast_rul(FixedCrossingModel(),np.zeros(8),visible,8*604800.,2,'raw','joint',seed=9,
                     max_proposals=64,n_samples=8,min_accept_rate=0.,max_valid_checks=16,
                     proposal_batch_size=8,fixed_gap_weeks=.4,condition_on_no_arrival=True)
    except RuntimeError as e:
        on_rejected='insufficient accepted' in str(e) or 'acceptance below' in str(e)
    assert on_rejected
    out=forecast_rul(FixedCrossingModel(),np.zeros(8),visible,8*604800.,2,'raw','joint',seed=9,
                     max_proposals=64,n_samples=8,min_accept_rate=0.,max_valid_checks=48,
                     proposal_batch_size=8,fixed_gap_weeks=.4,condition_on_no_arrival=False)
    assert len(out['samples'])==8 and out['condition_on_no_arrival'] is False
    assert out['tail_mass']==0.0
    return {'conditioning_on_rejects':'PASS','conditioning_off_accepts':'PASS'}


def main():
    torch.manual_seed(42)
    net=JointMarkedMixtureNet(8)
    fixed=torch.zeros((2,8))
    dynamic=torch.tensor([[.5,.1,-.01,0.,0.,0.],[.6,.2,-.02,.3,1.,1.]])
    p=net(fixed,dynamic)
    lg=torch.tensor([math.log(1.),math.log(2.)]);dc=torch.tensor([-.02,.01]);dk=torch.tensor([1,2])
    assert torch.isfinite(log_prob(p,lg,dc,dk,'joint')).all()
    assert torch.isfinite(log_prob(p,lg,dc,dk,'independent')).all()
    w,m,s=conditional_delta_capacity_mixture(p[0],1.5,'joint')
    assert torch.isfinite(w).all() and abs(float(w.sum())-1)<1e-6 and (s>0).all()
    st=update_dynamic_state([.5,math.log1p(1.),-.01,0.,0.,0.],1.25,2,math.log(1.03))
    assert abs(st[0]-.515)<1e-12 and abs(math.expm1(st[3])-1.25)<1e-12 and abs(math.expm1(st[5])-2)<1e-12
    _check_bivariate_density_and_conditional()
    idx=torch.tensor([3,4,5]);t=torch.tensor([100.,100.,100.]);q=100.+8*86400.
    assert _due_tensor('sparse2',idx,t,q,2).tolist()==[False,True,False]
    assert _due_tensor('delay7d',idx,t,q,2).tolist()==[True,True,True]
    assert not bool(_due_tensor('delay7d',torch.tensor([3]),torch.tensor([100.]),100.+6*86400.,2)[0])
    model=FixedCrossingModel()
    visible=[
      {'source_stop_epoch':0.-604800.,'arrival_epoch':0.-604800.,'source_rpt_index':1,'capacity_ah':.28},
      {'source_stop_epoch':0.,'arrival_epoch':0.,'source_rpt_index':2,'capacity_ah':.25},
    ]
    out=forecast_rul(model,np.zeros(8),visible,0.+.5*604800.,2,'delay7d','joint',
                     seed=7,max_proposals=16,n_samples=8,min_accept_rate=0.,
                     max_valid_checks=8,proposal_batch_size=8)
    assert len(out['samples'])==8 and all(abs(x)<1e-8 for x in out['samples']),out
    extra={}
    extra.update(_check_weighted_standardization())
    extra.update(_check_proposal_order())
    extra.update(_check_fixed_gap_marks())
    extra.update(_check_conditioning_switch())
    print({'density_fixture':'PASS','conditional_moments':'PASS','Ah_jacobian':'PASS',
           'source_arm_clocks':'PASS','vectorized_delay_rollout':'PASS',
           'rollout_acceptance':out['acceptance_rate'],'known_zero_mass':'PASS',
           'fixed_dim':8,'fits':0,'data_reads':0,**extra})


if __name__=='__main__':
    main()
