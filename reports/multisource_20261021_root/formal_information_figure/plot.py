"""Formal 2x2 information experiment: frozen saved metric visualization."""
from pathlib import Path
import sys,json,csv,hashlib,shutil
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path('/home/yndx/zxk/rul');D=R/'reports/multisource_20261021_root/formal_information_figure';E=R/'experiments/multisource_factorial_20261021/run2_clocksafe'
Q=R/'reports/multisource_20261021_literature/information_figure/qa_scripts';sys.path.insert(0,str(Q))
from audit_panel_alignment import require_matplotlib_panel_alignment
G=json.loads((D/'ROOT_GO.json').read_text());assert G['status']=='APPROVED'
for p,h in G['input_sha256'].items():assert hashlib.sha256((R/p).read_bytes()).hexdigest()==h
S=list(csv.DictReader((E/'arm_summary.csv').open()));C=list(csv.DictReader((E/'cell_metrics.csv').open()));N=list(csv.DictReader((E/'no_new_rpt_pairs.csv').open()))
A=['raw','sparse2','delay7d'];AL=['Full RPT','Sparse RPT','7-day delay'];F=['hgb','catboost'];FL=['HGB','CatBoost'];colors=['#777777','#0072B2','#D55E00','#009E73'];markers=['o','s','^','D']
def savecsv(name,rows):
 with (D/name).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def ci(v):
 v=np.array(v,float);v=v[np.isfinite(v)];assert len(v)>0
 rng=np.random.default_rng(20261021);m=float(v.mean());lo,hi=np.quantile(rng.choice(v,(4000,len(v)),replace=True).mean(1),[.025,.975]);return m,float(lo),float(hi),len(v)
lookup={(r['model'],r['arm'],r['cell_id']):r for r in C if r['stratum']=='all'}
def effect(fam,cand,ref,metric,arms):
 per={}
 for (m,a,c),r in lookup.items():
  if m!=fam+'_'+cand or a not in arms:continue
  b=lookup[(fam+'_'+ref,a,c)]
  if r[metric]=='' or b[metric]=='':continue
  v=float(r[metric])-float(b[metric])
  if metric=='coverage80':v=abs(float(r[metric])-.8)-abs(float(b[metric])-.8)
  if np.isfinite(v):per.setdefault(c,[]).append(v)
 return ci([np.mean(v) for v in per.values()])
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':6.8,'axes.titlesize':7.4,'axes.labelsize':7,'xtick.labelsize':6.5,'ytick.labelsize':6.5,'pdf.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.6})
fig,axs=plt.subplots(3,2,figsize=(183/25.4,185/25.4),gridspec_kw={'hspace':.69,'wspace':.52});fig.subplots_adjust(left=.19,right=.985,bottom=.17,top=.92)
source=[]
for k,(fam,lab) in enumerate(zip(F,FL)):
 ax=axs[0,k]
 for j,p in enumerate(['F0','F1','F2','F3']):
  vv=[float(next(r for r in S if r['model']==fam+'_'+p and r['arm']==a and r['stratum']=='all')['mean_abs_error']) for a in A]
  ax.scatter(np.arange(3)+(j-1.5)*.14,vv,c=colors[j],marker=markers[j],s=19,label=p,zorder=3)
  for a,v in zip(A,vv):source.append(dict(panel=chr(97+k),model=fam,contrast=p,arm=a,metric='MAE_weeks',mean=v,ci_lo='',ci_hi='',n=61))
 ax.set(xticks=range(3),xticklabels=AL,ylim=(0,2.75),xlim=(-.4,2.4),ylabel='RUL MAE (weeks)',title=lab);ax.set_yticks([0,1,2]);ax.grid(axis='y',color='.93',lw=.5)
 if k==0:ax.legend(ncol=4,frameon=False,loc='upper left',bbox_to_anchor=(-.13,1.47),fontsize=6.3,handletextpad=.15,columnspacing=.6)
ax=axs[1,0];ticks=[]
controls=[('control_capacity_normalized_shape_only','F0','Shape / summary'),('control_cycle_vi_e_time_only','F0','VI + time / summary')]
for j,(cand,ref,label) in enumerate(controls):
 for k,fam in enumerate(F):
  y=j*2+k;m,lo,hi,n=effect(fam,cand,ref,'mean_abs_error',A);ax.errorbar(m,y,xerr=[[m-lo],[hi-m]],fmt=markers[k],color=colors[k+1],capsize=2,lw=.8,ms=3);ticks.append(label+'\n'+FL[k]);source.append(dict(panel='c',model=fam,contrast=cand+' minus '+ref,arm='cell average of 3 arms',metric='MAE_weeks_delta',mean=m,ci_lo=lo,ci_hi=hi,n=n))
ax.set(yticks=range(4),yticklabels=ticks,xlabel='MAE difference (weeks)',title='Capacity controls',xlim=(-.8,.25),ylim=(3.7,-.7));ax.axvline(0,color='.55',ls='--',lw=.6)
ax=axs[1,1];ticks=[]
for j,pair in enumerate(['F0_time_only_to_F2_updated','F1_time_only_to_F3_updated']):
 for k,fam in enumerate(F):
  rr=[r for r in N if r['factor_pair']==pair and r['model']==fam];per={}
  for r in rr:
   try:v=float(r['source_updated_mean_abs_error'])-float(r['time_shifted_mean_abs_error'])
   except ValueError:continue
   if np.isfinite(v):per.setdefault(r['cell_id'],[]).append(v)
  m,lo,hi,n=ci([np.mean(v) for v in per.values()]);y=j*2+k;ax.errorbar(m,y,xerr=[[m-lo],[hi-m]],fmt=markers[k],color=colors[k+1],capsize=2,lw=.8,ms=3);ticks.append(['F2 / transported F0','F3 / transported F1'][j]+'\n'+FL[k]);source.append(dict(panel='d',model=fam,contrast=pair,arm='sparse2 same RPT history pairs',metric='MAE_weeks_delta',mean=m,ci_lo=lo,ci_hi=hi,n=n))
ax.set(yticks=range(4),yticklabels=ticks,xlabel='MAE difference (weeks)',title='No new RPT between queries',xlim=(-.85,.25),ylim=(3.7,-.7));ax.axvline(0,color='.55',ls='--',lw=.6)
for col,metric,title,xlabel in [(0,'coverage80','Nominal-coverage error','Change in |coverage - 0.80|'),(1,'severe_gt4w','Severe RUL overestimation','Change in fraction > 4 weeks')]:
 ax=axs[2,col];ticks=[]
 for j,a in enumerate(A):
  for k,fam in enumerate(F):
   y=j*2+k;m,lo,hi,n=effect(fam,'F3','F0',metric,[a]);ax.errorbar(m,y,xerr=[[m-lo],[hi-m]],fmt=markers[k],color=colors[k+1],capsize=2,lw=.8,ms=3);ticks.append(AL[j]+' / '+FL[k]);source.append(dict(panel='ef'[col],model=fam,contrast='F3 minus F0',arm=a,metric=metric+'_delta',mean=m,ci_lo=lo,ci_hi=hi,n=n))
 ax.set(yticks=range(6),yticklabels=ticks,xlabel=xlabel,title=title,ylim=(5.7,-.7));ax.axvline(0,color='.55',ls='--',lw=.6)
for letter,ax in zip('abcdef',axs.flat):ax.text(-.11,1.10,letter,transform=ax.transAxes,fontweight='bold',fontsize=8,va='bottom');ax.tick_params(length=2.5,width=.6)
fig.text(.19,.025,'C3 development, seed 42. F0: summary; F1: + RPT; F2: + Cycling; F3: both.\nPanels c-f: mean and 95% physical-cell bootstrap CI; left of zero is favorable.\nPanel d: exact elapsed-time transport of saved distributions; no claim of causal state identification.',fontsize=6.2,linespacing=1.4)
fig.canvas.draw();require_matplotlib_panel_alignment(fig,json_out=D/'alignment.json',tolerance_pt=1.5)
for ext in ['pdf','svg','png']:fig.savefig(D/('formal_information.'+ext),dpi=300)
plt.close(fig);savecsv('figure_source.csv',source)
contract={'claim':'New raw RPT and Cycling signals improve development MAE, with capacity controls and explicit reliability tradeoffs.','dimensions_mm':[183,185],'scope':'C3 same-condition new cells, one seed, no independent confirmation. 61 observed-event cells for MAE; 62 cells for event metrics.','factorial':'F0=74;F1=F0+RPT;F2=F0+Cycling;F3=all','uncertainty':'4000 physical-cell percentile bootstrap draws seed20261021. c averages three arms within cell first. d aggregates repeated same-history pairs within cell first. a/b descriptive aggregates, no seed CI.','inputs':G['input_sha256'],'counterfactual_limits':'Cycle availability assumed at source completion because transmission times absent. Shape normalized by matching arrived leg capacity. VI/time panel removes six Q/throughput variables but retains observed cycle count.','panel_roles':dict(zip('abcdef',['HGB2x2','CatBoost2x2','capacitycontrols','nonewRPT','coverageerror','severeover']))}
(D/'figure_contract.json').write_text(json.dumps(contract,indent=2)+'\n');print('exported',len(source),'source rows')
